from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from .contracts import AgentRunHeader, AgentRunState
from .events import AgentEventType
from .ownership import AgentOwnershipPermit, AgentOwnershipStore
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
        self.ownership = AgentOwnershipStore(store, now=now)

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
        permit: AgentOwnershipPermit | None = None,
        event_id: str | None = None,
    ) -> AgentRunProjection:
        payload = {"reason_code": reason_code, "reason_digest": reason_digest}
        if permit is None:
            return self.store._transition_unowned(
                agent_run_id,
                expected_state=AgentRunState.CREATED,
                target_state=AgentRunState.CANCELLED,
                expected_revision=expected_revision,
                expected_epoch=expected_epoch,
                event_type=AgentEventType.CANCELLED,
                payload=payload,
                created_at=self._timestamp(),
                event_id=event_id,
            )
        if permit.agent_run_id != agent_run_id:
            raise ValueError("permit does not belong to AgentRun")
        return self.store._transition_owned(
            permit,
            expected_states=frozenset(
                {
                    AgentRunState.ADMITTED,
                    AgentRunState.ACTIVE,
                    AgentRunState.BLOCKED,
                }
            ),
            target_state=AgentRunState.CANCELLED,
            expected_revision=expected_revision,
            expected_epoch=expected_epoch,
            event_type=AgentEventType.CANCELLED,
            payload=payload,
            created_at=self._timestamp(),
            event_id=event_id,
        )

    def acquire_agent_run(
        self,
        agent_run_id: str,
        owner_id: str,
        *,
        expected_revision: int,
        expected_epoch: int,
        ttl_seconds: int,
        event_id: str | None = None,
    ) -> AgentOwnershipPermit:
        return self.ownership.acquire(
            agent_run_id,
            owner_id,
            expected_revision=expected_revision,
            expected_epoch=expected_epoch,
            ttl_seconds=ttl_seconds,
            event_id=event_id,
        )

    def renew_agent_run(
        self,
        permit: AgentOwnershipPermit,
        *,
        ttl_seconds: int,
    ) -> AgentOwnershipPermit:
        return self.ownership.renew(permit, ttl_seconds=ttl_seconds)

    def release_agent_run(self, permit: AgentOwnershipPermit) -> bool:
        return self.ownership.release(permit)

    def get_agent_ownership(
        self,
        agent_run_id: str,
    ) -> AgentOwnershipPermit | None:
        return self.ownership.read(agent_run_id)

    def activate_agent_run(
        self,
        permit: AgentOwnershipPermit,
        *,
        expected_revision: int,
        expected_epoch: int,
        reason_code: str,
        reason_digest: str,
        event_id: str | None = None,
    ) -> AgentRunProjection:
        return self.store._transition_owned(
            permit,
            expected_states=frozenset(
                {AgentRunState.ADMITTED, AgentRunState.BLOCKED}
            ),
            target_state=AgentRunState.ACTIVE,
            expected_revision=expected_revision,
            expected_epoch=expected_epoch,
            event_type=AgentEventType.RUN_ACTIVATED,
            payload={"reason_code": reason_code, "reason_digest": reason_digest},
            created_at=self._timestamp(),
            event_id=event_id,
        )

    def block_agent_run(
        self,
        permit: AgentOwnershipPermit,
        *,
        expected_revision: int,
        expected_epoch: int,
        reason_code: str,
        reason_digest: str,
        event_id: str | None = None,
    ) -> AgentRunProjection:
        return self.store._transition_owned(
            permit,
            expected_states=frozenset({AgentRunState.ACTIVE}),
            target_state=AgentRunState.BLOCKED,
            expected_revision=expected_revision,
            expected_epoch=expected_epoch,
            event_type=AgentEventType.BLOCKED,
            payload={"reason_code": reason_code, "reason_digest": reason_digest},
            created_at=self._timestamp(),
            event_id=event_id,
        )

    def complete_agent_run(
        self,
        permit: AgentOwnershipPermit,
        *,
        expected_revision: int,
        expected_epoch: int,
        evidence_ref: str,
        evidence_digest: str,
        event_id: str | None = None,
    ) -> AgentRunProjection:
        return self.store._transition_owned(
            permit,
            expected_states=frozenset({AgentRunState.ACTIVE}),
            target_state=AgentRunState.COMPLETED,
            expected_revision=expected_revision,
            expected_epoch=expected_epoch,
            event_type=AgentEventType.COMPLETED,
            payload={
                "evidence_ref": evidence_ref,
                "evidence_digest": evidence_digest,
            },
            created_at=self._timestamp(),
            event_id=event_id,
        )

    def fail_agent_run(
        self,
        permit: AgentOwnershipPermit,
        *,
        expected_revision: int,
        expected_epoch: int,
        reason_code: str,
        reason_digest: str,
        event_id: str | None = None,
    ) -> AgentRunProjection:
        return self.store._transition_owned(
            permit,
            expected_states=frozenset(
                {
                    AgentRunState.ADMITTED,
                    AgentRunState.ACTIVE,
                    AgentRunState.BLOCKED,
                }
            ),
            target_state=AgentRunState.FAILED,
            expected_revision=expected_revision,
            expected_epoch=expected_epoch,
            event_type=AgentEventType.FAILED,
            payload={"reason_code": reason_code, "reason_digest": reason_digest},
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
