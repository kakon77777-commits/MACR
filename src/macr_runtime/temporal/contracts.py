from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from .._v07_contracts import (
    canonical_record_digest,
    freeze_json_value,
    normalize_timestamp,
    public_json_value,
    require_closed_mapping,
    require_json_object,
    require_non_empty,
    require_non_negative_int,
    require_optional_non_empty,
    require_positive_int,
    require_sha256,
    require_string_tuple,
    require_uuid4,
)


class WakeKind(str, Enum):
    AT_TIME = "at_time"
    AFTER_DURATION = "after_duration"
    EXTERNAL_EVENT = "external_event"
    DOMAIN_LOGICAL_TIME = "domain_logical_time"
    WORLD_CONDITION = "world_condition"
    HUMAN_RESPONSE = "human_response"
    DEPENDENCY_COMPLETED = "dependency_completed"
    PROVIDER_COMPLETED = "provider_completed"
    BUDGET_AVAILABLE = "budget_available"
    MANUAL_WAKE = "manual_wake"


class DependencyState(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class AgentCheckpoint:
    checkpoint_id: str
    agent_run_id: str
    agent_run_epoch: int
    state_revision: int
    goal_ref: str
    goal_digest: str
    authority_ref: str
    authority_digest: str
    authority_revision: int
    authority_epoch: int
    budget_ref: str
    budget_digest: str
    budget_revision: int
    semantic_state_ref: str
    semantic_state_digest: str
    semantic_state_revision: int
    active_plan_ref: str | None
    active_plan_digest: str | None
    active_plan_revision: int | None
    world_basis_refs: tuple[str, ...]
    memory_binding_digests: tuple[str, ...]
    pending_action_refs: tuple[str, ...]
    reconciliation_refs: tuple[str, ...]
    verification_state_ref: str
    wake_condition_ref: str | None
    parent_checkpoint_ref: str | None
    created_at: str
    checkpoint_digest: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "checkpoint_id", "goal_ref", "authority_ref", "budget_ref",
            "semantic_state_ref", "verification_state_ref",
        ):
            object.__setattr__(self, name, require_non_empty(name, getattr(self, name)))
        object.__setattr__(self, "agent_run_id", require_uuid4("agent_run_id", self.agent_run_id))
        object.__setattr__(
            self,
            "agent_run_epoch",
            require_non_negative_int("agent_run_epoch", self.agent_run_epoch),
        )
        object.__setattr__(
            self,
            "state_revision",
            require_positive_int("state_revision", self.state_revision),
        )
        for name in ("goal_digest", "authority_digest", "budget_digest", "semantic_state_digest"):
            object.__setattr__(self, name, require_sha256(name, getattr(self, name)))
        object.__setattr__(
            self,
            "authority_revision",
            require_positive_int("authority_revision", self.authority_revision),
        )
        object.__setattr__(
            self,
            "authority_epoch",
            require_non_negative_int("authority_epoch", self.authority_epoch),
        )
        object.__setattr__(
            self,
            "budget_revision",
            require_positive_int("budget_revision", self.budget_revision),
        )
        object.__setattr__(
            self,
            "semantic_state_revision",
            require_positive_int("semantic_state_revision", self.semantic_state_revision),
        )
        plan_ref = require_optional_non_empty("active_plan_ref", self.active_plan_ref)
        plan_digest = self.active_plan_digest
        if plan_digest is not None:
            plan_digest = require_sha256("active_plan_digest", plan_digest)
        plan_revision = self.active_plan_revision
        if plan_revision is not None:
            plan_revision = require_positive_int("active_plan_revision", plan_revision)
        plan_present = (plan_ref is not None, plan_digest is not None, plan_revision is not None)
        if any(plan_present) and not all(plan_present):
            raise ValueError("active plan fields must be all present or all absent")
        object.__setattr__(self, "active_plan_ref", plan_ref)
        object.__setattr__(self, "active_plan_digest", plan_digest)
        object.__setattr__(self, "active_plan_revision", plan_revision)
        for name in ("world_basis_refs", "pending_action_refs", "reconciliation_refs"):
            object.__setattr__(
                self,
                name,
                require_string_tuple(name, getattr(self, name)),
            )
        object.__setattr__(
            self,
            "memory_binding_digests",
            _digest_tuple("memory_binding_digests", self.memory_binding_digests),
        )
        object.__setattr__(
            self,
            "wake_condition_ref",
            require_optional_non_empty("wake_condition_ref", self.wake_condition_ref),
        )
        object.__setattr__(
            self,
            "parent_checkpoint_ref",
            require_optional_non_empty("parent_checkpoint_ref", self.parent_checkpoint_ref),
        )
        object.__setattr__(self, "created_at", normalize_timestamp("created_at", self.created_at))
        object.__setattr__(
            self,
            "checkpoint_digest",
            canonical_record_digest("macr.temporal.checkpoint.v1", self._identity_dict()),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "agent_run_id": self.agent_run_id,
            "agent_run_epoch": self.agent_run_epoch,
            "state_revision": self.state_revision,
            "goal_ref": self.goal_ref,
            "goal_digest": self.goal_digest,
            "authority_ref": self.authority_ref,
            "authority_digest": self.authority_digest,
            "authority_revision": self.authority_revision,
            "authority_epoch": self.authority_epoch,
            "budget_ref": self.budget_ref,
            "budget_digest": self.budget_digest,
            "budget_revision": self.budget_revision,
            "semantic_state_ref": self.semantic_state_ref,
            "semantic_state_digest": self.semantic_state_digest,
            "semantic_state_revision": self.semantic_state_revision,
            "active_plan_ref": self.active_plan_ref,
            "active_plan_digest": self.active_plan_digest,
            "active_plan_revision": self.active_plan_revision,
            "world_basis_refs": list(self.world_basis_refs),
            "memory_binding_digests": list(self.memory_binding_digests),
            "pending_action_refs": list(self.pending_action_refs),
            "reconciliation_refs": list(self.reconciliation_refs),
            "verification_state_ref": self.verification_state_ref,
            "wake_condition_ref": self.wake_condition_ref,
            "parent_checkpoint_ref": self.parent_checkpoint_ref,
            "created_at": self.created_at,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "checkpoint_digest": self.checkpoint_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentCheckpoint":
        required = frozenset(
            {
                "checkpoint_id", "agent_run_id", "agent_run_epoch", "state_revision",
                "goal_ref", "goal_digest", "authority_ref", "authority_digest",
                "authority_revision", "authority_epoch", "budget_ref", "budget_digest",
                "budget_revision", "semantic_state_ref", "semantic_state_digest",
                "semantic_state_revision", "active_plan_ref", "active_plan_digest",
                "active_plan_revision", "world_basis_refs", "memory_binding_digests",
                "pending_action_refs", "reconciliation_refs", "verification_state_ref",
                "wake_condition_ref", "parent_checkpoint_ref", "created_at",
                "checkpoint_digest",
            }
        )
        parsed = require_closed_mapping("AgentCheckpoint", data, required=required, optional=frozenset())
        result = cls(**{name: parsed[name] for name in required if name != "checkpoint_digest"})
        _verify_digest("AgentCheckpoint", result.checkpoint_digest, parsed["checkpoint_digest"])
        return result


@dataclass(frozen=True)
class SuspendRecord:
    suspend_record_id: str
    agent_run_id: str
    checkpoint_ref: str
    checkpoint_digest: str
    wake_condition_ref: str | None
    reason: str
    suspended_at: str
    suspend_digest: str = field(init=False)

    def __post_init__(self) -> None:
        for name in ("suspend_record_id", "checkpoint_ref", "reason"):
            object.__setattr__(self, name, require_non_empty(name, getattr(self, name), 2048))
        object.__setattr__(self, "agent_run_id", require_uuid4("agent_run_id", self.agent_run_id))
        object.__setattr__(
            self,
            "checkpoint_digest",
            require_sha256("checkpoint_digest", self.checkpoint_digest),
        )
        object.__setattr__(
            self,
            "wake_condition_ref",
            require_optional_non_empty("wake_condition_ref", self.wake_condition_ref),
        )
        object.__setattr__(
            self,
            "suspended_at",
            normalize_timestamp("suspended_at", self.suspended_at),
        )
        object.__setattr__(
            self,
            "suspend_digest",
            canonical_record_digest("macr.temporal.suspend.v1", self._identity_dict()),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "suspend_record_id": self.suspend_record_id,
            "agent_run_id": self.agent_run_id,
            "checkpoint_ref": self.checkpoint_ref,
            "checkpoint_digest": self.checkpoint_digest,
            "wake_condition_ref": self.wake_condition_ref,
            "reason": self.reason,
            "suspended_at": self.suspended_at,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "suspend_digest": self.suspend_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SuspendRecord":
        required = frozenset(
            {"suspend_record_id", "agent_run_id", "checkpoint_ref", "checkpoint_digest", "wake_condition_ref", "reason", "suspended_at", "suspend_digest"}
        )
        parsed = require_closed_mapping("SuspendRecord", data, required=required, optional=frozenset())
        result = cls(**{name: parsed[name] for name in required if name != "suspend_digest"})
        _verify_digest("SuspendRecord", result.suspend_digest, parsed["suspend_digest"])
        return result


@dataclass(frozen=True)
class WakeCondition:
    wake_condition_id: str
    agent_run_id: str
    kind: WakeKind
    parameters: object
    not_before: str | None = None
    expires_at: str | None = None
    condition_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "wake_condition_id",
            require_non_empty("wake_condition_id", self.wake_condition_id),
        )
        object.__setattr__(self, "agent_run_id", require_uuid4("agent_run_id", self.agent_run_id))
        if not isinstance(self.kind, WakeKind):
            raise ValueError("kind must be a WakeKind")
        object.__setattr__(
            self,
            "parameters",
            freeze_json_value(
                "wake parameters",
                require_json_object("wake parameters", self.parameters),
            ),
        )
        not_before = self.not_before
        expires_at = self.expires_at
        if not_before is not None:
            not_before = normalize_timestamp("not_before", not_before)
        if expires_at is not None:
            expires_at = normalize_timestamp("expires_at", expires_at)
        if not_before is not None and expires_at is not None and not _before(not_before, expires_at):
            raise ValueError("expires_at must be later than not_before")
        object.__setattr__(self, "not_before", not_before)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(
            self,
            "condition_digest",
            canonical_record_digest("macr.temporal.wake-condition.v1", self._identity_dict()),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "wake_condition_id": self.wake_condition_id,
            "agent_run_id": self.agent_run_id,
            "kind": self.kind.value,
            "parameters": public_json_value(self.parameters),
            "not_before": self.not_before,
            "expires_at": self.expires_at,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "condition_digest": self.condition_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WakeCondition":
        required = frozenset(
            {"wake_condition_id", "agent_run_id", "kind", "parameters", "not_before", "expires_at", "condition_digest"}
        )
        parsed = require_closed_mapping("WakeCondition", data, required=required, optional=frozenset())
        result = cls(
            wake_condition_id=parsed["wake_condition_id"],
            agent_run_id=parsed["agent_run_id"],
            kind=WakeKind(parsed["kind"]),
            parameters=parsed["parameters"],
            not_before=parsed["not_before"],
            expires_at=parsed["expires_at"],
        )
        _verify_digest("WakeCondition", result.condition_digest, parsed["condition_digest"])
        return result


@dataclass(frozen=True)
class WakeEvent:
    wake_event_id: str
    agent_run_id: str
    wake_condition_ref: str
    source: str
    source_event_ref: str | None
    received_at: str
    source_event_time: str | None
    deduplication_key: str
    wake_event_digest: str = field(init=False)

    def __post_init__(self) -> None:
        for name in ("wake_event_id", "wake_condition_ref", "source", "deduplication_key"):
            object.__setattr__(self, name, require_non_empty(name, getattr(self, name)))
        object.__setattr__(self, "agent_run_id", require_uuid4("agent_run_id", self.agent_run_id))
        object.__setattr__(
            self,
            "source_event_ref",
            require_optional_non_empty("source_event_ref", self.source_event_ref),
        )
        object.__setattr__(self, "received_at", normalize_timestamp("received_at", self.received_at))
        event_time = self.source_event_time
        if event_time is not None:
            event_time = normalize_timestamp("source_event_time", event_time)
        object.__setattr__(self, "source_event_time", event_time)
        object.__setattr__(
            self,
            "wake_event_digest",
            canonical_record_digest("macr.temporal.wake-event.v1", self._identity_dict()),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "wake_event_id": self.wake_event_id,
            "agent_run_id": self.agent_run_id,
            "wake_condition_ref": self.wake_condition_ref,
            "source": self.source,
            "source_event_ref": self.source_event_ref,
            "received_at": self.received_at,
            "source_event_time": self.source_event_time,
            "deduplication_key": self.deduplication_key,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "wake_event_digest": self.wake_event_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WakeEvent":
        required = frozenset(
            {"wake_event_id", "agent_run_id", "wake_condition_ref", "source", "source_event_ref", "received_at", "source_event_time", "deduplication_key", "wake_event_digest"}
        )
        parsed = require_closed_mapping("WakeEvent", data, required=required, optional=frozenset())
        result = cls(**{name: parsed[name] for name in required if name != "wake_event_digest"})
        _verify_digest("WakeEvent", result.wake_event_digest, parsed["wake_event_digest"])
        return result


@dataclass(frozen=True)
class ResumeRecord:
    resume_record_id: str
    agent_run_id: str
    checkpoint_ref: str
    wake_event_ref: str
    previous_epoch: int
    new_epoch: int
    authority_binding_digest: str
    budget_binding_digest: str
    fresh_observation_refs: tuple[str, ...]
    invalidated_plan_refs: tuple[str, ...]
    resumed_at: str
    resume_digest: str = field(init=False)

    def __post_init__(self) -> None:
        for name in ("resume_record_id", "checkpoint_ref", "wake_event_ref"):
            object.__setattr__(self, name, require_non_empty(name, getattr(self, name)))
        object.__setattr__(self, "agent_run_id", require_uuid4("agent_run_id", self.agent_run_id))
        previous = require_non_negative_int("previous_epoch", self.previous_epoch)
        new = require_non_negative_int("new_epoch", self.new_epoch)
        if new <= previous:
            raise ValueError("new_epoch must be greater than previous_epoch")
        object.__setattr__(self, "previous_epoch", previous)
        object.__setattr__(self, "new_epoch", new)
        for name in ("authority_binding_digest", "budget_binding_digest"):
            object.__setattr__(self, name, require_sha256(name, getattr(self, name)))
        object.__setattr__(
            self,
            "fresh_observation_refs",
            require_string_tuple("fresh_observation_refs", self.fresh_observation_refs),
        )
        object.__setattr__(
            self,
            "invalidated_plan_refs",
            require_string_tuple("invalidated_plan_refs", self.invalidated_plan_refs),
        )
        object.__setattr__(self, "resumed_at", normalize_timestamp("resumed_at", self.resumed_at))
        object.__setattr__(
            self,
            "resume_digest",
            canonical_record_digest("macr.temporal.resume.v1", self._identity_dict()),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "resume_record_id": self.resume_record_id,
            "agent_run_id": self.agent_run_id,
            "checkpoint_ref": self.checkpoint_ref,
            "wake_event_ref": self.wake_event_ref,
            "previous_epoch": self.previous_epoch,
            "new_epoch": self.new_epoch,
            "authority_binding_digest": self.authority_binding_digest,
            "budget_binding_digest": self.budget_binding_digest,
            "fresh_observation_refs": list(self.fresh_observation_refs),
            "invalidated_plan_refs": list(self.invalidated_plan_refs),
            "resumed_at": self.resumed_at,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "resume_digest": self.resume_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ResumeRecord":
        required = frozenset(
            {"resume_record_id", "agent_run_id", "checkpoint_ref", "wake_event_ref", "previous_epoch", "new_epoch", "authority_binding_digest", "budget_binding_digest", "fresh_observation_refs", "invalidated_plan_refs", "resumed_at", "resume_digest"}
        )
        parsed = require_closed_mapping("ResumeRecord", data, required=required, optional=frozenset())
        result = cls(**{name: parsed[name] for name in required if name != "resume_digest"})
        _verify_digest("ResumeRecord", result.resume_digest, parsed["resume_digest"])
        return result


@dataclass(frozen=True)
class TemporalLease:
    lease_id: str
    agent_run_id: str
    owner_id: str
    epoch: int
    fencing_token: str
    acquired_at: str
    expires_at: str
    lease_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "lease_id", require_uuid4("lease_id", self.lease_id))
        object.__setattr__(self, "agent_run_id", require_uuid4("agent_run_id", self.agent_run_id))
        object.__setattr__(self, "owner_id", require_non_empty("owner_id", self.owner_id))
        object.__setattr__(self, "epoch", require_non_negative_int("epoch", self.epoch))
        object.__setattr__(
            self,
            "fencing_token",
            require_non_empty("fencing_token", self.fencing_token),
        )
        acquired = normalize_timestamp("acquired_at", self.acquired_at)
        expires = normalize_timestamp("expires_at", self.expires_at)
        if not _before(acquired, expires):
            raise ValueError("expires_at must be later than acquired_at")
        object.__setattr__(self, "acquired_at", acquired)
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(
            self,
            "lease_digest",
            canonical_record_digest("macr.temporal.lease.v1", self._identity_dict()),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "lease_id": self.lease_id,
            "agent_run_id": self.agent_run_id,
            "owner_id": self.owner_id,
            "epoch": self.epoch,
            "fencing_token": self.fencing_token,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "lease_digest": self.lease_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TemporalLease":
        required = frozenset(
            {"lease_id", "agent_run_id", "owner_id", "epoch", "fencing_token", "acquired_at", "expires_at", "lease_digest"}
        )
        parsed = require_closed_mapping("TemporalLease", data, required=required, optional=frozenset())
        result = cls(**{name: parsed[name] for name in required if name != "lease_digest"})
        _verify_digest("TemporalLease", result.lease_digest, parsed["lease_digest"])
        return result


@dataclass(frozen=True)
class PendingDependency:
    dependency_id: str
    agent_run_id: str
    dependency_kind: str
    target_ref: str
    state: DependencyState
    completion_ref: str | None
    created_at: str
    updated_at: str
    dependency_digest: str = field(init=False)

    def __post_init__(self) -> None:
        for name in ("dependency_id", "dependency_kind", "target_ref"):
            object.__setattr__(self, name, require_non_empty(name, getattr(self, name)))
        object.__setattr__(self, "agent_run_id", require_uuid4("agent_run_id", self.agent_run_id))
        if not isinstance(self.state, DependencyState):
            raise ValueError("state must be a DependencyState")
        completion = require_optional_non_empty("completion_ref", self.completion_ref)
        if (self.state is DependencyState.PENDING) != (completion is None):
            raise ValueError("dependency state and completion_ref must agree")
        object.__setattr__(self, "completion_ref", completion)
        created = normalize_timestamp("created_at", self.created_at)
        updated = normalize_timestamp("updated_at", self.updated_at)
        if _before(updated, created):
            raise ValueError("updated_at must not be earlier than created_at")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)
        object.__setattr__(
            self,
            "dependency_digest",
            canonical_record_digest("macr.temporal.pending-dependency.v1", self._identity_dict()),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "dependency_id": self.dependency_id,
            "agent_run_id": self.agent_run_id,
            "dependency_kind": self.dependency_kind,
            "target_ref": self.target_ref,
            "state": self.state.value,
            "completion_ref": self.completion_ref,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "dependency_digest": self.dependency_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PendingDependency":
        required = frozenset(
            {"dependency_id", "agent_run_id", "dependency_kind", "target_ref", "state", "completion_ref", "created_at", "updated_at", "dependency_digest"}
        )
        parsed = require_closed_mapping("PendingDependency", data, required=required, optional=frozenset())
        result = cls(
            dependency_id=parsed["dependency_id"],
            agent_run_id=parsed["agent_run_id"],
            dependency_kind=parsed["dependency_kind"],
            target_ref=parsed["target_ref"],
            state=DependencyState(parsed["state"]),
            completion_ref=parsed["completion_ref"],
            created_at=parsed["created_at"],
            updated_at=parsed["updated_at"],
        )
        _verify_digest("PendingDependency", result.dependency_digest, parsed["dependency_digest"])
        return result


def _digest_tuple(name: str, values: object) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, (tuple, list)):
        raise ValueError(f"{name} must be an array")
    normalized = tuple(require_sha256(f"{name} item", item) for item in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must not contain duplicates")
    return tuple(sorted(normalized))


def _before(left: str, right: str) -> bool:
    return datetime.fromisoformat(left) < datetime.fromisoformat(right)


def _verify_digest(name: str, actual: str, supplied: object) -> None:
    if actual != require_sha256(f"{name} digest", supplied):
        raise ValueError(f"{name} digest does not match")
