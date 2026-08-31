from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from .contracts import AgentRunHeader, AgentRunState
from .events import AgentEventType
from .state import AgentRunProjection
from .store import AgentEventRecord, AgentStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentStateService:
    """Host/runtime-facing Phase B state operations without an Agent loop."""

    def __init__(
        self,
        store: AgentStore,
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not isinstance(store, AgentStore):
            raise ValueError("store must be an AgentStore")
        self.store = store
        self._now = now

    def _timestamp(self) -> str:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("Agent service clock must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()

    def create_agent_run(
        self,
        header: AgentRunHeader,
        *,
        event_id: str | None = None,
    ) -> AgentRunProjection:
        return self.store.create_agent_run(header, event_id=event_id)

    def admit_agent_run(
        self,
        agent_run_id: str,
        *,
        expected_revision: int,
        expected_epoch: int,
        reason_code: str,
        reason_digest: str,
        event_id: str | None = None,
    ) -> AgentRunProjection:
        return self.store._transition_unowned(
            agent_run_id,
            expected_state=AgentRunState.CREATED,
            target_state=AgentRunState.ADMITTED,
            expected_revision=expected_revision,
            expected_epoch=expected_epoch,
            event_type=AgentEventType.RUN_ADMITTED,
            payload={
                "reason_code": reason_code,
                "reason_digest": reason_digest,
            },
            created_at=self._timestamp(),
            event_id=event_id,
        )

    def cancel_agent_run(
        self,
        agent_run_id: str,
        *,
        expected_revision: int,
        expected_epoch: int,
        reason_code: str,
        reason_digest: str,
        event_id: str | None = None,
    ) -> AgentRunProjection:
        return self.store._transition_unowned(
            agent_run_id,
            expected_state=AgentRunState.CREATED,
            target_state=AgentRunState.CANCELLED,
            expected_revision=expected_revision,
            expected_epoch=expected_epoch,
            event_type=AgentEventType.CANCELLED,
            payload={
                "reason_code": reason_code,
                "reason_digest": reason_digest,
            },
            created_at=self._timestamp(),
            event_id=event_id,
        )

    def get_agent_run(self, agent_run_id: str) -> AgentRunProjection:
        return self.store.get_agent_run(agent_run_id)

    def list_agent_runs(
        self,
        *,
        state: AgentRunState | None = None,
        limit: int = 100,
        after_run_id: str | None = None,
    ) -> tuple[AgentRunProjection, ...]:
        return self.store.list_agent_runs(
            state=state,
            limit=limit,
            after_run_id=after_run_id,
        )

    def list_agent_events(
        self,
        agent_run_id: str,
        *,
        limit: int = 100,
        after_sequence: int | None = None,
    ) -> tuple[AgentEventRecord, ...]:
        return self.store.list_agent_events(
            agent_run_id,
            limit=limit,
            after_sequence=after_sequence,
        )
