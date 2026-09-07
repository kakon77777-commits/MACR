from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from .accounting import AccountingStore
from .authority import DispatchAuthorityStore
from .candidate_vault import CandidateCapture, CandidateVault
from .contracts import ProviderResult, ResultStatus, TaskContract
from .dispatch import AdmissionGate, DispatcherLeaseStore
from .errors import MacrError, ProviderPolicyError
from .event_store import SqliteEventStore
from .execution import (
    DispatchContext,
    ProviderExecution,
    RawProviderObservation,
    ReturnContractState,
)
from .model_token_store import ModelTokenPolicyStore
from .provider_capability_store import ProviderCapabilityPolicyStore
from .registry import ProviderRegistry
from .return_contracts import validate_return_contract
from .storage import StorageLayout
from .task_preflight import validate_task_consistency


@dataclass(frozen=True)
class RuntimeServices:
    events: SqliteEventStore
    authorities: DispatchAuthorityStore
    leases: DispatcherLeaseStore
    admission: AdmissionGate
    accounting: AccountingStore
    vault: CandidateVault
    token_policies: ModelTokenPolicyStore
    capability_policies: ProviderCapabilityPolicyStore | None = None

    @classmethod
    def from_layout(cls, layout: StorageLayout) -> "RuntimeServices":
        if not isinstance(layout, StorageLayout):
            raise ValueError("layout must be a StorageLayout")
        events = SqliteEventStore(layout.runtime_db_path)
        authorities = DispatchAuthorityStore(layout.runtime_db_path)
        leases = DispatcherLeaseStore(layout.runtime_db_path)
        return cls(
            events=events,
            authorities=authorities,
            leases=leases,
            admission=AdmissionGate(authorities, leases),
            accounting=AccountingStore(layout.accounting_db_path),
            vault=CandidateVault(layout.candidate_root, layout.runtime_db_path),
            token_policies=ModelTokenPolicyStore(layout.model_token_policy_db_path),
            capability_policies=ProviderCapabilityPolicyStore(
                layout.provider_capability_policy_db_path
            ),
        )


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def task_contract_digest(task: TaskContract) -> str:
    return hashlib.sha256(
        _canonical_json(task.to_dict()).encode("utf-8")
    ).hexdigest()


def _task_digest(task: TaskContract) -> str:
    return task_contract_digest(task)


def dispatch_resource_key(provider_id: str, task: TaskContract) -> str:
    """Return a non-sensitive conservative collision key for one delegated task."""
    if not isinstance(provider_id, str) or not provider_id.strip():
        raise ValueError("provider_id must be a non-empty string")
    if not isinstance(task, TaskContract):
        raise ValueError("task must be a TaskContract")
    if task.workspace.write_scope:
        target_digest = hashlib.sha256(
            _canonical_json(
                {
                    "repo": task.workspace.repo,
                }
            ).encode("utf-8")
        ).hexdigest()
        return f"workspace-write:{target_digest}"
    return f"provider:{provider_id.strip()}:task:{task.task_id}"


def _billing_state(observation: RawProviderObservation) -> str:
    if observation.currency_cost_usd is None:
        return "unknown_after_dispatch"
    if observation.cost_kind in {"provider_reported", "actual"}:
        return "provider_reported"
    if observation.cost_kind == "zero_local":
        return "zero_local"
    return "estimated"


def _admission_failure(
    provider_id: str,
    task: TaskContract,
    exc: MacrError,
) -> ProviderResult:
    return ProviderResult(
        task_id=task.task_id,
        status=ResultStatus.CANDIDATE_FAILURE,
        warnings=("Provider dispatch was refused before invocation.",),
        provider_meta={
            "provider": provider_id,
            "failure_type": type(exc).__name__,
            "failure_stage": "admission",
        },
    )


def _post_dispatch_failure(
    provider_id: str,
    task: TaskContract,
    exc: BaseException,
) -> ProviderResult:
    return ProviderResult(
        task_id=task.task_id,
        status=ResultStatus.CANDIDATE_FAILURE,
        warnings=(
            "Provider execution failed after dispatch; exception details were omitted.",
        ),
        provider_meta={
            "provider": provider_id,
            "failure_type": type(exc).__name__,
            "failure_stage": "provider_execution",
        },
    )


def _token_policy_failure(
    provider_id: str,
    task: TaskContract,
    exc: ProviderPolicyError,
) -> ProviderResult:
    return ProviderResult(
        task_id=task.task_id,
        status=ResultStatus.CANDIDATE_FAILURE,
        warnings=("Provider model token policy refused the task.",),
        provider_meta={
            "provider": provider_id,
            "failure_type": type(exc).__name__,
            "failure_stage": "token_policy",
        },
    )


class MacrRuntime:
    def __init__(
        self,
        registry: ProviderRegistry,
        services: RuntimeServices,
    ) -> None:
        if not isinstance(registry, ProviderRegistry):
            raise ValueError("registry must be a ProviderRegistry")
        if not isinstance(services, RuntimeServices):
            raise ValueError("services must be RuntimeServices")
        self.registry = registry
        self.services = services

    def invoke(
        self,
        provider_id: str,
        task: TaskContract,
        context: DispatchContext,
    ) -> ProviderResult:
        validate_task_consistency(task)
        if not isinstance(context, DispatchContext):
            raise ValueError("context must be a DispatchContext")
        provider = self.registry.get(provider_id)
        try:
            if self.registry.requires_model_token_policy(provider_id):
                token_policy = self.registry.token_policy(
                    provider_id,
                    store=self.services.token_policies,
                )
                if (
                    task.constraints.max_output_tokens
                    > token_policy.max_output_tokens
                ):
                    raise ProviderPolicyError(
                        "task output exceeds exact model token policy"
                    )
                requested_context = task.constraints.max_context_tokens
                if (
                    requested_context is not None
                    and requested_context > token_policy.hard_context_tokens
                ):
                    raise ProviderPolicyError(
                        "task context exceeds exact model token policy"
                    )
                context = replace(
                    context,
                    model_token_policy_digest=token_policy.policy_digest,
                )
        except ProviderPolicyError as exc:
            return _token_policy_failure(provider_id, task, exc)
        resource_key = dispatch_resource_key(provider_id, task)
        ttl_seconds = max(
            1,
            min(86400, math.ceil(task.constraints.max_latency_s) + 60),
        )
        try:
            permit = self.services.admission.admit(
                context,
                resource_key=resource_key,
                provider_id=provider_id,
                task_type=task.task_type,
                ttl_seconds=ttl_seconds,
            )
        except MacrError as exc:
            return _admission_failure(provider_id, task, exc)

        try:
            dispatch_event_id = str(uuid.uuid4())
            self.services.events.start_run(
                run_id=context.run_id,
                dispatch_event_id=dispatch_event_id,
                payload=self._dispatch_payload(
                    provider_id,
                    task,
                    context,
                    permit.fencing_token,
                ),
            )
            self.services.accounting.record_dispatch(
                context.run_id,
                context,
                provider_id=provider_id,
                model=self.registry.requested_model(provider_id),
                estimate_usd=None,
                soft_warning=False,
            )

            try:
                execution = provider.invoke_observed(task)
                if not isinstance(execution, ProviderExecution):
                    raise TypeError(
                        "provider invoke_observed returned an invalid execution"
                    )
            except Exception as exc:
                observation = RawProviderObservation.empty(provider_id)
                execution = ProviderExecution.from_observation(
                    observation,
                    _post_dispatch_failure(provider_id, task, exc),
                )

            capture = self._capture_candidate(
                provider_id,
                task,
                context,
                execution,
            )
            self.services.accounting.record_observation(
                context.run_id,
                execution.observation,
            )
            execution, return_reason = self._validate_candidate_return(task, execution)
            billing_state = _billing_state(execution.observation)

            self.services.accounting.record_terminal(
                context.run_id,
                candidate_status=execution.result.status.value,
                billing_state=billing_state,
            )
            self.services.events.finish_run(
                run_id=context.run_id,
                terminal_event_id=str(uuid.uuid4()),
                state=execution.result.status.value,
                payload=self._terminal_payload(
                    provider_id,
                    task,
                    context,
                    dispatch_event_id,
                    execution,
                    capture,
                    billing_state,
                    return_reason,
                ),
            )
            return execution.result
        finally:
            self.services.leases.release(
                permit.resource_key,
                permit.run_id,
                permit.fencing_token,
            )

    def _capture_candidate(
        self,
        provider_id: str,
        task: TaskContract,
        context: DispatchContext,
        execution: ProviderExecution,
    ) -> CandidateCapture | None:
        answer_bytes = execution.observation.answer_bytes
        if answer_bytes is None:
            return None
        return self.services.vault.capture(
            provider_id,
            context.run_id,
            answer_bytes,
            task_digest=_task_digest(task),
            approval_digest=task.delegation_approval_sha256,
        )

    @staticmethod
    def _validate_candidate_return(
        task: TaskContract,
        execution: ProviderExecution,
    ) -> tuple[ProviderExecution, str | None]:
        if execution.result.status is not ResultStatus.CANDIDATE_SUCCESS:
            return execution, None
        validation = validate_return_contract(task, execution.result.answer)
        result = execution.result
        if validation.state is ReturnContractState.INVALID:
            result = replace(
                result,
                status=ResultStatus.CANDIDATE_FAILURE,
                answer="",
                warnings=(
                    *result.warnings,
                    f"Return contract rejected the candidate: {validation.reason_code}.",
                ),
                provider_meta={
                    **dict(result.provider_meta),
                    "failure_type": "ReturnContractError",
                },
            )
        return (
            replace(
                execution,
                result=result,
                return_contract_state=validation.state,
            ),
            validation.reason_code,
        )

    @staticmethod
    def _dispatch_payload(
        provider_id: str,
        task: TaskContract,
        context: DispatchContext,
        fencing_token: int,
    ) -> dict[str, Any]:
        return {
            "provider_id": provider_id,
            "task_id": task.task_id,
            "task_type": task.task_type,
            "interaction_plane": context.plane.value,
            "origin_host": context.origin.host,
            "origin_identifier_kind": context.origin.identifier_kind,
            "origin_native_id": context.origin.native_id,
            "authority_source_kind": context.authorization.source_kind,
            "authority_source_id": context.authorization.source_id,
            "authority_digest": context.authorization.digest,
            "authority_revision": context.authorization.revision,
            "authority_epoch": context.authorization.epoch,
            "authority_scope_sha256": hashlib.sha256(
                context.authorization.scope.encode("utf-8")
            ).hexdigest(),
            "policy_snapshot_sha256": context.policy_snapshot_sha256,
            "model_token_policy_digest": context.model_token_policy_digest,
            "batch_id": context.batch_id,
            "member_digest": context.member_digest,
            "relay_is_authorship": context.relay_is_authorship,
            "fencing_token": fencing_token,
            "plan_digest": context.plan_digest,
            "plan_revision": context.plan_revision,
            "role_slot_id": context.role_slot_id,
            "route_id": context.route_id,
        }

    @staticmethod
    def _terminal_payload(
        provider_id: str,
        task: TaskContract,
        context: DispatchContext,
        dispatch_event_id: str,
        execution: ProviderExecution,
        capture: CandidateCapture | None,
        billing_state: str,
        return_reason: str | None,
    ) -> dict[str, Any]:
        observation = execution.observation
        raw_metrics = execution.result.provider_meta.get("metrics")
        metrics = raw_metrics if isinstance(raw_metrics, Mapping) else {}

        def safe_count(name: str) -> int | None:
            value = metrics.get(name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return None
            return value

        return {
            "provider_id": provider_id,
            "task_id": task.task_id,
            "dispatch_event_id": dispatch_event_id,
            "status": execution.result.status.value,
            "model": observation.model,
            "response_id": observation.response_id,
            "finish_reason": observation.finish_reason,
            "provider_state": observation.provider_state.value,
            "input_tokens": observation.usage.input_tokens,
            "output_tokens": observation.usage.output_tokens,
            "reasoning_tokens": observation.usage.reasoning_tokens,
            "cached_tokens": observation.usage.cached_tokens,
            "currency_cost_usd": observation.currency_cost_usd,
            "cost_kind": observation.cost_kind,
            "pricing_basis_version": observation.pricing_basis_version,
            "duration_ms": observation.duration_ms,
            "input_media_count": safe_count("input_media_count"),
            "input_media_bytes": safe_count("input_media_bytes"),
            "output_artifact_count": safe_count("output_artifact_count"),
            "output_artifact_bytes": safe_count("output_artifact_bytes"),
            "billing_state": billing_state,
            "capture_state": execution.capture_state.value,
            "candidate_capture": (
                capture.to_public_dict() if capture is not None else None
            ),
            "return_contract_state": execution.return_contract_state.value,
            "return_contract_reason": return_reason,
            "failure_type": execution.result.provider_meta.get("failure_type"),
            "authority_digest": context.authorization.digest,
            "authority_revision": context.authorization.revision,
            "authority_epoch": context.authorization.epoch,
            "plan_digest": context.plan_digest,
            "plan_revision": context.plan_revision,
            "role_slot_id": context.role_slot_id,
            "route_id": context.route_id,
        }
