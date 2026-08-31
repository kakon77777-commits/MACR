from __future__ import annotations

import unittest

from macr_runtime.semantic.projection import SemanticContextProjector
from tests.support import d_drive_tempdir
from tests.test_semantic_projection import committed_world, context_request


def run_goal_to_plan_subject():
    with d_drive_tempdir() as temp:
        agent, semantic, head, receipt = committed_world(temp)
        projection = SemanticContextProjector(agent.store, semantic).project(
            context_request(head)
        )
        direct_database_exists = (temp / "direct.sqlite3").exists()
        database_names = tuple(sorted(item.name for item in temp.glob("*.sqlite3")))
        return (
            projection.canonical_bytes(),
            projection.projection_digest,
            projection.graph_revision,
            receipt.agent_state_revision,
            database_names,
            direct_database_exists,
        )


class SemanticGoalToPlanIntegrationTests(unittest.TestCase):
    def test_two_fresh_offline_worlds_reproduce_goal_to_plan_without_direct_db(self) -> None:
        first = run_goal_to_plan_subject()
        second = run_goal_to_plan_subject()

        self.assertEqual(second, first)
        self.assertEqual(first[2], 2)
        self.assertEqual(first[3], 6)
        self.assertEqual(first[4], ("agent.sqlite3",))
        self.assertFalse(first[5])


if __name__ == "__main__":
    unittest.main()
