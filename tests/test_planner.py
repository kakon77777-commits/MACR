from __future__ import annotations

import dataclasses
import unittest

from macr_runtime.canonical import canonical_json_bytes, sha256_id
from macr_runtime.contracts import PrivacyLevel
from macr_runtime.coordination import RoleSlot, TopologyId
from macr_runtime.event_store import SqliteEventStore
from macr_runtime.model_identity import (
    ExecutionRouteIdentity,
    IdentityStatus,
    ModelSubject,
    QualificationKey,
    RoleDefinition,
)
from macr_runtime.planner import (
    DynamicCoordinationPlanner,
    ExclusionReason,
    PlanningCandidate,
    PlanningError,
    PlanningInput,
    PlanningState,
)
from macr_runtime.planning_contracts import (
    BudgetMode,
    ContextCapsule,
    ContextSourceItem,
    OperatorPolicyProfile,
)
from macr_runtime.probe_registry import ProbeClass, ProbeDefinition
from macr_runtime.qualification import QualificationState
from macr_runtime.verification_graph import VerifierGraph, VerifierNode

from tests.support import d_drive_tempdir


DIGESTS = {
    name: sha256_id("planner_test_v1", {"name": name})
    for name in (
        "snapshot",
        "params-a",
        "params-b",
        "data-policy",
        "verifier",
        "task-pack",
        "task",
        "qualification-snapshot",
        "route-snapshot",
        "availability-snapshot",
        "pricing-snapshot",
        "topology-registry",
        "evidence-snapshot",
        "source-bytes",
        "verifier-input",
        "verifier-config",
        "reason-evidence",
    )
}


def subject() -> ModelSubject:
    return ModelSubject.create(
        "z-ai",
        "glm-5.3-flash",
        "2026-08-28",
        IdentityStatus.CLAIMED,
        DIGESTS["snapshot"],
    )


def route(provider: str, params: str) -> ExecutionRouteIdentity:
    item = subject()
    return ExecutionRouteIdentity.create(
        item.subject_id,
        provider,
        f"https://{provider}.example.invalid/v1",
        "glm-5.3-flash",
        params,
        "worker-v1",
        DIGESTS["data-policy"],
    )


ROLE = RoleDefinition.create(
    "worker",
    authority=("candidate_generate",),
    context_classes=("public_text",),
    required_capabilities=("text_generation",),
)
PROBE = ProbeDefinition.create(
    "worker-p0",
    ProbeClass.P0_EXACT_OUTPUT,
    "1.0.0",
    role_digest=ROLE.role_digest,
    context_class="public_text",
    verifier_suite_digest=DIGESTS["verifier"],
    task_pack_digest=DIGESTS["task-pack"],
    held_out_variant_count=8,
    cost_ceiling_usd=0.05,
)


def qualification(route_item: ExecutionRouteIdentity) -> QualificationKey:
    return QualificationKey.create(
        subject(),
        route_item,
        ROLE,
        "public_text",
        DIGESTS["verifier"],
        PROBE.probe_digest,
    )


def verifier_graph() -> VerifierGraph:
    return VerifierGraph.build(
        (
            VerifierNode(
                "exact",
                "sha256_exact",
                "1.0.0",
                (DIGESTS["verifier-input"],),
                config_digest=DIGESTS["verifier-config"],
            ),
        )
    )


def candidate(
    route_item: ExecutionRouteIdentity,
    *,
    utility: float = 0.90,
    cost: float | None = 0.01,
    latency: float = 1000,
    privacy: tuple[PrivacyLevel, ...] = (PrivacyLevel.PUBLIC,),
    qualification_state: QualificationState = QualificationState.QUALIFIED,
    capabilities: tuple[str, ...] = ("text_generation",),
    route_allowlisted: bool = True,
    available: bool = True,
) -> PlanningCandidate:
    key = qualification(route_item)
    return PlanningCandidate(
        model_subject_id=subject().subject_id,
        identity_status=IdentityStatus.CLAIMED,
        provider_id=route_item.provider_id,
        route_id=route_item.route_id,
        parameter_profile_digest=route_item.parameter_profile_digest,
        qualification_key=key,
        qualification_state=qualification_state,
        qualification_evidence_set_digest=DIGESTS["evidence-snapshot"],
        approved_privacy=privacy,
        capabilities=capabilities,
        verifier_graph_digest=verifier_graph().graph_digest,
        route_allowlisted=route_allowlisted,
        available=available,
        expected_total_cost_usd=cost,
        expected_latency_ms=latency,
        verified_utility_lower_bound=utility,
        evidence_freshness_epoch=10,
        reason_evidence_digest=DIGESTS["reason-evidence"],
    )


def capsule(
    routes: tuple[str, ...],
    *,
    classification: PrivacyLevel = PrivacyLevel.PUBLIC,
    expires_at: str | None = None,
) -> ContextCapsule:
    return ContextCapsule.build(
        (
            ContextSourceItem(
                source_id="document:public-task",
                byte_sha256=DIGESTS["source-bytes"],
                selected_ranges=((0, 100),),
                selection_authority_digest=None,
            ),
        ),
        "capsule-v1",
        classification,
        (ROLE.role_digest,),
        routes,
        expires_at=expires_at,
    )


def planning_input(
    context_capsule: ContextCapsule,
    *,
    profile: OperatorPolicyProfile | None = None,
    max_cost_usd: float = 0.02,
) -> PlanningInput:
    policy = profile or OperatorPolicyProfile.owner_default()
    return PlanningInput(
        task_digest=DIGESTS["task"],
        required_role_digest=ROLE.role_digest,
        context_class="public_text",
        required_capabilities=("text_generation",),
        privacy=PrivacyLevel.PUBLIC,
        max_cost_usd=max_cost_usd,
        latency_objective_ms=5000,
        context_capsule_ids=(context_capsule.capsule_id,),
        operator_policy=policy,
        operator_policy_snapshot_id=policy.snapshot_id,
        qualification_snapshot_id=DIGESTS["qualification-snapshot"],
        route_snapshot_id=DIGESTS["route-snapshot"],
        availability_snapshot_id=DIGESTS["availability-snapshot"],
        pricing_snapshot_id=DIGESTS["pricing-snapshot"],
        evidence_snapshot_ids=(DIGESTS["evidence-snapshot"],),
        topology_registry_digest=DIGESTS["topology-registry"],
        planner_version="shadow-planner-v1",
        topology_id=TopologyId.T0_DIRECT_VERIFIED,
        plan_revision=1,
        planned_at="2026-08-29T00:00:00+00:00",
    )


def state(
    candidates: tuple[PlanningCandidate, ...],
    context_capsule: ContextCapsule,
) -> PlanningState:
    graph = verifier_graph()
    return PlanningState(
        role_slot=RoleSlot.create(
            "worker",
            ROLE.role_digest,
            authority=("candidate_generate",),
            context_capsule_ids=(context_capsule.capsule_id,),
            verifier_graph_digest=graph.graph_digest,
        ),
        verifier_graph=graph,
        context_capsules=(context_capsule,),
        candidates=candidates,
    )


def exclusion(plan, route_id: str):
    return next(item for item in plan.excluded_candidates if item.route_id == route_id)


class PlannerTests(unittest.TestCase):
    def test_cheapest_route_cannot_trade_off_privacy_or_stale_qualification(self) -> None:
        cheap_route = route("cheap_route", DIGESTS["params-a"])
        costly_route = route("costly_route", DIGESTS["params-b"])
        cap = capsule((cheap_route.route_id, costly_route.route_id))
        cheap = candidate(
            cheap_route,
            cost=0.0001,
            privacy=(PrivacyLevel.LOCAL_ONLY,),
        )
        costly = candidate(costly_route, cost=0.01)
        plan = DynamicCoordinationPlanner().plan(
            planning_input(cap),
            state((cheap, costly), cap),
        )

        self.assertEqual(plan.bindings[0].route_id, costly_route.route_id)
        self.assertEqual(
            exclusion(plan, cheap_route.route_id).reason_code,
            ExclusionReason.PRIVACY_DENIED.value,
        )

        stale = dataclasses.replace(
            cheap,
            approved_privacy=(PrivacyLevel.PUBLIC,),
            qualification_state=QualificationState.STALE,
        )
        stale_plan = DynamicCoordinationPlanner().plan(
            planning_input(cap),
            state((stale, costly), cap),
        )
        self.assertEqual(stale_plan.bindings[0].route_id, costly_route.route_id)
        self.assertEqual(
            exclusion(stale_plan, cheap_route.route_id).reason_code,
            ExclusionReason.QUALIFICATION_NOT_CURRENT.value,
        )

    def test_no_eligible_model_fails_without_dispatch_or_runtime_write(self) -> None:
        denied_route = route("denied", DIGESTS["params-a"])
        cap = capsule((denied_route.route_id,))
        denied = candidate(denied_route, route_allowlisted=False)
        with d_drive_tempdir() as temp:
            events = SqliteEventStore(temp / "dispatch.sqlite3")
            before = len(events.read_events())
            with self.assertRaisesRegex(PlanningError, "no eligible binding"):
                DynamicCoordinationPlanner().plan(
                    planning_input(cap),
                    state((denied,), cap),
                )
            after = len(events.read_events())

        self.assertEqual((before, after), (0, 0))

    def test_equal_candidates_use_route_id_tie_break_and_input_order_is_irrelevant(self) -> None:
        route_a = route("route_a", DIGESTS["params-a"])
        route_b = route("route_b", DIGESTS["params-b"])
        cap = capsule((route_a.route_id, route_b.route_id))
        a = candidate(route_a)
        b = candidate(route_b)
        planner = DynamicCoordinationPlanner(
            plan_id_factory=lambda: "11111111-1111-4111-8111-111111111111"
        )
        first = planner.plan(
            planning_input(cap),
            state((b, a), cap),
        )
        second = planner.plan(
            planning_input(cap),
            state((a, b), cap),
        )

        self.assertEqual(
            first.bindings[0].route_id,
            min(route_a.route_id, route_b.route_id),
        )
        self.assertEqual(first.plan_digest, second.plan_digest)
        self.assertEqual(
            canonical_json_bytes(first.canonical_plan()),
            canonical_json_bytes(second.canonical_plan()),
        )

    def test_warn_only_budget_records_warning_but_enforce_mode_denies(self) -> None:
        route_item = route("costly", DIGESTS["params-a"])
        cap = capsule((route_item.route_id,))
        costly = candidate(route_item, cost=0.10)
        warn_plan = DynamicCoordinationPlanner().plan(
            planning_input(cap, max_cost_usd=0.02),
            state((costly,), cap),
        )

        self.assertTrue(warn_plan.budget_evaluation.warning_triggered)
        self.assertEqual(warn_plan.budget_evaluation.budget_mode, "warn")

        enforce = dataclasses.replace(
            OperatorPolicyProfile.owner_default(),
            budget_mode=BudgetMode.ENFORCE,
        )
        with self.assertRaisesRegex(PlanningError, "no eligible binding"):
            DynamicCoordinationPlanner().plan(
                planning_input(cap, profile=enforce, max_cost_usd=0.02),
                state((costly,), cap),
            )

    def test_fallback_is_new_plan_revision_not_silent_substitution(self) -> None:
        route_a = route("route_a", DIGESTS["params-a"])
        route_b = route("route_b", DIGESTS["params-b"])
        cap = capsule((route_a.route_id, route_b.route_id))
        a = candidate(route_a, utility=0.9)
        b = candidate(route_b, utility=0.8)
        planner = DynamicCoordinationPlanner(
            plan_id_factory=lambda: "11111111-1111-4111-8111-111111111111"
        )
        planning_state = state((a, b), cap)
        original = planner.plan(planning_input(cap), planning_state)
        revised = planner.revise_for_failure(
            original,
            failure_reason="provider_unavailable",
            state=planning_state,
        )

        self.assertEqual(revised.plan_revision, original.plan_revision + 1)
        self.assertNotEqual(revised.plan_digest, original.plan_digest)
        self.assertNotEqual(
            revised.bindings[0].route_id,
            original.bindings[0].route_id,
        )
        self.assertEqual(
            revised.fallback_rules[-1].reason_code,
            "provider_unavailable",
        )
        self.assertEqual(
            revised.fallback_rules[-1].from_route_id,
            original.bindings[0].route_id,
        )
        self.assertEqual(
            revised.fallback_rules[-1].to_route_id,
            revised.bindings[0].route_id,
        )

    def test_capsule_classification_and_expiry_are_hard_gates(self) -> None:
        external_route = route("external", DIGESTS["params-a"])
        local_route = route("local", DIGESTS["params-b"])
        local_capsule = capsule(
            (external_route.route_id, local_route.route_id),
            classification=PrivacyLevel.LOCAL_ONLY,
        )
        external = candidate(
            external_route,
            cost=0.0001,
            privacy=(PrivacyLevel.PUBLIC,),
        )
        local = candidate(
            local_route,
            cost=0.01,
            privacy=(PrivacyLevel.PUBLIC, PrivacyLevel.LOCAL_ONLY),
        )
        plan = DynamicCoordinationPlanner().plan(
            planning_input(local_capsule),
            state((external, local), local_capsule),
        )

        self.assertEqual(plan.bindings[0].route_id, local_route.route_id)
        self.assertEqual(
            exclusion(plan, external_route.route_id).reason_code,
            ExclusionReason.PRIVACY_DENIED.value,
        )

        expired = capsule(
            (local_route.route_id,),
            expires_at="2026-08-28T00:00:00+00:00",
        )
        with self.assertRaisesRegex(PlanningError, "no eligible binding"):
            DynamicCoordinationPlanner().plan(
                planning_input(expired),
                state((local,), expired),
            )


if __name__ == "__main__":
    unittest.main()
