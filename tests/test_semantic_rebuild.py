from __future__ import annotations

import unittest

from macr_runtime.agent.database import AgentDatabase
from macr_runtime.semantic.commit import SemanticCommitRequest, SemanticCommitService, ownership_permit_digest
from macr_runtime.semantic.errors import SemanticGraphDigestMismatchError, SemanticPatchConflictError
from macr_runtime.semantic.store import SemanticStore
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


class SemanticRebuildTests(unittest.TestCase):
    def test_agent_and_graph_heads_rebuild_to_same_committed_binding(self) -> None:
        with d_drive_tempdir() as temp:
            agent, semantic, header, permit, head, proposal, clock = active_world(temp)
            commits = SemanticCommitService(agent.store, semantic, now=clock)
            attach(commits, agent, header, permit, head)
            request = SemanticCommitRequest.from_proposal(
                commit_id=COMMIT_ID,
                proposal=proposal.proposal,
                expected_agent_revision=5,
                expected_agent_epoch=1,
                ownership_permit_digest=ownership_permit_digest(permit),
                authorization_reference=header.authority.reference,
            )
            receipt = commits.commit_patch(
                request,
                permit=permit,
                semantic_event_id=SEMANTIC_EVENT_ID,
                agent_event_id=COMMIT_AGENT_EVENT_ID,
            )
            expected_head = semantic.get_graph_head(GRAPH_ID)
            expected_binding = agent.store.get_agent_semantic_binding(RUN_ID)
            expected_events = agent.list_agent_events(RUN_ID)
            agent.release_agent_run(permit)
            connection = semantic.database.connect()
            try:
                connection.execute(
                    "DELETE FROM semantic_graph_heads WHERE graph_id = ?",
                    (GRAPH_ID,),
                )
                connection.execute(
                    "DELETE FROM agent_runs WHERE agent_run_id = ?",
                    (RUN_ID,),
                )
            finally:
                connection.close()

            rebuilt_head = semantic.rebuild_graph_head(GRAPH_ID)
            rebuilt_agent = agent.store.rebuild_projection(
                RUN_ID,
                observed_at="2026-09-01T02:00:00+00:00",
            )
            rebuilt_binding = agent.store.get_agent_semantic_binding(RUN_ID)
            rebuilt_events = agent.list_agent_events(RUN_ID)

        self.assertEqual(rebuilt_head, expected_head)
        self.assertEqual(rebuilt_binding, expected_binding)
        self.assertEqual(rebuilt_events, expected_events)
        self.assertEqual(rebuilt_agent.state_revision, receipt.agent_state_revision)

    def test_missing_or_tampered_revision_membership_is_detected(self) -> None:
        for mutation in ("missing", "tampered"):
            with self.subTest(mutation=mutation), d_drive_tempdir() as temp:
                agent, semantic, header, permit, head, proposal, clock = active_world(temp)
                commits = SemanticCommitService(agent.store, semantic, now=clock)
                attach(commits, agent, header, permit, head)
                request = SemanticCommitRequest.from_proposal(
                    commit_id=COMMIT_ID,
                    proposal=proposal.proposal,
                    expected_agent_revision=5,
                    expected_agent_epoch=1,
                    ownership_permit_digest=ownership_permit_digest(permit),
                    authorization_reference=header.authority.reference,
                )
                commits.commit_patch(
                    request,
                    permit=permit,
                    semantic_event_id=SEMANTIC_EVENT_ID,
                    agent_event_id=COMMIT_AGENT_EVENT_ID,
                )
                connection = semantic.database.connect()
                try:
                    if mutation == "missing":
                        connection.execute(
                            "DELETE FROM semantic_graph_revision_nodes "
                            "WHERE rowid = (SELECT rowid FROM "
                            "semantic_graph_revision_nodes WHERE graph_id = ? "
                            "AND graph_revision = 2 ORDER BY rowid LIMIT 1)",
                            (GRAPH_ID,),
                        )
                    else:
                        connection.execute(
                            "UPDATE semantic_graph_revision_nodes SET record_digest = ? "
                            "WHERE rowid = (SELECT rowid FROM "
                            "semantic_graph_revision_nodes WHERE graph_id = ? "
                            "AND graph_revision = 2 ORDER BY rowid LIMIT 1)",
                            ("f" * 64, GRAPH_ID),
                        )
                finally:
                    connection.close()

                with self.assertRaises(SemanticGraphDigestMismatchError):
                    semantic.get_graph_revision(GRAPH_ID, 2)

    def test_rebuild_rejects_corrupt_membership_without_creating_head(self) -> None:
        mutations = (
            ("node_missing", "DELETE", "semantic_graph_revision_nodes", None),
            ("node_tampered", "UPDATE", "semantic_graph_revision_nodes", "record_digest"),
            (
                "relation_missing",
                "DELETE",
                "semantic_graph_revision_relations",
                None,
            ),
            (
                "relation_tampered",
                "UPDATE",
                "semantic_graph_revision_relations",
                "relation_digest",
            ),
        )
        observed_tables = (
            "semantic_graph_heads",
            "semantic_graph_revisions",
            "semantic_graph_revision_nodes",
            "semantic_graph_revision_relations",
            "semantic_nodes",
            "semantic_relations",
            "semantic_events",
            "semantic_attach_receipts",
            "semantic_commit_receipts",
        )
        for name, operation, table, digest_column in mutations:
            with self.subTest(mutation=name), d_drive_tempdir() as temp:
                agent, semantic, header, permit, head, proposal, clock = active_world(temp)
                commits = SemanticCommitService(agent.store, semantic, now=clock)
                attach(commits, agent, header, permit, head)
                request = SemanticCommitRequest.from_proposal(
                    commit_id=COMMIT_ID,
                    proposal=proposal.proposal,
                    expected_agent_revision=5,
                    expected_agent_epoch=1,
                    ownership_permit_digest=ownership_permit_digest(permit),
                    authorization_reference=header.authority.reference,
                )
                commits.commit_patch(
                    request,
                    permit=permit,
                    semantic_event_id=SEMANTIC_EVENT_ID,
                    agent_event_id=COMMIT_AGENT_EVENT_ID,
                )
                connection = semantic.database.connect()
                try:
                    connection.execute(
                        "DELETE FROM semantic_graph_heads WHERE graph_id = ?",
                        (GRAPH_ID,),
                    )
                    if operation == "DELETE":
                        connection.execute(
                            f"DELETE FROM {table} WHERE rowid = (SELECT rowid "
                            f"FROM {table} WHERE graph_id = ? AND graph_revision = 2 "
                            "ORDER BY rowid LIMIT 1)",
                            (GRAPH_ID,),
                        )
                    else:
                        connection.execute(
                            f"UPDATE {table} SET {digest_column} = ? WHERE rowid = "
                            f"(SELECT rowid FROM {table} WHERE graph_id = ? "
                            "AND graph_revision = 2 ORDER BY rowid LIMIT 1)",
                            ("f" * 64, GRAPH_ID),
                        )
                    before = tuple(
                        (
                            selected,
                            tuple(
                                tuple(row)
                                for row in connection.execute(
                                    f"SELECT * FROM {selected} ORDER BY rowid"
                                ).fetchall()
                            ),
                        )
                        for selected in observed_tables
                    )
                finally:
                    connection.close()

                with self.assertRaises(SemanticGraphDigestMismatchError):
                    semantic.rebuild_graph_head(GRAPH_ID)

                connection = semantic.database.connect()
                try:
                    after = tuple(
                        (
                            selected,
                            tuple(
                                tuple(row)
                                for row in connection.execute(
                                    f"SELECT * FROM {selected} ORDER BY rowid"
                                ).fetchall()
                            ),
                        )
                        for selected in observed_tables
                    )
                finally:
                    connection.close()

                self.assertEqual(after, before)
                self.assertEqual(dict(after)["semantic_graph_heads"], ())

    def test_tampered_commit_receipt_is_rejected_on_idempotent_readback(self) -> None:
        with d_drive_tempdir() as temp:
            agent, semantic, header, permit, head, proposal, clock = active_world(temp)
            commits = SemanticCommitService(agent.store, semantic, now=clock)
            attach(commits, agent, header, permit, head)
            request = SemanticCommitRequest.from_proposal(
                commit_id=COMMIT_ID,
                proposal=proposal.proposal,
                expected_agent_revision=5,
                expected_agent_epoch=1,
                ownership_permit_digest=ownership_permit_digest(permit),
                authorization_reference=header.authority.reference,
            )
            commits.commit_patch(
                request,
                permit=permit,
                semantic_event_id=SEMANTIC_EVENT_ID,
                agent_event_id=COMMIT_AGENT_EVENT_ID,
            )
            connection = semantic.database.connect()
            try:
                connection.execute(
                    "UPDATE semantic_commit_receipts SET receipt_json = '{}' "
                    "WHERE commit_id = ?",
                    (COMMIT_ID,),
                )
            finally:
                connection.close()

            with self.assertRaises(SemanticPatchConflictError):
                commits.commit_patch(
                    request,
                    permit=permit,
                    semantic_event_id=SEMANTIC_EVENT_ID,
                    agent_event_id=COMMIT_AGENT_EVENT_ID,
                )


if __name__ == "__main__":
    unittest.main()
