from __future__ import annotations

import json
import sqlite3
import unittest
import uuid
from pathlib import Path

from macr_runtime.errors import LegacyLedgerError
from macr_runtime.legacy_ledger import LegacyLedgerImporter
from macr_runtime.runtime_db import RuntimeDatabase

from tests.support import d_drive_tempdir


def legacy_event(index: int, *, event_id: str | None = None) -> dict:
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "event_type": "provider.candidate_completed",
        "observed_at": f"2026-08-27T00:00:{index:02d}+00:00",
        "payload": {
            "task_id": f"legacy-{index}",
            "provider_id": "glm_flash_worker",
            "status": "candidate_success",
        },
    }


def write_legacy_fixture(path: Path, *, count: int) -> Path:
    path.write_text(
        "".join(
            json.dumps(legacy_event(index), sort_keys=True) + "\n"
            for index in range(count)
        ),
        encoding="utf-8",
    )
    return path


def write_legacy_documents(path: Path, documents: list[dict]) -> Path:
    path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in documents),
        encoding="utf-8",
    )
    return path


class LegacyLedgerImporterTests(unittest.TestCase):
    def test_valid_import_is_copy_only_and_exact_count(self) -> None:
        with d_drive_tempdir() as temp:
            source = write_legacy_fixture(temp / "events.jsonl", count=3)
            before = source.read_bytes()
            importer = LegacyLedgerImporter(
                temp / "dispatch.sqlite3",
                temp / "quarantine",
            )

            report = importer.import_file(source, expected_count=3)
            after = source.read_bytes()

        self.assertEqual(before, after)
        self.assertTrue(report.complete)
        self.assertEqual(report.observed_count, 3)
        self.assertEqual(report.valid_count, 3)
        self.assertEqual(report.imported_count, 3)
        self.assertEqual(report.corrupt_count, 0)

    def test_corrupt_line_is_quarantined_and_import_is_incomplete(self) -> None:
        valid = json.dumps(legacy_event(1), sort_keys=True).encode("utf-8")
        corrupt = b'"event_type":"legacy"} trailing'
        with d_drive_tempdir() as temp:
            source = temp / "events.jsonl"
            source.write_bytes(valid + b"\n" + corrupt + b"\n")
            before = source.read_bytes()
            importer = LegacyLedgerImporter(
                temp / "dispatch.sqlite3",
                temp / "quarantine",
            )

            report = importer.import_file(source, expected_count=2)
            after = source.read_bytes()
            quarantined = importer.read_quarantine(report.source_sha256)

        self.assertEqual(before, after)
        self.assertFalse(report.complete)
        self.assertEqual(report.valid_count, 1)
        self.assertEqual(report.corrupt_count, 1)
        self.assertEqual(quarantined[0]["line_number"], 2)
        self.assertEqual(quarantined[0]["raw_bytes"], corrupt)
        self.assertEqual(quarantined[0]["error_code"], "invalid_json")

    def test_invalid_utf8_is_quarantined_without_replacement_decode(self) -> None:
        with d_drive_tempdir() as temp:
            source = temp / "events.jsonl"
            source.write_bytes(b'{"event_id":"one"}\n\xff\xfe\n')
            importer = LegacyLedgerImporter(
                temp / "dispatch.sqlite3",
                temp / "quarantine",
            )

            report = importer.import_file(source)
            quarantined = importer.read_quarantine(report.source_sha256)

        self.assertFalse(report.complete)
        self.assertEqual(report.corrupt_count, 2)
        self.assertEqual(
            {item["error_code"] for item in quarantined},
            {"invalid_shape", "invalid_utf8"},
        )

    def test_duplicate_keys_and_forbidden_payload_are_quarantined(self) -> None:
        duplicate_key = (
            b'{"event_id":"one","event_id":"two",'
            b'"event_type":"legacy","observed_at":"2026-08-27T00:00:00+00:00",'
            b'"payload":{}}'
        )
        forbidden_payload = json.dumps(
            {
                **legacy_event(2),
                "payload": {"answer": "PRIVATE"},
            }
        ).encode("utf-8")
        invalid_time = json.dumps(
            {
                **legacy_event(3),
                "observed_at": "2026-08-27T00:00:00",
            }
        ).encode("utf-8")
        with d_drive_tempdir() as temp:
            source = temp / "events.jsonl"
            source.write_bytes(
                duplicate_key
                + b"\n"
                + forbidden_payload
                + b"\n"
                + invalid_time
                + b"\n"
            )
            importer = LegacyLedgerImporter(
                temp / "dispatch.sqlite3",
                temp / "quarantine",
            )

            report = importer.import_file(source, expected_count=3)
            quarantined = importer.read_quarantine(report.source_sha256)

        self.assertFalse(report.complete)
        self.assertEqual(report.valid_count, 0)
        self.assertEqual(
            [item["error_code"] for item in quarantined],
            ["duplicate_json_key", "forbidden_payload", "invalid_shape"],
        )

    def test_second_import_is_idempotent(self) -> None:
        with d_drive_tempdir() as temp:
            source = write_legacy_fixture(temp / "events.jsonl", count=3)
            importer = LegacyLedgerImporter(
                temp / "dispatch.sqlite3",
                temp / "quarantine",
            )

            first = importer.import_file(source, expected_count=3)
            second = importer.import_file(source, expected_count=3)

        self.assertEqual(first.imported_count, 3)
        self.assertEqual(second.imported_count, 0)
        self.assertEqual(second.already_imported_count, 3)
        self.assertTrue(second.complete)

    def test_appended_source_imports_only_new_logical_events(self) -> None:
        documents = [legacy_event(1), legacy_event(2)]
        with d_drive_tempdir() as temp:
            source = write_legacy_documents(temp / "events.jsonl", documents)
            database = temp / "dispatch.sqlite3"
            importer = LegacyLedgerImporter(database, temp / "quarantine")

            first = importer.import_file(source, expected_count=2)
            documents.append(legacy_event(3))
            write_legacy_documents(source, documents)
            appended_bytes = source.read_bytes()
            second = importer.import_file(source, expected_count=3)
            repeated = importer.import_file(source, expected_count=3)
            after_import_bytes = source.read_bytes()

            connection = sqlite3.connect(database)
            event_count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            source_count = connection.execute(
                "SELECT COUNT(*) FROM legacy_sources"
            ).fetchone()[0]
            connection.close()

        self.assertEqual(first.imported_count, 2)
        self.assertEqual(first.already_imported_count, 0)
        self.assertEqual(second.imported_count, 1)
        self.assertEqual(second.already_imported_count, 2)
        self.assertEqual(repeated.imported_count, 0)
        self.assertEqual(repeated.already_imported_count, 3)
        self.assertEqual(event_count, 3)
        self.assertEqual(source_count, 2)
        self.assertEqual(after_import_bytes, appended_bytes)

    def test_changed_content_for_existing_legacy_event_id_fails_closed(self) -> None:
        original = legacy_event(1)
        changed = {
            **original,
            "payload": {
                **original["payload"],
                "status": "candidate_failure",
            },
        }
        with d_drive_tempdir() as temp:
            source = write_legacy_documents(temp / "events.jsonl", [original])
            database = temp / "dispatch.sqlite3"
            importer = LegacyLedgerImporter(database, temp / "quarantine")
            importer.import_file(source, expected_count=1)
            write_legacy_documents(source, [changed])

            with self.assertRaisesRegex(LegacyLedgerError, "conflicts"):
                importer.import_file(source, expected_count=1)

            connection = sqlite3.connect(database)
            event_count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            source_count = connection.execute(
                "SELECT COUNT(*) FROM legacy_sources"
            ).fetchone()[0]
            connection.close()

        self.assertEqual(event_count, 1)
        self.assertEqual(source_count, 1)

    def test_expected_count_shortfall_is_visible(self) -> None:
        with d_drive_tempdir() as temp:
            source = write_legacy_fixture(temp / "events.jsonl", count=2)
            importer = LegacyLedgerImporter(
                temp / "dispatch.sqlite3",
                temp / "quarantine",
            )

            report = importer.import_file(source, expected_count=3)

        self.assertFalse(report.complete)
        self.assertEqual(report.expected_count, 3)
        self.assertEqual(report.observed_count, 2)

    def test_duplicate_original_event_ids_are_reported(self) -> None:
        duplicate = str(uuid.uuid4())
        documents = [
            legacy_event(1, event_id=duplicate),
            legacy_event(2, event_id=duplicate),
        ]
        with d_drive_tempdir() as temp:
            source = temp / "events.jsonl"
            source.write_text(
                "".join(json.dumps(item) + "\n" for item in documents),
                encoding="utf-8",
            )
            importer = LegacyLedgerImporter(
                temp / "dispatch.sqlite3",
                temp / "quarantine",
            )

            report = importer.import_file(source, expected_count=2)

        self.assertFalse(report.complete)
        self.assertEqual(report.duplicate_count, 1)
        self.assertEqual(report.imported_count, 2)

    def test_dry_run_writes_nothing(self) -> None:
        with d_drive_tempdir() as temp:
            source = write_legacy_fixture(temp / "events.jsonl", count=2)
            database = temp / "dispatch.sqlite3"
            quarantine = temp / "quarantine"
            importer = LegacyLedgerImporter(database, quarantine)

            report = importer.inspect(source, expected_count=2)

            self.assertTrue(report.complete)
            self.assertFalse(database.exists())
            self.assertFalse(quarantine.exists())

    def test_runtime_schema_one_upgrades_in_place_to_current_schema(self) -> None:
        with d_drive_tempdir() as temp:
            database = temp / "dispatch.sqlite3"
            connection = sqlite3.connect(database)
            connection.execute(
                "CREATE TABLE schema_meta(component TEXT PRIMARY KEY, version INTEGER NOT NULL)"
            )
            connection.execute(
                "INSERT INTO schema_meta(component, version) VALUES ('runtime', 1)"
            )
            connection.commit()
            connection.close()
            source = write_legacy_fixture(temp / "events.jsonl", count=1)

            report = LegacyLedgerImporter(
                database,
                temp / "quarantine",
            ).import_file(source, expected_count=1)

            connection = sqlite3.connect(database)
            version = connection.execute(
                "SELECT version FROM schema_meta WHERE component = 'runtime'"
            ).fetchone()[0]
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            connection.close()

        self.assertTrue(report.complete)
        self.assertEqual(version, RuntimeDatabase.SCHEMA_VERSION)
        self.assertIn("legacy_sources", tables)
        self.assertIn("legacy_quarantine", tables)
        self.assertIn("dispatch_authorities", tables)
        self.assertIn("dispatch_leases", tables)
        self.assertIn("candidate_captures", tables)
        self.assertIn("materializations", tables)


if __name__ == "__main__":
    unittest.main()
