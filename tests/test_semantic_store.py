from __future__ import annotations

import unittest

from macr_runtime.agent.database import AgentDatabase
from macr_runtime.agent.store import AgentStore
from macr_runtime.semantic.errors import (
    SemanticGraphAlreadyExistsError,
    SemanticGraphNotFoundError,
)
from macr_runtime.semantic.graph import SemanticGraphRevision
from macr_runtime.semantic.registry import SemanticRegistry
from macr_runtime.semantic.store import SemanticStore
from tests.support import d_drive_tempdir
from tests.test_agent_state import RUN_ID, make_header


GRAPH_A = "44444444-4444-4444-8444-444444444444"
GRAPH_B = "55555555-5555-4555-8555-555555555555"


class SemanticStoreTests(unittest.TestCase):
    def test_create_graph_writes_exact_empty_revision_and_head_atomically(self) -> None:
        registry = SemanticRegistry.from_builtin()
        with d_drive_tempdir() as temp:
            path = temp / "agent.sqlite3"
            AgentStore(path).create_agent_run(make_header())
            store = SemanticStore(AgentDatabase(path), registry=registry)

            head = store.create_graph(
                graph_id=GRAPH_A,
                scope_ref="project:phase-c",
                created_by_agent_run_id=RUN_ID,
                created_at="2026-09-01T00:00:00+00:00",
            )
            loaded = store.get_graph_head(GRAPH_A)
            revision = store.get_graph_revision(GRAPH_A, 1)

        self.assertEqual(loaded, head)
        self.assertEqual(revision, SemanticGraphRevision.from_initial_head(head))
        self.assertEqual(head.graph_revision, 1)
        self.assertEqual(head.active_node_record_digests, ())
        self.assertEqual(head.active_relation_digests, ())
        self.assertEqual(head.registry_digest, registry.registry_digest)

    def test_duplicate_graph_id_fails_without_second_revision(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "agent.sqlite3"
            AgentStore(path).create_agent_run(make_header())
            store = SemanticStore(AgentDatabase(path))
            store.create_graph(
                graph_id=GRAPH_A,
                scope_ref="project:phase-c",
                created_by_agent_run_id=RUN_ID,
                created_at="2026-09-01T00:00:00+00:00",
            )

            with self.assertRaises(SemanticGraphAlreadyExistsError):
                store.create_graph(
                    graph_id=GRAPH_A,
                    scope_ref="project:other",
                    created_by_agent_run_id=RUN_ID,
                    created_at="2026-09-01T00:00:00+00:00",
                )
            connection = store.database.connect()
            try:
                count = connection.execute(
                    "SELECT COUNT(*) FROM semantic_graph_revisions "
                    "WHERE graph_id = ?",
                    (GRAPH_A,),
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(count, 1)

    def test_graph_identity_and_equal_empty_digest_remain_distinct(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "agent.sqlite3"
            AgentStore(path).create_agent_run(make_header())
            store = SemanticStore(AgentDatabase(path))
            first = store.create_graph(
                graph_id=GRAPH_A,
                scope_ref="project:phase-c",
                created_by_agent_run_id=RUN_ID,
                created_at="2026-09-01T00:00:00+00:00",
            )
            second = store.create_graph(
                graph_id=GRAPH_B,
                scope_ref="project:phase-c",
                created_by_agent_run_id=RUN_ID,
                created_at="2026-09-01T00:00:00+00:00",
            )

        self.assertNotEqual(first.graph_id, second.graph_id)
        self.assertEqual(first.graph_digest, second.graph_digest)

    def test_graph_reads_are_bounded_deterministic_and_missing_is_typed(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "agent.sqlite3"
            AgentStore(path).create_agent_run(make_header())
            store = SemanticStore(AgentDatabase(path))
            first = store.create_graph(
                graph_id=GRAPH_A,
                scope_ref="project:phase-c",
                created_by_agent_run_id=RUN_ID,
                created_at="2026-09-01T00:00:00+00:00",
            )
            second = store.create_graph(
                graph_id=GRAPH_B,
                scope_ref="project:phase-c",
                created_by_agent_run_id=RUN_ID,
                created_at="2026-09-01T00:00:00+00:00",
            )

            self.assertEqual(store.list_graphs(limit=1), (first,))
            self.assertEqual(
                store.list_graphs(limit=1, after_graph_id=GRAPH_A),
                (second,),
            )
            with self.assertRaises(SemanticGraphNotFoundError):
                store.get_graph_head("66666666-6666-4666-8666-666666666666")

    def test_local_path_scope_rejects_before_graph_write_and_database_is_content_free(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "agent.sqlite3"
            AgentStore(path).create_agent_run(make_header())
            store = SemanticStore(AgentDatabase(path))
            with self.assertRaisesRegex(ValueError, "path"):
                store.create_graph(
                    graph_id=GRAPH_A,
                    scope_ref=r"D:\private\project",
                    created_by_agent_run_id=RUN_ID,
                    created_at="2026-09-01T00:00:00+00:00",
                )
            connection = store.database.connect()
            try:
                count = connection.execute(
                    "SELECT COUNT(*) FROM semantic_graphs"
                ).fetchone()[0]
                dump = "\n".join(connection.iterdump())
            finally:
                connection.close()

        self.assertEqual(count, 0)
        for forbidden in ("prompt", "answer", "api_key", r"D:\private"):
            self.assertNotIn(forbidden, dump)


if __name__ == "__main__":
    unittest.main()
