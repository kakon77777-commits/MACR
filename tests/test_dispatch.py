from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from macr_runtime.authority import AuthorityScope, DispatchAuthorityStore
from macr_runtime.dispatch import AdmissionGate, DispatcherLeaseStore
from macr_runtime.errors import DispatchAuthorizationError, DispatchLeaseError
from macr_runtime.execution import (
    DispatchContext,
    DispatchOrigin,
    InteractionPlane,
)

from tests.support import d_drive_tempdir


RUN_ONE = "11111111-1111-4111-8111-111111111111"
RUN_TWO = "22222222-2222-4222-8222-222222222222"


class Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def context_for(
    reference,
    *,
    run_id: str = RUN_ONE,
    provider_tier_binding_digest: str | None = None,
) -> DispatchContext:
    return DispatchContext(
        run_id=run_id,
        plane=InteractionPlane.DELEGATION,
        origin=DispatchOrigin("test", "process_id", "1234"),
        authorization=reference,
        policy_snapshot_sha256="d" * 64,
        provider_tier_binding_digest=provider_tier_binding_digest,
    )


class DispatcherLeaseStoreTests(unittest.TestCase):
    def test_admission_passes_exact_tier_binding_to_authority(self) -> None:
        now = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
        binding = "a" * 64
        with d_drive_tempdir() as temp:
            database = temp / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(database, now=Clock(now))
            leases = DispatcherLeaseStore(database, now=Clock(now))
            reference = authorities.issue(
                source_kind="test",
                source_id="tier-authority",
                scope=AuthorityScope(
                    providers=("glm_flash_worker",),
                    planes=("delegation",),
                    provider_tier_binding_digests=(binding,),
                ),
                expires_at=(now + timedelta(days=1)).isoformat(),
            )

            with self.assertRaisesRegex(DispatchAuthorizationError, "scope"):
                AdmissionGate(authorities, leases).admit(
                    context_for(reference, provider_tier_binding_digest="b" * 64),
                    resource_key="provider:glm_flash_worker",
                    provider_id="glm_flash_worker",
                    task_type="delegated_routine",
                )
            self.assertIsNone(leases.read("provider:glm_flash_worker"))

    def test_two_runs_cannot_hold_one_slot(self) -> None:
        now = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
        with d_drive_tempdir() as temp:
            store = DispatcherLeaseStore(temp / "dispatch.sqlite3", now=Clock(now))

            first = store.acquire(
                "provider:glm_flash_worker",
                RUN_ONE,
                ttl_seconds=60,
            )
            with self.assertRaisesRegex(DispatchLeaseError, "held"):
                store.acquire(
                    "provider:glm_flash_worker",
                    RUN_TWO,
                    ttl_seconds=60,
                )

        self.assertGreater(first.fencing_token, 0)

    def test_expired_lease_gets_new_fencing_token(self) -> None:
        start = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
        clock = Clock(start)
        with d_drive_tempdir() as temp:
            store = DispatcherLeaseStore(temp / "dispatch.sqlite3", now=clock)
            first = store.acquire("provider:grok", RUN_ONE, ttl_seconds=10)
            clock.value = start + timedelta(seconds=11)

            second = store.acquire("provider:grok", RUN_TWO, ttl_seconds=10)

        self.assertGreater(second.fencing_token, first.fencing_token)

    def test_wrong_holder_cannot_renew_or_release(self) -> None:
        now = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
        with d_drive_tempdir() as temp:
            store = DispatcherLeaseStore(temp / "dispatch.sqlite3", now=Clock(now))
            permit = store.acquire("provider:grok", RUN_ONE, ttl_seconds=60)

            with self.assertRaisesRegex(DispatchLeaseError, "holder"):
                store.renew(
                    "provider:grok",
                    RUN_TWO,
                    permit.fencing_token,
                    ttl_seconds=60,
                )
            with self.assertRaisesRegex(DispatchLeaseError, "holder"):
                store.release(
                    "provider:grok",
                    RUN_ONE,
                    permit.fencing_token + 1,
                )
            self.assertIsNotNone(store.read("provider:grok"))
            self.assertTrue(
                store.release(
                    "provider:grok",
                    RUN_ONE,
                    permit.fencing_token,
                )
            )
            self.assertIsNone(store.read("provider:grok"))

    def test_admission_rechecks_authority_and_releases_on_revocation(self) -> None:
        now = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
        with d_drive_tempdir() as temp:
            database = temp / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(database, now=Clock(now))
            leases = DispatcherLeaseStore(database, now=Clock(now))
            reference = authorities.issue(
                source_kind="test",
                source_id="authority-1",
                scope=AuthorityScope(
                    providers=("glm_flash_worker",),
                    planes=("delegation",),
                    task_types=("delegated_routine",),
                ),
                expires_at=(now + timedelta(days=1)).isoformat(),
            )
            original_verify = authorities.verify
            calls = 0

            def verify_then_revoke(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    authorities.advance_epoch(reason_digest="e" * 64, state="hold")
                return original_verify(*args, **kwargs)

            with patch.object(authorities, "verify", side_effect=verify_then_revoke):
                with self.assertRaisesRegex(DispatchAuthorizationError, "stale epoch"):
                    AdmissionGate(authorities, leases).admit(
                        context_for(reference),
                        resource_key="provider:glm_flash_worker",
                        provider_id="glm_flash_worker",
                        task_type="delegated_routine",
                    )

            self.assertIsNone(leases.read("provider:glm_flash_worker"))


if __name__ == "__main__":
    unittest.main()
