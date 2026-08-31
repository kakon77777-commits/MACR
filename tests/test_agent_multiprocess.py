from __future__ import annotations

import dataclasses
import multiprocessing
import unittest
from datetime import datetime, timezone

from macr_runtime.agent.service import AgentStateService
from macr_runtime.agent.store import AgentStore
from tests.helpers.agent_state_worker import (
    hard_exit_after_event_insert,
    owner_contender,
    stale_activate,
)
from tests.support import d_drive_tempdir
from tests.test_agent_service import Clock
from tests.test_agent_state import RUN_ID, make_header
from tests.test_agent_store import mutation_counts


OBSERVED_AT = "2026-08-31T01:00:00+00:00"


def admitted_service(database_path) -> AgentStateService:
    service = AgentStateService(
        AgentStore(database_path),
        now=Clock(datetime.fromisoformat(OBSERVED_AT)),
    )
    service.create_agent_run(make_header())
    service.admit_agent_run(
        RUN_ID,
        expected_revision=1,
        expected_epoch=0,
        reason_code="INITIAL_ADMISSION",
        reason_digest="a" * 64,
    )
    return service


def run_contenders(
    context,
    database_path,
    *,
    expected_revision: int,
    expected_epoch: int,
) -> list[tuple]:
    start_event = context.Event()
    results = context.Queue()
    processes = [
        context.Process(
            target=owner_contender,
            args=(
                str(database_path),
                f"owner:{index}",
                expected_revision,
                expected_epoch,
                OBSERVED_AT,
                start_event,
                results,
            ),
        )
        for index in range(8)
    ]
    for process in processes:
        process.start()
    start_event.set()
    observations = [results.get(timeout=60) for _ in processes]
    for process in processes:
        process.join(timeout=60)
        if process.is_alive():
            process.terminate()
            process.join(timeout=15)
            raise AssertionError("Agent ownership contender did not terminate")
        if process.exitcode != 0:
            raise AssertionError(f"Agent ownership contender exited {process.exitcode}")
    results.close()
    return observations


class AgentMultiprocessTests(unittest.TestCase):
    def test_eight_processes_produce_exactly_one_owner_and_one_canonical_mutation(self) -> None:
        context = multiprocessing.get_context("spawn")
        with d_drive_tempdir() as temp:
            path = temp / "agent.sqlite3"
            service = admitted_service(path)

            observations = run_contenders(
                context,
                path,
                expected_revision=2,
                expected_epoch=0,
            )

            projection = service.get_agent_run(RUN_ID)
            events = service.list_agent_events(RUN_ID)
            ownership = service.get_agent_ownership(RUN_ID)
            connection = service.store.database.connect()
            try:
                counter = connection.execute(
                    "SELECT value FROM agent_fencing_counter WHERE singleton = 1"
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertEqual([item[0] for item in observations].count("acquired"), 1)
        self.assertEqual([item[0] for item in observations].count("refused"), 7)
        self.assertEqual(projection.state_revision, 3)
        self.assertEqual(projection.epoch, 1)
        self.assertEqual(len(events), 3)
        self.assertIsNotNone(ownership)
        self.assertEqual(counter, 1)

    def test_release_then_eight_process_reacquire_has_one_new_epoch_and_token(self) -> None:
        context = multiprocessing.get_context("spawn")
        with d_drive_tempdir() as temp:
            path = temp / "agent.sqlite3"
            service = admitted_service(path)
            first = service.acquire_agent_run(
                RUN_ID,
                "owner:first",
                expected_revision=2,
                expected_epoch=0,
                ttl_seconds=300,
            )
            service.release_agent_run(first)

            observations = run_contenders(
                context,
                path,
                expected_revision=3,
                expected_epoch=1,
            )

            projection = service.get_agent_run(RUN_ID)
            ownership = service.get_agent_ownership(RUN_ID)
            events = service.list_agent_events(RUN_ID)

        self.assertEqual([item[0] for item in observations].count("acquired"), 1)
        self.assertEqual(projection.state_revision, 4)
        self.assertEqual(projection.epoch, 2)
        self.assertGreater(ownership.fencing_token, first.fencing_token)
        self.assertEqual(len(events), 4)

    def test_stale_process_cannot_mutate_after_ownership_changes(self) -> None:
        context = multiprocessing.get_context("spawn")
        with d_drive_tempdir() as temp:
            path = temp / "agent.sqlite3"
            service = admitted_service(path)
            first = service.acquire_agent_run(
                RUN_ID,
                "owner:first",
                expected_revision=2,
                expected_epoch=0,
                ttl_seconds=300,
            )
            service.release_agent_run(first)
            second = service.acquire_agent_run(
                RUN_ID,
                "owner:second",
                expected_revision=3,
                expected_epoch=1,
                ttl_seconds=300,
            )
            before = service.get_agent_run(RUN_ID)
            before_events = service.list_agent_events(RUN_ID)

            start_event = context.Event()
            results = context.Queue()
            process = context.Process(
                target=stale_activate,
                args=(
                    str(path),
                    dataclasses.asdict(first),
                    before.state_revision,
                    before.epoch,
                    OBSERVED_AT,
                    start_event,
                    results,
                ),
            )
            process.start()
            start_event.set()
            observation = results.get(timeout=60)
            process.join(timeout=60)
            results.close()

            after = service.get_agent_run(RUN_ID)
            after_events = service.list_agent_events(RUN_ID)
            current_ownership = service.get_agent_ownership(RUN_ID)

        self.assertEqual(process.exitcode, 0)
        self.assertEqual(observation[0], "refused")
        self.assertEqual(observation[2], "STALE_AGENT_FENCING_TOKEN")
        self.assertEqual(after, before)
        self.assertEqual(after_events, before_events)
        self.assertEqual(current_ownership, second)

    def test_process_exit_after_event_insert_rolls_back_all_canonical_state(self) -> None:
        context = multiprocessing.get_context("spawn")
        with d_drive_tempdir() as temp:
            path = temp / "agent.sqlite3"
            process = context.Process(
                target=hard_exit_after_event_insert,
                args=(str(path),),
            )
            process.start()
            process.join(timeout=60)
            if process.is_alive():
                process.terminate()
                process.join(timeout=15)
                self.fail("hard-exit worker did not terminate")

            store = AgentStore(path)
            counts = mutation_counts(store)

        self.assertEqual(process.exitcode, 73)
        self.assertEqual(
            counts,
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


if __name__ == "__main__":
    unittest.main()
