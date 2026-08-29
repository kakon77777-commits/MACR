from __future__ import annotations

import sqlite3
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from macr_runtime.batch_authority import (
    BatchAuthorityStore,
    BatchMemberScope,
    BatchScope,
)
from macr_runtime.errors import DispatchAuthorizationError

from tests.support import d_drive_tempdir


class Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def _member(seed: str, *, cost: float = 0.05) -> BatchMemberScope:
    return BatchMemberScope(
        member_digest=seed * 64,
        provider_id="glm_flash_worker",
        route_id=("a" if seed != "a" else "b") * 64,
        role_digest=("c" if seed != "c" else "d") * 64,
        privacy="public_text",
        context_class="non_sensitive_routine",
        cost_ceiling_usd=cost,
    )


def _scope(now: datetime) -> BatchScope:
    return BatchScope(
        plan_digest="f" * 64,
        ordered_members=(_member("1"), _member("2")),
        aggregate_cost_ceiling_usd=0.10,
        expires_at=(now + timedelta(hours=1)).isoformat(),
        authorized_dispatchers=("dispatcher-a", "dispatcher-b"),
    )


class BatchAuthorityTests(unittest.TestCase):
    def test_authority_binds_ordered_exact_members_and_aggregate_cost(self) -> None:
        now = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
        with d_drive_tempdir() as temp:
            store = BatchAuthorityStore(temp / "dispatch.sqlite3", now=Clock(now))
            scope = _scope(now)
            authority = store.issue(scope)

            self.assertEqual(
                store.verify(authority, scope, dispatcher_id="dispatcher-a"),
                authority,
            )
            with self.assertRaisesRegex(DispatchAuthorizationError, "member"):
                store.verify(
                    authority,
                    replace(scope, ordered_members=tuple(reversed(scope.ordered_members))),
                    dispatcher_id="dispatcher-a",
                )
            with self.assertRaisesRegex(DispatchAuthorizationError, "aggregate cost"):
                store.verify(
                    authority,
                    replace(scope, aggregate_cost_ceiling_usd=0.11),
                    dispatcher_id="dispatcher-a",
                )

    def test_dispatcher_and_expiry_are_fail_closed(self) -> None:
        now = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as temp:
            store = BatchAuthorityStore(temp / "dispatch.sqlite3", now=clock)
            scope = _scope(now)
            authority = store.issue(scope)

            with self.assertRaisesRegex(DispatchAuthorizationError, "dispatcher"):
                store.verify(authority, scope, dispatcher_id="dispatcher-z")

            clock.value = now + timedelta(hours=2)
            with self.assertRaisesRegex(DispatchAuthorizationError, "expired"):
                store.verify(authority, scope, dispatcher_id="dispatcher-a")

    def test_authorized_dispatchers_are_a_canonical_set(self) -> None:
        now = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
        with d_drive_tempdir() as temp:
            store = BatchAuthorityStore(temp / "dispatch.sqlite3", now=Clock(now))
            scope = replace(
                _scope(now),
                authorized_dispatchers=("dispatcher-b", "dispatcher-a"),
            )
            authority = store.issue(scope)

            store.verify(
                authority,
                replace(
                    scope,
                    authorized_dispatchers=("dispatcher-a", "dispatcher-b"),
                ),
                dispatcher_id="dispatcher-a",
            )

    def test_tampered_persistent_body_is_rejected(self) -> None:
        now = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
        with d_drive_tempdir() as temp:
            database = temp / "dispatch.sqlite3"
            store = BatchAuthorityStore(database, now=Clock(now))
            scope = _scope(now)
            authority = store.issue(scope)

            connection = sqlite3.connect(database)
            connection.execute(
                "UPDATE batch_authorities SET scope_json = ?",
                ('{"tampered":true}',),
            )
            connection.commit()
            connection.close()

            with self.assertRaisesRegex(DispatchAuthorizationError, "digest"):
                store.verify(authority, scope, dispatcher_id="dispatcher-a")


if __name__ == "__main__":
    unittest.main()
