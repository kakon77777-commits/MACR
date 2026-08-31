from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .._v07_contracts import (
    canonical_record_digest,
    require_closed_mapping,
    require_non_empty,
    require_positive_int,
    require_sha256,
    require_string_tuple,
    require_uuid4,
)
from ..agent.contracts import SemanticStateBinding
from ..agent.store import AgentStore
from ..canonical import canonical_json_bytes
from .contracts import (
    ResolutionStatus,
    SemanticNode,
    SemanticNodeType,
    SemanticRelation,
    SemanticRelationType,
)
from .errors import (
    SemanticProjectionConflictError,
    SemanticProjectionIncompleteError,
)
from .store import SemanticStore


SEMANTIC_PROJECTION_PROFILE_SCHEMA_VERSION = "macr-semantic-projection-profile/v1"
SEMANTIC_CONTEXT_REQUEST_SCHEMA_VERSION = "macr-semantic-context-request/v1"
SEMANTIC_CONTEXT_PROJECTION_SCHEMA_VERSION = "macr-semantic-context-projection/v1"
MAX_PROJECTION_NODES = 128
MAX_PROJECTION_RELATIONS = 128


def _bounded_limit(name: str, value: object, maximum: int) -> int:
    selected = require_positive_int(name, value)
    if selected > maximum:
        raise ValueError(f"{name} must not exceed {maximum}")
    return selected


@dataclass(frozen=True)
class SemanticProjectionProfile:
    profile_id: str
    profile_version: str
    require_goal_plan_connection: bool
    include_unresolved_obligations: bool
    include_blocking_ambiguities: bool
    schema_version: str = field(
        init=False, default=SEMANTIC_PROJECTION_PROFILE_SCHEMA_VERSION
    )
    profile_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "profile_id", require_non_empty("profile_id", self.profile_id)
        )
        object.__setattr__(
            self,
            "profile_version",
            require_non_empty("profile_version", self.profile_version),
        )
        for name in (
            "require_goal_plan_connection",
            "include_unresolved_obligations",
            "include_blocking_ambiguities",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be boolean")
        object.__setattr__(
            self,
            "profile_digest",
            canonical_record_digest(
                "macr.semantic.projection-profile.v1", self._identity_dict()
            ),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "require_goal_plan_connection": self.require_goal_plan_connection,
            "include_unresolved_obligations": self.include_unresolved_obligations,
            "include_blocking_ambiguities": self.include_blocking_ambiguities,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "profile_digest": self.profile_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SemanticProjectionProfile":
        parsed = require_closed_mapping(
            "SemanticProjectionProfile",
            data,
            required=frozenset(
                {
                    "schema_version",
                    "profile_id",
                    "profile_version",
                    "require_goal_plan_connection",
                    "include_unresolved_obligations",
                    "include_blocking_ambiguities",
                    "profile_digest",
                }
            ),
            optional=frozenset(),
        )
        if parsed["schema_version"] != SEMANTIC_PROJECTION_PROFILE_SCHEMA_VERSION:
            raise ValueError("semantic projection profile schema mismatch")
        result = cls(
            profile_id=parsed["profile_id"],
            profile_version=parsed["profile_version"],
            require_goal_plan_connection=parsed["require_goal_plan_connection"],
            include_unresolved_obligations=parsed["include_unresolved_obligations"],
            include_blocking_ambiguities=parsed["include_blocking_ambiguities"],
        )
        if require_sha256("profile_digest", parsed["profile_digest"]) != result.profile_digest:
            raise ValueError("semantic projection profile digest mismatch")
        return result


@dataclass(frozen=True)
class SemanticContextRequest:
    agent_run_id: str
    graph_id: str
    graph_revision: int
    graph_digest: str
    profile: SemanticProjectionProfile
    required_root_node_ids: tuple[str, ...]
    allowed_node_types: tuple[SemanticNodeType, ...]
    max_nodes: int
    max_relations: int
    schema_version: str = field(
        init=False, default=SEMANTIC_CONTEXT_REQUEST_SCHEMA_VERSION
    )
    request_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "agent_run_id", require_uuid4("agent_run_id", self.agent_run_id)
        )
        object.__setattr__(self, "graph_id", require_uuid4("graph_id", self.graph_id))
        object.__setattr__(
            self,
            "graph_revision",
            require_positive_int("graph_revision", self.graph_revision),
        )
        object.__setattr__(
            self, "graph_digest", require_sha256("graph_digest", self.graph_digest)
        )
        if not isinstance(self.profile, SemanticProjectionProfile):
            raise ValueError("profile must be a SemanticProjectionProfile")
        roots = require_string_tuple(
            "required_root_node_ids", self.required_root_node_ids, maximum=128
        )
        if not roots:
            raise ValueError("required_root_node_ids must not be empty")
        object.__setattr__(self, "required_root_node_ids", roots)
        if not isinstance(self.allowed_node_types, (tuple, list)):
            raise ValueError("allowed_node_types must be an array")
        allowed = tuple(self.allowed_node_types)
        if not allowed or any(not isinstance(item, SemanticNodeType) for item in allowed):
            raise ValueError("allowed_node_types must contain SemanticNodeType values")
        if len(set(allowed)) != len(allowed):
            raise ValueError("allowed_node_types must not contain duplicates")
        object.__setattr__(
            self, "allowed_node_types", tuple(sorted(allowed, key=lambda item: item.value))
        )
        object.__setattr__(
            self,
            "max_nodes",
            _bounded_limit("max_nodes", self.max_nodes, MAX_PROJECTION_NODES),
        )
        object.__setattr__(
            self,
            "max_relations",
            _bounded_limit(
                "max_relations", self.max_relations, MAX_PROJECTION_RELATIONS
            ),
        )
        object.__setattr__(
            self,
            "request_digest",
            canonical_record_digest(
                "macr.semantic.context-request.v1", self._identity_dict()
            ),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "agent_run_id": self.agent_run_id,
            "graph_id": self.graph_id,
            "graph_revision": self.graph_revision,
            "graph_digest": self.graph_digest,
            "profile": self.profile.to_public_dict(),
            "required_root_node_ids": list(self.required_root_node_ids),
            "allowed_node_types": [item.value for item in self.allowed_node_types],
            "max_nodes": self.max_nodes,
            "max_relations": self.max_relations,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "request_digest": self.request_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SemanticContextRequest":
        parsed = require_closed_mapping(
            "SemanticContextRequest",
            data,
            required=frozenset(
                {
                    "schema_version",
                    "agent_run_id",
                    "graph_id",
                    "graph_revision",
                    "graph_digest",
                    "profile",
                    "required_root_node_ids",
                    "allowed_node_types",
                    "max_nodes",
                    "max_relations",
                    "request_digest",
                }
            ),
            optional=frozenset(),
        )
        if parsed["schema_version"] != SEMANTIC_CONTEXT_REQUEST_SCHEMA_VERSION:
            raise ValueError("semantic context request schema mismatch")
        try:
            result = cls(
                agent_run_id=parsed["agent_run_id"],
                graph_id=parsed["graph_id"],
                graph_revision=parsed["graph_revision"],
                graph_digest=parsed["graph_digest"],
                profile=SemanticProjectionProfile.from_dict(parsed["profile"]),
                required_root_node_ids=tuple(parsed["required_root_node_ids"]),
                allowed_node_types=tuple(
                    SemanticNodeType(item) for item in parsed["allowed_node_types"]
                ),
                max_nodes=parsed["max_nodes"],
                max_relations=parsed["max_relations"],
            )
        except Exception as exc:
            raise ValueError("semantic context request is invalid") from exc
        if require_sha256("request_digest", parsed["request_digest"]) != result.request_digest:
            raise ValueError("semantic context request digest mismatch")
        return result


@dataclass(frozen=True)
class SemanticContextProjection:
    request_digest: str
    agent_run_id: str
    graph_id: str
    graph_revision: int
    graph_digest: str
    profile: SemanticProjectionProfile
    nodes: tuple[SemanticNode, ...]
    relations: tuple[SemanticRelation, ...]
    omitted_node_record_digests: tuple[str, ...]
    omitted_relation_digests: tuple[str, ...]
    schema_version: str = field(
        init=False, default=SEMANTIC_CONTEXT_PROJECTION_SCHEMA_VERSION
    )
    projection_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "request_digest", require_sha256("request_digest", self.request_digest)
        )
        object.__setattr__(
            self, "agent_run_id", require_uuid4("agent_run_id", self.agent_run_id)
        )
        object.__setattr__(self, "graph_id", require_uuid4("graph_id", self.graph_id))
        object.__setattr__(
            self,
            "graph_revision",
            require_positive_int("graph_revision", self.graph_revision),
        )
        object.__setattr__(
            self, "graph_digest", require_sha256("graph_digest", self.graph_digest)
        )
        if not isinstance(self.profile, SemanticProjectionProfile):
            raise ValueError("profile must be a SemanticProjectionProfile")
        nodes = tuple(self.nodes)
        relations = tuple(self.relations)
        if any(not isinstance(item, SemanticNode) for item in nodes):
            raise ValueError("nodes must contain SemanticNode values")
        if any(not isinstance(item, SemanticRelation) for item in relations):
            raise ValueError("relations must contain SemanticRelation values")
        if len(nodes) > MAX_PROJECTION_NODES or len(relations) > MAX_PROJECTION_RELATIONS:
            raise ValueError("semantic context projection exceeds hard limits")
        object.__setattr__(self, "nodes", tuple(sorted(nodes, key=lambda item: item.node_id)))
        object.__setattr__(
            self, "relations", tuple(sorted(relations, key=lambda item: item.relation_id))
        )
        object.__setattr__(
            self,
            "omitted_node_record_digests",
            tuple(
                sorted(
                    require_sha256("omitted node digest", item)
                    for item in self.omitted_node_record_digests
                )
            ),
        )
        object.__setattr__(
            self,
            "omitted_relation_digests",
            tuple(
                sorted(
                    require_sha256("omitted relation digest", item)
                    for item in self.omitted_relation_digests
                )
            ),
        )
        object.__setattr__(
            self,
            "projection_digest",
            canonical_record_digest(
                "macr.semantic.context-projection.v1", self._identity_dict()
            ),
        )

    @property
    def graph_ref(self) -> str:
        return f"semantic-graph:{self.graph_id}"

    def _identity_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_digest": self.request_digest,
            "agent_run_id": self.agent_run_id,
            "graph_id": self.graph_id,
            "graph_ref": self.graph_ref,
            "graph_revision": self.graph_revision,
            "graph_digest": self.graph_digest,
            "profile": self.profile.to_public_dict(),
            "nodes": [item.to_public_dict() for item in self.nodes],
            "relations": [item.to_public_dict() for item in self.relations],
            "omitted_node_record_digests": list(self.omitted_node_record_digests),
            "omitted_relation_digests": list(self.omitted_relation_digests),
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "projection_digest": self.projection_digest}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_public_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SemanticContextProjection":
        parsed = require_closed_mapping(
            "SemanticContextProjection",
            data,
            required=frozenset(
                {
                    "schema_version",
                    "request_digest",
                    "agent_run_id",
                    "graph_id",
                    "graph_ref",
                    "graph_revision",
                    "graph_digest",
                    "profile",
                    "nodes",
                    "relations",
                    "omitted_node_record_digests",
                    "omitted_relation_digests",
                    "projection_digest",
                }
            ),
            optional=frozenset(),
        )
        if parsed["schema_version"] != SEMANTIC_CONTEXT_PROJECTION_SCHEMA_VERSION:
            raise ValueError("semantic context projection schema mismatch")
        result = cls(
            request_digest=parsed["request_digest"],
            agent_run_id=parsed["agent_run_id"],
            graph_id=parsed["graph_id"],
            graph_revision=parsed["graph_revision"],
            graph_digest=parsed["graph_digest"],
            profile=SemanticProjectionProfile.from_dict(parsed["profile"]),
            nodes=tuple(SemanticNode.from_dict(item) for item in parsed["nodes"]),
            relations=tuple(
                SemanticRelation.from_dict(item) for item in parsed["relations"]
            ),
            omitted_node_record_digests=tuple(
                parsed["omitted_node_record_digests"]
            ),
            omitted_relation_digests=tuple(parsed["omitted_relation_digests"]),
        )
        if parsed["graph_ref"] != result.graph_ref:
            raise ValueError("semantic context graph_ref mismatch")
        if require_sha256("projection_digest", parsed["projection_digest"]) != result.projection_digest:
            raise ValueError("semantic context projection digest mismatch")
        return result


class SemanticContextProjector:
    def __init__(self, agent_store: AgentStore, semantic_store: SemanticStore) -> None:
        if not isinstance(agent_store, AgentStore):
            raise ValueError("agent_store must be an AgentStore")
        if not isinstance(semantic_store, SemanticStore):
            raise ValueError("semantic_store must be a SemanticStore")
        if agent_store.database.path != semantic_store.database.path:
            raise ValueError("Agent and semantic stores must share one database")
        self.agent_store = agent_store
        self.semantic_store = semantic_store

    def _after_binding_read(self) -> None:
        """Test seam after the snapshot-pinning read; production is a no-op."""

    def project(self, request: SemanticContextRequest) -> SemanticContextProjection:
        if not isinstance(request, SemanticContextRequest):
            raise ValueError("request must be a SemanticContextRequest")
        expected_binding = SemanticStateBinding(
            f"semantic-graph:{request.graph_id}",
            request.graph_digest,
            request.graph_revision,
        )
        connection = self.agent_store.database.connect()
        try:
            connection.execute("BEGIN")
            observed_binding = (
                self.agent_store._get_agent_semantic_binding_on_connection(
                    connection, request.agent_run_id
                )
            )
            self._after_binding_read()
            revision, nodes, relations = (
                self.semantic_store._graph_snapshot_on_connection(
                    connection, request.graph_id, request.graph_revision
                )
            )
            connection.commit()
        except Exception as exc:
            connection.rollback()
            raise SemanticProjectionConflictError(
                "semantic context source evidence is invalid"
            ) from exc
        finally:
            connection.close()
        if observed_binding != expected_binding:
            raise SemanticProjectionConflictError(
                "AgentRun is not pinned to requested semantic revision"
            )
        if revision.graph_digest != request.graph_digest:
            raise SemanticProjectionConflictError(
                "semantic context graph digest conflicts"
            )
        return self._select(request, nodes, relations)

    @staticmethod
    def _select(
        request: SemanticContextRequest,
        nodes: tuple[SemanticNode, ...],
        relations: tuple[SemanticRelation, ...],
    ) -> SemanticContextProjection:
        by_id = {item.node_id: item for item in nodes}
        if len(by_id) != len(nodes):
            raise SemanticProjectionConflictError("semantic node IDs are ambiguous")
        missing = [item for item in request.required_root_node_ids if item not in by_id]
        if missing:
            raise SemanticProjectionIncompleteError(
                "required semantic root is absent"
            )
        mandatory = set(request.required_root_node_ids)
        if request.profile.include_unresolved_obligations:
            mandatory.update(
                item.node_id
                for item in nodes
                if item.node_type is SemanticNodeType.OBLIGATION
                and item.status is ResolutionStatus.UNRESOLVED
            )
        if request.profile.include_blocking_ambiguities:
            blocking_sources = {
                relation.source_ref
                for relation in relations
                if relation.relation_type is SemanticRelationType.BLOCKS
                and relation.target_ref in mandatory
            }
            mandatory.update(
                item.node_id
                for item in nodes
                if item.node_id in blocking_sources
                and item.node_type is SemanticNodeType.AMBIGUITY
                and item.status is ResolutionStatus.UNRESOLVED
            )
        allowed = set(request.allowed_node_types)
        if any(by_id[item].node_type not in allowed for item in mandatory):
            raise SemanticProjectionIncompleteError(
                "required semantic node type is not allowed"
            )
        if request.profile.require_goal_plan_connection:
            required_nodes = [by_id[item] for item in request.required_root_node_ids]
            goals = {item.node_id for item in required_nodes if item.node_type is SemanticNodeType.GOAL}
            plans = {item.node_id for item in required_nodes if item.node_type is SemanticNodeType.PLAN}
            if not goals or not plans or not any(
                relation.source_ref in goals and relation.target_ref in plans
                for relation in relations
            ):
                raise SemanticProjectionIncompleteError(
                    "required Goal-to-Plan connection is absent"
                )
        mandatory_nodes = sorted((by_id[item] for item in mandatory), key=lambda item: item.node_id)
        if len(mandatory_nodes) > request.max_nodes:
            raise SemanticProjectionIncompleteError(
                "required semantic nodes exceed projection limit"
            )
        optional_nodes = sorted(
            (
                item
                for item in nodes
                if item.node_id not in mandatory and item.node_type in allowed
            ),
            key=lambda item: item.node_id,
        )
        selected_nodes = tuple(
            mandatory_nodes
            + optional_nodes[: request.max_nodes - len(mandatory_nodes)]
        )
        selected_ids = {item.node_id for item in selected_nodes}
        eligible_relations = sorted(
            (
                item
                for item in relations
                if item.source_ref in selected_ids and item.target_ref in selected_ids
            ),
            key=lambda item: item.relation_id,
        )
        mandatory_relations = [
            item
            for item in eligible_relations
            if item.source_ref in mandatory and item.target_ref in mandatory
        ]
        if len(mandatory_relations) > request.max_relations:
            raise SemanticProjectionIncompleteError(
                "required semantic relations exceed projection limit"
            )
        mandatory_digests = {item.relation_digest for item in mandatory_relations}
        optional_relations = [
            item for item in eligible_relations if item.relation_digest not in mandatory_digests
        ]
        selected_relations = tuple(
            mandatory_relations
            + optional_relations[: request.max_relations - len(mandatory_relations)]
        )
        selected_node_digests = {item.record_digest for item in selected_nodes}
        selected_relation_digests = {
            item.relation_digest for item in selected_relations
        }
        return SemanticContextProjection(
            request_digest=request.request_digest,
            agent_run_id=request.agent_run_id,
            graph_id=request.graph_id,
            graph_revision=request.graph_revision,
            graph_digest=request.graph_digest,
            profile=request.profile,
            nodes=selected_nodes,
            relations=selected_relations,
            omitted_node_record_digests=tuple(
                item.record_digest
                for item in nodes
                if item.record_digest not in selected_node_digests
            ),
            omitted_relation_digests=tuple(
                item.relation_digest
                for item in relations
                if item.relation_digest not in selected_relation_digests
            ),
        )
