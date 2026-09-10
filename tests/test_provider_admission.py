from __future__ import annotations

import sqlite3
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from macr_runtime.authority import AuthorityScope, DispatchAuthorityStore
from macr_runtime.errors import DispatchAuthorizationError
from macr_runtime.provider_admission import (
    AdmissionLane,
    ProjectAdmissionBinding,
    ProviderAdmissionPolicy,
    glm_provider_admission_policy,
)
from macr_runtime.runtime_db import RuntimeDatabase
from tests.support import d_drive_tempdir


class Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class ProviderAdmissionContractTests(unittest.TestCase):
    def test_glm_policy_has_bounded_unmeasured_headroom(self) -> None:
        policy = glm_provider_admission_policy()

        self.assertEqual(policy.provider_id, "glm_flash_worker")
        self.assertEqual(policy.capacity_unit, 1)
        self.assertEqual(policy.effective_target, 1)
        self.assertEqual(policy.candidate_target, 2)
        self.assertEqual(policy.hard_max, 8)
        self.assertEqual(policy.per_project_cap, 2)
        self.assertEqual(policy.policy_source, "built_in")
        self.assertEqual(len(policy.policy_digest), 64)

    def test_policy_rejects_zero_unlimited_and_unmeasured_effective_values(self) -> None:
        valid = glm_provider_admission_policy()

        for changed in (
            {"hard_max": 0},
            {"hard_max": 9},
            {"effective_target": 0},
            {"effective_target": 2},
            {"candidate_target": 1},
            {"candidate_target": 9},
            {"per_project_cap": 0},
            {"per_project_cap": 9},
            {"capacity_unit": 0},
            {"capacity_unit": -1},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    replace(valid, **changed)

    def test_project_binding_is_canonical_and_lane_is_closed(self) -> None:
        binding = ProjectAdmissionBinding(
            project_id="agiright",
            revision=1,
            binding_source="operator_asserted",
        )

        self.assertEqual(
            ProjectAdmissionBinding.from_dict(binding.to_dict()),
            binding,
        )
        self.assertEqual(len(binding.binding_digest), 64)
        self.assertEqual(
            tuple(item.value for item in AdmissionLane),
            ("interactive", "routine", "bulk"),
        )
        with self.assertRaises(ValueError):
            ProjectAdmissionBinding("../forged", 1, "operator_asserted")
        with self.assertRaises(ValueError):
            ProjectAdmissionBinding("agiright", 0, "operator_asserted")
        with self.assertRaises(ValueError):
            ProviderAdmissionPolicy.from_dict(
                {**glm_provider_admission_policy().to_dict(), "hard_max": None}
            )


class ProviderAdmissionAuthorityTests(unittest.TestCase):
    def test_v3_authority_binds_project_lane_and_policy(self) -> None:
        now = datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        project = ProjectAdmissionBinding(
            "agiright",
            1,
            "operator_asserted",
        )
        policy = glm_provider_admission_policy()
        tier = "a" * 64
        with d_drive_tempdir() as temp:
            store = DispatchAuthorityStore(temp / "dispatch.sqlite3", now=clock)
            reference = store.issue(
                source_kind="operator_test",
                source_id="admission-v3",
                scope=AuthorityScope(
                    providers=("glm_flash_worker",),
                    planes=("delegation",),
                    task_types=("delegated_routine",),
                    provider_tier_binding_digests=(tier,),
                    project_binding_digests=(project.binding_digest,),
                    admission_lanes=(AdmissionLane.BULK.value,),
                    provider_admission_policy_digests=(policy.policy_digest,),
                    scope_contract_version=3,
                ),
                expires_at=(now + timedelta(minutes=10)).isoformat(),
            )

            verified = store.verify(
                reference,
                provider_id="glm_flash_worker",
                plane="delegation",
                task_type="delegated_routine",
                provider_tier_binding_digest=tier,
                project_binding_digest=project.binding_digest,
                admission_lane=AdmissionLane.BULK.value,
                provider_admission_policy_digest=policy.policy_digest,
            )
            self.assertEqual(verified, reference)

            attacks = (
                {"project_binding_digest": "b" * 64},
                {"admission_lane": AdmissionLane.INTERACTIVE.value},
                {"provider_admission_policy_digest": "c" * 64},
            )
            for changed in attacks:
                kwargs = {
                    "provider_id": "glm_flash_worker",
                    "plane": "delegation",
                    "task_type": "delegated_routine",
                    "provider_tier_binding_digest": tier,
                    "project_binding_digest": project.binding_digest,
                    "admission_lane": AdmissionLane.BULK.value,
                    "provider_admission_policy_digest": policy.policy_digest,
                    **changed,
                }
                with self.subTest(changed=changed):
                    with self.assertRaisesRegex(
                        DispatchAuthorizationError,
                        "scope",
                    ):
                        store.verify(reference, **kwargs)

    def test_v2_authority_is_readable_but_cannot_gain_admission_identity(self) -> None:
        scope = AuthorityScope.from_dict(
            {
                "scope_contract_version": 2,
                "providers": ["glm_flash_worker"],
                "planes": ["delegation"],
                "task_types": ["delegated_routine"],
                "batch_ids": [],
                "member_digests": [],
                "provider_tier_binding_digests": ["a" * 64],
            }
        )

        self.assertEqual(scope.scope_contract_version, 2)
        self.assertFalse(
            scope.permits(
                provider_id="glm_flash_worker",
                plane="delegation",
                task_type="delegated_routine",
                batch_id=None,
                member_digest=None,
                provider_tier_binding_digest="a" * 64,
                project_binding_digest="b" * 64,
                admission_lane=AdmissionLane.BULK.value,
                provider_admission_policy_digest="c" * 64,
            )
        )


class ProviderAdmissionSchemaTests(unittest.TestCase):
    def test_runtime_schema_eight_adds_admission_tables(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            RuntimeDatabase(path)
            connection = sqlite3.connect(path)
            try:
                version = connection.execute(
                    "SELECT version FROM schema_meta WHERE component='runtime'"
                ).fetchone()[0]
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                request_columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(provider_admission_requests)"
                    )
                }
            finally:
                connection.close()

        self.assertEqual(version, 8)
        self.assertTrue(
            {
                "provider_admission_policies",
                "provider_admission_state",
                "provider_admission_projects",
                "provider_admission_requests",
            }
            <= tables
        )
        self.assertTrue(
            {
                "request_id",
                "provider_id",
                "project_binding_digest",
                "admission_lane",
                "run_id",
                "authority_digest",
                "authority_epoch",
                "task_digest",
                "member_digest",
                "provider_tier_binding_digest",
                "policy_digest",
                "capacity_unit",
                "state",
                "fencing_token",
                "expires_at",
            }
            <= request_columns
        )


if __name__ == "__main__":
    unittest.main()
