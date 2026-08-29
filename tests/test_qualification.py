from __future__ import annotations

import unittest

from macr_runtime.canonical import sha256_id
from macr_runtime.model_identity import (
    ExecutionRouteIdentity,
    IdentityStatus,
    ModelSubject,
    QualificationKey,
    RoleDefinition,
)
from macr_runtime.observatory_db import ObservatoryDatabase
from macr_runtime.probe_registry import (
    ProbeClass,
    ProbeDefinition,
    ProbeRegistry,
)
from macr_runtime.qualification import (
    QualificationEngine,
    QualificationPolicy,
    QualificationState,
    wilson_lower_bound,
)

from tests.support import d_drive_tempdir


NOW = "2026-08-29T12:00:00+00:00"
OLD = "2026-07-01T00:00:00+00:00"
REQUEST = sha256_id("request_shape_v1", {"qualification": 1})
PARAMS = sha256_id("parameter_profile_v1", {"temperature": 0})
DATA_POLICY = sha256_id("data_policy_v1", {"class": "public"})
VERIFIER = sha256_id("verifier_suite_v1", {"version": "1"})
TASK_PACK = sha256_id("task_pack_v1", {"pack": "p0"})


def build_subject_route(
    store: ObservatoryDatabase,
    *,
    status: IdentityStatus = IdentityStatus.CLAIMED,
    provider: str = "z_ai_direct",
) -> tuple[ModelSubject, ExecutionRouteIdentity]:
    snapshot = store.append_snapshot(
        {
            "source_id": "qualification_fixture",
            "observed_at": "2026-06-01T00:00:00+00:00",
            "request_shape_sha256": REQUEST,
            "normalized_bytes_sha256": None,
            "parser_version": "qualification-v1",
        },
        raw_bytes=(provider + status.value).encode("utf-8"),
    )
    subject = ModelSubject.create(
        "z-ai",
        "glm-5.3-flash",
        "2026-08-28",
        status,
        snapshot.snapshot_id,
    )
    route = ExecutionRouteIdentity.create(
        subject.subject_id,
        provider,
        f"https://{provider}.example.invalid/v1",
        "glm-5.3-flash",
        PARAMS,
        "worker-v1",
        DATA_POLICY,
    )
    store.append_model_subject(subject)
    store.append_execution_route(route)
    return subject, route


def role(role_id: str) -> RoleDefinition:
    return RoleDefinition.create(
        role_id,
        authority=("candidate_generate",),
        context_classes=("public_text",),
        required_capabilities=("text_generation",),
    )


def definition(role_def: RoleDefinition, probe_id: str) -> ProbeDefinition:
    return ProbeDefinition.create(
        probe_id,
        ProbeClass.P0_EXACT_OUTPUT,
        "1.0.0",
        role_digest=role_def.role_digest,
        context_class="public_text",
        verifier_suite_digest=VERIFIER,
        task_pack_digest=TASK_PACK,
        held_out_variant_count=8,
        cost_ceiling_usd=0.05,
        mutation_controls=("trailing_newline",),
    )


def key_for(
    subject: ModelSubject,
    route: ExecutionRouteIdentity,
    role_def: RoleDefinition,
    probe_def: ProbeDefinition,
) -> QualificationKey:
    return QualificationKey.create(
        subject,
        route,
        role_def,
        "public_text",
        VERIFIER,
        probe_def.probe_digest,
    )


def append_trials(
    store: ObservatoryDatabase,
    key: QualificationKey,
    count: int,
    *,
    observed_at: str = NOW,
    verifier_passed: bool = True,
    negative_control_passed: bool = True,
    bound_versions_current: bool = True,
    lineage_complete: bool = True,
    conflicting: bool = False,
) -> None:
    for index in range(count):
        trial_id = sha256_id(
            "probe_trial_v1",
            {"qualification": key.digest, "index": index},
        )
        store.append_evidence(
            {
                "qualification_key": key.digest,
                "kind": "probe_result",
                "subject_digest": key.model_subject_id,
                "observed_at": observed_at,
                "payload": {
                    "trial_id": trial_id,
                    "model_subject_id": key.model_subject_id,
                    "route_id": key.route_id,
                    "role_digest": key.role_digest,
                    "context_class": key.context_class,
                    "verifier_suite_digest": key.verifier_suite_digest,
                    "probe_digest": key.probe_digest,
                    "provider_terminal_success": True,
                    "verifier_passed": verifier_passed,
                    "negative_control_passed": negative_control_passed,
                    "bound_versions_current": bound_versions_current,
                    "lineage_complete": lineage_complete,
                    "conflicting": conflicting,
                    "blind_spots": [],
                },
            }
        )


def policy(**changes) -> QualificationPolicy:
    values = {
        "min_trials": 5,
        "minimum_lower_bound": 0.80,
        "max_evidence_age_days": 30,
        "require_negative_controls": True,
    }
    values.update(changes)
    return QualificationPolicy(**values)


class QualificationTests(unittest.TestCase):
    def test_tiny_green_sample_does_not_auto_qualify(self) -> None:
        self.assertLess(wilson_lower_bound(1, 1), 0.50)
        with d_drive_tempdir() as temp:
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            subject, route_item = build_subject_route(store)
            worker = role("worker")
            probe = definition(worker, "worker-p0")
            key = key_for(subject, route_item, worker, probe)
            append_trials(store, key, 1)
            decision = QualificationEngine(
                store,
                ProbeRegistry((probe,)),
            ).evaluate(key, policy(), NOW)

        self.assertIs(decision.state, QualificationState.SHADOW_ONLY)
        self.assertEqual(decision.trials, 1)
        self.assertIn("minimum_trials_not_met", decision.blind_spots)

    def test_role_and_route_qualification_do_not_transfer(self) -> None:
        with d_drive_tempdir() as temp:
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            subject, direct = build_subject_route(store)
            _, router = build_subject_route(store, provider="router_claim")
            worker = role("worker")
            reviewer = role("reviewer")
            worker_probe = definition(worker, "worker-p0")
            reviewer_probe = definition(reviewer, "reviewer-p0")
            direct_worker = key_for(subject, direct, worker, worker_probe)
            direct_reviewer = key_for(subject, direct, reviewer, reviewer_probe)
            router_worker = key_for(subject, router, worker, worker_probe)
            append_trials(store, direct_worker, 20)
            engine = QualificationEngine(
                store,
                ProbeRegistry((worker_probe, reviewer_probe)),
            )

            qualified = engine.evaluate(direct_worker, policy(), NOW)
            reviewer_decision = engine.evaluate(direct_reviewer, policy(), NOW)
            router_decision = engine.evaluate(router_worker, policy(), NOW)

        self.assertIs(qualified.state, QualificationState.QUALIFIED)
        self.assertGreaterEqual(qualified.lower_bound, 0.80)
        self.assertIs(reviewer_decision.state, QualificationState.UNTESTED)
        self.assertIs(router_decision.state, QualificationState.UNTESTED)

    def test_incomplete_lineage_never_qualifies(self) -> None:
        with d_drive_tempdir() as temp:
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            subject, route_item = build_subject_route(store)
            worker = role("worker")
            probe = definition(worker, "worker-p0")
            key = key_for(subject, route_item, worker, probe)
            append_trials(store, key, 20, lineage_complete=False)
            decision = QualificationEngine(
                store,
                ProbeRegistry((probe,)),
            ).evaluate(key, policy(), NOW)

        self.assertIs(decision.state, QualificationState.SHADOW_ONLY)
        self.assertIn("lineage_incomplete", decision.blind_spots)

    def test_failed_negative_control_conflict_staleness_and_invalidation_fail_closed(self) -> None:
        scenarios = (
            (
                {"negative_control_passed": False},
                None,
                QualificationState.REJECTED,
            ),
            ({"conflicting": True}, None, QualificationState.REJECTED),
            ({"observed_at": OLD}, None, QualificationState.STALE),
            (
                {},
                "route_policy_changed",
                QualificationState.STALE,
            ),
            (
                {
                    "negative_control_passed": False,
                    "observed_at": OLD,
                },
                "route_policy_changed",
                QualificationState.REJECTED,
            ),
        )
        for trial_changes, invalidation, expected in scenarios:
            with self.subTest(expected=expected), d_drive_tempdir() as temp:
                store = ObservatoryDatabase(
                    temp / "observatory.sqlite3",
                    temp / "snapshots",
                )
                subject, route_item = build_subject_route(store)
                worker = role("worker")
                probe = definition(worker, "worker-p0")
                key = key_for(subject, route_item, worker, probe)
                append_trials(store, key, 20, **trial_changes)
                if invalidation is not None:
                    store.append_qualification_invalidation(
                        {
                            "qualification_key": key.digest,
                            "reason_code": invalidation,
                            "source_id": "policy_snapshot",
                            "invalidated_at": NOW,
                        }
                    )
                decision = QualificationEngine(
                    store,
                    ProbeRegistry((probe,)),
                ).evaluate(key, policy(), NOW)
            self.assertIs(decision.state, expected)

    def test_decision_is_idempotently_persisted_with_exact_evidence_set(self) -> None:
        with d_drive_tempdir() as temp:
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            subject, route_item = build_subject_route(store)
            worker = role("worker")
            probe = definition(worker, "worker-p0")
            key = key_for(subject, route_item, worker, probe)
            append_trials(store, key, 20)
            engine = QualificationEngine(store, ProbeRegistry((probe,)))
            first = engine.evaluate(key, policy(), NOW)
            second = engine.evaluate(key, policy(), NOW)
            records = store.read_qualification_decisions(key.digest)
            expected_evidence_ids = tuple(
                item.evidence_id for item in store.read_evidence(key.digest)
            )

        self.assertEqual(first, second)
        self.assertEqual(len(records), 1)
        self.assertEqual(first.evidence_ids, expected_evidence_ids)


if __name__ == "__main__":
    unittest.main()
