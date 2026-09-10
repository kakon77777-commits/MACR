from __future__ import annotations

import sqlite3
import unittest
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from macr_runtime.authority import AuthorityScope, DispatchAuthorityStore
from macr_runtime.errors import (
    DispatchAuthorizationError,
    ProviderAdmissionBusyError,
    ProviderAdmissionConflict,
    ProviderAdmissionReconciliationError,
)
from macr_runtime.provider_admission import (
    AdmissionLane,
    ProjectAdmissionBinding,
    ProviderAdmissionKernel,
    ProviderAdmissionPolicy,
    ProviderAdmissionRequest,
    ProviderAdmissionTargetBinding,
    ProviderAdmissionCircuitBinding,
    glm_provider_admission_policy,
    read_provider_admission_status,
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
    def test_readonly_status_does_not_create_or_mutate_runtime_database(self) -> None:
        with d_drive_tempdir() as temp:
            absent = temp / "absent" / "dispatch.sqlite3"
            empty = read_provider_admission_status(
                absent,
                "glm_flash_worker",
            )
            self.assertFalse(absent.exists())
            path = temp / "runtime" / "dispatch.sqlite3"
            ProviderAdmissionKernel(path)
            before = path.read_bytes()

            status = read_provider_admission_status(
                path,
                "glm_flash_worker",
            )
            after = path.read_bytes()

        self.assertFalse(empty.initialized)
        self.assertTrue(status.initialized)
        self.assertEqual(before, after)

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


class ProviderAdmissionKernelTests(unittest.TestCase):
    def test_known_429_requires_authorized_single_half_open_probe(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(path, now=self.clock)
            dispatch_reference = self._authority(authorities, (self.project_a,))
            kernel = ProviderAdmissionKernel(path, now=self.clock)
            request = self._request(
                dispatch_reference,
                self.project_a,
                AdmissionLane.ROUTINE,
            )
            permit = kernel.try_admit(request, ttl_seconds=60)
            kernel.begin_transport(permit, request)
            kernel.finish(
                permit,
                network_attempted=True,
                response_received=True,
                provider_http_status=429,
                terminal_persisted=True,
                terminal_evidence_digest="e" * 64,
            )
            with self.assertRaises(ProviderAdmissionReconciliationError):
                kernel.try_admit(
                    self._request(
                        dispatch_reference,
                        self.project_a,
                        AdmissionLane.ROUTINE,
                    ),
                    ttl_seconds=60,
                )
            half_open = ProviderAdmissionCircuitBinding.create(
                kernel.policy,
                from_state="open",
                to_state="half_open",
            )
            circuit_reference = authorities.issue(
                source_kind="operator_circuit_authority",
                source_id="half-open-one",
                scope=AuthorityScope(
                    providers=(kernel.policy.provider_id,),
                    planes=("provider_circuit_activation",),
                    task_types=("provider_circuit_half_open",),
                    provider_admission_circuit_digests=(
                        half_open.binding_digest,
                    ),
                    scope_contract_version=3,
                ),
                expires_at=(
                    self.clock.value + timedelta(minutes=5)
                ).isoformat(),
            )
            kernel.activate_half_open(half_open, circuit_reference)
            probe_request = self._request(
                dispatch_reference,
                self.project_a,
                AdmissionLane.INTERACTIVE,
            )
            probe = kernel.try_admit(probe_request, ttl_seconds=60)
            kernel.begin_transport(probe, probe_request)
            kernel.finish(
                probe,
                network_attempted=True,
                response_received=True,
                provider_http_status=200,
                terminal_persisted=True,
                terminal_evidence_digest="f" * 64,
            )
            status = kernel.status(kernel.policy.provider_id)

        self.assertEqual(status.circuit_state, "closed")
        self.assertEqual(status.last_signal, "http_200")

    def test_candidate_target_two_requires_exact_preissued_authority(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(path, now=self.clock)
            kernel = ProviderAdmissionKernel(path, now=self.clock)
            target = ProviderAdmissionTargetBinding.create(
                kernel.policy,
                target=2,
            )
            reference = authorities.issue(
                source_kind="operator_capacity_authority",
                source_id="glm-target-two",
                scope=AuthorityScope(
                    providers=(kernel.policy.provider_id,),
                    planes=("provider_capacity_activation",),
                    task_types=("provider_capacity_target",),
                    provider_admission_target_digests=(
                        target.binding_digest,
                    ),
                    scope_contract_version=3,
                ),
                expires_at=(
                    self.clock.value + timedelta(minutes=5)
                ).isoformat(),
            )

            activated = kernel.activate_target(target, reference)
            dispatch_reference = self._authority(
                authorities,
                (self.project_a, self.project_b),
            )
            first = kernel.try_admit(
                self._request(
                    dispatch_reference,
                    self.project_a,
                    AdmissionLane.ROUTINE,
                ),
                ttl_seconds=60,
            )
            second = kernel.try_admit(
                self._request(
                    dispatch_reference,
                    self.project_b,
                    AdmissionLane.BULK,
                ),
                ttl_seconds=60,
            )
            with self.assertRaises(ProviderAdmissionBusyError):
                kernel.try_admit(
                    self._request(
                        dispatch_reference,
                        self.project_b,
                        AdmissionLane.INTERACTIVE,
                    ),
                    ttl_seconds=60,
                )
            kernel.cancel_before_transport(first)
            kernel.cancel_before_transport(second)

        self.assertEqual(activated.effective_target, 2)
        with self.assertRaises(ValueError):
            ProviderAdmissionTargetBinding.create(kernel.policy, target=3)

    def test_target_two_still_enforces_per_project_cap(self) -> None:
        policy = replace(
            glm_provider_admission_policy(),
            per_project_cap=1,
        )
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(path, now=self.clock)
            kernel = ProviderAdmissionKernel(
                path,
                policy=policy,
                now=self.clock,
            )
            target = ProviderAdmissionTargetBinding.create(policy, target=2)
            target_reference = authorities.issue(
                source_kind="operator_capacity_authority",
                source_id="per-project-target-two",
                scope=AuthorityScope(
                    providers=(policy.provider_id,),
                    planes=("provider_capacity_activation",),
                    task_types=("provider_capacity_target",),
                    provider_admission_target_digests=(
                        target.binding_digest,
                    ),
                    scope_contract_version=3,
                ),
                expires_at=(
                    self.clock.value + timedelta(minutes=5)
                ).isoformat(),
            )
            kernel.activate_target(target, target_reference)
            dispatch_reference = authorities.issue(
                source_kind="operator_test",
                source_id="per-project-cap",
                scope=AuthorityScope(
                    providers=(policy.provider_id,),
                    planes=("delegation",),
                    task_types=("delegated_routine",),
                    provider_tier_binding_digests=("a" * 64,),
                    project_binding_digests=(
                        self.project_a.binding_digest,
                        self.project_b.binding_digest,
                    ),
                    admission_lanes=(AdmissionLane.ROUTINE.value,),
                    provider_admission_policy_digests=(
                        policy.policy_digest,
                    ),
                    scope_contract_version=3,
                ),
                expires_at=(
                    self.clock.value + timedelta(minutes=5)
                ).isoformat(),
            )
            first = kernel.try_admit(
                self._request(
                    dispatch_reference,
                    self.project_a,
                    AdmissionLane.ROUTINE,
                ),
                ttl_seconds=60,
            )
            same_project = self._request(
                dispatch_reference,
                self.project_a,
                AdmissionLane.ROUTINE,
            )
            with self.assertRaises(ProviderAdmissionBusyError):
                kernel.try_admit(same_project, ttl_seconds=60)
            other_project = kernel.try_admit(
                self._request(
                    dispatch_reference,
                    self.project_b,
                    AdmissionLane.ROUTINE,
                ),
                ttl_seconds=60,
            )
            kernel.cancel_before_transport(first)
            kernel.cancel_before_transport(other_project)

        self.assertNotEqual(
            first.project_binding_digest,
            other_project.project_binding_digest,
        )

    def test_denormalized_project_counter_cannot_bypass_project_cap(self) -> None:
        policy = replace(
            glm_provider_admission_policy(),
            per_project_cap=1,
        )
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(path, now=self.clock)
            kernel = ProviderAdmissionKernel(
                path,
                policy=policy,
                now=self.clock,
            )
            target = ProviderAdmissionTargetBinding.create(policy, target=2)
            target_reference = authorities.issue(
                source_kind="operator_capacity_authority",
                source_id="counter-attack-target-two",
                scope=AuthorityScope(
                    providers=(policy.provider_id,),
                    planes=("provider_capacity_activation",),
                    task_types=("provider_capacity_target",),
                    provider_admission_target_digests=(
                        target.binding_digest,
                    ),
                    scope_contract_version=3,
                ),
                expires_at=(
                    self.clock.value + timedelta(minutes=5)
                ).isoformat(),
            )
            kernel.activate_target(target, target_reference)
            dispatch_reference = authorities.issue(
                source_kind="operator_test",
                source_id="counter-attack",
                scope=AuthorityScope(
                    providers=(policy.provider_id,),
                    planes=("delegation",),
                    task_types=("delegated_routine",),
                    provider_tier_binding_digests=("a" * 64,),
                    project_binding_digests=(
                        self.project_a.binding_digest,
                    ),
                    admission_lanes=(AdmissionLane.ROUTINE.value,),
                    provider_admission_policy_digests=(
                        policy.policy_digest,
                    ),
                    scope_contract_version=3,
                ),
                expires_at=(
                    self.clock.value + timedelta(minutes=5)
                ).isoformat(),
            )
            first = kernel.try_admit(
                self._request(
                    dispatch_reference,
                    self.project_a,
                    AdmissionLane.ROUTINE,
                ),
                ttl_seconds=60,
            )
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    """UPDATE provider_admission_projects
                    SET active_units=0 WHERE provider_id=?""",
                    (policy.provider_id,),
                )
                connection.commit()
            finally:
                connection.close()

            with self.assertRaises(ProviderAdmissionBusyError):
                kernel.try_admit(
                    self._request(
                        dispatch_reference,
                        self.project_a,
                        AdmissionLane.ROUTINE,
                    ),
                    ttl_seconds=60,
                )

        self.assertEqual(first.project_binding_digest, self.project_a.binding_digest)

    def test_tampered_effective_target_above_candidate_fails_closed(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(path, now=self.clock)
            reference = self._authority(authorities, (self.project_a,))
            kernel = ProviderAdmissionKernel(path, now=self.clock)
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    """UPDATE provider_admission_state
                    SET effective_target=8 WHERE provider_id=?""",
                    (kernel.policy.provider_id,),
                )
                connection.commit()
            finally:
                connection.close()

            with self.assertRaisesRegex(
                ProviderAdmissionConflict,
                "state",
            ):
                kernel.try_admit(
                    self._request(
                        reference,
                        self.project_a,
                        AdmissionLane.ROUTINE,
                    ),
                    ttl_seconds=60,
                )

    def setUp(self) -> None:
        self.now = datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc)
        self.clock = Clock(self.now)
        self.project_a = ProjectAdmissionBinding(
            "project-a",
            1,
            "operator_asserted",
        )
        self.project_b = ProjectAdmissionBinding(
            "project-b",
            1,
            "operator_asserted",
        )

    def _authority(
        self,
        store: DispatchAuthorityStore,
        projects: tuple[ProjectAdmissionBinding, ...],
    ):
        policy = glm_provider_admission_policy()
        return store.issue(
            source_kind="operator_test",
            source_id=str(uuid.uuid4()),
            scope=AuthorityScope(
                providers=(policy.provider_id,),
                planes=("delegation",),
                task_types=("delegated_routine",),
                provider_tier_binding_digests=("a" * 64,),
                project_binding_digests=tuple(
                    item.binding_digest for item in projects
                ),
                admission_lanes=tuple(item.value for item in AdmissionLane),
                provider_admission_policy_digests=(policy.policy_digest,),
                scope_contract_version=3,
            ),
            expires_at=(self.clock.value + timedelta(hours=1)).isoformat(),
        )

    def _request(
        self,
        authority,
        project: ProjectAdmissionBinding,
        lane: AdmissionLane,
        *,
        run_id: str | None = None,
        request_id: str | None = None,
    ) -> ProviderAdmissionRequest:
        return ProviderAdmissionRequest(
            request_id=request_id or str(uuid.uuid4()),
            provider_id="glm_flash_worker",
            project_binding_digest=project.binding_digest,
            lane=lane,
            run_id=run_id or str(uuid.uuid4()),
            authorization=authority,
            plane="delegation",
            task_type="delegated_routine",
            task_digest="b" * 64,
            member_digest="c" * 64,
            batch_id=None,
            provider_tier_binding_digest="a" * 64,
        )

    def test_target_one_is_global_across_projects_and_busy_is_nonterminal(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(path, now=self.clock)
            reference = self._authority(
                authorities,
                (self.project_a, self.project_b),
            )
            kernel = ProviderAdmissionKernel(path, now=self.clock)
            first = kernel.try_admit(
                self._request(reference, self.project_a, AdmissionLane.BULK),
                ttl_seconds=60,
            )
            second_request = self._request(
                reference,
                self.project_b,
                AdmissionLane.ROUTINE,
            )

            with self.assertRaises(ProviderAdmissionBusyError):
                kernel.try_admit(second_request, ttl_seconds=60)
            status = kernel.status("glm_flash_worker")

        self.assertEqual(first.capacity_unit, 1)
        self.assertEqual(status.effective_target, 1)
        self.assertEqual(status.counts["granted"], 1)
        self.assertEqual(status.counts["waiting"], 1)
        self.assertEqual(status.counts["dispatched"], 0)

    def test_waiting_request_can_gain_released_slot_without_new_identity(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(path, now=self.clock)
            reference = self._authority(
                authorities,
                (self.project_a, self.project_b),
            )
            kernel = ProviderAdmissionKernel(path, now=self.clock)
            first = kernel.try_admit(
                self._request(reference, self.project_a, AdmissionLane.BULK),
                ttl_seconds=60,
            )
            waiting = self._request(
                reference,
                self.project_b,
                AdmissionLane.INTERACTIVE,
            )
            with self.assertRaises(ProviderAdmissionBusyError):
                kernel.try_admit(waiting, ttl_seconds=60)

            kernel.cancel_before_transport(first)
            granted = kernel.try_admit(waiting, ttl_seconds=60)

        self.assertEqual(granted.request_id, waiting.request_id)
        self.assertEqual(granted.project_binding_digest, self.project_b.binding_digest)

    def test_interactive_gets_next_slot_then_older_bulk_makes_progress(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(path, now=self.clock)
            reference = self._authority(
                authorities,
                (self.project_a, self.project_b),
            )
            kernel = ProviderAdmissionKernel(path, now=self.clock)
            holder = kernel.try_admit(
                self._request(reference, self.project_a, AdmissionLane.ROUTINE),
                ttl_seconds=60,
            )
            bulk = self._request(
                reference,
                self.project_a,
                AdmissionLane.BULK,
            )
            interactive = self._request(
                reference,
                self.project_b,
                AdmissionLane.INTERACTIVE,
            )
            with self.assertRaises(ProviderAdmissionBusyError):
                kernel.try_admit(bulk, ttl_seconds=60)
            with self.assertRaises(ProviderAdmissionBusyError):
                kernel.try_admit(interactive, ttl_seconds=60)

            kernel.cancel_before_transport(holder)
            with self.assertRaisesRegex(ProviderAdmissionBusyError, "fair turn"):
                kernel.try_admit(bulk, ttl_seconds=60)
            interactive_permit = kernel.try_admit(interactive, ttl_seconds=60)
            kernel.cancel_before_transport(interactive_permit)
            bulk_permit = kernel.try_admit(bulk, ttl_seconds=60)

        self.assertEqual(bulk_permit.request_id, bulk.request_id)

    def test_request_id_cannot_be_replayed_with_changed_project(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(path, now=self.clock)
            reference = self._authority(
                authorities,
                (self.project_a, self.project_b),
            )
            kernel = ProviderAdmissionKernel(path, now=self.clock)
            original = self._request(
                reference,
                self.project_a,
                AdmissionLane.ROUTINE,
            )
            permit = kernel.try_admit(original, ttl_seconds=60)
            changed = self._request(
                reference,
                self.project_b,
                AdmissionLane.ROUTINE,
                request_id=original.request_id,
                run_id=original.run_id,
            )

            with self.assertRaisesRegex(ProviderAdmissionConflict, "identity"):
                kernel.try_admit(changed, ttl_seconds=60)
            kernel.cancel_before_transport(permit)

    def test_permit_is_one_use_at_transport_boundary(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(path, now=self.clock)
            reference = self._authority(authorities, (self.project_a,))
            kernel = ProviderAdmissionKernel(path, now=self.clock)
            request = self._request(
                reference,
                self.project_a,
                AdmissionLane.ROUTINE,
            )
            permit = kernel.try_admit(request, ttl_seconds=60)

            kernel.begin_transport(permit, request)
            with self.assertRaises(ProviderAdmissionConflict):
                kernel.begin_transport(permit, request)
            record = kernel.read_request(permit.request_id)

        self.assertEqual(record.state, "dispatched")

    def test_known_terminal_releases_capacity_but_unknown_requires_reconciliation(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(path, now=self.clock)
            reference = self._authority(
                authorities,
                (self.project_a, self.project_b),
            )
            kernel = ProviderAdmissionKernel(path, now=self.clock)
            known_request = self._request(
                reference,
                self.project_a,
                AdmissionLane.ROUTINE,
            )
            known = kernel.try_admit(known_request, ttl_seconds=60)
            kernel.begin_transport(known, known_request)
            kernel.finish(
                known,
                network_attempted=True,
                response_received=True,
                provider_http_status=200,
                terminal_persisted=True,
                terminal_evidence_digest="d" * 64,
            )
            unknown_request = self._request(
                reference,
                self.project_b,
                AdmissionLane.BULK,
            )
            unknown = kernel.try_admit(unknown_request, ttl_seconds=60)
            kernel.begin_transport(unknown, unknown_request)
            kernel.finish(
                unknown,
                network_attempted=True,
                response_received=False,
                provider_http_status=None,
                terminal_persisted=True,
                terminal_evidence_digest="e" * 64,
            )

            with self.assertRaises(ProviderAdmissionReconciliationError):
                kernel.try_admit(
                    self._request(
                        reference,
                        self.project_a,
                        AdmissionLane.INTERACTIVE,
                    ),
                    ttl_seconds=60,
                )
            status = kernel.status("glm_flash_worker")
            known_record = kernel.read_request(known.request_id)
            unknown_record = kernel.read_request(unknown.request_id)

        self.assertEqual(known_record.state, "completed")
        self.assertEqual(unknown_record.state, "reconciliation_required")
        self.assertEqual(status.counts["reconciliation_required"], 1)
        self.assertEqual(status.circuit_state, "open")

    def test_reconciliation_requires_exact_authority_and_restores_capacity(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(path, now=self.clock)
            dispatch_reference = self._authority(authorities, (self.project_a,))
            kernel = ProviderAdmissionKernel(path, now=self.clock)
            request = self._request(
                dispatch_reference,
                self.project_a,
                AdmissionLane.BULK,
            )
            permit = kernel.try_admit(request, ttl_seconds=60)
            kernel.begin_transport(permit, request)
            kernel.finish(
                permit,
                network_attempted=True,
                response_received=False,
                provider_http_status=None,
                terminal_persisted=True,
                terminal_evidence_digest="e" * 64,
            )

            with self.assertRaises(DispatchAuthorizationError):
                kernel.resolve_reconciliation(
                    request.request_id,
                    dispatch_reference,
                    resolution_evidence_digest="f" * 64,
                )
            resolution_reference = authorities.issue(
                source_kind="operator_reconciliation",
                source_id="resolve-one",
                scope=AuthorityScope(
                    providers=(kernel.policy.provider_id,),
                    planes=("provider_admission_reconciliation",),
                    task_types=("provider_admission_resolution",),
                    member_digests=(request.member_digest,),
                    provider_tier_binding_digests=(
                        request.provider_tier_binding_digest,
                    ),
                    project_binding_digests=(
                        request.project_binding_digest,
                    ),
                    admission_lanes=(request.lane.value,),
                    provider_admission_policy_digests=(
                        kernel.policy.policy_digest,
                    ),
                    scope_contract_version=3,
                ),
                expires_at=(
                    self.clock.value + timedelta(minutes=5)
                ).isoformat(),
            )
            record = kernel.resolve_reconciliation(
                request.request_id,
                resolution_reference,
                resolution_evidence_digest="f" * 64,
            )
            status = kernel.status(kernel.policy.provider_id)

        self.assertEqual(record.state, "reconciled")
        self.assertEqual(record.resolution_evidence_digest, "f" * 64)
        self.assertEqual(status.circuit_state, "closed")
        self.assertEqual(status.counts["reconciled"], 1)

    def test_expired_waiting_cancels_but_expired_grant_never_auto_releases(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(path, now=self.clock)
            reference = self._authority(
                authorities,
                (self.project_a, self.project_b),
            )
            kernel = ProviderAdmissionKernel(path, now=self.clock)
            first_request = self._request(
                reference,
                self.project_a,
                AdmissionLane.BULK,
            )
            first = kernel.try_admit(first_request, ttl_seconds=2)
            waiting = self._request(
                reference,
                self.project_b,
                AdmissionLane.ROUTINE,
            )
            with self.assertRaises(ProviderAdmissionBusyError):
                kernel.try_admit(waiting, ttl_seconds=1)

            self.clock.value += timedelta(seconds=3)
            with self.assertRaises(ProviderAdmissionReconciliationError):
                kernel.try_admit(
                    self._request(
                        reference,
                        self.project_b,
                        AdmissionLane.INTERACTIVE,
                    ),
                    ttl_seconds=60,
                )
            waiting_record = kernel.read_request(waiting.request_id)
            first_record = kernel.read_request(first.request_id)

        self.assertEqual(waiting_record.state, "cancelled")
        self.assertEqual(first_record.state, "reconciliation_required")


if __name__ == "__main__":
    unittest.main()
