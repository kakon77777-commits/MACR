from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Protocol

from .canonical import sha256_id
from .contracts import ResultStatus, TaskContract
from .coordination import CoordinationPlan, PlanExecutionMode, TopologyId
from .errors import MacrError
from .execution import (
    AcceptanceState,
    AuthorizationReference,
    DispatchContext,
    DispatchOrigin,
    InteractionPlane,
    MaterializationState,
    VerificationState,
)
from .registry import ProviderRegistry
from .route_resolution import ExecutionRouteProposal
from .runtime import MacrRuntime, RuntimeServices, task_contract_digest


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PlanExecutionError(MacrError):
    """An executable T0 plan fails its local authority or lineage contract."""


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True)
class VerificationReport:
    graph_digest: str
    state: VerificationState
    evidence_digest: str
    node_result_digests: tuple[str, ...]
    bounded_diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _digest("graph_digest", self.graph_digest)
        if self.state not in {VerificationState.PASSED, VerificationState.FAILED}:
            raise ValueError("verification report state must be passed or failed")
        _digest("evidence_digest", self.evidence_digest)
        if not self.node_result_digests or any(
            not isinstance(item, str) or not _SHA256.fullmatch(item)
            for item in self.node_result_digests
        ):
            raise ValueError("node_result_digests must contain SHA-256 digests")
        if any(
            not isinstance(item, str)
            or not item
            or len(item.encode("utf-8")) > 512
            for item in self.bounded_diagnostics
        ):
            raise ValueError("bounded_diagnostics contains invalid text")

    def to_public_dict(self) -> dict[str, object]:
        return {
            "graph_digest": self.graph_digest,
            "state": self.state.value,
            "evidence_digest": self.evidence_digest,
            "node_result_digests": list(self.node_result_digests),
            "bounded_diagnostics": list(self.bounded_diagnostics),
        }


class PlanVerifier(Protocol):
    def verify(
        self,
        graph,
        candidate_bytes: bytes,
        *,
        plan: CoordinationPlan,
        contract: TaskContract,
    ) -> VerificationReport: ...


@dataclass(frozen=True)
class PlanExecutionResult:
    plan_digest: str
    plan_revision: int
    run_id: str
    provider_id: str
    route_id: str
    provider_status: str
    provider_state: str
    capture_state: str
    return_contract_state: str
    materialization_state: MaterializationState
    verification_state: VerificationState
    acceptance_state: AcceptanceState
    candidate_capture_id: str | None
    verification_evidence_digest: str | None
    persistence_state: str
    failure_type: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_digest": self.plan_digest,
            "plan_revision": self.plan_revision,
            "run_id": self.run_id,
            "provider_id": self.provider_id,
            "route_id": self.route_id,
            "provider_status": self.provider_status,
            "provider_state": self.provider_state,
            "capture_state": self.capture_state,
            "return_contract_state": self.return_contract_state,
            "materialization_state": self.materialization_state.value,
            "verification_state": self.verification_state.value,
            "acceptance_state": self.acceptance_state.value,
            "candidate_capture_id": self.candidate_capture_id,
            "verification_evidence_digest": (
                self.verification_evidence_digest
            ),
            "persistence_state": self.persistence_state,
            "failure_type": self.failure_type,
        }


class PlanRuntime:
    def __init__(
        self,
        registry: ProviderRegistry,
        services: RuntimeServices,
        verifier: PlanVerifier,
    ) -> None:
        if not isinstance(registry, ProviderRegistry):
            raise ValueError("registry must be a ProviderRegistry")
        if not isinstance(services, RuntimeServices):
            raise ValueError("services must be RuntimeServices")
        if not callable(getattr(verifier, "verify", None)):
            raise ValueError("verifier must implement verify")
        self.registry = registry
        self.services = services
        self.verifier = verifier

    def execute(
        self,
        plan: CoordinationPlan,
        task: TaskContract,
        proposal: ExecutionRouteProposal,
        authority: AuthorizationReference,
        origin: DispatchOrigin,
    ) -> PlanExecutionResult:
        self._validate_plan_task_proposal(plan, task, proposal)
        if not isinstance(origin, DispatchOrigin):
            raise ValueError("origin must be a DispatchOrigin")
        self.services.authorities.verify(
            authority,
            provider_id=proposal.provider_id,
            plane=InteractionPlane.DELEGATION.value,
            task_type=task.task_type,
            member_digest=plan.plan_digest,
        )
        run_id = str(uuid.uuid4())
        binding = plan.bindings[0]
        context = DispatchContext(
            run_id=run_id,
            plane=InteractionPlane.DELEGATION,
            origin=origin,
            authorization=authority,
            policy_snapshot_sha256=proposal.policy_snapshot_id,
            member_digest=plan.plan_digest,
            plan_digest=plan.plan_digest,
            plan_revision=plan.plan_revision,
            role_slot_id=binding.slot_id,
            route_id=binding.route_id,
        )
        try:
            result = MacrRuntime(self.registry, self.services).invoke(
                proposal.provider_id,
                task,
                context,
            )
        except Exception as exc:
            return self._persistence_failure_result(
                plan,
                proposal,
                run_id,
                type(exc).__name__,
            )
        terminal = self._terminal_payload(run_id)
        capture = self.services.vault.read_by_run(run_id)
        verification_state = VerificationState.NOT_RUN
        verification_report: VerificationReport | None = None
        if (
            result.status is ResultStatus.CANDIDATE_SUCCESS
            and capture is not None
            and terminal["return_contract_state"] == "valid"
        ):
            candidate_bytes = self.services.vault.read(capture.capture_id)
            try:
                verification_report = self.verifier.verify(
                    plan.verifier_graph,
                    candidate_bytes,
                    plan=plan,
                    contract=task,
                )
                if not isinstance(verification_report, VerificationReport):
                    raise TypeError("verifier returned invalid report")
                if (
                    verification_report.graph_digest
                    != plan.verifier_graph.graph_digest
                ):
                    raise ValueError("verification report graph mismatch")
            except Exception as exc:
                failure_digest = sha256_id(
                    "plan_verifier_failure_v1",
                    {
                        "plan_digest": plan.plan_digest,
                        "run_id": run_id,
                        "failure_type": type(exc).__name__,
                    },
                )
                verification_report = VerificationReport(
                    graph_digest=plan.verifier_graph.graph_digest,
                    state=VerificationState.FAILED,
                    evidence_digest=failure_digest,
                    node_result_digests=(failure_digest,),
                    bounded_diagnostics=("verifier_execution_failed",),
                )
            verification_state = verification_report.state

        verification_evidence = (
            verification_report.evidence_digest
            if verification_report is not None
            else None
        )
        persistence_state = "complete"
        failure_type = None
        try:
            self.services.events.append_standalone(
                "plan.verification_completed",
                str(uuid.uuid4()),
                {
                    "plan_digest": plan.plan_digest,
                    "plan_revision": plan.plan_revision,
                    "run_id": run_id,
                    "provider_id": proposal.provider_id,
                    "route_id": binding.route_id,
                    "role_slot_id": binding.slot_id,
                    "provider_status": result.status.value,
                    "verification_state": verification_state.value,
                    "verification_graph_digest": (
                        plan.verifier_graph.graph_digest
                    ),
                    "verification_evidence_digest": verification_evidence,
                    "acceptance_state": AcceptanceState.PENDING.value,
                },
                run_id=run_id,
            )
        except Exception as exc:
            persistence_state = "failed"
            failure_type = type(exc).__name__
        return PlanExecutionResult(
            plan_digest=plan.plan_digest,
            plan_revision=plan.plan_revision,
            run_id=run_id,
            provider_id=proposal.provider_id,
            route_id=binding.route_id,
            provider_status=result.status.value,
            provider_state=terminal["provider_state"],
            capture_state=terminal["capture_state"],
            return_contract_state=terminal["return_contract_state"],
            materialization_state=MaterializationState.NONE,
            verification_state=verification_state,
            acceptance_state=AcceptanceState.PENDING,
            candidate_capture_id=(
                capture.capture_id if capture is not None else None
            ),
            verification_evidence_digest=verification_evidence,
            persistence_state=persistence_state,
            failure_type=failure_type,
        )

    def _persistence_failure_result(
        self,
        plan: CoordinationPlan,
        proposal: ExecutionRouteProposal,
        run_id: str,
        failure_type: str,
    ) -> PlanExecutionResult:
        try:
            events = self.services.events.read_events(run_id=run_id)
        except Exception:
            events = ()
        dispatched = any(
            item["event_type"] == "provider.dispatch_requested"
            for item in events
        )
        try:
            capture = self.services.vault.read_by_run(run_id)
        except Exception:
            capture = None
        if dispatched:
            try:
                self.services.events.append_standalone(
                    "plan.persistence_failed",
                    str(uuid.uuid4()),
                    {
                        "plan_digest": plan.plan_digest,
                        "plan_revision": plan.plan_revision,
                        "run_id": run_id,
                        "provider_id": proposal.provider_id,
                        "route_id": proposal.route_id,
                        "failure_type": failure_type,
                        "provider_state": "unknown_after_dispatch",
                        "acceptance_state": AcceptanceState.PENDING.value,
                    },
                    run_id=run_id,
                )
            except Exception:
                pass
        return PlanExecutionResult(
            plan_digest=plan.plan_digest,
            plan_revision=plan.plan_revision,
            run_id=run_id,
            provider_id=proposal.provider_id,
            route_id=proposal.route_id,
            provider_status=(
                "unknown_after_dispatch" if dispatched else "not_dispatched"
            ),
            provider_state=(
                "unknown_after_dispatch" if dispatched else "not_dispatched"
            ),
            capture_state="captured" if capture is not None else "absent",
            return_contract_state="not_evaluated",
            materialization_state=MaterializationState.NONE,
            verification_state=VerificationState.NOT_RUN,
            acceptance_state=AcceptanceState.PENDING,
            candidate_capture_id=(
                capture.capture_id if capture is not None else None
            ),
            verification_evidence_digest=None,
            persistence_state="failed",
            failure_type=failure_type,
        )

    def _validate_plan_task_proposal(
        self,
        plan: CoordinationPlan,
        task: TaskContract,
        proposal: ExecutionRouteProposal,
    ) -> None:
        if not isinstance(plan, CoordinationPlan):
            raise ValueError("plan must be a CoordinationPlan")
        if plan.topology_id is not TopologyId.T0_DIRECT_VERIFIED:
            raise PlanExecutionError("only T0 plans are executable")
        if plan.execution_mode is not PlanExecutionMode.EXECUTION_ELIGIBLE:
            raise PlanExecutionError("shadow plan cannot execute")
        if len(plan.bindings) != 1 or len(plan.roles) != 1:
            raise PlanExecutionError("T0 execution requires one role and binding")
        if not isinstance(task, TaskContract):
            raise ValueError("task must be a TaskContract")
        if task_contract_digest(task) != plan.task_digest:
            raise PlanExecutionError("task digest does not match plan")
        if not isinstance(proposal, ExecutionRouteProposal):
            raise ValueError("proposal must be an ExecutionRouteProposal")
        binding = plan.bindings[0]
        if (
            proposal.route_id != binding.route_id
            or proposal.parameter_profile_digest
            != binding.parameter_profile_digest
            or proposal.route_snapshot_id != plan.route_snapshot_id
            or proposal.policy_snapshot_id not in plan.policy_snapshot_ids
        ):
            raise PlanExecutionError("route proposal does not match plan binding")
        profile = self.registry.execution_profile(proposal.provider_id)
        if (
            profile["model"] != proposal.provider_model_id
            or profile["base_url"] != proposal.endpoint_identity
            or profile["kind"] != proposal.provider_kind
            or profile["connection_scope"] != proposal.connection_scope
        ):
            raise PlanExecutionError(
                "execution provider profile does not match route proposal"
            )

    def _terminal_payload(self, run_id: str) -> dict[str, object]:
        events = self.services.events.read_events(run_id=run_id)
        terminal = next(
            (
                item
                for item in events
                if item["event_type"] == "provider.candidate_completed"
            ),
            None,
        )
        if terminal is None:
            raise PlanExecutionError("provider terminal event is missing")
        return terminal["payload"]


__all__ = [
    "PlanExecutionError",
    "PlanExecutionResult",
    "PlanRuntime",
    "PlanVerifier",
    "VerificationReport",
]
