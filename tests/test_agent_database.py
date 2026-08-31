from __future__ import annotations

import multiprocessing
import sqlite3
import unittest
from pathlib import Path

from macr_runtime.agent.database import AgentDatabase
from macr_runtime.agent.errors import AgentProjectionConflictError
from macr_runtime.errors import StoragePolicyError
from tests.support import d_drive_tempdir


EXPECTED_TABLES = {
    "schema_meta",
    "agent_runs",
    "agent_events",
    "agent_goals",
    "agent_world_bindings",
    "agent_memory_bindings",
    "agent_plan_bindings",
    "agent_children",
    "agent_ownership",
    "agent_fencing_counter",
}


def _bootstrap_worker(
    database_path: str,
    start_event,
    results,
) -> None:
    start_event.wait(timeout=30)
    try:
        database = AgentDatabase(database_path)
        connection = database.connect()
        try:
            version = connection.execute(
                "SELECT version FROM schema_meta WHERE component = 'agent_runtime'"
            ).fetchone()[0]
        finally:
            connection.close()
        results.put(("ok", version))
    except Exception as exc:  # pragma: no cover - parent reports exact failure
        results.put((type(exc).__name__, str(exc)))


class AgentDatabaseTests(unittest.TestCase):
    def test_database_path_must_be_absolute_on_d_before_creation(self) -> None:
        relative = Path("phase-b-agent.sqlite3")
        self.assertFalse(relative.exists())

        for candidate in (relative, Path(r"C:\macr-phase-b\agent.sqlite3")):
            with self.subTest(path=str(candidate)):
                with self.assertRaisesRegex(StoragePolicyError, "absolute on D:"):
                    AgentDatabase(candidate)

        self.assertFalse(relative.exists())

    def test_fresh_schema_is_exact_versioned_and_dedicated(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "runtime" / "agent.sqlite3"
            database = AgentDatabase(path)
            connection = database.connect()
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                    )
                }
                version = connection.execute(
                    "SELECT version FROM schema_meta "
                    "WHERE component = 'agent_runtime'"
                ).fetchone()[0]
                counter = connection.execute(
                    "SELECT value FROM agent_fencing_counter WHERE singleton = 1"
                ).fetchone()[0]
            finally:
                connection.close()

            self.assertEqual(tables, EXPECTED_TABLES)
            self.assertEqual(version, 1)
            self.assertEqual(counter, 0)
            self.assertTrue(path.is_file())
            self.assertFalse((temp / "runtime" / "dispatch.sqlite3").exists())
            self.assertFalse((temp / "direct" / "conversations.sqlite3").exists())
            self.assertFalse((temp / "accounting" / "accounting.sqlite3").exists())
            self.assertFalse((temp / "observatory" / "observatory.sqlite3").exists())

    def test_connection_policy_is_wal_full_foreign_keyed_and_bounded(self) -> None:
        with d_drive_tempdir() as temp:
            connection = AgentDatabase(temp / "agent.sqlite3").connect()
            try:
                journal = connection.execute("PRAGMA journal_mode").fetchone()[0]
                synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]
                foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
                busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(journal.lower(), "wal")
        self.assertEqual(synchronous, 2)
        self.assertEqual(foreign_keys, 1)
        self.assertEqual(busy_timeout, 30000)

    def test_sql_constraints_reject_revision_gap_and_invalid_state(self) -> None:
        with d_drive_tempdir() as temp:
            connection = AgentDatabase(temp / "agent.sqlite3").connect()
            try:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """
                        INSERT INTO agent_events(
                            event_id, agent_run_id, epoch, before_revision,
                            after_revision, event_type, payload_json,
                            payload_digest, state_digest_after, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "11111111-1111-4111-8111-111111111111",
                            "22222222-2222-4222-8222-222222222222",
                            0,
                            1,
                            3,
                            "agent.run_created",
                            "{}",
                            "a" * 64,
                            "b" * 64,
                            "2026-08-31T00:00:00+00:00",
                        ),
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """
                        INSERT INTO agent_runs(
                            agent_run_id, subject_digest, agent_ref,
                            initial_header_json, state, state_revision, epoch,
                            goal_ref, authority_ref, budget_ref,
                            state_digest, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "33333333-3333-4333-8333-333333333333",
                            "a" * 64,
                            "agent:test",
                            "{}",
                            "invented",
                            1,
                            0,
                            "goal:test",
                            "authority:test",
                            "budget:test",
                            "b" * 64,
                            "2026-08-31T00:00:00+00:00",
                            "2026-08-31T00:00:00+00:00",
                        ),
                    )
            finally:
                connection.close()

    def test_newer_or_invalid_schema_version_fails_closed(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "agent.sqlite3"
            database = AgentDatabase(path)
            connection = database.connect()
            try:
                connection.execute(
                    "UPDATE schema_meta SET version = 2 "
                    "WHERE component = 'agent_runtime'"
                )
            finally:
                connection.close()

            with self.assertRaisesRegex(
                AgentProjectionConflictError,
                "schema version is unsupported",
            ):
                AgentDatabase(path)

    def test_fresh_sqlite_bootstrap_is_safe_for_32_synchronized_processes(self) -> None:
        context = multiprocessing.get_context("spawn")
        with d_drive_tempdir() as temp:
            path = temp / "agent.sqlite3"
            start_event = context.Event()
            results = context.Queue()
            processes = [
                context.Process(
                    target=_bootstrap_worker,
                    args=(str(path), start_event, results),
                )
                for _ in range(32)
            ]
            for process in processes:
                process.start()
            start_event.set()
            observations = [results.get(timeout=60) for _ in processes]
            for process in processes:
                process.join(timeout=60)
                self.assertEqual(process.exitcode, 0)
            results.close()

            connection = AgentDatabase(path).connect()
            try:
                version_rows = connection.execute(
                    "SELECT component, version FROM schema_meta"
                ).fetchall()
            finally:
                connection.close()

        self.assertEqual(observations, [("ok", 1)] * 32)
        self.assertEqual([tuple(row) for row in version_rows], [("agent_runtime", 1)])


if __name__ == "__main__":
    unittest.main()
