from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from .accounting import AccountingStore
from .authority import DispatchAuthorityStore
from .candidate_vault import CandidateCapture, CandidateVault
from .contracts import ProviderResult, ResultStatus, TaskContract
from .dispatch import AdmissionGate, DispatcherLeaseStore
from .errors import (
    MacrError,
    ProviderAdmissionBusyError,
    ProviderAdmissionConflict,
    ProviderAdmissionRequiredError,
    ProviderOutputBudgetTooSmallError,
    ProviderPolicyError,
)
from .event_store import SqliteEventStore
from .execution import (
    DispatchContext,
    ProviderExecution,
    ProviderState,
    ProviderUsage,
    RawProviderObservation,
    ReturnContractState,
)
from .model_token_store import ModelTokenPolicyStore
from .provider_capability_store import ProviderCapabilityPolicyStore
from .provider_capability import ProviderTierBinding
from .provider_admission import (
    AdmissionLane,
    ProviderAdmissionKernel,
    ProviderAdmissionPermit,
    ProviderAdmissionRequest,
)
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
    provider_admission: ProviderAdmissionKernel | None = None

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
            provider_admission=ProviderAdmissionKernel.canonical_runtime(
                layout.runtime_db_path
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


def build_provider_admission_request(
    provider_id: str,
    task: TaskContract,
    context: DispatchContext,
    *,
    request_id: str | None = None,
) -> ProviderAdmissionRequest:
    if (
        context.project_binding_digest is None
        or context.admission_lane is None
    ):
        raise ProviderAdmissionRequiredError(
            "provider admission identity is missing"
        )
    return ProviderAdmissionRequest(
        request_id=request_id or str(uuid.uuid4()),
        provider_id=provider_id,
        project_binding_digest=context.project_binding_digest,
        lane=AdmissionLane(context.admission_lane),
        run_id=context.run_id,
        authorization=context.authorization,
        plane=context.plane.value,
        task_type=task.task_type,
        task_digest=_task_digest(task),
        member_digest=context.member_digest,
        batch_id=context.batch_id,
        provider_tier_binding_digest=(
            context.provider_tier_binding_digest
        ),
    )


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
    diagnostic_method = getattr(exc, "safe_diagnostic", None)
    raw_diagnostic = (
        diagnostic_method() if callable(diagnostic_method) else {}
    )
    diagnostic = (
        dict(raw_diagnostic)
        if isinstance(raw_diagnostic, Mapping)
        else {}
    )
    return ProviderResult(
        task_id=task.task_id,
        status=ResultStatus.CANDIDATE_FAILURE,
        warnings=("Provider dispatch was refused before invocation.",),
        failure_code=type(exc).__name__,
        failure_stage="admission",
        provider_meta={
            "provider": provider_id,
            "failure_type": type(exc).__name__,
            "failure_stage": "admission",
            **diagnostic,
        },
    )


def _post_dispatch_failure(
    provider_id: str,
    task: TaskContract,
    exc: BaseException,
    observation: RawProviderObservation,
) -> ProviderResult:
    transport = {
        "network_attempted": observation.network_attempted,
        "response_received": observation.response_received,
        "provider_http_status": observation.provider_http_status,
        "provider_error_code": observation.provider_error_code,
        "transport_stage": observation.transport_stage,
    }
    return ProviderResult(
        task_id=task.task_id,
        status=ResultStatus.CANDIDATE_FAILURE,
        warnings=(
            f"Provider execution failed after dispatch ({type(exc).__name__}); "
            "exception details were omitted.",
        ),
        failure_code=type(exc).__name__,
        failure_stage="provider_execution",
        provider_meta={
            "provider": provider_id,
            "failure_type": type(exc).__name__,
            "failure_stage": "provider_execution",
            "metrics": {"duration_ms": observation.duration_ms},
            **transport,
        },
    )


def _failed_provider_observation(
    provider_id: str,
    exc: BaseException,
    duration_ms: int,
) -> RawProviderObservation:
    diagnostic_method = getattr(exc, "safe_diagnostic", None)
    raw = diagnostic_method() if callable(diagnostic_method) else {}
    diagnostic = raw if isinstance(raw, Mapping) else {}
    try:
        if diagnostic.get("network_attempted") is False:
            return RawProviderObservation(
                provider_id=provider_id,
                model=None,
                response_id=None,
                finish_reason=None,
                usage=ProviderUsage(None, None, None, None),
                currency_cost_usd=0.0,
                cost_kind="zero_local",
                pricing_basis_version="macr-pre-network-v1",
                duration_ms=duration_ms,
                answer_bytes=None,
                provider_state=ProviderState.MALFORMED,
                network_attempted=False,
                response_received=False,
                provider_http_status=None,
                provider_error_code=None,
                transport_stage=diagnostic.get("transport_stage"),
            )
        return RawProviderObservation.empty(
            provider_id,
            duration_ms=duration_ms,
            network_attempted=diagnostic.get("network_attempted"),
            response_received=diagnostic.get("response_received"),
            provider_http_status=diagnostic.get("provider_http_status"),
            provider_error_code=diagnostic.get("provider_error_code"),
            transport_stage=diagnostic.get("transport_stage"),
        )
    except ValueError:
        return RawProviderObservation.empty(
            provider_id,
            duration_ms=duration_ms,
        )


def _token_policy_failure(
    provider_id: str,
    task: TaskContract,
    exc: ProviderPolicyError,
) -> ProviderResult:
    provider_meta: dict[str, Any] = {
        "provider": provider_id,
        "failure_type": type(exc).__name__,
        "failure_stage": "token_policy",
    }
    if isinstance(exc, ProviderOutputBudgetTooSmallError):
        provider_meta["policy_violation"] = exc.safe_diagnostic()
    return ProviderResult(
        task_id=task.task_id,
        status=ResultStatus.CANDIDATE_FAILURE,
        warnings=("Provider model token policy refused the task.",),
        failure_code=type(exc).__name__,
        failure_stage="token_policy",
        provider_meta=provider_meta,
    )


def _capability_policy_failure(
    provider_id: str,
    task: TaskContract,
    exc: ProviderPolicyError,
) -> ProviderResult:
    return ProviderResult(
        task_id=task.task_id,
        status=ResultStatus.CANDIDATE_FAILURE,
        warnings=("Provider capability policy refused the task.",),
        failure_code=type(exc).__name__,
        failure_stage="provider_capability",
        provider_meta={
            "provider": provider_id,
            "failure_type": type(exc).__name__,
            "failure_stage": "provider_capability",
        },
    )


def _provider_approval_failure(
    provider_id: str,
    task: TaskContract,
    exc: MacrError,
) -> ProviderResult:
    return ProviderResult(
        task_id=task.task_id,
        status=ResultStatus.CANDIDATE_FAILURE,
        warnings=("Provider approval refused the task before dispatch.",),
        failure_code=type(exc).__name__,
        failure_stage="provider_approval",
        provider_meta={
            "provider": provider_id,
            "failure_type": type(exc).__name__,
            "failure_stage": "provider_approval",
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
        *,
        provider_admission_permit: ProviderAdmissionPermit | None = None,
        provider_admission_request: ProviderAdmissionRequest | None = None,
    ) -> ProviderResult:
        try:
            result = self._invoke_owned(
                provider_id,
                task,
                context,
                provider_admission_permit=provider_admission_permit,
                provider_admission_request=provider_admission_request,
            )
        except Exception as primary_error:
            try:
                self._cleanup_unused_pregrant(provider_admission_permit)
            except Exception as cleanup_error:
                primary_error.add_note(
                    "provider admission cleanup also failed: "
                    f"{type(cleanup_error).__name__}"
                )
                raise primary_error from cleanup_error
            raise
        self._cleanup_unused_pregrant(provider_admission_permit)
        return result

    def _cleanup_unused_pregrant(
        self,
        permit: ProviderAdmissionPermit | None,
    ) -> None:
        # T1 can reserve provider capacity before it claims a queue member.
        # Any refusal above the dispatch lease boundary must therefore give the
        # still-unused grant back.  The inner lifecycle owns grants once
        # transport starts; this outer guard exists specifically so early
        # validation returns and exceptions cannot strand capacity.
        if permit is None:
            return
        admission = self.services.provider_admission
        if admission is None:
            raise ProviderAdmissionRequiredError(
                "pre-granted provider admission has no shared kernel"
            )
        record = admission.read_request(permit.request_id)
        if record.state == "granted":
            admission.cancel_before_transport(permit)

    def _invoke_owned(
        self,
        provider_id: str,
        task: TaskContract,
        context: DispatchContext,
        *,
        provider_admission_permit: ProviderAdmissionPermit | None = None,
        provider_admission_request: ProviderAdmissionRequest | None = None,
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
                token_policy.validate_task_output_tokens(
                    task.constraints.max_output_tokens
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
        provider_binding = getattr(provider, "capability_binding", None)
        if (
            isinstance(provider_binding, ProviderTierBinding)
            and self.services.capability_policies is not None
        ):
            try:
                active_binding = self.services.capability_policies.effective_binding(
                    provider_id,
                    provider_binding.model_id,
                )
            except (MacrError, ValueError):
                return _capability_policy_failure(
                    provider_id,
                    task,
                    ProviderPolicyError(
                        "active provider capability binding is unavailable"
                    ),
                )
            if active_binding != provider_binding:
                return _capability_policy_failure(
                    provider_id,
                    task,
                    ProviderPolicyError(
                        "provider registry capability binding is stale"
                    ),
                )
        if (
            provider_binding is not None
            or context.provider_tier_binding_digest is not None
        ):
            if (
                not isinstance(provider_binding, ProviderTierBinding)
                or provider_binding.provider_id != provider_id
                or context.provider_tier_binding_digest
                != provider_binding.binding_digest
            ):
                return _capability_policy_failure(
                    provider_id,
                    task,
                    ProviderPolicyError(
                        "dispatch context does not match provider capability binding"
                    ),
                )
        validate_approval = getattr(provider, "validate_approval", None)
        if callable(validate_approval):
            try:
                approval_metadata = validate_approval(task)
                if (
                    isinstance(provider_binding, ProviderTierBinding)
                    and (
                        not isinstance(approval_metadata, Mapping)
                        or approval_metadata.get("provider_tier_binding_digest")
                        != provider_binding.binding_digest
                    )
                ):
                    raise ProviderPolicyError(
                        "provider approval does not bind the active capability tier"
                    )
            except MacrError as exc:
                return _provider_approval_failure(provider_id, task, exc)
        requires_provider_admission = bool(
            getattr(provider, "requires_provider_admission", False)
        )
        provider_admission = self.services.provider_admission
        if requires_provider_admission and (
            not isinstance(provider_admission, ProviderAdmissionKernel)
            or getattr(provider, "admission_guard", None)
            is not provider_admission
            or context.project_binding_digest is None
            or context.admission_lane is None
            or context.provider_admission_policy_digest
            != provider_admission.policy.policy_digest
        ):
            return _admission_failure(
                provider_id,
                task,
                ProviderAdmissionRequiredError(
                    "provider admission identity or policy is missing"
                ),
            )
        if requires_provider_admission:
            validate_transport_binding = getattr(
                provider,
                "validate_admission_transport_binding",
                None,
            )
            if not callable(validate_transport_binding):
                return _admission_failure(
                    provider_id,
                    task,
                    ProviderAdmissionRequiredError(
                        "provider has no admission transport binding"
                    ),
                )
            try:
                validate_transport_binding()
            except MacrError as exc:
                return _admission_failure(provider_id, task, exc)
        if (provider_admission_permit is None) != (
            provider_admission_request is None
        ):
            return _admission_failure(
                provider_id,
                task,
                ProviderAdmissionRequiredError(
                    "provider admission permit and request must be supplied together"
                ),
            )
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

        provider_request = provider_admission_request
        provider_permit = provider_admission_permit
        provider_admission_finished = False
        execution: ProviderExecution | None = None
        try:
            if requires_provider_admission:
                assert provider_admission is not None
                assert context.project_binding_digest is not None
                assert context.admission_lane is not None
                if provider_request is None:
                    provider_request = build_provider_admission_request(
                        provider_id,
                        task,
                        context,
                    )
                    try:
                        provider_permit = provider_admission.try_admit(
                            provider_request,
                            ttl_seconds=ttl_seconds,
                        )
                    except ProviderAdmissionBusyError:
                        provider_admission.cancel_waiting(
                            provider_request.request_id,
                            provider_request.run_id,
                        )
                        raise
                else:
                    expected_request = build_provider_admission_request(
                        provider_id,
                        task,
                        context,
                        request_id=provider_request.request_id,
                    )
                    if expected_request != provider_request:
                        raise ProviderAdmissionConflict(
                            "pre-granted provider admission request is stale"
                        )
                assert provider_permit is not None
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

            provider_started = time.perf_counter()
            try:
                if requires_provider_admission:
                    execution = provider.invoke_observed(
                        task,
                        admission_permit=provider_permit,
                        admission_request=provider_request,
                    )
                else:
                    execution = provider.invoke_observed(task)
                if not isinstance(execution, ProviderExecution):
                    raise TypeError(
                        "provider invoke_observed returned an invalid execution"
                    )
            except Exception as exc:
                duration_ms = max(
                    0,
                    round((time.perf_counter() - provider_started) * 1000),
                )
                observation = _failed_provider_observation(
                    provider_id,
                    exc,
                    duration_ms,
                )
                execution = ProviderExecution.from_observation(
                    observation,
                    _post_dispatch_failure(
                        provider_id,
                        task,
                        exc,
                        observation,
                    ),
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
                failure_code=execution.result.failure_code,
                failure_stage=execution.result.failure_stage,
            )
            terminal_payload = self._terminal_payload(
                provider_id,
                task,
                context,
                dispatch_event_id,
                execution,
                capture,
                billing_state,
                return_reason,
            )
            self.services.events.finish_run(
                run_id=context.run_id,
                terminal_event_id=str(uuid.uuid4()),
                state=execution.result.status.value,
                payload=terminal_payload,
            )
            if provider_permit is not None:
                assert provider_admission is not None
                admission_record = provider_admission.read_request(
                    provider_permit.request_id
                )
                if admission_record.state == "dispatched":
                    provider_admission.finish(
                        provider_permit,
                        network_attempted=(
                            execution.observation.network_attempted
                        ),
                        response_received=(
                            execution.observation.response_received
                        ),
                        provider_http_status=(
                            execution.observation.provider_http_status
                        ),
                        terminal_persisted=True,
                        terminal_evidence_digest=hashlib.sha256(
                            _canonical_json(terminal_payload).encode("utf-8")
                        ).hexdigest(),
                    )
                elif not (
                    admission_record.state
                    in {"cancelled", "reconciliation_required"}
                    and execution.observation.network_attempted is False
                ):
                    raise ProviderAdmissionConflict(
                        "provider admission terminal state is inconsistent"
                    )
                provider_admission_finished = True
            return execution.result
        finally:
            if (
                provider_permit is not None
                and provider_admission is not None
                and not provider_admission_finished
            ):
                try:
                    record = provider_admission.read_request(
                        provider_permit.request_id
                    )
                    if record.state == "granted":
                        provider_admission.cancel_before_transport(
                            provider_permit
                        )
                    elif record.state == "dispatched":
                        observation = (
                            execution.observation
                            if execution is not None
                            else RawProviderObservation.empty(provider_id)
                        )
                        provider_admission.finish(
                            provider_permit,
                            network_attempted=observation.network_attempted,
                            response_received=observation.response_received,
                            provider_http_status=(
                                observation.provider_http_status
                            ),
                            terminal_persisted=False,
                            terminal_evidence_digest=hashlib.sha256(
                                _canonical_json(
                                    {
                                        "run_id": context.run_id,
                                        "state": "terminal_persistence_incomplete",
                                    }
                                ).encode("utf-8")
                            ).hexdigest(),
                        )
                except Exception:
                    pass
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
                failure_code="ReturnContractError",
                failure_stage="return_contract",
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
            "dispatch_contract_version": 3,
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
            "provider_tier_binding_digest": (
                context.provider_tier_binding_digest
            ),
            "project_binding_digest": context.project_binding_digest,
            "admission_lane": context.admission_lane,
            "provider_admission_policy_digest": (
                context.provider_admission_policy_digest
            ),
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
            "terminal_contract_version": 4,
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
            "network_attempted": observation.network_attempted,
            "response_received": observation.response_received,
            "provider_http_status": observation.provider_http_status,
            "provider_error_code": observation.provider_error_code,
            "transport_stage": observation.transport_stage,
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
            "failure_type": (
                execution.result.failure_code
                or execution.result.provider_meta.get("failure_type")
            ),
            "failure_stage": execution.result.failure_stage,
            "authority_digest": context.authorization.digest,
            "authority_revision": context.authorization.revision,
            "authority_epoch": context.authorization.epoch,
            "plan_digest": context.plan_digest,
            "plan_revision": context.plan_revision,
            "role_slot_id": context.role_slot_id,
            "route_id": context.route_id,
            "provider_tier_binding_digest": (
                context.provider_tier_binding_digest
            ),
            "project_binding_digest": context.project_binding_digest,
            "admission_lane": context.admission_lane,
            "provider_admission_policy_digest": (
                context.provider_admission_policy_digest
            ),
        }
