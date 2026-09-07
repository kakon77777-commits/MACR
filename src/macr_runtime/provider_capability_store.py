from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .canonical import canonical_json_bytes
from .direct_database import DirectDatabase
from .errors import DirectStoreConflict
from .provider_capability import (
    ProviderCapabilityPolicy,
    ProviderCapabilityResolver,
    ProviderTierBinding,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OperatorTierActivationVerifier(Protocol):
    def verify(self, *, witness: str, binding_digest: str) -> None: ...


def _encode_policy(policy: ProviderCapabilityPolicy) -> tuple[str, str]:
    body = canonical_json_bytes(policy.to_dict()).decode("utf-8")
    return body, hashlib.sha256(body.encode("utf-8")).hexdigest()


def _policy_from_row(row: sqlite3.Row) -> ProviderCapabilityPolicy:
    expected_body_sha256 = hashlib.sha256(
        row["body_json"].encode("utf-8")
    ).hexdigest()
    if expected_body_sha256 != row["body_sha256"]:
        raise DirectStoreConflict("provider capability policy digest is invalid")
    try:
        policy = ProviderCapabilityPolicy.from_dict(json.loads(row["body_json"]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DirectStoreConflict(
            "provider capability policy digest is invalid"
        ) from exc
    canonical, body_sha256 = _encode_policy(policy)
    binding = policy.binding()
    if (
        canonical != row["body_json"]
        or body_sha256 != row["body_sha256"]
        or binding.binding_digest != row["binding_digest"]
    ):
        raise DirectStoreConflict("provider capability policy digest is invalid")
    return policy


def _binding_from_row(row: sqlite3.Row) -> ProviderTierBinding:
    return _policy_from_row(row).binding()


def _read_effective_from_connection(
    connection: sqlite3.Connection,
    resolver: ProviderCapabilityResolver,
    provider_id: str,
    model_id: str,
) -> ProviderTierBinding:
    active = connection.execute(
        """SELECT tier_id, revision, binding_digest
        FROM provider_capability_active
        WHERE provider_id = ? AND model_id = ?""",
        (provider_id, model_id),
    ).fetchone()
    if active is None:
        return resolver.default_binding(provider_id, model_id)
    row = connection.execute(
        """SELECT body_json, body_sha256, binding_digest
        FROM provider_capability_policies
        WHERE provider_id = ? AND model_id = ?
          AND tier_id = ? AND revision = ?""",
        (provider_id, model_id, active["tier_id"], active["revision"]),
    ).fetchone()
    if row is None or row["binding_digest"] != active["binding_digest"]:
        raise DirectStoreConflict("provider capability activation is invalid")
    return _binding_from_row(row)


def _read_effective_policy_from_connection(
    connection: sqlite3.Connection,
    resolver: ProviderCapabilityResolver,
    provider_id: str,
    model_id: str,
) -> ProviderCapabilityPolicy:
    active = connection.execute(
        """SELECT tier_id, revision, binding_digest
        FROM provider_capability_active
        WHERE provider_id = ? AND model_id = ?""",
        (provider_id, model_id),
    ).fetchone()
    if active is None:
        return resolver.resolve(provider_id, model_id, "standard", 1)
    row = connection.execute(
        """SELECT body_json, body_sha256, binding_digest
        FROM provider_capability_policies
        WHERE provider_id = ? AND model_id = ?
          AND tier_id = ? AND revision = ?""",
        (provider_id, model_id, active["tier_id"], active["revision"]),
    ).fetchone()
    if row is None or row["binding_digest"] != active["binding_digest"]:
        raise DirectStoreConflict("provider capability activation is invalid")
    return _policy_from_row(row)


class ProviderCapabilityPolicyStore:
    SCHEMA_VERSION = 1

    def __init__(
        self,
        path: str | Path,
        *,
        resolver: ProviderCapabilityResolver | None = None,
    ) -> None:
        self.database = DirectDatabase(path)
        self.resolver = resolver or ProviderCapabilityResolver.builtins_only()
        self._initialize()

    @property
    def path(self) -> Path:
        return self.database.path

    def _initialize(self) -> None:
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS provider_capability_schema_meta (
                    component TEXT PRIMARY KEY,
                    version INTEGER NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS provider_capability_policies (
                    provider_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    tier_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK(revision >= 1),
                    body_json TEXT NOT NULL,
                    body_sha256 TEXT NOT NULL,
                    binding_digest TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(provider_id, model_id, tier_id, revision)
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS provider_capability_active (
                    provider_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    tier_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    binding_digest TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(provider_id, model_id),
                    FOREIGN KEY(provider_id, model_id, tier_id, revision)
                        REFERENCES provider_capability_policies(
                            provider_id, model_id, tier_id, revision
                        )
                )"""
            )
            row = connection.execute(
                """SELECT version FROM provider_capability_schema_meta
                WHERE component = 'provider_capability_policies'"""
            ).fetchone()
            if row is None:
                connection.execute(
                    """INSERT INTO provider_capability_schema_meta(component, version)
                    VALUES ('provider_capability_policies', ?)""",
                    (self.SCHEMA_VERSION,),
                )
            elif row["version"] != self.SCHEMA_VERSION:
                raise DirectStoreConflict(
                    "provider capability policy database schema is unsupported"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save_policy(self, policy: ProviderCapabilityPolicy) -> bool:
        if not isinstance(policy, ProviderCapabilityPolicy):
            raise ValueError("policy must be a ProviderCapabilityPolicy")
        body, body_sha256 = _encode_policy(policy)
        binding_digest = policy.binding().binding_digest
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT body_json, body_sha256, binding_digest
                FROM provider_capability_policies
                WHERE provider_id = ? AND model_id = ?
                  AND tier_id = ? AND revision = ?""",
                (
                    policy.provider_id,
                    policy.model_id,
                    policy.tier_id,
                    policy.revision,
                ),
            ).fetchone()
            inserted = row is None
            if row is None:
                connection.execute(
                    """INSERT INTO provider_capability_policies(
                        provider_id, model_id, tier_id, revision,
                        body_json, body_sha256, binding_digest, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        policy.provider_id,
                        policy.model_id,
                        policy.tier_id,
                        policy.revision,
                        body,
                        body_sha256,
                        binding_digest,
                        _utc_now(),
                    ),
                )
            elif (
                row["body_json"] != body
                or row["body_sha256"] != body_sha256
                or row["binding_digest"] != binding_digest
            ):
                raise DirectStoreConflict(
                    "provider capability policy revision conflicts with existing record"
                )
            connection.commit()
            return inserted
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def activate(
        self,
        binding_digest: str,
        *,
        witness: str,
        verifier: OperatorTierActivationVerifier,
    ) -> None:
        if not isinstance(binding_digest, str):
            raise DirectStoreConflict("provider capability binding digest is invalid")
        connection = self.database.connect()
        try:
            row = connection.execute(
                """SELECT provider_id, model_id, tier_id, revision,
                          body_json, body_sha256, binding_digest
                FROM provider_capability_policies
                WHERE binding_digest = ?""",
                (binding_digest,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise DirectStoreConflict("provider capability policy does not exist")
        binding = _binding_from_row(row)
        verifier.verify(witness=witness, binding_digest=binding.binding_digest)

        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                """SELECT body_json, body_sha256, binding_digest
                FROM provider_capability_policies
                WHERE provider_id = ? AND model_id = ?
                  AND tier_id = ? AND revision = ?""",
                (
                    binding.provider_id,
                    binding.model_id,
                    binding.tier_id,
                    binding.revision,
                ),
            ).fetchone()
            if current is None or _binding_from_row(current) != binding:
                raise DirectStoreConflict("provider capability policy changed")
            connection.execute(
                """INSERT INTO provider_capability_active(
                    provider_id, model_id, tier_id, revision,
                    binding_digest, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_id, model_id) DO UPDATE SET
                    tier_id = excluded.tier_id,
                    revision = excluded.revision,
                    binding_digest = excluded.binding_digest,
                    updated_at = excluded.updated_at""",
                (
                    binding.provider_id,
                    binding.model_id,
                    binding.tier_id,
                    binding.revision,
                    binding.binding_digest,
                    _utc_now(),
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def effective_binding(
        self,
        provider_id: str,
        model_id: str,
    ) -> ProviderTierBinding:
        connection = self.database.connect()
        try:
            return _read_effective_from_connection(
                connection,
                self.resolver,
                provider_id,
                model_id,
            )
        finally:
            connection.close()

    def effective_policy(
        self,
        provider_id: str,
        model_id: str,
    ) -> ProviderCapabilityPolicy:
        connection = self.database.connect()
        try:
            return _read_effective_policy_from_connection(
                connection,
                self.resolver,
                provider_id,
                model_id,
            )
        finally:
            connection.close()


def read_effective_binding(
    path: str | Path,
    provider_id: str,
    model_id: str,
    *,
    resolver: ProviderCapabilityResolver | None = None,
) -> ProviderTierBinding:
    candidate = Path(path)
    selected = resolver or ProviderCapabilityResolver.builtins_only()
    if not candidate.exists():
        return selected.default_binding(provider_id, model_id)
    uri = candidate.absolute().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """SELECT version FROM provider_capability_schema_meta
            WHERE component = 'provider_capability_policies'"""
        ).fetchone()
        if row is None or row["version"] != ProviderCapabilityPolicyStore.SCHEMA_VERSION:
            raise DirectStoreConflict(
                "provider capability policy database schema is unsupported"
            )
        return _read_effective_from_connection(
            connection,
            selected,
            provider_id,
            model_id,
        )
    except sqlite3.Error as exc:
        raise DirectStoreConflict(
            "provider capability policy database is invalid"
        ) from exc
    finally:
        connection.close()


def read_effective_policy(
    path: str | Path,
    provider_id: str,
    model_id: str,
    *,
    resolver: ProviderCapabilityResolver | None = None,
) -> ProviderCapabilityPolicy:
    candidate = Path(path)
    selected = resolver or ProviderCapabilityResolver.builtins_only()
    if not candidate.exists():
        return selected.resolve(provider_id, model_id, "standard", 1)
    uri = candidate.absolute().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """SELECT version FROM provider_capability_schema_meta
            WHERE component = 'provider_capability_policies'"""
        ).fetchone()
        if row is None or row["version"] != ProviderCapabilityPolicyStore.SCHEMA_VERSION:
            raise DirectStoreConflict(
                "provider capability policy database schema is unsupported"
            )
        return _read_effective_policy_from_connection(
            connection,
            selected,
            provider_id,
            model_id,
        )
    except sqlite3.Error as exc:
        raise DirectStoreConflict(
            "provider capability policy database is invalid"
        ) from exc
    finally:
        connection.close()


__all__ = [
    "OperatorTierActivationVerifier",
    "ProviderCapabilityPolicyStore",
    "read_effective_binding",
    "read_effective_policy",
]
