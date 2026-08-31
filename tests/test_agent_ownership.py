from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timedelta, timezone

from macr_runtime.agent.contracts import AgentRunState
from macr_runtime.agent.errors import (
    AgentLeaseExpiredError,
    AgentOwnershipConflictError,
    IllegalAgentRunTransitionError,
    StaleAgentFencingTokenError,
    StaleAgentRunEpochError,
    StaleAgentRunRevisionError,
)
from macr_runtime.agent.events import AgentEventType
from macr_runtime.agent.ownership import AgentOwnershipPermit
from macr_runtime.agent.service import AgentStateService
from macr_runtime.agent.store import AgentStore
from tests.support import d_drive_tempdir
from tests.test_agent_service import Clock
from tests.test_agent_state import RUN_ID, make_header


def admitted_service(temp, clock: Clock) -> AgentStateService:
    service = AgentStateService(AgentStore(temp / "agent.sqlite3"), now=clock)
    service.create_agent_run(make_header())
    service.admit_agent_run(
        RUN_ID,
        expected_revision=1,
        expected_epoch=0,
        reason_code="INITIAL_ADMISSION",
        reason_digest="a" * 64,
    )
    return service


class AgentOwnershipTests(unittest.TestCase):
    def test_new_acquire_atomically_advances_epoch_revision_event_token_and_lease(self) -> None:
        start = datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc)
        clock = Clock(start)
        with d_drive_tempdir() as temp:
            service = admitted_service(temp, clock)

            permit = service.acquire_agent_run(
                RUN_ID,
                "owner:one",
                expected_revision=2,
                expected_epoch=0,
                ttl_seconds=300,
            )
            projection = service.get_agent_run(RUN_ID)
            events = service.list_agent_events(RUN_ID)
            stored = service.get_agent_ownership(RUN_ID)

        self.assertEqual(projection.state, AgentRunState.ADMITTED)
        self.assertEqual(projection.state_revision, 3)
        self.assertEqual(projection.epoch, 1)
        self.assertEqual(permit.revision, 3)
        self.assertEqual(permit.epoch, 1)
        self.assertGreater(permit.fencing_token, 0)
        self.assertEqual(stored, permit)
        self.assertEqual(events[-1].event.event_type, AgentEventType.OWNER_ACQUIRED)
        self.assertEqual(events[-1].event.before_revision, 2)
        self.assertEqual(events[-1].event.after_revision, 3)

    def test_exact_same_owner_acquire_is_idempotent_without_drift(self) -> None:
        clock = Clock(datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc))
        with d_drive_tempdir() as temp:
            service = admitted_service(temp, clock)
            first = service.acquire_agent_run(
                RUN_ID,
                "owner:one",
                expected_revision=2,
                expected_epoch=0,
                ttl_seconds=300,
            )

            second = service.acquire_agent_run(
                RUN_ID,
                "owner:one",
                expected_revision=3,
                expected_epoch=1,
                ttl_seconds=300,
            )

            self.assertEqual(second, first)
            self.assertEqual(service.get_agent_run(RUN_ID).state_revision, 3)
            self.assertEqual(len(service.list_agent_events(RUN_ID)), 3)

    def test_competing_owner_refuses_without_event_epoch_revision_or_token_drift(self) -> None:
        clock = Clock(datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc))
        with d_drive_tempdir() as temp:
            service = admitted_service(temp, clock)
            first = service.acquire_agent_run(
                RUN_ID,
                "owner:one",
                expected_revision=2,
                expected_epoch=0,
                ttl_seconds=300,
            )

            with self.assertRaisesRegex(
                AgentOwnershipConflictError,
                "another owner",
            ):
                service.acquire_agent_run(
                    RUN_ID,
                    "owner:two",
                    expected_revision=3,
                    expected_epoch=1,
                    ttl_seconds=300,
                )

            self.assertEqual(service.get_agent_ownership(RUN_ID), first)
            self.assertEqual(service.get_agent_run(RUN_ID).state_revision, 3)
            self.assertEqual(len(service.list_agent_events(RUN_ID)), 3)

    def test_renew_preserves_token_epoch_revision_and_expired_renew_refuses(self) -> None:
        start = datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc)
        clock = Clock(start)
        with d_drive_tempdir() as temp:
            service = admitted_service(temp, clock)
            permit = service.acquire_agent_run(
                RUN_ID,
                "owner:one",
                expected_revision=2,
                expected_epoch=0,
                ttl_seconds=10,
            )
            clock.value = start + timedelta(seconds=5)

            renewed = service.renew_agent_run(permit, ttl_seconds=20)

            self.assertEqual(renewed.fencing_token, permit.fencing_token)
            self.assertEqual(renewed.epoch, permit.epoch)
            self.assertEqual(renewed.revision, permit.revision)
            self.assertGreater(renewed.expires_at, permit.expires_at)

            clock.value = start + timedelta(seconds=26)
            with self.assertRaisesRegex(AgentLeaseExpiredError, "expired"):
                service.renew_agent_run(renewed, ttl_seconds=20)

    def test_release_requires_exact_permit_and_reacquire_creates_new_epoch(self) -> None:
        start = datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc)
        clock = Clock(start)
        with d_drive_tempdir() as temp:
            service = admitted_service(temp, clock)
            first = service.acquire_agent_run(
                RUN_ID,
                "owner:one",
                expected_revision=2,
                expected_epoch=0,
                ttl_seconds=300,
            )

            with self.assertRaises(StaleAgentFencingTokenError):
                service.release_agent_run(
                    dataclasses.replace(
                        first,
                        fencing_token=first.fencing_token + 1,
                    )
                )
            self.assertEqual(service.get_agent_ownership(RUN_ID), first)

            self.assertTrue(service.release_agent_run(first))
            self.assertIsNone(service.get_agent_ownership(RUN_ID))
            second = service.acquire_agent_run(
                RUN_ID,
                "owner:two",
                expected_revision=3,
                expected_epoch=1,
                ttl_seconds=300,
            )

        self.assertGreater(second.fencing_token, first.fencing_token)
        self.assertEqual(second.epoch, 2)
        self.assertEqual(second.revision, 4)

    def test_expiry_reacquire_invalidates_old_epoch_and_fencing_token(self) -> None:
        start = datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc)
        clock = Clock(start)
        with d_drive_tempdir() as temp:
            service = admitted_service(temp, clock)
            first = service.acquire_agent_run(
                RUN_ID,
                "owner:one",
                expected_revision=2,
                expected_epoch=0,
                ttl_seconds=10,
            )
            clock.value = start + timedelta(seconds=11)
            second = service.acquire_agent_run(
                RUN_ID,
                "owner:two",
                expected_revision=3,
                expected_epoch=1,
                ttl_seconds=10,
            )

            with self.assertRaises(StaleAgentRunEpochError):
                service.activate_agent_run(
                    first,
                    expected_revision=4,
                    expected_epoch=1,
                    reason_code="OWNER_READY",
                    reason_digest="b" * 64,
                )
            with self.assertRaises(StaleAgentFencingTokenError):
                service.activate_agent_run(
                    dataclasses.replace(first, epoch=second.epoch),
                    expected_revision=4,
                    expected_epoch=2,
                    reason_code="OWNER_READY",
                    reason_digest="b" * 64,
                )

    def test_acquisition_state_revision_and_epoch_fail_closed(self) -> None:
        clock = Clock(datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc))
        with d_drive_tempdir() as temp:
            raw = AgentStateService(AgentStore(temp / "raw.sqlite3"), now=clock)
            raw.create_agent_run(make_header())
            with self.assertRaises(IllegalAgentRunTransitionError):
                raw.acquire_agent_run(
                    RUN_ID,
                    "owner:one",
                    expected_revision=1,
                    expected_epoch=0,
                    ttl_seconds=10,
                )

            service = admitted_service(temp / "admitted", clock)
            with self.assertRaises(StaleAgentRunRevisionError):
                service.acquire_agent_run(
                    RUN_ID,
                    "owner:one",
                    expected_revision=1,
                    expected_epoch=0,
                    ttl_seconds=10,
                )
            with self.assertRaises(StaleAgentRunEpochError):
                service.acquire_agent_run(
                    RUN_ID,
                    "owner:one",
                    expected_revision=2,
                    expected_epoch=1,
                    ttl_seconds=10,
                )

    def test_permit_is_immutable_and_validates_canonical_shape(self) -> None:
        with self.assertRaisesRegex(ValueError, "UUIDv4"):
            AgentOwnershipPermit(
                agent_run_id=RUN_ID,
                owner_id="owner:one",
                lease_id="not-a-uuid",
                fencing_token=1,
                epoch=1,
                revision=3,
                acquired_at="2026-08-31T01:00:00+00:00",
                expires_at="2026-08-31T01:05:00+00:00",
            )


if __name__ == "__main__":
    unittest.main()
