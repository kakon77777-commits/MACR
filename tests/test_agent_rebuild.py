from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from macr_runtime.agent.contracts import AgentRunState
from macr_runtime.agent.errors import (
    AgentEventIntegrityError,
    AgentRebuildBlockedError,
)
from macr_runtime.agent.events import (
    AgentEventType,
    AgentStateEvent,
    replay_agent_events,
)
from macr_runtime.agent.service import AgentStateService
from macr_runtime.agent.state import AgentRunProjection
from macr_runtime.agent.store import (
    AgentStore,
    ProjectionInspectionStatus,
)
from macr_runtime.canonical import canonical_json_bytes
from tests.support import d_drive_tempdir
from tests.test_agent_service import Clock
from tests.test_agent_state import RUN_ID, make_header


def completed_service(temp) -> tuple[AgentStateService, object]:
    clock = Clock(datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc))
    service = AgentStateService(AgentStore(temp / "agent.sqlite3"), now=clock)
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
    service.activate_agent_run(
        permit,
        expected_revision=3,
        expected_epoch=1,
        reason_code="OWNER_READY",
        reason_digest="b" * 64,
    )
    completed = service.complete_agent_run(
        permit,
        expected_revision=4,
        expected_epoch=1,
        evidence_ref="evidence:phase-b",
        evidence_digest="c" * 64,
    )
    return service, completed


class AgentRebuildTests(unittest.TestCase):
    def test_inspection_is_read_only_and_reports_exact_match(self) -> None:
        with d_drive_tempdir() as temp:
            service, completed = completed_service(temp)
            before = service.list_agent_events(RUN_ID)

            inspection = service.store.inspect_projection(RUN_ID)

            after = service.list_agent_events(RUN_ID)

        self.assertEqual(inspection.status, ProjectionInspectionStatus.EXACT_MATCH)
        self.assertEqual(inspection.event_count, 5)
        self.assertEqual(inspection.replay_state_digest, completed.state_digest)
        self.assertEqual(inspection.projection_state_digest, completed.state_digest)
        self.assertEqual(before, after)

    def test_projection_deletion_rebuilds_byte_equivalent_state_and_indexes(self) -> None:
        with d_drive_tempdir() as temp:
            service, completed = completed_service(temp)
            expected_bytes = canonical_json_bytes(completed.to_public_dict())
            expected_events = service.list_agent_events(RUN_ID)
            connection = service.store.database.connect()
            try:
                connection.execute(
                    "DELETE FROM agent_runs WHERE agent_run_id = ?",
                    (RUN_ID,),
                )
            finally:
                connection.close()

            missing = service.store.inspect_projection(RUN_ID)
            rebuilt = service.store.rebuild_projection(RUN_ID)
            exact = service.store.inspect_projection(RUN_ID)
            rebuilt_events = service.list_agent_events(RUN_ID)
            connection = service.store.database.connect()
            try:
                goal_count = connection.execute(
                    "SELECT COUNT(*) FROM agent_goals WHERE agent_run_id = ?",
                    (RUN_ID,),
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(missing.status, ProjectionInspectionStatus.MISSING)
        self.assertEqual(canonical_json_bytes(rebuilt.to_public_dict()), expected_bytes)
        self.assertEqual(rebuilt.state_digest, completed.state_digest)
        self.assertEqual(exact.status, ProjectionInspectionStatus.EXACT_MATCH)
        self.assertEqual(rebuilt_events, expected_events)
        self.assertEqual(goal_count, 1)

    def test_active_lease_blocks_rebuild_even_when_projection_matches(self) -> None:
        clock = Clock(datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc))
        with d_drive_tempdir() as temp:
            service = AgentStateService(AgentStore(temp / "agent.sqlite3"), now=clock)
            service.create_agent_run(make_header())
            service.admit_agent_run(
                RUN_ID,
                expected_revision=1,
                expected_epoch=0,
                reason_code="INITIAL_ADMISSION",
                reason_digest="a" * 64,
            )
            service.acquire_agent_run(
                RUN_ID,
                "owner:one",
                expected_revision=2,
                expected_epoch=0,
                ttl_seconds=300,
            )

            with self.assertRaisesRegex(AgentRebuildBlockedError, "lease"):
                service.store.rebuild_projection(
                    RUN_ID,
                    observed_at=clock.value.isoformat(),
                )

    def test_event_gap_and_payload_digest_tamper_are_integrity_failures(self) -> None:
        for mutation in ("gap", "payload_digest"):
            with self.subTest(mutation=mutation), d_drive_tempdir() as temp:
                service, _ = completed_service(temp)
                connection = service.store.database.connect()
                try:
                    if mutation == "gap":
                        connection.execute(
                            "DELETE FROM agent_events "
                            "WHERE agent_run_id = ? AND after_revision = 2",
                            (RUN_ID,),
                        )
                    else:
                        connection.execute(
                            "UPDATE agent_events SET payload_digest = ? "
                            "WHERE agent_run_id = ? AND after_revision = 2",
                            ("f" * 64, RUN_ID),
                        )
                finally:
                    connection.close()

                with self.assertRaises(AgentEventIntegrityError):
                    service.store.inspect_projection(RUN_ID)

    def test_projection_tamper_reports_conflict_without_repair(self) -> None:
        with d_drive_tempdir() as temp:
            service, completed = completed_service(temp)
            connection = service.store.database.connect()
            try:
                connection.execute(
                    "UPDATE agent_runs SET state_digest = ? WHERE agent_run_id = ?",
                    ("9" * 64, RUN_ID),
                )
            finally:
                connection.close()

            inspection = service.store.inspect_projection(RUN_ID)
            connection = service.store.database.connect()
            try:
                retained = connection.execute(
                    "SELECT state_digest FROM agent_runs WHERE agent_run_id = ?",
                    (RUN_ID,),
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(inspection.status, ProjectionInspectionStatus.CONFLICT)
        self.assertEqual(inspection.replay_state_digest, completed.state_digest)
        self.assertEqual(retained, "9" * 64)

    def test_binding_index_tamper_reports_conflict_with_same_row_count(self) -> None:
        with d_drive_tempdir() as temp:
            service, _ = completed_service(temp)
            connection = service.store.database.connect()
            try:
                connection.execute(
                    "UPDATE agent_goals SET goal_digest = ? WHERE agent_run_id = ?",
                    ("9" * 64, RUN_ID),
                )
            finally:
                connection.close()

            inspection = service.store.inspect_projection(RUN_ID)

        self.assertEqual(inspection.status, ProjectionInspectionStatus.CONFLICT)
        self.assertEqual(inspection.reason_code, "PROJECTION_MISMATCH")

    def test_bad_event_chain_leaves_existing_projection_unchanged_on_rebuild(self) -> None:
        with d_drive_tempdir() as temp:
            service, completed = completed_service(temp)
            connection = service.store.database.connect()
            try:
                connection.execute(
                    "UPDATE agent_events SET state_digest_after = ? "
                    "WHERE agent_run_id = ? AND after_revision = 2",
                    ("8" * 64, RUN_ID),
                )
            finally:
                connection.close()

            with self.assertRaises(AgentEventIntegrityError):
                service.store.rebuild_projection(RUN_ID)

            connection = service.store.database.connect()
            try:
                retained = connection.execute(
                    "SELECT state_digest FROM agent_runs WHERE agent_run_id = ?",
                    (RUN_ID,),
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(retained, completed.state_digest)

    def test_replay_rejects_duplicate_event_and_terminal_continuation(self) -> None:
        with d_drive_tempdir() as temp:
            service, completed = completed_service(temp)
            events = tuple(record.event for record in service.list_agent_events(RUN_ID))

        with self.assertRaisesRegex(AgentEventIntegrityError, "duplicate"):
            replay_agent_events((*events, events[-1]))

        failed_projection = AgentRunProjection(
            initial_header=completed.initial_header,
            state=AgentRunState.FAILED,
            state_revision=completed.state_revision + 1,
            epoch=completed.epoch,
            updated_at="2026-08-31T02:00:00+00:00",
        )
        late = AgentStateEvent(
            event_id="77777777-7777-4777-8777-777777777777",
            agent_run_id=RUN_ID,
            epoch=completed.epoch,
            before_revision=completed.state_revision,
            after_revision=completed.state_revision + 1,
            event_type=AgentEventType.FAILED,
            payload={"reason_code": "LATE_FAILURE", "reason_digest": "d" * 64},
            state_digest_after=failed_projection.state_digest,
            created_at="2026-08-31T02:00:00+00:00",
        )
        with self.assertRaisesRegex(AgentEventIntegrityError, "transition"):
            replay_agent_events((*events, late))

    def test_changed_immutable_header_is_projection_conflict(self) -> None:
        with d_drive_tempdir() as temp:
            service, completed = completed_service(temp)
            public = completed.initial_header.to_public_dict()
            public["agent_ref"] = "agent:tampered"
            connection = service.store.database.connect()
            try:
                connection.execute(
                    "UPDATE agent_runs SET initial_header_json = ? "
                    "WHERE agent_run_id = ?",
                    (json.dumps(public, sort_keys=True), RUN_ID),
                )
            finally:
                connection.close()

            inspection = service.store.inspect_projection(RUN_ID)

        self.assertEqual(inspection.status, ProjectionInspectionStatus.CONFLICT)


if __name__ == "__main__":
    unittest.main()
