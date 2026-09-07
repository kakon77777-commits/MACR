from __future__ import annotations

import sqlite3
import unittest
from dataclasses import replace

from macr_runtime.errors import DirectStoreConflict
from macr_runtime.provider_capability import (
    glm_extended_text_policy,
    glm_standard_policy,
)
from macr_runtime.provider_capability_store import (
    ProviderCapabilityPolicyStore,
    read_effective_binding,
    read_effective_policy,
)
from macr_runtime.runtime import RuntimeServices
from macr_runtime.storage import StorageLayout
from tests.support import d_drive_tempdir


class ExactWitnessVerifier:
    def __init__(self, accepted_witness: str) -> None:
        self.accepted_witness = accepted_witness
        self.calls: list[tuple[str, str]] = []

    def verify(self, *, witness: str, binding_digest: str) -> None:
        self.calls.append((witness, binding_digest))
        if witness != self.accepted_witness:
            raise DirectStoreConflict("operator activation witness is invalid")


class ProviderCapabilityPolicyStoreTests(unittest.TestCase):
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
            with self.assertRaisesRegex(DirectStoreConflict, "conflicts"):
                store.save_policy(replace(extended, max_latency_s=901))

    def test_activation_requires_exact_preexisting_witness(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "policies.sqlite3"
            store = ProviderCapabilityPolicyStore(path)
            extended = glm_extended_text_policy()
            store.save_policy(extended)
            verifier = ExactWitnessVerifier("owner-witness")

            with self.assertRaisesRegex(DirectStoreConflict, "witness"):
                store.activate(
                    extended.binding().binding_digest,
                    witness="fabricated",
                    verifier=verifier,
                )
            self.assertEqual(
                store.effective_binding("glm_flash_worker", "glm-5.3-flash"),
                glm_standard_policy().binding(),
            )

            store.activate(
                extended.binding().binding_digest,
                witness="owner-witness",
                verifier=verifier,
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
            path = temp / "policies.sqlite3"
            store = ProviderCapabilityPolicyStore(path)
            extended = glm_extended_text_policy()
            store.save_policy(extended)
            store.activate(
                extended.binding().binding_digest,
                witness="owner-witness",
                verifier=ExactWitnessVerifier("owner-witness"),
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
