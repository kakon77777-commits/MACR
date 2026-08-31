from __future__ import annotations

import dataclasses
import json
import unittest

from macr_runtime.agent.contracts import (
    AgentRunHeader,
    AgentRunIdentity,
    AgentRunState,
    MemoryBindingRef,
    PlanBinding,
    SemanticStateBinding,
    WorldBindingRef,
    agent_run_subject_digest,
)
from macr_runtime.agent.errors import (
    AgentProjectionConflictError,
    AgentRunAlreadyExistsError,
)
from macr_runtime.agent.events import AgentEventType
from macr_runtime.agent.store import AgentStore
from tests.support import d_drive_tempdir
from tests.test_agent_state import RUN_ID, make_header


RUN_TWO = "22222222-2222-4222-8222-222222222222"


def with_run_id(header: AgentRunHeader, run_id: str) -> AgentRunHeader:
    return dataclasses.replace(
        header,
        identity=AgentRunIdentity(run_id, header.identity.subject_digest),
    )


def rich_header() -> AgentRunHeader:
    base = make_header()
    world_a = WorldBindingRef("world:a", "d" * 64, 1)
    world_b = WorldBindingRef("world:b", "e" * 64, 2)
    memory = MemoryBindingRef(
        memory_system_id="mneme",
        profile_id="MLF-RM/0.1",
        subject_ref="agent:phase-b",
        head_ref="memory-head:1",
        head_digest="f" * 64,
        access_policy_ref="policy:read-only",
        projection_policy_ref="projection:bounded",
    )
    semantic = SemanticStateBinding("semantic:phase-b", "1" * 64, 1)
    plan = PlanBinding("plan:phase-b", "2" * 64, 1)
    identity = AgentRunIdentity(
        RUN_ID,
        agent_run_subject_digest(
            agent_ref=base.agent_ref,
            origin=base.origin,
            goal=base.goal,
            authority=base.authority,
            budget=base.budget,
            world_bindings=(world_b, world_a),
            memory_bindings=(memory,),
        ),
    )
    return dataclasses.replace(
        base,
        identity=identity,
        semantic_state=semantic,
        active_plan=plan,
        world_bindings=(world_b, world_a),
        memory_bindings=(memory,),
    )


def mutation_counts(store: AgentStore) -> dict[str, int]:
    connection = store.database.connect()
    try:
        names = (
            "agent_runs",
            "agent_events",
            "agent_goals",
            "agent_world_bindings",
            "agent_memory_bindings",
            "agent_plan_bindings",
            "agent_children",
            "agent_ownership",
        )
        counts = {
            name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in names
        }
        counts["fencing_value"] = connection.execute(
            "SELECT value FROM agent_fencing_counter WHERE singleton = 1"
        ).fetchone()[0]
        return counts
    finally:
        connection.close()


class AgentStoreTests(unittest.TestCase):
    def test_create_writes_one_event_projection_and_exact_binding_indexes(self) -> None:
        header = rich_header()
        with d_drive_tempdir() as temp:
            store = AgentStore(temp / "agent.sqlite3")

            projection = store.create_agent_run(
                header,
                event_id="33333333-3333-4333-8333-333333333333",
            )
            loaded = store.get_agent_run(RUN_ID)
            events = store.list_agent_events(RUN_ID)
            connection = store.database.connect()
            try:
                counts = {
                    table: connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                    for table in (
                        "agent_goals",
                        "agent_world_bindings",
                        "agent_memory_bindings",
                        "agent_plan_bindings",
                    )
                }
            finally:
                connection.close()

        self.assertEqual(loaded, projection)
        self.assertEqual(projection.initial_header, header)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].sequence, 1)
        self.assertEqual(events[0].event.event_type, AgentEventType.RUN_CREATED)
        self.assertEqual(events[0].event.before_revision, 0)
        self.assertEqual(events[0].event.after_revision, 1)
        self.assertEqual(
            counts,
            {
                "agent_goals": 1,
                "agent_world_bindings": 2,
                "agent_memory_bindings": 1,
                "agent_plan_bindings": 1,
            },
        )

    def test_creation_guard_mismatches_have_no_database_mutation_delta(self) -> None:
        invalid = (
            make_header(state=AgentRunState.ACTIVE),
            make_header(state_revision=2),
            make_header(epoch=1),
        )
        with d_drive_tempdir() as temp:
            store = AgentStore(temp / "agent.sqlite3")
            baseline = mutation_counts(store)

            for header in invalid:
                with self.subTest(
                    state=header.state.value,
                    revision=header.state_revision,
                    epoch=header.epoch,
                ):
                    with self.assertRaisesRegex(
                        ValueError,
                        "CREATED/revision 1/epoch 0",
                    ):
                        store.create_agent_run(header)
                    self.assertEqual(mutation_counts(store), baseline)

        self.assertEqual(
            baseline,
            {
                "agent_runs": 0,
                "agent_events": 0,
                "agent_goals": 0,
                "agent_world_bindings": 0,
                "agent_memory_bindings": 0,
                "agent_plan_bindings": 0,
                "agent_children": 0,
                "agent_ownership": 0,
                "fencing_value": 0,
            },
        )

    def test_duplicate_run_id_rejects_without_second_event(self) -> None:
        with d_drive_tempdir() as temp:
            store = AgentStore(temp / "agent.sqlite3")
            store.create_agent_run(make_header())

            with self.assertRaisesRegex(AgentRunAlreadyExistsError, "already exists"):
                store.create_agent_run(make_header())

            self.assertEqual(mutation_counts(store)["agent_runs"], 1)
            self.assertEqual(mutation_counts(store)["agent_events"], 1)

    def test_fault_markers_roll_back_event_projection_and_indexes(self) -> None:
        for marker in (
            "before_event_insert",
            "after_event_insert",
            "after_projection_update",
            "before_commit",
        ):
            with self.subTest(marker=marker), d_drive_tempdir() as temp:
                def fail_at(observed: str) -> None:
                    if observed == marker:
                        raise RuntimeError(f"injected:{marker}")

                store = AgentStore(temp / "agent.sqlite3", fault_injector=fail_at)
                with self.assertRaisesRegex(RuntimeError, f"injected:{marker}"):
                    store.create_agent_run(rich_header())

                self.assertEqual(
                    mutation_counts(store),
                    {
                        "agent_runs": 0,
                        "agent_events": 0,
                        "agent_goals": 0,
                        "agent_world_bindings": 0,
                        "agent_memory_bindings": 0,
                        "agent_plan_bindings": 0,
                        "agent_children": 0,
                        "agent_ownership": 0,
                        "fencing_value": 0,
                    },
                )

    def test_lists_are_bounded_deterministic_and_cursor_based(self) -> None:
        first_header = make_header()
        second_header = with_run_id(first_header, RUN_TWO)
        with d_drive_tempdir() as temp:
            store = AgentStore(temp / "agent.sqlite3")
            first = store.create_agent_run(first_header)
            second = store.create_agent_run(second_header)

            page_one = store.list_agent_runs(limit=1)
            page_two = store.list_agent_runs(limit=1, after_run_id=RUN_ID)
            only_created = store.list_agent_runs(state=AgentRunState.CREATED)

        self.assertEqual(page_one, (first,))
        self.assertEqual(page_two, (second,))
        self.assertEqual(only_created, (first, second))

    def test_projection_and_event_tail_disagreement_is_visible(self) -> None:
        with d_drive_tempdir() as temp:
            store = AgentStore(temp / "agent.sqlite3")
            store.create_agent_run(make_header())
            connection = store.database.connect()
            try:
                connection.execute(
                    "UPDATE agent_runs SET state_digest = ? WHERE agent_run_id = ?",
                    ("9" * 64, RUN_ID),
                )
            finally:
                connection.close()

            with self.assertRaisesRegex(
                AgentProjectionConflictError,
                "projection",
            ):
                store.get_agent_run(RUN_ID)

    def test_same_subject_can_create_a_distinct_occurrence(self) -> None:
        first_header = make_header()
        second_header = with_run_id(first_header, RUN_TWO)
        with d_drive_tempdir() as temp:
            store = AgentStore(temp / "agent.sqlite3")
            first = store.create_agent_run(first_header)
            second = store.create_agent_run(second_header)

        self.assertNotEqual(first.agent_run_id, second.agent_run_id)
        self.assertEqual(first.subject_digest, second.subject_digest)

    def test_public_rows_and_raw_database_remain_content_free(self) -> None:
        with d_drive_tempdir() as temp:
            store = AgentStore(temp / "agent.sqlite3")
            store.create_agent_run(rich_header())
            public = store.get_agent_run(RUN_ID).to_public_dict()
            connection = store.database.connect()
            try:
                dump = "\n".join(connection.iterdump())
            finally:
                connection.close()

        combined = json.dumps(public, sort_keys=True) + dump
        for forbidden in (
            "prompt",
            "answer",
            "api_key",
            "memory_content",
            "D:\\",
        ):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
