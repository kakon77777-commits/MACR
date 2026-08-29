from __future__ import annotations

import copy
import dataclasses
import unittest

from macr_runtime.coordinator_contract import (
    CoordinatorConstraints,
    CoordinatorProposal,
    compile_coordinator_proposal,
)
from macr_runtime.errors import CoordinatorPolicyError
from macr_runtime.execution import VerificationState
from macr_runtime.plan_runtime import PlanRuntime
from macr_runtime.planner import DynamicCoordinationPlanner
from macr_runtime.registry import ProviderRegistry

from tests.support import build_test_services, d_drive_tempdir
from tests.test_coordination import make_plan
from tests.test_plan_runtime import FakeProvider, StaticVerifier


ROLE_A = "a" * 64
ROLE_B = "b" * 64
TASK_A = "c" * 64
TASK_B = "d" * 64
SOURCE = "e" * 64


def constraints(parent=None) -> CoordinatorConstraints:
    parent = parent or make_plan()
    return CoordinatorConstraints.from_parent(
        parent,
        allowed_role_template_digests=(ROLE_A, ROLE_B),
        allowed_task_digests=(TASK_A, TASK_B),
        allowed_context_capsule_ids=parent.context_capsule_ids,
        allowed_capabilities=("text_generation", "structured_output"),
        max_children=3,
        per_child_cost_ceiling_usd=0.05,
        aggregate_cost_ceiling_usd=0.08,
    )


def document(parent=None) -> dict[str, object]:
    parent = parent or make_plan()
    capsule = parent.context_capsule_ids[0]
    return {
        "schema_version": 1,
        "parent_plan_digest": parent.plan_digest,
        "source_candidate_digest": SOURCE,
        "children": [
            {
                "child_id": "worker-a",
                "task_digest": TASK_A,
                "role_template_digest": ROLE_A,
                "context_capsule_ids": [capsule],
                "required_capabilities": ["text_generation"],
                "cost_ceiling_usd": 0.03,
            },
            {
                "child_id": "worker-b",
                "task_digest": TASK_B,
                "role_template_digest": ROLE_B,
                "context_capsule_ids": [capsule],
                "required_capabilities": [
                    "structured_output",
                    "text_generation",
                ],
                "cost_ceiling_usd": 0.04,
            },
        ],
    }


class CoordinatorContractTests(unittest.TestCase):
    def test_coordinator_cannot_issue_authority_or_request_host_powers(self) -> None:
        parent = make_plan()
        malicious = document(parent)
        malicious["authority"] = {
            "issue": True,
            "accept": True,
            "merge": True,
        }
        proposal = CoordinatorProposal.from_dict(malicious)

        with self.assertRaisesRegex(CoordinatorPolicyError, "authority"):
            compile_coordinator_proposal(proposal, constraints(parent))

    def test_context_role_task_and_capability_expansion_fail_closed(self) -> None:
        parent = make_plan()
        cases = (
            ("context", "context_capsule_ids", ["9" * 64]),
            ("role", "role_template_digest", "9" * 64),
            ("task", "task_digest", "9" * 64),
            ("capabilit", "required_capabilities", ["shell_execute"]),
        )
        for message, field, value in cases:
            with self.subTest(field=field):
                candidate = document(parent)
                candidate["children"][0][field] = value
                with self.assertRaisesRegex(CoordinatorPolicyError, message):
                    compile_coordinator_proposal(
                        CoordinatorProposal.from_dict(candidate),
                        constraints(parent),
                    )

    def test_child_and_aggregate_cost_limits_are_both_hard(self) -> None:
        parent = make_plan()
        child_over = document(parent)
        child_over["children"][0]["cost_ceiling_usd"] = 0.06
        with self.assertRaisesRegex(CoordinatorPolicyError, "child cost"):
            compile_coordinator_proposal(
                CoordinatorProposal.from_dict(child_over),
                constraints(parent),
            )

        aggregate_over = document(parent)
        aggregate_over["children"][0]["cost_ceiling_usd"] = 0.05
        aggregate_over["children"][1]["cost_ceiling_usd"] = 0.04
        with self.assertRaisesRegex(CoordinatorPolicyError, "aggregate cost"):
            compile_coordinator_proposal(
                CoordinatorProposal.from_dict(aggregate_over),
                constraints(parent),
            )

    def test_compile_is_deterministic_and_emits_no_execution_authority(self) -> None:
        parent = make_plan()
        first_document = document(parent)
        second_document = copy.deepcopy(first_document)
        second_document["children"].reverse()
        first = compile_coordinator_proposal(
            CoordinatorProposal.from_dict(first_document),
            constraints(parent),
        )
        second = DynamicCoordinationPlanner().compile_coordinator_proposal(
            CoordinatorProposal.from_dict(second_document),
            constraints(parent),
        )

        self.assertEqual(first, second)
        self.assertEqual(first.proposed_revision, parent.plan_revision + 1)
        self.assertEqual(first.execution_mode, "shadow_only")
        self.assertTrue(first.host_authorization_required)
        self.assertFalse(first.authority_issued)
        self.assertFalse(first.network_activity)
        self.assertEqual(len({item.member_digest for item in first.members}), 2)
        self.assertNotIn("provider_id", first.to_dict())
        self.assertNotIn("route_id", first.to_dict())

    def test_runtime_preparation_writes_no_authority_queue_event_or_provider_state(self) -> None:
        parent = make_plan()
        provider = FakeProvider()
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            runtime = PlanRuntime(
                ProviderRegistry((provider,)),
                services,
                StaticVerifier(VerificationState.PASSED),
            )
            revision = runtime.prepare_coordinator_revision(
                parent,
                CoordinatorProposal.from_dict(document(parent)),
                constraints(parent),
            )
            connection = services.events.database.connect()
            try:
                counts = {
                    table: connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                    for table in (
                        "dispatch_authorities",
                        "batch_authorities",
                        "plan_queue_batches",
                        "plan_queue_members",
                        "events",
                    )
                }
            finally:
                connection.close()

        self.assertEqual(revision.parent_plan_digest, parent.plan_digest)
        self.assertEqual(set(counts.values()), {0})
        self.assertEqual(provider.calls, 0)

    def test_parent_binding_and_duplicate_json_keys_fail(self) -> None:
        parent = make_plan()
        proposal = CoordinatorProposal.from_dict(document(parent))
        other_parent = dataclasses.replace(parent, plan_revision=2)
        with self.assertRaisesRegex(CoordinatorPolicyError, "parent"):
            compile_coordinator_proposal(proposal, constraints(other_parent))

        with self.assertRaisesRegex(ValueError, "duplicate"):
            CoordinatorProposal.from_json(
                '{"schema_version":1,"schema_version":1,'
                f'"parent_plan_digest":"{parent.plan_digest}",'
                f'"source_candidate_digest":"{SOURCE}","children":[]}}'
            )

    def test_revision_contract_rejects_invalid_member_and_cost_rewrite(self) -> None:
        parent = make_plan()
        revision = compile_coordinator_proposal(
            CoordinatorProposal.from_dict(document(parent)),
            constraints(parent),
        )
        with self.assertRaisesRegex(ValueError, "member_digest"):
            dataclasses.replace(
                revision.members[0],
                member_digest="not-a-digest",
            )
        with self.assertRaisesRegex(ValueError, "aggregate cost"):
            dataclasses.replace(
                revision,
                aggregate_cost_ceiling_usd=(
                    revision.aggregate_cost_ceiling_usd + 0.01
                ),
            )


if __name__ == "__main__":
    unittest.main()
