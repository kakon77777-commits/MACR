from __future__ import annotations

import sqlite3
import unittest
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from macr_runtime.authority import AuthorityScope, DispatchAuthorityStore
from macr_runtime.errors import (
    DispatchAuthorizationError,
    ProviderAdmissionBusyError,
    ProviderAdmissionConflict,
    ProviderAdmissionReconciliationError,
    ProviderAdmissionRequiredError,
)
from macr_runtime.provider_admission import (
    AdmissionDeploymentMode,
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
    def test_deployment_capability_distinguishes_canonical_and_offline(self) -> None:
        with d_drive_tempdir() as temp:
            offline_path = temp / "offline" / "dispatch.sqlite3"
            canonical_path = temp / "canonical" / "dispatch.sqlite3"
            offline = ProviderAdmissionKernel(offline_path)
            canonical = ProviderAdmissionKernel.canonical_runtime(
                canonical_path
            )

            offline.require_transport_binding(
                offline_path,
                offline_test=True,
            )
            canonical.require_transport_binding(
                canonical_path,
                offline_test=False,
            )
            with self.assertRaises(ProviderAdmissionRequiredError):
                offline.require_transport_binding(
                    canonical_path,
                    offline_test=False,
                )
            with self.assertRaises(ProviderAdmissionRequiredError):
                canonical.require_transport_binding(
                    offline_path,
                    offline_test=False,
                )
            with self.assertRaisesRegex(
                ProviderAdmissionConflict,
                "control state",
            ):
                ProviderAdmissionKernel.canonical_runtime(offline_path)

        self.assertIs(
            offline.deployment_mode,
            AdmissionDeploymentMode.OFFLINE_TEST,
        )
        self.assertIs(
            canonical.deployment_mode,
            AdmissionDeploymentMode.CANONICAL_RUNTIME,
        )
        self.assertNotEqual(
            offline.deployment_digest,
            canonical.deployment_digest,
        )

    def test_glm_policy_has_bounded_unmeasured_headroom(self) -> None:
        policy = glm_provider_admission_policy()

        self.assertEqual(policy.provider_id, "glm_flash_worker")
        self.assertEqual(policy.revision, 2)
        self.assertEqual(policy.capacity_unit, 1)
        self.assertEqual(policy.effective_target, 8)
        self.assertEqual(policy.candidate_target, 16)
        self.assertEqual(policy.hard_max, 32)
        self.assertEqual(policy.per_project_cap, 8)
        self.assertEqual(policy.policy_source, "built_in")
        self.assertEqual(len(policy.policy_digest), 64)

    def test_policy_rejects_zero_unlimited_and_unmeasured_effective_values(self) -> None:
        valid = glm_provider_admission_policy()

        for changed in (
            {"hard_max": 0},
            {"hard_max": 33},
            {"effective_target": 0},
            {"effective_target": 33},
            {"candidate_target": 7},
            {"candidate_target": 33},
            {"per_project_cap": 0},
            {"per_project_cap": 33},
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
    def test_revision_one_runtime_cannot_silently_gain_revision_two_capacity(self) -> None:
        legacy_policy = ProviderAdmissionPolicy(
            provider_id="glm_flash_worker",
            revision=1,
            capacity_unit=1,
            effective_target=1,
            candidate_target=2,
            hard_max=8,
            per_project_cap=2,
            policy_source="built_in",
        )
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            ProviderAdmissionKernel(path, policy=legacy_policy)
            connection = sqlite3.connect(path)
            try:
                before = connection.execute(
                    """SELECT policy_digest, effective_target,
                              control_revision, control_digest
                    FROM provider_admission_state"""
                ).fetchone()
                transition_count_before = connection.execute(
                    "SELECT COUNT(*) FROM provider_admission_transitions"
                ).fetchone()[0]
                policy_count_before = connection.execute(
                    "SELECT COUNT(*) FROM provider_admission_policies"
                ).fetchone()[0]
            finally:
                connection.close()

            with self.assertRaisesRegex(
                ProviderAdmissionConflict,
                "control state",
            ):
                ProviderAdmissionKernel(path)
            connection = sqlite3.connect(path)
            try:
                after = connection.execute(
                    """SELECT policy_digest, effective_target,
                              control_revision, control_digest
                    FROM provider_admission_state"""
                ).fetchone()
                transition_count_after = connection.execute(
                    "SELECT COUNT(*) FROM provider_admission_transitions"
                ).fetchone()[0]
                policy_count_after = connection.execute(
                    "SELECT COUNT(*) FROM provider_admission_policies"
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(before, after)
        self.assertEqual(
            (transition_count_before, transition_count_after),
            (1, 1),
        )
        self.assertEqual((policy_count_before, policy_count_after), (1, 1))

    def test_schema_seven_migrates_but_nonterminal_runtime_blocks_bootstrap(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            path.parent.mkdir(parents=True, exist_ok=True)
            source = (
                Path(__file__).parent
                / "fixtures"
                / "runtime-schema7-main-f806fdb.sql"
            )
            connection = sqlite3.connect(path)
            try:
                connection.executescript(source.read_text(encoding="utf-8"))
                before = connection.execute(
                    """SELECT event_id, run_id, event_type, observed_at,
                              payload_json, source_sha256, source_line
                    FROM events WHERE event_id=?""",
                    ("22222222-2222-4222-8222-222222222222",),
                ).fetchone()
            finally:
                connection.close()

            RuntimeDatabase(path)
            with self.assertRaisesRegex(
                ProviderAdmissionConflict,
                "quiescent",
            ):
                ProviderAdmissionKernel(path)
            connection = sqlite3.connect(path)
            try:
                version = connection.execute(
                    "SELECT version FROM schema_meta WHERE component='runtime'"
                ).fetchone()[0]
                after = connection.execute(
                    """SELECT event_id, run_id, event_type, observed_at,
                              payload_json, source_sha256, source_line
                    FROM events WHERE event_id=?""",
                    ("22222222-2222-4222-8222-222222222222",),
                ).fetchone()
                batch_columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(plan_queue_batches)"
                    )
                }
                transition_count = connection.execute(
                    "SELECT COUNT(*) FROM provider_admission_transitions"
                ).fetchone()[0]
                state_count = connection.execute(
                    "SELECT COUNT(*) FROM provider_admission_state"
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(version, 8)
        self.assertEqual(before, after)
        self.assertEqual(
            after[4],
            '{"fixture":"schema7-main-f806fdb"}',
        )
        self.assertEqual((transition_count, state_count), (0, 0))
        self.assertTrue(
            {
                "project_binding_digest",
                "admission_lane",
                "provider_admission_policy_digest",
            }
            <= batch_columns
        )

    def test_quiescent_schema_seven_copy_replay_initializes_genesis(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            path.parent.mkdir(parents=True, exist_ok=True)
            source = (
                Path(__file__).parent
                / "fixtures"
                / "runtime-schema7-main-f806fdb.sql"
            )
            terminal_id = "33333333-3333-4333-8333-333333333333"
            connection = sqlite3.connect(path)
            try:
                connection.executescript(source.read_text(encoding="utf-8"))
                connection.execute(
                    """INSERT INTO events(
                        event_id, run_id, event_type, observed_at,
                        payload_json, source_sha256, source_line
                    ) VALUES (?, ?, 'provider.candidate_completed', ?, ?, NULL, NULL)""",
                    (
                        terminal_id,
                        "11111111-1111-4111-8111-111111111111",
                        "2026-09-10T00:01:00+00:00",
                        '{"fixture_terminal":true}',
                    ),
                )
                connection.execute(
                    """UPDATE runs SET terminal_event_id=?,
                        state='candidate_success', terminal_at=?
                    WHERE run_id=?""",
                    (
                        terminal_id,
                        "2026-09-10T00:01:00+00:00",
                        "11111111-1111-4111-8111-111111111111",
                    ),
                )
                connection.commit()
                before = tuple(
                    connection.execute(
                        """SELECT event_id, run_id, event_type, observed_at,
                                  payload_json, source_sha256, source_line
                        FROM events ORDER BY sequence"""
                    ).fetchall()
                )
            finally:
                connection.close()

            RuntimeDatabase(path)
            kernel = ProviderAdmissionKernel(path)
            status = kernel.status("glm_flash_worker")
            connection = sqlite3.connect(path)
            try:
                after = tuple(
                    connection.execute(
                        """SELECT event_id, run_id, event_type, observed_at,
                                  payload_json, source_sha256, source_line
                        FROM events ORDER BY sequence"""
                    ).fetchall()
                )
                transition = connection.execute(
                    """SELECT transition_kind, control_revision
                    FROM provider_admission_transitions"""
                ).fetchone()
            finally:
                connection.close()

        self.assertEqual(before, after)
        self.assertEqual(transition, ("genesis", 1))
        self.assertTrue(status.initialized)

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
                state_columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(provider_admission_state)"
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
                "provider_admission_transitions",
            }
            <= tables
        )
        self.assertTrue(
            {
                "deployment_mode",
                "deployment_digest",
                "half_open_probe_request_digest",
                "control_revision",
                "control_digest",
            }
            <= state_columns
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
    def test_target_activation_revalidates_epoch_under_write_lock(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(path, now=self.clock)
            kernel = ProviderAdmissionKernel(path, now=self.clock)
            target = ProviderAdmissionTargetBinding.create(
                kernel.policy,
                target=32,
            )
            reference = authorities.issue(
                source_kind="operator_capacity_authority",
                source_id="stale-target-thirty-two",
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
            original_verify = kernel.authorities.verify

            def verify_then_supersede(*args, **kwargs):
                result = original_verify(*args, **kwargs)
                kernel.authorities.advance_epoch(
                    reason_digest="d" * 64,
                    state="open",
                )
                return result

            with patch.object(
                kernel.authorities,
                "verify",
                side_effect=verify_then_supersede,
            ):
                with self.assertRaisesRegex(
                    DispatchAuthorizationError,
                    "stale epoch",
                ):
                    kernel.activate_target(target, reference)
            status = kernel.status(kernel.policy.provider_id)
            connection = sqlite3.connect(path)
            try:
                transitions = connection.execute(
                    "SELECT COUNT(*) FROM provider_admission_transitions"
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(status.effective_target, 8)
        self.assertEqual(transitions, 1)

    def test_half_open_activation_revalidates_authority_under_write_lock(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(path, now=self.clock)
            dispatch_reference = self._authority(
                authorities,
                (self.project_a,),
            )
            kernel = ProviderAdmissionKernel(path, now=self.clock)
            opening_request = self._request(
                dispatch_reference,
                self.project_a,
                AdmissionLane.ROUTINE,
            )
            opening = kernel.try_admit(opening_request, ttl_seconds=60)
            kernel.begin_transport(opening, opening_request)
            kernel.finish(
                opening,
                network_attempted=True,
                response_received=True,
                provider_http_status=429,
                terminal_persisted=True,
                terminal_evidence_digest="a" * 64,
            )
            probe_request = self._request(
                dispatch_reference,
                self.project_a,
                AdmissionLane.INTERACTIVE,
            )
            binding = ProviderAdmissionCircuitBinding.create(
                kernel.policy,
                from_state="open",
                to_state="half_open",
                probe_request_digest=probe_request.binding_digest,
            )
            circuit_reference = authorities.issue(
                source_kind="operator_circuit_authority",
                source_id="revoked-half-open",
                scope=AuthorityScope(
                    providers=(kernel.policy.provider_id,),
                    planes=("provider_circuit_activation",),
                    task_types=("provider_circuit_half_open",),
                    provider_admission_circuit_digests=(
                        binding.binding_digest,
                    ),
                    scope_contract_version=3,
                ),
                expires_at=(
                    self.clock.value + timedelta(minutes=5)
                ).isoformat(),
            )
            original_verify = kernel.authorities.verify

            def verify_then_revoke(reference_arg, *args, **kwargs):
                result = original_verify(reference_arg, *args, **kwargs)
                if reference_arg == circuit_reference:
                    authorities.revoke(circuit_reference)
                return result

            with patch.object(
                kernel.authorities,
                "verify",
                side_effect=verify_then_revoke,
            ):
                with self.assertRaisesRegex(
                    DispatchAuthorizationError,
                    "revoked",
                ):
                    kernel.activate_half_open(
                        binding,
                        circuit_reference,
                        probe_request,
                    )
            status = kernel.status(kernel.policy.provider_id)
            connection = sqlite3.connect(path)
            try:
                transitions = connection.execute(
                    "SELECT COUNT(*) FROM provider_admission_transitions"
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(status.circuit_state, "open")
        self.assertEqual(transitions, 2)

    def test_operator_can_activate_any_target_through_hard_max(self) -> None:
        for selected_target in (1, 7, 16, 24, 32):
            with self.subTest(target=selected_target), d_drive_tempdir() as temp:
                path = temp / "runtime" / "dispatch.sqlite3"
                authorities = DispatchAuthorityStore(path, now=self.clock)
                kernel = ProviderAdmissionKernel(path, now=self.clock)
                target = ProviderAdmissionTargetBinding.create(
                    kernel.policy,
                    target=selected_target,
                )
                reference = authorities.issue(
                    source_kind="operator_capacity_authority",
                    source_id=f"target-{selected_target}",
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

                status = kernel.activate_target(target, reference)

            self.assertEqual(status.effective_target, selected_target)

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
            probe_request = self._request(
                dispatch_reference,
                self.project_a,
                AdmissionLane.INTERACTIVE,
            )
            half_open = ProviderAdmissionCircuitBinding.create(
                kernel.policy,
                from_state="open",
                to_state="half_open",
                probe_request_digest=probe_request.binding_digest,
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
            kernel.activate_half_open(
                half_open,
                circuit_reference,
                probe_request,
            )
            with self.assertRaises(DispatchAuthorizationError):
                kernel.activate_half_open(
                    half_open,
                    circuit_reference,
                    probe_request,
                )
            with self.assertRaisesRegex(
                ProviderAdmissionReconciliationError,
                "another probe",
            ):
                kernel.try_admit(
                    self._request(
                        dispatch_reference,
                        self.project_a,
                        AdmissionLane.INTERACTIVE,
                    ),
                    ttl_seconds=60,
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

    def test_half_open_pre_network_failure_reopens_exact_probe_gate(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(path, now=self.clock)
            dispatch_reference = self._authority(
                authorities,
                (self.project_a,),
            )
            kernel = ProviderAdmissionKernel(path, now=self.clock)
            first_request = self._request(
                dispatch_reference,
                self.project_a,
                AdmissionLane.ROUTINE,
            )
            first = kernel.try_admit(first_request, ttl_seconds=60)
            kernel.begin_transport(first, first_request)
            kernel.finish(
                first,
                network_attempted=True,
                response_received=True,
                provider_http_status=429,
                terminal_persisted=True,
                terminal_evidence_digest="d" * 64,
            )
            probe_request = self._request(
                dispatch_reference,
                self.project_a,
                AdmissionLane.INTERACTIVE,
            )
            binding = ProviderAdmissionCircuitBinding.create(
                kernel.policy,
                from_state="open",
                to_state="half_open",
                probe_request_digest=probe_request.binding_digest,
            )
            circuit_reference = authorities.issue(
                source_kind="operator_circuit_authority",
                source_id="half-open-local-failure",
                scope=AuthorityScope(
                    providers=(kernel.policy.provider_id,),
                    planes=("provider_circuit_activation",),
                    task_types=("provider_circuit_half_open",),
                    provider_admission_circuit_digests=(
                        binding.binding_digest,
                    ),
                    scope_contract_version=3,
                ),
                expires_at=(
                    self.clock.value + timedelta(minutes=5)
                ).isoformat(),
            )
            kernel.activate_half_open(
                binding,
                circuit_reference,
                probe_request,
            )
            probe = kernel.try_admit(probe_request, ttl_seconds=60)
            kernel.begin_transport(probe, probe_request)
            kernel.finish(
                probe,
                network_attempted=False,
                response_received=False,
                provider_http_status=None,
                terminal_persisted=True,
                terminal_evidence_digest="e" * 64,
            )
            status = kernel.status(kernel.policy.provider_id)
            with self.assertRaises(ProviderAdmissionReconciliationError):
                kernel.try_admit(
                    self._request(
                        dispatch_reference,
                        self.project_a,
                        AdmissionLane.ROUTINE,
                    ),
                    ttl_seconds=60,
                )

        self.assertEqual(status.circuit_state, "open")
        self.assertEqual(status.last_signal, "known_pre_network_terminal")

    def test_target_two_downgrade_requires_exact_preissued_authority(self) -> None:
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
        self.assertEqual(
            ProviderAdmissionTargetBinding.create(
                kernel.policy,
                target=3,
            ).target,
            3,
        )
        with self.assertRaises(ValueError):
            ProviderAdmissionTargetBinding.create(kernel.policy, target=33)

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

    def test_tampered_effective_target_above_hard_max_fails_closed(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(path, now=self.clock)
            reference = self._authority(authorities, (self.project_a,))
            kernel = ProviderAdmissionKernel(path, now=self.clock)
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    """UPDATE provider_admission_state
                    SET effective_target=33 WHERE provider_id=?""",
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

    def test_in_range_target_tamper_is_rejected_by_control_receipt(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            kernel = ProviderAdmissionKernel(path, now=self.clock)
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    """UPDATE provider_admission_state
                    SET effective_target=2 WHERE provider_id=?""",
                    (kernel.policy.provider_id,),
                )
                connection.commit()
            finally:
                connection.close()

            with self.assertRaisesRegex(
                ProviderAdmissionConflict,
                "projection",
            ):
                kernel.status(kernel.policy.provider_id)

    def test_open_to_closed_tamper_is_rejected_by_control_receipt(self) -> None:
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
            kernel.finish(
                permit,
                network_attempted=True,
                response_received=True,
                provider_http_status=429,
                terminal_persisted=True,
                terminal_evidence_digest="f" * 64,
            )
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    """UPDATE provider_admission_state
                    SET circuit_state='closed' WHERE provider_id=?""",
                    (kernel.policy.provider_id,),
                )
                connection.commit()
            finally:
                connection.close()

            with self.assertRaisesRegex(
                ProviderAdmissionConflict,
                "projection",
            ):
                kernel.status(kernel.policy.provider_id)

    def test_control_receipts_reject_update_and_delete(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            kernel = ProviderAdmissionKernel(path, now=self.clock)
            connection = sqlite3.connect(path)
            try:
                with self.assertRaisesRegex(
                    sqlite3.DatabaseError,
                    "append-only",
                ):
                    connection.execute(
                        """UPDATE provider_admission_transitions
                        SET transition_kind='tampered' WHERE provider_id=?""",
                        (kernel.policy.provider_id,),
                    )
                connection.rollback()
                with self.assertRaisesRegex(
                    sqlite3.DatabaseError,
                    "append-only",
                ):
                    connection.execute(
                        """DELETE FROM provider_admission_transitions
                        WHERE provider_id=?""",
                        (kernel.policy.provider_id,),
                    )
            finally:
                connection.close()

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
        *,
        policy: ProviderAdmissionPolicy | None = None,
    ):
        policy = policy or glm_provider_admission_policy()
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
            policy = replace(
                glm_provider_admission_policy(),
                effective_target=1,
                per_project_cap=1,
            )
            authorities = DispatchAuthorityStore(path, now=self.clock)
            reference = self._authority(
                authorities,
                (self.project_a, self.project_b),
                policy=policy,
            )
            kernel = ProviderAdmissionKernel(
                path,
                policy=policy,
                now=self.clock,
            )
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
            policy = replace(
                glm_provider_admission_policy(),
                effective_target=1,
                per_project_cap=1,
            )
            authorities = DispatchAuthorityStore(path, now=self.clock)
            reference = self._authority(
                authorities,
                (self.project_a, self.project_b),
                policy=policy,
            )
            kernel = ProviderAdmissionKernel(
                path,
                policy=policy,
                now=self.clock,
            )
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
            policy = replace(
                glm_provider_admission_policy(),
                effective_target=1,
                per_project_cap=1,
            )
            authorities = DispatchAuthorityStore(path, now=self.clock)
            reference = self._authority(
                authorities,
                (self.project_a, self.project_b),
                policy=policy,
            )
            kernel = ProviderAdmissionKernel(
                path,
                policy=policy,
                now=self.clock,
            )
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

    def test_expired_grant_cannot_begin_transport_and_is_reconciled(self) -> None:
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
            permit = kernel.try_admit(request, ttl_seconds=1)
            self.clock.value += timedelta(seconds=2)

            with self.assertRaisesRegex(
                ProviderAdmissionReconciliationError,
                "expired",
            ):
                kernel.begin_transport(permit, request)
            record = kernel.read_request(request.request_id)
            status = kernel.status(kernel.policy.provider_id)

        self.assertEqual(record.state, "reconciliation_required")
        self.assertEqual(status.circuit_state, "open")

    def test_revoked_authority_cancels_grant_before_transport(self) -> None:
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
            authorities.revoke(reference)

            with self.assertRaisesRegex(
                DispatchAuthorizationError,
                "revoked",
            ):
                kernel.begin_transport(permit, request)
            record = kernel.read_request(request.request_id)
            status = kernel.status(kernel.policy.provider_id)

        self.assertEqual(record.state, "cancelled")
        self.assertEqual(status.project_active_counts, ())

    def test_open_circuit_cancels_another_preexisting_grant(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(path, now=self.clock)
            kernel = ProviderAdmissionKernel(path, now=self.clock)
            target = ProviderAdmissionTargetBinding.create(
                kernel.policy,
                target=2,
            )
            target_reference = authorities.issue(
                source_kind="operator_capacity_authority",
                source_id="superseded-grant-target-two",
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
            kernel.activate_target(target, target_reference)
            dispatch_reference = self._authority(
                authorities,
                (self.project_a, self.project_b),
            )
            first_request = self._request(
                dispatch_reference,
                self.project_a,
                AdmissionLane.ROUTINE,
            )
            second_request = self._request(
                dispatch_reference,
                self.project_b,
                AdmissionLane.BULK,
            )
            first = kernel.try_admit(first_request, ttl_seconds=60)
            second = kernel.try_admit(second_request, ttl_seconds=60)
            kernel.begin_transport(first, first_request)
            kernel.finish(
                first,
                network_attempted=True,
                response_received=True,
                provider_http_status=429,
                terminal_persisted=True,
                terminal_evidence_digest="a" * 64,
            )

            with self.assertRaisesRegex(
                ProviderAdmissionReconciliationError,
                "opened",
            ):
                kernel.begin_transport(second, second_request)
            second_record = kernel.read_request(second.request_id)
            status = kernel.status(kernel.policy.provider_id)

        self.assertEqual(second_record.state, "cancelled")
        self.assertEqual(status.circuit_state, "open")
        self.assertEqual(status.project_active_counts, ())

    def test_cancelled_half_open_probe_reopens_circuit(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(path, now=self.clock)
            dispatch_reference = self._authority(
                authorities,
                (self.project_a,),
            )
            kernel = ProviderAdmissionKernel(path, now=self.clock)
            opening_request = self._request(
                dispatch_reference,
                self.project_a,
                AdmissionLane.ROUTINE,
            )
            opening = kernel.try_admit(opening_request, ttl_seconds=60)
            kernel.begin_transport(opening, opening_request)
            kernel.finish(
                opening,
                network_attempted=True,
                response_received=True,
                provider_http_status=429,
                terminal_persisted=True,
                terminal_evidence_digest="b" * 64,
            )
            probe_request = self._request(
                dispatch_reference,
                self.project_a,
                AdmissionLane.INTERACTIVE,
            )
            binding = ProviderAdmissionCircuitBinding.create(
                kernel.policy,
                from_state="open",
                to_state="half_open",
                probe_request_digest=probe_request.binding_digest,
            )
            circuit_reference = authorities.issue(
                source_kind="operator_circuit_authority",
                source_id="cancelled-half-open",
                scope=AuthorityScope(
                    providers=(kernel.policy.provider_id,),
                    planes=("provider_circuit_activation",),
                    task_types=("provider_circuit_half_open",),
                    provider_admission_circuit_digests=(
                        binding.binding_digest,
                    ),
                    scope_contract_version=3,
                ),
                expires_at=(
                    self.clock.value + timedelta(minutes=5)
                ).isoformat(),
            )
            kernel.activate_half_open(
                binding,
                circuit_reference,
                probe_request,
            )
            probe = kernel.try_admit(probe_request, ttl_seconds=60)
            kernel.cancel_before_transport(probe)
            status = kernel.status(kernel.policy.provider_id)

        self.assertEqual(status.circuit_state, "open")
        self.assertEqual(status.last_signal, "half_open_cancelled")

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
            policy = replace(
                glm_provider_admission_policy(),
                effective_target=1,
                per_project_cap=1,
            )
            authorities = DispatchAuthorityStore(path, now=self.clock)
            reference = self._authority(
                authorities,
                (self.project_a, self.project_b),
                policy=policy,
            )
            kernel = ProviderAdmissionKernel(
                path,
                policy=policy,
                now=self.clock,
            )
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
