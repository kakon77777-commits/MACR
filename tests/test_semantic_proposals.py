from __future__ import annotations

import dataclasses
import inspect
import unittest

from macr_runtime.agent.database import AgentDatabase
from macr_runtime.agent.store import AgentStore
from macr_runtime.semantic.contracts import (
    SemanticPatch,
    SemanticRelation,
    SemanticRelationType,
)
from macr_runtime.semantic.errors import SemanticPatchConflictError
from macr_runtime.semantic.patch import SemanticPatchProposalRequest
from macr_runtime.semantic.service import SemanticProposalService
from macr_runtime.semantic.store import SemanticStore
from tests.support import d_drive_tempdir
from tests.test_agent_state import RUN_ID, make_header
from tests.test_semantic_patch_validation import (
    GRAPH_ID,
    empty_head,
    goal_plan_patch,
    proposal_for,
    provenance,
    semantic_node,
)
from macr_runtime.semantic.contracts import SemanticNodeType


class SemanticProposalTests(unittest.TestCase):
    def _services(self, temp):
        path = temp / "agent.sqlite3"
        agent_store = AgentStore(path)
        agent_store.create_agent_run(make_header())
        semantic_store = SemanticStore(AgentDatabase(path))
        semantic_store.create_graph(
            graph_id=GRAPH_ID,
            scope_ref="project:phase-c",
            created_by_agent_run_id=RUN_ID,
            created_at="2026-09-01T00:00:00+00:00",
        )
        return agent_store, semantic_store, SemanticProposalService(semantic_store)

    def test_valid_proposal_persists_without_advancing_graph_or_agent(self) -> None:
        with d_drive_tempdir() as temp:
            agent_store, semantic_store, service = self._services(temp)
            before_head = semantic_store.get_graph_head(GRAPH_ID)
            before_agent = agent_store.get_agent_run(RUN_ID)

            record = service.propose_patch(
                proposal_for(),
                created_at="2026-09-01T01:00:00+00:00",
            )

            after_head = semantic_store.get_graph_head(GRAPH_ID)
            after_agent = agent_store.get_agent_run(RUN_ID)
            observed = service.get_proposal(record.proposal.proposal_id)
            connection = semantic_store.database.connect()
            try:
                counts = {
                    table: connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                    for table in (
                        "semantic_nodes",
                        "semantic_relations",
                        "semantic_graph_revisions",
                        "semantic_commit_receipts",
                    )
                }
            finally:
                connection.close()

        self.assertEqual(record.state, "proposed")
        self.assertIsNone(record.failure_code)
        self.assertIsNotNone(record.compiled_digest)
        self.assertEqual(observed, record)
        self.assertEqual(after_head, before_head)
        self.assertEqual(after_agent, before_agent)
        self.assertEqual(
            counts,
            {
                "semantic_nodes": 0,
                "semantic_relations": 0,
                "semantic_graph_revisions": 1,
                "semantic_commit_receipts": 0,
            },
        )

    def test_exact_duplicate_is_idempotent_but_conflicting_id_fails(self) -> None:
        with d_drive_tempdir() as temp:
            _, _, service = self._services(temp)
            proposal = proposal_for()
            first = service.propose_patch(
                proposal,
                created_at="2026-09-01T01:00:00+00:00",
            )
            second = service.propose_patch(
                proposal,
                created_at="2026-09-01T01:00:00+00:00",
            )

            changed_patch = goal_plan_patch(proposal.base_graph_digest)
            changed_goal = semantic_node(
                "goal:changed",
                SemanticNodeType.GOAL,
            )
            changed_patch = SemanticPatch(
                patch_id="patch:changed",
                base_graph_digest=proposal.base_graph_digest,
                add_nodes=(changed_goal,),
                add_relations=(),
                status_updates=(),
                supersession_refs=(),
                producer_ref="model:candidate-only",
            )
            conflict = SemanticPatchProposalRequest(
                proposal_id=proposal.proposal_id,
                graph_id=proposal.graph_id,
                agent_run_id=proposal.agent_run_id,
                base_graph_revision=proposal.base_graph_revision,
                base_graph_digest=proposal.base_graph_digest,
                registry_version=proposal.registry_version,
                registry_digest=proposal.registry_digest,
                patch=changed_patch,
            )
            with self.assertRaises(SemanticPatchConflictError):
                service.propose_patch(
                    conflict,
                    created_at="2026-09-01T01:00:00+00:00",
                )

        self.assertEqual(second, first)

    def test_invalid_semantic_proposal_records_bounded_failure_without_partial_write(self) -> None:
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
        patch = SemanticPatch(
            patch_id="patch:invalid-direction",
            base_graph_digest=empty_head().graph_digest,
            add_nodes=(goal, plan),
            add_relations=(reverse,),
            status_updates=(),
            supersession_refs=(),
            producer_ref="model:candidate-only",
        )
        proposal = proposal_for(patch)
        with d_drive_tempdir() as temp:
            agent_store, semantic_store, service = self._services(temp)
            before_head = semantic_store.get_graph_head(GRAPH_ID)
            before_agent = agent_store.get_agent_run(RUN_ID)

            record = service.propose_patch(
                proposal,
                created_at="2026-09-01T01:00:00+00:00",
            )

            after_head = semantic_store.get_graph_head(GRAPH_ID)
            after_agent = agent_store.get_agent_run(RUN_ID)

            connection = semantic_store.database.connect()
            try:
                nodes = connection.execute(
                    "SELECT COUNT(*) FROM semantic_nodes"
                ).fetchone()[0]
                relations = connection.execute(
                    "SELECT COUNT(*) FROM semantic_relations"
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(record.state, "validation_failed")
        self.assertEqual(
            record.failure_code,
            "SEMANTIC_RELATION_DIRECTION_INVALID",
        )
        self.assertEqual(after_head, before_head)
        self.assertEqual(after_agent, before_agent)
        self.assertEqual((nodes, relations), (0, 0))

    def test_service_has_no_raw_model_or_commit_authority_surface(self) -> None:
        parameters = inspect.signature(SemanticProposalService.propose_patch).parameters
        self.assertNotIn("raw_model_output", parameters)
        for forbidden in (
            "commit_patch",
            "force_commit",
            "authorize",
            "mark_verified",
            "resolve_reconciliation",
        ):
            self.assertFalse(hasattr(SemanticProposalService, forbidden), forbidden)


if __name__ == "__main__":
    unittest.main()
