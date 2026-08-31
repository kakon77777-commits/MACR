from __future__ import annotations

import multiprocessing
import sqlite3
import unittest
from pathlib import Path

from macr_runtime.agent.contracts import SemanticStateBinding
from macr_runtime.agent.database import AgentDatabase
from macr_runtime.agent.errors import AgentProjectionConflictError
from macr_runtime.agent.events import AgentEventType, AgentStateEvent
from macr_runtime.agent.state import AgentRunProjection
from macr_runtime.canonical import canonical_json_bytes
from macr_runtime.errors import StoragePolicyError
from tests.support import d_drive_tempdir
from tests.test_agent_state import RUN_ID, make_header


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
            self.assertEqual(version, 2)
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
                    "UPDATE schema_meta SET version = 3 "
                    "WHERE component = 'agent_runtime'"
                )
            finally:
                connection.close()

            with self.assertRaisesRegex(
                AgentProjectionConflictError,
                "schema version is unsupported",
            ):
                AgentDatabase(path)

    def test_schema_one_migrates_to_two_without_rewriting_event_evidence(self) -> None:
        binding = SemanticStateBinding(
            "semantic-graph:44444444-4444-4444-8444-444444444444",
            "d" * 64,
            1,
        )
        header = make_header(semantic_state=binding)
        projection = AgentRunProjection.from_creation_header(header)
        event = AgentStateEvent(
            event_id="77777777-7777-4777-8777-777777777777",
            agent_run_id=RUN_ID,
            epoch=0,
            before_revision=0,
            after_revision=1,
            event_type=AgentEventType.RUN_CREATED,
            payload={"initial_header": header.to_public_dict()},
            state_digest_after=projection.state_digest,
            created_at=header.created_at,
        )
        fixture = (
            Path(__file__).parent / "fixtures/agent-runtime-v1.sql"
        ).read_text(encoding="utf-8")

        with d_drive_tempdir() as temp:
            path = temp / "agent.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.executescript(fixture)
                connection.execute(
                    """
                    INSERT INTO agent_runs(
                        agent_run_id, subject_digest, agent_ref,
                        initial_header_json, state, state_revision, epoch,
                        goal_ref, authority_ref, budget_ref, semantic_state_ref,
                        active_plan_ref, latest_checkpoint_ref,
                        parent_agent_run_id, delegation_ref, state_digest,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        RUN_ID,
                        projection.subject_digest,
                        header.agent_ref,
                        canonical_json_bytes(header.to_public_dict()).decode("utf-8"),
                        projection.state.value,
                        projection.state_revision,
                        projection.epoch,
                        header.goal.ref,
                        header.authority.reference.source_id,
                        header.budget.ref,
                        binding.ref,
                        None,
                        None,
                        None,
                        None,
                        projection.state_digest,
                        header.created_at,
                        projection.updated_at,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO agent_events(
                        event_id, agent_run_id, epoch, before_revision,
                        after_revision, event_type, payload_json, payload_digest,
                        state_digest_after, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.agent_run_id,
                        event.epoch,
                        event.before_revision,
                        event.after_revision,
                        event.event_type.value,
                        canonical_json_bytes(
                            event.to_public_dict()["payload"]
                        ).decode("utf-8"),
                        event.payload_digest,
                        event.state_digest_after,
                        event.created_at,
                    ),
                )
                connection.commit()
                before = tuple(
                    connection.execute(
                        "SELECT * FROM agent_events ORDER BY sequence"
                    ).fetchone()
                )
            finally:
                connection.close()

            migrated = AgentDatabase(path)
            connection = migrated.connect()
            try:
                version = connection.execute(
                    "SELECT version FROM schema_meta "
                    "WHERE component = 'agent_runtime'"
                ).fetchone()[0]
                semantic = tuple(
                    connection.execute(
                        "SELECT semantic_state_ref, semantic_state_digest, "
                        "semantic_state_revision FROM agent_runs "
                        "WHERE agent_run_id = ?",
                        (RUN_ID,),
                    ).fetchone()
                )
                after = tuple(
                    connection.execute(
                        "SELECT * FROM agent_events ORDER BY sequence"
                    ).fetchone()
                )
            finally:
                connection.close()

        self.assertEqual(version, 2)
        self.assertEqual(semantic, (binding.ref, binding.digest, binding.revision))
        self.assertEqual(after, before)

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

        self.assertEqual(observations, [("ok", 2)] * 32)
        self.assertEqual([tuple(row) for row in version_rows], [("agent_runtime", 2)])


if __name__ == "__main__":
    unittest.main()
