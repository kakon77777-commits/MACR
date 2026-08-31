from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .._v07_contracts import (
    canonical_record_digest,
    normalize_timestamp,
    require_closed_mapping,
    require_non_empty,
    require_non_negative_int,
    require_non_negative_number,
    require_optional_non_empty,
    require_positive_int,
    require_sha256,
    require_string_tuple,
    require_uuid4,
)
from ..execution import AuthorizationReference


class EffectName(str, Enum):
    REPOSITORY_READ = "repository.read"
    REPOSITORY_WORKING_TREE_WRITE = "repository.working_tree.write"
    REPOSITORY_BRANCH_WRITE = "repository.branch.write"
    PROCESS_EXECUTE = "process.execute"
    SOFTWARE_DOMAIN_INSPECT = "software_domain.inspect"
    SOFTWARE_DOMAIN_PAUSE = "software_domain.pause"
    SOFTWARE_DOMAIN_RESUME = "software_domain.resume"
    SOFTWARE_DOMAIN_TEMPORAL_RATE_WRITE = "software_domain.temporal_rate.write"


class CapabilityAvailability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    DISABLED = "disabled"
    UNSUPPORTED = "unsupported"


class AdmissionDecision(str, Enum):
    ALLOW = "allow"
    ALLOW_WITH_VERIFY = "allow_with_verify"
    REQUIRE_APPROVAL = "require_approval"
    DEFER = "defer"
    DENY = "deny"
    ESCALATE = "escalate"


class ActionAttemptState(str, Enum):
    CREATED = "created"
    DISPATCHING = "dispatching"
    DISPATCHED = "dispatched"
    RECEIPT_CAPTURED = "receipt_captured"
    FAILED = "failed"


class ReceiptStatus(str, Enum):
    ACCEPTED = "accepted"
    APPLYING = "applying"
    CONFIRMED = "confirmed"
    PARTIAL = "partial"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    COMPENSATED = "compensated"
    EXPIRED = "expired"


class VerificationVerdict(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    DIVERGED = "diverged"
    UNKNOWN = "unknown"
    STALE = "stale"


class ReconciliationClassification(str, Enum):
    NOT_EXECUTED = "not_executed"
    EXECUTED_AS_EXPECTED = "executed_as_expected"
    EXECUTED_DIFFERENTLY = "executed_differently"
    PARTIALLY_EXECUTED = "partially_executed"
    STATE_UNKNOWN = "state_unknown"
    COMPENSATION_REQUIRED = "compensation_required"


@dataclass(frozen=True)
class EffectSet:
    effects: tuple[EffectName, ...]
    effect_digest: str = field(init=False)

    def __post_init__(self) -> None:
        normalized = tuple(self.effects)
        if not normalized or any(not isinstance(item, EffectName) for item in normalized):
            raise ValueError("effects must contain one or more EffectName values")
        values = [item.value for item in normalized]
        if len(set(values)) != len(values):
            raise ValueError("effects must not contain duplicates")
        normalized = tuple(sorted(normalized, key=lambda item: item.value))
        object.__setattr__(self, "effects", normalized)
        object.__setattr__(
            self,
            "effect_digest",
            canonical_record_digest(
                "macr.action.effect-set.v1",
                {"effects": [item.value for item in normalized]},
            ),
        )

    @classmethod
    def from_values(cls, values: Sequence[str | EffectName]) -> "EffectSet":
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
            raise ValueError("effects must be an array")
        return cls(tuple(item if isinstance(item, EffectName) else EffectName(item) for item in values))

    def to_public_dict(self) -> dict[str, object]:
        return {
            "effects": [item.value for item in self.effects],
            "effect_digest": self.effect_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EffectSet":
        parsed = require_closed_mapping(
            "EffectSet",
            data,
            required=frozenset({"effects", "effect_digest"}),
            optional=frozenset(),
        )
        result = cls.from_values(tuple(parsed["effects"]))
        _verify_digest("EffectSet", result.effect_digest, parsed["effect_digest"])
        return result


@dataclass(frozen=True)
class CapabilityRef:
    capability_id: str
    provider: str
    operation: str
    effect_profile_ref: str
    adapter_version: str
    availability_state: CapabilityAvailability
    capability_digest: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "capability_id",
            "provider",
            "operation",
            "effect_profile_ref",
            "adapter_version",
        ):
            object.__setattr__(self, name, require_non_empty(name, getattr(self, name)))
        if not isinstance(self.availability_state, CapabilityAvailability):
            raise ValueError("availability_state must be a CapabilityAvailability")
        object.__setattr__(
            self,
            "capability_digest",
            canonical_record_digest(
                "macr.action.capability-ref.v1",
                {
                    "capability_id": self.capability_id,
                    "provider": self.provider,
                    "operation": self.operation,
                    "effect_profile_ref": self.effect_profile_ref,
                    "adapter_version": self.adapter_version,
                    "availability_state": self.availability_state.value,
                },
            ),
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "capability_id": self.capability_id,
            "provider": self.provider,
            "operation": self.operation,
            "effect_profile_ref": self.effect_profile_ref,
            "adapter_version": self.adapter_version,
            "availability_state": self.availability_state.value,
            "capability_digest": self.capability_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CapabilityRef":
        required = frozenset(
            {
                "capability_id",
                "provider",
                "operation",
                "effect_profile_ref",
                "adapter_version",
                "availability_state",
                "capability_digest",
            }
        )
        parsed = require_closed_mapping("CapabilityRef", data, required=required, optional=frozenset())
        result = cls(
            capability_id=parsed["capability_id"],
            provider=parsed["provider"],
            operation=parsed["operation"],
            effect_profile_ref=parsed["effect_profile_ref"],
            adapter_version=parsed["adapter_version"],
            availability_state=CapabilityAvailability(parsed["availability_state"]),
        )
        _verify_digest("CapabilityRef", result.capability_digest, parsed["capability_digest"])
        return result


@dataclass(frozen=True)
class BudgetEnvelope:
    budget_id: str
    agent_run_id: str
    provider_calls: int
    currency_cost_usd: int | float
    wall_clock_seconds: int | float
    child_agent_count: int
    revision: int
    budget_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "budget_id", require_non_empty("budget_id", self.budget_id))
        object.__setattr__(self, "agent_run_id", require_uuid4("agent_run_id", self.agent_run_id))
        object.__setattr__(
            self,
            "provider_calls",
            require_non_negative_int("provider_calls", self.provider_calls),
        )
        object.__setattr__(
            self,
            "currency_cost_usd",
            require_non_negative_number("currency_cost_usd", self.currency_cost_usd),
        )
        object.__setattr__(
            self,
            "wall_clock_seconds",
            require_non_negative_number("wall_clock_seconds", self.wall_clock_seconds),
        )
        object.__setattr__(
            self,
            "child_agent_count",
            require_non_negative_int("child_agent_count", self.child_agent_count),
        )
        object.__setattr__(self, "revision", require_positive_int("revision", self.revision))
        object.__setattr__(
            self,
            "budget_digest",
            canonical_record_digest("macr.action.budget-envelope.v1", self._identity_dict()),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "budget_id": self.budget_id,
            "agent_run_id": self.agent_run_id,
            "provider_calls": self.provider_calls,
            "currency_cost_usd": self.currency_cost_usd,
            "wall_clock_seconds": self.wall_clock_seconds,
            "child_agent_count": self.child_agent_count,
            "revision": self.revision,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "budget_digest": self.budget_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BudgetEnvelope":
        required = frozenset(
            {
                "budget_id",
                "agent_run_id",
                "provider_calls",
                "currency_cost_usd",
                "wall_clock_seconds",
                "child_agent_count",
                "revision",
                "budget_digest",
            }
        )
        parsed = require_closed_mapping("BudgetEnvelope", data, required=required, optional=frozenset())
        result = cls(**{name: parsed[name] for name in required if name != "budget_digest"})
        _verify_digest("BudgetEnvelope", result.budget_digest, parsed["budget_digest"])
        return result


@dataclass(frozen=True)
class ActionProposal:
    action_id: str
    agent_run_id: str
    agent_run_epoch: int
    goal_ref: str
    plan_ref: str
    task_ref: str
    operation: str
    target_ref: str
    parameters_ref: str
    declared_effects: EffectSet
    basis_refs: tuple[str, ...]
    preconditions: tuple[str, ...]
    expected_result_ref: str
    rollback_policy_ref: str
    verification_policy_ref: str
    provenance_ref: str
    proposal_digest: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "action_id",
            "goal_ref",
            "plan_ref",
            "task_ref",
            "operation",
            "target_ref",
            "parameters_ref",
            "expected_result_ref",
            "rollback_policy_ref",
            "verification_policy_ref",
            "provenance_ref",
        ):
            object.__setattr__(self, name, require_non_empty(name, getattr(self, name)))
        object.__setattr__(self, "agent_run_id", require_uuid4("agent_run_id", self.agent_run_id))
        object.__setattr__(
            self,
            "agent_run_epoch",
            require_non_negative_int("agent_run_epoch", self.agent_run_epoch),
        )
        if not isinstance(self.declared_effects, EffectSet):
            raise ValueError("declared_effects must be an EffectSet")
        basis = require_string_tuple("basis_refs", self.basis_refs)
        if not basis:
            raise ValueError("basis_refs must not be empty")
        object.__setattr__(self, "basis_refs", basis)
        object.__setattr__(
            self,
            "preconditions",
            require_string_tuple("preconditions", self.preconditions),
        )
        object.__setattr__(
            self,
            "proposal_digest",
            canonical_record_digest("macr.action.proposal.v1", self._identity_dict()),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "agent_run_id": self.agent_run_id,
            "agent_run_epoch": self.agent_run_epoch,
            "goal_ref": self.goal_ref,
            "plan_ref": self.plan_ref,
            "task_ref": self.task_ref,
            "operation": self.operation,
            "target_ref": self.target_ref,
            "parameters_ref": self.parameters_ref,
            "declared_effect_digest": self.declared_effects.effect_digest,
            "basis_refs": list(self.basis_refs),
            "preconditions": list(self.preconditions),
            "expected_result_ref": self.expected_result_ref,
            "rollback_policy_ref": self.rollback_policy_ref,
            "verification_policy_ref": self.verification_policy_ref,
            "provenance_ref": self.provenance_ref,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "agent_run_id": self.agent_run_id,
            "agent_run_epoch": self.agent_run_epoch,
            "goal_ref": self.goal_ref,
            "plan_ref": self.plan_ref,
            "task_ref": self.task_ref,
            "operation": self.operation,
            "target_ref": self.target_ref,
            "parameters_ref": self.parameters_ref,
            "declared_effects": self.declared_effects.to_public_dict(),
            "basis_refs": list(self.basis_refs),
            "preconditions": list(self.preconditions),
            "expected_result_ref": self.expected_result_ref,
            "rollback_policy_ref": self.rollback_policy_ref,
            "verification_policy_ref": self.verification_policy_ref,
            "provenance_ref": self.provenance_ref,
            "proposal_digest": self.proposal_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ActionProposal":
        required = frozenset(
            {
                "action_id", "agent_run_id", "agent_run_epoch", "goal_ref",
                "plan_ref", "task_ref", "operation", "target_ref", "parameters_ref",
                "declared_effects", "basis_refs", "preconditions", "expected_result_ref",
                "rollback_policy_ref", "verification_policy_ref", "provenance_ref",
                "proposal_digest",
            }
        )
        parsed = require_closed_mapping("ActionProposal", data, required=required, optional=frozenset())
        result = cls(
            action_id=parsed["action_id"],
            agent_run_id=parsed["agent_run_id"],
            agent_run_epoch=parsed["agent_run_epoch"],
            goal_ref=parsed["goal_ref"],
            plan_ref=parsed["plan_ref"],
            task_ref=parsed["task_ref"],
            operation=parsed["operation"],
            target_ref=parsed["target_ref"],
            parameters_ref=parsed["parameters_ref"],
            declared_effects=EffectSet.from_dict(parsed["declared_effects"]),
            basis_refs=tuple(parsed["basis_refs"]),
            preconditions=tuple(parsed["preconditions"]),
            expected_result_ref=parsed["expected_result_ref"],
            rollback_policy_ref=parsed["rollback_policy_ref"],
            verification_policy_ref=parsed["verification_policy_ref"],
            provenance_ref=parsed["provenance_ref"],
        )
        _verify_digest("ActionProposal", result.proposal_digest, parsed["proposal_digest"])
        return result


@dataclass(frozen=True)
class ActionAdmission:
    action_id: str
    proposal_digest: str
    decision: AdmissionDecision
    effective_effects: EffectSet
    capability_refs: tuple[CapabilityRef, ...]
    authorization: AuthorizationReference
    budget_digest: str
    budget_revision: int
    world_basis_digest: str
    policy_snapshot_digest: str
    admission_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_id", require_non_empty("action_id", self.action_id))
        object.__setattr__(self, "proposal_digest", require_sha256("proposal_digest", self.proposal_digest))
        if not isinstance(self.decision, AdmissionDecision):
            raise ValueError("decision must be an AdmissionDecision")
        if not isinstance(self.effective_effects, EffectSet):
            raise ValueError("effective_effects must be an EffectSet")
        capabilities = _canonical_records(
            "capability_refs", self.capability_refs, CapabilityRef, "capability_digest"
        )
        if self.decision in {
            AdmissionDecision.ALLOW,
            AdmissionDecision.ALLOW_WITH_VERIFY,
        } and not capabilities:
            raise ValueError("allow admission requires at least one capability")
        object.__setattr__(self, "capability_refs", capabilities)
        if not isinstance(self.authorization, AuthorizationReference):
            raise ValueError("authorization must be an AuthorizationReference")
        object.__setattr__(self, "budget_digest", require_sha256("budget_digest", self.budget_digest))
        object.__setattr__(
            self,
            "budget_revision",
            require_positive_int("budget_revision", self.budget_revision),
        )
        object.__setattr__(
            self,
            "world_basis_digest",
            require_sha256("world_basis_digest", self.world_basis_digest),
        )
        object.__setattr__(
            self,
            "policy_snapshot_digest",
            require_sha256("policy_snapshot_digest", self.policy_snapshot_digest),
        )
        object.__setattr__(
            self,
            "admission_digest",
            canonical_record_digest("macr.action.admission.v1", self._identity_dict()),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "proposal_digest": self.proposal_digest,
            "decision": self.decision.value,
            "effective_effect_digest": self.effective_effects.effect_digest,
            "capability_digests": [item.capability_digest for item in self.capability_refs],
            "authorization": _authorization_dict(self.authorization),
            "budget_digest": self.budget_digest,
            "budget_revision": self.budget_revision,
            "world_basis_digest": self.world_basis_digest,
            "policy_snapshot_digest": self.policy_snapshot_digest,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "proposal_digest": self.proposal_digest,
            "decision": self.decision.value,
            "effective_effects": self.effective_effects.to_public_dict(),
            "capability_refs": [item.to_public_dict() for item in self.capability_refs],
            "authorization": _authorization_dict(self.authorization),
            "budget_digest": self.budget_digest,
            "budget_revision": self.budget_revision,
            "world_basis_digest": self.world_basis_digest,
            "policy_snapshot_digest": self.policy_snapshot_digest,
            "admission_digest": self.admission_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ActionAdmission":
        required = frozenset(
            {
                "action_id", "proposal_digest", "decision", "effective_effects",
                "capability_refs", "authorization", "budget_digest", "budget_revision",
                "world_basis_digest", "policy_snapshot_digest", "admission_digest",
            }
        )
        parsed = require_closed_mapping("ActionAdmission", data, required=required, optional=frozenset())
        result = cls(
            action_id=parsed["action_id"],
            proposal_digest=parsed["proposal_digest"],
            decision=AdmissionDecision(parsed["decision"]),
            effective_effects=EffectSet.from_dict(parsed["effective_effects"]),
            capability_refs=tuple(CapabilityRef.from_dict(item) for item in parsed["capability_refs"]),
            authorization=_authorization_from_dict(parsed["authorization"]),
            budget_digest=parsed["budget_digest"],
            budget_revision=parsed["budget_revision"],
            world_basis_digest=parsed["world_basis_digest"],
            policy_snapshot_digest=parsed["policy_snapshot_digest"],
        )
        _verify_digest("ActionAdmission", result.admission_digest, parsed["admission_digest"])
        return result


@dataclass(frozen=True)
class CommandIntent:
    command_intent_id: str
    action_ref: str
    operation: str
    target_ref: str
    parameter_ref: str
    effective_effects: EffectSet
    admission_ref: str
    idempotency_ref: str
    verification_policy_ref: str
    command_digest: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "command_intent_id", "action_ref", "operation", "target_ref",
            "parameter_ref", "admission_ref", "idempotency_ref", "verification_policy_ref",
        ):
            object.__setattr__(self, name, require_non_empty(name, getattr(self, name)))
        if not isinstance(self.effective_effects, EffectSet):
            raise ValueError("effective_effects must be an EffectSet")
        object.__setattr__(
            self,
            "command_digest",
            canonical_record_digest(
                "macr.action.command-intent.v1",
                {
                    "command_intent_id": self.command_intent_id,
                    "action_ref": self.action_ref,
                    "operation": self.operation,
                    "target_ref": self.target_ref,
                    "parameter_ref": self.parameter_ref,
                    "effective_effect_digest": self.effective_effects.effect_digest,
                    "admission_ref": self.admission_ref,
                    "idempotency_ref": self.idempotency_ref,
                    "verification_policy_ref": self.verification_policy_ref,
                },
            ),
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "command_intent_id": self.command_intent_id,
            "action_ref": self.action_ref,
            "operation": self.operation,
            "target_ref": self.target_ref,
            "parameter_ref": self.parameter_ref,
            "effective_effects": self.effective_effects.to_public_dict(),
            "admission_ref": self.admission_ref,
            "idempotency_ref": self.idempotency_ref,
            "verification_policy_ref": self.verification_policy_ref,
            "command_digest": self.command_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CommandIntent":
        required = frozenset(
            {
                "command_intent_id", "action_ref", "operation", "target_ref",
                "parameter_ref", "effective_effects", "admission_ref", "idempotency_ref",
                "verification_policy_ref", "command_digest",
            }
        )
        parsed = require_closed_mapping("CommandIntent", data, required=required, optional=frozenset())
        result = cls(
            command_intent_id=parsed["command_intent_id"],
            action_ref=parsed["action_ref"],
            operation=parsed["operation"],
            target_ref=parsed["target_ref"],
            parameter_ref=parsed["parameter_ref"],
            effective_effects=EffectSet.from_dict(parsed["effective_effects"]),
            admission_ref=parsed["admission_ref"],
            idempotency_ref=parsed["idempotency_ref"],
            verification_policy_ref=parsed["verification_policy_ref"],
        )
        _verify_digest("CommandIntent", result.command_digest, parsed["command_digest"])
        return result


@dataclass(frozen=True)
class ActionAttempt:
    attempt_id: str
    action_ref: str
    command_ref: str
    provider_ref: str
    state: ActionAttemptState
    started_at: str
    finished_at: str | None
    provider_operation_id: str | None
    attempt_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "attempt_id", require_uuid4("attempt_id", self.attempt_id))
        for name in ("action_ref", "command_ref", "provider_ref"):
            object.__setattr__(self, name, require_non_empty(name, getattr(self, name)))
        if not isinstance(self.state, ActionAttemptState):
            raise ValueError("state must be an ActionAttemptState")
        object.__setattr__(self, "started_at", normalize_timestamp("started_at", self.started_at))
        finished = self.finished_at
        if finished is not None:
            finished = normalize_timestamp("finished_at", finished)
        terminal = self.state in {ActionAttemptState.RECEIPT_CAPTURED, ActionAttemptState.FAILED}
        if terminal != (finished is not None):
            raise ValueError("terminal attempt state and finished_at must agree")
        object.__setattr__(self, "finished_at", finished)
        object.__setattr__(
            self,
            "provider_operation_id",
            require_optional_non_empty("provider_operation_id", self.provider_operation_id),
        )
        object.__setattr__(
            self,
            "attempt_digest",
            canonical_record_digest("macr.action.attempt.v1", self._identity_dict()),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "attempt_id": self.attempt_id,
            "action_ref": self.action_ref,
            "command_ref": self.command_ref,
            "provider_ref": self.provider_ref,
            "state": self.state.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "provider_operation_id": self.provider_operation_id,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "attempt_digest": self.attempt_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ActionAttempt":
        required = frozenset(
            {"attempt_id", "action_ref", "command_ref", "provider_ref", "state", "started_at", "finished_at", "provider_operation_id", "attempt_digest"}
        )
        parsed = require_closed_mapping("ActionAttempt", data, required=required, optional=frozenset())
        result = cls(
            attempt_id=parsed["attempt_id"], action_ref=parsed["action_ref"],
            command_ref=parsed["command_ref"], provider_ref=parsed["provider_ref"],
            state=ActionAttemptState(parsed["state"]), started_at=parsed["started_at"],
            finished_at=parsed["finished_at"], provider_operation_id=parsed["provider_operation_id"],
        )
        _verify_digest("ActionAttempt", result.attempt_digest, parsed["attempt_digest"])
        return result


@dataclass(frozen=True)
class ActuationReceipt:
    receipt_id: str
    action_ref: str
    command_ref: str
    attempt_id: str
    provider: str
    provider_operation_id: str | None
    status: ReceiptStatus
    reported_result_ref: str | None
    observed_cost_ref: str | None
    duration_ms: int | None
    evidence_refs: tuple[str, ...]
    receipt_digest: str = field(init=False)

    def __post_init__(self) -> None:
        for name in ("receipt_id", "action_ref", "command_ref", "provider"):
            object.__setattr__(self, name, require_non_empty(name, getattr(self, name)))
        object.__setattr__(self, "attempt_id", require_uuid4("attempt_id", self.attempt_id))
        for name in ("provider_operation_id", "reported_result_ref", "observed_cost_ref"):
            object.__setattr__(self, name, require_optional_non_empty(name, getattr(self, name)))
        if not isinstance(self.status, ReceiptStatus):
            raise ValueError("status must be a ReceiptStatus")
        if self.duration_ms is not None:
            object.__setattr__(
                self,
                "duration_ms",
                require_non_negative_int("duration_ms", self.duration_ms),
            )
        evidence = require_string_tuple("evidence_refs", self.evidence_refs)
        if not evidence:
            raise ValueError("evidence_refs must not be empty")
        object.__setattr__(self, "evidence_refs", evidence)
        object.__setattr__(
            self,
            "receipt_digest",
            canonical_record_digest("macr.action.receipt.v1", self._identity_dict()),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "receipt_id": self.receipt_id, "action_ref": self.action_ref,
            "command_ref": self.command_ref, "attempt_id": self.attempt_id,
            "provider": self.provider, "provider_operation_id": self.provider_operation_id,
            "status": self.status.value, "reported_result_ref": self.reported_result_ref,
            "observed_cost_ref": self.observed_cost_ref, "duration_ms": self.duration_ms,
            "evidence_refs": list(self.evidence_refs),
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "receipt_digest": self.receipt_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ActuationReceipt":
        required = frozenset(
            {"receipt_id", "action_ref", "command_ref", "attempt_id", "provider", "provider_operation_id", "status", "reported_result_ref", "observed_cost_ref", "duration_ms", "evidence_refs", "receipt_digest"}
        )
        parsed = require_closed_mapping("ActuationReceipt", data, required=required, optional=frozenset())
        result = cls(
            receipt_id=parsed["receipt_id"], action_ref=parsed["action_ref"],
            command_ref=parsed["command_ref"], attempt_id=parsed["attempt_id"],
            provider=parsed["provider"], provider_operation_id=parsed["provider_operation_id"],
            status=ReceiptStatus(parsed["status"]), reported_result_ref=parsed["reported_result_ref"],
            observed_cost_ref=parsed["observed_cost_ref"], duration_ms=parsed["duration_ms"],
            evidence_refs=tuple(parsed["evidence_refs"]),
        )
        _verify_digest("ActuationReceipt", result.receipt_digest, parsed["receipt_digest"])
        return result


@dataclass(frozen=True)
class ActionVerification:
    verification_id: str
    action_ref: str
    verification_kind: str
    basis_refs: tuple[str, ...]
    verdict: VerificationVerdict
    evidence_refs: tuple[str, ...]
    verifier_ref: str
    verification_digest: str = field(init=False)

    def __post_init__(self) -> None:
        for name in ("verification_id", "action_ref", "verification_kind", "verifier_ref"):
            object.__setattr__(self, name, require_non_empty(name, getattr(self, name)))
        basis = require_string_tuple("basis_refs", self.basis_refs)
        evidence = require_string_tuple("evidence_refs", self.evidence_refs)
        if not basis or not evidence:
            raise ValueError("basis_refs and evidence_refs must not be empty")
        object.__setattr__(self, "basis_refs", basis)
        object.__setattr__(self, "evidence_refs", evidence)
        if not isinstance(self.verdict, VerificationVerdict):
            raise ValueError("verdict must be a VerificationVerdict")
        object.__setattr__(
            self,
            "verification_digest",
            canonical_record_digest("macr.action.verification.v1", self._identity_dict()),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "verification_id": self.verification_id, "action_ref": self.action_ref,
            "verification_kind": self.verification_kind, "basis_refs": list(self.basis_refs),
            "verdict": self.verdict.value, "evidence_refs": list(self.evidence_refs),
            "verifier_ref": self.verifier_ref,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "verification_digest": self.verification_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ActionVerification":
        required = frozenset(
            {"verification_id", "action_ref", "verification_kind", "basis_refs", "verdict", "evidence_refs", "verifier_ref", "verification_digest"}
        )
        parsed = require_closed_mapping("ActionVerification", data, required=required, optional=frozenset())
        result = cls(
            verification_id=parsed["verification_id"], action_ref=parsed["action_ref"],
            verification_kind=parsed["verification_kind"], basis_refs=tuple(parsed["basis_refs"]),
            verdict=VerificationVerdict(parsed["verdict"]), evidence_refs=tuple(parsed["evidence_refs"]),
            verifier_ref=parsed["verifier_ref"],
        )
        _verify_digest("ActionVerification", result.verification_digest, parsed["verification_digest"])
        return result


@dataclass(frozen=True)
class ReconciliationRecord:
    reconciliation_id: str
    agent_run_id: str
    action_id: str
    classification: ReconciliationClassification
    evidence_refs: tuple[str, ...]
    resolved_by: str | None
    authority_ref: AuthorizationReference | None
    resolved_at: str | None
    resolution_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "reconciliation_id", require_non_empty("reconciliation_id", self.reconciliation_id))
        object.__setattr__(self, "agent_run_id", require_uuid4("agent_run_id", self.agent_run_id))
        object.__setattr__(self, "action_id", require_non_empty("action_id", self.action_id))
        if not isinstance(self.classification, ReconciliationClassification):
            raise ValueError("classification must be a ReconciliationClassification")
        evidence = require_string_tuple("evidence_refs", self.evidence_refs)
        if not evidence:
            raise ValueError("evidence_refs must not be empty")
        object.__setattr__(self, "evidence_refs", evidence)
        resolved_by = require_optional_non_empty("resolved_by", self.resolved_by)
        object.__setattr__(self, "resolved_by", resolved_by)
        if self.authority_ref is not None and not isinstance(self.authority_ref, AuthorizationReference):
            raise ValueError("authority_ref must be an AuthorizationReference or None")
        resolved_at = self.resolved_at
        if resolved_at is not None:
            resolved_at = normalize_timestamp("resolved_at", resolved_at)
        object.__setattr__(self, "resolved_at", resolved_at)
        resolution_fields = (resolved_by is not None, self.authority_ref is not None, resolved_at is not None)
        if self.classification is ReconciliationClassification.STATE_UNKNOWN:
            if any(resolution_fields):
                raise ValueError("STATE_UNKNOWN cannot carry resolution authority")
        elif not all(resolution_fields):
            raise ValueError("resolved reconciliation requires actor, authority, and time")
        object.__setattr__(
            self,
            "resolution_digest",
            canonical_record_digest("macr.action.reconciliation.v1", self._identity_dict()),
        )

    @property
    def is_resolved(self) -> bool:
        return self.classification is not ReconciliationClassification.STATE_UNKNOWN

    def _identity_dict(self) -> dict[str, object]:
        return {
            "reconciliation_id": self.reconciliation_id, "agent_run_id": self.agent_run_id,
            "action_id": self.action_id, "classification": self.classification.value,
            "evidence_refs": list(self.evidence_refs), "resolved_by": self.resolved_by,
            "authority_ref": None if self.authority_ref is None else _authorization_dict(self.authority_ref),
            "resolved_at": self.resolved_at,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "resolution_digest": self.resolution_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReconciliationRecord":
        required = frozenset(
            {"reconciliation_id", "agent_run_id", "action_id", "classification", "evidence_refs", "resolved_by", "authority_ref", "resolved_at", "resolution_digest"}
        )
        parsed = require_closed_mapping("ReconciliationRecord", data, required=required, optional=frozenset())
        authority = parsed["authority_ref"]
        result = cls(
            reconciliation_id=parsed["reconciliation_id"], agent_run_id=parsed["agent_run_id"],
            action_id=parsed["action_id"], classification=ReconciliationClassification(parsed["classification"]),
            evidence_refs=tuple(parsed["evidence_refs"]), resolved_by=parsed["resolved_by"],
            authority_ref=None if authority is None else _authorization_from_dict(authority),
            resolved_at=parsed["resolved_at"],
        )
        _verify_digest("ReconciliationRecord", result.resolution_digest, parsed["resolution_digest"])
        return result


def _authorization_dict(reference: AuthorizationReference) -> dict[str, object]:
    return {
        "source_kind": reference.source_kind,
        "source_id": reference.source_id,
        "digest": reference.digest,
        "revision": reference.revision,
        "epoch": reference.epoch,
        "scope": reference.scope,
    }


def _authorization_from_dict(data: Mapping[str, Any]) -> AuthorizationReference:
    parsed = require_closed_mapping(
        "AuthorizationReference",
        data,
        required=frozenset({"source_kind", "source_id", "digest", "revision", "epoch", "scope"}),
        optional=frozenset(),
    )
    return AuthorizationReference(**parsed)


def _canonical_records(
    name: str,
    values: Sequence[Any],
    expected_type: type,
    digest_field: str,
) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"{name} must be a sequence")
    normalized = tuple(values)
    if any(not isinstance(item, expected_type) for item in normalized):
        raise ValueError(f"{name} contains an invalid record")
    digests = [getattr(item, digest_field) for item in normalized]
    if len(set(digests)) != len(digests):
        raise ValueError(f"{name} must not contain duplicates")
    return tuple(sorted(normalized, key=lambda item: getattr(item, digest_field)))


def _verify_digest(name: str, actual: str, supplied: object) -> None:
    if actual != require_sha256(f"{name} digest", supplied):
        raise ValueError(f"{name} digest does not match")
