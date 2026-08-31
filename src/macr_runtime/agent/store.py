from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .._v07_contracts import require_positive_int, require_uuid4
from ..canonical import canonical_json_bytes
from .contracts import AgentRunHeader, AgentRunState
from .database import AgentDatabase
from .errors import (
    AgentProjectionConflictError,
    AgentRunAlreadyExistsError,
    AgentRunNotFoundError,
)
from .events import AgentEventType, AgentStateEvent
from .state import AgentRunProjection


FaultInjector = Callable[[str], None]


@dataclass(frozen=True)
class AgentEventRecord:
    sequence: int
    event: AgentStateEvent


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(name: str, text: object) -> dict[str, object]:
    if not isinstance(text, str):
        raise AgentProjectionConflictError(f"{name} is not canonical JSON text")
    try:
        value = json.loads(text, object_pairs_hook=_strict_object)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AgentProjectionConflictError(f"{name} is invalid") from exc
    if not isinstance(value, dict):
        raise AgentProjectionConflictError(f"{name} must be an object")
    return value


def _json_text(value: object) -> str:
    return canonical_json_bytes(value).decode("utf-8")


class AgentStore:
    def __init__(
        self,
        path: str | Path,
        *,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        self.database = AgentDatabase(path)
        self._fault_injector = fault_injector

    def _fault(self, marker: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(marker)

    def create_agent_run(
        self,
        header: AgentRunHeader,
        *,
        event_id: str | None = None,
    ) -> AgentRunProjection:
        projection = AgentRunProjection.from_creation_header(header)
        selected_event_id = str(uuid.uuid4()) if event_id is None else event_id
        event = AgentStateEvent(
            event_id=selected_event_id,
            agent_run_id=projection.agent_run_id,
            epoch=0,
            before_revision=0,
            after_revision=1,
            event_type=AgentEventType.RUN_CREATED,
            payload={"initial_header": header.to_public_dict()},
            state_digest_after=projection.state_digest,
            created_at=header.created_at,
        )

        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT 1 FROM agent_runs WHERE agent_run_id = ?",
                (projection.agent_run_id,),
            ).fetchone()
            if existing is not None:
                raise AgentRunAlreadyExistsError("AgentRun already exists")

            self._fault("before_event_insert")
            self._insert_event(connection, event)
            self._fault("after_event_insert")
            self._insert_projection(connection, projection)
            self._insert_bindings(connection, header)
            self._fault("after_projection_update")
            self._fault("before_commit")
            connection.commit()
            return projection
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _insert_event(
        connection: sqlite3.Connection,
        event: AgentStateEvent,
    ) -> None:
        connection.execute(
            """
            INSERT INTO agent_events(
                event_id, agent_run_id, epoch, before_revision,
                after_revision, event_type, payload_json, payload_digest,
                state_digest_after, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.agent_run_id,
                event.epoch,
                event.before_revision,
                event.after_revision,
                event.event_type.value,
                _json_text(event.to_public_dict()["payload"]),
                event.payload_digest,
                event.state_digest_after,
                event.created_at,
            ),
        )

    @staticmethod
    def _insert_projection(
        connection: sqlite3.Connection,
        projection: AgentRunProjection,
    ) -> None:
        header = projection.initial_header
        connection.execute(
            """
            INSERT INTO agent_runs(
                agent_run_id, subject_digest, agent_ref,
                initial_header_json, state, state_revision, epoch,
                goal_ref, authority_ref, budget_ref, semantic_state_ref,
                active_plan_ref, latest_checkpoint_ref, parent_agent_run_id,
                delegation_ref, state_digest, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                projection.agent_run_id,
                projection.subject_digest,
                header.agent_ref,
                _json_text(header.to_public_dict()),
                projection.state.value,
                projection.state_revision,
                projection.epoch,
                header.goal.ref,
                header.authority.reference.source_id,
                header.budget.ref,
                None if header.semantic_state is None else header.semantic_state.ref,
                None if header.active_plan is None else header.active_plan.ref,
                None,
                header.parent_agent_run_id,
                header.delegation_ref,
                projection.state_digest,
                header.created_at,
                projection.updated_at,
            ),
        )

    @staticmethod
    def _insert_bindings(
        connection: sqlite3.Connection,
        header: AgentRunHeader,
    ) -> None:
        run_id = header.identity.agent_run_id
        connection.execute(
            """
            INSERT INTO agent_goals(
                agent_run_id, goal_ref, goal_digest, goal_revision,
                binding_digest
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                run_id,
                header.goal.ref,
                header.goal.digest,
                header.goal.revision,
                header.goal.binding_digest,
            ),
        )
        for binding in header.world_bindings:
            connection.execute(
                """
                INSERT INTO agent_world_bindings(
                    agent_run_id, world_ref, world_digest, world_revision,
                    binding_digest
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    binding.ref,
                    binding.digest,
                    binding.revision,
                    binding.binding_digest,
                ),
            )
        for binding in header.memory_bindings:
            connection.execute(
                """
                INSERT INTO agent_memory_bindings(
                    agent_run_id, memory_system_id, profile_id, subject_ref,
                    head_ref, head_digest, access_policy_ref,
                    projection_policy_ref, binding_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    binding.memory_system_id,
                    binding.profile_id,
                    binding.subject_ref,
                    binding.head_ref,
                    binding.head_digest,
                    binding.access_policy_ref,
                    binding.projection_policy_ref,
                    binding.binding_digest,
                ),
            )
        if header.active_plan is not None:
            connection.execute(
                """
                INSERT INTO agent_plan_bindings(
                    agent_run_id, plan_ref, plan_digest, plan_revision,
                    binding_digest
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    header.active_plan.ref,
                    header.active_plan.digest,
                    header.active_plan.revision,
                    header.active_plan.binding_digest,
                ),
            )
        if header.parent_agent_run_id is not None:
            connection.execute(
                """
                INSERT INTO agent_children(
                    parent_agent_run_id, child_agent_run_id, delegation_ref
                ) VALUES (?, ?, ?)
                """,
                (
                    header.parent_agent_run_id,
                    run_id,
                    header.delegation_ref,
                ),
            )

    def get_agent_run(self, agent_run_id: str) -> AgentRunProjection:
        run_id = require_uuid4("agent_run_id", agent_run_id)
        connection = self.database.connect()
        try:
            row = connection.execute(
                "SELECT * FROM agent_runs WHERE agent_run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise AgentRunNotFoundError("AgentRun was not found")
            projection = self._projection_from_row(row)
            tail = connection.execute(
                """
                SELECT after_revision, epoch, state_digest_after
                FROM agent_events
                WHERE agent_run_id = ?
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        finally:
            connection.close()
        if tail is None:
            raise AgentProjectionConflictError("Agent projection has no event tail")
        if (
            tail["after_revision"] != projection.state_revision
            or tail["epoch"] != projection.epoch
            or tail["state_digest_after"] != projection.state_digest
        ):
            raise AgentProjectionConflictError(
                "Agent projection does not match its event tail"
            )
        return projection

    @staticmethod
    def _projection_from_row(row: sqlite3.Row) -> AgentRunProjection:
        try:
            header = AgentRunHeader.from_dict(
                _load_json("initial Agent header", row["initial_header_json"])
            )
            projection = AgentRunProjection(
                initial_header=header,
                state=AgentRunState(row["state"]),
                state_revision=row["state_revision"],
                epoch=row["epoch"],
                updated_at=row["updated_at"],
            )
        except AgentProjectionConflictError:
            raise
        except Exception as exc:
            raise AgentProjectionConflictError("Agent projection is invalid") from exc
        if projection.agent_run_id != row["agent_run_id"]:
            raise AgentProjectionConflictError("Agent projection identity is invalid")
        if projection.subject_digest != row["subject_digest"]:
            raise AgentProjectionConflictError("Agent projection subject is invalid")
        if projection.state_digest != row["state_digest"]:
            raise AgentProjectionConflictError("Agent projection digest is invalid")
        return projection

    def list_agent_runs(
        self,
        *,
        state: AgentRunState | None = None,
        limit: int = 100,
        after_run_id: str | None = None,
    ) -> tuple[AgentRunProjection, ...]:
        selected_limit = require_positive_int("limit", limit)
        if selected_limit > 1000:
            raise ValueError("limit must not exceed 1000")
        if state is not None and not isinstance(state, AgentRunState):
            raise ValueError("state must be an AgentRunState or None")
        cursor = (
            None
            if after_run_id is None
            else require_uuid4("after_run_id", after_run_id)
        )
        clauses: list[str] = []
        values: list[object] = []
        if state is not None:
            clauses.append("state = ?")
            values.append(state.value)
        if cursor is not None:
            clauses.append("agent_run_id > ?")
            values.append(cursor)
        where = "" if not clauses else "WHERE " + " AND ".join(clauses)
        connection = self.database.connect()
        try:
            rows = connection.execute(
                f"SELECT agent_run_id FROM agent_runs {where} "
                "ORDER BY agent_run_id LIMIT ?",
                (*values, selected_limit),
            ).fetchall()
        finally:
            connection.close()
        return tuple(self.get_agent_run(row["agent_run_id"]) for row in rows)

    def list_agent_events(
        self,
        agent_run_id: str,
        *,
        limit: int = 100,
        after_sequence: int | None = None,
    ) -> tuple[AgentEventRecord, ...]:
        run_id = require_uuid4("agent_run_id", agent_run_id)
        selected_limit = require_positive_int("limit", limit)
        if selected_limit > 1000:
            raise ValueError("limit must not exceed 1000")
        cursor = 0
        if after_sequence is not None:
            cursor = require_positive_int("after_sequence", after_sequence)
        connection = self.database.connect()
        try:
            exists = connection.execute(
                "SELECT 1 FROM agent_runs WHERE agent_run_id = ?",
                (run_id,),
            ).fetchone()
            if exists is None:
                raise AgentRunNotFoundError("AgentRun was not found")
            rows = connection.execute(
                """
                SELECT * FROM agent_events
                WHERE agent_run_id = ? AND sequence > ?
                ORDER BY sequence
                LIMIT ?
                """,
                (run_id, cursor, selected_limit),
            ).fetchall()
        finally:
            connection.close()
        records: list[AgentEventRecord] = []
        for row in rows:
            try:
                event = AgentStateEvent.from_dict(
                    {
                        "schema_version": "macr-agent-event/v1",
                        "event_id": row["event_id"],
                        "agent_run_id": row["agent_run_id"],
                        "epoch": row["epoch"],
                        "before_revision": row["before_revision"],
                        "after_revision": row["after_revision"],
                        "event_type": row["event_type"],
                        "payload": _load_json(
                            "Agent event payload",
                            row["payload_json"],
                        ),
                        "payload_digest": row["payload_digest"],
                        "state_digest_after": row["state_digest_after"],
                        "created_at": row["created_at"],
                    }
                )
            except AgentProjectionConflictError:
                raise
            except Exception as exc:
                raise AgentProjectionConflictError("Agent event row is invalid") from exc
            records.append(AgentEventRecord(row["sequence"], event))
        return tuple(records)
