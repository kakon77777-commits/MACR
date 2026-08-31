from __future__ import annotations

import dataclasses
import multiprocessing
import unittest

from macr_runtime.agent.database import AgentDatabase
from macr_runtime.semantic.store import SemanticStore
from tests.helpers.semantic_commit_worker import commit_contender
from tests.support import d_drive_tempdir
from tests.test_agent_state import RUN_ID
from tests.test_semantic_commit import active_world, attach
from tests.test_semantic_patch_validation import GRAPH_ID


class SemanticMultiprocessTests(unittest.TestCase):
    def test_eight_exact_base_commits_produce_one_revision_and_seven_no_drift_refusals(self) -> None:
        context = multiprocessing.get_context("spawn")
        with d_drive_tempdir() as temp:
            agent, semantic, header, permit, head, _, clock = active_world(temp)
            from macr_runtime.semantic.commit import SemanticCommitService

            attach(
                SemanticCommitService(agent.store, semantic, now=clock),
                agent,
                header,
                permit,
                head,
            )
            start_event = context.Event()
            results = context.Queue()
            processes = []
            for index in range(8):
                token = f"{index + 1:08x}"
                processes.append(
                    context.Process(
                        target=commit_contender,
                        args=(
                            str(agent.store.database.path),
                            dataclasses.asdict(permit),
                            f"{token}-0000-4000-8000-000000000001",
                            f"{token}-0000-4000-8000-000000000002",
                            f"{token}-0000-4000-8000-000000000003",
                            start_event,
                            results,
                        ),
                    )
                )
            for process in processes:
                process.start()
            start_event.set()
            observations = [results.get(timeout=60) for _ in processes]
            for process in processes:
                process.join(timeout=60)
                self.assertEqual(process.exitcode, 0)
            results.close()

            graph = SemanticStore(AgentDatabase(agent.store.database.path)).get_graph_head(
                GRAPH_ID
            )
            agent_projection = agent.get_agent_run(RUN_ID)
            connection = semantic.database.connect()
            try:
                counts = tuple(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in (
                        "semantic_graph_revisions",
                        "semantic_events",
                        "semantic_commit_receipts",
                    )
                )
            finally:
                connection.close()

        self.assertEqual([item[0] for item in observations].count("committed"), 1)
        self.assertEqual([item[0] for item in observations].count("refused"), 7)
        self.assertEqual(graph.graph_revision, 2)
        self.assertEqual(agent_projection.state_revision, 6)
        self.assertEqual(counts, (2, 1, 1))


if __name__ == "__main__":
    unittest.main()
