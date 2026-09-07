from __future__ import annotations

import hashlib
import hmac
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID

from macr_runtime.errors import ProviderPolicyError
from macr_runtime.glm_approval import GlmApprovalStore
from tests.support import d_drive_tempdir


class Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


SIGNING_KEY = "host-approval-signing-key"


def sign_record(document: dict, signing_key: str = SIGNING_KEY) -> None:
    body = {key: value for key, value in document.items() if key != "mac_sha256"}
    encoded = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    document["mac_sha256"] = hmac.new(
        signing_key.encode("utf-8"),
        encoded,
        hashlib.sha256,
    ).hexdigest()


class GlmApprovalStoreTests(unittest.TestCase):
    def test_typed_approval_record_binds_contract_and_provider_tier(self):
        now = datetime(2026, 8, 27, 7, 0, tzinfo=timezone.utc)
        digest = "a" * 64
        binding_digest = "b" * 64
        with d_drive_tempdir() as state_root:
            store = GlmApprovalStore(state_root, now=Clock(now))

            created = store.create(
                digest,
                signing_key=SIGNING_KEY,
                expires_in_days=30,
                approval_contract_schema=3,
                provider_tier_binding_digest=binding_digest,
            )
            verified = store.verify(digest, signing_key=SIGNING_KEY)

        self.assertEqual(created["schema_version"], 2)
        self.assertEqual(created["approval_contract_schema"], 3)
        self.assertEqual(
            created["provider_tier_binding_digest"],
            binding_digest,
        )
        self.assertEqual(verified, created)

    def test_content_free_status_distinguishes_legacy_and_typed_records(self):
        now = datetime(2026, 8, 27, 7, 0, tzinfo=timezone.utc)
        with d_drive_tempdir() as state_root:
            store = GlmApprovalStore(state_root, now=Clock(now))
            store.create(
                "c" * 64,
                signing_key=SIGNING_KEY,
                expires_in_days=30,
            )
            store.create(
                "d" * 64,
                signing_key=SIGNING_KEY,
                expires_in_days=30,
                approval_contract_schema=3,
                provider_tier_binding_digest="e" * 64,
            )

            status = store.status_snapshot()

        self.assertEqual(
            status,
            {
                "current_typed_count": 1,
                "invalid_count": 0,
                "legacy_pre_tier_count": 1,
                "total_count": 2,
            },
        )

    def test_reparse_approval_ancestor_is_rejected_before_child_creation(self):
        with d_drive_tempdir() as state_root:
            approvals_root = state_root / "approvals"
            approvals_root.mkdir()
            store = GlmApprovalStore(state_root)

            with patch.object(
                store,
                "_is_reparse",
                side_effect=lambda path: path == approvals_root,
            ):
                with self.assertRaisesRegex(ProviderPolicyError, "reparse"):
                    store._ensure_root()

            self.assertFalse((approvals_root / "glm").exists())

    def test_host_approval_record_is_external_content_free_and_verifiable(self):
        now = datetime(2026, 8, 27, 7, 0, tzinfo=timezone.utc)
        digest = "c" * 64
        with d_drive_tempdir() as state_root:
            store = GlmApprovalStore(state_root, now=Clock(now))

            created = store.create(
                digest,
                signing_key=SIGNING_KEY,
                expires_in_days=30,
            )
            verified = store.verify(digest, signing_key=SIGNING_KEY)
            record_text = store.record_path(digest).read_text(encoding="utf-8")

        self.assertEqual(created["approval_sha256"], digest)
        self.assertEqual(created["approved_by"], "host_operator")
        self.assertEqual(len(created["mac_sha256"]), 64)
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
            store.create(digest, signing_key=SIGNING_KEY, expires_in_days=1)
            clock.value = start + timedelta(days=2)

            with self.assertRaisesRegex(ProviderPolicyError, "expired"):
                store.verify(digest, signing_key=SIGNING_KEY)
            with self.assertRaisesRegex(ProviderPolicyError, "record"):
                store.verify("e" * 64, signing_key=SIGNING_KEY)

    def test_record_shape_tampering_is_rejected(self):
        now = datetime(2026, 8, 27, 7, 0, tzinfo=timezone.utc)
        digest = "f" * 64
        with d_drive_tempdir() as state_root:
            store = GlmApprovalStore(state_root, now=Clock(now))
            store.create(digest, signing_key=SIGNING_KEY, expires_in_days=30)
            path = store.record_path(digest)
            document = json.loads(path.read_text(encoding="utf-8"))
            document["approved_by"] = "task_producer"
            path.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(ProviderPolicyError, "MAC"):
                store.verify(digest, signing_key=SIGNING_KEY)

    def test_well_shaped_forgery_and_future_dated_record_are_rejected(self):
        now = datetime(2026, 8, 27, 7, 0, tzinfo=timezone.utc)
        digest = "1" * 64
        with d_drive_tempdir() as state_root:
            store = GlmApprovalStore(state_root, now=Clock(now))
            store.create(digest, signing_key=SIGNING_KEY, expires_in_days=30)
            path = store.record_path(digest)
            document = json.loads(path.read_text(encoding="utf-8"))
            document["expires_at"] = (now + timedelta(days=300)).isoformat()
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ProviderPolicyError, "MAC"):
                store.verify(digest, signing_key=SIGNING_KEY)

            document["approved_at"] = (now + timedelta(days=10)).isoformat()
            document["expires_at"] = (now + timedelta(days=20)).isoformat()
            sign_record(document)
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ProviderPolicyError, "future"):
                store.verify(digest, signing_key=SIGNING_KEY)

    def test_explicit_replacement_archives_existing_record_before_renewal(self):
        start = datetime(2026, 8, 27, 7, 0, tzinfo=timezone.utc)
        clock = Clock(start)
        digest = "2" * 64
        with d_drive_tempdir() as state_root:
            store = GlmApprovalStore(state_root, now=clock)
            original = store.create(
                digest,
                signing_key=SIGNING_KEY,
                expires_in_days=1,
            )
            clock.value = start + timedelta(days=2)

            renewed = store.create(
                digest,
                signing_key=SIGNING_KEY,
                expires_in_days=30,
                replace_existing=True,
            )
            history = list((store.root / "history").glob("*.json"))
            verified = store.verify(digest, signing_key=SIGNING_KEY)

        self.assertNotEqual(renewed["nonce"], original["nonce"])
        self.assertEqual(renewed, verified)
        self.assertEqual(len(history), 1)


if __name__ == "__main__":
    unittest.main()
