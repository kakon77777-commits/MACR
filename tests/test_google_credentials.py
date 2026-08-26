from __future__ import annotations

import json
import contextlib
import io
import unittest

from macr_runtime.errors import StoragePolicyError
from macr_runtime.google_credentials import main, stage_service_account
from tests.support import d_drive_tempdir


def fake_service_account() -> bytes:
    document = {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "test-key-id",
        "private_key": (
            "-----BEGIN "
            + "PRIVATE KEY-----\nTEST\n-----END "
            + "PRIVATE KEY-----\n"
        ),
        "client_email": "test@example.invalid",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    return json.dumps(document, sort_keys=True).encode("utf-8")


class GoogleCredentialTests(unittest.TestCase):
    def test_copy_is_byte_exact_and_source_remains(self) -> None:
        with d_drive_tempdir() as temp:
            source = temp / "source.json"
            target = temp / "key-area" / "GOOGLE_VERTEX.json"
            source.write_bytes(fake_service_account())
            result = stage_service_account(source, target)
            self.assertTrue(result.copied)
            self.assertTrue(result.sha256_equal)
            self.assertTrue(result.shape_valid)
            self.assertEqual(source.read_bytes(), target.read_bytes())

    def test_identical_target_is_idempotent_but_different_target_is_refused(
        self,
    ) -> None:
        with d_drive_tempdir() as temp:
            source = temp / "source.json"
            target = temp / "GOOGLE_VERTEX.json"
            source.write_bytes(fake_service_account())
            target.write_bytes(fake_service_account())
            self.assertFalse(stage_service_account(source, target).copied)
            target.write_bytes(b"different")
            with self.assertRaisesRegex(FileExistsError, "different bytes"):
                stage_service_account(source, target)

    def test_non_d_target_is_rejected_before_copy(self) -> None:
        with d_drive_tempdir() as temp:
            source = temp / "source.json"
            source.write_bytes(fake_service_account())
            with self.assertRaisesRegex(StoragePolicyError, "target must be on D"):
                stage_service_account(source, r"C:\temp\GOOGLE_VERTEX.json")

    def test_wrong_token_uri_and_missing_fields_are_rejected(self) -> None:
        with d_drive_tempdir() as temp:
            source = temp / "bad.json"
            source.write_text(
                json.dumps(
                    {
                        "type": "service_account",
                        "project_id": "test-project",
                        "private_key_id": "test-key-id",
                        "private_key": "test-key",
                        "client_email": "test@example.invalid",
                        "token_uri": "https://example.invalid/token",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(StoragePolicyError, "token URI"):
                stage_service_account(source, temp / "target.json")

    def test_cli_reports_only_bounded_copy_metadata(self) -> None:
        with d_drive_tempdir() as temp:
            source = temp / "private-source.json"
            target = temp / "private-target.json"
            source.write_bytes(fake_service_account())
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(
                    ["--source", str(source), "--target", str(target)]
                )
            document = json.loads(output.getvalue())
            self.assertEqual(status, 0)
            self.assertEqual(document["status"], "staged")
            self.assertTrue(document["sha256_equal"])
            self.assertNotIn(str(source), output.getvalue())
            self.assertNotIn(str(target), output.getvalue())
            self.assertNotIn("test-project", output.getvalue())
            self.assertNotIn("test@example.invalid", output.getvalue())


if __name__ == "__main__":
    unittest.main()
