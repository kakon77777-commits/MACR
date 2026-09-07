from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .canonical import canonical_json_bytes
from .authority import DispatchAuthorityStore
from .direct_database import DirectDatabase
from .errors import DirectStoreConflict, ProviderPolicyError
from .execution import AuthorizationReference
from .provider_capability import (
    ProviderCapabilityPolicy,
    ProviderCapabilityResolver,
    ProviderTierBinding,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, init=False)
class _TierActivationPermit:
    binding_digest: str
    authority_digest: str

    @classmethod
    def _issue(
        cls,
        *,
        binding_digest: str,
        authority_digest: str,
    ) -> "_TierActivationPermit":
        instance = object.__new__(cls)
        object.__setattr__(instance, "binding_digest", binding_digest)
        object.__setattr__(instance, "authority_digest", authority_digest)
        return instance


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


def _require_supported_policy(
    resolver: ProviderCapabilityResolver,
    policy: ProviderCapabilityPolicy,
) -> ProviderCapabilityPolicy:
    try:
        supported = resolver.resolve(
            policy.provider_id,
            policy.model_id,
            policy.tier_id,
            policy.revision,
        )
    except ProviderPolicyError as exc:
        raise DirectStoreConflict(
            "provider capability policy is not adapter-supported"
        ) from exc
    if supported != policy:
        raise DirectStoreConflict(
            "provider capability policy is not adapter-supported"
        )
    return policy


def _read_effective_from_connection(
    connection: sqlite3.Connection,
    resolver: ProviderCapabilityResolver,
    provider_id: str,
    model_id: str,
) -> ProviderTierBinding:
    active = connection.execute(
        """SELECT tier_id, revision, binding_digest, authority_digest
        FROM provider_capability_active
        WHERE provider_id = ? AND model_id = ?""",
        (provider_id, model_id),
    ).fetchone()
    if active is None:
        return resolver.default_binding(provider_id, model_id)
    if (
        not isinstance(active["authority_digest"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", active["authority_digest"])
    ):
        raise DirectStoreConflict(
            "legacy_pre_tier provider capability activation is incompatible"
        )
    row = connection.execute(
        """SELECT body_json, body_sha256, binding_digest
        FROM provider_capability_policies
        WHERE provider_id = ? AND model_id = ?
          AND tier_id = ? AND revision = ?""",
        (provider_id, model_id, active["tier_id"], active["revision"]),
    ).fetchone()
    if row is None or row["binding_digest"] != active["binding_digest"]:
        raise DirectStoreConflict("provider capability activation is invalid")
    return _require_supported_policy(resolver, _policy_from_row(row)).binding()


def _read_effective_policy_from_connection(
    connection: sqlite3.Connection,
    resolver: ProviderCapabilityResolver,
    provider_id: str,
    model_id: str,
) -> ProviderCapabilityPolicy:
    active = connection.execute(
        """SELECT tier_id, revision, binding_digest, authority_digest
        FROM provider_capability_active
        WHERE provider_id = ? AND model_id = ?""",
        (provider_id, model_id),
    ).fetchone()
    if active is None:
        return resolver.resolve(provider_id, model_id, "standard", 1)
    if (
        not isinstance(active["authority_digest"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", active["authority_digest"])
    ):
        raise DirectStoreConflict(
            "legacy_pre_tier provider capability activation is incompatible"
        )
    row = connection.execute(
        """SELECT body_json, body_sha256, binding_digest
        FROM provider_capability_policies
        WHERE provider_id = ? AND model_id = ?
          AND tier_id = ? AND revision = ?""",
        (provider_id, model_id, active["tier_id"], active["revision"]),
    ).fetchone()
    if row is None or row["binding_digest"] != active["binding_digest"]:
        raise DirectStoreConflict("provider capability activation is invalid")
    return _require_supported_policy(resolver, _policy_from_row(row))


class ProviderCapabilityPolicyStore:
    SCHEMA_VERSION = 2

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
                    authority_digest TEXT,
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
            elif row["version"] == 1:
                columns = {
                    item[1]
                    for item in connection.execute(
                        "PRAGMA table_info(provider_capability_active)"
                    ).fetchall()
                }
                if "authority_digest" not in columns:
                    connection.execute(
                        """ALTER TABLE provider_capability_active
                        ADD COLUMN authority_digest TEXT"""
                    )
                connection.execute(
                    """UPDATE provider_capability_schema_meta SET version = ?
                    WHERE component = 'provider_capability_policies'""",
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
        try:
            supported = self.resolver.resolve(
                policy.provider_id,
                policy.model_id,
                policy.tier_id,
                policy.revision,
            )
        except ProviderPolicyError as exc:
            raise DirectStoreConflict(
                "provider capability policy is not adapter-supported"
            ) from exc
        if supported != policy:
            raise DirectStoreConflict(
                "provider capability policy is not adapter-supported"
            )
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

    def _binding_for_digest(self, binding_digest: str) -> ProviderTierBinding:
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
        return _binding_from_row(row)

    def _activate_authorized(
        self,
        binding_digest: str,
        *,
        permit: _TierActivationPermit,
    ) -> None:
        if (
            not isinstance(permit, _TierActivationPermit)
            or permit.binding_digest != binding_digest
        ):
            raise DirectStoreConflict("operator activation permit is invalid")
        binding = self._binding_for_digest(binding_digest)

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
                    binding_digest, authority_digest, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_id, model_id) DO UPDATE SET
                    tier_id = excluded.tier_id,
                    revision = excluded.revision,
                    binding_digest = excluded.binding_digest,
                    authority_digest = excluded.authority_digest,
                    updated_at = excluded.updated_at""",
                (
                    binding.provider_id,
                    binding.model_id,
                    binding.tier_id,
                    binding.revision,
                    binding.binding_digest,
                    permit.authority_digest,
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


class ProviderCapabilityGovernance:
    def __init__(
        self,
        store: ProviderCapabilityPolicyStore,
        authorities: DispatchAuthorityStore,
    ) -> None:
        if not isinstance(store, ProviderCapabilityPolicyStore):
            raise ValueError("store must be a ProviderCapabilityPolicyStore")
        if not isinstance(authorities, DispatchAuthorityStore):
            raise ValueError("authorities must be a DispatchAuthorityStore")
        expected_authority_path = (
            store.path.parent.parent / "runtime" / "dispatch.sqlite3"
        ).absolute()
        if (
            store.path.name != "provider-capability-policies.sqlite3"
            or store.path.parent.name != "settings"
            or authorities.database.path.absolute() != expected_authority_path
        ):
            raise ValueError(
                "provider capability governance requires the canonical "
                "state-root authority database"
            )
        self.store = store
        self.authorities = authorities

    def activate(
        self,
        binding_digest: str,
        reference: AuthorizationReference,
    ) -> ProviderTierBinding:
        if not isinstance(reference, AuthorizationReference):
            raise DirectStoreConflict("operator activation authority is invalid")
        binding = self.store._binding_for_digest(binding_digest)
        self.authorities.verify(
            reference,
            provider_id=binding.provider_id,
            plane="policy_activation",
            task_type="provider_tier_activation",
            provider_tier_binding_digest=binding.binding_digest,
        )
        permit = _TierActivationPermit._issue(
            binding_digest=binding.binding_digest,
            authority_digest=reference.digest,
        )
        self.store._activate_authorized(
            binding.binding_digest,
            permit=permit,
        )
        return binding

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
    "ProviderCapabilityPolicyStore",
    "ProviderCapabilityGovernance",
    "read_effective_binding",
    "read_effective_policy",
]
