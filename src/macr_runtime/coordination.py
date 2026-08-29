from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .canonical import aware_iso8601, sha256_id
from .verification_graph import VerifierGraph


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded identifier")
    return value


def _digests(
    name: str,
    values: Iterable[str],
    *,
    required: bool,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must contain digests")
    normalized = tuple(_digest(f"{name} item", item) for item in values)
    if required and not normalized:
        raise ValueError(f"{name} must not be empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must not contain duplicates")
    return tuple(sorted(normalized))


def _identifiers(
    name: str,
    values: Iterable[str],
    *,
    required: bool,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must contain identifiers")
    normalized = tuple(_identifier(f"{name} item", item) for item in values)
    if required and not normalized:
        raise ValueError(f"{name} must not be empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must not contain duplicates")
    return tuple(sorted(normalized))


def _ordered_identifiers(
    name: str,
    values: Iterable[str],
    *,
    required: bool,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must contain identifiers")
    normalized = tuple(_identifier(f"{name} item", item) for item in values)
    if required and not normalized:
        raise ValueError(f"{name} must not be empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must not contain duplicates")
    return normalized


def _non_negative(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite non-negative")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError(f"{name} must be finite non-negative")
    return normalized


def _uuid4(name: str, value: object) -> str:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a UUIDv4") from exc
    if parsed.version != 4 or str(parsed) != str(value).lower():
        raise ValueError(f"{name} must be a canonical UUIDv4")
    return str(parsed)


class TopologyId(str, Enum):
    T0_DIRECT_VERIFIED = "T0_DIRECT_VERIFIED"
    T1_FANOUT_VERIFIED = "T1_FANOUT_VERIFIED"
    T2_SUPERVISOR_WORKER = "T2_SUPERVISOR_WORKER"
    T3_CROSSFILE_PAIR_EXPERIMENTAL = "T3_CROSSFILE_PAIR_EXPERIMENTAL"


class PlanExecutionMode(str, Enum):
    SHADOW_ONLY = "shadow_only"
    EXECUTION_ELIGIBLE = "execution_eligible"


@dataclass(frozen=True)
class RoleSlot:
    slot_id: str
    role_definition_digest: str
    authority: tuple[str, ...]
    context_capsule_ids: tuple[str, ...]
    verifier_graph_digest: str
    required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "slot_id", _identifier("slot_id", self.slot_id))
        object.__setattr__(
            self,
            "role_definition_digest",
            _digest("role_definition_digest", self.role_definition_digest),
        )
        object.__setattr__(
            self,
            "authority",
            _identifiers("authority", self.authority, required=True),
        )
        object.__setattr__(
            self,
            "context_capsule_ids",
            _digests(
                "context_capsule_ids",
                self.context_capsule_ids,
                required=True,
            ),
        )
        object.__setattr__(
            self,
            "verifier_graph_digest",
            _digest("verifier_graph_digest", self.verifier_graph_digest),
        )
        if not isinstance(self.required, bool):
            raise ValueError("role slot required must be boolean")

    @classmethod
    def create(
        cls,
        slot_id: str,
        role_definition_digest: str,
        *,
        authority: Iterable[str],
        context_capsule_ids: Iterable[str],
        verifier_graph_digest: str,
        required: bool = True,
    ) -> "RoleSlot":
        return cls(
            slot_id=slot_id,
            role_definition_digest=role_definition_digest,
            authority=tuple(authority),
            context_capsule_ids=tuple(context_capsule_ids),
            verifier_graph_digest=verifier_graph_digest,
            required=required,
        )

    @property
    def slot_digest(self) -> str:
        return sha256_id("coordination_role_slot_v1", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "slot_id": self.slot_id,
            "role_definition_digest": self.role_definition_digest,
            "authority": list(self.authority),
            "context_capsule_ids": list(self.context_capsule_ids),
            "verifier_graph_digest": self.verifier_graph_digest,
            "required": self.required,
        }


@dataclass(frozen=True)
class ModelBinding:
    slot_id: str
    model_subject_id: str
    route_id: str
    qualification_key: str
    parameter_profile_digest: str
    context_capsule_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "slot_id", _identifier("slot_id", self.slot_id))
        for field_name in (
            "model_subject_id",
            "route_id",
            "qualification_key",
            "parameter_profile_digest",
        ):
            object.__setattr__(
                self,
                field_name,
                _digest(field_name, getattr(self, field_name)),
            )
        object.__setattr__(
            self,
            "context_capsule_ids",
            _digests(
                "context_capsule_ids",
                self.context_capsule_ids,
                required=True,
            ),
        )

    @property
    def binding_digest(self) -> str:
        return sha256_id("coordination_model_binding_v1", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "slot_id": self.slot_id,
            "model_subject_id": self.model_subject_id,
            "route_id": self.route_id,
            "qualification_key": self.qualification_key,
            "parameter_profile_digest": self.parameter_profile_digest,
            "context_capsule_ids": list(self.context_capsule_ids),
        }


@dataclass(frozen=True)
class EligibleCandidate:
    model_subject_id: str
    route_id: str
    qualification_key: str
    verified_utility_lower_bound: float
    expected_total_cost_usd: float
    expected_latency_ms: float
    evidence_freshness_epoch: int

    def __post_init__(self) -> None:
        for field_name in (
            "model_subject_id",
            "route_id",
            "qualification_key",
        ):
            object.__setattr__(
                self,
                field_name,
                _digest(field_name, getattr(self, field_name)),
            )
        if isinstance(self.verified_utility_lower_bound, bool):
            raise ValueError(
                "verified_utility_lower_bound must be between 0 and 1"
            )
        utility = float(self.verified_utility_lower_bound)
        if not math.isfinite(utility) or not 0 <= utility <= 1:
            raise ValueError(
                "verified_utility_lower_bound must be between 0 and 1"
            )
        object.__setattr__(self, "verified_utility_lower_bound", utility)
        object.__setattr__(
            self,
            "expected_total_cost_usd",
            _non_negative(
                "expected_total_cost_usd",
                self.expected_total_cost_usd,
            ),
        )
        object.__setattr__(
            self,
            "expected_latency_ms",
            _non_negative("expected_latency_ms", self.expected_latency_ms),
        )
        if (
            isinstance(self.evidence_freshness_epoch, bool)
            or not isinstance(self.evidence_freshness_epoch, int)
            or self.evidence_freshness_epoch < 0
        ):
            raise ValueError("evidence_freshness_epoch must be non-negative integer")

    def to_dict(self) -> dict[str, object]:
        return {
            "model_subject_id": self.model_subject_id,
            "route_id": self.route_id,
            "qualification_key": self.qualification_key,
            "verified_utility_lower_bound": self.verified_utility_lower_bound,
            "expected_total_cost_usd": self.expected_total_cost_usd,
            "expected_latency_ms": self.expected_latency_ms,
            "evidence_freshness_epoch": self.evidence_freshness_epoch,
        }


@dataclass(frozen=True)
class ExcludedCandidate:
    model_subject_id: str
    route_id: str
    reason_code: str
    reason_evidence_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_subject_id",
            _digest("model_subject_id", self.model_subject_id),
        )
        object.__setattr__(self, "route_id", _digest("route_id", self.route_id))
        object.__setattr__(
            self,
            "reason_code",
            _identifier("reason_code", self.reason_code),
        )
        object.__setattr__(
            self,
            "reason_evidence_digest",
            _digest("reason_evidence_digest", self.reason_evidence_digest),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "model_subject_id": self.model_subject_id,
            "route_id": self.route_id,
            "reason_code": self.reason_code,
            "reason_evidence_digest": self.reason_evidence_digest,
        }


@dataclass(frozen=True)
class BudgetEvaluation:
    budget_mode: str
    estimated_total_cost_usd: float
    warning_threshold_usd: float | None
    warning_triggered: bool

    def __post_init__(self) -> None:
        if self.budget_mode not in {"observe", "warn", "enforce"}:
            raise ValueError("budget_mode is invalid")
        object.__setattr__(
            self,
            "estimated_total_cost_usd",
            _non_negative(
                "estimated_total_cost_usd",
                self.estimated_total_cost_usd,
            ),
        )
        if self.warning_threshold_usd is not None:
            object.__setattr__(
                self,
                "warning_threshold_usd",
                _non_negative(
                    "warning_threshold_usd",
                    self.warning_threshold_usd,
                ),
            )
        if not isinstance(self.warning_triggered, bool):
            raise ValueError("warning_triggered must be boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "budget_mode": self.budget_mode,
            "estimated_total_cost_usd": self.estimated_total_cost_usd,
            "warning_threshold_usd": self.warning_threshold_usd,
            "warning_triggered": self.warning_triggered,
        }


@dataclass(frozen=True)
class FallbackRule:
    reason_code: str
    from_route_id: str
    to_route_id: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reason_code",
            _identifier("reason_code", self.reason_code),
        )
        object.__setattr__(
            self,
            "from_route_id",
            _digest("from_route_id", self.from_route_id),
        )
        if self.to_route_id is not None:
            object.__setattr__(
                self,
                "to_route_id",
                _digest("to_route_id", self.to_route_id),
            )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "reason_code": self.reason_code,
            "from_route_id": self.from_route_id,
            "to_route_id": self.to_route_id,
        }


@dataclass(frozen=True)
class CoordinationPlan:
    plan_id: str
    plan_revision: int
    planned_at: str
    planner_version: str
    topology_id: TopologyId
    execution_mode: PlanExecutionMode
    task_digest: str
    roles: tuple[RoleSlot, ...]
    bindings: tuple[ModelBinding, ...]
    context_capsule_ids: tuple[str, ...]
    verifier_graph: VerifierGraph
    policy_snapshot_ids: tuple[str, ...]
    evidence_snapshot_ids: tuple[str, ...]
    qualification_snapshot_id: str
    route_snapshot_id: str
    availability_snapshot_id: str
    pricing_snapshot_id: str
    topology_registry_digest: str
    eligible_candidates: tuple[EligibleCandidate, ...]
    excluded_candidates: tuple[ExcludedCandidate, ...]
    budget_evaluation: BudgetEvaluation
    fallback_rules: tuple[FallbackRule, ...]
    tie_break_rules: tuple[str, ...]
    acceptance_authority: str = "host_only"

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", _uuid4("plan_id", self.plan_id))
        if (
            isinstance(self.plan_revision, bool)
            or not isinstance(self.plan_revision, int)
            or self.plan_revision < 1
        ):
            raise ValueError("plan_revision must be a positive integer")
        object.__setattr__(
            self,
            "planned_at",
            aware_iso8601("planned_at", self.planned_at),
        )
        object.__setattr__(
            self,
            "planner_version",
            _identifier("planner_version", self.planner_version),
        )
        if not isinstance(self.topology_id, TopologyId):
            raise ValueError("topology_id must be a TopologyId")
        if not isinstance(self.execution_mode, PlanExecutionMode):
            raise ValueError("execution_mode must be a PlanExecutionMode")
        object.__setattr__(self, "task_digest", _digest("task_digest", self.task_digest))
        roles = tuple(self.roles)
        if not roles or any(not isinstance(item, RoleSlot) for item in roles):
            raise ValueError("roles must contain RoleSlot values")
        roles = tuple(sorted(roles, key=lambda item: item.slot_id))
        if len({item.slot_id for item in roles}) != len(roles):
            raise ValueError("roles contain duplicate slot")
        bindings = tuple(self.bindings)
        if not bindings or any(
            not isinstance(item, ModelBinding) for item in bindings
        ):
            raise ValueError("bindings must contain ModelBinding values")
        bindings = tuple(
            sorted(bindings, key=lambda item: (item.slot_id, item.route_id))
        )
        if len({item.slot_id for item in bindings}) != len(bindings):
            raise ValueError("bindings contain duplicate slot")
        role_slots = {item.slot_id for item in roles}
        unknown_slots = sorted({item.slot_id for item in bindings} - role_slots)
        missing_required = sorted(
            item.slot_id
            for item in roles
            if item.required and item.slot_id not in {binding.slot_id for binding in bindings}
        )
        if unknown_slots or missing_required:
            raise ValueError("binding slot does not match required role slot")
        capsules = _digests(
            "context_capsule_ids",
            self.context_capsule_ids,
            required=True,
        )
        for item in (*roles, *bindings):
            if not set(item.context_capsule_ids).issubset(capsules):
                raise ValueError("role or binding capsule is not in plan capsules")
        if not isinstance(self.verifier_graph, VerifierGraph):
            raise ValueError("verifier_graph must be a VerifierGraph")
        if any(
            item.verifier_graph_digest != self.verifier_graph.graph_digest
            for item in roles
        ):
            raise ValueError("role verifier graph does not match plan verifier graph")
        object.__setattr__(
            self,
            "policy_snapshot_ids",
            _digests(
                "policy_snapshot_ids",
                self.policy_snapshot_ids,
                required=True,
            ),
        )
        object.__setattr__(
            self,
            "evidence_snapshot_ids",
            _digests(
                "evidence_snapshot_ids",
                self.evidence_snapshot_ids,
                required=True,
            ),
        )
        for field_name in (
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
        eligible = tuple(self.eligible_candidates)
        if any(not isinstance(item, EligibleCandidate) for item in eligible):
            raise ValueError("eligible_candidates are invalid")
        eligible = tuple(
            sorted(
                eligible,
                key=lambda item: (item.route_id, item.qualification_key),
            )
        )
        excluded = tuple(self.excluded_candidates)
        if any(not isinstance(item, ExcludedCandidate) for item in excluded):
            raise ValueError("excluded_candidates are invalid")
        excluded = tuple(
            sorted(
                excluded,
                key=lambda item: (item.route_id, item.reason_code),
            )
        )
        chosen_routes = {item.route_id for item in bindings}
        eligible_routes = {item.route_id for item in eligible}
        if not chosen_routes.issubset(eligible_routes):
            raise ValueError("chosen binding route is not an eligible candidate")
        if eligible_routes & {item.route_id for item in excluded}:
            raise ValueError("candidate route cannot be eligible and excluded")
        if not isinstance(self.budget_evaluation, BudgetEvaluation):
            raise ValueError("budget_evaluation must be a BudgetEvaluation")
        fallback = tuple(self.fallback_rules)
        if any(not isinstance(item, FallbackRule) for item in fallback):
            raise ValueError("fallback_rules must contain FallbackRule values")
        tie_breaks = _ordered_identifiers(
            "tie_break_rules",
            self.tie_break_rules,
            required=True,
        )
        if self.acceptance_authority != "host_only":
            raise ValueError("acceptance_authority must be host_only")
        if self.topology_id is TopologyId.T0_DIRECT_VERIFIED and (
            len(roles) != 1 or len(bindings) != 1
        ):
            raise ValueError("T0 requires exactly one role and one binding")
        object.__setattr__(self, "roles", roles)
        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(self, "context_capsule_ids", capsules)
        object.__setattr__(self, "eligible_candidates", eligible)
        object.__setattr__(self, "excluded_candidates", excluded)
        object.__setattr__(self, "fallback_rules", fallback)
        object.__setattr__(self, "tie_break_rules", tie_breaks)

    @classmethod
    def create(cls, **values) -> "CoordinationPlan":
        return cls(**values)

    @property
    def plan_digest(self) -> str:
        return sha256_id("coordination_plan_v1", self.canonical_plan())

    def canonical_digest(self) -> str:
        return self.plan_digest

    def canonical_plan(self) -> dict[str, object]:
        return {
            "plan_revision": self.plan_revision,
            "planned_at": self.planned_at,
            "planner_version": self.planner_version,
            "topology_id": self.topology_id.value,
            "execution_mode": self.execution_mode.value,
            "task_digest": self.task_digest,
            "roles": [item.to_dict() for item in self.roles],
            "bindings": [item.to_dict() for item in self.bindings],
            "context_capsule_ids": list(self.context_capsule_ids),
            "verifier_graph": self.verifier_graph.to_dict(),
            "policy_snapshot_ids": list(self.policy_snapshot_ids),
            "evidence_snapshot_ids": list(self.evidence_snapshot_ids),
            "qualification_snapshot_id": self.qualification_snapshot_id,
            "route_snapshot_id": self.route_snapshot_id,
            "availability_snapshot_id": self.availability_snapshot_id,
            "pricing_snapshot_id": self.pricing_snapshot_id,
            "topology_registry_digest": self.topology_registry_digest,
            "eligible_candidates": [
                item.to_dict() for item in self.eligible_candidates
            ],
            "excluded_candidates": [
                item.to_dict() for item in self.excluded_candidates
            ],
            "budget_evaluation": self.budget_evaluation.to_dict(),
            "fallback_rules": [item.to_dict() for item in self.fallback_rules],
            "tie_break_rules": list(self.tie_break_rules),
            "acceptance_authority": self.acceptance_authority,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "plan_digest": self.plan_digest,
            **self.canonical_plan(),
        }


__all__ = [
    "BudgetEvaluation",
    "CoordinationPlan",
    "EligibleCandidate",
    "ExcludedCandidate",
    "FallbackRule",
    "ModelBinding",
    "PlanExecutionMode",
    "RoleSlot",
    "TopologyId",
]
