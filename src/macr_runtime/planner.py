from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable

from .canonical import aware_iso8601, sha256_id
from .contracts import PrivacyLevel
from .coordination import (
    BudgetEvaluation,
    CoordinationPlan,
    EligibleCandidate,
    ExcludedCandidate,
    FallbackRule,
    ModelBinding,
    PlanExecutionMode,
    RoleSlot,
    TopologyId,
)
from .model_identity import IdentityStatus, QualificationKey
from .planning_contracts import BudgetMode, ContextCapsule, OperatorPolicyProfile
from .qualification import QualificationState
from .verification_graph import VerifierGraph


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TIE_BREAK_RULES = (
    "verified_utility_desc",
    "total_cost_asc",
    "latency_asc",
    "freshness_desc",
    "route_id_asc",
)


class PlanningError(ValueError):
    """No deterministic coordination plan satisfies all hard gates."""


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded identifier")
    return value


def _digests(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must contain digests")
    normalized = tuple(_digest(f"{name} item", item) for item in values)
    if not normalized or len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must be non-empty and unique")
    return tuple(sorted(normalized))


def _identifiers(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must contain identifiers")
    normalized = tuple(_identifier(f"{name} item", item) for item in values)
    if not normalized or len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must be non-empty and unique")
    return tuple(sorted(normalized))


def _non_negative(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite non-negative")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError(f"{name} must be finite non-negative")
    return normalized


class ExclusionReason(str, Enum):
    IDENTITY_UNRESOLVED = "identity_unresolved"
    ROLE_MISMATCH = "role_mismatch"
    CONTEXT_CLASS_MISMATCH = "context_class_mismatch"
    QUALIFICATION_NOT_CURRENT = "qualification_not_current"
    QUALIFICATION_SNAPSHOT_MISMATCH = "qualification_snapshot_mismatch"
    PRIVACY_DENIED = "privacy_denied"
    CAPABILITY_MISSING = "capability_missing"
    VERIFIER_UNAVAILABLE = "verifier_unavailable"
    CONTEXT_CAPSULE_DENIED = "context_capsule_denied"
    CONTEXT_CAPSULE_EXPIRED = "context_capsule_expired"
    ROUTE_NOT_ALLOWLISTED = "route_not_allowlisted"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    BUDGET_UNASSESSABLE = "budget_unassessable"
    BUDGET_DENIED = "budget_denied"


@dataclass(frozen=True)
class PlanningCandidate:
    model_subject_id: str
    identity_status: IdentityStatus
    provider_id: str
    route_id: str
    parameter_profile_digest: str
    qualification_key: QualificationKey
    qualification_state: QualificationState
    qualification_evidence_set_digest: str
    approved_privacy: tuple[PrivacyLevel, ...]
    capabilities: tuple[str, ...]
    verifier_graph_digest: str
    route_allowlisted: bool
    available: bool
    expected_total_cost_usd: float | None
    expected_latency_ms: float
    verified_utility_lower_bound: float
    evidence_freshness_epoch: int
    reason_evidence_digest: str

    def __post_init__(self) -> None:
        model_subject_id = _digest("model_subject_id", self.model_subject_id)
        if not isinstance(self.identity_status, IdentityStatus):
            raise ValueError("identity_status must be an IdentityStatus")
        provider_id = _identifier("provider_id", self.provider_id)
        route_id = _digest("route_id", self.route_id)
        parameter_digest = _digest(
            "parameter_profile_digest",
            self.parameter_profile_digest,
        )
        if not isinstance(self.qualification_key, QualificationKey):
            raise ValueError("qualification_key must be a QualificationKey")
        if (
            self.qualification_key.model_subject_id != model_subject_id
            or self.qualification_key.route_id != route_id
        ):
            raise ValueError("qualification key does not bind candidate identity and route")
        if not isinstance(self.qualification_state, QualificationState):
            raise ValueError("qualification_state must be a QualificationState")
        evidence_set = _digest(
            "qualification_evidence_set_digest",
            self.qualification_evidence_set_digest,
        )
        raw_privacy = tuple(self.approved_privacy)
        if not raw_privacy or any(
            not isinstance(item, PrivacyLevel) for item in raw_privacy
        ):
            raise ValueError("approved_privacy must contain PrivacyLevel values")
        privacy = tuple(sorted(set(raw_privacy), key=lambda item: item.value))
        capabilities = _identifiers("capabilities", self.capabilities)
        verifier = _digest("verifier_graph_digest", self.verifier_graph_digest)
        if not isinstance(self.route_allowlisted, bool):
            raise ValueError("route_allowlisted must be boolean")
        if not isinstance(self.available, bool):
            raise ValueError("available must be boolean")
        cost = self.expected_total_cost_usd
        if cost is not None:
            cost = _non_negative("expected_total_cost_usd", cost)
        latency = _non_negative("expected_latency_ms", self.expected_latency_ms)
        if isinstance(self.verified_utility_lower_bound, bool) or not isinstance(
            self.verified_utility_lower_bound,
            (int, float),
        ):
            raise ValueError(
                "verified_utility_lower_bound must be between 0 and 1"
            )
        utility = float(self.verified_utility_lower_bound)
        if not math.isfinite(utility) or not 0 <= utility <= 1:
            raise ValueError(
                "verified_utility_lower_bound must be between 0 and 1"
            )
        if (
            isinstance(self.evidence_freshness_epoch, bool)
            or not isinstance(self.evidence_freshness_epoch, int)
            or self.evidence_freshness_epoch < 0
        ):
            raise ValueError("evidence_freshness_epoch must be non-negative integer")
        reason = _digest("reason_evidence_digest", self.reason_evidence_digest)
        object.__setattr__(self, "model_subject_id", model_subject_id)
        object.__setattr__(self, "provider_id", provider_id)
        object.__setattr__(self, "route_id", route_id)
        object.__setattr__(self, "parameter_profile_digest", parameter_digest)
        object.__setattr__(
            self,
            "qualification_evidence_set_digest",
            evidence_set,
        )
        object.__setattr__(self, "approved_privacy", privacy)
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "verifier_graph_digest", verifier)
        object.__setattr__(self, "expected_total_cost_usd", cost)
        object.__setattr__(self, "expected_latency_ms", latency)
        object.__setattr__(self, "verified_utility_lower_bound", utility)
        object.__setattr__(self, "reason_evidence_digest", reason)

    @property
    def candidate_id(self) -> str:
        return sha256_id("planning_candidate_v1", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "model_subject_id": self.model_subject_id,
            "identity_status": self.identity_status.value,
            "provider_id": self.provider_id,
            "route_id": self.route_id,
            "parameter_profile_digest": self.parameter_profile_digest,
            "qualification_key": self.qualification_key.digest,
            "qualification_state": self.qualification_state.value,
            "qualification_evidence_set_digest": (
                self.qualification_evidence_set_digest
            ),
            "approved_privacy": [item.value for item in self.approved_privacy],
            "capabilities": list(self.capabilities),
            "verifier_graph_digest": self.verifier_graph_digest,
            "route_allowlisted": self.route_allowlisted,
            "available": self.available,
            "expected_total_cost_usd": self.expected_total_cost_usd,
            "expected_latency_ms": self.expected_latency_ms,
            "verified_utility_lower_bound": self.verified_utility_lower_bound,
            "evidence_freshness_epoch": self.evidence_freshness_epoch,
            "reason_evidence_digest": self.reason_evidence_digest,
        }


@dataclass(frozen=True)
class PlanningInput:
    task_digest: str
    required_role_digest: str
    context_class: str
    required_capabilities: tuple[str, ...]
    privacy: PrivacyLevel
    max_cost_usd: float
    latency_objective_ms: float
    context_capsule_ids: tuple[str, ...]
    operator_policy: OperatorPolicyProfile
    operator_policy_snapshot_id: str
    qualification_snapshot_id: str
    route_snapshot_id: str
    availability_snapshot_id: str
    pricing_snapshot_id: str
    evidence_snapshot_ids: tuple[str, ...]
    topology_registry_digest: str
    planner_version: str
    topology_id: TopologyId
    plan_revision: int
    planned_at: str

    def __post_init__(self) -> None:
        for field_name in (
            "task_digest",
            "required_role_digest",
            "operator_policy_snapshot_id",
            "qualification_snapshot_id",
            "route_snapshot_id",
            "availability_snapshot_id",
            "pricing_snapshot_id",
            "topology_registry_digest",
        ):
            object.__setattr__(
                self,
                field_name,
                _digest(field_name, getattr(self, field_name)),
            )
        object.__setattr__(
            self,
            "context_class",
            _identifier("context_class", self.context_class),
        )
        object.__setattr__(
            self,
            "required_capabilities",
            _identifiers("required_capabilities", self.required_capabilities),
        )
        if not isinstance(self.privacy, PrivacyLevel):
            raise ValueError("privacy must be a PrivacyLevel")
        object.__setattr__(
            self,
            "max_cost_usd",
            _non_negative("max_cost_usd", self.max_cost_usd),
        )
        object.__setattr__(
            self,
            "latency_objective_ms",
            _non_negative("latency_objective_ms", self.latency_objective_ms),
        )
        object.__setattr__(
            self,
            "context_capsule_ids",
            _digests("context_capsule_ids", self.context_capsule_ids),
        )
        if not isinstance(self.operator_policy, OperatorPolicyProfile):
            raise ValueError("operator_policy must be an OperatorPolicyProfile")
        if self.operator_policy_snapshot_id != self.operator_policy.snapshot_id:
            raise ValueError("operator policy snapshot does not match profile")
        object.__setattr__(
            self,
            "evidence_snapshot_ids",
            _digests("evidence_snapshot_ids", self.evidence_snapshot_ids),
        )
        object.__setattr__(
            self,
            "planner_version",
            _identifier("planner_version", self.planner_version),
        )
        if not isinstance(self.topology_id, TopologyId):
            raise ValueError("topology_id must be a TopologyId")
        if (
            isinstance(self.plan_revision, bool)
            or not isinstance(self.plan_revision, int)
            or self.plan_revision < 1
        ):
            raise ValueError("plan_revision must be positive integer")
        object.__setattr__(
            self,
            "planned_at",
            aware_iso8601("planned_at", self.planned_at),
        )


@dataclass(frozen=True)
class PlanningState:
    role_slot: RoleSlot
    verifier_graph: VerifierGraph
    context_capsules: tuple[ContextCapsule, ...]
    candidates: tuple[PlanningCandidate, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.role_slot, RoleSlot):
            raise ValueError("role_slot must be a RoleSlot")
        if not isinstance(self.verifier_graph, VerifierGraph):
            raise ValueError("verifier_graph must be a VerifierGraph")
        if self.role_slot.verifier_graph_digest != self.verifier_graph.graph_digest:
            raise ValueError("role slot verifier graph mismatch")
        capsules = tuple(self.context_capsules)
        if not capsules or any(
            not isinstance(item, ContextCapsule) for item in capsules
        ):
            raise ValueError("context_capsules must contain ContextCapsule values")
        if len({item.capsule_id for item in capsules}) != len(capsules):
            raise ValueError("context_capsules contain duplicates")
        candidates = tuple(self.candidates)
        if any(not isinstance(item, PlanningCandidate) for item in candidates):
            raise ValueError("candidates must contain PlanningCandidate values")
        if len({item.route_id for item in candidates}) != len(candidates):
            raise ValueError("candidates contain duplicate routes")
        object.__setattr__(
            self,
            "context_capsules",
            tuple(sorted(capsules, key=lambda item: item.capsule_id)),
        )
        object.__setattr__(
            self,
            "candidates",
            tuple(sorted(candidates, key=lambda item: item.route_id)),
        )

    def candidate_for_route(self, route_id: str) -> PlanningCandidate:
        route_id = _digest("route_id", route_id)
        try:
            return next(item for item in self.candidates if item.route_id == route_id)
        except StopIteration as exc:
            raise PlanningError("planning state does not contain route") from exc


@dataclass(frozen=True)
class EligibilityDecision:
    candidate_id: str
    allowed: bool
    reasons: tuple[ExclusionReason, ...]


class DynamicCoordinationPlanner:
    def __init__(
        self,
        *,
        plan_id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        if not callable(plan_id_factory):
            raise ValueError("plan_id_factory must be callable")
        self._plan_id_factory = plan_id_factory

    def plan(
        self,
        planning_input: PlanningInput,
        state: PlanningState,
    ) -> CoordinationPlan:
        self._validate_input_state(planning_input, state)
        decisions = tuple(
            self._eligibility(planning_input, state, item)
            for item in state.candidates
        )
        allowed = tuple(
            candidate
            for candidate, decision in zip(state.candidates, decisions)
            if decision.allowed
        )
        if not allowed:
            raise PlanningError("no eligible binding satisfies hard policy gates")
        ranked = tuple(sorted(allowed, key=self._rank_key))
        chosen = ranked[0]
        eligible = tuple(self._eligible_record(item) for item in ranked)
        excluded = tuple(
            ExcludedCandidate(
                model_subject_id=candidate.model_subject_id,
                route_id=candidate.route_id,
                reason_code=decision.reasons[0].value,
                reason_evidence_digest=candidate.reason_evidence_digest,
            )
            for candidate, decision in zip(state.candidates, decisions)
            if not decision.allowed
        )
        cost = chosen.expected_total_cost_usd
        assert cost is not None
        budget = self._budget_evaluation(planning_input, cost)
        return CoordinationPlan.create(
            plan_id=self._plan_id_factory(),
            plan_revision=planning_input.plan_revision,
            planned_at=planning_input.planned_at,
            planner_version=planning_input.planner_version,
            topology_id=planning_input.topology_id,
            execution_mode=PlanExecutionMode.SHADOW_ONLY,
            task_digest=planning_input.task_digest,
            roles=(state.role_slot,),
            bindings=(self._binding(state, chosen),),
            context_capsule_ids=planning_input.context_capsule_ids,
            verifier_graph=state.verifier_graph,
            policy_snapshot_ids=(planning_input.operator_policy_snapshot_id,),
            evidence_snapshot_ids=planning_input.evidence_snapshot_ids,
            qualification_snapshot_id=(
                planning_input.qualification_snapshot_id
            ),
            route_snapshot_id=planning_input.route_snapshot_id,
            availability_snapshot_id=planning_input.availability_snapshot_id,
            pricing_snapshot_id=planning_input.pricing_snapshot_id,
            topology_registry_digest=planning_input.topology_registry_digest,
            eligible_candidates=eligible,
            excluded_candidates=excluded,
            budget_evaluation=budget,
            fallback_rules=(),
            tie_break_rules=_TIE_BREAK_RULES,
        )

    def revise_for_failure(
        self,
        plan: CoordinationPlan,
        *,
        failure_reason: str,
        state: PlanningState,
    ) -> CoordinationPlan:
        if not isinstance(plan, CoordinationPlan):
            raise ValueError("plan must be a CoordinationPlan")
        if not isinstance(state, PlanningState):
            raise ValueError("state must be a PlanningState")
        reason = _identifier("failure_reason", failure_reason)
        if len(plan.bindings) != 1:
            raise PlanningError("fallback revision currently requires one binding")
        prior = plan.bindings[0]
        remaining_routes = {
            item.route_id for item in plan.eligible_candidates
            if item.route_id != prior.route_id
        }
        remaining = tuple(
            item for item in state.candidates if item.route_id in remaining_routes
        )
        if not remaining:
            raise PlanningError("no eligible fallback binding remains")
        chosen = sorted(remaining, key=self._rank_key)[0]
        failure_evidence = sha256_id(
            "plan_fallback_failure_v1",
            {
                "prior_plan_digest": plan.plan_digest,
                "from_route_id": prior.route_id,
                "reason_code": reason,
                "next_revision": plan.plan_revision + 1,
            },
        )
        availability_snapshot = sha256_id(
            "availability_revision_v1",
            {
                "previous_snapshot_id": plan.availability_snapshot_id,
                "failure_evidence_digest": failure_evidence,
            },
        )
        eligible = tuple(
            item for item in plan.eligible_candidates
            if item.route_id != prior.route_id
        )
        excluded = tuple(plan.excluded_candidates) + (
            ExcludedCandidate(
                model_subject_id=prior.model_subject_id,
                route_id=prior.route_id,
                reason_code=ExclusionReason.PROVIDER_UNAVAILABLE.value,
                reason_evidence_digest=failure_evidence,
            ),
        )
        cost = chosen.expected_total_cost_usd
        if cost is None:
            raise PlanningError("fallback cost cannot be evaluated")
        threshold = plan.budget_evaluation.warning_threshold_usd
        warning = (
            plan.budget_evaluation.budget_mode == BudgetMode.WARN.value
            and threshold is not None
            and cost > threshold
        )
        return CoordinationPlan.create(
            plan_id=plan.plan_id,
            plan_revision=plan.plan_revision + 1,
            planned_at=plan.planned_at,
            planner_version=plan.planner_version,
            topology_id=plan.topology_id,
            execution_mode=PlanExecutionMode.SHADOW_ONLY,
            task_digest=plan.task_digest,
            roles=plan.roles,
            bindings=(self._binding(state, chosen),),
            context_capsule_ids=plan.context_capsule_ids,
            verifier_graph=plan.verifier_graph,
            policy_snapshot_ids=plan.policy_snapshot_ids,
            evidence_snapshot_ids=tuple(
                sorted((*plan.evidence_snapshot_ids, failure_evidence))
            ),
            qualification_snapshot_id=plan.qualification_snapshot_id,
            route_snapshot_id=plan.route_snapshot_id,
            availability_snapshot_id=availability_snapshot,
            pricing_snapshot_id=plan.pricing_snapshot_id,
            topology_registry_digest=plan.topology_registry_digest,
            eligible_candidates=eligible,
            excluded_candidates=excluded,
            budget_evaluation=BudgetEvaluation(
                budget_mode=plan.budget_evaluation.budget_mode,
                estimated_total_cost_usd=cost,
                warning_threshold_usd=threshold,
                warning_triggered=warning,
            ),
            fallback_rules=tuple(plan.fallback_rules)
            + (
                FallbackRule(
                    reason_code=reason,
                    from_route_id=prior.route_id,
                    to_route_id=chosen.route_id,
                ),
            ),
            tie_break_rules=plan.tie_break_rules,
        )

    @staticmethod
    def _validate_input_state(
        planning_input: PlanningInput,
        state: PlanningState,
    ) -> None:
        if not isinstance(planning_input, PlanningInput):
            raise ValueError("planning_input must be a PlanningInput")
        if not isinstance(state, PlanningState):
            raise ValueError("state must be a PlanningState")
        if state.role_slot.role_definition_digest != planning_input.required_role_digest:
            raise PlanningError("role slot does not match required role")
        capsule_ids = tuple(item.capsule_id for item in state.context_capsules)
        if tuple(sorted(capsule_ids)) != planning_input.context_capsule_ids:
            raise PlanningError("context capsule snapshot does not match input")
        if state.role_slot.context_capsule_ids != planning_input.context_capsule_ids:
            raise PlanningError("role slot context capsules do not match input")

    @staticmethod
    def _eligibility(
        planning_input: PlanningInput,
        state: PlanningState,
        candidate: PlanningCandidate,
    ) -> EligibilityDecision:
        reasons: list[ExclusionReason] = []
        if candidate.identity_status not in {
            IdentityStatus.RESOLVED,
            IdentityStatus.CLAIMED,
        }:
            reasons.append(ExclusionReason.IDENTITY_UNRESOLVED)
        key = candidate.qualification_key
        if key.role_digest != planning_input.required_role_digest:
            reasons.append(ExclusionReason.ROLE_MISMATCH)
        if key.context_class != planning_input.context_class:
            reasons.append(ExclusionReason.CONTEXT_CLASS_MISMATCH)
        if candidate.qualification_state is not QualificationState.QUALIFIED:
            reasons.append(ExclusionReason.QUALIFICATION_NOT_CURRENT)
        if (
            candidate.qualification_evidence_set_digest
            not in planning_input.evidence_snapshot_ids
        ):
            reasons.append(ExclusionReason.QUALIFICATION_SNAPSHOT_MISMATCH)
        if planning_input.privacy not in candidate.approved_privacy:
            reasons.append(ExclusionReason.PRIVACY_DENIED)
        if not set(planning_input.required_capabilities).issubset(
            candidate.capabilities
        ):
            reasons.append(ExclusionReason.CAPABILITY_MISSING)
        if candidate.verifier_graph_digest != state.verifier_graph.graph_digest:
            reasons.append(ExclusionReason.VERIFIER_UNAVAILABLE)
        for capsule in state.context_capsules:
            if capsule.data_classification not in candidate.approved_privacy:
                reasons.append(ExclusionReason.PRIVACY_DENIED)
            if (
                capsule.expires_at is not None
                and planning_input.planned_at >= capsule.expires_at
            ):
                reasons.append(ExclusionReason.CONTEXT_CAPSULE_EXPIRED)
            try:
                capsule.assert_allowed(
                    planning_input.required_role_digest,
                    candidate.route_id,
                )
            except ValueError:
                reasons.append(ExclusionReason.CONTEXT_CAPSULE_DENIED)
                break
        if not candidate.route_allowlisted:
            reasons.append(ExclusionReason.ROUTE_NOT_ALLOWLISTED)
        if not candidate.available:
            reasons.append(ExclusionReason.PROVIDER_UNAVAILABLE)
        if candidate.expected_total_cost_usd is None:
            reasons.append(ExclusionReason.BUDGET_UNASSESSABLE)
        elif (
            planning_input.operator_policy.budget_mode is BudgetMode.ENFORCE
            and candidate.expected_total_cost_usd > planning_input.max_cost_usd
        ):
            reasons.append(ExclusionReason.BUDGET_DENIED)
        reasons = list(dict.fromkeys(reasons))
        return EligibilityDecision(
            candidate_id=candidate.candidate_id,
            allowed=not reasons,
            reasons=tuple(reasons),
        )

    @staticmethod
    def _rank_key(candidate: PlanningCandidate) -> tuple[object, ...]:
        cost = candidate.expected_total_cost_usd
        if cost is None:
            raise PlanningError("eligible candidate cost is unavailable")
        return (
            -candidate.verified_utility_lower_bound,
            cost,
            candidate.expected_latency_ms,
            -candidate.evidence_freshness_epoch,
            candidate.route_id,
        )

    @staticmethod
    def _eligible_record(candidate: PlanningCandidate) -> EligibleCandidate:
        cost = candidate.expected_total_cost_usd
        if cost is None:
            raise PlanningError("eligible candidate cost is unavailable")
        return EligibleCandidate(
            model_subject_id=candidate.model_subject_id,
            route_id=candidate.route_id,
            qualification_key=candidate.qualification_key.digest,
            verified_utility_lower_bound=(
                candidate.verified_utility_lower_bound
            ),
            expected_total_cost_usd=cost,
            expected_latency_ms=candidate.expected_latency_ms,
            evidence_freshness_epoch=candidate.evidence_freshness_epoch,
        )

    @staticmethod
    def _binding(
        state: PlanningState,
        candidate: PlanningCandidate,
    ) -> ModelBinding:
        return ModelBinding(
            slot_id=state.role_slot.slot_id,
            model_subject_id=candidate.model_subject_id,
            route_id=candidate.route_id,
            qualification_key=candidate.qualification_key.digest,
            parameter_profile_digest=candidate.parameter_profile_digest,
            context_capsule_ids=state.role_slot.context_capsule_ids,
        )

    @staticmethod
    def _budget_evaluation(
        planning_input: PlanningInput,
        cost: float,
    ) -> BudgetEvaluation:
        mode = planning_input.operator_policy.budget_mode
        return BudgetEvaluation(
            budget_mode=mode.value,
            estimated_total_cost_usd=cost,
            warning_threshold_usd=planning_input.max_cost_usd,
            warning_triggered=(
                mode is BudgetMode.WARN and cost > planning_input.max_cost_usd
            ),
        )


__all__ = [
    "DynamicCoordinationPlanner",
    "EligibilityDecision",
    "ExclusionReason",
    "PlanningCandidate",
    "PlanningError",
    "PlanningInput",
    "PlanningState",
]
