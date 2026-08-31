from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timezone

from macr_runtime.agent.database import AgentDatabase
from macr_runtime.agent.service import AgentStateService
from macr_runtime.agent.store import AgentStore
from macr_runtime.semantic.commit import SemanticCommitService, ownership_permit_digest
from macr_runtime.semantic.errors import SemanticGraphHeadStaleError
from macr_runtime.semantic.patch import SemanticCommitRequest, SemanticPatchProposalRequest
from macr_runtime.semantic.service import SemanticProposalService
from macr_runtime.semantic.store import SemanticStore
from tests.support import d_drive_tempdir
from tests.test_agent_service import Clock
from tests.test_agent_state import RUN_ID, make_header
from tests.test_agent_store import RUN_TWO, with_run_id
from tests.test_semantic_commit import (
    ATTACH_EVENT_ID,
    ATTACH_OPERATION_ID,
    COMMIT_AGENT_EVENT_ID,
    COMMIT_ID,
    SEMANTIC_EVENT_ID,
)
from tests.test_semantic_patch_validation import GRAPH_ID, goal_plan_patch


def activate(agent: AgentStateService, header, owner: str):
    run_id = header.identity.agent_run_id
    agent.create_agent_run(header)
    agent.admit_agent_run(
        run_id,
        expected_revision=1,
        expected_epoch=0,
        reason_code="INITIAL_ADMISSION",
        reason_digest="a" * 64,
    )
    permit = agent.acquire_agent_run(
        run_id,
        owner,
        expected_revision=2,
        expected_epoch=0,
        ttl_seconds=300,
    )
    agent.activate_agent_run(
        permit,
        expected_revision=3,
        expected_epoch=1,
        reason_code="SEMANTIC_READY",
        reason_digest="b" * 64,
    )
    return permit


class SemanticSharedGraphTests(unittest.TestCase):
    def test_one_run_advances_shared_head_while_other_remains_pinned_and_stale(self) -> None:
        clock = Clock(datetime(2026, 9, 1, 1, 0, tzinfo=timezone.utc))
        with d_drive_tempdir() as temp:
            path = temp / "agent.sqlite3"
            store = AgentStore(path)
            agent = AgentStateService(store, now=clock)
            first_header = make_header()
            second_header = with_run_id(make_header(), RUN_TWO)
            first_permit = activate(agent, first_header, "owner:first")
            second_permit = activate(agent, second_header, "owner:second")
            semantic = SemanticStore(AgentDatabase(path))
            head = semantic.create_graph(
                graph_id=GRAPH_ID,
                scope_ref="project:phase-c",
                created_by_agent_run_id=RUN_ID,
                created_at="2026-09-01T01:00:00+00:00",
            )
            commits = SemanticCommitService(store, semantic, now=clock)
            first_attached = commits.attach_graph(
                agent_run_id=RUN_ID,
                graph_id=GRAPH_ID,
                graph_revision=1,
                graph_digest=head.graph_digest,
                expected_agent_revision=4,
                expected_agent_epoch=1,
                permit=first_permit,
                authorization_reference=first_header.authority.reference,
                operation_id=ATTACH_OPERATION_ID,
                agent_event_id=ATTACH_EVENT_ID,
            )
            commits.attach_graph(
                agent_run_id=RUN_TWO,
                graph_id=GRAPH_ID,
                graph_revision=1,
                graph_digest=head.graph_digest,
                expected_agent_revision=4,
                expected_agent_epoch=1,
                permit=second_permit,
                authorization_reference=second_header.authority.reference,
                operation_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
                agent_event_id="dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            )
            proposals = SemanticProposalService(semantic)
            first_proposal = SemanticPatchProposalRequest(
                proposal_id="33333333-3333-4333-8333-333333333333",
                graph_id=GRAPH_ID,
                agent_run_id=RUN_ID,
                base_graph_revision=1,
                base_graph_digest=head.graph_digest,
                registry_version=semantic.registry.registry_version,
                registry_digest=semantic.registry.registry_digest,
                patch=goal_plan_patch(head.graph_digest),
            )
            second_proposal = dataclasses.replace(
                first_proposal,
                proposal_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
                agent_run_id=RUN_TWO,
            )
            first_record = proposals.propose_patch(
                first_proposal,
                created_at="2026-09-01T01:00:00+00:00",
            )
            second_record = proposals.propose_patch(
                second_proposal,
                created_at="2026-09-01T01:00:00+00:00",
            )
            first_request = SemanticCommitRequest.from_proposal(
                commit_id=COMMIT_ID,
                proposal=first_record.proposal,
                expected_agent_revision=first_attached.agent_state_revision,
                expected_agent_epoch=1,
                ownership_permit_digest=ownership_permit_digest(first_permit),
                authorization_reference=first_header.authority.reference,
            )
            commits.commit_patch(
                first_request,
                permit=first_permit,
                semantic_event_id=SEMANTIC_EVENT_ID,
                agent_event_id=COMMIT_AGENT_EVENT_ID,
            )
            second_request = SemanticCommitRequest.from_proposal(
                commit_id="ffffffff-ffff-4fff-8fff-ffffffffffff",
                proposal=second_record.proposal,
                expected_agent_revision=5,
                expected_agent_epoch=1,
                ownership_permit_digest=ownership_permit_digest(second_permit),
                authorization_reference=second_header.authority.reference,
            )

            with self.assertRaises(SemanticGraphHeadStaleError):
                commits.commit_patch(
                    second_request,
                    permit=second_permit,
                    semantic_event_id="12121212-1212-4212-8212-121212121212",
                    agent_event_id="13131313-1313-4313-8313-131313131313",
                )

            graph = semantic.get_graph_head(GRAPH_ID)
            first_binding = store.get_agent_semantic_binding(RUN_ID)
            second_binding = store.get_agent_semantic_binding(RUN_TWO)

        self.assertEqual(graph.graph_revision, 2)
        self.assertEqual(first_binding.revision, 2)
        self.assertEqual(second_binding.revision, 1)
        self.assertEqual(second_binding.digest, head.graph_digest)


if __name__ == "__main__":
    unittest.main()
