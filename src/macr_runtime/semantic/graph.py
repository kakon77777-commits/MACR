from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .._v07_contracts import (
    canonical_record_digest,
    normalize_timestamp,
    require_closed_mapping,
    require_optional_non_empty,
    require_positive_int,
    require_sha256,
    require_string_tuple,
    require_uuid4,
)
from ..agent.contracts import SemanticStateBinding
from .errors import SemanticGraphDigestMismatchError
from .registry import SemanticRegistry


SEMANTIC_GRAPH_HEAD_SCHEMA_VERSION = "macr-semantic-graph-head/v1"
SEMANTIC_GRAPH_REVISION_SCHEMA_VERSION = "macr-semantic-graph-revision/v1"


def _digest_tuple(name: str, values: object) -> tuple[str, ...]:
    items = require_string_tuple(name, values, maximum=128)
    normalized = tuple(require_sha256(f"{name} item", item) for item in items)
    return tuple(sorted(normalized))


def calculate_graph_digest(
    *,
    registry_version: str,
    registry_digest: str,
    active_node_record_digests: object,
    active_relation_digests: object,
) -> str:
    return canonical_record_digest(
        "macr.semantic.graph-content.v1",
        {
            "registry_version": registry_version,
            "registry_digest": require_sha256("registry_digest", registry_digest),
            "active_node_record_digests": list(
                _digest_tuple("active_node_record_digests", active_node_record_digests)
            ),
            "active_relation_digests": list(
                _digest_tuple("active_relation_digests", active_relation_digests)
            ),
        },
    )


@dataclass(frozen=True)
class SemanticGraphHead:
    graph_id: str
    scope_ref: str
    graph_revision: int
    registry_version: str
    registry_digest: str
    active_node_record_digests: tuple[str, ...]
    active_relation_digests: tuple[str, ...]
    created_by_agent_run_id: str
    created_at: str
    updated_at: str
    schema_version: str = field(
        init=False, default=SEMANTIC_GRAPH_HEAD_SCHEMA_VERSION
    )
    graph_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "graph_id", require_uuid4("graph_id", self.graph_id))
        if not isinstance(self.scope_ref, str) or not self.scope_ref.strip():
            raise ValueError("scope_ref must be non-empty text")
        object.__setattr__(self, "scope_ref", self.scope_ref.strip())
        object.__setattr__(
            self, "graph_revision", require_positive_int("graph_revision", self.graph_revision)
        )
        if not isinstance(self.registry_version, str) or not self.registry_version.strip():
            raise ValueError("registry_version must be non-empty text")
        object.__setattr__(self, "registry_version", self.registry_version.strip())
        object.__setattr__(
            self, "registry_digest", require_sha256("registry_digest", self.registry_digest)
        )
        object.__setattr__(
            self,
            "active_node_record_digests",
            _digest_tuple("active_node_record_digests", self.active_node_record_digests),
        )
        object.__setattr__(
            self,
            "active_relation_digests",
            _digest_tuple("active_relation_digests", self.active_relation_digests),
        )
        object.__setattr__(
            self,
            "created_by_agent_run_id",
            require_uuid4("created_by_agent_run_id", self.created_by_agent_run_id),
        )
        object.__setattr__(self, "created_at", normalize_timestamp("created_at", self.created_at))
        object.__setattr__(self, "updated_at", normalize_timestamp("updated_at", self.updated_at))
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        object.__setattr__(
            self,
            "graph_digest",
            calculate_graph_digest(
                registry_version=self.registry_version,
                registry_digest=self.registry_digest,
                active_node_record_digests=self.active_node_record_digests,
                active_relation_digests=self.active_relation_digests,
            ),
        )

    @property
    def graph_ref(self) -> str:
        return f"semantic-graph:{self.graph_id}"

    @classmethod
    def create_empty(
        cls,
        *,
        graph_id: str,
        scope_ref: str,
        registry: SemanticRegistry,
        created_by_agent_run_id: str,
        created_at: str,
    ) -> "SemanticGraphHead":
        if not isinstance(registry, SemanticRegistry):
            raise ValueError("registry must be a SemanticRegistry")
        return cls(
            graph_id=graph_id,
            scope_ref=scope_ref,
            graph_revision=1,
            registry_version=registry.registry_version,
            registry_digest=registry.registry_digest,
            active_node_record_digests=(),
            active_relation_digests=(),
            created_by_agent_run_id=created_by_agent_run_id,
            created_at=created_at,
            updated_at=created_at,
        )

    def to_semantic_state_binding(self) -> SemanticStateBinding:
        return SemanticStateBinding(
            self.graph_ref,
            self.graph_digest,
            self.graph_revision,
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "graph_id": self.graph_id,
            "graph_ref": self.graph_ref,
            "scope_ref": self.scope_ref,
            "graph_revision": self.graph_revision,
            "registry_version": self.registry_version,
            "registry_digest": self.registry_digest,
            "active_node_record_digests": list(self.active_node_record_digests),
            "active_relation_digests": list(self.active_relation_digests),
            "created_by_agent_run_id": self.created_by_agent_run_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "graph_digest": self.graph_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SemanticGraphHead":
        parsed = require_closed_mapping(
            "SemanticGraphHead",
            data,
            required=frozenset(
                {
                    "schema_version", "graph_id", "graph_ref", "scope_ref",
                    "graph_revision", "registry_version", "registry_digest",
                    "active_node_record_digests", "active_relation_digests",
                    "created_by_agent_run_id", "created_at", "updated_at",
                    "graph_digest",
                }
            ),
            optional=frozenset(),
        )
        if parsed["schema_version"] != SEMANTIC_GRAPH_HEAD_SCHEMA_VERSION:
            raise ValueError("semantic graph head schema mismatch")
        result = cls(
            graph_id=parsed["graph_id"],
            scope_ref=parsed["scope_ref"],
            graph_revision=parsed["graph_revision"],
            registry_version=parsed["registry_version"],
            registry_digest=parsed["registry_digest"],
            active_node_record_digests=tuple(parsed["active_node_record_digests"]),
            active_relation_digests=tuple(parsed["active_relation_digests"]),
            created_by_agent_run_id=parsed["created_by_agent_run_id"],
            created_at=parsed["created_at"],
            updated_at=parsed["updated_at"],
        )
        if parsed["graph_ref"] != result.graph_ref:
            raise ValueError("graph_ref does not match graph_id")
        if require_sha256("graph_digest", parsed["graph_digest"]) != result.graph_digest:
            raise SemanticGraphDigestMismatchError("semantic graph digest mismatch")
        return result


@dataclass(frozen=True)
class SemanticGraphRevision:
    graph_id: str
    graph_revision: int
    graph_digest: str
    parent_revision: int | None
    parent_graph_digest: str | None
    patch_digest: str | None
    registry_version: str
    registry_digest: str
    active_node_record_digests: tuple[str, ...]
    active_relation_digests: tuple[str, ...]
    committed_at: str
    schema_version: str = field(
        init=False, default=SEMANTIC_GRAPH_REVISION_SCHEMA_VERSION
    )
    revision_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "graph_id", require_uuid4("graph_id", self.graph_id))
        object.__setattr__(
            self, "graph_revision", require_positive_int("graph_revision", self.graph_revision)
        )
        object.__setattr__(self, "graph_digest", require_sha256("graph_digest", self.graph_digest))
        if self.parent_revision is not None:
            object.__setattr__(
                self,
                "parent_revision",
                require_positive_int("parent_revision", self.parent_revision),
            )
        object.__setattr__(
            self,
            "parent_graph_digest",
            None
            if self.parent_graph_digest is None
            else require_sha256("parent_graph_digest", self.parent_graph_digest),
        )
        if (self.parent_revision is None) != (self.parent_graph_digest is None):
            raise ValueError("parent revision and digest must be paired")
        object.__setattr__(
            self,
            "patch_digest",
            None if self.patch_digest is None else require_sha256("patch_digest", self.patch_digest),
        )
        if self.graph_revision == 1 and (
            self.parent_revision is not None or self.patch_digest is not None
        ):
            raise ValueError("initial graph revision cannot have parent or patch")
        if self.graph_revision > 1 and (
            self.parent_revision != self.graph_revision - 1 or self.patch_digest is None
        ):
            raise ValueError("later graph revision requires previous parent and patch")
        if not isinstance(self.registry_version, str) or not self.registry_version.strip():
            raise ValueError("registry_version must be non-empty text")
        object.__setattr__(self, "registry_version", self.registry_version.strip())
        object.__setattr__(self, "registry_digest", require_sha256("registry_digest", self.registry_digest))
        object.__setattr__(
            self,
            "active_node_record_digests",
            _digest_tuple("active_node_record_digests", self.active_node_record_digests),
        )
        object.__setattr__(
            self,
            "active_relation_digests",
            _digest_tuple("active_relation_digests", self.active_relation_digests),
        )
        expected_graph = calculate_graph_digest(
            registry_version=self.registry_version,
            registry_digest=self.registry_digest,
            active_node_record_digests=self.active_node_record_digests,
            active_relation_digests=self.active_relation_digests,
        )
        if expected_graph != self.graph_digest:
            raise SemanticGraphDigestMismatchError("semantic graph revision digest mismatch")
        object.__setattr__(self, "committed_at", normalize_timestamp("committed_at", self.committed_at))
        object.__setattr__(
            self,
            "revision_digest",
            canonical_record_digest(
                "macr.semantic.graph-revision.v1",
                self._identity_dict(),
            ),
        )

    @classmethod
    def from_initial_head(cls, head: SemanticGraphHead) -> "SemanticGraphRevision":
        if not isinstance(head, SemanticGraphHead) or head.graph_revision != 1:
            raise ValueError("initial head must be SemanticGraphHead revision 1")
        return cls(
            graph_id=head.graph_id,
            graph_revision=1,
            graph_digest=head.graph_digest,
            parent_revision=None,
            parent_graph_digest=None,
            patch_digest=None,
            registry_version=head.registry_version,
            registry_digest=head.registry_digest,
            active_node_record_digests=head.active_node_record_digests,
            active_relation_digests=head.active_relation_digests,
            committed_at=head.created_at,
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "graph_id": self.graph_id,
            "graph_revision": self.graph_revision,
            "graph_digest": self.graph_digest,
            "parent_revision": self.parent_revision,
            "parent_graph_digest": self.parent_graph_digest,
            "patch_digest": self.patch_digest,
            "registry_version": self.registry_version,
            "registry_digest": self.registry_digest,
            "active_node_record_digests": list(self.active_node_record_digests),
            "active_relation_digests": list(self.active_relation_digests),
            "committed_at": self.committed_at,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "revision_digest": self.revision_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SemanticGraphRevision":
        parsed = require_closed_mapping(
            "SemanticGraphRevision",
            data,
            required=frozenset(
                {
                    "schema_version", "graph_id", "graph_revision",
                    "graph_digest", "parent_revision", "parent_graph_digest",
                    "patch_digest", "registry_version", "registry_digest",
                    "active_node_record_digests", "active_relation_digests",
                    "committed_at", "revision_digest",
                }
            ),
            optional=frozenset(),
        )
        if parsed["schema_version"] != SEMANTIC_GRAPH_REVISION_SCHEMA_VERSION:
            raise ValueError("semantic graph revision schema mismatch")
        result = cls(
            graph_id=parsed["graph_id"],
            graph_revision=parsed["graph_revision"],
            graph_digest=parsed["graph_digest"],
            parent_revision=parsed["parent_revision"],
            parent_graph_digest=parsed["parent_graph_digest"],
            patch_digest=parsed["patch_digest"],
            registry_version=parsed["registry_version"],
            registry_digest=parsed["registry_digest"],
            active_node_record_digests=tuple(parsed["active_node_record_digests"]),
            active_relation_digests=tuple(parsed["active_relation_digests"]),
            committed_at=parsed["committed_at"],
        )
        if require_sha256("revision_digest", parsed["revision_digest"]) != result.revision_digest:
            raise SemanticGraphDigestMismatchError("semantic graph revision record mismatch")
        return result
