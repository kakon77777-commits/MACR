from __future__ import annotations

import hashlib
import json
import shutil
import unittest
from pathlib import Path

from macr_runtime.evidence_import import (
    EvidenceImportError,
    EvidenceImporter,
)
from macr_runtime.observatory_db import ObservatoryDatabase

from tests.support import d_drive_tempdir


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = ROOT / "tests" / "fixtures" / "glm-a3-evidence-manifest.json"
SOURCE_EVIDENCE = ROOT / "tests" / "fixtures" / "glm-a3-evidence"


def copy_fixture(target: Path) -> Path:
    manifest = target / SOURCE_MANIFEST.name
    shutil.copy2(SOURCE_MANIFEST, manifest)
    shutil.copytree(SOURCE_EVIDENCE, target / SOURCE_EVIDENCE.name)
    return manifest


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class EvidenceImportTests(unittest.TestCase):
    def test_inspect_writes_nothing_and_imports_bounded_roles_only(self) -> None:
        with d_drive_tempdir() as temp:
            manifest = copy_fixture(temp)
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            importer = EvidenceImporter(store)
            inspected = importer.inspect(manifest)
            before = store.evidence_count()
            report = importer.import_manifest(manifest, digest(manifest))
            repeated = importer.import_manifest(manifest, digest(manifest))
            decisions = store.qualification_decision_count()

        self.assertFalse(inspected.wrote)
        self.assertEqual(before, 0)
        self.assertEqual(
            report.imported_roles,
            (
                "bounded_exact_worker",
                "structured_output_worker",
                "verified_code_worker",
            ),
        )
        self.assertIn(
            "architecture_reviewer",
            report.rejected_or_unqualified_roles,
        )
        self.assertEqual(report.imported_count, 3)
        self.assertEqual(report.already_imported_count, 0)
        self.assertEqual(repeated.imported_count, 0)
        self.assertEqual(repeated.already_imported_count, 3)
        self.assertEqual(decisions, 0)
        self.assertTrue(report.wrote)
        self.assertNotIn("relative_path", str(report.to_dict()))
        self.assertNotIn("bounded-exact-worker.json", str(report.to_dict()))

    def test_changed_external_evidence_hash_fails_before_any_write(self) -> None:
        with d_drive_tempdir() as temp:
            manifest = copy_fixture(temp)
            target = temp / "glm-a3-evidence" / "verified-code-worker.json"
            target.write_bytes(target.read_bytes() + b"\nTAMPERED")
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            importer = EvidenceImporter(store)

            with self.assertRaisesRegex(EvidenceImportError, "hash mismatch"):
                importer.import_manifest(manifest, digest(manifest))
            count = store.evidence_count()

        self.assertEqual(count, 0)

    def test_unqualified_file_is_still_hash_checked_before_bounded_import(self) -> None:
        with d_drive_tempdir() as temp:
            manifest = copy_fixture(temp)
            target = temp / "glm-a3-evidence" / "architecture-reviewer.json"
            target.write_bytes(b"changed")
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            with self.assertRaisesRegex(EvidenceImportError, "hash mismatch"):
                EvidenceImporter(store).import_manifest(
                    manifest,
                    digest(manifest),
                )
            count = store.evidence_count()

        self.assertEqual(count, 0)

    def test_expected_manifest_digest_and_path_containment_fail_closed(self) -> None:
        with d_drive_tempdir() as temp:
            manifest = copy_fixture(temp)
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            importer = EvidenceImporter(store)
            with self.assertRaisesRegex(EvidenceImportError, "manifest digest"):
                importer.import_manifest(manifest, "0" * 64)

            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["entries"][0]["relative_path"] = "../escape.json"
            manifest.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(EvidenceImportError, "relative_path"):
                importer.inspect(manifest)
            count = store.evidence_count()

        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
