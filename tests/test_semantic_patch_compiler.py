from __future__ import annotations

import unittest

from macr_runtime.semantic.contracts import (
    ResolutionStatus,
    SemanticLifecycleStatus,
    SemanticNodeType,
    SemanticPatch,
    SemanticRelation,
    SemanticRelationType,
)
from macr_runtime.semantic.errors import (
    SemanticGraphHeadStaleError,
    SemanticNodeConflictError,
    SemanticPatchInvalidError,
    SemanticRelationDanglingError,
    SemanticRelationDirectionInvalidError,
    SemanticScopeEscalationError,
    SemanticSupersessionInvalidError,
)
from macr_runtime.semantic.patch import SemanticPatchCompiler
from macr_runtime.semantic.registry import SemanticRegistry
from tests.test_semantic_patch_validation import (
    empty_head,
    goal_plan_patch,
    proposal_for,
    provenance,
    semantic_node,
)


class SemanticPatchCompilerTests(unittest.TestCase):
    def test_goal_to_plan_patch_compiles_deterministically_without_sql(self) -> None:
        compiler = SemanticPatchCompiler(SemanticRegistry.from_builtin())
        proposal = proposal_for()

        first = compiler.compile(
            head=empty_head(),
            proposal=proposal,
            active_nodes=(),
            active_relations=(),
        )
        second = compiler.compile(
            head=empty_head(),
            proposal=proposal,
            active_nodes=(),
            active_relations=(),
        )

        self.assertEqual(second, first)
        self.assertEqual(first.next_graph_revision, 2)
        self.assertEqual(len(first.active_nodes), 2)
        self.assertEqual(len(first.active_relations), 1)
        self.assertNotEqual(first.next_graph_digest, empty_head().graph_digest)
        self.assertFalse(hasattr(first, "connection"))
        self.assertFalse(hasattr(compiler, "commit"))

    def test_unknown_effect_direction_dangling_and_scope_fail_distinctly(self) -> None:
        compiler = SemanticPatchCompiler(SemanticRegistry.from_builtin())
        head = empty_head()
        invalid_effect = semantic_node(
            "goal:bad-effect",
            SemanticNodeType.GOAL,
            effects=("invented.effect",),
        )
        cases = []
        cases.append(
            (
                SemanticPatch(
                    patch_id="patch:effect",
                    base_graph_digest=head.graph_digest,
                    add_nodes=(invalid_effect,),
                    add_relations=(),
                    status_updates=(),
                    supersession_refs=(),
                    producer_ref="model:candidate",
                ),
                SemanticPatchInvalidError,
            )
        )
        goal = semantic_node("goal:one", SemanticNodeType.GOAL)
        plan = semantic_node("plan:one", SemanticNodeType.PLAN)
        reverse = SemanticRelation(
            relation_id="relation:reverse",
            source_ref=plan.node_id,
            relation_type=SemanticRelationType.MOTIVATES,
            target_ref=goal.node_id,
            qualifiers={},
            provenance=provenance(),
        )
        cases.append(
            (
                SemanticPatch(
                    patch_id="patch:direction",
                    base_graph_digest=head.graph_digest,
                    add_nodes=(goal, plan),
                    add_relations=(reverse,),
                    status_updates=(),
                    supersession_refs=(),
                    producer_ref="model:candidate",
                ),
                SemanticRelationDirectionInvalidError,
            )
        )
        dangling = SemanticRelation(
            relation_id="relation:dangling",
            source_ref=goal.node_id,
            relation_type=SemanticRelationType.MOTIVATES,
            target_ref="plan:missing",
            qualifiers={},
            provenance=provenance(),
        )
        cases.append(
            (
                SemanticPatch(
                    patch_id="patch:dangling",
                    base_graph_digest=head.graph_digest,
                    add_nodes=(goal,),
                    add_relations=(dangling,),
                    status_updates=(),
                    supersession_refs=(),
                    producer_ref="model:candidate",
                ),
                SemanticRelationDanglingError,
            )
        )
        other_scope = semantic_node(
            "goal:other",
            SemanticNodeType.GOAL,
            scope_ref="project:other",
        )
        cases.append(
            (
                SemanticPatch(
                    patch_id="patch:scope",
                    base_graph_digest=head.graph_digest,
                    add_nodes=(other_scope,),
                    add_relations=(),
                    status_updates=(),
                    supersession_refs=(),
                    producer_ref="model:candidate",
                ),
                SemanticScopeEscalationError,
            )
        )

        for patch, error_type in cases:
            with self.subTest(patch=patch.patch_id):
                with self.assertRaises(error_type):
                    compiler.compile(
                        head=head,
                        proposal=proposal_for(patch),
                        active_nodes=(),
                        active_relations=(),
                    )

    def test_stale_head_and_registry_fail_before_compilation(self) -> None:
        compiler = SemanticPatchCompiler(SemanticRegistry.from_builtin())
        proposal = proposal_for()
        stale = empty_head()
        stale = type(stale)(
            graph_id=stale.graph_id,
            scope_ref=stale.scope_ref,
            graph_revision=2,
            registry_version=stale.registry_version,
            registry_digest=stale.registry_digest,
            active_node_record_digests=(),
            active_relation_digests=(),
            created_by_agent_run_id=stale.created_by_agent_run_id,
            created_at=stale.created_at,
            updated_at=stale.updated_at,
        )

        with self.assertRaises(SemanticGraphHeadStaleError):
            compiler.compile(
                head=stale,
                proposal=proposal,
                active_nodes=(),
                active_relations=(),
            )

    def test_silent_overwrite_requires_exact_supersession_and_preserves_old_record(self) -> None:
        compiler = SemanticPatchCompiler(SemanticRegistry.from_builtin())
        head = empty_head()
        old = semantic_node("goal:one", SemanticNodeType.GOAL, payload={"v": 1})
        head = type(head)(
            graph_id=head.graph_id,
            scope_ref=head.scope_ref,
            graph_revision=1,
            registry_version=head.registry_version,
            registry_digest=head.registry_digest,
            active_node_record_digests=(old.record_digest,),
            active_relation_digests=(),
            created_by_agent_run_id=head.created_by_agent_run_id,
            created_at=head.created_at,
            updated_at=head.updated_at,
        )
        replacement = semantic_node("goal:one", SemanticNodeType.GOAL, payload={"v": 2})
        invalid = SemanticPatch(
            patch_id="patch:overwrite",
            base_graph_digest=head.graph_digest,
            add_nodes=(replacement,),
            add_relations=(),
            status_updates=(),
            supersession_refs=(),
            producer_ref="model:candidate",
        )
        with self.assertRaises(SemanticNodeConflictError):
            compiler.compile(
                head=head,
                proposal=proposal_for(invalid, head=head),
                active_nodes=(old,),
                active_relations=(),
            )

        valid = SemanticPatch(
            patch_id="patch:supersede",
            base_graph_digest=head.graph_digest,
            add_nodes=(replacement,),
            add_relations=(),
            status_updates=(),
            supersession_refs=(old.record_digest,),
            producer_ref="model:candidate",
        )
        compiled = compiler.compile(
            head=head,
            proposal=proposal_for(valid, head=head),
            active_nodes=(old,),
            active_relations=(),
        )

        self.assertIn(old.record_digest, compiled.superseded_record_digests)
        self.assertIn(replacement, compiled.active_nodes)
        self.assertIn(old, compiled.historical_nodes)

    def test_status_update_is_exact_and_obligation_resolution_requires_evidence(self) -> None:
        compiler = SemanticPatchCompiler(SemanticRegistry.from_builtin())
        head = empty_head()
        obligation = semantic_node(
            "obligation:one",
            SemanticNodeType.OBLIGATION,
            status=ResolutionStatus.UNRESOLVED,
        )
        head = type(head)(
            graph_id=head.graph_id,
            scope_ref=head.scope_ref,
            graph_revision=1,
            registry_version=head.registry_version,
            registry_digest=head.registry_digest,
            active_node_record_digests=(obligation.record_digest,),
            active_relation_digests=(),
            created_by_agent_run_id=head.created_by_agent_run_id,
            created_at=head.created_at,
            updated_at=head.updated_at,
        )
        missing_evidence = SemanticPatch(
            patch_id="patch:resolve-missing",
            base_graph_digest=head.graph_digest,
            add_nodes=(),
            add_relations=(),
            status_updates=(
                {
                    "node_id": obligation.node_id,
                    "from_record_digest": obligation.record_digest,
                    "to_status": "resolved",
                    "reason_digest": "a" * 64,
                    "evidence_refs": [],
                },
            ),
            supersession_refs=(obligation.record_digest,),
            producer_ref="model:candidate",
        )
        with self.assertRaises(SemanticPatchInvalidError):
            compiler.compile(
                head=head,
                proposal=proposal_for(missing_evidence, head=head),
                active_nodes=(obligation,),
                active_relations=(),
            )

        valid = SemanticPatch(
            patch_id="patch:resolve",
            base_graph_digest=head.graph_digest,
            add_nodes=(),
            add_relations=(),
            status_updates=(
                {
                    "node_id": obligation.node_id,
                    "from_record_digest": obligation.record_digest,
                    "to_status": "resolved",
                    "reason_digest": "a" * 64,
                    "evidence_refs": ["evidence:human-decision"],
                },
            ),
            supersession_refs=(obligation.record_digest,),
            producer_ref="model:candidate",
        )
        compiled = compiler.compile(
            head=head,
            proposal=proposal_for(valid, head=head),
            active_nodes=(obligation,),
            active_relations=(),
        )

        self.assertIn(obligation, compiled.historical_nodes)
        self.assertEqual(compiled.status_updates[0].status, ResolutionStatus.RESOLVED)

    def test_unconsumed_supersession_and_unknown_status_fields_fail_closed(self) -> None:
        compiler = SemanticPatchCompiler(SemanticRegistry.from_builtin())
        head = empty_head()
        patch = SemanticPatch(
            patch_id="patch:unused",
            base_graph_digest=head.graph_digest,
            add_nodes=(),
            add_relations=(),
            status_updates=(),
            supersession_refs=("a" * 64,),
            producer_ref="model:candidate",
        )
        with self.assertRaises(SemanticSupersessionInvalidError):
            compiler.compile(
                head=head,
                proposal=proposal_for(patch),
                active_nodes=(),
                active_relations=(),
            )


if __name__ == "__main__":
    unittest.main()
