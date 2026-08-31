from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .._v07_contracts import (
    canonical_record_digest,
    freeze_json_value,
    normalize_timestamp,
    public_json_value,
    require_closed_mapping,
    require_json_object,
    require_non_empty,
    require_optional_non_empty,
    require_positive_int,
    require_sha256,
    require_string_tuple,
    require_uuid4,
)


class SemanticNodeType(str, Enum):
    GOAL = "goal"
    TRIGGER = "trigger"
    OBSERVATION = "observation"
    CLAIM = "claim"
    HYPOTHESIS = "hypothesis"
    PLAN = "plan"
    TASK = "task"
    ACTION_PROPOSAL = "action_proposal"
    CONSTRAINT = "constraint"
    DECISION = "decision"
    RECEIPT = "receipt"
    VERIFICATION = "verification"
    CHECKPOINT = "checkpoint"
    FAILURE = "failure"
    WAKE_CONDITION = "wake_condition"
    AMBIGUITY = "ambiguity"
    OBLIGATION = "obligation"


class SemanticLifecycleStatus(str, Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    STALE = "stale"
    SUPERSEDED = "superseded"
    COMPLETED = "completed"
    FAILED = "failed"


class ClaimStatus(str, Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    SUPPORTED = "supported"
    CONTESTED = "contested"
    VERIFIED = "verified"
    REFUTED = "refuted"
    STALE = "stale"
    SUPERSEDED = "superseded"
    UNRESOLVED = "unresolved"


class ResolutionStatus(str, Enum):
    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"


class SemanticRelationType(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DEPENDS_ON = "depends_on"
    DERIVED_FROM = "derived_from"
    OBSERVES = "observes"
    DESCRIBES = "describes"
    CONSTRAINS = "constrains"
    MOTIVATES = "motivates"
    TARGETS = "targets"
    AFFECTS = "affects"
    EXPECTS = "expects"
    PRODUCED = "produced"
    VERIFIES = "verifies"
    REFUTES = "refutes"
    SUPERSEDES = "supersedes"
    REVISES = "revises"
    BLOCKS = "blocks"
    RESOLVES = "resolves"
    CAUSES = "causes"
    PRECEDES = "precedes"
    FOLLOWS = "follows"
    WAITS_FOR = "waits_for"


class SemanticEventType(str, Enum):
    PROPOSAL = "proposal"
    STATUS_CHANGE = "status_change"
    CORRECTION = "correction"
    RESOLUTION = "resolution"
    PATCH_PROPOSAL = "patch_proposal"


class BindingKind(str, Enum):
    REFERENCE = "reference"
    PROJECTION = "projection"
    DERIVED = "derived"
    TRANSFORMATION = "transformation"


class ArtifactRole(str, Enum):
    CANONICAL_SOURCE = "canonical_source"
    CANONICAL_DERIVED = "canonical_derived"
    DERIVED_REBUILDABLE = "derived_rebuildable"
    PROJECTION = "projection"
    CACHE_INDEX = "cache_index"
    LEGACY_COMPATIBILITY = "legacy_compatibility"


SemanticStatus = SemanticLifecycleStatus | ClaimStatus | ResolutionStatus


@dataclass(frozen=True)
class SemanticProfileRef:
    system_id: str
    profile_id: str
    profile_version: str
    registry_ref: str | None
    registry_revision: int | None
    registry_digest: str | None
    decoder_contract_ref: str | None
    binding_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "system_id", require_non_empty("system_id", self.system_id))
        object.__setattr__(self, "profile_id", require_non_empty("profile_id", self.profile_id))
        object.__setattr__(
            self,
            "profile_version",
            require_non_empty("profile_version", self.profile_version),
        )
        object.__setattr__(
            self,
            "registry_ref",
            require_optional_non_empty("registry_ref", self.registry_ref),
        )
        if self.registry_revision is not None:
            object.__setattr__(
                self,
                "registry_revision",
                require_positive_int("registry_revision", self.registry_revision),
            )
        if self.registry_digest is not None:
            object.__setattr__(
                self,
                "registry_digest",
                require_sha256("registry_digest", self.registry_digest),
            )
        registry_present = (
            self.registry_ref is not None,
            self.registry_revision is not None,
            self.registry_digest is not None,
        )
        if any(registry_present) and not all(registry_present):
            raise ValueError("registry fields must be all present or all absent")
        object.__setattr__(
            self,
            "decoder_contract_ref",
            require_optional_non_empty(
                "decoder_contract_ref",
                self.decoder_contract_ref,
            ),
        )
        object.__setattr__(
            self,
            "binding_digest",
            canonical_record_digest(
                "macr.semantic.profile-ref.v1",
                self._identity_dict(),
            ),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "system_id": self.system_id,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "registry_ref": self.registry_ref,
            "registry_revision": self.registry_revision,
            "registry_digest": self.registry_digest,
            "decoder_contract_ref": self.decoder_contract_ref,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "binding_digest": self.binding_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SemanticProfileRef":
        parsed = require_closed_mapping(
            "SemanticProfileRef",
            data,
            required=frozenset(
                {
                    "system_id",
                    "profile_id",
                    "profile_version",
                    "registry_ref",
                    "registry_revision",
                    "registry_digest",
                    "decoder_contract_ref",
                    "binding_digest",
                }
            ),
            optional=frozenset(),
        )
        result = cls(
            system_id=parsed["system_id"],
            profile_id=parsed["profile_id"],
            profile_version=parsed["profile_version"],
            registry_ref=parsed["registry_ref"],
            registry_revision=parsed["registry_revision"],
            registry_digest=parsed["registry_digest"],
            decoder_contract_ref=parsed["decoder_contract_ref"],
        )
        _verify_digest("SemanticProfileRef", result.binding_digest, parsed["binding_digest"])
        return result


@dataclass(frozen=True)
class ExternalSemanticBinding:
    semantic_ref: str
    profile: SemanticProfileRef
    external_object_ref: str
    external_object_digest: str
    binding_kind: BindingKind
    artifact_role: ArtifactRole
    binding_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "semantic_ref",
            require_non_empty("semantic_ref", self.semantic_ref),
        )
        if not isinstance(self.profile, SemanticProfileRef):
            raise ValueError("profile must be a SemanticProfileRef")
        object.__setattr__(
            self,
            "external_object_ref",
            require_non_empty("external_object_ref", self.external_object_ref),
        )
        object.__setattr__(
            self,
            "external_object_digest",
            require_sha256("external_object_digest", self.external_object_digest),
        )
        if not isinstance(self.binding_kind, BindingKind):
            raise ValueError("binding_kind must be a BindingKind")
        if not isinstance(self.artifact_role, ArtifactRole):
            raise ValueError("artifact_role must be an ArtifactRole")
        object.__setattr__(
            self,
            "binding_digest",
            canonical_record_digest(
                "macr.semantic.external-binding.v1",
                self._identity_dict(),
            ),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "semantic_ref": self.semantic_ref,
            "profile_binding_digest": self.profile.binding_digest,
            "external_object_ref": self.external_object_ref,
            "external_object_digest": self.external_object_digest,
            "binding_kind": self.binding_kind.value,
            "artifact_role": self.artifact_role.value,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {
            "semantic_ref": self.semantic_ref,
            "profile": self.profile.to_public_dict(),
            "external_object_ref": self.external_object_ref,
            "external_object_digest": self.external_object_digest,
            "binding_kind": self.binding_kind.value,
            "artifact_role": self.artifact_role.value,
            "binding_digest": self.binding_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExternalSemanticBinding":
        parsed = require_closed_mapping(
            "ExternalSemanticBinding",
            data,
            required=frozenset(
                {
                    "semantic_ref",
                    "profile",
                    "external_object_ref",
                    "external_object_digest",
                    "binding_kind",
                    "artifact_role",
                    "binding_digest",
                }
            ),
            optional=frozenset(),
        )
        result = cls(
            semantic_ref=parsed["semantic_ref"],
            profile=SemanticProfileRef.from_dict(parsed["profile"]),
            external_object_ref=parsed["external_object_ref"],
            external_object_digest=parsed["external_object_digest"],
            binding_kind=BindingKind(parsed["binding_kind"]),
            artifact_role=ArtifactRole(parsed["artifact_role"]),
        )
        _verify_digest(
            "ExternalSemanticBinding",
            result.binding_digest,
            parsed["binding_digest"],
        )
        return result


@dataclass(frozen=True)
class SemanticProvenance:
    origin_kind: str
    origin_ref: str
    source_refs: tuple[str, ...]
    agent_run_id: str | None
    created_by_ref: str
    created_at: str
    provenance_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "origin_kind", require_non_empty("origin_kind", self.origin_kind))
        object.__setattr__(self, "origin_ref", require_non_empty("origin_ref", self.origin_ref))
        object.__setattr__(
            self,
            "source_refs",
            require_string_tuple("source_refs", self.source_refs),
        )
        if self.agent_run_id is not None:
            object.__setattr__(
                self,
                "agent_run_id",
                require_uuid4("agent_run_id", self.agent_run_id),
            )
        object.__setattr__(
            self,
            "created_by_ref",
            require_non_empty("created_by_ref", self.created_by_ref),
        )
        object.__setattr__(
            self,
            "created_at",
            normalize_timestamp("created_at", self.created_at),
        )
        object.__setattr__(
            self,
            "provenance_digest",
            canonical_record_digest(
                "macr.semantic.provenance.v1",
                self._identity_dict(),
            ),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "origin_kind": self.origin_kind,
            "origin_ref": self.origin_ref,
            "source_refs": list(self.source_refs),
            "agent_run_id": self.agent_run_id,
            "created_by_ref": self.created_by_ref,
            "created_at": self.created_at,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "provenance_digest": self.provenance_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SemanticProvenance":
        parsed = require_closed_mapping(
            "SemanticProvenance",
            data,
            required=frozenset(
                {
                    "origin_kind",
                    "origin_ref",
                    "source_refs",
                    "agent_run_id",
                    "created_by_ref",
                    "created_at",
                    "provenance_digest",
                }
            ),
            optional=frozenset(),
        )
        result = cls(
            origin_kind=parsed["origin_kind"],
            origin_ref=parsed["origin_ref"],
            source_refs=tuple(parsed["source_refs"]),
            agent_run_id=parsed["agent_run_id"],
            created_by_ref=parsed["created_by_ref"],
            created_at=parsed["created_at"],
        )
        _verify_digest("SemanticProvenance", result.provenance_digest, parsed["provenance_digest"])
        return result


def _status_for_node(node_type: SemanticNodeType, value: object) -> SemanticStatus:
    if node_type in {SemanticNodeType.CLAIM, SemanticNodeType.HYPOTHESIS}:
        if not isinstance(value, ClaimStatus):
            raise ValueError("claim and hypothesis nodes require ClaimStatus")
        return value
    if node_type in {SemanticNodeType.AMBIGUITY, SemanticNodeType.OBLIGATION}:
        if not isinstance(value, ResolutionStatus):
            raise ValueError("ambiguity and obligation nodes require ResolutionStatus")
        return value
    if not isinstance(value, SemanticLifecycleStatus):
        raise ValueError("this node type requires SemanticLifecycleStatus")
    return value


def _status_from_text(node_type: SemanticNodeType, value: object) -> SemanticStatus:
    if not isinstance(value, str):
        raise ValueError("semantic status must be text")
    if node_type in {SemanticNodeType.CLAIM, SemanticNodeType.HYPOTHESIS}:
        return ClaimStatus(value)
    if node_type in {SemanticNodeType.AMBIGUITY, SemanticNodeType.OBLIGATION}:
        return ResolutionStatus(value)
    return SemanticLifecycleStatus(value)


@dataclass(frozen=True)
class SemanticNode:
    node_id: str
    node_type: SemanticNodeType
    payload: object
    scope_ref: str
    status: SemanticStatus
    effects: tuple[str, ...]
    constraints: tuple[str, ...]
    policy: object
    provenance: SemanticProvenance
    temporal: object
    external_bindings: tuple[ExternalSemanticBinding, ...]
    content_digest: str = field(init=False)
    record_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", require_non_empty("node_id", self.node_id))
        if not isinstance(self.node_type, SemanticNodeType):
            raise ValueError("node_type must be a SemanticNodeType")
        object.__setattr__(
            self,
            "payload",
            freeze_json_value("semantic payload", require_json_object("semantic payload", self.payload)),
        )
        object.__setattr__(self, "scope_ref", require_non_empty("scope_ref", self.scope_ref))
        object.__setattr__(self, "status", _status_for_node(self.node_type, self.status))
        object.__setattr__(self, "effects", require_string_tuple("effects", self.effects))
        object.__setattr__(
            self,
            "constraints",
            require_string_tuple("constraints", self.constraints),
        )
        object.__setattr__(
            self,
            "policy",
            freeze_json_value("semantic policy", require_json_object("semantic policy", self.policy)),
        )
        if not isinstance(self.provenance, SemanticProvenance):
            raise ValueError("provenance must be SemanticProvenance")
        object.__setattr__(
            self,
            "temporal",
            freeze_json_value(
                "semantic temporal",
                require_json_object("semantic temporal", self.temporal),
            ),
        )
        bindings = _canonical_records(
            "external_bindings",
            self.external_bindings,
            ExternalSemanticBinding,
            "binding_digest",
        )
        if any(item.semantic_ref != self.node_id for item in bindings):
            raise ValueError("external binding semantic_ref must match node_id")
        object.__setattr__(self, "external_bindings", bindings)
        object.__setattr__(
            self,
            "content_digest",
            canonical_record_digest(
                "macr.semantic.node-content.v1",
                {
                    "node_type": self.node_type.value,
                    "payload": public_json_value(self.payload),
                    "scope_ref": self.scope_ref,
                },
            ),
        )
        object.__setattr__(
            self,
            "record_digest",
            canonical_record_digest(
                "macr.semantic.node-record.v1",
                self._record_identity_dict(),
            ),
        )

    def _record_identity_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "content_digest": self.content_digest,
            "status": self.status.value,
            "effects": list(self.effects),
            "constraints": list(self.constraints),
            "policy": public_json_value(self.policy),
            "provenance_digest": self.provenance.provenance_digest,
            "temporal": public_json_value(self.temporal),
            "external_binding_digests": [
                item.binding_digest for item in self.external_bindings
            ],
        }

    def to_public_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "payload": public_json_value(self.payload),
            "scope_ref": self.scope_ref,
            "status": self.status.value,
            "effects": list(self.effects),
            "constraints": list(self.constraints),
            "policy": public_json_value(self.policy),
            "provenance": self.provenance.to_public_dict(),
            "temporal": public_json_value(self.temporal),
            "external_bindings": [item.to_public_dict() for item in self.external_bindings],
            "content_digest": self.content_digest,
            "record_digest": self.record_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SemanticNode":
        required = frozenset(
            {
                "node_id",
                "node_type",
                "payload",
                "scope_ref",
                "status",
                "effects",
                "constraints",
                "policy",
                "provenance",
                "temporal",
                "external_bindings",
                "content_digest",
                "record_digest",
            }
        )
        parsed = require_closed_mapping(
            "SemanticNode",
            data,
            required=required,
            optional=frozenset(),
        )
        node_type = SemanticNodeType(parsed["node_type"])
        result = cls(
            node_id=parsed["node_id"],
            node_type=node_type,
            payload=parsed["payload"],
            scope_ref=parsed["scope_ref"],
            status=_status_from_text(node_type, parsed["status"]),
            effects=tuple(parsed["effects"]),
            constraints=tuple(parsed["constraints"]),
            policy=parsed["policy"],
            provenance=SemanticProvenance.from_dict(parsed["provenance"]),
            temporal=parsed["temporal"],
            external_bindings=tuple(
                ExternalSemanticBinding.from_dict(item)
                for item in parsed["external_bindings"]
            ),
        )
        _verify_digest("SemanticNode content", result.content_digest, parsed["content_digest"])
        _verify_digest("SemanticNode record", result.record_digest, parsed["record_digest"])
        return result


@dataclass(frozen=True)
class SemanticRelation:
    relation_id: str
    source_ref: str
    relation_type: SemanticRelationType
    target_ref: str
    qualifiers: object
    provenance: SemanticProvenance
    relation_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "relation_id", require_non_empty("relation_id", self.relation_id))
        object.__setattr__(self, "source_ref", require_non_empty("source_ref", self.source_ref))
        if not isinstance(self.relation_type, SemanticRelationType):
            raise ValueError("relation_type must be a SemanticRelationType")
        object.__setattr__(self, "target_ref", require_non_empty("target_ref", self.target_ref))
        object.__setattr__(
            self,
            "qualifiers",
            freeze_json_value("relation qualifiers", require_json_object("relation qualifiers", self.qualifiers)),
        )
        if not isinstance(self.provenance, SemanticProvenance):
            raise ValueError("provenance must be SemanticProvenance")
        object.__setattr__(
            self,
            "relation_digest",
            canonical_record_digest(
                "macr.semantic.relation.v1",
                {
                    "relation_id": self.relation_id,
                    "source_ref": self.source_ref,
                    "relation_type": self.relation_type.value,
                    "target_ref": self.target_ref,
                    "qualifiers": public_json_value(self.qualifiers),
                    "provenance_digest": self.provenance.provenance_digest,
                },
            ),
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "relation_id": self.relation_id,
            "source_ref": self.source_ref,
            "relation_type": self.relation_type.value,
            "target_ref": self.target_ref,
            "qualifiers": public_json_value(self.qualifiers),
            "provenance": self.provenance.to_public_dict(),
            "relation_digest": self.relation_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SemanticRelation":
        parsed = require_closed_mapping(
            "SemanticRelation",
            data,
            required=frozenset(
                {
                    "relation_id",
                    "source_ref",
                    "relation_type",
                    "target_ref",
                    "qualifiers",
                    "provenance",
                    "relation_digest",
                }
            ),
            optional=frozenset(),
        )
        result = cls(
            relation_id=parsed["relation_id"],
            source_ref=parsed["source_ref"],
            relation_type=SemanticRelationType(parsed["relation_type"]),
            target_ref=parsed["target_ref"],
            qualifiers=parsed["qualifiers"],
            provenance=SemanticProvenance.from_dict(parsed["provenance"]),
        )
        _verify_digest("SemanticRelation", result.relation_digest, parsed["relation_digest"])
        return result


@dataclass(frozen=True)
class SemanticEvent:
    event_id: str
    event_type: SemanticEventType
    subject_refs: tuple[str, ...]
    parent_event_refs: tuple[str, ...]
    payload: object
    provenance: SemanticProvenance
    created_at: str
    event_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", require_non_empty("event_id", self.event_id))
        if not isinstance(self.event_type, SemanticEventType):
            raise ValueError("event_type must be a SemanticEventType")
        subjects = require_string_tuple("subject_refs", self.subject_refs)
        if not subjects:
            raise ValueError("subject_refs must not be empty")
        object.__setattr__(self, "subject_refs", subjects)
        parents = require_string_tuple("parent_event_refs", self.parent_event_refs)
        if self.event_type in {SemanticEventType.CORRECTION, SemanticEventType.RESOLUTION} and not parents:
            raise ValueError("correction and resolution require parent_event_refs")
        object.__setattr__(self, "parent_event_refs", parents)
        object.__setattr__(
            self,
            "payload",
            freeze_json_value("event payload", require_json_object("event payload", self.payload)),
        )
        if not isinstance(self.provenance, SemanticProvenance):
            raise ValueError("provenance must be SemanticProvenance")
        object.__setattr__(
            self,
            "created_at",
            normalize_timestamp("created_at", self.created_at),
        )
        object.__setattr__(
            self,
            "event_digest",
            canonical_record_digest(
                "macr.semantic.event.v1",
                {
                    "event_id": self.event_id,
                    "event_type": self.event_type.value,
                    "subject_refs": list(self.subject_refs),
                    "parent_event_refs": list(self.parent_event_refs),
                    "payload": public_json_value(self.payload),
                    "provenance_digest": self.provenance.provenance_digest,
                    "created_at": self.created_at,
                },
            ),
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "subject_refs": list(self.subject_refs),
            "parent_event_refs": list(self.parent_event_refs),
            "payload": public_json_value(self.payload),
            "provenance": self.provenance.to_public_dict(),
            "created_at": self.created_at,
            "event_digest": self.event_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SemanticEvent":
        parsed = require_closed_mapping(
            "SemanticEvent",
            data,
            required=frozenset(
                {
                    "event_id",
                    "event_type",
                    "subject_refs",
                    "parent_event_refs",
                    "payload",
                    "provenance",
                    "created_at",
                    "event_digest",
                }
            ),
            optional=frozenset(),
        )
        result = cls(
            event_id=parsed["event_id"],
            event_type=SemanticEventType(parsed["event_type"]),
            subject_refs=tuple(parsed["subject_refs"]),
            parent_event_refs=tuple(parsed["parent_event_refs"]),
            payload=parsed["payload"],
            provenance=SemanticProvenance.from_dict(parsed["provenance"]),
            created_at=parsed["created_at"],
        )
        _verify_digest("SemanticEvent", result.event_digest, parsed["event_digest"])
        return result


@dataclass(frozen=True)
class SemanticPatch:
    patch_id: str
    base_graph_digest: str
    add_nodes: tuple[SemanticNode, ...]
    add_relations: tuple[SemanticRelation, ...]
    status_updates: tuple[object, ...]
    supersession_refs: tuple[str, ...]
    producer_ref: str
    patch_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "patch_id", require_non_empty("patch_id", self.patch_id))
        object.__setattr__(
            self,
            "base_graph_digest",
            require_sha256("base_graph_digest", self.base_graph_digest),
        )
        nodes = _canonical_records(
            "add_nodes",
            self.add_nodes,
            SemanticNode,
            "record_digest",
        )
        relations = _canonical_records(
            "add_relations",
            self.add_relations,
            SemanticRelation,
            "relation_digest",
        )
        object.__setattr__(self, "add_nodes", nodes)
        object.__setattr__(self, "add_relations", relations)
        updates = tuple(
            freeze_json_value(
                "status update",
                require_json_object("status update", item),
            )
            for item in self.status_updates
        )
        update_keys = [
            canonical_record_digest("macr.semantic.status-update.v1", item)
            for item in updates
        ]
        if len(set(update_keys)) != len(update_keys):
            raise ValueError("status_updates must not contain duplicates")
        object.__setattr__(
            self,
            "status_updates",
            tuple(item for _, item in sorted(zip(update_keys, updates, strict=True))),
        )
        object.__setattr__(
            self,
            "supersession_refs",
            require_string_tuple("supersession_refs", self.supersession_refs),
        )
        object.__setattr__(
            self,
            "producer_ref",
            require_non_empty("producer_ref", self.producer_ref),
        )
        object.__setattr__(
            self,
            "patch_digest",
            canonical_record_digest(
                "macr.semantic.patch.v1",
                {
                    "patch_id": self.patch_id,
                    "base_graph_digest": self.base_graph_digest,
                    "add_node_digests": [item.record_digest for item in self.add_nodes],
                    "add_relation_digests": [
                        item.relation_digest for item in self.add_relations
                    ],
                    "status_updates": [
                        public_json_value(item) for item in self.status_updates
                    ],
                    "supersession_refs": list(self.supersession_refs),
                    "producer_ref": self.producer_ref,
                },
            ),
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "patch_id": self.patch_id,
            "base_graph_digest": self.base_graph_digest,
            "add_nodes": [item.to_public_dict() for item in self.add_nodes],
            "add_relations": [item.to_public_dict() for item in self.add_relations],
            "status_updates": [public_json_value(item) for item in self.status_updates],
            "supersession_refs": list(self.supersession_refs),
            "producer_ref": self.producer_ref,
            "patch_digest": self.patch_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SemanticPatch":
        parsed = require_closed_mapping(
            "SemanticPatch",
            data,
            required=frozenset(
                {
                    "patch_id",
                    "base_graph_digest",
                    "add_nodes",
                    "add_relations",
                    "status_updates",
                    "supersession_refs",
                    "producer_ref",
                    "patch_digest",
                }
            ),
            optional=frozenset(),
        )
        result = cls(
            patch_id=parsed["patch_id"],
            base_graph_digest=parsed["base_graph_digest"],
            add_nodes=tuple(SemanticNode.from_dict(item) for item in parsed["add_nodes"]),
            add_relations=tuple(
                SemanticRelation.from_dict(item) for item in parsed["add_relations"]
            ),
            status_updates=tuple(parsed["status_updates"]),
            supersession_refs=tuple(parsed["supersession_refs"]),
            producer_ref=parsed["producer_ref"],
        )
        _verify_digest("SemanticPatch", result.patch_digest, parsed["patch_digest"])
        return result


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
