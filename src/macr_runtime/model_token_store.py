from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .canonical import canonical_json_bytes
from .direct_database import DirectDatabase
from .errors import DirectStoreConflict
from .token_policy import (
    ModelTokenOverride,
    ModelTokenPolicy,
    ModelTokenPolicyResolver,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
                """SELECT 1 FROM model_token_overrides
                WHERE provider_id = ? AND model_id = ? AND revision = ?""",
                (provider_id, model_id, revision),
            ).fetchone()
            if row is None:
                raise DirectStoreConflict("model token override does not exist")
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
        expected = hashlib.sha256(row["body_json"].encode("utf-8")).hexdigest()
        if expected != row["body_sha256"]:
            raise DirectStoreConflict("model token override digest is invalid")
        try:
            document = json.loads(row["body_json"])
            override = ModelTokenOverride.from_dict(document)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DirectStoreConflict("model token override digest is invalid") from exc
        canonical, digest = self._encode(override)
        if canonical != row["body_json"] or digest != row["body_sha256"]:
            raise DirectStoreConflict("model token override digest is invalid")
        return override

    def effective_policy(
        self,
        provider_id: str,
        model_id: str,
    ) -> ModelTokenPolicy:
        base = self.resolver.resolve(provider_id, model_id)
        override = self._read_active_override(provider_id, model_id)
        return base if override is None else override.apply(base)

    def list_effective(self) -> tuple[ModelTokenPolicy, ...]:
        return tuple(
            self.effective_policy(item.provider_id, item.model_id)
            for item in self.resolver.policies()
        )


__all__ = ["ModelTokenPolicyStore"]
