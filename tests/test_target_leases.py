from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from macr_runtime.errors import DispatchLeaseError
from macr_runtime.target_leases import (
    RepositoryIdentity,
    TargetLeaseState,
    TargetLeaseStore,
)

from tests.support import d_drive_tempdir


PLAN = "a" * 64
MEMBER_A = "b" * 64
MEMBER_B = "c" * 64


class Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class TargetLeaseTests(unittest.TestCase):
    def test_two_members_cannot_own_same_target_without_named_alternatives(self) -> None:
        now = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)
        with d_drive_tempdir() as temp:
            root = temp / "repo"
            root.mkdir()
            repository = RepositoryIdentity.create(root, "d" * 64)
            leases = TargetLeaseStore(
                temp / "runtime.sqlite3",
                repository,
                now=Clock(now),
            )
            leases.acquire(PLAN, MEMBER_A, "src/a.py", ttl_seconds=60)

            with self.assertRaisesRegex(DispatchLeaseError, "target"):
                leases.acquire(PLAN, MEMBER_B, "src/a.py", ttl_seconds=60)

    def test_named_alternatives_allow_at_most_one_automatic_materializer(self) -> None:
        now = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)
        with d_drive_tempdir() as temp:
            root = temp / "repo"
            root.mkdir()
            repository = RepositoryIdentity.create(root, "d" * 64)
            leases = TargetLeaseStore(
                temp / "runtime.sqlite3",
                repository,
                now=Clock(now),
            )
            first = leases.acquire(
                PLAN,
                MEMBER_A,
                "src/a.py",
                alternative_group="implementation-alternatives",
                materialize_automatically=True,
                ttl_seconds=60,
            )
            second = leases.acquire(
                PLAN,
                MEMBER_B,
                "src/a.py",
                alternative_group="implementation-alternatives",
                materialize_automatically=False,
                ttl_seconds=60,
            )
            self.assertNotEqual(first.lease_id, second.lease_id)

        with d_drive_tempdir() as temp:
            root = temp / "repo"
            root.mkdir()
            repository = RepositoryIdentity.create(root, "d" * 64)
            leases = TargetLeaseStore(
                temp / "runtime.sqlite3",
                repository,
                now=Clock(now),
            )
            leases.acquire(
                PLAN,
                MEMBER_A,
                "src/a.py",
                alternative_group="implementation-alternatives",
                materialize_automatically=True,
                ttl_seconds=60,
            )
            with self.assertRaisesRegex(DispatchLeaseError, "automatic"):
                leases.acquire(
                    PLAN,
                    MEMBER_B,
                    "src/a.py",
                    alternative_group="implementation-alternatives",
                    materialize_automatically=True,
                    ttl_seconds=60,
                )

    def test_windows_aliases_collide_and_raw_path_never_enters_database(self) -> None:
        now = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)
        with d_drive_tempdir() as temp:
            root = temp / "repo"
            root.mkdir()
            database = temp / "runtime.sqlite3"
            repository = RepositoryIdentity.create(root, "d" * 64)
            leases = TargetLeaseStore(database, repository, now=Clock(now))
            first = leases.acquire(
                PLAN,
                MEMBER_A,
                r"Src\Module.py",
                ttl_seconds=60,
            )
            with self.assertRaisesRegex(DispatchLeaseError, "target"):
                leases.acquire(
                    PLAN,
                    MEMBER_B,
                    "src/module.py",
                    ttl_seconds=60,
                )

            self.assertEqual(
                first.target_key,
                repository.normalize_target("src/module.py").target_key,
            )
            self.assertNotIn(b"Src\\Module.py", database.read_bytes())
            self.assertNotIn(b"src/module.py", database.read_bytes())

    def test_escape_drive_unc_reserved_and_reparse_aliases_are_rejected(self) -> None:
        with d_drive_tempdir() as temp:
            root = temp / "repo"
            root.mkdir()
            repository = RepositoryIdentity.create(root, "d" * 64)
            cases = (
                "../outside.py",
                r"D:\outside.py",
                r"\\server\share\file.py",
                "/absolute/file.py",
                "src/NUL.txt",
                "src/file.py:stream",
            )
            for target in cases:
                with self.subTest(target=target):
                    with self.assertRaisesRegex(ValueError, "target"):
                        repository.normalize_target(target)

    def test_expiry_requires_visible_reconciliation_before_release(self) -> None:
        now = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as temp:
            root = temp / "repo"
            root.mkdir()
            repository = RepositoryIdentity.create(root, "d" * 64)
            leases = TargetLeaseStore(
                temp / "runtime.sqlite3",
                repository,
                now=clock,
            )
            first = leases.acquire(
                PLAN,
                MEMBER_A,
                "src/a.py",
                ttl_seconds=30,
            )
            clock.value = now + timedelta(minutes=1)

            with self.assertRaisesRegex(DispatchLeaseError, "reconciliation"):
                leases.acquire(
                    PLAN,
                    MEMBER_B,
                    "src/a.py",
                    ttl_seconds=30,
                )
            self.assertEqual(
                leases.read(first.lease_id).state,
                TargetLeaseState.RECONCILIATION_REQUIRED,
            )
            leases.reconcile_release(first.lease_id, evidence_digest="e" * 64)
            second = leases.acquire(
                PLAN,
                MEMBER_B,
                "src/a.py",
                ttl_seconds=30,
            )
            self.assertEqual(second.state, TargetLeaseState.ACTIVE)


if __name__ == "__main__":
    unittest.main()
