from __future__ import annotations

import unittest
from datetime import datetime, timezone

from macr_runtime.agent.contracts import AgentRunState
from macr_runtime.agent.errors import (
    AgentRunNotFoundError,
    IllegalAgentRunTransitionError,
    StaleAgentRunEpochError,
    StaleAgentRunRevisionError,
)
from macr_runtime.agent.events import AgentEventType
from macr_runtime.agent.service import AgentStateService
from macr_runtime.agent.store import AgentStore
from tests.support import d_drive_tempdir
from tests.test_agent_state import RUN_ID, make_header


class Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class AgentServiceTests(unittest.TestCase):
    def test_create_then_admit_is_host_named_revision_fenced_flow(self) -> None:
        now = datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc)
        with d_drive_tempdir() as temp:
            service = AgentStateService(
                AgentStore(temp / "agent.sqlite3"),
                now=Clock(now),
            )

            created = service.create_agent_run(make_header())
            admitted = service.admit_agent_run(
                RUN_ID,
                expected_revision=1,
                expected_epoch=0,
                reason_code="INITIAL_ADMISSION",
                reason_digest="a" * 64,
            )
            loaded = service.get_agent_run(RUN_ID)
            events = service.list_agent_events(RUN_ID)

        self.assertEqual(created.state, AgentRunState.CREATED)
        self.assertEqual(admitted.state, AgentRunState.ADMITTED)
        self.assertEqual(admitted.state_revision, 2)
        self.assertEqual(admitted.epoch, 0)
        self.assertEqual(loaded, admitted)
        self.assertEqual(
            tuple(record.event.event_type for record in events),
            (AgentEventType.RUN_CREATED, AgentEventType.RUN_ADMITTED),
        )

    def test_stale_revision_and_epoch_reject_before_event_or_projection_write(self) -> None:
        now = datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc)
        with d_drive_tempdir() as temp:
            service = AgentStateService(
                AgentStore(temp / "agent.sqlite3"),
                now=Clock(now),
            )
            created = service.create_agent_run(make_header())

            with self.assertRaisesRegex(
                StaleAgentRunRevisionError,
                "revision",
            ) as revision_error:
                service.admit_agent_run(
                    RUN_ID,
                    expected_revision=2,
                    expected_epoch=0,
                    reason_code="INITIAL_ADMISSION",
                    reason_digest="a" * 64,
                )
            with self.assertRaisesRegex(
                StaleAgentRunEpochError,
                "epoch",
            ) as epoch_error:
                service.admit_agent_run(
                    RUN_ID,
                    expected_revision=1,
                    expected_epoch=1,
                    reason_code="INITIAL_ADMISSION",
                    reason_digest="a" * 64,
                )

            self.assertEqual(service.get_agent_run(RUN_ID), created)
            self.assertEqual(len(service.list_agent_events(RUN_ID)), 1)

        self.assertEqual(revision_error.exception.code, "STALE_AGENT_RUN_REVISION")
        self.assertEqual(epoch_error.exception.code, "STALE_AGENT_RUN_EPOCH")

    def test_revision_rollback_after_admission_fails_closed(self) -> None:
        now = datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc)
        with d_drive_tempdir() as temp:
            service = AgentStateService(
                AgentStore(temp / "agent.sqlite3"),
                now=Clock(now),
            )
            service.create_agent_run(make_header())
            admitted = service.admit_agent_run(
                RUN_ID,
                expected_revision=1,
                expected_epoch=0,
                reason_code="INITIAL_ADMISSION",
                reason_digest="a" * 64,
            )

            with self.assertRaises(StaleAgentRunRevisionError):
                service.cancel_agent_run(
                    RUN_ID,
                    expected_revision=1,
                    expected_epoch=0,
                    reason_code="OPERATOR_CANCEL",
                    reason_digest="b" * 64,
                )

            self.assertEqual(service.get_agent_run(RUN_ID), admitted)
            self.assertEqual(len(service.list_agent_events(RUN_ID)), 2)

    def test_created_host_cancellation_is_cas_bound_and_terminal(self) -> None:
        now = datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc)
        with d_drive_tempdir() as temp:
            service = AgentStateService(
                AgentStore(temp / "agent.sqlite3"),
                now=Clock(now),
            )
            service.create_agent_run(make_header())

            cancelled = service.cancel_agent_run(
                RUN_ID,
                expected_revision=1,
                expected_epoch=0,
                reason_code="OPERATOR_CANCEL",
                reason_digest="b" * 64,
            )

            self.assertEqual(cancelled.state, AgentRunState.CANCELLED)
            self.assertEqual(cancelled.state_revision, 2)
            with self.assertRaises(IllegalAgentRunTransitionError):
                service.admit_agent_run(
                    RUN_ID,
                    expected_revision=2,
                    expected_epoch=0,
                    reason_code="INITIAL_ADMISSION",
                    reason_digest="a" * 64,
                )

    def test_service_has_no_generic_or_future_phase_mutation_surface(self) -> None:
        with d_drive_tempdir() as temp:
            service = AgentStateService(AgentStore(temp / "agent.sqlite3"))

        for forbidden in (
            "set_state",
            "transition_agent_run",
            "suspend_agent_run",
            "wake_agent_run",
            "resume_agent_run",
            "require_reconciliation",
        ):
            self.assertFalse(hasattr(service, forbidden), forbidden)

    def test_owned_lifecycle_reaches_terminal_and_releases_ownership(self) -> None:
        start = datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc)
        clock = Clock(start)
        with d_drive_tempdir() as temp:
            service = AgentStateService(
                AgentStore(temp / "agent.sqlite3"),
                now=clock,
            )
            service.create_agent_run(make_header())
            service.admit_agent_run(
                RUN_ID,
                expected_revision=1,
                expected_epoch=0,
                reason_code="INITIAL_ADMISSION",
                reason_digest="a" * 64,
            )
            permit = service.acquire_agent_run(
                RUN_ID,
                "owner:one",
                expected_revision=2,
                expected_epoch=0,
                ttl_seconds=300,
            )
            active = service.activate_agent_run(
                permit,
                expected_revision=3,
                expected_epoch=1,
                reason_code="OWNER_READY",
                reason_digest="b" * 64,
            )
            blocked = service.block_agent_run(
                permit,
                expected_revision=4,
                expected_epoch=1,
                reason_code="DEPENDENCY_UNAVAILABLE",
                reason_digest="c" * 64,
            )
            active_again = service.activate_agent_run(
                permit,
                expected_revision=5,
                expected_epoch=1,
                reason_code="DEPENDENCY_READY",
                reason_digest="d" * 64,
            )
            completed = service.complete_agent_run(
                permit,
                expected_revision=6,
                expected_epoch=1,
                evidence_ref="evidence:phase-b-test",
                evidence_digest="e" * 64,
            )
            events = service.list_agent_events(RUN_ID)
            ownership = service.get_agent_ownership(RUN_ID)

        self.assertEqual(active.state, AgentRunState.ACTIVE)
        self.assertEqual(blocked.state, AgentRunState.BLOCKED)
        self.assertEqual(active_again.state, AgentRunState.ACTIVE)
        self.assertEqual(completed.state, AgentRunState.COMPLETED)
        self.assertEqual(completed.state_revision, 7)
        self.assertIsNone(ownership)
        self.assertEqual(
            tuple(record.event.event_type for record in events),
            (
                AgentEventType.RUN_CREATED,
                AgentEventType.RUN_ADMITTED,
                AgentEventType.OWNER_ACQUIRED,
                AgentEventType.RUN_ACTIVATED,
                AgentEventType.BLOCKED,
                AgentEventType.RUN_ACTIVATED,
                AgentEventType.COMPLETED,
            ),
        )

    def test_owned_fail_and_cancel_paths_are_terminal_and_release_ownership(self) -> None:
        start = datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc)
        for terminal in (AgentRunState.FAILED, AgentRunState.CANCELLED):
            with self.subTest(terminal=terminal.value), d_drive_tempdir() as temp:
                service = AgentStateService(
                    AgentStore(temp / "agent.sqlite3"),
                    now=Clock(start),
                )
                service.create_agent_run(make_header())
                service.admit_agent_run(
                    RUN_ID,
                    expected_revision=1,
                    expected_epoch=0,
                    reason_code="INITIAL_ADMISSION",
                    reason_digest="a" * 64,
                )
                permit = service.acquire_agent_run(
                    RUN_ID,
                    "owner:one",
                    expected_revision=2,
                    expected_epoch=0,
                    ttl_seconds=300,
                )
                revision = 3
                if terminal is AgentRunState.CANCELLED:
                    service.activate_agent_run(
                        permit,
                        expected_revision=revision,
                        expected_epoch=1,
                        reason_code="OWNER_READY",
                        reason_digest="b" * 64,
                    )
                    revision += 1
                    result = service.cancel_agent_run(
                        RUN_ID,
                        permit=permit,
                        expected_revision=revision,
                        expected_epoch=1,
                        reason_code="OPERATOR_CANCEL",
                        reason_digest="c" * 64,
                    )
                else:
                    result = service.fail_agent_run(
                        permit,
                        expected_revision=revision,
                        expected_epoch=1,
                        reason_code="HOST_FAILURE",
                        reason_digest="d" * 64,
                    )
                ownership = service.get_agent_ownership(RUN_ID)

            self.assertEqual(result.state, terminal)
            self.assertIsNone(ownership)

    def test_missing_run_failure_is_typed_and_sanitized(self) -> None:
        with d_drive_tempdir() as temp:
            service = AgentStateService(AgentStore(temp / "agent.sqlite3"))
            with self.assertRaises(AgentRunNotFoundError) as caught:
                service.get_agent_run(RUN_ID)

        self.assertEqual(caught.exception.code, "AGENT_RUN_NOT_FOUND")
        self.assertNotIn("D:\\", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
