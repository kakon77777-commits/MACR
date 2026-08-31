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

    def test_missing_run_failure_is_typed_and_sanitized(self) -> None:
        with d_drive_tempdir() as temp:
            service = AgentStateService(AgentStore(temp / "agent.sqlite3"))
            with self.assertRaises(AgentRunNotFoundError) as caught:
                service.get_agent_run(RUN_ID)

        self.assertEqual(caught.exception.code, "AGENT_RUN_NOT_FOUND")
        self.assertNotIn("D:\\", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
