from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from ..._v07_contracts import canonical_record_digest, require_non_empty
from ...agent.contracts import AgentRunState
from ...agent.ownership import AgentOwnershipPermit
from ...agent.service import AgentStateService
from ...candidate_vault import CandidateCapture, CandidateVault
from ...canonical import canonical_json_bytes
from ...semantic.projection import SemanticContextProjector
from ...temporal import AgentCheckpoint
from .blobs import HostedAgentBlobStore
from .context import HostedContextBuilder
from .contracts import (
    HostedAgentCellPolicy,
    HostedAgentCellState,
    HostedAgentCellStatus,
    HostedBlobRole,
    HostedContextKind,
    HostedContextSection,
    HostedDecisionKind,
    HostedModelRequest,
    HostedToolResultRef,
    HostedToolResultStatus,
)
from .errors import (
    HostedAgentCellBudgetError,
    HostedAgentCellStateError,
    HostedAgentReconciliationRequired,
    HostedModelProtocolError,
    HostedToolDeniedError,
)
from .model import (
    HostedModelInvocationError,
    HostedModelPort,
    HostedRawModelResponse,
)
from .store import HostedAgentCellStore
from .tools import HostedActionGate


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class HostedAgentActivationResult:
    agent_run_id: str
    status: str
    cell_state: HostedAgentCellState
    checkpoint_digest: str | None
    candidate: CandidateCapture | None
    failure_code: str | None


class HostedAgentCellRunner:
    def __init__(
        self,
        agent: AgentStateService,
        store: HostedAgentCellStore,
        semantic_projector: SemanticContextProjector,
        candidate_vault: CandidateVault,
        action_gate: HostedActionGate,
        *,
        now: Callable[[], datetime] = _utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        uuid_factory: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(agent, AgentStateService):
            raise ValueError("agent must be an AgentStateService")
        if not isinstance(store, HostedAgentCellStore):
            raise ValueError("store must be a HostedAgentCellStore")
        if agent.store.database.path != store.database.path:
            raise ValueError("Agent and hosted cell stores must share one database")
        if not isinstance(semantic_projector, SemanticContextProjector):
            raise ValueError("semantic_projector is invalid")
        if not isinstance(candidate_vault, CandidateVault):
            raise ValueError("candidate_vault must be a CandidateVault")
        if not isinstance(action_gate, HostedActionGate):
            raise ValueError("action_gate must be a HostedActionGate")
        self.agent = agent
        self.store = store
        self.semantic_projector = semantic_projector
        self.candidate_vault = candidate_vault
        self.action_gate = action_gate
        self.context = HostedContextBuilder(store)
        self.blobs: HostedAgentBlobStore = store.blobs
        self._now = now
        self._monotonic = monotonic
        self._uuid = uuid_factory or (lambda: str(uuid.uuid4()))

    def _fault(self, name: str) -> None:
        """Failure-injection seam; production is a no-op."""

    def _timestamp(self) -> str:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("hosted Agent runner clock must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()

    def attach(
        self,
        permit: AgentOwnershipPermit,
        policy: HostedAgentCellPolicy,
        semantic_request,
        sections: tuple[HostedContextSection, ...],
    ) -> HostedAgentCellState:
        if policy.tool_catalog_digest != self.action_gate.tools.catalog.catalog_digest:
            raise HostedAgentCellStateError("cell policy tool catalog is stale")
        if any(
            tool_id
            not in {item.tool_id for item in self.action_gate.tools.catalog.tools}
            for tool_id in policy.allowed_tool_ids
        ):
            raise HostedAgentCellStateError("cell policy names an unknown tool")
        self.semantic_projector.project(semantic_request)
        return self.store.attach(permit, policy, semantic_request, sections)

    def _budget_exhausted(
        self,
        state: HostedAgentCellState,
        policy: HostedAgentCellPolicy,
    ) -> str | None:
        if state.next_step > policy.max_steps:
            return "max_steps_exhausted"
        if state.provider_calls >= policy.max_provider_calls:
            return "provider_calls_exhausted"
        if state.tool_calls > policy.max_tool_calls:
            return "tool_calls_exhausted"
        if state.active_wall_ms >= round(policy.max_active_wall_seconds * 1000):
            return "active_wall_exhausted"
        if state.currency_cost_usd > policy.max_currency_cost_usd:
            return "currency_budget_exceeded"
        return None

    def _checkpoint(
        self,
        permit: AgentOwnershipPermit,
        *,
        failure_code: str | None,
    ) -> HostedAgentActivationResult:
        projection = self.agent.get_agent_run(permit.agent_run_id)
        state = self.store.read_state(permit.agent_run_id)
        request = self.store.read_semantic_request(permit.agent_run_id)
        header = projection.initial_header
        active_plan = header.active_plan
        checkpoint = AgentCheckpoint(
            checkpoint_id=self._uuid(),
            agent_run_id=permit.agent_run_id,
            agent_run_epoch=projection.epoch,
            state_revision=projection.state_revision,
            goal_ref=header.goal.ref,
            goal_digest=header.goal.digest,
            authority_ref=(
                f"authority:{header.authority.reference.source_kind}:"
                f"{header.authority.reference.source_id}:"
                f"{header.authority.reference.revision}"
            ),
            authority_digest=header.authority.reference.digest,
            authority_revision=header.authority.reference.revision,
            authority_epoch=header.authority.reference.epoch,
            budget_ref=header.budget.ref,
            budget_digest=header.budget.digest,
            budget_revision=header.budget.revision,
            semantic_state_ref=f"semantic-graph:{request.graph_id}",
            semantic_state_digest=request.graph_digest,
            semantic_state_revision=request.graph_revision,
            active_plan_ref=None if active_plan is None else active_plan.ref,
            active_plan_digest=None if active_plan is None else active_plan.digest,
            active_plan_revision=None if active_plan is None else active_plan.revision,
            world_basis_refs=tuple(item.ref for item in header.world_bindings),
            memory_binding_digests=tuple(
                item.binding_digest for item in header.memory_bindings
            ),
            pending_action_refs=(),
            reconciliation_refs=(),
            verification_state_ref=f"hosted-cell-state:{state.state_digest}",
            wake_condition_ref=None,
            parent_checkpoint_ref=(
                None
                if state.latest_checkpoint_digest is None
                else f"hosted-checkpoint:{state.latest_checkpoint_digest}"
            ),
            created_at=self._timestamp(),
        )
        checkpointed, _ = self.store.create_checkpoint(permit, checkpoint)
        self.agent.release_agent_run(permit)
        return HostedAgentActivationResult(
            agent_run_id=permit.agent_run_id,
            status="checkpointed",
            cell_state=checkpointed,
            checkpoint_digest=checkpoint.checkpoint_digest,
            candidate=None,
            failure_code=failure_code,
        )

    def checkpoint_activation(
        self,
        permit: AgentOwnershipPermit,
    ) -> HostedAgentActivationResult:
        return self._checkpoint(permit, failure_code=None)

    def run_activation(
        self,
        permit: AgentOwnershipPermit,
        model: HostedModelPort,
    ) -> HostedAgentActivationResult:
        policy = self.store.read_policy(permit.agent_run_id)
        if model.provider_id != policy.provider_id or model.model_id != policy.model_id:
            raise HostedAgentCellStateError("hosted model port identity conflicts")
        semantic_request = self.store.read_semantic_request(permit.agent_run_id)
        while True:
            agent_projection = self.agent.get_agent_run(permit.agent_run_id)
            if (
                agent_projection.state is not AgentRunState.ACTIVE
                or agent_projection.epoch != permit.epoch
            ):
                raise HostedAgentCellStateError("AgentRun is not owned and active")
            state = self.store.read_state(permit.agent_run_id)
            if self.store.read_completion_intent(permit.agent_run_id) is not None:
                return self._recover_completion(permit, policy)
            pending = self.store.mark_pending_reconciliation(permit)
            if pending is not None:
                self.agent.release_agent_run(permit)
                return HostedAgentActivationResult(
                    permit.agent_run_id,
                    "reconciliation_required",
                    pending,
                    None,
                    None,
                    "PendingOperationWithoutTerminal",
                )
            if state.status is HostedAgentCellStatus.RECONCILIATION_REQUIRED:
                raise HostedAgentReconciliationRequired(
                    "cell has unresolved provider/tool dispatch"
                )
            if state.status is HostedAgentCellStatus.CHECKPOINTED:
                raise HostedAgentCellStateError(
                    "checkpointed cell must be explicitly rehydrated"
                )
            budget_code = self._budget_exhausted(state, policy)
            if budget_code is not None:
                return self._checkpoint(permit, failure_code=budget_code)
            semantic_projection = self.semantic_projector.project(semantic_request)
            materialized = self.context.build(
                permit=permit,
                state=state,
                policy=policy,
                semantic_projection=semantic_projection,
                tool_catalog=self.action_gate.tools.catalog,
                agent_run_epoch=agent_projection.epoch,
                agent_state_revision=agent_projection.state_revision,
                created_at=self._timestamp(),
            )
            invocation_id = self._uuid()
            model_request = HostedModelRequest(
                provider_invocation_id=invocation_id,
                agent_run_id=permit.agent_run_id,
                agent_run_epoch=agent_projection.epoch,
                agent_state_revision=agent_projection.state_revision,
                step_index=state.next_step,
                provider_id=policy.provider_id,
                model_id=policy.model_id,
                context_blob_ref=materialized.blob.blob_ref,
                context_digest=materialized.envelope_digest,
                context_bytes=len(materialized.payload),
                policy_digest=policy.policy_digest,
                model_token_policy_digest=(policy.model_token_policy_digest),
                provider_execution_profile_digest=(
                    policy.provider_execution_profile_digest
                ),
                prompt_compiler_version=policy.prompt_compiler_version,
                delegation_class=policy.delegation_class,
                privacy=policy.privacy,
                provider_tier_binding_digest=(policy.provider_tier_binding_digest),
                project_binding_digest=policy.project_binding_digest,
                admission_lane=policy.admission_lane,
                provider_admission_policy_digest=(
                    policy.provider_admission_policy_digest
                ),
                max_latency_s=policy.max_latency_s,
                max_output_tokens=policy.max_output_tokens,
                max_provider_context_tokens=(policy.max_provider_context_tokens),
                cost_ceiling_usd=policy.max_provider_call_cost_usd,
            )
            self.store.begin_model_attempt(permit, model_request)
            try:
                raw = model.invoke(model_request, materialized.payload)
                if not isinstance(raw, HostedRawModelResponse):
                    raise HostedModelInvocationError(
                        "InvalidModelPortResult",
                        network_attempted=None,
                        response_received=None,
                        duration_ms=0,
                    )
                if (
                    raw.provider_invocation_id != invocation_id
                    or raw.provider_id != policy.provider_id
                    or raw.model_id != policy.model_id
                ):
                    raise HostedModelInvocationError(
                        "ModelIdentityMismatch",
                        network_attempted=raw.network_attempted,
                        response_received=raw.response_received,
                        duration_ms=raw.duration_ms,
                        currency_cost_usd=raw.currency_cost_usd,
                        raw_response=raw.raw_decision,
                    )
            except HostedModelInvocationError as exc:
                bounded_raw = (
                    exc.raw_response
                    if exc.raw_response is not None
                    and len(exc.raw_response) <= policy.max_raw_model_response_bytes
                    else None
                )
                raw_blob = (
                    None
                    if bounded_raw is None
                    else self.blobs.write(
                        permit.agent_run_id,
                        HostedBlobRole.MODEL_RAW,
                        bounded_raw,
                    )
                )
                failure_digest = canonical_record_digest(
                    "macr.hosted-model-failure.v1",
                    {
                        "provider_invocation_id": invocation_id,
                        "failure_code": exc.failure_code,
                        "network_attempted": exc.network_attempted,
                        "response_received": exc.response_received,
                        "duration_ms": exc.duration_ms,
                        "currency_cost_usd": exc.currency_cost_usd,
                        "raw_digest": None if raw_blob is None else raw_blob.sha256,
                    },
                )
                ambiguous = exc.network_attempted is not False and (
                    exc.response_received is not True or exc.currency_cost_usd is None
                )
                failed = self.store.finish_model_failure(
                    permit,
                    invocation_id,
                    failure_code=exc.failure_code,
                    failure_digest=failure_digest,
                    duration_ms=exc.duration_ms,
                    ambiguous=ambiguous,
                    currency_cost_usd=exc.currency_cost_usd,
                    network_attempted=exc.network_attempted,
                    response_received=exc.response_received,
                    raw_blob=raw_blob,
                )
                if ambiguous:
                    self.agent.release_agent_run(permit)
                    return HostedAgentActivationResult(
                        permit.agent_run_id,
                        "reconciliation_required",
                        failed,
                        None,
                        None,
                        exc.failure_code,
                    )
                return self._checkpoint(permit, failure_code=exc.failure_code)
            if len(raw.raw_decision) > policy.max_raw_model_response_bytes:
                failure_code = "RawModelResponseTooLarge"
                failure_digest = canonical_record_digest(
                    "macr.hosted-model-size-failure.v1",
                    {
                        "provider_invocation_id": invocation_id,
                        "observed_bytes": len(raw.raw_decision),
                        "maximum_bytes": policy.max_raw_model_response_bytes,
                    },
                )
                self.store.finish_model_failure(
                    permit,
                    invocation_id,
                    failure_code=failure_code,
                    failure_digest=failure_digest,
                    duration_ms=raw.duration_ms,
                    ambiguous=False,
                    currency_cost_usd=raw.currency_cost_usd,
                    network_attempted=raw.network_attempted,
                    response_received=raw.response_received,
                    raw_blob=None,
                )
                return self._checkpoint(permit, failure_code=failure_code)
            raw_blob = self.blobs.write(
                permit.agent_run_id,
                HostedBlobRole.MODEL_RAW,
                raw.raw_decision,
            )
            remaining_currency = max(
                0.0,
                float(policy.max_currency_cost_usd) - float(state.currency_cost_usd),
            )
            if (
                float(raw.currency_cost_usd) > float(model_request.cost_ceiling_usd)
                or float(raw.currency_cost_usd) > remaining_currency
            ):
                failure_code = "ModelCostCeilingExceeded"
                failure_digest = canonical_record_digest(
                    "macr.hosted-model-cost-failure.v1",
                    {
                        "provider_invocation_id": invocation_id,
                        "observed_cost_usd": raw.currency_cost_usd,
                        "per_call_ceiling_usd": model_request.cost_ceiling_usd,
                        "remaining_currency_usd": remaining_currency,
                        "raw_digest": raw_blob.sha256,
                    },
                )
                self.store.finish_model_failure(
                    permit,
                    invocation_id,
                    failure_code=failure_code,
                    failure_digest=failure_digest,
                    duration_ms=raw.duration_ms,
                    ambiguous=False,
                    currency_cost_usd=raw.currency_cost_usd,
                    network_attempted=raw.network_attempted,
                    response_received=raw.response_received,
                    raw_blob=raw_blob,
                )
                return self._checkpoint(permit, failure_code=failure_code)
            try:
                result = raw.compile(id_factory=self._uuid)
            except Exception as exc:
                failure_code = "HostedModelProtocolError"
                failure_digest = canonical_record_digest(
                    "macr.hosted-model-protocol-failure.v1",
                    {
                        "provider_invocation_id": invocation_id,
                        "failure_type": type(exc).__name__,
                        "raw_digest": raw_blob.sha256,
                    },
                )
                self.store.finish_model_failure(
                    permit,
                    invocation_id,
                    failure_code=failure_code,
                    failure_digest=failure_digest,
                    duration_ms=raw.duration_ms,
                    ambiguous=False,
                    currency_cost_usd=raw.currency_cost_usd,
                    network_attempted=raw.network_attempted,
                    response_received=raw.response_received,
                    raw_blob=raw_blob,
                )
                return self._checkpoint(permit, failure_code=failure_code)
            decision_blob = self.blobs.write(
                permit.agent_run_id,
                HostedBlobRole.MODEL_DECISION,
                result.decision.canonical_bytes(),
            )
            state = self.store.finish_model_success(
                permit,
                result,
                raw_blob,
                decision_blob,
            )
            if result.decision.kind is HostedDecisionKind.FINAL_CANDIDATE:
                return self._complete(
                    permit,
                    result.decision,
                    policy,
                )
            request = result.decision.tool_request
            assert request is not None
            arguments_blob = self.blobs.write(
                permit.agent_run_id,
                HostedBlobRole.TOOL_ARGUMENTS,
                canonical_json_bytes(dict(request.arguments)),
            )
            try:
                admitted = self.action_gate.compile(
                    header=agent_projection.initial_header,
                    agent_run_epoch=agent_projection.epoch,
                    state=state,
                    policy=policy,
                    semantic_projection=semantic_projection,
                    model_decision=result.decision,
                    context_envelope_digest=materialized.envelope_digest,
                )
            except (HostedToolDeniedError, HostedAgentCellBudgetError) as exc:
                code = type(exc).__name__
                reason_digest = canonical_record_digest(
                    "macr.hosted-tool-denial.v1",
                    {
                        "request_digest": request.request_digest,
                        "reason_code": code,
                    },
                )
                denial_body = canonical_json_bytes(
                    {
                        "status": "denied",
                        "tool_id": request.tool_id,
                        "request_digest": request.request_digest,
                        "reason_code": code,
                    }
                ).decode("utf-8")
                denial_context = HostedContextSection(
                    section_id=self._uuid(),
                    agent_run_id=permit.agent_run_id,
                    kind=HostedContextKind.TOOL_DENIAL,
                    label="Tool request denied by host",
                    body=denial_body,
                    source_ref=f"hosted-tool-denial:{request.request_id}",
                    source_digest=reason_digest,
                    created_at=self._timestamp(),
                )
                denial_blob = self.blobs.write(
                    permit.agent_run_id,
                    HostedBlobRole.CONTEXT,
                    denial_context.canonical_bytes(),
                )
                self.store.record_tool_denial(
                    permit,
                    step_index=model_request.step_index,
                    request=request,
                    arguments_blob=arguments_blob,
                    reason_code=code,
                    reason_digest=reason_digest,
                    context=denial_context,
                    context_blob=denial_blob,
                )
                continue
            state = self.store.begin_tool(
                permit,
                step_index=model_request.step_index,
                request=request,
                arguments_blob=arguments_blob,
                proposal=admitted.proposal,
                admission=admitted.admission,
            )
            state, execution_permit = self.store.claim_tool_execution(
                permit,
                action_id=admitted.proposal.action_id,
                admission_digest=admitted.admission.admission_digest,
                semantic_projection_digest=semantic_projection.projection_digest,
            )
            started = self._monotonic()
            try:
                result_bytes = self.action_gate.execute(
                    admitted,
                    execution_permit,
                    header=agent_projection.initial_header,
                    policy=policy,
                    ownership=permit,
                    state=state,
                    semantic_projection=semantic_projection,
                )
            except HostedToolDeniedError:
                duration_ms = max(0, round((self._monotonic() - started) * 1000))
                observed_at = self._timestamp()
                result_ref = HostedToolResultRef(
                    action_id=request.request_id,
                    request_digest=request.request_digest,
                    tool_id=request.tool_id,
                    status=HostedToolResultStatus.FAILED,
                    result_blob_ref=None,
                    result_digest=None,
                    result_bytes=None,
                    observed_at=observed_at,
                )
                body = canonical_json_bytes(
                    {
                        "result_ref": result_ref.to_public_dict(),
                        "payload": None,
                    }
                ).decode("utf-8")
                context_item = HostedContextSection(
                    section_id=self._uuid(),
                    agent_run_id=permit.agent_run_id,
                    kind=HostedContextKind.TOOL_RESULT,
                    label="Tool execution failed locally",
                    body=body,
                    source_ref=result_ref.evidence_ref,
                    source_digest=result_ref.reference_digest,
                    created_at=observed_at,
                )
                context_blob = self.blobs.write(
                    permit.agent_run_id,
                    HostedBlobRole.CONTEXT,
                    context_item.canonical_bytes(),
                )
                self.store.finish_tool(
                    permit,
                    result=result_ref,
                    result_blob=None,
                    context=context_item,
                    context_blob=context_blob,
                    duration_ms=duration_ms,
                )
                continue
            duration_ms = max(0, round((self._monotonic() - started) * 1000))
            result_blob = self.blobs.write(
                permit.agent_run_id,
                HostedBlobRole.TOOL_RESULT,
                result_bytes,
            )
            observed_at = self._timestamp()
            result_ref = HostedToolResultRef(
                action_id=request.request_id,
                request_digest=request.request_digest,
                tool_id=request.tool_id,
                status=HostedToolResultStatus.COMPLETED,
                result_blob_ref=result_blob.blob_ref,
                result_digest=result_blob.sha256,
                result_bytes=result_blob.byte_count,
                observed_at=observed_at,
            )
            context_body = canonical_json_bytes(
                {
                    "result_ref": result_ref.to_public_dict(),
                    "payload": json.loads(result_bytes.decode("utf-8")),
                }
            ).decode("utf-8")
            context_item = HostedContextSection(
                section_id=self._uuid(),
                agent_run_id=permit.agent_run_id,
                kind=HostedContextKind.TOOL_RESULT,
                label=f"Result from {request.tool_id}",
                body=context_body,
                source_ref=result_ref.evidence_ref,
                source_digest=result_ref.reference_digest,
                created_at=observed_at,
            )
            context_blob = self.blobs.write(
                permit.agent_run_id,
                HostedBlobRole.CONTEXT,
                context_item.canonical_bytes(),
            )
            self.store.finish_tool(
                permit,
                result=result_ref,
                result_blob=result_blob,
                context=context_item,
                context_blob=context_blob,
                duration_ms=duration_ms,
            )

    def _complete(
        self,
        permit: AgentOwnershipPermit,
        decision,
        policy: HostedAgentCellPolicy,
    ) -> HostedAgentActivationResult:
        final_candidate = decision.final_candidate
        evidence_refs = decision.evidence_refs
        if not isinstance(final_candidate, str) or not final_candidate:
            raise HostedModelProtocolError("final candidate is missing")
        candidate_bytes, task_digest, approval_digest = (
            self._expected_completion_capture(
                permit.agent_run_id,
                policy,
                decision,
            )
        )
        if len(candidate_bytes) > policy.max_final_output_bytes:
            raise HostedModelProtocolError("final candidate exceeds output bound")
        candidate_run_id = self._uuid()
        self.store.create_completion_intent(
            permit,
            candidate_run_id=candidate_run_id,
            decision=decision,
        )
        self._fault("after_completion_intent")
        capture = self.candidate_vault.capture(
            "hosted_agent_cell",
            candidate_run_id,
            candidate_bytes,
            task_digest=task_digest,
            approval_digest=approval_digest,
        )
        self._require_exact_completion_capture(
            capture,
            candidate_run_id=candidate_run_id,
            candidate_bytes=candidate_bytes,
            task_digest=task_digest,
            approval_digest=approval_digest,
        )
        self._fault("after_candidate_capture")
        self.store.prepare_completion(
            permit,
            candidate_run_id=candidate_run_id,
            capture=capture,
            decision=decision,
            evidence_refs=evidence_refs,
        )
        self._fault("after_cell_completion_prepare")
        projection = self.agent.get_agent_run(permit.agent_run_id)
        self.agent.complete_agent_run(
            permit,
            expected_revision=projection.state_revision,
            expected_epoch=projection.epoch,
            evidence_ref=f"candidate:{capture.capture_id}",
            evidence_digest=capture.sha256,
        )
        self._fault("after_agent_run_complete")
        completed = self.store.finalize_completion(permit.agent_run_id)
        return HostedAgentActivationResult(
            permit.agent_run_id,
            "completed",
            completed,
            completed.latest_checkpoint_digest,
            capture,
            None,
        )

    def _expected_completion_capture(
        self,
        agent_run_id: str,
        policy: HostedAgentCellPolicy,
        decision,
    ) -> tuple[bytes, str, str]:
        candidate_bytes = decision.final_candidate.encode("utf-8")
        task_digest = canonical_record_digest(
            "macr.hosted-agent-cell.final-task.v1",
            {
                "agent_run_id": agent_run_id,
                "policy_digest": policy.policy_digest,
                "evidence_refs": list(decision.evidence_refs),
            },
        )
        approval_digest = self.agent.get_agent_run(
            agent_run_id
        ).initial_header.authority.reference.digest
        return candidate_bytes, task_digest, approval_digest

    def _require_exact_completion_capture(
        self,
        capture: CandidateCapture,
        *,
        candidate_run_id: str,
        candidate_bytes: bytes,
        task_digest: str,
        approval_digest: str,
    ) -> None:
        if (
            capture.run_id != candidate_run_id
            or capture.provider_id != "hosted_agent_cell"
            or capture.sha256 != hashlib.sha256(candidate_bytes).hexdigest()
            or capture.byte_count != len(candidate_bytes)
            or capture.task_digest != task_digest
            or capture.approval_digest != approval_digest
            or self.candidate_vault.read(capture.capture_id) != candidate_bytes
        ):
            raise HostedAgentCellStateError(
                "completion capture identity or provenance conflicts"
            )

    def _recover_completion(
        self,
        permit: AgentOwnershipPermit,
        policy: HostedAgentCellPolicy,
    ) -> HostedAgentActivationResult:
        intent = self.store.read_completion_intent(permit.agent_run_id)
        if intent is None:
            raise HostedAgentCellStateError("completion intent disappeared")
        decision = intent["decision"]
        candidate_run_id = intent["candidate_run_id"]
        candidate_bytes, task_digest, approval_digest = (
            self._expected_completion_capture(
                permit.agent_run_id,
                policy,
                decision,
            )
        )
        capture = self.candidate_vault.read_by_run(candidate_run_id)
        if capture is None:
            if len(candidate_bytes) > policy.max_final_output_bytes:
                raise HostedAgentCellStateError(
                    "completion intent output exceeds current policy"
                )
            capture = self.candidate_vault.capture(
                "hosted_agent_cell",
                candidate_run_id,
                candidate_bytes,
                task_digest=task_digest,
                approval_digest=approval_digest,
            )
        self._require_exact_completion_capture(
            capture,
            candidate_run_id=candidate_run_id,
            candidate_bytes=candidate_bytes,
            task_digest=task_digest,
            approval_digest=approval_digest,
        )
        if capture.sha256 != intent["final_answer_digest"]:
            raise HostedAgentCellStateError(
                "completion intent candidate bytes conflict"
            )
        state = self.store.read_state(permit.agent_run_id)
        if state.status is HostedAgentCellStatus.RUNNING:
            state = self.store.prepare_completion(
                permit,
                candidate_run_id=candidate_run_id,
                capture=capture,
                decision=decision,
                evidence_refs=tuple(intent["evidence_refs"]),
            )
        if state.status is not HostedAgentCellStatus.COMPLETION_PENDING:
            raise HostedAgentCellStateError(
                "completion recovery found an invalid cell state"
            )
        projection = self.agent.get_agent_run(permit.agent_run_id)
        if projection.state is AgentRunState.ACTIVE:
            self.agent.complete_agent_run(
                permit,
                expected_revision=projection.state_revision,
                expected_epoch=projection.epoch,
                evidence_ref=f"candidate:{capture.capture_id}",
                evidence_digest=capture.sha256,
            )
        elif projection.state is not AgentRunState.COMPLETED:
            raise HostedAgentCellStateError(
                "completion recovery found an invalid AgentRun state"
            )
        completed = self.store.finalize_completion(permit.agent_run_id)
        return HostedAgentActivationResult(
            permit.agent_run_id,
            "completed",
            completed,
            completed.latest_checkpoint_digest,
            capture,
            None,
        )

    def recover_terminal_completion(
        self,
        agent_run_id: str,
    ) -> HostedAgentActivationResult:
        projection = self.agent.get_agent_run(agent_run_id)
        if projection.state is not AgentRunState.COMPLETED:
            raise HostedAgentCellStateError("AgentRun is not terminal-completed")
        intent = self.store.read_completion_intent(agent_run_id)
        if intent is None:
            raise HostedAgentCellStateError("completion intent is missing")
        policy = self.store.read_policy(agent_run_id)
        candidate_bytes, task_digest, approval_digest = (
            self._expected_completion_capture(
                agent_run_id,
                policy,
                intent["decision"],
            )
        )
        capture = self.candidate_vault.read_by_run(intent["candidate_run_id"])
        if capture is None:
            raise HostedAgentCellStateError("terminal completion capture conflicts")
        self._require_exact_completion_capture(
            capture,
            candidate_run_id=intent["candidate_run_id"],
            candidate_bytes=candidate_bytes,
            task_digest=task_digest,
            approval_digest=approval_digest,
        )
        if capture.sha256 != intent["final_answer_digest"]:
            raise HostedAgentCellStateError("terminal completion capture conflicts")
        completed = self.store.finalize_completion(agent_run_id)
        return HostedAgentActivationResult(
            agent_run_id,
            "completed",
            completed,
            completed.latest_checkpoint_digest,
            capture,
            None,
        )

    def rehydrate_and_run(
        self,
        agent_run_id: str,
        owner_id: str,
        *,
        ttl_seconds: int,
        model: HostedModelPort,
    ) -> HostedAgentActivationResult:
        run_id = require_non_empty("agent_run_id", agent_run_id)
        state = self.store.read_state(run_id)
        if (
            state.status is not HostedAgentCellStatus.CHECKPOINTED
            or state.latest_checkpoint_digest is None
        ):
            raise HostedAgentCellStateError("cell has no rehydratable checkpoint")
        projection = self.agent.get_agent_run(run_id)
        permit = self.agent.acquire_agent_run(
            run_id,
            owner_id,
            expected_revision=projection.state_revision,
            expected_epoch=projection.epoch,
            ttl_seconds=ttl_seconds,
        )
        try:
            self.store.rehydrate(permit, state.latest_checkpoint_digest)
        except Exception:
            self.agent.release_agent_run(permit)
            raise
        return self.run_activation(permit, model)
