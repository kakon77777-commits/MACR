from __future__ import annotations

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from macr_runtime.authority import AuthorityScope, DispatchAuthorityStore
from macr_runtime.errors import DispatchAuthorizationError

from tests.support import d_drive_tempdir


class Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class DispatchAuthorityStoreTests(unittest.TestCase):
    def test_current_exact_authority_verifies(self) -> None:
        now = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
        with d_drive_tempdir() as temp:
            store = DispatchAuthorityStore(temp / "dispatch.sqlite3", now=Clock(now))
            reference = store.issue(
                source_kind="operator_profile",
                source_id="operator-managed-v1",
                scope=AuthorityScope(
                    providers=("grok",),
                    planes=("direct",),
                ),
                expires_at=(now + timedelta(days=1)).isoformat(),
            )

            verified = store.verify(
                reference,
                provider_id="grok",
                plane="direct",
                task_type="direct_chat",
            )

        self.assertEqual(verified.digest, reference.digest)
        self.assertEqual(verified.epoch, 0)

    def test_stop_epoch_revokes_old_authority(self) -> None:
        now = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
        with d_drive_tempdir() as temp:
            store = DispatchAuthorityStore(temp / "dispatch.sqlite3", now=Clock(now))
            reference = store.issue(
                source_kind="operator_profile",
                source_id="operator-managed-v1",
                scope=AuthorityScope(
                    providers=("grok",),
                    planes=("direct",),
                ),
                expires_at=(now + timedelta(days=1)).isoformat(),
            )

            epoch = store.advance_epoch(reason_digest="c" * 64, state="hold")

            self.assertEqual(epoch, 1)
            with self.assertRaisesRegex(DispatchAuthorizationError, "stale epoch"):
                store.verify(
                    reference,
                    provider_id="grok",
                    plane="direct",
                    task_type="direct_chat",
                )

    def test_reopen_epoch_requires_new_authority(self) -> None:
        now = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
        with d_drive_tempdir() as temp:
            store = DispatchAuthorityStore(temp / "dispatch.sqlite3", now=Clock(now))
            old = store.issue(
                source_kind="operator_profile",
                source_id="operator-managed-v1",
                scope=AuthorityScope(("grok",), ("direct",)),
                expires_at=(now + timedelta(days=1)).isoformat(),
            )
            store.advance_epoch(reason_digest="c" * 64, state="hold")
            store.advance_epoch(reason_digest="d" * 64, state="open")

            new = store.issue(
                source_kind="operator_profile",
                source_id="operator-managed-v1",
                scope=AuthorityScope(("grok",), ("direct",)),
                expires_at=(now + timedelta(days=1)).isoformat(),
            )

            self.assertEqual(new.epoch, 2)
            self.assertEqual(new.revision, 2)
            with self.assertRaisesRegex(DispatchAuthorizationError, "stale epoch"):
                store.verify(
                    old,
                    provider_id="grok",
                    plane="direct",
                    task_type="direct_chat",
                )
            store.verify(
                new,
                provider_id="grok",
                plane="direct",
                task_type="direct_chat",
            )

    def test_scope_and_expiry_mismatches_fail(self) -> None:
        now = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as temp:
            store = DispatchAuthorityStore(temp / "dispatch.sqlite3", now=clock)
            reference = store.issue(
                source_kind="batch_decision",
                source_id="batch-1",
                scope=AuthorityScope(
                    providers=("glm_flash_worker",),
                    planes=("delegation",),
                    task_types=("delegated_routine",),
                    batch_ids=("batch-1",),
                    member_digests=("a" * 64,),
                ),
                expires_at=(now + timedelta(minutes=5)).isoformat(),
            )

            cases = (
                {"provider_id": "grok", "plane": "delegation", "task_type": "delegated_routine", "batch_id": "batch-1", "member_digest": "a" * 64},
                {"provider_id": "glm_flash_worker", "plane": "direct", "task_type": "delegated_routine", "batch_id": "batch-1", "member_digest": "a" * 64},
                {"provider_id": "glm_flash_worker", "plane": "delegation", "task_type": "testing", "batch_id": "batch-1", "member_digest": "a" * 64},
                {"provider_id": "glm_flash_worker", "plane": "delegation", "task_type": "delegated_routine", "batch_id": "batch-2", "member_digest": "a" * 64},
                {"provider_id": "glm_flash_worker", "plane": "delegation", "task_type": "delegated_routine", "batch_id": "batch-1", "member_digest": "b" * 64},
            )
            for arguments in cases:
                with self.subTest(arguments=arguments):
                    with self.assertRaisesRegex(DispatchAuthorizationError, "scope"):
                        store.verify(reference, **arguments)

            clock.value = now + timedelta(minutes=6)
            with self.assertRaisesRegex(DispatchAuthorizationError, "expired"):
                store.verify(
                    reference,
                    provider_id="glm_flash_worker",
                    plane="delegation",
                    task_type="delegated_routine",
                    batch_id="batch-1",
                    member_digest="a" * 64,
                )

    def test_tampered_authority_body_is_rejected(self) -> None:
        now = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
        with d_drive_tempdir() as temp:
            database = temp / "dispatch.sqlite3"
            store = DispatchAuthorityStore(database, now=Clock(now))
            reference = store.issue(
                source_kind="test",
                source_id="authority-1",
                scope=AuthorityScope(("grok",), ("direct",)),
                expires_at=(now + timedelta(days=1)).isoformat(),
            )
            connection = sqlite3.connect(database)
            connection.execute(
                "UPDATE dispatch_authorities SET scope_json = ?",
                ('{"providers":["changed"]}',),
            )
            connection.commit()
            connection.close()

            with self.assertRaisesRegex(DispatchAuthorizationError, "digest"):
                store.verify(
                    reference,
                    provider_id="grok",
                    plane="direct",
                    task_type="direct_chat",
                )


if __name__ == "__main__":
    unittest.main()
