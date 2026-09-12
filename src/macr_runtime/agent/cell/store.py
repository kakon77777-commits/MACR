from __future__ import annotations

import json
import hashlib
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, Iterable, Protocol

from ..._v07_contracts import (
    canonical_record_digest,
    normalize_timestamp,
    require_non_empty,
    require_non_negative_number,
    require_sha256,
    require_uuid4,
)
from ...action import ActionAdmission, ActionProposal
from ...agent.contracts import AgentRunState
from ...agent.ownership import AgentOwnershipPermit
from ...agent.store import AgentStore
from ...candidate_vault import CandidateCapture
from ...canonical import canonical_json_bytes
from ...semantic.projection import SemanticContextRequest
from ...temporal import AgentCheckpoint
from .blobs import HostedAgentBlobStore
from .contracts import (
    HostedAgentCellPolicy,
    HostedAgentCellState,
    HostedAgentCellStatus,
    HostedBlobRef,
    HostedBlobRole,
    HostedContextKind,
    HostedContextSection,
    HostedModelDecision,
    HostedModelRequest,
    HostedModelResult,
    HostedToolRequest,
    HostedToolResultRef,
    HostedToolResultStatus,
)
from .database import HostedAgentCellSchema
from .errors import (
    HostedAgentCellBudgetError,
    HostedAgentCellStateError,
    HostedAgentCheckpointError,
    HostedAgentReconciliationRequired,
)


class HostedCellAuthorityVerifier(Protocol):
    def verify_cell(
        self,
        reference,
        *,
        agent_run_id: str,
        policy_digest: str,
        operation: str,
    ) -> None: ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_text(value: object) -> str:
    return canonical_json_bytes(value).decode("utf-8")


_ZERO_DIGEST = "0" * 64


class HostedAgentCellStore:
    def __init__(
        self,
        agent_store: AgentStore,
        blobs: HostedAgentBlobStore,
        authority_verifier: HostedCellAuthorityVerifier,
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not isinstance(agent_store, AgentStore):
            raise ValueError("agent_store must be an AgentStore")
        if not isinstance(blobs, HostedAgentBlobStore):
            raise ValueError("blobs must be a HostedAgentBlobStore")
        self.agent_store = agent_store
        self.database = agent_store.database
        self.schema = HostedAgentCellSchema(self.database)
        self.blobs = blobs
        if not callable(getattr(authority_verifier, "verify_cell", None)):
            raise ValueError("authority_verifier must implement verify_cell")
        self.authority_verifier = authority_verifier
        self._now = now

    def _verify_authority(
        self,
        projection,
        *,
        policy_digest: str,
        operation: str,
    ) -> None:
        self.authority_verifier.verify_cell(
            projection.initial_header.authority.reference,
            agent_run_id=projection.agent_run_id,
            policy_digest=policy_digest,
            operation=operation,
        )

    def _timestamp(self) -> str:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("hosted Agent cell clock must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()

    def _verify_permit(
        self,
        connection,
        permit: AgentOwnershipPermit,
        *,
        observed_at: str,
    ):
        if not isinstance(permit, AgentOwnershipPermit):
            raise ValueError("permit must be an AgentOwnershipPermit")
        row = connection.execute(
            "SELECT * FROM agent_runs WHERE agent_run_id=?",
            (permit.agent_run_id,),
        ).fetchone()
        if row is None:
            raise HostedAgentCellStateError("AgentRun does not exist")
        projection = self.agent_store._projection_from_row(row)
        if projection.state is not AgentRunState.ACTIVE:
            raise HostedAgentCellStateError(
                "hosted Agent cell requires ACTIVE AgentRun"
            )
        ownership = connection.execute(
            "SELECT * FROM agent_ownership WHERE agent_run_id=?",
            (permit.agent_run_id,),
        ).fetchone()
        self.agent_store._require_permit_row(
            ownership,
            permit,
            observed_at=observed_at,
        )
        if projection.epoch != permit.epoch:
            raise HostedAgentCellStateError("AgentRun epoch does not match ownership")
        return projection, row

    @staticmethod
    def _state_from_row(row) -> HostedAgentCellState:
        try:
            state = HostedAgentCellState(
                agent_run_id=row["agent_run_id"],
                cell_revision=row["cell_revision"],
                policy_digest=row["policy_digest"],
                semantic_request_digest=row["semantic_request_digest"],
                status=HostedAgentCellStatus(row["status"]),
                next_step=row["next_step"],
                provider_calls=row["provider_calls"],
                tool_calls=row["tool_calls"],
                active_wall_ms=row["active_wall_ms"],
                currency_cost_usd=row["currency_cost_usd"],
                latest_checkpoint_digest=row["latest_checkpoint_digest"],
                candidate_run_id=row["candidate_run_id"],
                final_capture_id=row["final_capture_id"],
                final_answer_digest=row["final_answer_digest"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        except Exception as exc:
            raise HostedAgentCellStateError(
                "hosted Agent cell projection is invalid"
            ) from exc
        if state.state_digest != row["state_digest"]:
            raise HostedAgentCellStateError("hosted Agent cell state digest conflicts")
        return state

    def _cell_row(self, connection, agent_run_id: str):
        run_id = require_uuid4("agent_run_id", agent_run_id)
        row = connection.execute(
            "SELECT * FROM hosted_agent_cells WHERE agent_run_id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise HostedAgentCellStateError("hosted Agent cell does not exist")
        observed = self._state_from_row(row)
        replayed = self._replay_events(connection, run_id)
        if replayed != observed:
            raise HostedAgentCellStateError(
                "hosted Agent cell projection does not match event history"
            )
        self._verify_evidence_tables(connection, run_id)
        return row

    @staticmethod
    def _verify_evidence_tables(connection, agent_run_id: str) -> None:
        events = [
            (row["event_type"], json.loads(row["payload_json"]))
            for row in connection.execute(
                """SELECT event_type, payload_json
                FROM hosted_agent_cell_events WHERE agent_run_id=?
                ORDER BY cell_revision""",
                (agent_run_id,),
            ).fetchall()
        ]

        def payloads(event_type: str) -> list[dict[str, object]]:
            return [payload for kind, payload in events if kind == event_type]

        expected_sections: list[str] = []
        for kind, payload in events:
            if kind == "cell.attached":
                expected_sections.extend(payload["section_digests"])
            elif kind in {
                "cell.context_appended",
                "cell.tool_denied",
                "cell.tool_completed",
            }:
                expected_sections.append(payload["section_digest"])
        observed_sections = [
            row["section_digest"]
            for row in connection.execute(
                """SELECT section_digest FROM hosted_context_sections
                WHERE agent_run_id=? ORDER BY sequence""",
                (agent_run_id,),
            ).fetchall()
        ]
        if observed_sections != expected_sections:
            raise HostedAgentCellStateError(
                "context section evidence does not match cell events"
            )
        attached = payloads("cell.attached")
        cell_row = connection.execute(
            "SELECT * FROM hosted_agent_cells WHERE agent_run_id=?",
            (agent_run_id,),
        ).fetchone()
        if len(attached) != 1 or attached[0] != {
            "policy_digest": cell_row["policy_digest"],
            "semantic_request_digest": cell_row["semantic_request_digest"],
            "section_digests": expected_sections[
                : len(attached[0].get("section_digests", []))
            ],
        }:
            raise HostedAgentCellStateError(
                "cell attachment evidence does not match genesis event"
            )

        model_dispatch = [
            {
                "provider_invocation_id": row["provider_invocation_id"],
                "request_digest": row["request_digest"],
                "context_digest": row["context_digest"],
                "cost_ceiling_usd": json.loads(row["request_json"])["cost_ceiling_usd"],
            }
            for row in connection.execute(
                """SELECT * FROM hosted_model_dispatches
                WHERE agent_run_id=? ORDER BY step_index""",
                (agent_run_id,),
            ).fetchall()
        ]
        if model_dispatch != payloads("cell.model_dispatched"):
            raise HostedAgentCellStateError(
                "model dispatch evidence does not match cell events"
            )
        completed = []
        failed = []
        for row in connection.execute(
            """SELECT d.step_index, t.* FROM hosted_model_dispatches d
            JOIN hosted_model_terminals t USING(provider_invocation_id)
            WHERE d.agent_run_id=? ORDER BY d.step_index""",
            (agent_run_id,),
        ).fetchall():
            if row["terminal_state"] == "completed":
                result = json.loads(row["result_json"])
                completed.append(
                    {
                        "provider_invocation_id": row["provider_invocation_id"],
                        "result_digest": row["result_digest"],
                        "duration_ms": row["duration_ms"],
                        "currency_cost_usd": result["currency_cost_usd"],
                    }
                )
            else:
                failed.append(
                    {
                        "provider_invocation_id": row["provider_invocation_id"],
                        "failure_digest": row["failure_digest"],
                        "duration_ms": row["duration_ms"],
                        "currency_cost_usd": row["currency_cost_usd"],
                        "network_attempted": (
                            None
                            if row["network_attempted"] is None
                            else bool(row["network_attempted"])
                        ),
                        "response_received": (
                            None
                            if row["response_received"] is None
                            else bool(row["response_received"])
                        ),
                        "cell_status": (
                            HostedAgentCellStatus.RECONCILIATION_REQUIRED.value
                            if row["terminal_state"] == "reconciliation_required"
                            else HostedAgentCellStatus.BLOCKED.value
                        ),
                    }
                )
        if completed != payloads("cell.model_completed") or failed != payloads(
            "cell.model_failed"
        ):
            raise HostedAgentCellStateError(
                "model terminal evidence does not match cell events"
            )
        tool_rows = connection.execute(
            """SELECT * FROM hosted_tool_requests WHERE agent_run_id=?
            ORDER BY step_index, action_id""",
            (agent_run_id,),
        ).fetchall()
        admitted = [
            {
                "action_id": row["action_id"],
                "request_digest": row["model_request_digest"],
                "admission_digest": row["admission_digest"],
            }
            for row in tool_rows
            if row["decision"] == "admitted"
        ]
        denied = [row for row in tool_rows if row["decision"] == "denied"]
        denied_payloads = payloads("cell.tool_denied")
        if admitted != payloads("cell.tool_admitted") or len(denied) != len(
            denied_payloads
        ):
            raise HostedAgentCellStateError(
                "tool request evidence does not match cell events"
            )
        for row, payload in zip(denied, denied_payloads):
            if (
                payload["action_id"] != row["action_id"]
                or payload["request_digest"] != row["model_request_digest"]
                or payload["reason_digest"] != row["reason_digest"]
            ):
                raise HostedAgentCellStateError(
                    "tool denial evidence does not match cell event"
                )
        claims = [
            {
                "action_id": row["action_id"],
                "admission_digest": row["admission_digest"],
                "semantic_projection_digest": row["semantic_projection_digest"],
                "ownership_fencing_token": row["ownership_fencing_token"],
            }
            for row in connection.execute(
                """SELECT c.* FROM hosted_tool_execution_claims c
                JOIN hosted_tool_requests q USING(action_id)
                WHERE q.agent_run_id=? ORDER BY q.step_index, q.action_id""",
                (agent_run_id,),
            ).fetchall()
        ]
        if claims != payloads("cell.tool_claimed"):
            raise HostedAgentCellStateError(
                "tool claim evidence does not match cell events"
            )
        tool_results = []
        for row in connection.execute(
            """SELECT q.step_index, r.*, s.section_digest
            FROM hosted_tool_requests q
            JOIN hosted_tool_results r USING(action_id)
            JOIN hosted_context_sections s
              ON s.source_digest=r.reference_digest
            WHERE q.agent_run_id=? ORDER BY q.step_index, q.action_id""",
            (agent_run_id,),
        ).fetchall():
            tool_results.append(
                {
                    "action_id": row["action_id"],
                    "reference_digest": row["reference_digest"],
                    "section_digest": row["section_digest"],
                    "duration_ms": row["duration_ms"],
                    "status": row["status"],
                }
            )
        if tool_results != payloads("cell.tool_completed"):
            raise HostedAgentCellStateError(
                "tool terminal evidence does not match cell events"
            )
        checkpoint_rows = connection.execute(
            """SELECT checkpoint_digest, cell_snapshot_digest
            FROM hosted_agent_checkpoints WHERE agent_run_id=?
            ORDER BY cell_revision""",
            (agent_run_id,),
        ).fetchall()
        checkpoints = [
            {
                "checkpoint_digest": row["checkpoint_digest"],
                "cell_snapshot_digest": row["cell_snapshot_digest"],
            }
            for row in checkpoint_rows
        ]
        if checkpoints != payloads("cell.checkpointed"):
            raise HostedAgentCellStateError(
                "checkpoint evidence does not match cell events"
            )
        rehydrations = [
            {
                "checkpoint_digest": row["checkpoint_digest"],
                "receipt_digest": row["receipt_digest"],
                "previous_epoch": row["previous_epoch"],
                "new_epoch": row["new_epoch"],
            }
            for row in connection.execute(
                """SELECT * FROM hosted_agent_rehydrations
                WHERE agent_run_id=? ORDER BY cell_revision""",
                (agent_run_id,),
            ).fetchall()
        ]
        if rehydrations != payloads("cell.rehydrated"):
            raise HostedAgentCellStateError(
                "rehydration evidence does not match cell events"
            )
        intents = [
            {
                "candidate_run_id": row["candidate_run_id"],
                "decision_digest": row["decision_digest"],
                "final_answer_digest": row["final_answer_digest"],
                "evidence_refs_digest": row["evidence_refs_digest"],
                "intent_digest": row["intent_digest"],
            }
            for row in connection.execute(
                """SELECT * FROM hosted_agent_completion_intents
                WHERE agent_run_id=? ORDER BY created_at, candidate_run_id""",
                (agent_run_id,),
            ).fetchall()
        ]
        if intents != payloads("cell.completion_intent"):
            raise HostedAgentCellStateError(
                "completion intent evidence does not match cell events"
            )
        prepared = [
            {
                "candidate_run_id": row["candidate_run_id"],
                "final_capture_id": row["final_capture_id"],
                "final_answer_digest": row["final_answer_digest"],
                "decision_digest": row["decision_digest"],
                "evidence_refs_digest": row["evidence_refs_digest"],
            }
            for row in connection.execute(
                """SELECT * FROM hosted_agent_completions
                WHERE agent_run_id=? ORDER BY prepared_at""",
                (agent_run_id,),
            ).fetchall()
        ]
        if prepared != payloads("cell.completion_prepared"):
            raise HostedAgentCellStateError(
                "completion evidence does not match cell events"
            )
        completed_events = payloads("cell.completed")
        finalized = [
            row
            for row in connection.execute(
                """SELECT final_capture_id, final_answer_digest
                FROM hosted_agent_completions
                WHERE agent_run_id=? AND finalized_at IS NOT NULL""",
                (agent_run_id,),
            ).fetchall()
        ]
        if [dict(row) for row in finalized] != completed_events:
            raise HostedAgentCellStateError(
                "finalized completion does not match cell event"
            )

    def _register_blob(self, connection, blob: HostedBlobRef, created_at: str) -> None:
        self.blobs.read(blob)
        existing = connection.execute(
            """SELECT * FROM hosted_agent_blobs
            WHERE agent_run_id=? AND role=? AND sha256=?""",
            (blob.agent_run_id, blob.role.value, blob.sha256),
        ).fetchone()
        if existing is None:
            connection.execute(
                """INSERT INTO hosted_agent_blobs(
                    agent_run_id, role, sha256, byte_count, blob_ref,
                    reference_digest, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    blob.agent_run_id,
                    blob.role.value,
                    blob.sha256,
                    blob.byte_count,
                    blob.blob_ref,
                    blob.reference_digest,
                    created_at,
                ),
            )
            return
        expected = (
            blob.byte_count,
            blob.blob_ref,
            blob.reference_digest,
        )
        actual = (
            existing["byte_count"],
            existing["blob_ref"],
            existing["reference_digest"],
        )
        if actual != expected:
            raise HostedAgentCellStateError("hosted blob metadata conflicts")

    @staticmethod
    def _require_blob(
        blob: HostedBlobRef,
        *,
        agent_run_id: str,
        role: HostedBlobRole,
    ) -> None:
        if (
            not isinstance(blob, HostedBlobRef)
            or blob.agent_run_id != agent_run_id
            or blob.role is not role
        ):
            raise HostedAgentCellStateError(
                "hosted blob does not match its AgentRun and role"
            )

    @staticmethod
    def _transition_expected(
        current: HostedAgentCellState | None,
        next_state: HostedAgentCellState,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        if current is None:
            if (
                event_type != "cell.attached"
                or next_state.cell_revision != 1
                or next_state.status is not HostedAgentCellStatus.READY
                or next_state.next_step != 1
                or next_state.provider_calls != 0
                or next_state.tool_calls != 0
            ):
                raise HostedAgentCellStateError("cell event chain has invalid genesis")
            return
        base = {
            "cell_revision": current.cell_revision + 1,
            "updated_at": next_state.updated_at,
        }
        if event_type == "cell.context_appended":
            expected = replace(current, **base)
        elif event_type == "cell.model_dispatched":
            expected = replace(
                current,
                **base,
                status=HostedAgentCellStatus.RUNNING,
                next_step=current.next_step + 1,
                provider_calls=current.provider_calls + 1,
            )
        elif event_type == "cell.model_completed":
            expected = replace(
                current,
                **base,
                active_wall_ms=current.active_wall_ms + payload["duration_ms"],
                currency_cost_usd=(
                    float(current.currency_cost_usd)
                    + float(payload["currency_cost_usd"])
                ),
            )
        elif event_type == "cell.model_failed":
            expected = replace(
                current,
                **base,
                status=HostedAgentCellStatus(payload["cell_status"]),
                active_wall_ms=current.active_wall_ms + payload["duration_ms"],
                currency_cost_usd=(
                    current.currency_cost_usd
                    if payload["currency_cost_usd"] is None
                    else float(current.currency_cost_usd)
                    + float(payload["currency_cost_usd"])
                ),
            )
        elif event_type == "cell.reconciliation_required":
            expected = replace(
                current,
                **base,
                status=HostedAgentCellStatus.RECONCILIATION_REQUIRED,
            )
        elif event_type == "cell.tool_admitted":
            expected = replace(
                current,
                **base,
                tool_calls=current.tool_calls + 1,
            )
        elif event_type in {
            "cell.tool_denied",
            "cell.tool_claimed",
            "cell.completion_intent",
        }:
            expected = replace(current, **base)
        elif event_type == "cell.tool_completed":
            expected = replace(
                current,
                **base,
                active_wall_ms=current.active_wall_ms + payload["duration_ms"],
            )
        elif event_type == "cell.checkpointed":
            expected = replace(
                current,
                **base,
                status=HostedAgentCellStatus.CHECKPOINTED,
                latest_checkpoint_digest=payload["checkpoint_digest"],
            )
        elif event_type == "cell.rehydrated":
            expected = replace(
                current,
                **base,
                status=HostedAgentCellStatus.RUNNING,
            )
        elif event_type == "cell.completion_prepared":
            expected = replace(
                current,
                **base,
                status=HostedAgentCellStatus.COMPLETION_PENDING,
                candidate_run_id=payload["candidate_run_id"],
                final_capture_id=payload["final_capture_id"],
                final_answer_digest=payload["final_answer_digest"],
            )
        elif event_type == "cell.completed":
            expected = replace(
                current,
                **base,
                status=HostedAgentCellStatus.COMPLETED,
            )
        else:
            raise HostedAgentCellStateError("cell event type is unsupported")
        if expected != next_state:
            raise HostedAgentCellStateError(
                "cell event does not produce its claimed projection"
            )

    def _append_event(
        self,
        connection,
        current: HostedAgentCellState | None,
        next_state: HostedAgentCellState,
        *,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        self._transition_expected(current, next_state, event_type, payload)
        previous = connection.execute(
            """SELECT event_digest FROM hosted_agent_cell_events
            WHERE agent_run_id=? ORDER BY cell_revision DESC LIMIT 1""",
            (next_state.agent_run_id,),
        ).fetchone()
        prior_digest = _ZERO_DIGEST if previous is None else previous["event_digest"]
        payload_digest = canonical_record_digest(
            "macr.hosted-agent-cell.event-payload.v1",
            {"event_type": event_type, "payload": payload},
        )
        event_id = str(uuid.uuid4())
        event_digest = canonical_record_digest(
            "macr.hosted-agent-cell.event.v1",
            {
                "event_id": event_id,
                "agent_run_id": next_state.agent_run_id,
                "cell_revision": next_state.cell_revision,
                "event_type": event_type,
                "payload_digest": payload_digest,
                "prior_event_digest": prior_digest,
                "state_digest_after": next_state.state_digest,
                "created_at": next_state.updated_at,
            },
        )
        connection.execute(
            """INSERT INTO hosted_agent_cell_events(
                event_id, agent_run_id, cell_revision, event_type,
                payload_json, payload_digest, prior_event_digest,
                state_after_json, state_digest_after, event_digest, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                next_state.agent_run_id,
                next_state.cell_revision,
                event_type,
                _json_text(payload),
                payload_digest,
                prior_digest,
                _json_text(next_state.to_public_dict()),
                next_state.state_digest,
                event_digest,
                next_state.updated_at,
            ),
        )

    def _replay_events(self, connection, agent_run_id: str) -> HostedAgentCellState:
        rows = connection.execute(
            """SELECT * FROM hosted_agent_cell_events
            WHERE agent_run_id=? ORDER BY cell_revision""",
            (agent_run_id,),
        ).fetchall()
        current = None
        prior_digest = _ZERO_DIGEST
        for index, row in enumerate(rows, start=1):
            payload = json.loads(row["payload_json"])
            next_state = HostedAgentCellState.from_dict(
                json.loads(row["state_after_json"])
            )
            expected_payload = canonical_record_digest(
                "macr.hosted-agent-cell.event-payload.v1",
                {"event_type": row["event_type"], "payload": payload},
            )
            expected_event = canonical_record_digest(
                "macr.hosted-agent-cell.event.v1",
                {
                    "event_id": row["event_id"],
                    "agent_run_id": agent_run_id,
                    "cell_revision": index,
                    "event_type": row["event_type"],
                    "payload_digest": expected_payload,
                    "prior_event_digest": prior_digest,
                    "state_digest_after": next_state.state_digest,
                    "created_at": row["created_at"],
                },
            )
            if (
                row["cell_revision"] != index
                or row["payload_digest"] != expected_payload
                or row["prior_event_digest"] != prior_digest
                or row["state_digest_after"] != next_state.state_digest
                or row["event_digest"] != expected_event
                or next_state.agent_run_id != agent_run_id
                or next_state.cell_revision != index
                or next_state.updated_at != row["created_at"]
            ):
                raise HostedAgentCellStateError("cell event chain is invalid")
            self._transition_expected(current, next_state, row["event_type"], payload)
            current = next_state
            prior_digest = row["event_digest"]
        if current is None:
            raise HostedAgentCellStateError("cell event history is missing")
        return current

    def _update_state(
        self,
        connection,
        current_row,
        *,
        event_type: str,
        event_payload: dict[str, object],
        **changes,
    ) -> HostedAgentCellState:
        current = self._state_from_row(current_row)
        next_state = replace(
            current,
            cell_revision=current.cell_revision + 1,
            **changes,
        )
        self._append_event(
            connection,
            current,
            next_state,
            event_type=event_type,
            payload=event_payload,
        )
        changed = connection.execute(
            """UPDATE hosted_agent_cells SET
                cell_revision=?, status=?, next_step=?, provider_calls=?, tool_calls=?,
                active_wall_ms=?, currency_cost_usd=?,
                latest_checkpoint_digest=?, candidate_run_id=?,
                final_capture_id=?, final_answer_digest=?, state_digest=?,
                updated_at=?
            WHERE agent_run_id=? AND state_digest=?""",
            (
                next_state.cell_revision,
                next_state.status.value,
                next_state.next_step,
                next_state.provider_calls,
                next_state.tool_calls,
                next_state.active_wall_ms,
                float(next_state.currency_cost_usd),
                next_state.latest_checkpoint_digest,
                next_state.candidate_run_id,
                next_state.final_capture_id,
                next_state.final_answer_digest,
                next_state.state_digest,
                next_state.updated_at,
                next_state.agent_run_id,
                current.state_digest,
            ),
        ).rowcount
        if changed != 1:
            raise HostedAgentCellStateError(
                "hosted Agent cell state changed concurrently"
            )
        return next_state

    def attach(
        self,
        permit: AgentOwnershipPermit,
        policy: HostedAgentCellPolicy,
        semantic_request: SemanticContextRequest,
        sections: Iterable[HostedContextSection],
    ) -> HostedAgentCellState:
        if not isinstance(policy, HostedAgentCellPolicy):
            raise ValueError("policy must be a HostedAgentCellPolicy")
        if not isinstance(semantic_request, SemanticContextRequest):
            raise ValueError("semantic_request must be a SemanticContextRequest")
        items = tuple(sections)
        if not items or any(
            not isinstance(item, HostedContextSection)
            or item.agent_run_id != policy.agent_run_id
            for item in items
        ):
            raise ValueError("sections must contain this AgentRun's context")
        if (
            permit.agent_run_id != policy.agent_run_id
            or semantic_request.agent_run_id != policy.agent_run_id
        ):
            raise HostedAgentCellStateError("hosted cell identities conflict")
        timestamp = self._timestamp()
        blobs = tuple(
            (
                item,
                self.blobs.write(
                    item.agent_run_id,
                    HostedBlobRole.CONTEXT,
                    item.canonical_bytes(),
                ),
            )
            for item in items
        )
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            projection, agent_row = self._verify_permit(
                connection,
                permit,
                observed_at=timestamp,
            )
            self._verify_authority(
                projection,
                policy_digest=policy.policy_digest,
                operation="cell_attach",
            )
            if (
                connection.execute(
                    "SELECT 1 FROM hosted_agent_cells WHERE agent_run_id=?",
                    (policy.agent_run_id,),
                ).fetchone()
                is not None
            ):
                raise HostedAgentCellStateError("hosted Agent cell already exists")
            expected_semantic_ref = f"semantic-graph:{semantic_request.graph_id}"
            if (
                agent_row["semantic_state_ref"] != expected_semantic_ref
                or agent_row["semantic_state_digest"] != semantic_request.graph_digest
                or agent_row["semantic_state_revision"]
                != semantic_request.graph_revision
            ):
                raise HostedAgentCellStateError(
                    "hosted cell semantic request is not AgentRun-pinned"
                )
            state = HostedAgentCellState(
                agent_run_id=policy.agent_run_id,
                cell_revision=1,
                policy_digest=policy.policy_digest,
                semantic_request_digest=semantic_request.request_digest,
                status=HostedAgentCellStatus.READY,
                next_step=1,
                provider_calls=0,
                tool_calls=0,
                active_wall_ms=0,
                currency_cost_usd=0.0,
                latest_checkpoint_digest=None,
                candidate_run_id=None,
                final_capture_id=None,
                final_answer_digest=None,
                created_at=timestamp,
                updated_at=timestamp,
            )
            connection.execute(
                """INSERT INTO hosted_agent_cells(
                    agent_run_id, cell_revision, policy_json, policy_digest,
                    semantic_request_json, semantic_request_digest, status,
                    next_step, provider_calls, tool_calls, active_wall_ms,
                    currency_cost_usd, latest_checkpoint_digest,
                    candidate_run_id, final_capture_id, final_answer_digest,
                    state_digest, created_at, updated_at
                ) VALUES (?, 1, ?, ?, ?, ?, ?, 1, 0, 0, 0, 0.0,
                          NULL, NULL, NULL, NULL, ?, ?, ?)""",
                (
                    state.agent_run_id,
                    _json_text(policy.to_public_dict()),
                    state.policy_digest,
                    _json_text(semantic_request.to_public_dict()),
                    state.semantic_request_digest,
                    state.status.value,
                    state.state_digest,
                    timestamp,
                    timestamp,
                ),
            )
            for item, blob in blobs:
                self._register_blob(connection, blob, timestamp)
                connection.execute(
                    """INSERT INTO hosted_context_sections(
                        section_id, agent_run_id, kind, blob_ref, body_digest,
                        body_bytes, source_digest, section_digest, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        item.section_id,
                        item.agent_run_id,
                        item.kind.value,
                        blob.blob_ref,
                        item.body_digest,
                        len(item.body.encode("utf-8")),
                        item.source_digest,
                        item.section_digest,
                        item.created_at,
                    ),
                )
            self._append_event(
                connection,
                None,
                state,
                event_type="cell.attached",
                payload={
                    "policy_digest": policy.policy_digest,
                    "semantic_request_digest": semantic_request.request_digest,
                    "section_digests": [item.section_digest for item in items],
                },
            )
            connection.commit()
            return state
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def read_state(self, agent_run_id: str) -> HostedAgentCellState:
        connection = self.database.connect()
        try:
            return self._state_from_row(self._cell_row(connection, agent_run_id))
        finally:
            connection.close()

    def append_context_section(
        self,
        permit: AgentOwnershipPermit,
        section: HostedContextSection,
    ) -> None:
        if (
            not isinstance(section, HostedContextSection)
            or section.agent_run_id != permit.agent_run_id
        ):
            raise ValueError("section must belong to the permitted AgentRun")
        timestamp = self._timestamp()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            projection, _ = self._verify_permit(
                connection,
                permit,
                observed_at=timestamp,
            )
            row = self._cell_row(connection, permit.agent_run_id)
            state = self._state_from_row(row)
            self._verify_authority(
                projection,
                policy_digest=state.policy_digest,
                operation="context_append",
            )
            if state.status is not HostedAgentCellStatus.RUNNING:
                raise HostedAgentCellStateError(
                    "cell cannot append context in current state"
                )
            if self._pending_counts(connection, permit.agent_run_id) != (0, 0):
                raise HostedAgentReconciliationRequired(
                    "cell cannot append context while an operation is pending"
                )
            blob = self.blobs.write(
                section.agent_run_id,
                HostedBlobRole.CONTEXT,
                section.canonical_bytes(),
            )
            self._register_blob(connection, blob, timestamp)
            connection.execute(
                """INSERT INTO hosted_context_sections(
                    section_id, agent_run_id, kind, blob_ref, body_digest,
                    body_bytes, source_digest, section_digest, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    section.section_id,
                    section.agent_run_id,
                    section.kind.value,
                    blob.blob_ref,
                    section.body_digest,
                    len(section.body.encode("utf-8")),
                    section.source_digest,
                    section.section_digest,
                    section.created_at,
                ),
            )
            self._update_state(
                connection,
                row,
                event_type="cell.context_appended",
                event_payload={"section_digest": section.section_digest},
                updated_at=timestamp,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def read_policy(self, agent_run_id: str) -> HostedAgentCellPolicy:
        connection = self.database.connect()
        try:
            row = self._cell_row(connection, agent_run_id)
            policy = HostedAgentCellPolicy.from_dict(json.loads(row["policy_json"]))
        finally:
            connection.close()
        if policy.policy_digest != row["policy_digest"]:
            raise HostedAgentCellStateError("hosted cell policy conflicts")
        return policy

    def read_semantic_request(self, agent_run_id: str) -> SemanticContextRequest:
        connection = self.database.connect()
        try:
            row = self._cell_row(connection, agent_run_id)
            request = SemanticContextRequest.from_dict(
                json.loads(row["semantic_request_json"])
            )
        finally:
            connection.close()
        if request.request_digest != row["semantic_request_digest"]:
            raise HostedAgentCellStateError("semantic request conflicts")
        return request

    def _blob_from_ref(
        self,
        connection,
        blob_ref: str,
        *,
        expected_run_id: str,
        expected_role: HostedBlobRole,
    ) -> HostedBlobRef:
        row = connection.execute(
            "SELECT * FROM hosted_agent_blobs WHERE blob_ref=?",
            (blob_ref,),
        ).fetchone()
        if row is None:
            raise HostedAgentCellStateError("hosted blob metadata is missing")
        blob = HostedBlobRef(
            row["agent_run_id"],
            HostedBlobRole(row["role"]),
            row["sha256"],
            row["byte_count"],
        )
        if blob.reference_digest != row["reference_digest"]:
            raise HostedAgentCellStateError("hosted blob reference conflicts")
        if blob.agent_run_id != expected_run_id or blob.role is not expected_role:
            raise HostedAgentCellStateError(
                "hosted blob reference crosses AgentRun or role"
            )
        return blob

    def _verify_read_permit(self, permit: AgentOwnershipPermit) -> None:
        timestamp = self._timestamp()
        connection = self.database.connect()
        try:
            self._verify_permit(connection, permit, observed_at=timestamp)
        finally:
            connection.close()

    def list_context_sections(
        self,
        permit: AgentOwnershipPermit,
        agent_run_id: str,
    ) -> tuple[HostedContextSection, ...]:
        if permit.agent_run_id != agent_run_id:
            raise HostedAgentCellStateError("context read permit uses another run")
        timestamp = self._timestamp()
        connection = self.database.connect()
        try:
            self._verify_permit(connection, permit, observed_at=timestamp)
            rows = connection.execute(
                """SELECT * FROM hosted_context_sections
                WHERE agent_run_id=? ORDER BY sequence""",
                (agent_run_id,),
            ).fetchall()
            refs = tuple(
                self._blob_from_ref(
                    connection,
                    row["blob_ref"],
                    expected_run_id=agent_run_id,
                    expected_role=HostedBlobRole.CONTEXT,
                )
                for row in rows
            )
        finally:
            connection.close()
        result = []
        for row, blob in zip(rows, refs):
            item = HostedContextSection.from_private_dict(
                json.loads(self.blobs.read(blob).decode("utf-8"))
            )
            if (
                item.agent_run_id != agent_run_id
                or item.section_id != row["section_id"]
                or item.section_digest != row["section_digest"]
                or item.body_digest != row["body_digest"]
                or len(item.body.encode("utf-8")) != row["body_bytes"]
                or item.source_digest != row["source_digest"]
            ):
                raise HostedAgentCellStateError("hosted context metadata conflicts")
            result.append(item)
        return tuple(result)

    def context_causal_inputs(
        self,
        permit: AgentOwnershipPermit,
        agent_run_id: str,
    ) -> dict[str, object]:
        if permit.agent_run_id != agent_run_id:
            raise HostedAgentCellStateError("causal read permit uses another run")
        timestamp = self._timestamp()
        connection = self.database.connect()
        try:
            self._verify_permit(connection, permit, observed_at=timestamp)
            sections = [
                {
                    "section_id": row["section_id"],
                    "section_digest": row["section_digest"],
                }
                for row in connection.execute(
                    """SELECT section_id, section_digest
                    FROM hosted_context_sections WHERE agent_run_id=?
                    ORDER BY sequence""",
                    (agent_run_id,),
                ).fetchall()
            ]
            model = [
                row["result_digest"]
                for row in connection.execute(
                    """SELECT t.result_digest FROM hosted_model_dispatches d
                    JOIN hosted_model_terminals t USING(provider_invocation_id)
                    WHERE d.agent_run_id=? AND t.terminal_state='completed'
                    ORDER BY d.step_index""",
                    (agent_run_id,),
                ).fetchall()
            ]
            tools = [
                row["reference_digest"]
                for row in connection.execute(
                    """SELECT r.reference_digest FROM hosted_tool_requests q
                    JOIN hosted_tool_results r USING(action_id)
                    WHERE q.agent_run_id=? ORDER BY q.step_index, q.action_id""",
                    (agent_run_id,),
                ).fetchall()
            ]
        finally:
            connection.close()
        return {
            "sections": sections,
            "model_result_digests": model,
            "tool_result_digests": tools,
        }

    def get_cached_envelope(
        self,
        permit: AgentOwnershipPermit,
        agent_run_id: str,
        step_index: int,
        causal_digest: str,
    ) -> tuple[HostedBlobRef, bytes, str] | None:
        timestamp = self._timestamp()
        connection = self.database.connect()
        try:
            projection, _ = self._verify_permit(
                connection,
                permit,
                observed_at=timestamp,
            )
            cell = self._state_from_row(self._cell_row(connection, agent_run_id))
            self._verify_authority(
                projection,
                policy_digest=cell.policy_digest,
                operation="context_projection",
            )
            if cell.next_step != step_index or projection.epoch != permit.epoch:
                raise HostedAgentCellStateError("cached context request is stale")
            rows = connection.execute(
                """SELECT envelope_digest, blob_ref
                FROM hosted_context_envelopes
                WHERE agent_run_id=? AND step_index=? AND causal_digest=?""",
                (
                    agent_run_id,
                    step_index,
                    require_sha256("causal_digest", causal_digest),
                ),
            ).fetchall()
            if len(rows) > 1:
                raise HostedAgentCellStateError("context cache identity is ambiguous")
            if not rows:
                return None
            blob = self._blob_from_ref(
                connection,
                rows[0]["blob_ref"],
                expected_run_id=agent_run_id,
                expected_role=HostedBlobRole.PROJECTION,
            )
            envelope_digest = rows[0]["envelope_digest"]
            policy = HostedAgentCellPolicy.from_dict(
                json.loads(self._cell_row(connection, agent_run_id)["policy_json"])
            )
        finally:
            connection.close()
        if not self.blobs.exists(blob):
            return None
        payload = self.blobs.read(blob)
        if len(payload) > policy.max_context_bytes:
            raise HostedAgentCellStateError("cached context exceeds current policy")
        try:
            document = json.loads(payload)
            claimed_digest = document.pop("envelope_digest")
            embedded_causal = document["causal_digest"]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise HostedAgentCellStateError(
                "cached context payload is invalid"
            ) from exc
        encoded = canonical_json_bytes(document)
        expected_digest = canonical_record_digest(
            "macr.hosted-context-envelope.v1",
            {
                "causal_digest": causal_digest,
                "payload_sha256": hashlib.sha256(encoded).hexdigest(),
                "payload_bytes": len(encoded),
            },
        )
        if (
            embedded_causal != causal_digest
            or claimed_digest != envelope_digest
            or expected_digest != envelope_digest
        ):
            raise HostedAgentCellStateError("cached context identity conflicts")
        return blob, payload, envelope_digest

    def save_context_envelope(
        self,
        *,
        permit: AgentOwnershipPermit,
        state: HostedAgentCellState,
        step_index: int,
        agent_run_epoch: int,
        agent_state_revision: int,
        semantic_projection_digest: str,
        policy_digest: str,
        tool_catalog_digest: str,
        causal_digest: str,
        envelope_digest: str,
        envelope_bytes: bytes,
        created_at: str,
    ) -> HostedBlobRef:
        timestamp = normalize_timestamp("created_at", created_at)
        blob = self.blobs.write(
            state.agent_run_id,
            HostedBlobRole.PROJECTION,
            envelope_bytes,
        )
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            projection, _ = self._verify_permit(
                connection,
                permit,
                observed_at=timestamp,
            )
            current = self._state_from_row(
                self._cell_row(connection, state.agent_run_id)
            )
            if (
                current != state
                or current.next_step != step_index
                or projection.epoch != agent_run_epoch
                or projection.state_revision != agent_state_revision
                or current.policy_digest != policy_digest
            ):
                raise HostedAgentCellStateError("context envelope inputs changed")
            self._verify_authority(
                projection,
                policy_digest=current.policy_digest,
                operation="context_projection",
            )
            self._register_blob(connection, blob, timestamp)
            existing = connection.execute(
                "SELECT * FROM hosted_context_envelopes WHERE envelope_digest=?",
                (envelope_digest,),
            ).fetchone()
            values = (
                state.agent_run_id,
                step_index,
                agent_run_epoch,
                agent_state_revision,
                semantic_projection_digest,
                policy_digest,
                tool_catalog_digest,
                causal_digest,
                blob.blob_ref,
                len(envelope_bytes),
                timestamp,
            )
            if existing is None:
                connection.execute(
                    """INSERT INTO hosted_context_envelopes(
                        envelope_digest, agent_run_id, step_index,
                        agent_run_epoch, agent_state_revision,
                        semantic_projection_digest, policy_digest,
                        tool_catalog_digest, causal_digest, blob_ref,
                        byte_count, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (envelope_digest, *values),
                )
            else:
                actual = tuple(
                    existing[name]
                    for name in (
                        "agent_run_id",
                        "step_index",
                        "agent_run_epoch",
                        "agent_state_revision",
                        "semantic_projection_digest",
                        "policy_digest",
                        "tool_catalog_digest",
                        "causal_digest",
                        "blob_ref",
                        "byte_count",
                        "created_at",
                    )
                )
                if actual != values:
                    raise HostedAgentCellStateError(
                        "context envelope identity conflicts"
                    )
            connection.commit()
            return blob
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def clear_context_cache(self, agent_run_id: str) -> int:
        run_id = require_uuid4("agent_run_id", agent_run_id)
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """SELECT DISTINCT b.* FROM hosted_context_envelopes e
                JOIN hosted_agent_blobs b ON b.blob_ref=e.blob_ref
                WHERE e.agent_run_id=?""",
                (run_id,),
            ).fetchall()
            connection.execute(
                "DELETE FROM hosted_context_envelopes WHERE agent_run_id=?",
                (run_id,),
            )
            connection.execute(
                "DELETE FROM hosted_agent_blobs WHERE agent_run_id=? AND role='projection'",
                (run_id,),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        removed = 0
        for row in rows:
            blob = HostedBlobRef(
                row["agent_run_id"],
                HostedBlobRole(row["role"]),
                row["sha256"],
                row["byte_count"],
            )
            if self.blobs.delete_projection_cache(blob):
                removed += 1
        return removed

    def _pending_counts(self, connection, agent_run_id: str) -> tuple[int, int]:
        models = connection.execute(
            """SELECT COUNT(*) FROM hosted_model_dispatches d
            LEFT JOIN hosted_model_terminals t USING(provider_invocation_id)
            WHERE d.agent_run_id=? AND t.provider_invocation_id IS NULL""",
            (agent_run_id,),
        ).fetchone()[0]
        tools = connection.execute(
            """SELECT COUNT(*) FROM hosted_tool_requests q
            LEFT JOIN hosted_tool_results r USING(action_id)
            WHERE q.agent_run_id=? AND q.decision='admitted'
              AND r.action_id IS NULL""",
            (agent_run_id,),
        ).fetchone()[0]
        return models, tools

    def mark_pending_reconciliation(
        self,
        permit: AgentOwnershipPermit,
    ) -> HostedAgentCellState | None:
        timestamp = self._timestamp()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._verify_permit(connection, permit, observed_at=timestamp)
            row = self._cell_row(connection, permit.agent_run_id)
            state = self._state_from_row(row)
            pending_models, pending_tools = self._pending_counts(
                connection,
                permit.agent_run_id,
            )
            if not pending_models and not pending_tools:
                connection.commit()
                return None
            if state.status is HostedAgentCellStatus.RECONCILIATION_REQUIRED:
                connection.commit()
                return state
            next_state = self._update_state(
                connection,
                row,
                event_type="cell.reconciliation_required",
                event_payload={
                    "pending_model_dispatches": pending_models,
                    "pending_tool_dispatches": pending_tools,
                },
                status=HostedAgentCellStatus.RECONCILIATION_REQUIRED,
                updated_at=timestamp,
            )
            connection.commit()
            return next_state
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def begin_model_attempt(
        self,
        permit: AgentOwnershipPermit,
        request: HostedModelRequest,
    ) -> HostedAgentCellState:
        timestamp = self._timestamp()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            projection, _ = self._verify_permit(
                connection,
                permit,
                observed_at=timestamp,
            )
            row = self._cell_row(connection, request.agent_run_id)
            state = self._state_from_row(row)
            policy = HostedAgentCellPolicy.from_dict(json.loads(row["policy_json"]))
            self._verify_authority(
                projection,
                policy_digest=policy.policy_digest,
                operation="model_dispatch",
            )
            if state.status not in {
                HostedAgentCellStatus.READY,
                HostedAgentCellStatus.RUNNING,
            }:
                raise HostedAgentCellStateError(
                    "cell cannot dispatch a model in current state"
                )
            if self._pending_counts(connection, state.agent_run_id) != (0, 0):
                raise HostedAgentReconciliationRequired("cell has a pending operation")
            if (
                request.step_index != state.next_step
                or request.policy_digest != state.policy_digest
                or request.provider_id != policy.provider_id
                or request.model_id != policy.model_id
                or request.model_token_policy_digest != policy.model_token_policy_digest
                or request.provider_execution_profile_digest
                != policy.provider_execution_profile_digest
                or request.prompt_compiler_version != policy.prompt_compiler_version
                or request.delegation_class != policy.delegation_class
                or request.privacy != policy.privacy
                or request.provider_tier_binding_digest
                != policy.provider_tier_binding_digest
                or request.project_binding_digest != policy.project_binding_digest
                or request.admission_lane != policy.admission_lane
                or request.provider_admission_policy_digest
                != policy.provider_admission_policy_digest
                or request.max_latency_s != policy.max_latency_s
                or request.max_output_tokens != policy.max_output_tokens
                or request.max_provider_context_tokens
                != policy.max_provider_context_tokens
                or request.agent_run_epoch != permit.epoch
            ):
                raise HostedAgentCellStateError("model request is stale or mismatched")
            if (
                state.next_step > policy.max_steps
                or state.provider_calls >= policy.max_provider_calls
            ):
                raise HostedAgentCellBudgetError("model-call budget is exhausted")
            if state.active_wall_ms >= round(policy.max_active_wall_seconds * 1000):
                raise HostedAgentCellBudgetError("active wall budget is exhausted")
            if state.currency_cost_usd > policy.max_currency_cost_usd:
                raise HostedAgentCellBudgetError("currency budget is exhausted")
            remaining_cost = float(policy.max_currency_cost_usd) - float(
                state.currency_cost_usd
            )
            if (
                request.cost_ceiling_usd != policy.max_provider_call_cost_usd
                or request.cost_ceiling_usd > remaining_cost
            ):
                raise HostedAgentCellBudgetError(
                    "per-call cost ceiling exceeds remaining budget"
                )
            if request.context_bytes > policy.max_context_bytes:
                raise HostedAgentCellBudgetError("context byte budget is exceeded")
            connection.execute(
                """INSERT INTO hosted_model_dispatches(
                    provider_invocation_id, agent_run_id, step_index,
                    request_json, request_digest, context_digest, dispatched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    request.provider_invocation_id,
                    request.agent_run_id,
                    request.step_index,
                    _json_text(request.to_public_dict()),
                    request.request_digest,
                    request.context_digest,
                    timestamp,
                ),
            )
            result = self._update_state(
                connection,
                row,
                event_type="cell.model_dispatched",
                event_payload={
                    "provider_invocation_id": request.provider_invocation_id,
                    "request_digest": request.request_digest,
                    "context_digest": request.context_digest,
                    "cost_ceiling_usd": request.cost_ceiling_usd,
                },
                status=HostedAgentCellStatus.RUNNING,
                next_step=state.next_step + 1,
                provider_calls=state.provider_calls + 1,
                updated_at=timestamp,
            )
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def finish_model_success(
        self,
        permit: AgentOwnershipPermit,
        result: HostedModelResult,
        raw_blob: HostedBlobRef,
        decision_blob: HostedBlobRef,
    ) -> HostedAgentCellState:
        timestamp = self._timestamp()
        self._require_blob(
            raw_blob,
            agent_run_id=permit.agent_run_id,
            role=HostedBlobRole.MODEL_RAW,
        )
        self._require_blob(
            decision_blob,
            agent_run_id=permit.agent_run_id,
            role=HostedBlobRole.MODEL_DECISION,
        )
        raw_bytes = self.blobs.read(raw_blob)
        decision_bytes = self.blobs.read(decision_blob)
        if decision_bytes != result.decision.canonical_bytes():
            raise HostedAgentCellStateError(
                "model decision blob conflicts with compiled decision"
            )
        try:
            raw_compiled = HostedModelDecision.from_json_bytes(
                raw_bytes,
                id_factory=lambda: str(uuid.uuid4()),
            )
        except Exception as exc:
            raise HostedAgentCellStateError(
                "raw model bytes cannot reconstruct the compiled proposal"
            ) from exc
        if raw_compiled.proposal_digest != result.decision.proposal_digest:
            raise HostedAgentCellStateError("raw and compiled model proposals conflict")
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            projection, _ = self._verify_permit(
                connection,
                permit,
                observed_at=timestamp,
            )
            dispatch = connection.execute(
                "SELECT * FROM hosted_model_dispatches WHERE provider_invocation_id=?",
                (result.provider_invocation_id,),
            ).fetchone()
            if dispatch is None or dispatch["agent_run_id"] != permit.agent_run_id:
                raise HostedAgentCellStateError("model dispatch evidence is missing")
            row = self._cell_row(connection, permit.agent_run_id)
            existing = connection.execute(
                "SELECT * FROM hosted_model_terminals WHERE provider_invocation_id=?",
                (result.provider_invocation_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["result_digest"] != result.result_digest
                    or existing["raw_blob_ref"] != raw_blob.blob_ref
                    or existing["decision_blob_ref"] != decision_blob.blob_ref
                ):
                    raise HostedAgentCellStateError("model terminal conflicts")
                return self._state_from_row(
                    self._cell_row(connection, permit.agent_run_id)
                )
            policy = HostedAgentCellPolicy.from_dict(json.loads(row["policy_json"]))
            if (
                result.provider_id != policy.provider_id
                or result.model_id != policy.model_id
            ):
                raise HostedAgentCellStateError("model result identity conflicts")
            self._register_blob(connection, raw_blob, timestamp)
            self._register_blob(connection, decision_blob, timestamp)
            connection.execute(
                """INSERT INTO hosted_model_terminals(
                    provider_invocation_id, terminal_state, result_json,
                    result_digest, raw_blob_ref, decision_blob_ref,
                    currency_cost_usd, duration_ms, network_attempted,
                    response_received, failure_code, failure_digest, terminal_at
                ) VALUES (?, 'completed', ?, ?, ?, ?, ?, ?, ?, ?,
                          NULL, NULL, ?)""",
                (
                    result.provider_invocation_id,
                    _json_text(result.to_public_dict()),
                    result.result_digest,
                    raw_blob.blob_ref,
                    decision_blob.blob_ref,
                    float(result.currency_cost_usd),
                    result.duration_ms,
                    None
                    if result.network_attempted is None
                    else int(result.network_attempted),
                    None
                    if result.response_received is None
                    else int(result.response_received),
                    timestamp,
                ),
            )
            state = self._state_from_row(row)
            next_state = self._update_state(
                connection,
                row,
                event_type="cell.model_completed",
                event_payload={
                    "provider_invocation_id": result.provider_invocation_id,
                    "result_digest": result.result_digest,
                    "duration_ms": result.duration_ms,
                    "currency_cost_usd": result.currency_cost_usd,
                },
                active_wall_ms=state.active_wall_ms + result.duration_ms,
                currency_cost_usd=(
                    float(state.currency_cost_usd) + float(result.currency_cost_usd)
                ),
                updated_at=timestamp,
            )
            connection.commit()
            return next_state
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def finish_model_failure(
        self,
        permit: AgentOwnershipPermit,
        provider_invocation_id: str,
        *,
        failure_code: str,
        failure_digest: str,
        duration_ms: int,
        ambiguous: bool,
        currency_cost_usd: int | float | None,
        network_attempted: bool | None,
        response_received: bool | None,
        raw_blob: HostedBlobRef | None = None,
    ) -> HostedAgentCellState:
        timestamp = self._timestamp()
        invocation_id = require_uuid4("provider_invocation_id", provider_invocation_id)
        code = require_non_empty("failure_code", failure_code, 128)
        digest = require_sha256("failure_digest", failure_digest)
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or duration_ms < 0
        ):
            raise ValueError("duration_ms must be non-negative")
        if currency_cost_usd is not None:
            currency_cost_usd = require_non_negative_number(
                "currency_cost_usd",
                currency_cost_usd,
            )
        if network_attempted not in {True, False, None}:
            raise ValueError("network_attempted must be boolean or None")
        if response_received not in {True, False, None}:
            raise ValueError("response_received must be boolean or None")
        if response_received is True and network_attempted is not True:
            raise ValueError("response_received requires network_attempted")
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            projection, _ = self._verify_permit(
                connection,
                permit,
                observed_at=timestamp,
            )
            dispatch = connection.execute(
                "SELECT * FROM hosted_model_dispatches WHERE provider_invocation_id=?",
                (invocation_id,),
            ).fetchone()
            if dispatch is None or dispatch["agent_run_id"] != permit.agent_run_id:
                raise HostedAgentCellStateError("model dispatch evidence is missing")
            if (
                connection.execute(
                    "SELECT 1 FROM hosted_model_terminals WHERE provider_invocation_id=?",
                    (invocation_id,),
                ).fetchone()
                is not None
            ):
                raise HostedAgentCellStateError("model attempt is already terminal")
            row = self._cell_row(connection, permit.agent_run_id)
            if raw_blob is not None:
                self._require_blob(
                    raw_blob,
                    agent_run_id=permit.agent_run_id,
                    role=HostedBlobRole.MODEL_RAW,
                )
                self._register_blob(connection, raw_blob, timestamp)
            terminal_state = "reconciliation_required" if ambiguous else "failed"
            connection.execute(
                """INSERT INTO hosted_model_terminals(
                    provider_invocation_id, terminal_state, result_json,
                    result_digest, raw_blob_ref, decision_blob_ref,
                    currency_cost_usd, duration_ms, network_attempted,
                    response_received, failure_code, failure_digest, terminal_at
                ) VALUES (?, ?, NULL, NULL, ?, NULL, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    invocation_id,
                    terminal_state,
                    None if raw_blob is None else raw_blob.blob_ref,
                    None if currency_cost_usd is None else float(currency_cost_usd),
                    duration_ms,
                    None if network_attempted is None else int(network_attempted),
                    None if response_received is None else int(response_received),
                    code,
                    digest,
                    timestamp,
                ),
            )
            state = self._state_from_row(row)
            next_state = self._update_state(
                connection,
                row,
                event_type="cell.model_failed",
                event_payload={
                    "provider_invocation_id": invocation_id,
                    "failure_digest": digest,
                    "duration_ms": duration_ms,
                    "currency_cost_usd": currency_cost_usd,
                    "network_attempted": network_attempted,
                    "response_received": response_received,
                    "cell_status": (
                        HostedAgentCellStatus.RECONCILIATION_REQUIRED.value
                        if ambiguous
                        else HostedAgentCellStatus.BLOCKED.value
                    ),
                },
                status=(
                    HostedAgentCellStatus.RECONCILIATION_REQUIRED
                    if ambiguous
                    else HostedAgentCellStatus.BLOCKED
                ),
                active_wall_ms=state.active_wall_ms + duration_ms,
                currency_cost_usd=(
                    state.currency_cost_usd
                    if currency_cost_usd is None
                    else float(state.currency_cost_usd) + float(currency_cost_usd)
                ),
                updated_at=timestamp,
            )
            connection.commit()
            return next_state
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def begin_tool(
        self,
        permit: AgentOwnershipPermit,
        *,
        step_index: int,
        request: HostedToolRequest,
        arguments_blob: HostedBlobRef,
        proposal: ActionProposal,
        admission: ActionAdmission,
    ) -> HostedAgentCellState:
        timestamp = self._timestamp()
        self._require_blob(
            arguments_blob,
            agent_run_id=permit.agent_run_id,
            role=HostedBlobRole.TOOL_ARGUMENTS,
        )
        if self.blobs.read(arguments_blob) != canonical_json_bytes(
            dict(request.arguments)
        ):
            raise HostedAgentCellStateError(
                "tool arguments blob conflicts with model request"
            )
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            projection, _ = self._verify_permit(
                connection,
                permit,
                observed_at=timestamp,
            )
            row = self._cell_row(connection, permit.agent_run_id)
            state = self._state_from_row(row)
            policy = HostedAgentCellPolicy.from_dict(json.loads(row["policy_json"]))
            self._verify_authority(
                projection,
                policy_digest=policy.policy_digest,
                operation="tool_admission",
            )
            if state.status is not HostedAgentCellStatus.RUNNING:
                raise HostedAgentCellStateError("cell cannot execute a tool now")
            if self._pending_counts(connection, permit.agent_run_id) != (0, 0):
                raise HostedAgentReconciliationRequired("cell has a pending operation")
            if step_index != state.next_step - 1:
                raise HostedAgentCellStateError("tool request step is stale")
            if state.tool_calls >= policy.max_tool_calls:
                raise HostedAgentCellBudgetError("tool-call budget is exhausted")
            if state.active_wall_ms >= round(policy.max_active_wall_seconds * 1000):
                raise HostedAgentCellBudgetError(
                    "active wall budget is exhausted before tool admission"
                )
            if state.currency_cost_usd > policy.max_currency_cost_usd:
                raise HostedAgentCellBudgetError(
                    "currency budget is exceeded before tool admission"
                )
            if (
                proposal.action_id != request.request_id
                or admission.action_id != proposal.action_id
                or admission.proposal_digest != proposal.proposal_digest
                or admission.policy_snapshot_digest != policy.policy_digest
            ):
                raise HostedAgentCellStateError("tool admission evidence conflicts")
            self._register_blob(connection, arguments_blob, timestamp)
            connection.execute(
                """INSERT INTO hosted_tool_requests(
                    action_id, agent_run_id, step_index,
                    model_request_digest, tool_id, arguments_blob_ref,
                    arguments_digest, proposal_json, proposal_digest,
                    admission_json, admission_digest, decision,
                    reason_code, reason_digest, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'admitted',
                          NULL, NULL, ?)""",
                (
                    request.request_id,
                    permit.agent_run_id,
                    step_index,
                    request.request_digest,
                    request.tool_id,
                    arguments_blob.blob_ref,
                    request.arguments_digest,
                    _json_text(proposal.to_public_dict()),
                    proposal.proposal_digest,
                    _json_text(admission.to_public_dict()),
                    admission.admission_digest,
                    timestamp,
                ),
            )
            next_state = self._update_state(
                connection,
                row,
                event_type="cell.tool_admitted",
                event_payload={
                    "action_id": request.request_id,
                    "request_digest": request.request_digest,
                    "admission_digest": admission.admission_digest,
                },
                tool_calls=state.tool_calls + 1,
                updated_at=timestamp,
            )
            connection.commit()
            return next_state
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def claim_tool_execution(
        self,
        permit: AgentOwnershipPermit,
        *,
        action_id: str,
        admission_digest: str,
        semantic_projection_digest: str,
    ):
        timestamp = self._timestamp()
        action = require_uuid4("action_id", action_id)
        admission = require_sha256("admission_digest", admission_digest)
        semantic = require_sha256(
            "semantic_projection_digest",
            semantic_projection_digest,
        )
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            projection, _ = self._verify_permit(
                connection,
                permit,
                observed_at=timestamp,
            )
            request = connection.execute(
                "SELECT * FROM hosted_tool_requests WHERE action_id=?",
                (action,),
            ).fetchone()
            if (
                request is None
                or request["agent_run_id"] != permit.agent_run_id
                or request["decision"] != "admitted"
                or request["admission_digest"] != admission
            ):
                raise HostedAgentCellStateError(
                    "tool execution has no exact durable admission"
                )
            if (
                connection.execute(
                    "SELECT 1 FROM hosted_tool_results WHERE action_id=?",
                    (action,),
                ).fetchone()
                is not None
            ):
                raise HostedAgentCellStateError("tool action is already terminal")
            if (
                connection.execute(
                    "SELECT 1 FROM hosted_tool_execution_claims WHERE action_id=?",
                    (action,),
                ).fetchone()
                is not None
            ):
                raise HostedAgentCellStateError("tool execution was already claimed")
            row = self._cell_row(connection, permit.agent_run_id)
            state = self._state_from_row(row)
            policy = HostedAgentCellPolicy.from_dict(json.loads(row["policy_json"]))
            self._verify_authority(
                projection,
                policy_digest=policy.policy_digest,
                operation="tool_execution",
            )
            if (
                state.status is not HostedAgentCellStatus.RUNNING
                or state.tool_calls > policy.max_tool_calls
                or state.provider_calls > policy.max_provider_calls
                or state.active_wall_ms >= round(policy.max_active_wall_seconds * 1000)
                or state.currency_cost_usd > policy.max_currency_cost_usd
            ):
                raise HostedAgentCellBudgetError(
                    "tool execution no longer fits current cell state"
                )
            next_state = self._update_state(
                connection,
                row,
                event_type="cell.tool_claimed",
                event_payload={
                    "action_id": action,
                    "admission_digest": admission,
                    "semantic_projection_digest": semantic,
                    "ownership_fencing_token": permit.fencing_token,
                },
                updated_at=timestamp,
            )
            claim_digest = canonical_record_digest(
                "macr.hosted-tool-execution-claim.v1",
                {
                    "action_id": action,
                    "admission_digest": admission,
                    "ownership_lease_id": permit.lease_id,
                    "ownership_fencing_token": permit.fencing_token,
                    "cell_state_digest": next_state.state_digest,
                    "semantic_projection_digest": semantic,
                    "claimed_at": timestamp,
                },
            )
            connection.execute(
                """INSERT INTO hosted_tool_execution_claims(
                    action_id, admission_digest, ownership_lease_id,
                    ownership_fencing_token, cell_state_digest,
                    semantic_projection_digest, claim_digest, claimed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    action,
                    admission,
                    permit.lease_id,
                    permit.fencing_token,
                    next_state.state_digest,
                    semantic,
                    claim_digest,
                    timestamp,
                ),
            )
            from .tools import _mint_execution_permit

            execution_permit = _mint_execution_permit(
                action_id=action,
                request_digest=request["model_request_digest"],
                admission_digest=admission,
                ownership=permit,
                cell_state_digest=next_state.state_digest,
                semantic_projection_digest=semantic,
            )
            connection.commit()
            return next_state, execution_permit
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def record_tool_denial(
        self,
        permit: AgentOwnershipPermit,
        *,
        step_index: int,
        request: HostedToolRequest,
        arguments_blob: HostedBlobRef,
        reason_code: str,
        reason_digest: str,
        context: HostedContextSection,
        context_blob: HostedBlobRef,
    ) -> None:
        timestamp = self._timestamp()
        code = require_non_empty("reason_code", reason_code, 128)
        digest = require_sha256("reason_digest", reason_digest)
        self._require_blob(
            arguments_blob,
            agent_run_id=permit.agent_run_id,
            role=HostedBlobRole.TOOL_ARGUMENTS,
        )
        self._require_blob(
            context_blob,
            agent_run_id=permit.agent_run_id,
            role=HostedBlobRole.CONTEXT,
        )
        if (
            self.blobs.read(arguments_blob)
            != canonical_json_bytes(dict(request.arguments))
            or self.blobs.read(context_blob) != context.canonical_bytes()
        ):
            raise HostedAgentCellStateError("tool denial private evidence conflicts")
        if (
            context.agent_run_id != permit.agent_run_id
            or context.kind is not HostedContextKind.TOOL_DENIAL
            or context_blob.role is not HostedBlobRole.CONTEXT
        ):
            raise ValueError("tool denial context is invalid")
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._verify_permit(connection, permit, observed_at=timestamp)
            row = self._cell_row(connection, permit.agent_run_id)
            state = self._state_from_row(row)
            if step_index != state.next_step - 1:
                raise HostedAgentCellStateError("tool denial step is stale")
            self._register_blob(connection, arguments_blob, timestamp)
            self._register_blob(connection, context_blob, timestamp)
            connection.execute(
                """INSERT INTO hosted_tool_requests(
                    action_id, agent_run_id, step_index,
                    model_request_digest, tool_id, arguments_blob_ref,
                    arguments_digest, proposal_json, proposal_digest,
                    admission_json, admission_digest, decision,
                    reason_code, reason_digest, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL,
                          'denied', ?, ?, ?)""",
                (
                    request.request_id,
                    permit.agent_run_id,
                    step_index,
                    request.request_digest,
                    request.tool_id,
                    arguments_blob.blob_ref,
                    request.arguments_digest,
                    code,
                    digest,
                    timestamp,
                ),
            )
            connection.execute(
                """INSERT INTO hosted_context_sections(
                    section_id, agent_run_id, kind, blob_ref, body_digest,
                    body_bytes, source_digest, section_digest, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    context.section_id,
                    context.agent_run_id,
                    context.kind.value,
                    context_blob.blob_ref,
                    context.body_digest,
                    len(context.body.encode("utf-8")),
                    context.source_digest,
                    context.section_digest,
                    context.created_at,
                ),
            )
            self._update_state(
                connection,
                row,
                event_type="cell.tool_denied",
                event_payload={
                    "action_id": request.request_id,
                    "request_digest": request.request_digest,
                    "reason_digest": digest,
                    "section_digest": context.section_digest,
                },
                updated_at=timestamp,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def finish_tool(
        self,
        permit: AgentOwnershipPermit,
        *,
        result: HostedToolResultRef,
        result_blob: HostedBlobRef | None,
        context: HostedContextSection,
        context_blob: HostedBlobRef,
        duration_ms: int,
    ) -> HostedAgentCellState:
        timestamp = self._timestamp()
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or duration_ms < 0
        ):
            raise ValueError("duration_ms must be non-negative")
        if context.kind not in {
            HostedContextKind.TOOL_RESULT,
            HostedContextKind.TOOL_DENIAL,
        }:
            raise ValueError("tool context has invalid kind")
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._verify_permit(connection, permit, observed_at=timestamp)
            row = self._cell_row(connection, permit.agent_run_id)
            request_row = connection.execute(
                "SELECT * FROM hosted_tool_requests WHERE action_id=?",
                (result.action_id,),
            ).fetchone()
            if (
                request_row is None
                or request_row["agent_run_id"] != permit.agent_run_id
            ):
                raise HostedAgentCellStateError("tool request evidence is missing")
            if request_row["decision"] != "admitted":
                raise HostedAgentCellStateError("denied tool cannot gain a result")
            claim = connection.execute(
                "SELECT * FROM hosted_tool_execution_claims WHERE action_id=?",
                (result.action_id,),
            ).fetchone()
            if (
                claim is None
                or claim["admission_digest"] != request_row["admission_digest"]
                or claim["ownership_lease_id"] != permit.lease_id
                or claim["ownership_fencing_token"] != permit.fencing_token
            ):
                raise HostedAgentCellStateError(
                    "tool result has no exact durable execution claim"
                )
            if (
                result.request_digest != request_row["model_request_digest"]
                or result.tool_id != request_row["tool_id"]
            ):
                raise HostedAgentCellStateError(
                    "tool result does not match its request"
                )
            if (
                connection.execute(
                    "SELECT 1 FROM hosted_tool_results WHERE action_id=?",
                    (result.action_id,),
                ).fetchone()
                is not None
            ):
                raise HostedAgentCellStateError("tool result is already terminal")
            if result.status is HostedToolResultStatus.COMPLETED:
                if result_blob is None:
                    raise ValueError("completed tool result lacks its blob")
                self._require_blob(
                    result_blob,
                    agent_run_id=permit.agent_run_id,
                    role=HostedBlobRole.TOOL_RESULT,
                )
                self._register_blob(connection, result_blob, timestamp)
            elif result_blob is not None:
                raise ValueError("failed tool result cannot carry bytes")
            self._require_blob(
                context_blob,
                agent_run_id=permit.agent_run_id,
                role=HostedBlobRole.CONTEXT,
            )
            result_payload = (
                None
                if result_blob is None
                else json.loads(self.blobs.read(result_blob).decode("utf-8"))
            )
            expected_context_body = canonical_json_bytes(
                {
                    "result_ref": result.to_public_dict(),
                    "payload": result_payload,
                }
            ).decode("utf-8")
            if (
                result_blob is not None
                and (
                    result.result_blob_ref != result_blob.blob_ref
                    or result.result_digest != result_blob.sha256
                    or result.result_bytes != result_blob.byte_count
                )
            ) or (
                context.kind is not HostedContextKind.TOOL_RESULT
                or context.source_ref != result.evidence_ref
                or context.source_digest != result.reference_digest
                or context.body != expected_context_body
                or context.created_at != result.observed_at
                or self.blobs.read(context_blob) != context.canonical_bytes()
            ):
                raise HostedAgentCellStateError(
                    "tool result context does not derive from exact evidence"
                )
            self._register_blob(connection, context_blob, timestamp)
            connection.execute(
                """INSERT INTO hosted_tool_results(
                    action_id, result_ref_json, reference_digest,
                    result_blob_ref, result_digest, result_bytes,
                    duration_ms, status, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.action_id,
                    _json_text(result.to_public_dict()),
                    result.reference_digest,
                    None if result_blob is None else result_blob.blob_ref,
                    result.result_digest,
                    result.result_bytes,
                    duration_ms,
                    result.status.value,
                    result.observed_at,
                ),
            )
            connection.execute(
                """INSERT INTO hosted_context_sections(
                    section_id, agent_run_id, kind, blob_ref, body_digest,
                    body_bytes, source_digest, section_digest, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    context.section_id,
                    context.agent_run_id,
                    context.kind.value,
                    context_blob.blob_ref,
                    context.body_digest,
                    len(context.body.encode("utf-8")),
                    context.source_digest,
                    context.section_digest,
                    context.created_at,
                ),
            )
            state = self._state_from_row(row)
            next_state = self._update_state(
                connection,
                row,
                event_type="cell.tool_completed",
                event_payload={
                    "action_id": result.action_id,
                    "reference_digest": result.reference_digest,
                    "section_digest": context.section_digest,
                    "duration_ms": duration_ms,
                    "status": result.status.value,
                },
                active_wall_ms=state.active_wall_ms + duration_ms,
                updated_at=timestamp,
            )
            connection.commit()
            return next_state
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _snapshot(self, connection, agent_run_id: str) -> tuple[dict[str, object], str]:
        state = self._state_from_row(self._cell_row(connection, agent_run_id))
        sections = [
            row["section_digest"]
            for row in connection.execute(
                """SELECT section_digest FROM hosted_context_sections
                WHERE agent_run_id=? ORDER BY sequence""",
                (agent_run_id,),
            ).fetchall()
        ]
        model = [
            {
                "request_digest": row["request_digest"],
                "terminal_state": row["terminal_state"],
                "result_digest": row["result_digest"],
                "failure_digest": row["failure_digest"],
            }
            for row in connection.execute(
                """SELECT d.step_index, d.request_digest, t.terminal_state,
                           t.result_digest, t.failure_digest
                FROM hosted_model_dispatches d
                LEFT JOIN hosted_model_terminals t USING(provider_invocation_id)
                WHERE d.agent_run_id=? ORDER BY d.step_index""",
                (agent_run_id,),
            ).fetchall()
        ]
        tools = [
            {
                "model_request_digest": row["model_request_digest"],
                "decision": row["decision"],
                "admission_digest": row["admission_digest"],
                "reason_digest": row["reason_digest"],
                "reference_digest": row["reference_digest"],
            }
            for row in connection.execute(
                """SELECT q.step_index, q.model_request_digest, q.decision,
                           q.admission_digest, q.reason_digest,
                           r.reference_digest
                FROM hosted_tool_requests q
                LEFT JOIN hosted_tool_results r USING(action_id)
                WHERE q.agent_run_id=? ORDER BY q.step_index, q.action_id""",
                (agent_run_id,),
            ).fetchall()
        ]
        snapshot = {
            "agent_run_id": agent_run_id,
            "policy_digest": state.policy_digest,
            "semantic_request_digest": state.semantic_request_digest,
            "next_step": state.next_step,
            "provider_calls": state.provider_calls,
            "tool_calls": state.tool_calls,
            "active_wall_ms": state.active_wall_ms,
            "currency_cost_usd": state.currency_cost_usd,
            "section_digests": sections,
            "model_records": model,
            "tool_records": tools,
        }
        return snapshot, canonical_record_digest(
            "macr.hosted-agent-cell.snapshot.v1",
            snapshot,
        )

    def create_checkpoint(
        self,
        permit: AgentOwnershipPermit,
        checkpoint: AgentCheckpoint,
    ) -> tuple[HostedAgentCellState, str]:
        if not isinstance(checkpoint, AgentCheckpoint):
            raise ValueError("checkpoint must be an AgentCheckpoint")
        timestamp = self._timestamp()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            projection, agent_row = self._verify_permit(
                connection,
                permit,
                observed_at=timestamp,
            )
            row = self._cell_row(connection, permit.agent_run_id)
            state = self._state_from_row(row)
            self._verify_authority(
                projection,
                policy_digest=state.policy_digest,
                operation="checkpoint",
            )
            if state.status not in {
                HostedAgentCellStatus.READY,
                HostedAgentCellStatus.RUNNING,
                HostedAgentCellStatus.BLOCKED,
            }:
                raise HostedAgentCheckpointError("cell cannot checkpoint now")
            if self._pending_counts(connection, permit.agent_run_id) != (0, 0):
                raise HostedAgentReconciliationRequired(
                    "checkpoint cannot include a pending operation"
                )
            if (
                require_uuid4("checkpoint_id", checkpoint.checkpoint_id)
                != checkpoint.checkpoint_id
                or checkpoint.agent_run_id != permit.agent_run_id
                or checkpoint.agent_run_epoch != projection.epoch
                or checkpoint.state_revision != projection.state_revision
                or checkpoint.goal_ref != projection.initial_header.goal.ref
                or checkpoint.goal_digest != projection.initial_header.goal.digest
                or checkpoint.authority_digest
                != projection.initial_header.authority.reference.digest
                or checkpoint.authority_ref
                != (
                    "authority:"
                    f"{projection.initial_header.authority.reference.source_kind}:"
                    f"{projection.initial_header.authority.reference.source_id}:"
                    f"{projection.initial_header.authority.reference.revision}"
                )
                or checkpoint.authority_revision
                != projection.initial_header.authority.reference.revision
                or checkpoint.authority_epoch
                != projection.initial_header.authority.reference.epoch
                or checkpoint.budget_ref != projection.initial_header.budget.ref
                or checkpoint.budget_digest != projection.initial_header.budget.digest
                or checkpoint.budget_revision
                != projection.initial_header.budget.revision
                or checkpoint.semantic_state_ref != agent_row["semantic_state_ref"]
                or checkpoint.semantic_state_digest
                != agent_row["semantic_state_digest"]
                or checkpoint.semantic_state_revision
                != agent_row["semantic_state_revision"]
                or checkpoint.active_plan_ref
                != (
                    None
                    if projection.initial_header.active_plan is None
                    else projection.initial_header.active_plan.ref
                )
                or checkpoint.active_plan_digest
                != (
                    None
                    if projection.initial_header.active_plan is None
                    else projection.initial_header.active_plan.digest
                )
                or checkpoint.active_plan_revision
                != (
                    None
                    if projection.initial_header.active_plan is None
                    else projection.initial_header.active_plan.revision
                )
                or checkpoint.world_basis_refs
                != tuple(
                    sorted(
                        item.ref for item in projection.initial_header.world_bindings
                    )
                )
                or checkpoint.memory_binding_digests
                != tuple(
                    sorted(
                        item.binding_digest
                        for item in projection.initial_header.memory_bindings
                    )
                )
                or checkpoint.pending_action_refs
                or checkpoint.reconciliation_refs
                or checkpoint.verification_state_ref
                != f"hosted-cell-state:{state.state_digest}"
                or checkpoint.wake_condition_ref is not None
                or checkpoint.parent_checkpoint_ref
                != (
                    None
                    if state.latest_checkpoint_digest is None
                    else f"hosted-checkpoint:{state.latest_checkpoint_digest}"
                )
            ):
                raise HostedAgentCheckpointError("checkpoint bindings are stale")
            snapshot, snapshot_digest = self._snapshot(connection, permit.agent_run_id)
            existing = connection.execute(
                "SELECT checkpoint_digest FROM hosted_agent_checkpoints WHERE checkpoint_id=?",
                (checkpoint.checkpoint_id,),
            ).fetchone()
            if existing is not None:
                if existing["checkpoint_digest"] != checkpoint.checkpoint_digest:
                    raise HostedAgentCheckpointError("checkpoint identity conflicts")
                return state, snapshot_digest
            connection.execute(
                """INSERT INTO hosted_agent_checkpoints(
                    checkpoint_id, agent_run_id, cell_revision, checkpoint_json,
                    checkpoint_digest, cell_snapshot_json,
                    cell_snapshot_digest, parent_checkpoint_digest, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    checkpoint.checkpoint_id,
                    permit.agent_run_id,
                    state.cell_revision + 1,
                    _json_text(checkpoint.to_public_dict()),
                    checkpoint.checkpoint_digest,
                    _json_text(snapshot),
                    snapshot_digest,
                    state.latest_checkpoint_digest,
                    checkpoint.created_at,
                ),
            )
            next_state = self._update_state(
                connection,
                row,
                event_type="cell.checkpointed",
                event_payload={
                    "checkpoint_digest": checkpoint.checkpoint_digest,
                    "cell_snapshot_digest": snapshot_digest,
                },
                status=HostedAgentCellStatus.CHECKPOINTED,
                latest_checkpoint_digest=checkpoint.checkpoint_digest,
                updated_at=timestamp,
            )
            connection.commit()
            return next_state, snapshot_digest
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def rehydrate(
        self,
        permit: AgentOwnershipPermit,
        checkpoint_digest: str,
    ) -> HostedAgentCellState:
        timestamp = self._timestamp()
        selected = require_sha256("checkpoint_digest", checkpoint_digest)
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            projection, agent_row = self._verify_permit(
                connection,
                permit,
                observed_at=timestamp,
            )
            row = self._cell_row(connection, permit.agent_run_id)
            state = self._state_from_row(row)
            self._verify_authority(
                projection,
                policy_digest=state.policy_digest,
                operation="rehydrate",
            )
            if (
                state.status is not HostedAgentCellStatus.CHECKPOINTED
                or state.latest_checkpoint_digest != selected
            ):
                raise HostedAgentCheckpointError("cell is not at the named checkpoint")
            if self._pending_counts(connection, permit.agent_run_id) != (0, 0):
                raise HostedAgentReconciliationRequired(
                    "checkpoint has pending operations"
                )
            checkpoint_row = connection.execute(
                "SELECT * FROM hosted_agent_checkpoints WHERE checkpoint_digest=?",
                (selected,),
            ).fetchone()
            if checkpoint_row is None:
                raise HostedAgentCheckpointError("checkpoint evidence is missing")
            checkpoint = AgentCheckpoint.from_dict(
                json.loads(checkpoint_row["checkpoint_json"])
            )
            snapshot, snapshot_digest = self._snapshot(connection, permit.agent_run_id)
            if (
                checkpoint.checkpoint_digest != selected
                or checkpoint_row["checkpoint_digest"] != selected
                or checkpoint_row["cell_snapshot_digest"] != snapshot_digest
                or _json_text(snapshot) != checkpoint_row["cell_snapshot_json"]
                or checkpoint.agent_run_epoch >= permit.epoch
                or checkpoint.agent_run_id != permit.agent_run_id
                or checkpoint.goal_digest != projection.initial_header.goal.digest
                or checkpoint.authority_digest
                != projection.initial_header.authority.reference.digest
                or checkpoint.budget_digest != projection.initial_header.budget.digest
                or checkpoint.semantic_state_ref != agent_row["semantic_state_ref"]
                or checkpoint.semantic_state_digest
                != agent_row["semantic_state_digest"]
                or checkpoint.semantic_state_revision
                != agent_row["semantic_state_revision"]
            ):
                raise HostedAgentCheckpointError("checkpoint reconstruction diverged")
            rehydration_id = str(uuid.uuid4())
            receipt = canonical_record_digest(
                "macr.hosted-agent-cell.rehydration.v1",
                {
                    "rehydration_id": rehydration_id,
                    "agent_run_id": permit.agent_run_id,
                    "checkpoint_digest": selected,
                    "previous_epoch": checkpoint.agent_run_epoch,
                    "new_epoch": permit.epoch,
                    "fencing_token": permit.fencing_token,
                    "rehydrated_at": timestamp,
                },
            )
            connection.execute(
                """INSERT INTO hosted_agent_rehydrations(
                    rehydration_id, agent_run_id, cell_revision, checkpoint_digest,
                    previous_epoch, new_epoch, fencing_token,
                    receipt_digest, rehydrated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rehydration_id,
                    permit.agent_run_id,
                    state.cell_revision + 1,
                    selected,
                    checkpoint.agent_run_epoch,
                    permit.epoch,
                    permit.fencing_token,
                    receipt,
                    timestamp,
                ),
            )
            next_state = self._update_state(
                connection,
                row,
                event_type="cell.rehydrated",
                event_payload={
                    "checkpoint_digest": selected,
                    "receipt_digest": receipt,
                    "previous_epoch": checkpoint.agent_run_epoch,
                    "new_epoch": permit.epoch,
                },
                status=HostedAgentCellStatus.RUNNING,
                updated_at=timestamp,
            )
            connection.commit()
            return next_state
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _valid_evidence_refs_on_connection(
        connection,
        agent_run_id: str,
    ) -> frozenset[str]:
        refs = {
            f"hosted-context:{row['section_id']}"
            for row in connection.execute(
                "SELECT section_id FROM hosted_context_sections WHERE agent_run_id=?",
                (agent_run_id,),
            ).fetchall()
        }
        refs.update(
            f"hosted-tool-result:{row['action_id']}"
            for row in connection.execute(
                """SELECT r.action_id FROM hosted_tool_results r
                JOIN hosted_tool_requests q USING(action_id)
                WHERE q.agent_run_id=?""",
                (agent_run_id,),
            ).fetchall()
        )
        return frozenset(refs)

    def valid_evidence_refs(self, agent_run_id: str) -> frozenset[str]:
        run_id = require_uuid4("agent_run_id", agent_run_id)
        connection = self.database.connect()
        try:
            return self._valid_evidence_refs_on_connection(connection, run_id)
        finally:
            connection.close()

    def _last_model_decision(self, connection, agent_run_id: str):
        latest = connection.execute(
            """SELECT t.result_json, t.decision_blob_ref
            FROM hosted_model_dispatches d
            JOIN hosted_model_terminals t USING(provider_invocation_id)
            WHERE d.agent_run_id=? AND t.terminal_state='completed'
            ORDER BY d.step_index DESC LIMIT 1""",
            (agent_run_id,),
        ).fetchone()
        if latest is None:
            raise HostedAgentCellStateError("cell has no completed model decision")
        model_result = json.loads(latest["result_json"])
        decision_blob = self._blob_from_ref(
            connection,
            latest["decision_blob_ref"],
            expected_run_id=agent_run_id,
            expected_role=HostedBlobRole.MODEL_DECISION,
        )
        decision = HostedModelDecision.from_private_dict(
            json.loads(self.blobs.read(decision_blob).decode("utf-8"))
        )
        if model_result.get("decision_digest") != decision.decision_digest:
            raise HostedAgentCellStateError("stored model decision conflicts")
        return decision

    def _latest_model_context_evidence_refs(
        self,
        connection,
        agent_run_id: str,
    ) -> frozenset[str]:
        latest = connection.execute(
            """SELECT d.request_json, d.context_digest
            FROM hosted_model_dispatches d
            JOIN hosted_model_terminals t USING(provider_invocation_id)
            WHERE d.agent_run_id=? AND t.terminal_state='completed'
            ORDER BY d.step_index DESC LIMIT 1""",
            (agent_run_id,),
        ).fetchone()
        if latest is None:
            raise HostedAgentCellStateError("cell has no completed model context")
        try:
            request = json.loads(latest["request_json"])
            blob_ref = request["context_blob_ref"]
            context_digest = request["context_digest"]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise HostedAgentCellStateError("model context request is invalid") from exc
        if context_digest != latest["context_digest"]:
            raise HostedAgentCellStateError("model context request digest conflicts")
        blob = self._blob_from_ref(
            connection,
            blob_ref,
            expected_run_id=agent_run_id,
            expected_role=HostedBlobRole.PROJECTION,
        )
        envelope_row = connection.execute(
            """SELECT * FROM hosted_context_envelopes
            WHERE envelope_digest=? AND agent_run_id=?""",
            (context_digest, agent_run_id),
        ).fetchone()
        if envelope_row is None or envelope_row["blob_ref"] != blob.blob_ref:
            raise HostedAgentCellStateError(
                "model context envelope evidence is missing"
            )
        payload = self.blobs.read(blob)
        try:
            document = json.loads(payload)
            claimed_digest = document.pop("envelope_digest")
            causal_digest = document["causal_digest"]
            sections = document["context_sections"]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise HostedAgentCellStateError(
                "model context envelope is invalid"
            ) from exc
        encoded = canonical_json_bytes(document)
        expected_digest = canonical_record_digest(
            "macr.hosted-context-envelope.v1",
            {
                "causal_digest": causal_digest,
                "payload_sha256": hashlib.sha256(encoded).hexdigest(),
                "payload_bytes": len(encoded),
            },
        )
        if claimed_digest != context_digest or expected_digest != context_digest:
            raise HostedAgentCellStateError("model context envelope identity conflicts")
        if not isinstance(sections, list):
            raise HostedAgentCellStateError("model context sections are invalid")
        refs: set[str] = set()
        for value in sections:
            try:
                section = HostedContextSection.from_private_dict(value)
            except (TypeError, ValueError) as exc:
                raise HostedAgentCellStateError(
                    "model context section is invalid"
                ) from exc
            refs.add(section.evidence_ref)
            if section.kind is HostedContextKind.TOOL_RESULT:
                try:
                    result_ref = json.loads(section.body)["result_ref"]
                    evidence_ref = result_ref["evidence_ref"]
                except (KeyError, TypeError, json.JSONDecodeError) as exc:
                    raise HostedAgentCellStateError(
                        "model tool-result context is invalid"
                    ) from exc
                if evidence_ref != section.source_ref:
                    raise HostedAgentCellStateError(
                        "model tool-result evidence reference conflicts"
                    )
                refs.add(evidence_ref)
        return frozenset(refs)

    def create_completion_intent(
        self,
        permit: AgentOwnershipPermit,
        *,
        candidate_run_id: str,
        decision: HostedModelDecision,
    ) -> dict[str, object]:
        timestamp = self._timestamp()
        candidate = require_uuid4("candidate_run_id", candidate_run_id)
        if (
            not isinstance(decision, HostedModelDecision)
            or decision.final_candidate is None
            or not decision.evidence_refs
        ):
            raise ValueError("completion intent requires one final decision")
        answer_digest = hashlib.sha256(
            decision.final_candidate.encode("utf-8")
        ).hexdigest()
        refs = tuple(decision.evidence_refs)
        refs_digest = canonical_record_digest(
            "macr.hosted-agent-cell.completion-evidence.v1",
            {"evidence_refs": list(refs)},
        )
        intent = {
            "candidate_run_id": candidate,
            "agent_run_id": permit.agent_run_id,
            "decision_digest": decision.decision_digest,
            "final_answer_digest": answer_digest,
            "evidence_refs": list(refs),
            "evidence_refs_digest": refs_digest,
            "created_at": timestamp,
        }
        intent_digest = canonical_record_digest(
            "macr.hosted-agent-cell.completion-intent.v1",
            intent,
        )
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            projection, _ = self._verify_permit(
                connection,
                permit,
                observed_at=timestamp,
            )
            row = self._cell_row(connection, permit.agent_run_id)
            state = self._state_from_row(row)
            self._verify_authority(
                projection,
                policy_digest=state.policy_digest,
                operation="completion_intent",
            )
            if state.status is not HostedAgentCellStatus.RUNNING:
                raise HostedAgentCellStateError("cell cannot intend completion")
            if self._pending_counts(connection, permit.agent_run_id) != (0, 0):
                raise HostedAgentReconciliationRequired(
                    "completion intent has pending operations"
                )
            if self._last_model_decision(connection, permit.agent_run_id) != decision:
                raise HostedAgentCellStateError(
                    "completion intent does not bind last model decision"
                )
            valid = self._latest_model_context_evidence_refs(
                connection,
                permit.agent_run_id,
            )
            if any(item not in valid for item in refs):
                raise HostedAgentCellStateError(
                    "completion intent cites unknown evidence"
                )
            existing = connection.execute(
                """SELECT * FROM hosted_agent_completion_intents
                WHERE agent_run_id=?""",
                (permit.agent_run_id,),
            ).fetchone()
            if existing is not None:
                if existing["intent_digest"] != intent_digest:
                    raise HostedAgentCellStateError(
                        "completion intent identity conflicts"
                    )
                connection.commit()
                return {**intent, "intent_digest": intent_digest}
            connection.execute(
                """INSERT INTO hosted_agent_completion_intents(
                    candidate_run_id, agent_run_id, decision_digest,
                    final_answer_digest, evidence_refs_json,
                    evidence_refs_digest, intent_digest, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    candidate,
                    permit.agent_run_id,
                    decision.decision_digest,
                    answer_digest,
                    _json_text(list(refs)),
                    refs_digest,
                    intent_digest,
                    timestamp,
                ),
            )
            self._update_state(
                connection,
                row,
                event_type="cell.completion_intent",
                event_payload={
                    "candidate_run_id": candidate,
                    "decision_digest": decision.decision_digest,
                    "final_answer_digest": answer_digest,
                    "evidence_refs_digest": refs_digest,
                    "intent_digest": intent_digest,
                },
                updated_at=timestamp,
            )
            connection.commit()
            return {**intent, "intent_digest": intent_digest}
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def read_completion_intent(
        self,
        agent_run_id: str,
    ) -> dict[str, object] | None:
        run_id = require_uuid4("agent_run_id", agent_run_id)
        connection = self.database.connect()
        try:
            row = connection.execute(
                "SELECT * FROM hosted_agent_completion_intents WHERE agent_run_id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            refs = json.loads(row["evidence_refs_json"])
            intent = {
                "candidate_run_id": row["candidate_run_id"],
                "agent_run_id": run_id,
                "decision_digest": row["decision_digest"],
                "final_answer_digest": row["final_answer_digest"],
                "evidence_refs": refs,
                "evidence_refs_digest": row["evidence_refs_digest"],
                "created_at": row["created_at"],
            }
            expected = canonical_record_digest(
                "macr.hosted-agent-cell.completion-intent.v1",
                intent,
            )
            if expected != row["intent_digest"]:
                raise HostedAgentCellStateError("completion intent is invalid")
            decision = self._last_model_decision(connection, run_id)
            valid = self._latest_model_context_evidence_refs(
                connection,
                run_id,
            )
            if (
                decision.decision_digest != row["decision_digest"]
                or hashlib.sha256(decision.final_candidate.encode("utf-8")).hexdigest()
                != row["final_answer_digest"]
                or list(decision.evidence_refs) != refs
                or any(item not in valid for item in refs)
            ):
                raise HostedAgentCellStateError(
                    "completion intent and model decision diverge"
                )
            return {**intent, "intent_digest": expected, "decision": decision}
        finally:
            connection.close()

    def prepare_completion(
        self,
        permit: AgentOwnershipPermit,
        *,
        candidate_run_id: str,
        capture: CandidateCapture,
        decision: HostedModelDecision,
        evidence_refs: tuple[str, ...],
    ) -> HostedAgentCellState:
        timestamp = self._timestamp()
        candidate = require_uuid4("candidate_run_id", candidate_run_id)
        if (
            not isinstance(capture, CandidateCapture)
            or capture.run_id != candidate
            or capture.provider_id != "hosted_agent_cell"
            or not isinstance(decision, HostedModelDecision)
            or decision.final_candidate is None
            or hashlib.sha256(decision.final_candidate.encode("utf-8")).hexdigest()
            != capture.sha256
        ):
            raise ValueError("capture must belong to candidate_run_id")
        if not evidence_refs:
            raise HostedAgentCellStateError("final candidate cites no evidence")
        refs_digest = canonical_record_digest(
            "macr.hosted-agent-cell.completion-evidence.v1",
            {"evidence_refs": list(evidence_refs)},
        )
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            projection, _ = self._verify_permit(
                connection,
                permit,
                observed_at=timestamp,
            )
            row = self._cell_row(connection, permit.agent_run_id)
            state = self._state_from_row(row)
            policy = HostedAgentCellPolicy.from_dict(json.loads(row["policy_json"]))
            self._verify_authority(
                projection,
                policy_digest=state.policy_digest,
                operation="completion_prepare",
            )
            if state.status is not HostedAgentCellStatus.RUNNING:
                raise HostedAgentCellStateError("cell cannot complete now")
            if self._pending_counts(connection, permit.agent_run_id) != (0, 0):
                raise HostedAgentReconciliationRequired(
                    "completion has pending operations"
                )
            valid = self._latest_model_context_evidence_refs(
                connection,
                permit.agent_run_id,
            )
            if any(item not in valid for item in evidence_refs):
                raise HostedAgentCellStateError(
                    "completion evidence was not observed by the final model"
                )
            expected_task_digest = canonical_record_digest(
                "macr.hosted-agent-cell.final-task.v1",
                {
                    "agent_run_id": permit.agent_run_id,
                    "policy_digest": policy.policy_digest,
                    "evidence_refs": list(evidence_refs),
                },
            )
            if (
                capture.task_digest != expected_task_digest
                or capture.approval_digest
                != projection.initial_header.authority.reference.digest
            ):
                raise HostedAgentCellStateError(
                    "completion capture provenance conflicts"
                )
            intent_row = connection.execute(
                """SELECT * FROM hosted_agent_completion_intents
                WHERE agent_run_id=?""",
                (permit.agent_run_id,),
            ).fetchone()
            if (
                intent_row is None
                or intent_row["candidate_run_id"] != candidate
                or intent_row["decision_digest"] != decision.decision_digest
                or intent_row["final_answer_digest"] != capture.sha256
                or intent_row["evidence_refs_digest"] != refs_digest
                or json.loads(intent_row["evidence_refs_json"]) != list(evidence_refs)
            ):
                raise HostedAgentCellStateError(
                    "completion has no exact durable intent"
                )
            latest = connection.execute(
                """SELECT t.result_json, t.decision_blob_ref
                FROM hosted_model_dispatches d
                JOIN hosted_model_terminals t USING(provider_invocation_id)
                WHERE d.agent_run_id=? AND t.terminal_state='completed'
                ORDER BY d.step_index DESC LIMIT 1""",
                (permit.agent_run_id,),
            ).fetchone()
            if latest is None:
                raise HostedAgentCellStateError(
                    "final candidate has no completed model decision"
                )
            model_result = json.loads(latest["result_json"])
            decision_blob = self._blob_from_ref(
                connection,
                latest["decision_blob_ref"],
                expected_run_id=permit.agent_run_id,
                expected_role=HostedBlobRole.MODEL_DECISION,
            )
            stored_decision = HostedModelDecision.from_private_dict(
                json.loads(self.blobs.read(decision_blob).decode("utf-8"))
            )
            if (
                model_result.get("decision_digest") != decision.decision_digest
                or stored_decision != decision
                or tuple(decision.evidence_refs) != tuple(evidence_refs)
            ):
                raise HostedAgentCellStateError(
                    "completion does not bind the exact final model decision"
                )
            connection.execute(
                """INSERT INTO hosted_agent_completions(
                    candidate_run_id, agent_run_id, final_capture_id,
                    final_answer_digest, decision_digest,
                    evidence_refs_digest, prepared_at,
                    finalized_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
                (
                    candidate,
                    permit.agent_run_id,
                    capture.capture_id,
                    capture.sha256,
                    decision.decision_digest,
                    refs_digest,
                    timestamp,
                ),
            )
            next_state = self._update_state(
                connection,
                row,
                event_type="cell.completion_prepared",
                event_payload={
                    "candidate_run_id": candidate,
                    "final_capture_id": capture.capture_id,
                    "final_answer_digest": capture.sha256,
                    "decision_digest": decision.decision_digest,
                    "evidence_refs_digest": refs_digest,
                },
                status=HostedAgentCellStatus.COMPLETION_PENDING,
                candidate_run_id=candidate,
                final_capture_id=capture.capture_id,
                final_answer_digest=capture.sha256,
                updated_at=timestamp,
            )
            connection.commit()
            return next_state
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def finalize_completion(self, agent_run_id: str) -> HostedAgentCellState:
        timestamp = self._timestamp()
        run_id = require_uuid4("agent_run_id", agent_run_id)
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._cell_row(connection, run_id)
            state = self._state_from_row(row)
            if state.status is HostedAgentCellStatus.COMPLETED:
                connection.commit()
                return state
            if state.status is not HostedAgentCellStatus.COMPLETION_PENDING:
                raise HostedAgentCellStateError("cell has no pending completion")
            agent_row = connection.execute(
                "SELECT * FROM agent_runs WHERE agent_run_id=?",
                (run_id,),
            ).fetchone()
            projection = self.agent_store._projection_from_row(agent_row)
            if projection.state is not AgentRunState.COMPLETED:
                raise HostedAgentCellStateError("AgentRun is not completed")
            event = connection.execute(
                """SELECT payload_json FROM agent_events
                WHERE agent_run_id=? AND event_type='agent.completed'
                ORDER BY sequence DESC LIMIT 1""",
                (run_id,),
            ).fetchone()
            if event is None:
                raise HostedAgentCellStateError("AgentRun completion event is missing")
            payload = json.loads(event["payload_json"])
            if (
                payload.get("evidence_ref") != f"candidate:{state.final_capture_id}"
                or payload.get("evidence_digest") != state.final_answer_digest
            ):
                raise HostedAgentCellStateError(
                    "AgentRun completion evidence conflicts"
                )
            connection.execute(
                """UPDATE hosted_agent_completions SET finalized_at=?
                WHERE agent_run_id=? AND finalized_at IS NULL""",
                (timestamp, run_id),
            )
            next_state = self._update_state(
                connection,
                row,
                event_type="cell.completed",
                event_payload={
                    "final_capture_id": state.final_capture_id,
                    "final_answer_digest": state.final_answer_digest,
                },
                status=HostedAgentCellStatus.COMPLETED,
                updated_at=timestamp,
            )
            connection.commit()
            return next_state
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
