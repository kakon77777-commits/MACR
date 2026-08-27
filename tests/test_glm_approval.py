from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID

from macr_runtime.errors import ProviderPolicyError
from macr_runtime.glm_approval import GlmApprovalStore
from tests.support import d_drive_tempdir


class Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class GlmApprovalStoreTests(unittest.TestCase):
    def test_host_approval_record_is_external_content_free_and_verifiable(self):
        now = datetime(2026, 8, 27, 7, 0, tzinfo=timezone.utc)
        digest = "c" * 64
        with d_drive_tempdir() as state_root:
            store = GlmApprovalStore(state_root, now=Clock(now))

            created = store.create(digest, expires_in_days=30)
            verified = store.verify(digest)
            record_text = store.record_path(digest).read_text(encoding="utf-8")

        self.assertEqual(created["approval_sha256"], digest)
        self.assertEqual(created["approved_by"], "host_operator")
        self.assertEqual(verified, created)
        self.assertEqual(UUID(created["nonce"]).version, 4)
        self.assertNotIn("prompt", record_text.lower())
        self.assertNotIn("answer", record_text.lower())
        self.assertNotIn("credential", record_text.lower())

    def test_expired_or_missing_approval_fails_closed(self):
        start = datetime(2026, 8, 27, 7, 0, tzinfo=timezone.utc)
        clock = Clock(start)
        digest = "d" * 64
        with d_drive_tempdir() as state_root:
            store = GlmApprovalStore(state_root, now=clock)
            store.create(digest, expires_in_days=1)
            clock.value = start + timedelta(days=2)

            with self.assertRaisesRegex(ProviderPolicyError, "expired"):
                store.verify(digest)
            with self.assertRaisesRegex(ProviderPolicyError, "record"):
                store.verify("e" * 64)

    def test_record_shape_tampering_is_rejected(self):
        now = datetime(2026, 8, 27, 7, 0, tzinfo=timezone.utc)
        digest = "f" * 64
        with d_drive_tempdir() as state_root:
            store = GlmApprovalStore(state_root, now=Clock(now))
            store.create(digest, expires_in_days=30)
            path = store.record_path(digest)
            document = json.loads(path.read_text(encoding="utf-8"))
            document["approved_by"] = "task_producer"
            path.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(ProviderPolicyError, "invalid"):
                store.verify(digest)


if __name__ == "__main__":
    unittest.main()
