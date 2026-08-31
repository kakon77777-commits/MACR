from __future__ import annotations

import json
import unittest
from importlib.resources import files

from macr_runtime.agent.contracts import (
    AGENT_RUN_SCHEMA_VERSION,
    AgentRunHeader,
    AgentRunIdentity,
    AgentRunState,
    AuthorityBinding,
    BudgetBinding,
    GoalBinding,
    MemoryBindingRef,
    PlanBinding,
    SemanticStateBinding,
    WorldBindingRef,
    agent_run_subject_digest,
    is_terminal_agent_run_state,
)
from macr_runtime.execution import AuthorizationReference, DispatchOrigin


RUN_A = "11111111-1111-4111-8111-111111111111"
RUN_B = "22222222-2222-4222-8222-222222222222"
PARENT_RUN = "33333333-3333-4333-8333-333333333333"


class AgentContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.origin = DispatchOrigin(
            host="codex",
            identifier_kind="task",
            native_id="task:fixture",
        )
        self.authorization = AuthorizationReference(
            source_kind="host_operator",
            source_id="authority:fixture",
            digest="a" * 64,
            revision=2,
            epoch=3,
            scope="agent:fixture",
        )
        self.goal = GoalBinding("goal:fixture", "b" * 64, 1)
        self.authority = AuthorityBinding(self.authorization)
        self.budget = BudgetBinding("budget:fixture", "c" * 64, 1)
        self.semantic = SemanticStateBinding("semantic:fixture", "d" * 64, 1)
        self.plan = PlanBinding("plan:fixture", "e" * 64, 1)
        self.world_a = WorldBindingRef("world:a", "f" * 64, 1)
        self.world_b = WorldBindingRef("world:b", "1" * 64, 1)
        self.memory_a = MemoryBindingRef(
            memory_system_id="mneme",
            profile_id="MLF-RM/0.1",
            subject_ref="agent:fixture",
            head_ref="memory-head:1",
            head_digest="2" * 64,
            access_policy_ref="policy:read-only",
            projection_policy_ref="projection:bounded",
        )
        self.memory_b = MemoryBindingRef(
            memory_system_id="archive",
            profile_id="archive/0.1",
            subject_ref="project:fixture",
            head_ref=None,
            head_digest=None,
            access_policy_ref="policy:reference-only",
            projection_policy_ref="projection:none",
        )

    def make_identity(self, run_id: str = RUN_A) -> AgentRunIdentity:
        return AgentRunIdentity(
            agent_run_id=run_id,
            subject_digest=agent_run_subject_digest(
                agent_ref="agent:fixture",
                origin=self.origin,
                goal=self.goal,
                authority=self.authority,
                budget=self.budget,
                world_bindings=(self.world_b, self.world_a),
                memory_bindings=(self.memory_b, self.memory_a),
            ),
        )

    def make_header(self, **overrides: object) -> AgentRunHeader:
        values: dict[str, object] = {
            "schema_version": AGENT_RUN_SCHEMA_VERSION,
            "identity": self.make_identity(),
            "agent_ref": "agent:fixture",
            "origin": self.origin,
            "state": AgentRunState.CREATED,
            "state_revision": 1,
            "epoch": 0,
            "goal": self.goal,
            "authority": self.authority,
            "budget": self.budget,
            "semantic_state": None,
            "active_plan": None,
            "world_bindings": (self.world_b, self.world_a),
            "memory_bindings": (self.memory_b, self.memory_a),
            "parent_agent_run_id": None,
            "delegation_ref": None,
            "created_at": "2026-08-31T08:00:00+08:00",
        }
        values.update(overrides)
        return AgentRunHeader(**values)

    def test_valid_agent_run_header_round_trips_closed_public_shape(self) -> None:
        header = self.make_header(
            state=AgentRunState.ACTIVE,
            state_revision=2,
            epoch=1,
            semantic_state=self.semantic,
            active_plan=self.plan,
        )

        public = header.to_public_dict()
        rebuilt = AgentRunHeader.from_dict(public)

        self.assertEqual(rebuilt, header)
        self.assertEqual(public["schema_version"], "macr-agent-run/v1")
        self.assertEqual(public["created_at"], "2026-08-31T00:00:00+00:00")
        self.assertEqual(
            [item["binding_digest"] for item in public["world_bindings"]],
            sorted(item.binding_digest for item in (self.world_a, self.world_b)),
        )
        self.assertNotIn("memory_content", json.dumps(public))

    def test_same_subject_can_have_distinct_occurrence_ids(self) -> None:
        first = self.make_identity(RUN_A)
        second = self.make_identity(RUN_B)

        self.assertNotEqual(first.agent_run_id, second.agent_run_id)
        self.assertEqual(first.subject_digest, second.subject_digest)

    def test_subject_digest_ignores_set_like_binding_input_order(self) -> None:
        forward = agent_run_subject_digest(
            agent_ref="agent:fixture",
            origin=self.origin,
            goal=self.goal,
            authority=self.authority,
            budget=self.budget,
            world_bindings=(self.world_a, self.world_b),
            memory_bindings=(self.memory_a, self.memory_b),
        )
        reverse = agent_run_subject_digest(
            agent_ref="agent:fixture",
            origin=self.origin,
            goal=self.goal,
            authority=self.authority,
            budget=self.budget,
            world_bindings=(self.world_b, self.world_a),
            memory_bindings=(self.memory_b, self.memory_a),
        )

        self.assertEqual(forward, reverse)

    def test_subject_digest_changes_with_goal_authority_or_memory(self) -> None:
        baseline = self.make_identity().subject_digest
        changed_goal = GoalBinding("goal:fixture", "9" * 64, 1)
        changed_memory = MemoryBindingRef(
            memory_system_id="mneme",
            profile_id="MLF-RM/0.2",
            subject_ref="agent:fixture",
            head_ref="memory-head:1",
            head_digest="2" * 64,
            access_policy_ref="policy:read-only",
            projection_policy_ref="projection:bounded",
        )

        goal_digest = agent_run_subject_digest(
            agent_ref="agent:fixture",
            origin=self.origin,
            goal=changed_goal,
            authority=self.authority,
            budget=self.budget,
            world_bindings=(self.world_a, self.world_b),
            memory_bindings=(self.memory_a, self.memory_b),
        )
        memory_digest = agent_run_subject_digest(
            agent_ref="agent:fixture",
            origin=self.origin,
            goal=self.goal,
            authority=self.authority,
            budget=self.budget,
            world_bindings=(self.world_a, self.world_b),
            memory_bindings=(changed_memory, self.memory_b),
        )

        self.assertNotEqual(goal_digest, baseline)
        self.assertNotEqual(memory_digest, baseline)

    def test_authority_binding_reuses_existing_reference(self) -> None:
        public = self.authority.to_public_dict()

        self.assertIs(self.authority.reference, self.authorization)
        self.assertEqual(public["digest"], "a" * 64)
        self.assertEqual(public["revision"], 2)
        self.assertEqual(public["epoch"], 3)
        self.assertEqual(
            AuthorityBinding.from_dict(public).reference,
            self.authorization,
        )

    def test_memory_binding_is_reference_only_and_digest_bound(self) -> None:
        public = self.memory_a.to_public_dict()

        self.assertNotIn("content", public)
        self.assertNotIn("text", public)
        self.assertEqual(public["binding_digest"], self.memory_a.binding_digest)
        self.assertEqual(MemoryBindingRef.from_dict(public), self.memory_a)

    def test_memory_head_ref_and_digest_must_be_paired(self) -> None:
        for head_ref, head_digest in (("memory-head:1", None), (None, "2" * 64)):
            with self.subTest(head_ref=head_ref):
                with self.assertRaisesRegex(ValueError, "both present or both absent"):
                    MemoryBindingRef(
                        memory_system_id="mneme",
                        profile_id="MLF-RM/0.1",
                        subject_ref="agent:fixture",
                        head_ref=head_ref,
                        head_digest=head_digest,
                        access_policy_ref="policy:read-only",
                        projection_policy_ref="projection:bounded",
                    )

    def test_header_rejects_invalid_revision_epoch_and_wrong_authority(self) -> None:
        with self.assertRaises(ValueError):
            self.make_header(state_revision=0)
        with self.assertRaises(ValueError):
            self.make_header(epoch=-1)
        with self.assertRaises(ValueError):
            self.make_header(authority="user said yes")

    def test_parent_and_delegation_refs_are_paired(self) -> None:
        with self.assertRaisesRegex(ValueError, "parent and delegation"):
            self.make_header(parent_agent_run_id=PARENT_RUN)
        with self.assertRaisesRegex(ValueError, "parent and delegation"):
            self.make_header(delegation_ref="delegation:1")

        child = self.make_header(
            parent_agent_run_id=PARENT_RUN,
            delegation_ref="delegation:1",
        )
        self.assertEqual(child.parent_agent_run_id, PARENT_RUN)

    def test_from_dict_rejects_unknown_fields_and_invalid_schema(self) -> None:
        public = self.make_header().to_public_dict()
        public["authorized"] = True
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            AgentRunHeader.from_dict(public)

        public = self.make_header().to_public_dict()
        public["schema_version"] = "macr-agent-run/v2"
        with self.assertRaisesRegex(ValueError, "schema_version"):
            AgentRunHeader.from_dict(public)

    def test_terminal_state_helper_is_exact(self) -> None:
        for state in AgentRunState:
            self.assertEqual(
                is_terminal_agent_run_state(state),
                state
                in {
                    AgentRunState.COMPLETED,
                    AgentRunState.FAILED,
                    AgentRunState.CANCELLED,
                },
            )
        with self.assertRaises(ValueError):
            is_terminal_agent_run_state("completed")

    def test_agent_schema_is_packaged_closed_and_versioned(self) -> None:
        schema_path = files("macr_runtime.agent").joinpath(
            "schemas/agent-contracts-v1.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(
            schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertEqual(schema["$id"], "urn:evemisslab:macr:agent-contracts:v1")
        self.assertFalse(schema["$defs"]["AgentRunHeader"]["additionalProperties"])
        self.assertIn("MemoryBindingRef", schema["$defs"])
        self.assertEqual(
            {item["$ref"] for item in schema["oneOf"]},
            {
                "#/$defs/AgentRunHeader",
                "#/$defs/AgentRunIdentity",
                "#/$defs/GoalBinding",
                "#/$defs/AuthorityBinding",
                "#/$defs/BudgetBinding",
                "#/$defs/SemanticStateBinding",
                "#/$defs/PlanBinding",
                "#/$defs/WorldBindingRef",
                "#/$defs/MemoryBindingRef",
            },
        )


if __name__ == "__main__":
    unittest.main()
