from __future__ import annotations

import sqlite3
import unittest
import uuid
from unittest.mock import patch

from macr_runtime.errors import EventStoreConflict, StoragePolicyError
from macr_runtime.event_store import SqliteEventStore
from macr_runtime.runtime_db import RuntimeDatabase

from tests.support import d_drive_tempdir


RUN_ID = "11111111-1111-4111-8111-111111111111"
DISPATCH_ID = "22222222-2222-4222-8222-222222222222"
TERMINAL_ID = "33333333-3333-4333-8333-333333333333"


class SqliteEventStoreTests(unittest.TestCase):
    def test_wal_bootstrap_retries_transient_database_locks(self) -> None:
        original_connect = sqlite3.connect
        wal_attempts = 0

        class LockingConnection:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, statement, *args, **kwargs):
                nonlocal wal_attempts
                if statement == "PRAGMA journal_mode = WAL":
                    wal_attempts += 1
                    if wal_attempts < 3:
                        self.connection.close()
                        raise sqlite3.OperationalError("database is locked")
                return self.connection.execute(statement, *args, **kwargs)

            def __getattr__(self, name):
                return getattr(self.connection, name)

        def connect_with_transient_wal_lock(*args, **kwargs):
            return LockingConnection(original_connect(*args, **kwargs))

        with d_drive_tempdir() as temp, patch(
            "macr_runtime.runtime_db.sqlite3.connect",
            side_effect=connect_with_transient_wal_lock,
        ):
            database = RuntimeDatabase(temp / "dispatch.sqlite3")
            connection = database.connect()
            try:
                journal_mode = connection.execute(
                    "PRAGMA journal_mode"
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(wal_attempts, 3)
        self.assertEqual(journal_mode.lower(), "wal")

    def test_one_dispatch_and_one_terminal_per_run(self) -> None:
        with d_drive_tempdir() as temp:
            store = SqliteEventStore(temp / "dispatch.sqlite3")
            store.start_run(
                run_id=RUN_ID,
                dispatch_event_id=DISPATCH_ID,
                payload={"provider_id": "glm"},
            )
            store.finish_run(
                run_id=RUN_ID,
                terminal_event_id=TERMINAL_ID,
                state="candidate_failure",
                payload={"status": "candidate_failure"},
            )
            with self.assertRaisesRegex(EventStoreConflict, "terminal"):
                store.finish_run(
                    run_id=RUN_ID,
                    terminal_event_id=str(uuid.uuid4()),
                    state="candidate_success",
                    payload={"status": "candidate_success"},
                )
            run = store.read_run(RUN_ID)
            events = store.read_events(run_id=RUN_ID)

        self.assertEqual(run["dispatch_event_id"], DISPATCH_ID)
        self.assertEqual(run["terminal_event_id"], TERMINAL_ID)
        self.assertEqual(run["state"], "candidate_failure")
        self.assertEqual(
            [event["event_type"] for event in events],
            ["provider.dispatch_requested", "provider.candidate_completed"],
        )

    def test_event_payload_rejects_content_and_credentials_recursively(self) -> None:
        forbidden = (
            "prompt",
            "answer",
            "authorization",
            "api_key",
            "raw_response",
            "path",
            "source_path",
            "remote_body",
            "error_body",
            "localPath",
            "remoteBody",
            "remoteHTTPBody",
            "sourceURLPath",
            "artifactJSONContent",
        )
        with d_drive_tempdir() as temp:
            store = SqliteEventStore(temp / "dispatch.sqlite3")
            for key in forbidden:
                with self.subTest(key=key):
                    with self.assertRaisesRegex(
                        ValueError,
                        "forbidden payload key",
                    ):
                        store.append_standalone(
                            "runtime.test",
                            str(uuid.uuid4()),
                            {"nested": [{key: "PRIVATE"}]},
                        )

    def test_event_payload_rejects_path_values_hidden_under_aliases(self) -> None:
        path_values = (
            r"D:\SECRET\task.txt",
            r"D:SECRET\task.txt",
            r"\\private-host\share\task.txt",
            "//private-host/share/task.txt",
        )
        with d_drive_tempdir() as temp:
            store = SqliteEventStore(temp / "dispatch.sqlite3")
            for value in path_values:
                with self.subTest(value=value):
                    with self.assertRaisesRegex(ValueError, "path-like value"):
                        store.append_standalone(
                            "runtime.test",
                            str(uuid.uuid4()),
                            {"detail": value},
                        )
            accepted = store.append_standalone(
                "runtime.test",
                str(uuid.uuid4()),
                {
                    "endpoint": "https://api.example.invalid/v1",
                    "model": "hf.co/example/model",
                },
            )

        self.assertEqual(
            accepted["payload"],
            {
                "endpoint": "https://api.example.invalid/v1",
                "model": "hf.co/example/model",
            },
        )

    def test_operational_events_reject_unknown_payload_fields(self) -> None:
        with d_drive_tempdir() as temp:
            store = SqliteEventStore(temp / "dispatch.sqlite3")
            with self.assertRaisesRegex(ValueError, "not allowed"):
                store.start_run(
                    run_id=RUN_ID,
                    dispatch_event_id=DISPATCH_ID,
                    payload={
                        "provider_id": "glm",
                        "unreviewed_metric": 1,
                    },
                )
            self.assertIsNone(store.read_run(RUN_ID))

            store.start_run(
                run_id=RUN_ID,
                dispatch_event_id=DISPATCH_ID,
                payload={"provider_id": "glm"},
            )
            with self.assertRaisesRegex(ValueError, "not allowed"):
                store.finish_run(
                    run_id=RUN_ID,
                    terminal_event_id=TERMINAL_ID,
                    state="candidate_failure",
                    payload={
                        "status": "candidate_failure",
                        "unreviewed_metric": 1,
                    },
                )
            self.assertIsNone(store.read_run(RUN_ID)["terminal_event_id"])

    def test_operational_events_reject_invalid_field_types(self) -> None:
        with d_drive_tempdir() as temp:
            store = SqliteEventStore(temp / "dispatch.sqlite3")
            with self.assertRaisesRegex(ValueError, "provider_id must be"):
                store.start_run(
                    run_id=RUN_ID,
                    dispatch_event_id=DISPATCH_ID,
                    payload={
                        "provider_id": {
                            "nested": {"remoteHTTPBody": "PRIVATE"},
                        },
                    },
                )
            self.assertIsNone(store.read_run(RUN_ID))

            store.start_run(
                run_id=RUN_ID,
                dispatch_event_id=DISPATCH_ID,
                payload={"provider_id": "glm"},
            )
            invalid_terminal_values = (
                {
                    "status": "candidate_failure",
                    "failure_type": {
                        "artifactJSONContent": "PRIVATE",
                    },
                },
                {
                    "status": "candidate_failure",
                    "candidate_capture": "arbitrary scalar metadata",
                },
            )
            for payload in invalid_terminal_values:
                with self.subTest(payload=payload):
                    with self.assertRaisesRegex(ValueError, "must be"):
                        store.finish_run(
                            run_id=RUN_ID,
                            terminal_event_id=TERMINAL_ID,
                            state="candidate_failure",
                            payload=payload,
                        )
            self.assertIsNone(store.read_run(RUN_ID)["terminal_event_id"])

    def test_start_run_rolls_back_run_when_event_insert_fails(self) -> None:
        with d_drive_tempdir() as temp:
            store = SqliteEventStore(temp / "dispatch.sqlite3")
            with patch.object(
                store,
                "_insert_event",
                side_effect=RuntimeError("injected event failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "injected"):
                    store.start_run(
                        run_id=RUN_ID,
                        dispatch_event_id=DISPATCH_ID,
                        payload={"provider_id": "glm"},
                    )

            self.assertIsNone(store.read_run(RUN_ID))
            self.assertEqual(store.read_events(), ())

    def test_standalone_events_are_exact_and_filterable(self) -> None:
        with d_drive_tempdir() as temp:
            store = SqliteEventStore(temp / "dispatch.sqlite3")
            ids = [str(uuid.uuid4()) for _ in range(3)]
            for index, event_id in enumerate(ids):
                store.append_standalone(
                    "concurrency.probe",
                    event_id,
                    {"seq": index},
                )

            events = store.read_events(event_type="concurrency.probe")

        self.assertEqual(len(events), 3)
        self.assertEqual([event["event_id"] for event in events], ids)

    def test_imported_event_is_idempotent_but_conflicts_fail(self) -> None:
        event_id = "44444444-4444-4444-8444-444444444444"
        with d_drive_tempdir() as temp:
            store = SqliteEventStore(temp / "dispatch.sqlite3")
            first = store.append_imported(
                event_id=event_id,
                event_type="legacy.test",
                observed_at="2026-08-27T00:00:00+00:00",
                payload={"task_id": "legacy-one"},
                source_sha256="a" * 64,
                source_line=1,
            )
            second = store.append_imported(
                event_id=event_id,
                event_type="legacy.test",
                observed_at="2026-08-27T00:00:00+00:00",
                payload={"task_id": "legacy-one"},
                source_sha256="a" * 64,
                source_line=1,
            )
            with self.assertRaisesRegex(EventStoreConflict, "event_id"):
                store.append_imported(
                    event_id=event_id,
                    event_type="legacy.test",
                    observed_at="2026-08-27T00:00:00+00:00",
                    payload={"task_id": "changed"},
                    source_sha256="a" * 64,
                    source_line=1,
                )

        self.assertTrue(first)
        self.assertFalse(second)

    def test_database_path_must_be_absolute_on_d(self) -> None:
        with self.assertRaisesRegex(StoragePolicyError, "absolute on D"):
            SqliteEventStore(r"C:\temp\dispatch.sqlite3")


if __name__ == "__main__":
    unittest.main()
