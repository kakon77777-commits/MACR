from __future__ import annotations

import sqlite3
import unittest
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from macr_runtime.authority import AuthorityScope, DispatchAuthorityStore
from macr_runtime.errors import DirectStoreConflict, DispatchAuthorizationError
from macr_runtime.execution import AuthorizationReference
from macr_runtime.provider_capability import (
    glm_extended_text_policy,
    glm_standard_policy,
)
from macr_runtime.provider_capability_store import (
    ProviderCapabilityGovernance,
    ProviderCapabilityPolicyStore,
    read_effective_binding,
    read_effective_policy,
)
from macr_runtime.runtime import RuntimeServices
from macr_runtime.storage import StorageLayout
from tests.support import d_drive_tempdir


class AllowAllVerifier:
    def verify(self, *, witness: str, binding_digest: str) -> None:
        del witness, binding_digest


class ProviderCapabilityPolicyStoreTests(unittest.TestCase):
    def test_schema_one_active_row_migrates_as_legacy_then_reauthorizes(self) -> None:
        extended = glm_extended_text_policy()
        body = json.dumps(
            extended.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        body_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
        binding = extended.binding()
        with d_drive_tempdir() as temp:
            path = temp / "settings" / "provider-capability-policies.sqlite3"
            path.parent.mkdir(parents=True)
            connection = sqlite3.connect(path)
            connection.executescript(
                """CREATE TABLE provider_capability_schema_meta (
                    component TEXT PRIMARY KEY, version INTEGER NOT NULL
                );
                CREATE TABLE provider_capability_policies (
                    provider_id TEXT NOT NULL, model_id TEXT NOT NULL,
                    tier_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    body_json TEXT NOT NULL, body_sha256 TEXT NOT NULL,
                    binding_digest TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
                    PRIMARY KEY(provider_id, model_id, tier_id, revision)
                );
                CREATE TABLE provider_capability_active (
                    provider_id TEXT NOT NULL, model_id TEXT NOT NULL,
                    tier_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    binding_digest TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(provider_id, model_id)
                );"""
            )
            connection.execute(
                "INSERT INTO provider_capability_schema_meta VALUES (?, 1)",
                ("provider_capability_policies",),
            )
            connection.execute(
                """INSERT INTO provider_capability_policies VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?
                )""",
                (
                    extended.provider_id,
                    extended.model_id,
                    extended.tier_id,
                    extended.revision,
                    body,
                    body_sha256,
                    binding.binding_digest,
                    "2026-09-07T00:00:00+00:00",
                ),
            )
            connection.execute(
                "INSERT INTO provider_capability_active VALUES (?, ?, ?, ?, ?, ?)",
                (
                    extended.provider_id,
                    extended.model_id,
                    extended.tier_id,
                    extended.revision,
                    binding.binding_digest,
                    "2026-09-07T00:00:00+00:00",
                ),
            )
            connection.commit()
            connection.close()

            store = ProviderCapabilityPolicyStore(path)
            connection = sqlite3.connect(path)
            try:
                version = connection.execute(
                    "SELECT version FROM provider_capability_schema_meta"
                ).fetchone()[0]
                legacy_authority = connection.execute(
                    "SELECT authority_digest FROM provider_capability_active"
                ).fetchone()[0]
            finally:
                connection.close()
            with self.assertRaisesRegex(DirectStoreConflict, "legacy"):
                store.effective_binding(extended.provider_id, extended.model_id)

            authorities = DispatchAuthorityStore(
                temp / "runtime" / "dispatch.sqlite3"
            )
            reference = authorities.issue(
                source_kind="operator_policy_authority",
                source_id="reauthorize-extended-v1",
                scope=AuthorityScope(
                    providers=(extended.provider_id,),
                    planes=("policy_activation",),
                    task_types=("provider_tier_activation",),
                    provider_tier_binding_digests=(binding.binding_digest,),
                ),
                expires_at=(
                    datetime.now(timezone.utc) + timedelta(minutes=5)
                ).isoformat(),
            )
            ProviderCapabilityGovernance(store, authorities).activate(
                binding.binding_digest,
                reference,
            )
            reauthorized = store.effective_binding(
                extended.provider_id,
                extended.model_id,
            )

        self.assertEqual(version, 2)
        self.assertIsNone(legacy_authority)
        self.assertEqual(reauthorized, binding)

    def test_noncanonical_authority_database_cannot_activate_policy_store(self) -> None:
        with d_drive_tempdir() as temp:
            extended = glm_extended_text_policy()
            store = ProviderCapabilityPolicyStore(
                temp / "settings" / "provider-capability-policies.sqlite3"
            )
            store.save_policy(extended)
            rogue_authorities = DispatchAuthorityStore(temp / "rogue.sqlite3")
            reference = rogue_authorities.issue(
                source_kind="operator_policy_authority",
                source_id="rogue-authority-db",
                scope=AuthorityScope(
                    providers=(extended.provider_id,),
                    planes=("policy_activation",),
                    task_types=("provider_tier_activation",),
                    provider_tier_binding_digests=(
                        extended.binding().binding_digest,
                    ),
                ),
                expires_at=(
                    datetime.now(timezone.utc) + timedelta(minutes=5)
                ).isoformat(),
            )

            with self.assertRaisesRegex(ValueError, "canonical"):
                ProviderCapabilityGovernance(store, rogue_authorities).activate(
                    extended.binding().binding_digest,
                    reference,
                )

            self.assertEqual(
                store.effective_binding(extended.provider_id, extended.model_id),
                glm_standard_policy().binding(),
            )

    def test_allow_all_verifier_cannot_activate_without_authority_store(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "policies.sqlite3"
            store = ProviderCapabilityPolicyStore(path)
            extended = glm_extended_text_policy()
            store.save_policy(extended)

            with self.assertRaises((AttributeError, DirectStoreConflict)):
                store.activate(
                    extended.binding().binding_digest,
                    witness="fabricated",
                    verifier=AllowAllVerifier(),
                )

            self.assertEqual(
                store.effective_binding("glm_flash_worker", "glm-5.3-flash"),
                glm_standard_policy().binding(),
            )

    def test_store_rejects_policy_not_published_by_provider_adapter(self) -> None:
        rogue = replace(
            glm_extended_text_policy(),
            tier_id="rogue_unbounded",
            max_latency_s=3_600,
            patch_allowed=True,
            write_scope_allowed=True,
            verification_required=False,
        )
        with d_drive_tempdir() as temp:
            store = ProviderCapabilityPolicyStore(temp / "policies.sqlite3")

            with self.assertRaisesRegex(DirectStoreConflict, "supported"):
                store.save_policy(rogue)

            self.assertEqual(
                store.effective_binding("glm_flash_worker", "glm-5.3-flash"),
                glm_standard_policy().binding(),
            )

    def test_canonical_rogue_row_is_rejected_during_effective_read(self) -> None:
        rogue = replace(
            glm_extended_text_policy(),
            tier_id="rogue_unbounded",
            max_latency_s=3_600,
            patch_allowed=True,
        )
        body = json.dumps(
            rogue.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        body_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
        binding = rogue.binding()
        with d_drive_tempdir() as temp:
            path = temp / "policies.sqlite3"
            store = ProviderCapabilityPolicyStore(path)
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    """INSERT INTO provider_capability_policies(
                        provider_id, model_id, tier_id, revision, body_json,
                        body_sha256, binding_digest, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        rogue.provider_id,
                        rogue.model_id,
                        rogue.tier_id,
                        rogue.revision,
                        body,
                        body_sha256,
                        binding.binding_digest,
                        "2026-09-07T00:00:00+00:00",
                    ),
                )
                connection.execute(
                    """INSERT INTO provider_capability_active(
                        provider_id, model_id, tier_id, revision,
                        binding_digest, authority_digest, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        rogue.provider_id,
                        rogue.model_id,
                        rogue.tier_id,
                        rogue.revision,
                        binding.binding_digest,
                        "f" * 64,
                        "2026-09-07T00:00:00+00:00",
                    ),
                )
                connection.commit()
            finally:
                connection.close()

            with self.assertRaisesRegex(DirectStoreConflict, "supported"):
                store.effective_policy(rogue.provider_id, rogue.model_id)

    def test_activation_can_consume_but_not_issue_exact_dispatch_authority(self) -> None:
        with d_drive_tempdir() as temp:
            binding = glm_extended_text_policy().binding()
            authorities = DispatchAuthorityStore(
                temp / "runtime" / "dispatch.sqlite3"
            )
            reference = authorities.issue(
                source_kind="operator_policy_authority",
                source_id="glm-extended-text-v1",
                scope=AuthorityScope(
                    providers=(binding.provider_id,),
                    planes=("policy_activation",),
                    task_types=("provider_tier_activation",),
                    provider_tier_binding_digests=(binding.binding_digest,),
                ),
                expires_at=(
                    datetime.now(timezone.utc) + timedelta(minutes=5)
                ).isoformat(),
            )
            store = ProviderCapabilityPolicyStore(
                temp / "settings" / "provider-capability-policies.sqlite3"
            )
            store.save_policy(glm_extended_text_policy())
            ProviderCapabilityGovernance(store, authorities).activate(
                binding.binding_digest,
                reference,
            )

            self.assertEqual(
                store.effective_binding(binding.provider_id, binding.model_id),
                binding,
            )

    def test_runtime_services_uses_the_d_drive_capability_store(self) -> None:
        with d_drive_tempdir() as temp:
            layout = StorageLayout(
                source_root=r"D:\Ai\work together\MACR",
                state_root=str(temp),
                codex_home_target=r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
            )

            services = RuntimeServices.from_layout(layout)

            self.assertEqual(
                services.capability_policies.path,
                layout.provider_capability_policy_db_path,
            )

    def test_absent_database_resolves_standard_without_creating_file(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "settings" / "provider-capability-policies.sqlite3"

            binding = read_effective_binding(
                path,
                "glm_flash_worker",
                "glm-5.3-flash",
            )

            self.assertEqual(binding, glm_standard_policy().binding())
            self.assertEqual(
                read_effective_policy(
                    path,
                    "glm_flash_worker",
                    "glm-5.3-flash",
                ),
                glm_standard_policy(),
            )
            self.assertFalse(path.exists())

    def test_store_is_create_once_and_defaults_to_standard(self) -> None:
        with d_drive_tempdir() as temp:
            store = ProviderCapabilityPolicyStore(temp / "policies.sqlite3")
            extended = glm_extended_text_policy()

            self.assertTrue(store.save_policy(extended))
            self.assertFalse(store.save_policy(extended))
            self.assertEqual(
                store.effective_binding("glm_flash_worker", "glm-5.3-flash"),
                glm_standard_policy().binding(),
            )
            with self.assertRaisesRegex(DirectStoreConflict, "supported"):
                store.save_policy(replace(extended, max_latency_s=901))

    def test_activation_requires_exact_preexisting_witness(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "settings" / "provider-capability-policies.sqlite3"
            store = ProviderCapabilityPolicyStore(path)
            extended = glm_extended_text_policy()
            store.save_policy(extended)
            authorities = DispatchAuthorityStore(
                temp / "runtime" / "dispatch.sqlite3"
            )
            missing = AuthorizationReference(
                source_kind="missing",
                source_id="missing",
                digest="a" * 64,
                revision=1,
                epoch=0,
                scope="missing",
            )

            with self.assertRaises(DispatchAuthorizationError):
                ProviderCapabilityGovernance(store, authorities).activate(
                    extended.binding().binding_digest,
                    missing,
                )
            self.assertEqual(
                store.effective_binding("glm_flash_worker", "glm-5.3-flash"),
                glm_standard_policy().binding(),
            )

            reference = authorities.issue(
                source_kind="operator_policy_authority",
                source_id="extended-v1",
                scope=AuthorityScope(
                    providers=(extended.provider_id,),
                    planes=("policy_activation",),
                    task_types=("provider_tier_activation",),
                    provider_tier_binding_digests=(
                        extended.binding().binding_digest,
                    ),
                ),
                expires_at=(
                    datetime.now(timezone.utc) + timedelta(minutes=5)
                ).isoformat(),
            )
            ProviderCapabilityGovernance(store, authorities).activate(
                extended.binding().binding_digest,
                reference,
            )
            self.assertEqual(
                store.effective_binding("glm_flash_worker", "glm-5.3-flash"),
                extended.binding(),
            )
            self.assertEqual(
                store.effective_policy("glm_flash_worker", "glm-5.3-flash"),
                extended,
            )

    def test_corrupt_active_policy_fails_closed_without_standard_fallback(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "settings" / "provider-capability-policies.sqlite3"
            store = ProviderCapabilityPolicyStore(path)
            extended = glm_extended_text_policy()
            store.save_policy(extended)
            authorities = DispatchAuthorityStore(
                temp / "runtime" / "dispatch.sqlite3"
            )
            reference = authorities.issue(
                source_kind="operator_policy_authority",
                source_id="extended-v1",
                scope=AuthorityScope(
                    providers=(extended.provider_id,),
                    planes=("policy_activation",),
                    task_types=("provider_tier_activation",),
                    provider_tier_binding_digests=(
                        extended.binding().binding_digest,
                    ),
                ),
                expires_at=(
                    datetime.now(timezone.utc) + timedelta(minutes=5)
                ).isoformat(),
            )
            ProviderCapabilityGovernance(store, authorities).activate(
                extended.binding().binding_digest,
                reference,
            )
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    "UPDATE provider_capability_policies SET body_sha256 = ? WHERE tier_id = ?",
                    ("0" * 64, extended.tier_id),
                )
                connection.commit()
            finally:
                connection.close()

            with self.assertRaisesRegex(DirectStoreConflict, "digest"):
                store.effective_binding("glm_flash_worker", "glm-5.3-flash")


if __name__ == "__main__":
    unittest.main()
