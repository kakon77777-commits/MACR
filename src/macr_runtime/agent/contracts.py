from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Mapping, Sequence

from .._v07_contracts import (
    canonical_record_digest,
    normalize_timestamp,
    require_closed_mapping,
    require_non_empty,
    require_non_negative_int,
    require_optional_non_empty,
    require_positive_int,
    require_sha256,
    require_uuid4,
)
from ..execution import AuthorizationReference, DispatchOrigin


AGENT_RUN_SCHEMA_VERSION = "macr-agent-run/v1"


class AgentRunState(str, Enum):
    CREATED = "created"
    ADMITTED = "admitted"
    ACTIVE = "active"
    WAITING = "waiting"
    SUSPENDED = "suspended"
    WAKING = "waking"
    BLOCKED = "blocked"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATES = frozenset(
    {
        AgentRunState.COMPLETED,
        AgentRunState.FAILED,
        AgentRunState.CANCELLED,
    }
)


def is_terminal_agent_run_state(state: AgentRunState) -> bool:
    if not isinstance(state, AgentRunState):
        raise ValueError("state must be an AgentRunState")
    return state in _TERMINAL_STATES


@dataclass(frozen=True)
class _VersionedBinding:
    ref: str
    digest: str
    revision: int
    binding_digest: str = field(init=False)

    _NAMESPACE: ClassVar[str] = "macr.agent.versioned-binding.v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref", require_non_empty("binding ref", self.ref))
        object.__setattr__(
            self,
            "digest",
            require_sha256("binding digest source", self.digest),
        )
        object.__setattr__(
            self,
            "revision",
            require_positive_int("binding revision", self.revision),
        )
        object.__setattr__(
            self,
            "binding_digest",
            canonical_record_digest(self._NAMESPACE, self._identity_dict()),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "ref": self.ref,
            "digest": self.digest,
            "revision": self.revision,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "binding_digest": self.binding_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "_VersionedBinding":
        parsed = require_closed_mapping(
            cls.__name__,
            data,
            required=frozenset({"ref", "digest", "revision", "binding_digest"}),
            optional=frozenset(),
        )
        result = cls(
            ref=parsed["ref"],
            digest=parsed["digest"],
            revision=parsed["revision"],
        )
        if result.binding_digest != require_sha256(
            f"{cls.__name__} binding_digest",
            parsed["binding_digest"],
        ):
            raise ValueError(f"{cls.__name__} binding_digest does not match")
        return result


@dataclass(frozen=True)
class GoalBinding(_VersionedBinding):
    _NAMESPACE: ClassVar[str] = "macr.agent.goal-binding.v1"


@dataclass(frozen=True)
class BudgetBinding(_VersionedBinding):
    _NAMESPACE: ClassVar[str] = "macr.agent.budget-binding.v1"


@dataclass(frozen=True)
class SemanticStateBinding(_VersionedBinding):
    _NAMESPACE: ClassVar[str] = "macr.agent.semantic-state-binding.v1"


@dataclass(frozen=True)
class PlanBinding(_VersionedBinding):
    _NAMESPACE: ClassVar[str] = "macr.agent.plan-binding.v1"


@dataclass(frozen=True)
class WorldBindingRef(_VersionedBinding):
    _NAMESPACE: ClassVar[str] = "macr.agent.world-binding.v1"


@dataclass(frozen=True)
class AuthorityBinding:
    reference: AuthorizationReference
    binding_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.reference, AuthorizationReference):
            raise ValueError("authority reference must be an AuthorizationReference")
        object.__setattr__(
            self,
            "binding_digest",
            canonical_record_digest(
                "macr.agent.authority-binding.v1",
                self._reference_dict(),
            ),
        )

    def _reference_dict(self) -> dict[str, object]:
        return {
            "source_kind": self.reference.source_kind,
            "source_id": self.reference.source_id,
            "digest": self.reference.digest,
            "revision": self.reference.revision,
            "epoch": self.reference.epoch,
            "scope": self.reference.scope,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._reference_dict(), "binding_digest": self.binding_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AuthorityBinding":
        parsed = require_closed_mapping(
            "AuthorityBinding",
            data,
            required=frozenset(
                {
                    "source_kind",
                    "source_id",
                    "digest",
                    "revision",
                    "epoch",
                    "scope",
                    "binding_digest",
                }
            ),
            optional=frozenset(),
        )
        result = cls(
            AuthorizationReference(
                source_kind=parsed["source_kind"],
                source_id=parsed["source_id"],
                digest=parsed["digest"],
                revision=parsed["revision"],
                epoch=parsed["epoch"],
                scope=parsed["scope"],
            )
        )
        if result.binding_digest != require_sha256(
            "AuthorityBinding binding_digest",
            parsed["binding_digest"],
        ):
            raise ValueError("AuthorityBinding binding_digest does not match")
        return result


@dataclass(frozen=True)
class MemoryBindingRef:
    memory_system_id: str
    profile_id: str
    subject_ref: str
    head_ref: str | None
    head_digest: str | None
    access_policy_ref: str
    projection_policy_ref: str
    binding_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "memory_system_id",
            require_non_empty("memory_system_id", self.memory_system_id),
        )
        object.__setattr__(
            self,
            "profile_id",
            require_non_empty("memory profile_id", self.profile_id),
        )
        object.__setattr__(
            self,
            "subject_ref",
            require_non_empty("memory subject_ref", self.subject_ref),
        )
        object.__setattr__(
            self,
            "head_ref",
            require_optional_non_empty("memory head_ref", self.head_ref),
        )
        if self.head_digest is not None:
            object.__setattr__(
                self,
                "head_digest",
                require_sha256("memory head_digest", self.head_digest),
            )
        if (self.head_ref is None) != (self.head_digest is None):
            raise ValueError("memory head_ref and head_digest must be both present or both absent")
        object.__setattr__(
            self,
            "access_policy_ref",
            require_non_empty("memory access_policy_ref", self.access_policy_ref),
        )
        object.__setattr__(
            self,
            "projection_policy_ref",
            require_non_empty(
                "memory projection_policy_ref",
                self.projection_policy_ref,
            ),
        )
        object.__setattr__(
            self,
            "binding_digest",
            canonical_record_digest(
                "macr.agent.memory-binding.v1",
                self._identity_dict(),
            ),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "memory_system_id": self.memory_system_id,
            "profile_id": self.profile_id,
            "subject_ref": self.subject_ref,
            "head_ref": self.head_ref,
            "head_digest": self.head_digest,
            "access_policy_ref": self.access_policy_ref,
            "projection_policy_ref": self.projection_policy_ref,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "binding_digest": self.binding_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryBindingRef":
        parsed = require_closed_mapping(
            "MemoryBindingRef",
            data,
            required=frozenset(
                {
                    "memory_system_id",
                    "profile_id",
                    "subject_ref",
                    "head_ref",
                    "head_digest",
                    "access_policy_ref",
                    "projection_policy_ref",
                    "binding_digest",
                }
            ),
            optional=frozenset(),
        )
        result = cls(
            memory_system_id=parsed["memory_system_id"],
            profile_id=parsed["profile_id"],
            subject_ref=parsed["subject_ref"],
            head_ref=parsed["head_ref"],
            head_digest=parsed["head_digest"],
            access_policy_ref=parsed["access_policy_ref"],
            projection_policy_ref=parsed["projection_policy_ref"],
        )
        if result.binding_digest != require_sha256(
            "MemoryBindingRef binding_digest",
            parsed["binding_digest"],
        ):
            raise ValueError("MemoryBindingRef binding_digest does not match")
        return result


@dataclass(frozen=True)
class AgentRunIdentity:
    agent_run_id: str
    subject_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "agent_run_id",
            require_uuid4("agent_run_id", self.agent_run_id),
        )
        object.__setattr__(
            self,
            "subject_digest",
            require_sha256("subject_digest", self.subject_digest),
        )

    def to_public_dict(self) -> dict[str, str]:
        return {
            "agent_run_id": self.agent_run_id,
            "subject_digest": self.subject_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentRunIdentity":
        parsed = require_closed_mapping(
            "AgentRunIdentity",
            data,
            required=frozenset({"agent_run_id", "subject_digest"}),
            optional=frozenset(),
        )
        return cls(
            agent_run_id=parsed["agent_run_id"],
            subject_digest=parsed["subject_digest"],
        )


def agent_run_subject_digest(
    *,
    agent_ref: str,
    origin: DispatchOrigin,
    goal: GoalBinding,
    authority: AuthorityBinding,
    budget: BudgetBinding,
    world_bindings: Sequence[WorldBindingRef],
    memory_bindings: Sequence[MemoryBindingRef],
) -> str:
    normalized_agent_ref = require_non_empty("agent_ref", agent_ref)
    if not isinstance(origin, DispatchOrigin):
        raise ValueError("origin must be a DispatchOrigin")
    if not isinstance(goal, GoalBinding):
        raise ValueError("goal must be a GoalBinding")
    if not isinstance(authority, AuthorityBinding):
        raise ValueError("authority must be an AuthorityBinding")
    if not isinstance(budget, BudgetBinding):
        raise ValueError("budget must be a BudgetBinding")
    worlds = _canonical_bindings("world_bindings", world_bindings, WorldBindingRef)
    memories = _canonical_bindings("memory_bindings", memory_bindings, MemoryBindingRef)
    return canonical_record_digest(
        "macr.agent.run-subject.v1",
        {
            "agent_ref": normalized_agent_ref,
            "origin": _origin_dict(origin),
            "goal_binding_digest": goal.binding_digest,
            "authority_binding_digest": authority.binding_digest,
            "budget_binding_digest": budget.binding_digest,
            "world_binding_digests": [item.binding_digest for item in worlds],
            "memory_binding_digests": [item.binding_digest for item in memories],
        },
    )


def _canonical_bindings(
    name: str,
    values: Sequence[Any],
    expected_type: type,
) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"{name} must be a sequence")
    normalized = tuple(values)
    if any(not isinstance(item, expected_type) for item in normalized):
        raise ValueError(f"{name} contains an invalid binding")
    digests = [item.binding_digest for item in normalized]
    if len(set(digests)) != len(digests):
        raise ValueError(f"{name} must not contain duplicate bindings")
    return tuple(sorted(normalized, key=lambda item: item.binding_digest))


def _origin_dict(origin: DispatchOrigin) -> dict[str, str]:
    return {
        "host": origin.host,
        "identifier_kind": origin.identifier_kind,
        "native_id": origin.native_id,
    }


def _origin_from_dict(data: Mapping[str, Any]) -> DispatchOrigin:
    parsed = require_closed_mapping(
        "AgentRun origin",
        data,
        required=frozenset({"host", "identifier_kind", "native_id"}),
        optional=frozenset(),
    )
    return DispatchOrigin(
        host=parsed["host"],
        identifier_kind=parsed["identifier_kind"],
        native_id=parsed["native_id"],
    )


@dataclass(frozen=True)
class AgentRunHeader:
    schema_version: str
    identity: AgentRunIdentity
    agent_ref: str
    origin: DispatchOrigin
    state: AgentRunState
    state_revision: int
    epoch: int
    goal: GoalBinding
    authority: AuthorityBinding
    budget: BudgetBinding
    semantic_state: SemanticStateBinding | None
    active_plan: PlanBinding | None
    world_bindings: tuple[WorldBindingRef, ...]
    memory_bindings: tuple[MemoryBindingRef, ...]
    parent_agent_run_id: str | None
    delegation_ref: str | None
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != AGENT_RUN_SCHEMA_VERSION:
            raise ValueError("schema_version must be macr-agent-run/v1")
        if not isinstance(self.identity, AgentRunIdentity):
            raise ValueError("identity must be an AgentRunIdentity")
        object.__setattr__(
            self,
            "agent_ref",
            require_non_empty("agent_ref", self.agent_ref),
        )
        if not isinstance(self.origin, DispatchOrigin):
            raise ValueError("origin must be a DispatchOrigin")
        if not isinstance(self.state, AgentRunState):
            raise ValueError("state must be an AgentRunState")
        object.__setattr__(
            self,
            "state_revision",
            require_positive_int("state_revision", self.state_revision),
        )
        object.__setattr__(
            self,
            "epoch",
            require_non_negative_int("epoch", self.epoch),
        )
        if not isinstance(self.goal, GoalBinding):
            raise ValueError("goal must be a GoalBinding")
        if not isinstance(self.authority, AuthorityBinding):
            raise ValueError("authority must be an AuthorityBinding")
        if not isinstance(self.budget, BudgetBinding):
            raise ValueError("budget must be a BudgetBinding")
        if self.semantic_state is not None and not isinstance(
            self.semantic_state,
            SemanticStateBinding,
        ):
            raise ValueError("semantic_state must be a SemanticStateBinding or None")
        if self.active_plan is not None and not isinstance(self.active_plan, PlanBinding):
            raise ValueError("active_plan must be a PlanBinding or None")
        worlds = _canonical_bindings(
            "world_bindings",
            self.world_bindings,
            WorldBindingRef,
        )
        memories = _canonical_bindings(
            "memory_bindings",
            self.memory_bindings,
            MemoryBindingRef,
        )
        object.__setattr__(self, "world_bindings", worlds)
        object.__setattr__(self, "memory_bindings", memories)
        parent = require_optional_non_empty(
            "parent_agent_run_id",
            self.parent_agent_run_id,
        )
        if parent is not None:
            parent = require_uuid4("parent_agent_run_id", parent)
        delegation = require_optional_non_empty("delegation_ref", self.delegation_ref)
        if (parent is None) != (delegation is None):
            raise ValueError("parent and delegation refs must be both present or both absent")
        object.__setattr__(self, "parent_agent_run_id", parent)
        object.__setattr__(self, "delegation_ref", delegation)
        object.__setattr__(
            self,
            "created_at",
            normalize_timestamp("created_at", self.created_at),
        )
        expected_subject = agent_run_subject_digest(
            agent_ref=self.agent_ref,
            origin=self.origin,
            goal=self.goal,
            authority=self.authority,
            budget=self.budget,
            world_bindings=self.world_bindings,
            memory_bindings=self.memory_bindings,
        )
        if self.identity.subject_digest != expected_subject:
            raise ValueError("identity subject_digest does not match AgentRun subject")

    def to_public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "identity": self.identity.to_public_dict(),
            "agent_ref": self.agent_ref,
            "origin": _origin_dict(self.origin),
            "state": self.state.value,
            "state_revision": self.state_revision,
            "epoch": self.epoch,
            "goal": self.goal.to_public_dict(),
            "authority": self.authority.to_public_dict(),
            "budget": self.budget.to_public_dict(),
            "semantic_state": (
                None if self.semantic_state is None else self.semantic_state.to_public_dict()
            ),
            "active_plan": (
                None if self.active_plan is None else self.active_plan.to_public_dict()
            ),
            "world_bindings": [item.to_public_dict() for item in self.world_bindings],
            "memory_bindings": [item.to_public_dict() for item in self.memory_bindings],
            "parent_agent_run_id": self.parent_agent_run_id,
            "delegation_ref": self.delegation_ref,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentRunHeader":
        required = frozenset(
            {
                "schema_version",
                "identity",
                "agent_ref",
                "origin",
                "state",
                "state_revision",
                "epoch",
                "goal",
                "authority",
                "budget",
                "semantic_state",
                "active_plan",
                "world_bindings",
                "memory_bindings",
                "parent_agent_run_id",
                "delegation_ref",
                "created_at",
            }
        )
        parsed = require_closed_mapping(
            "AgentRunHeader",
            data,
            required=required,
            optional=frozenset(),
        )
        worlds = parsed["world_bindings"]
        memories = parsed["memory_bindings"]
        if isinstance(worlds, (str, bytes)) or not isinstance(worlds, list):
            raise ValueError("world_bindings must be an array")
        if isinstance(memories, (str, bytes)) or not isinstance(memories, list):
            raise ValueError("memory_bindings must be an array")
        semantic = parsed["semantic_state"]
        plan = parsed["active_plan"]
        return cls(
            schema_version=parsed["schema_version"],
            identity=AgentRunIdentity.from_dict(parsed["identity"]),
            agent_ref=parsed["agent_ref"],
            origin=_origin_from_dict(parsed["origin"]),
            state=AgentRunState(parsed["state"]),
            state_revision=parsed["state_revision"],
            epoch=parsed["epoch"],
            goal=GoalBinding.from_dict(parsed["goal"]),
            authority=AuthorityBinding.from_dict(parsed["authority"]),
            budget=BudgetBinding.from_dict(parsed["budget"]),
            semantic_state=(
                None if semantic is None else SemanticStateBinding.from_dict(semantic)
            ),
            active_plan=None if plan is None else PlanBinding.from_dict(plan),
            world_bindings=tuple(WorldBindingRef.from_dict(item) for item in worlds),
            memory_bindings=tuple(MemoryBindingRef.from_dict(item) for item in memories),
            parent_agent_run_id=parsed["parent_agent_run_id"],
            delegation_ref=parsed["delegation_ref"],
            created_at=parsed["created_at"],
        )
