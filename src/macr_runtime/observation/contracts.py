from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .._v07_contracts import (
    canonical_record_digest,
    normalize_timestamp,
    require_closed_mapping,
    require_non_empty,
    require_non_negative_number,
    require_optional_non_empty,
    require_sha256,
    require_string_tuple,
    require_uuid4,
)


class FreshnessMode(str, Enum):
    IMMUTABLE = "immutable"
    SOURCE_REVISION = "source_revision"
    MAX_AGE = "max_age"
    EVENT_INVALIDATED = "event_invalidated"
    ALWAYS_RECHECK_BEFORE_MUTATION = "always_recheck_before_mutation"


class ObservationVerificationRequirement(str, Enum):
    VERIFIED = "verified"


@dataclass(frozen=True)
class ObservationScope:
    scope_ref: str
    resource_refs: tuple[str, ...]
    region_refs: tuple[str, ...]
    scope_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope_ref", require_non_empty("scope_ref", self.scope_ref))
        object.__setattr__(
            self,
            "resource_refs",
            require_string_tuple("resource_refs", self.resource_refs),
        )
        object.__setattr__(
            self,
            "region_refs",
            require_string_tuple("region_refs", self.region_refs),
        )
        if not self.resource_refs and not self.region_refs:
            raise ValueError("observation scope requires at least one resource or region")
        object.__setattr__(
            self,
            "scope_digest",
            canonical_record_digest(
                "macr.observation.scope.v1",
                {
                    "scope_ref": self.scope_ref,
                    "resource_refs": list(self.resource_refs),
                    "region_refs": list(self.region_refs),
                },
            ),
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "scope_ref": self.scope_ref,
            "resource_refs": list(self.resource_refs),
            "region_refs": list(self.region_refs),
            "scope_digest": self.scope_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ObservationScope":
        parsed = require_closed_mapping(
            "ObservationScope",
            data,
            required=frozenset(
                {"scope_ref", "resource_refs", "region_refs", "scope_digest"}
            ),
            optional=frozenset(),
        )
        result = cls(
            scope_ref=parsed["scope_ref"],
            resource_refs=tuple(parsed["resource_refs"]),
            region_refs=tuple(parsed["region_refs"]),
        )
        _verify_digest("ObservationScope", result.scope_digest, parsed["scope_digest"])
        return result


@dataclass(frozen=True)
class FreshnessPolicy:
    policy_id: str
    mode: FreshnessMode
    source_revision: str | None
    max_age_seconds: int | float | None
    invalidation_event_refs: tuple[str, ...]
    policy_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", require_non_empty("policy_id", self.policy_id))
        if not isinstance(self.mode, FreshnessMode):
            raise ValueError("mode must be a FreshnessMode")
        revision = require_optional_non_empty("source_revision", self.source_revision)
        object.__setattr__(self, "source_revision", revision)
        age = self.max_age_seconds
        if age is not None:
            age = require_non_negative_number("max_age_seconds", age)
            if age <= 0:
                raise ValueError("max_age_seconds must be positive")
        object.__setattr__(self, "max_age_seconds", age)
        events = require_string_tuple(
            "invalidation_event_refs",
            self.invalidation_event_refs,
        )
        object.__setattr__(self, "invalidation_event_refs", events)
        if self.mode is FreshnessMode.SOURCE_REVISION:
            if revision is None or age is not None or events:
                raise ValueError("source_revision mode requires only source_revision")
        elif self.mode is FreshnessMode.MAX_AGE:
            if age is None or revision is not None or events:
                raise ValueError("max_age mode requires only max_age_seconds")
        elif self.mode is FreshnessMode.EVENT_INVALIDATED:
            if not events or revision is not None or age is not None:
                raise ValueError("event_invalidated mode requires only event refs")
        elif revision is not None or age is not None or events:
            raise ValueError("freshness mode does not accept mode-specific fields")
        object.__setattr__(
            self,
            "policy_digest",
            canonical_record_digest(
                "macr.observation.freshness-policy.v1",
                {
                    "policy_id": self.policy_id,
                    "mode": self.mode.value,
                    "source_revision": self.source_revision,
                    "max_age_seconds": self.max_age_seconds,
                    "invalidation_event_refs": list(self.invalidation_event_refs),
                },
            ),
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "mode": self.mode.value,
            "source_revision": self.source_revision,
            "max_age_seconds": self.max_age_seconds,
            "invalidation_event_refs": list(self.invalidation_event_refs),
            "policy_digest": self.policy_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FreshnessPolicy":
        parsed = require_closed_mapping(
            "FreshnessPolicy",
            data,
            required=frozenset(
                {
                    "policy_id",
                    "mode",
                    "source_revision",
                    "max_age_seconds",
                    "invalidation_event_refs",
                    "policy_digest",
                }
            ),
            optional=frozenset(),
        )
        result = cls(
            policy_id=parsed["policy_id"],
            mode=FreshnessMode(parsed["mode"]),
            source_revision=parsed["source_revision"],
            max_age_seconds=parsed["max_age_seconds"],
            invalidation_event_refs=tuple(parsed["invalidation_event_refs"]),
        )
        _verify_digest("FreshnessPolicy", result.policy_digest, parsed["policy_digest"])
        return result


@dataclass(frozen=True)
class RawObservationRef:
    raw_ref: str
    source_ref: str
    captured_at: str
    raw_digest: str
    reference_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_ref", require_non_empty("raw_ref", self.raw_ref))
        object.__setattr__(self, "source_ref", require_non_empty("source_ref", self.source_ref))
        object.__setattr__(
            self,
            "captured_at",
            normalize_timestamp("captured_at", self.captured_at),
        )
        object.__setattr__(self, "raw_digest", require_sha256("raw_digest", self.raw_digest))
        object.__setattr__(
            self,
            "reference_digest",
            canonical_record_digest(
                "macr.observation.raw-ref.v1",
                {
                    "raw_ref": self.raw_ref,
                    "source_ref": self.source_ref,
                    "captured_at": self.captured_at,
                    "raw_digest": self.raw_digest,
                },
            ),
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "raw_ref": self.raw_ref,
            "source_ref": self.source_ref,
            "captured_at": self.captured_at,
            "raw_digest": self.raw_digest,
            "reference_digest": self.reference_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RawObservationRef":
        parsed = require_closed_mapping(
            "RawObservationRef",
            data,
            required=frozenset(
                {"raw_ref", "source_ref", "captured_at", "raw_digest", "reference_digest"}
            ),
            optional=frozenset(),
        )
        result = cls(
            raw_ref=parsed["raw_ref"],
            source_ref=parsed["source_ref"],
            captured_at=parsed["captured_at"],
            raw_digest=parsed["raw_digest"],
        )
        _verify_digest("RawObservationRef", result.reference_digest, parsed["reference_digest"])
        return result


@dataclass(frozen=True)
class ObservationIntent:
    observation_intent_id: str
    agent_run_id: str
    goal_ref: str
    plan_ref: str | None
    task_ref: str | None
    world_binding_ref: str
    observation_purpose: str
    requested_scope: ObservationScope
    preferred_representation: str
    freshness_policy: FreshnessPolicy
    verification_requirement: ObservationVerificationRequirement
    intent_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observation_intent_id",
            require_non_empty("observation_intent_id", self.observation_intent_id),
        )
        object.__setattr__(self, "agent_run_id", require_uuid4("agent_run_id", self.agent_run_id))
        object.__setattr__(self, "goal_ref", require_non_empty("goal_ref", self.goal_ref))
        object.__setattr__(self, "plan_ref", require_optional_non_empty("plan_ref", self.plan_ref))
        object.__setattr__(self, "task_ref", require_optional_non_empty("task_ref", self.task_ref))
        object.__setattr__(
            self,
            "world_binding_ref",
            require_non_empty("world_binding_ref", self.world_binding_ref),
        )
        object.__setattr__(
            self,
            "observation_purpose",
            require_non_empty("observation_purpose", self.observation_purpose, 2048),
        )
        if not isinstance(self.requested_scope, ObservationScope):
            raise ValueError("requested_scope must be an ObservationScope")
        object.__setattr__(
            self,
            "preferred_representation",
            require_non_empty("preferred_representation", self.preferred_representation),
        )
        if not isinstance(self.freshness_policy, FreshnessPolicy):
            raise ValueError("freshness_policy must be a FreshnessPolicy")
        if not isinstance(
            self.verification_requirement,
            ObservationVerificationRequirement,
        ):
            raise ValueError(
                "verification_requirement must be an ObservationVerificationRequirement"
            )
        object.__setattr__(
            self,
            "intent_digest",
            canonical_record_digest(
                "macr.observation.intent.v1",
                {
                    "observation_intent_id": self.observation_intent_id,
                    "agent_run_id": self.agent_run_id,
                    "goal_ref": self.goal_ref,
                    "plan_ref": self.plan_ref,
                    "task_ref": self.task_ref,
                    "world_binding_ref": self.world_binding_ref,
                    "observation_purpose": self.observation_purpose,
                    "scope_digest": self.requested_scope.scope_digest,
                    "preferred_representation": self.preferred_representation,
                    "freshness_policy_digest": self.freshness_policy.policy_digest,
                    "verification_requirement": self.verification_requirement.value,
                },
            ),
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "observation_intent_id": self.observation_intent_id,
            "agent_run_id": self.agent_run_id,
            "goal_ref": self.goal_ref,
            "plan_ref": self.plan_ref,
            "task_ref": self.task_ref,
            "world_binding_ref": self.world_binding_ref,
            "observation_purpose": self.observation_purpose,
            "requested_scope": self.requested_scope.to_public_dict(),
            "preferred_representation": self.preferred_representation,
            "freshness_policy": self.freshness_policy.to_public_dict(),
            "verification_requirement": self.verification_requirement.value,
            "intent_digest": self.intent_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ObservationIntent":
        parsed = require_closed_mapping(
            "ObservationIntent",
            data,
            required=frozenset(
                {
                    "observation_intent_id",
                    "agent_run_id",
                    "goal_ref",
                    "plan_ref",
                    "task_ref",
                    "world_binding_ref",
                    "observation_purpose",
                    "requested_scope",
                    "preferred_representation",
                    "freshness_policy",
                    "verification_requirement",
                    "intent_digest",
                }
            ),
            optional=frozenset(),
        )
        result = cls(
            observation_intent_id=parsed["observation_intent_id"],
            agent_run_id=parsed["agent_run_id"],
            goal_ref=parsed["goal_ref"],
            plan_ref=parsed["plan_ref"],
            task_ref=parsed["task_ref"],
            world_binding_ref=parsed["world_binding_ref"],
            observation_purpose=parsed["observation_purpose"],
            requested_scope=ObservationScope.from_dict(parsed["requested_scope"]),
            preferred_representation=parsed["preferred_representation"],
            freshness_policy=FreshnessPolicy.from_dict(parsed["freshness_policy"]),
            verification_requirement=ObservationVerificationRequirement(
                parsed["verification_requirement"]
            ),
        )
        _verify_digest("ObservationIntent", result.intent_digest, parsed["intent_digest"])
        return result


@dataclass(frozen=True)
class VerifiedObservationRef:
    observation_ref_id: str
    agent_run_id: str
    observation_intent_ref: str
    projection_request_ref: str
    projection_result_ref: str
    manifest_digest: str
    verification_digest: str
    visibility_commit_ref: str
    source_identity: str
    source_revision: str
    scope_digest: str
    projection_profile_digest: str
    visible_at: str
    observation_digest: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "observation_ref_id",
            "observation_intent_ref",
            "projection_request_ref",
            "projection_result_ref",
            "visibility_commit_ref",
            "source_identity",
            "source_revision",
        ):
            object.__setattr__(self, name, require_non_empty(name, getattr(self, name)))
        object.__setattr__(self, "agent_run_id", require_uuid4("agent_run_id", self.agent_run_id))
        for name in (
            "manifest_digest",
            "verification_digest",
            "scope_digest",
            "projection_profile_digest",
        ):
            object.__setattr__(self, name, require_sha256(name, getattr(self, name)))
        object.__setattr__(self, "visible_at", normalize_timestamp("visible_at", self.visible_at))
        object.__setattr__(
            self,
            "observation_digest",
            canonical_record_digest(
                "macr.observation.verified-ref.v1",
                {
                    "observation_ref_id": self.observation_ref_id,
                    "agent_run_id": self.agent_run_id,
                    "observation_intent_ref": self.observation_intent_ref,
                    "projection_request_ref": self.projection_request_ref,
                    "projection_result_ref": self.projection_result_ref,
                    "manifest_digest": self.manifest_digest,
                    "verification_digest": self.verification_digest,
                    "visibility_commit_ref": self.visibility_commit_ref,
                    "source_identity": self.source_identity,
                    "source_revision": self.source_revision,
                    "scope_digest": self.scope_digest,
                    "projection_profile_digest": self.projection_profile_digest,
                    "visible_at": self.visible_at,
                },
            ),
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "observation_ref_id": self.observation_ref_id,
            "agent_run_id": self.agent_run_id,
            "observation_intent_ref": self.observation_intent_ref,
            "projection_request_ref": self.projection_request_ref,
            "projection_result_ref": self.projection_result_ref,
            "manifest_digest": self.manifest_digest,
            "verification_digest": self.verification_digest,
            "visibility_commit_ref": self.visibility_commit_ref,
            "source_identity": self.source_identity,
            "source_revision": self.source_revision,
            "scope_digest": self.scope_digest,
            "projection_profile_digest": self.projection_profile_digest,
            "visible_at": self.visible_at,
            "observation_digest": self.observation_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VerifiedObservationRef":
        fields = frozenset(
            {
                "observation_ref_id",
                "agent_run_id",
                "observation_intent_ref",
                "projection_request_ref",
                "projection_result_ref",
                "manifest_digest",
                "verification_digest",
                "visibility_commit_ref",
                "source_identity",
                "source_revision",
                "scope_digest",
                "projection_profile_digest",
                "visible_at",
                "observation_digest",
            }
        )
        parsed = require_closed_mapping(
            "VerifiedObservationRef",
            data,
            required=fields,
            optional=frozenset(),
        )
        result = cls(**{name: parsed[name] for name in fields if name != "observation_digest"})
        _verify_digest(
            "VerifiedObservationRef",
            result.observation_digest,
            parsed["observation_digest"],
        )
        return result


@dataclass(frozen=True)
class ObservationBinding:
    observation_binding_id: str
    agent_run_id: str
    observation_ref_id: str
    observation_digest: str
    semantic_node_ref: str
    world_binding_ref: str
    basis_digest: str
    bound_at: str
    binding_digest: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "observation_binding_id",
            "observation_ref_id",
            "semantic_node_ref",
            "world_binding_ref",
        ):
            object.__setattr__(self, name, require_non_empty(name, getattr(self, name)))
        object.__setattr__(self, "agent_run_id", require_uuid4("agent_run_id", self.agent_run_id))
        object.__setattr__(
            self,
            "observation_digest",
            require_sha256("observation_digest", self.observation_digest),
        )
        object.__setattr__(self, "basis_digest", require_sha256("basis_digest", self.basis_digest))
        object.__setattr__(self, "bound_at", normalize_timestamp("bound_at", self.bound_at))
        object.__setattr__(
            self,
            "binding_digest",
            canonical_record_digest(
                "macr.observation.binding.v1",
                self._identity_dict(),
            ),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "observation_binding_id": self.observation_binding_id,
            "agent_run_id": self.agent_run_id,
            "observation_ref_id": self.observation_ref_id,
            "observation_digest": self.observation_digest,
            "semantic_node_ref": self.semantic_node_ref,
            "world_binding_ref": self.world_binding_ref,
            "basis_digest": self.basis_digest,
            "bound_at": self.bound_at,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "binding_digest": self.binding_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ObservationBinding":
        required = frozenset(
            {
                "observation_binding_id",
                "agent_run_id",
                "observation_ref_id",
                "observation_digest",
                "semantic_node_ref",
                "world_binding_ref",
                "basis_digest",
                "bound_at",
                "binding_digest",
            }
        )
        parsed = require_closed_mapping(
            "ObservationBinding",
            data,
            required=required,
            optional=frozenset(),
        )
        result = cls(**{name: parsed[name] for name in required if name != "binding_digest"})
        _verify_digest("ObservationBinding", result.binding_digest, parsed["binding_digest"])
        return result


@dataclass(frozen=True)
class ReObservationRequest:
    reobservation_request_id: str
    agent_run_id: str
    prior_observation_ref: str
    action_ref: str | None
    requested_scope: ObservationScope
    freshness_policy: FreshnessPolicy
    reason: str
    request_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reobservation_request_id",
            require_non_empty("reobservation_request_id", self.reobservation_request_id),
        )
        object.__setattr__(self, "agent_run_id", require_uuid4("agent_run_id", self.agent_run_id))
        object.__setattr__(
            self,
            "prior_observation_ref",
            require_non_empty("prior_observation_ref", self.prior_observation_ref),
        )
        object.__setattr__(self, "action_ref", require_optional_non_empty("action_ref", self.action_ref))
        if not isinstance(self.requested_scope, ObservationScope):
            raise ValueError("requested_scope must be an ObservationScope")
        if not isinstance(self.freshness_policy, FreshnessPolicy):
            raise ValueError("freshness_policy must be a FreshnessPolicy")
        object.__setattr__(self, "reason", require_non_empty("reason", self.reason, 2048))
        object.__setattr__(
            self,
            "request_digest",
            canonical_record_digest(
                "macr.observation.reobservation-request.v1",
                {
                    "reobservation_request_id": self.reobservation_request_id,
                    "agent_run_id": self.agent_run_id,
                    "prior_observation_ref": self.prior_observation_ref,
                    "action_ref": self.action_ref,
                    "scope_digest": self.requested_scope.scope_digest,
                    "freshness_policy_digest": self.freshness_policy.policy_digest,
                    "reason": self.reason,
                },
            ),
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "reobservation_request_id": self.reobservation_request_id,
            "agent_run_id": self.agent_run_id,
            "prior_observation_ref": self.prior_observation_ref,
            "action_ref": self.action_ref,
            "requested_scope": self.requested_scope.to_public_dict(),
            "freshness_policy": self.freshness_policy.to_public_dict(),
            "reason": self.reason,
            "request_digest": self.request_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReObservationRequest":
        parsed = require_closed_mapping(
            "ReObservationRequest",
            data,
            required=frozenset(
                {
                    "reobservation_request_id",
                    "agent_run_id",
                    "prior_observation_ref",
                    "action_ref",
                    "requested_scope",
                    "freshness_policy",
                    "reason",
                    "request_digest",
                }
            ),
            optional=frozenset(),
        )
        result = cls(
            reobservation_request_id=parsed["reobservation_request_id"],
            agent_run_id=parsed["agent_run_id"],
            prior_observation_ref=parsed["prior_observation_ref"],
            action_ref=parsed["action_ref"],
            requested_scope=ObservationScope.from_dict(parsed["requested_scope"]),
            freshness_policy=FreshnessPolicy.from_dict(parsed["freshness_policy"]),
            reason=parsed["reason"],
        )
        _verify_digest("ReObservationRequest", result.request_digest, parsed["request_digest"])
        return result


def _verify_digest(name: str, actual: str, supplied: object) -> None:
    if actual != require_sha256(f"{name} digest", supplied):
        raise ValueError(f"{name} digest does not match")
