from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

from macr_runtime.canonical import sha256_id
from macr_runtime.model_identity import (
    ExecutionRouteIdentity,
    IdentityStatus,
    ModelSubject,
)
from macr_runtime.observatory_db import (
    ObservatoryConflict,
    ObservatoryDatabase,
)

from tests.support import d_drive_tempdir


ROOT = Path(__file__).resolve().parents[1]
WRITER = ROOT / "tests" / "helpers" / "sqlite_observatory_writer.py"
OBSERVED_AT = "2026-08-29T08:00:00+08:00"
REQUEST = sha256_id("request_shape_v1", {"source": "fixture"})
PARAMS = sha256_id("parameter_profile_v1", {"temperature": 0})
POLICY = sha256_id("data_policy_v1", {"class": "public"})


def snapshot_meta() -> dict[str, object]:
    return {
        "source_id": "fixture_models",
        "observed_at": OBSERVED_AT,
        "request_shape_sha256": REQUEST,
        "normalized_bytes_sha256": None,
        "parser_version": "fixture-v1",
    }


def make_subject(snapshot_id: str) -> ModelSubject:
    return ModelSubject.create(
        "z-ai",
        "glm-5.3-flash",
        "2026-08-28",
        IdentityStatus.CLAIMED,
        snapshot_id,
    )


def make_route(subject: ModelSubject) -> ExecutionRouteIdentity:
    return ExecutionRouteIdentity.create(
        subject.subject_id,
        "z_ai_direct",
        "https://api.z.ai/api/paas/v4",
        "glm-5.3-flash",
        PARAMS,
        "worker-v1",
        POLICY,
    )


class ObservatoryDatabaseTests(unittest.TestCase):
    def test_schema_has_exact_current_tables_and_wal(self) -> None:
        expected = {
            "source_snapshots",
            "model_subjects",
            "execution_routes",
            "model_observations",
            "evidence_items",
            "qualification_decisions",
            "qualification_invalidations",
            "coordination_plans",
            "shadow_comparisons",
        }
        with d_drive_tempdir() as temp:
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            connection = store.connect()
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                journal = connection.execute("PRAGMA journal_mode").fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(tables, expected)
        self.assertEqual(version, 2)
        self.assertEqual(journal.lower(), "wal")

    def test_schema_one_upgrades_additively_to_shadow_plan_schema(self) -> None:
        with d_drive_tempdir() as temp:
            database = temp / "observatory.sqlite3"
            snapshots = temp / "snapshots"
            store = ObservatoryDatabase(database, snapshots)
            connection = store.connect()
            try:
                connection.execute("DROP TABLE shadow_comparisons")
                connection.execute("DROP TABLE coordination_plans")
                connection.execute("PRAGMA user_version = 1")
            finally:
                connection.close()
            upgraded = ObservatoryDatabase(database, snapshots)
            connection = upgraded.connect()
            try:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            finally:
                connection.close()

        self.assertEqual(version, 2)
        self.assertIn("coordination_plans", tables)
        self.assertIn("shadow_comparisons", tables)

    def test_snapshot_is_create_once_and_raw_payload_is_private(self) -> None:
        raw = b'{"data":["SECRET_RAW_BODY"]}'
        with d_drive_tempdir() as temp:
            database = temp / "observatory.sqlite3"
            snapshot_root = temp / "snapshots"
            store = ObservatoryDatabase(database, snapshot_root)
            first = store.append_snapshot(snapshot_meta(), raw_bytes=raw)
            second = store.append_snapshot(snapshot_meta(), raw_bytes=raw)
            conflicting = {**snapshot_meta(), "snapshot_id": first.snapshot_id}
            with self.assertRaisesRegex(ObservatoryConflict, "conflicts"):
                store.append_snapshot(conflicting, raw_bytes=b'{"data":[1]}')

            self.assertEqual(first, second)
            self.assertEqual(store.read_snapshot(first.snapshot_id), first)
            self.assertEqual(store.read_snapshot_bytes(first.snapshot_id), raw)
            self.assertEqual(
                (snapshot_root / first.raw_relative_name).read_bytes(),
                raw,
            )
            self.assertNotIn(b"SECRET_RAW_BODY", database.read_bytes())

    def test_tampered_snapshot_bytes_fail_readback(self) -> None:
        with d_drive_tempdir() as temp:
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            snapshot = store.append_snapshot(snapshot_meta(), raw_bytes=b"original")
            (store.snapshot_root / snapshot.raw_relative_name).write_bytes(b"changed")
            with self.assertRaisesRegex(ObservatoryConflict, "hash mismatch"):
                store.read_snapshot_bytes(snapshot.snapshot_id)

    def test_subject_route_observation_are_create_once_and_foreign_keyed(self) -> None:
        with d_drive_tempdir() as temp:
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            snapshot = store.append_snapshot(snapshot_meta(), raw_bytes=b"{}")
            subject = make_subject(snapshot.snapshot_id)
            route = make_route(subject)
            self.assertEqual(
                store.append_model_subject(subject),
                store.append_model_subject(subject),
            )
            self.assertEqual(
                store.append_execution_route(route),
                store.append_execution_route(route),
            )
            observation = store.append_observation(
                {
                    "subject_id": subject.subject_id,
                    "route_id": route.route_id,
                    "snapshot_id": snapshot.snapshot_id,
                    "kind": "capability_claim",
                    "observed_at": OBSERVED_AT,
                    "payload": {
                        "capability": "text_generation",
                        "source_value_sha256": "b" * 64,
                    },
                }
            )
            repeated = store.append_observation(
                {
                    "subject_id": subject.subject_id,
                    "route_id": route.route_id,
                    "snapshot_id": snapshot.snapshot_id,
                    "kind": "capability_claim",
                    "observed_at": OBSERVED_AT,
                    "payload": {
                        "source_value_sha256": "b" * 64,
                        "capability": "text_generation",
                    },
                }
            )
            other = ModelSubject.create(
                "x-ai",
                "grok-4.6",
                "2026-08-29",
                IdentityStatus.CLAIMED,
                snapshot.snapshot_id,
            )
            store.append_model_subject(other)
            with self.assertRaisesRegex(ObservatoryConflict, "route.*model subject"):
                store.append_observation(
                    {
                        "subject_id": other.subject_id,
                        "route_id": route.route_id,
                        "snapshot_id": snapshot.snapshot_id,
                        "kind": "invalid_binding",
                        "observed_at": OBSERVED_AT,
                        "payload": {"claim_digest": "f" * 64},
                    }
                )

        self.assertEqual(observation, repeated)
        self.assertEqual(observation.observed_at, "2026-08-29T00:00:00+00:00")

    def test_repeat_subject_preserves_original_first_seen_snapshot(self) -> None:
        with d_drive_tempdir() as temp:
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            first_snapshot = store.append_snapshot(
                snapshot_meta(),
                raw_bytes=b'{"version":1}',
            )
            later_meta = {
                **snapshot_meta(),
                "observed_at": "2026-08-30T00:00:00+00:00",
            }
            later_snapshot = store.append_snapshot(
                later_meta,
                raw_bytes=b'{"version":2}',
            )
            first_subject = make_subject(first_snapshot.snapshot_id)
            later_subject = make_subject(later_snapshot.snapshot_id)

            first_record = store.append_model_subject(first_subject)
            repeated_record = store.append_model_subject(later_subject)

        self.assertEqual(first_subject.subject_id, later_subject.subject_id)
        self.assertEqual(first_record, repeated_record)
        self.assertEqual(
            repeated_record.first_seen_snapshot_id,
            first_snapshot.snapshot_id,
        )

    def test_evidence_decisions_and_invalidations_are_immutable_records(self) -> None:
        qualification = "c" * 64
        with d_drive_tempdir() as temp:
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            evidence = store.append_evidence(
                {
                    "qualification_key": qualification,
                    "kind": "probe_verification",
                    "subject_digest": "d" * 64,
                    "observed_at": OBSERVED_AT,
                    "payload": {"passed": True, "test_count": 8},
                }
            )
            decision = store.append_qualification_decision(
                {
                    "qualification_key": qualification,
                    "state": "shadow_only",
                    "evidence_set_digest": "e" * 64,
                    "decided_at": OBSERVED_AT,
                    "payload": {"blind_spots": ["live_not_measured"]},
                }
            )
            invalidation = store.append_qualification_invalidation(
                {
                    "qualification_key": qualification,
                    "reason_code": "route_policy_changed",
                    "source_id": "policy_snapshot",
                    "invalidated_at": OBSERVED_AT,
                }
            )
            self.assertEqual(store.read_evidence(qualification), (evidence,))
            self.assertEqual(
                store.read_qualification_decisions(qualification),
                (decision,),
            )
            self.assertEqual(
                store.read_qualification_invalidations(qualification),
                (invalidation,),
            )

        with self.assertRaises(dataclasses.FrozenInstanceError):
            evidence.kind = "changed"  # type: ignore[misc]

    def test_canonical_payload_rejects_raw_content_keys(self) -> None:
        with d_drive_tempdir() as temp:
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            for key in (
                "raw_body",
                "rawBody",
                "remoteHTTPBody",
                "artifactJSONContent",
                "sourceURLPath",
            ):
                with self.subTest(key=key), self.assertRaisesRegex(
                    ValueError,
                    "raw content key",
                ):
                    store.append_evidence(
                        {
                            "qualification_key": "a" * 64,
                            "kind": "unsafe",
                            "subject_digest": "b" * 64,
                            "observed_at": OBSERVED_AT,
                            "payload": {"nested": {key: "PRIVATE"}},
                        }
                    )
            self.assertEqual(store.read_evidence("a" * 64), ())

    def test_fresh_32_process_bootstrap_and_append_has_exact_count(self) -> None:
        with d_drive_tempdir() as temp:
            database = temp / "observatory.sqlite3"
            snapshots = temp / "snapshots"
            start_signal = temp / "start.signal"
            process_count = 32
            processes = [
                subprocess.Popen(
                    [
                        sys.executable,
                        str(WRITER),
                        str(database),
                        str(snapshots),
                        str(start_signal),
                        str(temp / f"ready-{index}"),
                        f"worker-{index}",
                    ],
                    env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                for index in range(process_count)
            ]
            completed: list[tuple[str, str]] = []
            try:
                deadline = time.monotonic() + 30
                while (
                    len(tuple(temp.glob("ready-*"))) < process_count
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.005)
                self.assertEqual(len(tuple(temp.glob("ready-*"))), process_count)
                start_signal.touch()
                completed = [
                    process.communicate(timeout=45) for process in processes
                ]
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=15)

            failures = [
                (index, process.returncode, stdout, stderr)
                for index, (process, (stdout, stderr)) in enumerate(
                    zip(processes, completed)
                )
                if process.returncode != 0
            ]
            self.assertEqual(failures, [])
            records = ObservatoryDatabase(
                database,
                snapshots,
            ).read_evidence("a" * 64)

        self.assertEqual(len(records), process_count)
        self.assertEqual(len({record.evidence_id for record in records}), process_count)


if __name__ == "__main__":
    unittest.main()
