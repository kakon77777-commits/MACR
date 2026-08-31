from __future__ import annotations

import math
import unittest

from macr_runtime.agent.contracts import AgentRunState
from macr_runtime.agent.errors import AgentEventIntegrityError
from macr_runtime.agent.events import (
    AGENT_EVENT_SCHEMA_VERSION,
    AgentEventType,
    AgentStateEvent,
    apply_agent_event,
)
from macr_runtime.agent.state import AgentRunProjection
from tests.test_agent_state import RUN_ID, make_header


EVENT_ID = "22222222-2222-4222-8222-222222222222"


def event_for(
    event_type: AgentEventType,
    *,
    before_revision: int,
    after_revision: int,
    epoch: int,
    payload: dict[str, object],
    state_digest_after: str = "d" * 64,
    event_id: str = EVENT_ID,
    created_at: str = "2026-08-31T01:00:00+00:00",
) -> AgentStateEvent:
    return AgentStateEvent(
        event_id=event_id,
        agent_run_id=RUN_ID,
        epoch=epoch,
        before_revision=before_revision,
        after_revision=after_revision,
        event_type=event_type,
        payload=payload,
        state_digest_after=state_digest_after,
        created_at=created_at,
    )


class AgentEventTests(unittest.TestCase):
    def test_event_type_set_is_exact(self) -> None:
        self.assertEqual(
            {item.value for item in AgentEventType},
            {
                "agent.run_created",
                "agent.run_admitted",
                "agent.owner_acquired",
                "agent.run_activated",
                "agent.blocked",
                "agent.completed",
                "agent.failed",
                "agent.cancelled",
            },
        )

    def test_creation_event_round_trips_and_applies_from_no_projection(self) -> None:
        projection = AgentRunProjection.from_creation_header(make_header())
        event = event_for(
            AgentEventType.RUN_CREATED,
            before_revision=0,
            after_revision=1,
            epoch=0,
            payload={"initial_header": projection.initial_header.to_public_dict()},
            state_digest_after=projection.state_digest,
            created_at=projection.updated_at,
        )

        public = event.to_public_dict()
        rebuilt = AgentStateEvent.from_dict(public)

        self.assertEqual(rebuilt, event)
        self.assertEqual(public["schema_version"], AGENT_EVENT_SCHEMA_VERSION)
        self.assertRegex(event.payload_digest, r"^[0-9a-f]{64}$")
        self.assertEqual(apply_agent_event(None, event), projection)

    def test_admission_owner_and_activation_reducer_is_exact(self) -> None:
        created = AgentRunProjection.from_creation_header(make_header())
        admitted = AgentRunProjection(
            initial_header=created.initial_header,
            state=AgentRunState.ADMITTED,
            state_revision=2,
            epoch=0,
            updated_at="2026-08-31T01:00:00+00:00",
        )
        admitted_event = event_for(
            AgentEventType.RUN_ADMITTED,
            before_revision=1,
            after_revision=2,
            epoch=0,
            payload={"reason_code": "INITIAL_ADMISSION", "reason_digest": "a" * 64},
            state_digest_after=admitted.state_digest,
        )
        self.assertEqual(apply_agent_event(created, admitted_event), admitted)

        owned = AgentRunProjection(
            initial_header=created.initial_header,
            state=AgentRunState.ADMITTED,
            state_revision=3,
            epoch=1,
            updated_at="2026-08-31T01:01:00+00:00",
        )
        owner_event = event_for(
            AgentEventType.OWNER_ACQUIRED,
            before_revision=2,
            after_revision=3,
            epoch=1,
            payload={
                "owner_id": "owner:one",
                "lease_id": "33333333-3333-4333-8333-333333333333",
                "fencing_token": 1,
                "expires_at": "2026-08-31T01:06:00+00:00",
            },
            state_digest_after=owned.state_digest,
            event_id="44444444-4444-4444-8444-444444444444",
            created_at="2026-08-31T01:01:00+00:00",
        )
        self.assertEqual(apply_agent_event(admitted, owner_event), owned)

        active = AgentRunProjection(
            initial_header=created.initial_header,
            state=AgentRunState.ACTIVE,
            state_revision=4,
            epoch=1,
            updated_at="2026-08-31T01:02:00+00:00",
        )
        active_event = event_for(
            AgentEventType.RUN_ACTIVATED,
            before_revision=3,
            after_revision=4,
            epoch=1,
            payload={"reason_code": "OWNER_READY", "reason_digest": "b" * 64},
            state_digest_after=active.state_digest,
            event_id="55555555-5555-4555-8555-555555555555",
            created_at="2026-08-31T01:02:00+00:00",
        )
        self.assertEqual(apply_agent_event(owned, active_event), active)

    def test_revision_shape_and_canonical_ids_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "after_revision"):
            event_for(
                AgentEventType.RUN_ADMITTED,
                before_revision=1,
                after_revision=3,
                epoch=0,
                payload={"reason_code": "ADMIT", "reason_digest": "a" * 64},
            )
        with self.assertRaisesRegex(ValueError, "UUIDv4"):
            event_for(
                AgentEventType.RUN_ADMITTED,
                before_revision=1,
                after_revision=2,
                epoch=0,
                payload={"reason_code": "ADMIT", "reason_digest": "a" * 64},
                event_id="not-a-uuid",
            )

    def test_payload_allowlist_types_bounds_and_privacy_fail_closed(self) -> None:
        base = {
            "reason_code": "ADMIT",
            "reason_digest": "a" * 64,
        }
        invalid_payloads = (
            {**base, "prompt": "secret"},
            {"reason_code": r"D:\secret\task.txt", "reason_digest": "a" * 64},
            {"reason_code": "sk-abcdefgh12345678", "reason_digest": "a" * 64},
            {"reason_code": b"bytes", "reason_digest": "a" * 64},
            {"reason_code": "x" * 129, "reason_digest": "a" * 64},
            {"reason_code": "ADMIT", "reason_digest": "not-a-digest"},
        )
        for payload in invalid_payloads:
            with self.subTest(payload=repr(payload)):
                with self.assertRaises(ValueError):
                    event_for(
                        AgentEventType.RUN_ADMITTED,
                        before_revision=1,
                        after_revision=2,
                        epoch=0,
                        payload=payload,
                    )

        for token in (True, math.nan):
            with self.subTest(token=token):
                with self.assertRaises(ValueError):
                    event_for(
                        AgentEventType.OWNER_ACQUIRED,
                        before_revision=2,
                        after_revision=3,
                        epoch=1,
                        payload={
                            "owner_id": "owner:one",
                            "lease_id": "33333333-3333-4333-8333-333333333333",
                            "fencing_token": token,
                            "expires_at": "2026-08-31T01:06:00+00:00",
                        },
                    )

    def test_https_model_and_reference_metadata_are_valid_controls(self) -> None:
        event = event_for(
            AgentEventType.RUN_ADMITTED,
            before_revision=1,
            after_revision=2,
            epoch=0,
            payload={
                "reason_code": "https://example.invalid/model:grok-4.6",
                "reason_digest": "a" * 64,
            },
        )

        self.assertEqual(
            event.payload["reason_code"],
            "https://example.invalid/model:grok-4.6",
        )

    def test_reducer_rejects_wrong_run_revision_epoch_and_state_digest(self) -> None:
        current = AgentRunProjection.from_creation_header(make_header())
        admitted = AgentRunProjection(
            initial_header=current.initial_header,
            state=AgentRunState.ADMITTED,
            state_revision=2,
            epoch=0,
            updated_at="2026-08-31T01:00:00+00:00",
        )
        valid_payload = {"reason_code": "ADMIT", "reason_digest": "a" * 64}
        cases = (
            AgentStateEvent(
                event_id=EVENT_ID,
                agent_run_id="66666666-6666-4666-8666-666666666666",
                epoch=0,
                before_revision=1,
                after_revision=2,
                event_type=AgentEventType.RUN_ADMITTED,
                payload=valid_payload,
                state_digest_after=admitted.state_digest,
                created_at="2026-08-31T01:00:00+00:00",
            ),
            event_for(
                AgentEventType.RUN_ADMITTED,
                before_revision=2,
                after_revision=3,
                epoch=0,
                payload=valid_payload,
                state_digest_after=admitted.state_digest,
            ),
            event_for(
                AgentEventType.RUN_ADMITTED,
                before_revision=1,
                after_revision=2,
                epoch=1,
                payload=valid_payload,
                state_digest_after=admitted.state_digest,
            ),
            event_for(
                AgentEventType.RUN_ADMITTED,
                before_revision=1,
                after_revision=2,
                epoch=0,
                payload=valid_payload,
                state_digest_after="e" * 64,
            ),
        )

        for event in cases:
            with self.subTest(event=event.to_public_dict()):
                with self.assertRaises(AgentEventIntegrityError):
                    apply_agent_event(current, event)


if __name__ == "__main__":
    unittest.main()
