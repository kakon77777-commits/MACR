from __future__ import annotations

import unittest

from macr_runtime.semantic.commit import (
    SemanticCommitService,
    ownership_permit_digest,
)
from macr_runtime.semantic.patch import SemanticCommitRequest
from tests.support import d_drive_tempdir
from tests.test_agent_state import RUN_ID
from tests.test_semantic_commit import (
    COMMIT_AGENT_EVENT_ID,
    COMMIT_ID,
    SEMANTIC_EVENT_ID,
    active_world,
    attach,
)
from tests.test_semantic_patch_validation import GRAPH_ID


def snapshot(agent, semantic):
    connection = semantic.database.connect()
    try:
        counts = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "semantic_nodes",
                "semantic_relations",
                "semantic_graph_revisions",
                "semantic_graph_revision_nodes",
                "semantic_graph_revision_relations",
                "semantic_events",
                "semantic_commit_receipts",
            )
        )
        proposal = tuple(
            connection.execute(
                "SELECT state, terminal_at FROM semantic_patches"
            ).fetchone()
        )
    finally:
        connection.close()
    return (
        semantic.get_graph_head(GRAPH_ID),
        agent.get_agent_run(RUN_ID),
        agent.store.get_agent_semantic_binding(RUN_ID),
        agent.list_agent_events(RUN_ID),
        counts,
        proposal,
    )


class SemanticAtomicityTests(unittest.TestCase):
    def test_faults_between_semantic_and_agent_halves_roll_back_everything(self) -> None:
        markers = (
            "after_semantic_records",
            "after_graph_head",
            "after_agent_event",
            "after_agent_binding",
            "before_receipt",
            "before_commit",
        )
        for marker in markers:
            with self.subTest(marker=marker), d_drive_tempdir() as temp:
                agent, semantic, header, permit, head, proposal_record, clock = active_world(temp)
                normal = SemanticCommitService(agent.store, semantic, now=clock)
                attach(normal, agent, header, permit, head)
                before = snapshot(agent, semantic)

                def fail_at(observed: str) -> None:
                    if observed == marker:
                        raise RuntimeError(f"injected:{marker}")

                service = SemanticCommitService(
                    agent.store,
                    semantic,
                    now=clock,
                    fault_injector=fail_at,
                )
                request = SemanticCommitRequest.from_proposal(
                    commit_id=COMMIT_ID,
                    proposal=proposal_record.proposal,
                    expected_agent_revision=5,
                    expected_agent_epoch=1,
                    ownership_permit_digest=ownership_permit_digest(permit),
                    authorization_reference=header.authority.reference,
                )
                with self.assertRaisesRegex(RuntimeError, f"injected:{marker}"):
                    service.commit_patch(
                        request,
                        permit=permit,
                        semantic_event_id=SEMANTIC_EVENT_ID,
                        agent_event_id=COMMIT_AGENT_EVENT_ID,
                    )

                after = snapshot(agent, semantic)
                self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
