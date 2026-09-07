from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .canonical import canonical_json_bytes, sha256_id
from .direct_database import DirectDatabase
from .errors import (
    DirectStoreConflict,
    LegacyOutputPolicyIncompatibleError,
    ProviderPolicyError,
    StoragePolicyError,
)
from .token_policy import (
    ModelTokenOverride,
    ModelTokenPolicy,
    ModelTokenPolicyResolver,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_status() -> dict[str, int]:
    return {
        "current_count": 0,
        "legacy_pre_quality_floor_count": 0,
        "invalid_count": 0,
        "active_current_count": 0,
        "active_legacy_pre_quality_floor_count": 0,
        "active_invalid_count": 0,
        "total_count": 0,
    }


def _legacy_v1_base_digest(policy: ModelTokenPolicy) -> str:
    document = policy.to_dict()
    document.pop("minimum_task_output_tokens")
    return sha256_id("model_token_policy_v1", document)


def _base_binding_kind(
    override: ModelTokenOverride,
    base: ModelTokenPolicy,
) -> str:
    if override.base_policy_digest == base.policy_digest:
        return "current"
    if override.base_policy_digest == _legacy_v1_base_digest(base):
        return "legacy_pre_quality_floor"
    return "invalid"


class ModelTokenPolicyStore:
    SCHEMA_VERSION = 1

    def __init__(
        self,
        path: str | Path,
        *,
        resolver: ModelTokenPolicyResolver | None = None,
    ) -> None:
        self.database = DirectDatabase(path)
        self.resolver = resolver or ModelTokenPolicyResolver.builtins_only()
        self._initialize()

    @property
    def path(self) -> Path:
        return self.database.path

    def _initialize(self) -> None:
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS model_token_schema_meta (
                    component TEXT PRIMARY KEY,
                    version INTEGER NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS model_token_overrides (
                    provider_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK(revision >= 1),
                    body_json TEXT NOT NULL,
                    body_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(provider_id, model_id, revision)
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS model_token_active (
                    provider_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(provider_id, model_id),
                    FOREIGN KEY(provider_id, model_id, revision)
                        REFERENCES model_token_overrides(
                            provider_id, model_id, revision
                        )
                )"""
            )
            row = connection.execute(
                """SELECT version FROM model_token_schema_meta
                WHERE component = 'model_token_policies'"""
            ).fetchone()
            if row is None:
                connection.execute(
                    """INSERT INTO model_token_schema_meta(component, version)
                    VALUES ('model_token_policies', ?)""",
                    (self.SCHEMA_VERSION,),
                )
            elif row["version"] != self.SCHEMA_VERSION:
                raise DirectStoreConflict(
                    "model token policy database schema is unsupported"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _encode(override: ModelTokenOverride) -> tuple[str, str]:
        body = canonical_json_bytes(override.to_dict()).decode("utf-8")
        return body, hashlib.sha256(body.encode("utf-8")).hexdigest()

    @classmethod
    def _decode_override(
        cls,
        body_json: str,
        body_sha256: str,
    ) -> ModelTokenOverride:
        expected = hashlib.sha256(body_json.encode("utf-8")).hexdigest()
        if expected != body_sha256:
            raise DirectStoreConflict("model token override digest is invalid")
        try:
            document = json.loads(body_json)
            override = ModelTokenOverride.from_dict(document)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DirectStoreConflict(
                "model token override digest is invalid"
            ) from exc
        canonical, digest = cls._encode(override)
        if canonical != body_json or digest != body_sha256:
            raise DirectStoreConflict("model token override digest is invalid")
        return override

    @classmethod
    def _status_from_connection(
        cls,
        connection: sqlite3.Connection,
        resolver: ModelTokenPolicyResolver,
    ) -> dict[str, int]:
        counts = _empty_status()
        rows = connection.execute(
            """SELECT o.body_json, o.body_sha256,
                      CASE WHEN a.revision IS NULL THEN 0 ELSE 1 END AS active
            FROM model_token_overrides o
            LEFT JOIN model_token_active a
              ON a.provider_id = o.provider_id
             AND a.model_id = o.model_id
             AND a.revision = o.revision
            ORDER BY o.provider_id, o.model_id, o.revision"""
        ).fetchall()
        counts["total_count"] = len(rows)
        for row in rows:
            try:
                override = cls._decode_override(
                    row["body_json"],
                    row["body_sha256"],
                )
                base = resolver.resolve(override.provider_id, override.model_id)
            except (DirectStoreConflict, ProviderPolicyError, ValueError):
                counts["invalid_count"] += 1
                continue
            binding_kind = _base_binding_kind(override, base)
            if binding_kind == "current":
                counts["current_count"] += 1
                if row["active"]:
                    counts["active_current_count"] += 1
            elif binding_kind == "legacy_pre_quality_floor":
                counts["legacy_pre_quality_floor_count"] += 1
                if row["active"]:
                    counts["active_legacy_pre_quality_floor_count"] += 1
            else:
                counts["invalid_count"] += 1
                if row["active"]:
                    counts["active_invalid_count"] += 1
        return counts

    def status_snapshot(self) -> dict[str, int]:
        connection = self.database.connect()
        try:
            return self._status_from_connection(connection, self.resolver)
        finally:
            connection.close()

    def save_override(
        self,
        override: ModelTokenOverride,
        *,
        activate: bool,
    ) -> bool:
        if not isinstance(override, ModelTokenOverride):
            raise ValueError("override must be a ModelTokenOverride")
        if not isinstance(activate, bool):
            raise ValueError("activate must be boolean")
        base = self.resolver.resolve(override.provider_id, override.model_id)
        override.apply(base)
        body, digest = self._encode(override)
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT body_json, body_sha256 FROM model_token_overrides
                WHERE provider_id = ? AND model_id = ? AND revision = ?""",
                (override.provider_id, override.model_id, override.revision),
            ).fetchone()
            inserted = row is None
            if row is None:
                connection.execute(
                    """INSERT INTO model_token_overrides(
                        provider_id, model_id, revision, body_json,
                        body_sha256, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        override.provider_id,
                        override.model_id,
                        override.revision,
                        body,
                        digest,
                        _utc_now(),
                    ),
                )
            elif row["body_json"] != body or row["body_sha256"] != digest:
                raise DirectStoreConflict(
                    "model token override revision conflicts with existing record"
                )
            if activate:
                connection.execute(
                    """INSERT INTO model_token_active(
                        provider_id, model_id, revision, updated_at
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(provider_id, model_id) DO UPDATE SET
                        revision = excluded.revision,
                        updated_at = excluded.updated_at""",
                    (
                        override.provider_id,
                        override.model_id,
                        override.revision,
                        _utc_now(),
                    ),
                )
            connection.commit()
            return inserted
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def activate(self, provider_id: str, model_id: str, revision: int) -> None:
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT body_json, body_sha256 FROM model_token_overrides
                WHERE provider_id = ? AND model_id = ? AND revision = ?""",
                (provider_id, model_id, revision),
            ).fetchone()
            if row is None:
                raise DirectStoreConflict("model token override does not exist")
            override = self._decode_override(
                row["body_json"],
                row["body_sha256"],
            )
            base = self.resolver.resolve(override.provider_id, override.model_id)
            binding_kind = _base_binding_kind(override, base)
            if binding_kind == "legacy_pre_quality_floor":
                raise LegacyOutputPolicyIncompatibleError(
                    "legacy_pre_quality_floor: model token override must be "
                    "reissued against policy contract v2"
                )
            if binding_kind == "invalid":
                raise DirectStoreConflict(
                    "model token override base policy digest is invalid"
                )
            connection.execute(
                """INSERT INTO model_token_active(
                    provider_id, model_id, revision, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(provider_id, model_id) DO UPDATE SET
                    revision = excluded.revision,
                    updated_at = excluded.updated_at""",
                (provider_id, model_id, revision, _utc_now()),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _read_active_override(
        self,
        provider_id: str,
        model_id: str,
    ) -> ModelTokenOverride | None:
        connection = self.database.connect()
        try:
            row = connection.execute(
                """SELECT o.body_json, o.body_sha256
                FROM model_token_active a
                JOIN model_token_overrides o
                  ON o.provider_id = a.provider_id
                 AND o.model_id = a.model_id
                 AND o.revision = a.revision
                WHERE a.provider_id = ? AND a.model_id = ?""",
                (provider_id, model_id),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return self._decode_override(row["body_json"], row["body_sha256"])

    def effective_policy(
        self,
        provider_id: str,
        model_id: str,
    ) -> ModelTokenPolicy:
        base = self.resolver.resolve(provider_id, model_id)
        override = self._read_active_override(provider_id, model_id)
        if override is None:
            return base
        binding_kind = _base_binding_kind(override, base)
        if binding_kind == "legacy_pre_quality_floor":
            raise LegacyOutputPolicyIncompatibleError(
                "legacy_pre_quality_floor: active model token override must be "
                "reissued against policy contract v2"
            )
        if binding_kind == "invalid":
            raise DirectStoreConflict(
                "model token override base policy digest is invalid"
            )
        try:
            return override.apply(base)
        except ValueError as exc:
            raise DirectStoreConflict("model token override is invalid") from exc

    def list_effective(self) -> tuple[ModelTokenPolicy, ...]:
        return tuple(
            self.effective_policy(item.provider_id, item.model_id)
            for item in self.resolver.policies()
        )


def read_model_token_override_status(path: str | Path) -> dict[str, int]:
    candidate = Path(path)
    if not candidate.is_absolute() or candidate.drive.upper() != "D:":
        raise StoragePolicyError(
            "model token policy database path must be absolute on D:"
        )
    database_path = candidate.absolute()
    if not database_path.is_file():
        return _empty_status()
    try:
        connection = sqlite3.connect(
            f"file:{database_path.as_posix()}?mode=ro",
            uri=True,
        )
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """SELECT version FROM model_token_schema_meta
            WHERE component = 'model_token_policies'"""
        ).fetchone()
        if row is None or row["version"] != ModelTokenPolicyStore.SCHEMA_VERSION:
            raise DirectStoreConflict(
                "model token policy database schema is unsupported"
            )
        return ModelTokenPolicyStore._status_from_connection(
            connection,
            ModelTokenPolicyResolver.builtins_only(),
        )
    except sqlite3.Error as exc:
        raise DirectStoreConflict("model token policy database is invalid") from exc
    finally:
        if "connection" in locals():
            connection.close()


__all__ = ["ModelTokenPolicyStore", "read_model_token_override_status"]
