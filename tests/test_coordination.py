from __future__ import annotations

import dataclasses
import re
import unittest

from macr_runtime.canonical import sha256_id
from macr_runtime.coordination import (
    BudgetEvaluation,
    CoordinationPlan,
    EligibleCandidate,
    ExcludedCandidate,
    FallbackRule,
    ModelBinding,
    PlanExecutionMode,
    RoleSlot,
    TopologyId,
)
from macr_runtime.verification_graph import VerifierGraph, VerifierNode


SHA256 = re.compile(r"^[0-9a-f]{64}$")
DIGESTS = {
    name: sha256_id("coordination_test_v1", {"name": name})
    for name in (
        "task",
        "role",
        "capsule",
        "subject",
        "route",
        "qualification",
        "params",
        "policy",
        "evidence",
        "qualification_snapshot",
        "route_snapshot",
        "availability",
        "pricing",
        "topology_registry",
        "verifier_input",
        "verifier_config",
    )
}


def graph() -> VerifierGraph:
    return VerifierGraph.build(
        (
            VerifierNode(
                "exact",
                "sha256_exact",
                "1.0.0",
                (DIGESTS["verifier_input"],),
                config_digest=DIGESTS["verifier_config"],
            ),
        )
    )


def make_plan(
    *,
    plan_id: str = "11111111-1111-4111-8111-111111111111",
    revision: int = 1,
    evidence_snapshot_id: str | None = None,
) -> CoordinationPlan:
    verifier_graph = graph()
    role = RoleSlot.create(
        "worker",
        DIGESTS["role"],
        authority=("candidate_generate",),
        context_capsule_ids=(DIGESTS["capsule"],),
        verifier_graph_digest=verifier_graph.graph_digest,
    )
    binding = ModelBinding(
        slot_id="worker",
        model_subject_id=DIGESTS["subject"],
        route_id=DIGESTS["route"],
        qualification_key=DIGESTS["qualification"],
        parameter_profile_digest=DIGESTS["params"],
        context_capsule_ids=(DIGESTS["capsule"],),
    )
    eligible = EligibleCandidate(
        model_subject_id=DIGESTS["subject"],
        route_id=DIGESTS["route"],
        qualification_key=DIGESTS["qualification"],
        verified_utility_lower_bound=0.82,
        expected_total_cost_usd=0.01,
        expected_latency_ms=1000,
        evidence_freshness_epoch=10,
    )
    excluded = ExcludedCandidate(
        model_subject_id="a" * 64,
        route_id="b" * 64,
        reason_code="privacy_denied",
        reason_evidence_digest="c" * 64,
    )
    return CoordinationPlan.create(
        plan_id=plan_id,
        plan_revision=revision,
        planner_version="shadow-planner-v1",
        topology_id=TopologyId.T0_DIRECT_VERIFIED,
        execution_mode=PlanExecutionMode.SHADOW_ONLY,
        task_digest=DIGESTS["task"],
        roles=(role,),
        bindings=(binding,),
        context_capsule_ids=(DIGESTS["capsule"],),
        verifier_graph=verifier_graph,
        policy_snapshot_ids=(DIGESTS["policy"],),
        evidence_snapshot_ids=(
            evidence_snapshot_id or DIGESTS["evidence"],
        ),
        qualification_snapshot_id=DIGESTS["qualification_snapshot"],
        route_snapshot_id=DIGESTS["route_snapshot"],
        availability_snapshot_id=DIGESTS["availability"],
        pricing_snapshot_id=DIGESTS["pricing"],
        topology_registry_digest=DIGESTS["topology_registry"],
        eligible_candidates=(eligible,),
        excluded_candidates=(excluded,),
        budget_evaluation=BudgetEvaluation(
            budget_mode="warn",
            estimated_total_cost_usd=0.01,
            warning_threshold_usd=0.005,
            warning_triggered=True,
        ),
        fallback_rules=(
            FallbackRule(
                reason_code="provider_unavailable",
                from_route_id=DIGESTS["route"],
                to_route_id=None,
            ),
        ),
        tie_break_rules=(
            "verified_utility_desc",
            "total_cost_asc",
            "latency_asc",
            "freshness_desc",
            "route_id_asc",
        ),
    )


class CoordinationPlanTests(unittest.TestCase):
    def test_plan_digest_ignores_uuid_but_covers_revision_and_snapshots(self) -> None:
        first = make_plan(
            plan_id="11111111-1111-4111-8111-111111111111",
        )
        second = make_plan(
            plan_id="22222222-2222-4222-8222-222222222222",
        )

        self.assertRegex(first.plan_digest, SHA256)
        self.assertEqual(first.plan_digest, second.plan_digest)
        self.assertNotEqual(
            first.plan_digest,
            dataclasses.replace(second, plan_revision=2).plan_digest,
        )
        self.assertNotEqual(
            first.plan_digest,
            make_plan(evidence_snapshot_id="f" * 64).plan_digest,
        )
        self.assertNotEqual(
            first.plan_digest,
            dataclasses.replace(
                first,
                qualification_snapshot_id="e" * 64,
            ).plan_digest,
        )

    def test_plan_digest_covers_tie_break_budget_fallback_and_route_parameters(self) -> None:
        base = make_plan()
        variants = (
            dataclasses.replace(
                base,
                tie_break_rules=("route_id_asc",),
            ),
            dataclasses.replace(
                base,
                budget_evaluation=BudgetEvaluation(
                    budget_mode="warn",
                    estimated_total_cost_usd=0.02,
                    warning_threshold_usd=0.005,
                    warning_triggered=True,
                ),
            ),
            dataclasses.replace(base, fallback_rules=()),
            dataclasses.replace(
                base,
                bindings=(
                    dataclasses.replace(
                        base.bindings[0],
                        parameter_profile_digest="f" * 64,
                    ),
                ),
            ),
        )
        for variant in variants:
            self.assertNotEqual(base.plan_digest, variant.plan_digest)

    def test_plan_rejects_unbound_slots_capsules_or_verifier_graph(self) -> None:
        base = make_plan()
        with self.assertRaisesRegex(ValueError, "slot"):
            dataclasses.replace(
                base,
                bindings=(dataclasses.replace(base.bindings[0], slot_id="ghost"),),
            )
        with self.assertRaisesRegex(ValueError, "capsule"):
            dataclasses.replace(base, context_capsule_ids=("f" * 64,))
        with self.assertRaisesRegex(ValueError, "verifier graph"):
            dataclasses.replace(
                base,
                roles=(
                    dataclasses.replace(
                        base.roles[0],
                        verifier_graph_digest="f" * 64,
                    ),
                ),
            )

    def test_roles_models_routes_and_residents_are_not_collapsed(self) -> None:
        plan = make_plan()
        public = plan.to_dict()

        self.assertNotEqual(
            plan.roles[0].role_definition_digest,
            plan.bindings[0].model_subject_id,
        )
        self.assertNotEqual(
            plan.bindings[0].model_subject_id,
            plan.bindings[0].route_id,
        )
        self.assertNotIn("resident", str(public).lower())
        self.assertNotIn("host_session", str(public).lower())
        self.assertEqual(public["acceptance_authority"], "host_only")
        self.assertEqual(public["execution_mode"], "shadow_only")
        self.assertEqual(
            plan.tie_break_rules,
            (
                "verified_utility_desc",
                "total_cost_asc",
                "latency_asc",
                "freshness_desc",
                "route_id_asc",
            ),
        )


if __name__ == "__main__":
    unittest.main()
