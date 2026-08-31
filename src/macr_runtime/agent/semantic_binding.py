from __future__ import annotations

import sqlite3

from .._v07_contracts import require_non_negative_int, require_positive_int
from .contracts import SemanticStateBinding
from .errors import (
    AgentProjectionConflictError,
    AgentRunNotFoundError,
    StaleAgentRunEpochError,
    StaleAgentRunRevisionError,
)
from .events import AgentEventType, AgentStateEvent, apply_agent_event
from .state import AgentRunProjection
from .store import AgentStore


class AgentSemanticBindingPort:
    """Connection-bound Agent half of a Phase C semantic transaction."""

    def __init__(self, store: AgentStore) -> None:
        if not isinstance(store, AgentStore):
            raise ValueError("store must be an AgentStore")
        self.store = store

    def build_event(
        self,
        *,
        current: AgentRunProjection,
        previous_binding: SemanticStateBinding | None,
        new_binding: SemanticStateBinding,
        operation_kind: str,
        operation_id: str,
        proposal_digest: str | None,
        patch_digest: str | None,
        registry_digest: str,
        authorization_digest: str,
        created_at: str,
        event_id: str,
    ) -> tuple[AgentStateEvent, AgentRunProjection]:
        if not isinstance(current, AgentRunProjection):
            raise ValueError("current must be an AgentRunProjection")
        if previous_binding is not None and not isinstance(
            previous_binding, SemanticStateBinding
        ):
            raise ValueError("previous_binding must be SemanticStateBinding or None")
        if not isinstance(new_binding, SemanticStateBinding):
            raise ValueError("new_binding must be a SemanticStateBinding")
        next_projection = AgentRunProjection(
            initial_header=current.initial_header,
            state=current.state,
            state_revision=current.state_revision + 1,
            epoch=current.epoch,
            updated_at=created_at,
        )
        event = AgentStateEvent(
            event_id=event_id,
            agent_run_id=current.agent_run_id,
            epoch=current.epoch,
            before_revision=current.state_revision,
            after_revision=next_projection.state_revision,
            event_type=AgentEventType.SEMANTIC_STATE_ADVANCED,
            payload={
                "operation_kind": operation_kind,
                "operation_id": operation_id,
                "previous_binding": (
                    None
                    if previous_binding is None
                    else previous_binding.to_public_dict()
                ),
                "new_binding": new_binding.to_public_dict(),
                "proposal_digest": proposal_digest,
                "patch_digest": patch_digest,
                "registry_digest": registry_digest,
                "authorization_digest": authorization_digest,
            },
            state_digest_after=next_projection.state_digest,
            created_at=created_at,
        )
        if apply_agent_event(current, event) != next_projection:
            raise AgentProjectionConflictError(
                "semantic binding event does not produce Agent projection"
            )
        return event, next_projection

    def commit_on_connection(
        self,
        connection: sqlite3.Connection,
        *,
        current: AgentRunProjection,
        event: AgentStateEvent,
        new_binding: SemanticStateBinding,
        expected_revision: int,
        expected_epoch: int,
    ) -> AgentRunProjection:
        if not isinstance(connection, sqlite3.Connection):
            raise ValueError("connection must be a sqlite3.Connection")
        if not isinstance(current, AgentRunProjection):
            raise ValueError("current must be an AgentRunProjection")
        if not isinstance(event, AgentStateEvent) or (
            event.event_type is not AgentEventType.SEMANTIC_STATE_ADVANCED
        ):
            raise ValueError("event must be a semantic-state AgentStateEvent")
        if not isinstance(new_binding, SemanticStateBinding):
            raise ValueError("new_binding must be a SemanticStateBinding")
        selected_revision = require_positive_int(
            "expected_revision", expected_revision
        )
        selected_epoch = require_non_negative_int("expected_epoch", expected_epoch)
        row = connection.execute(
            "SELECT * FROM agent_runs WHERE agent_run_id = ?",
            (current.agent_run_id,),
        ).fetchone()
        if row is None:
            raise AgentRunNotFoundError("AgentRun was not found")
        observed = self.store._projection_from_row(row)
        self.store._require_matching_tail(connection, observed)
        if observed != current or observed.state_revision != selected_revision:
            raise StaleAgentRunRevisionError("AgentRun revision is stale")
        if observed.epoch != selected_epoch:
            raise StaleAgentRunEpochError("AgentRun epoch is stale")
        previous = self.store._semantic_binding_from_row(row)
        event_previous = event.payload["previous_binding"]
        supplied_previous = (
            None
            if event_previous is None
            else SemanticStateBinding.from_dict(event_previous)
        )
        if supplied_previous != previous:
            raise AgentProjectionConflictError(
                "semantic binding event previous binding conflicts"
            )
        event_new = SemanticStateBinding.from_dict(event.payload["new_binding"])
        if event_new != new_binding:
            raise AgentProjectionConflictError(
                "semantic binding event new binding conflicts"
            )
        next_projection = apply_agent_event(current, event)
        self.store._insert_event(connection, event)
        cursor = connection.execute(
            """
            UPDATE agent_runs
            SET state_revision = ?, state_digest = ?, updated_at = ?,
                semantic_state_ref = ?, semantic_state_digest = ?,
                semantic_state_revision = ?
            WHERE agent_run_id = ? AND state_revision = ? AND epoch = ?
            """,
            (
                next_projection.state_revision,
                next_projection.state_digest,
                next_projection.updated_at,
                new_binding.ref,
                new_binding.digest,
                new_binding.revision,
                current.agent_run_id,
                selected_revision,
                selected_epoch,
            ),
        )
        if cursor.rowcount != 1:
            raise AgentProjectionConflictError(
                "semantic binding Agent compare-and-swap failed"
            )
        return next_projection
