from __future__ import annotations

import os
import unittest

from macr_runtime.candidate_vault import CandidateVault
from macr_runtime.errors import CandidateConflict, StoragePolicyError
from macr_runtime.execution import DispatchOrigin

from tests.support import d_drive_tempdir


PROVIDER = "glm_flash_worker"
RUN_ID = "11111111-1111-4111-8111-111111111111"
ORIGIN = DispatchOrigin("test", "process_id", "1234")


class CandidateVaultTests(unittest.TestCase):
    def test_capture_is_create_once_and_idempotent_for_identical_bytes(self) -> None:
        with d_drive_tempdir() as temp:
            vault = CandidateVault(
                temp / "candidates",
                temp / "dispatch.sqlite3",
            )

            first = vault.capture(
                PROVIDER,
                RUN_ID,
                b"exact answer",
                task_digest="a" * 64,
                approval_digest="b" * 64,
            )
            second = vault.capture(
                PROVIDER,
                RUN_ID,
                b"exact answer",
                task_digest="a" * 64,
                approval_digest="b" * 64,
            )
            with self.assertRaisesRegex(CandidateConflict, "different bytes"):
                vault.capture(
                    PROVIDER,
                    RUN_ID,
                    b"changed answer",
                    task_digest="a" * 64,
                    approval_digest="b" * 64,
                )

            self.assertEqual(vault.read(first.capture_id), b"exact answer")

        self.assertEqual(first, second)

    def test_public_capture_metadata_omits_path_and_content(self) -> None:
        with d_drive_tempdir() as temp:
            vault = CandidateVault(
                temp / "candidates",
                temp / "dispatch.sqlite3",
            )
            capture = vault.capture(
                PROVIDER,
                RUN_ID,
                b"PRIVATE ANSWER",
                task_digest="a" * 64,
                approval_digest=None,
            )

            public = capture.to_public_dict()

        self.assertNotIn("PRIVATE", str(public))
        self.assertNotIn("path", str(public).lower())
        self.assertEqual(public["answer_bytes"], 14)
        self.assertEqual(len(public["answer_sha256"]), 64)

    def test_verbatim_materialization_is_byte_identical_and_repeatable(self) -> None:
        with d_drive_tempdir() as temp:
            vault = CandidateVault(
                temp / "candidates",
                temp / "dispatch.sqlite3",
            )
            capture = vault.capture(
                PROVIDER,
                RUN_ID,
                b"source\r\nbytes",
                task_digest="a" * 64,
                approval_digest=None,
            )
            target = temp / "materialized" / "candidate.txt"

            first = vault.materialize_verbatim(
                capture.capture_id,
                target,
                builder_origin=ORIGIN,
            )
            second = vault.materialize_verbatim(
                capture.capture_id,
                target,
                builder_origin=ORIGIN,
            )

            output = target.read_bytes()

        self.assertEqual(output, b"source\r\nbytes")
        self.assertEqual(first.state, "verbatim")
        self.assertEqual(second.output_sha256, capture.sha256)

    def test_semantic_edit_cannot_claim_verbatim_materialization(self) -> None:
        with d_drive_tempdir() as temp:
            vault = CandidateVault(
                temp / "candidates",
                temp / "dispatch.sqlite3",
            )
            capture = vault.capture(
                PROVIDER,
                RUN_ID,
                b"source",
                task_digest="a" * 64,
                approval_digest=None,
            )

            transformed = vault.record_transformation(
                capture.capture_id,
                b"source\n// edited",
                transformer_version="manual-v1",
                builder_origin=ORIGIN,
            )

        self.assertEqual(transformed.state, "transformed")
        self.assertNotEqual(transformed.output_sha256, capture.sha256)
        self.assertEqual(transformed.transformer_version, "manual-v1")

    def test_vault_and_materialization_paths_must_be_on_d(self) -> None:
        with self.assertRaisesRegex(StoragePolicyError, "absolute on D"):
            CandidateVault(
                r"C:\candidate-vault",
                r"D:\AI_RESIDENCE\AI_Runtime\macr-state\dispatch.sqlite3",
            )
        with d_drive_tempdir() as temp:
            vault = CandidateVault(
                temp / "candidates",
                temp / "dispatch.sqlite3",
            )
            capture = vault.capture(
                PROVIDER,
                RUN_ID,
                b"source",
                task_digest="a" * 64,
                approval_digest=None,
            )
            with self.assertRaisesRegex(StoragePolicyError, "absolute on D"):
                vault.materialize_verbatim(
                    capture.capture_id,
                    r"C:\candidate.txt",
                    builder_origin=ORIGIN,
                )

    def test_reparse_candidate_root_is_rejected_when_supported(self) -> None:
        with d_drive_tempdir() as temp:
            target = temp / "target"
            target.mkdir()
            link = temp / "candidate-link"
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symbolic links unavailable: {type(exc).__name__}")

            with self.assertRaisesRegex(StoragePolicyError, "reparse"):
                CandidateVault(link, temp / "dispatch.sqlite3")

    def test_confirmed_direct_purge_removes_bytes_but_keeps_metadata(self) -> None:
        with d_drive_tempdir() as temp:
            vault = CandidateVault(
                temp / "candidates",
                temp / "dispatch.sqlite3",
            )
            capture = vault.capture(
                "ollama_qwythos",
                RUN_ID,
                b"PRIVATE_CANDIDATE_SENTINEL_49D5",
                task_digest="a" * 64,
                approval_digest="b" * 64,
            )
            target = vault.root / capture.relative_path
            self.assertTrue(target.is_file())

            with self.assertRaisesRegex(ValueError, "DELETE"):
                vault.purge_direct_run(
                    "ollama_qwythos",
                    RUN_ID,
                    confirmation="delete",
                )
            self.assertTrue(target.is_file())

            removed = vault.purge_direct_run(
                "ollama_qwythos",
                RUN_ID,
                confirmation="DELETE",
            )

            self.assertTrue(removed)
            self.assertFalse(target.exists())
            self.assertIsNotNone(vault.read_by_run(RUN_ID))
            with self.assertRaisesRegex(CandidateConflict, "missing"):
                vault.read(capture.capture_id)
            self.assertFalse(
                vault.purge_direct_run(
                    "ollama_qwythos",
                    RUN_ID,
                    confirmation="DELETE",
                )
            )

    def test_direct_purge_rejects_provider_mismatch(self) -> None:
        with d_drive_tempdir() as temp:
            vault = CandidateVault(
                temp / "candidates",
                temp / "dispatch.sqlite3",
            )
            capture = vault.capture(
                "ollama_qwythos",
                RUN_ID,
                b"private",
                task_digest="a" * 64,
                approval_digest=None,
            )
            with self.assertRaisesRegex(CandidateConflict, "provider"):
                vault.purge_direct_run(
                    "grok",
                    RUN_ID,
                    confirmation="DELETE",
                )
            self.assertEqual(vault.read(capture.capture_id), b"private")


if __name__ == "__main__":
    unittest.main()
