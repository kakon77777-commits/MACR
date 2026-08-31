from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .._v07_contracts import (
    canonical_record_digest,
    public_json_value,
    require_closed_mapping,
    require_non_negative_int,
    require_positive_int,
    require_sha256,
    require_uuid4,
)
from ..execution import AuthorizationReference
from .contracts import (
    SemanticNode,
    SemanticPatch,
    SemanticRelation,
)
from .errors import (
    SemanticGraphDigestMismatchError,
    SemanticGraphHeadStaleError,
    SemanticNodeConflictError,
    SemanticPatchInvalidError,
    SemanticRelationDanglingError,
    SemanticRelationDirectionInvalidError,
    SemanticRegistryMismatchError,
    SemanticScopeEscalationError,
    SemanticSupersessionInvalidError,
)
from .graph import SemanticGraphHead, calculate_graph_digest
from .registry import SemanticRegistry
from .validation import parse_status_update


SEMANTIC_PROPOSAL_SCHEMA_VERSION = "macr-semantic-patch-proposal/v1"
SEMANTIC_COMMIT_REQUEST_SCHEMA_VERSION = "macr-semantic-commit-request/v1"


def _authorization_dict(reference: AuthorizationReference) -> dict[str, object]:
    return {
        "source_kind": reference.source_kind,
        "source_id": reference.source_id,
        "digest": reference.digest,
        "revision": reference.revision,
        "epoch": reference.epoch,
        "scope": reference.scope,
    }


def _authorization_from_dict(value: object) -> AuthorizationReference:
    parsed = require_closed_mapping(
        "semantic commit authorization",
        value,
        required=frozenset(
            {"source_kind", "source_id", "digest", "revision", "epoch", "scope"}
        ),
        optional=frozenset(),
    )
    return AuthorizationReference(
        source_kind=parsed["source_kind"],
        source_id=parsed["source_id"],
        digest=parsed["digest"],
        revision=parsed["revision"],
        epoch=parsed["epoch"],
        scope=parsed["scope"],
    )


@dataclass(frozen=True)
class SemanticPatchProposalRequest:
    proposal_id: str
    graph_id: str
    agent_run_id: str
    base_graph_revision: int
    base_graph_digest: str
    registry_version: str
    registry_digest: str
    patch: SemanticPatch
    schema_version: str = field(
        init=False, default=SEMANTIC_PROPOSAL_SCHEMA_VERSION
    )
    proposal_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "proposal_id", require_uuid4("proposal_id", self.proposal_id)
        )
        object.__setattr__(self, "graph_id", require_uuid4("graph_id", self.graph_id))
        object.__setattr__(
            self,
            "agent_run_id",
            require_uuid4("agent_run_id", self.agent_run_id),
        )
        object.__setattr__(
            self,
            "base_graph_revision",
            require_positive_int("base_graph_revision", self.base_graph_revision),
        )
        object.__setattr__(
            self,
            "base_graph_digest",
            require_sha256("base_graph_digest", self.base_graph_digest),
        )
        if not isinstance(self.registry_version, str) or not self.registry_version.strip():
            raise ValueError("registry_version must be non-empty text")
        object.__setattr__(self, "registry_version", self.registry_version.strip())
        object.__setattr__(
            self,
            "registry_digest",
            require_sha256("registry_digest", self.registry_digest),
        )
        if not isinstance(self.patch, SemanticPatch):
            raise ValueError("patch must be a SemanticPatch")
        if self.patch.base_graph_digest != self.base_graph_digest:
            raise SemanticPatchInvalidError(
                "semantic patch base digest does not match proposal base"
            )
        object.__setattr__(
            self,
            "proposal_digest",
            canonical_record_digest(
                "macr.semantic.patch-proposal.v1",
                self._identity_dict(),
            ),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "graph_id": self.graph_id,
            "agent_run_id": self.agent_run_id,
            "base_graph_revision": self.base_graph_revision,
            "base_graph_digest": self.base_graph_digest,
            "registry_version": self.registry_version,
            "registry_digest": self.registry_digest,
            "patch": self.patch.to_public_dict(),
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "proposal_digest": self.proposal_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SemanticPatchProposalRequest":
        parsed = require_closed_mapping(
            "SemanticPatchProposalRequest",
            data,
            required=frozenset(
                {
                    "schema_version", "proposal_id", "graph_id", "agent_run_id",
                    "base_graph_revision", "base_graph_digest",
                    "registry_version", "registry_digest", "patch",
                    "proposal_digest",
                }
            ),
            optional=frozenset(),
        )
        if parsed["schema_version"] != SEMANTIC_PROPOSAL_SCHEMA_VERSION:
            raise ValueError("semantic proposal schema mismatch")
        result = cls(
            proposal_id=parsed["proposal_id"],
            graph_id=parsed["graph_id"],
            agent_run_id=parsed["agent_run_id"],
            base_graph_revision=parsed["base_graph_revision"],
            base_graph_digest=parsed["base_graph_digest"],
            registry_version=parsed["registry_version"],
            registry_digest=parsed["registry_digest"],
            patch=SemanticPatch.from_dict(parsed["patch"]),
        )
        supplied = require_sha256("proposal_digest", parsed["proposal_digest"])
        if result.proposal_digest != supplied:
            raise SemanticPatchInvalidError("semantic proposal digest mismatch")
        return result


@dataclass(frozen=True)
class SemanticCommitRequest:
    commit_id: str
    proposal_id: str
    proposal_digest: str
    graph_id: str
    agent_run_id: str
    base_graph_revision: int
    base_graph_digest: str
    registry_version: str
    registry_digest: str
    expected_agent_revision: int
    expected_agent_epoch: int
    ownership_permit_digest: str
    authorization_reference: AuthorizationReference
    patch: SemanticPatch
    schema_version: str = field(
        init=False, default=SEMANTIC_COMMIT_REQUEST_SCHEMA_VERSION
    )
    request_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "commit_id", require_uuid4("commit_id", self.commit_id))
        object.__setattr__(
            self, "proposal_id", require_uuid4("proposal_id", self.proposal_id)
        )
        object.__setattr__(
            self,
            "proposal_digest",
            require_sha256("proposal_digest", self.proposal_digest),
        )
        object.__setattr__(self, "graph_id", require_uuid4("graph_id", self.graph_id))
        object.__setattr__(
            self,
            "agent_run_id",
            require_uuid4("agent_run_id", self.agent_run_id),
        )
        object.__setattr__(
            self,
            "base_graph_revision",
            require_positive_int("base_graph_revision", self.base_graph_revision),
        )
        object.__setattr__(
            self,
            "base_graph_digest",
            require_sha256("base_graph_digest", self.base_graph_digest),
        )
        if not isinstance(self.registry_version, str) or not self.registry_version.strip():
            raise ValueError("registry_version must be non-empty text")
        object.__setattr__(self, "registry_version", self.registry_version.strip())
        object.__setattr__(
            self,
            "registry_digest",
            require_sha256("registry_digest", self.registry_digest),
        )
        object.__setattr__(
            self,
            "expected_agent_revision",
            require_positive_int(
                "expected_agent_revision", self.expected_agent_revision
            ),
        )
        object.__setattr__(
            self,
            "expected_agent_epoch",
            require_non_negative_int("expected_agent_epoch", self.expected_agent_epoch),
        )
        object.__setattr__(
            self,
            "ownership_permit_digest",
            require_sha256("ownership_permit_digest", self.ownership_permit_digest),
        )
        if not isinstance(self.authorization_reference, AuthorizationReference):
            raise ValueError("authorization_reference must be AuthorizationReference")
        if not isinstance(self.patch, SemanticPatch):
            raise ValueError("patch must be a SemanticPatch")
        proposal = SemanticPatchProposalRequest(
            proposal_id=self.proposal_id,
            graph_id=self.graph_id,
            agent_run_id=self.agent_run_id,
            base_graph_revision=self.base_graph_revision,
            base_graph_digest=self.base_graph_digest,
            registry_version=self.registry_version,
            registry_digest=self.registry_digest,
            patch=self.patch,
        )
        if proposal.proposal_digest != self.proposal_digest:
            raise SemanticPatchInvalidError(
                "semantic commit proposal binding mismatch"
            )
        object.__setattr__(
            self,
            "request_digest",
            canonical_record_digest(
                "macr.semantic.commit-request.v1",
                self._identity_dict(),
            ),
        )

    @classmethod
    def from_proposal(
        cls,
        *,
        commit_id: str,
        proposal: SemanticPatchProposalRequest,
        expected_agent_revision: int,
        expected_agent_epoch: int,
        ownership_permit_digest: str,
        authorization_reference: AuthorizationReference,
    ) -> "SemanticCommitRequest":
        if not isinstance(proposal, SemanticPatchProposalRequest):
            raise ValueError("proposal must be SemanticPatchProposalRequest")
        return cls(
            commit_id=commit_id,
            proposal_id=proposal.proposal_id,
            proposal_digest=proposal.proposal_digest,
            graph_id=proposal.graph_id,
            agent_run_id=proposal.agent_run_id,
            base_graph_revision=proposal.base_graph_revision,
            base_graph_digest=proposal.base_graph_digest,
            registry_version=proposal.registry_version,
            registry_digest=proposal.registry_digest,
            expected_agent_revision=expected_agent_revision,
            expected_agent_epoch=expected_agent_epoch,
            ownership_permit_digest=ownership_permit_digest,
            authorization_reference=authorization_reference,
            patch=proposal.patch,
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "commit_id": self.commit_id,
            "proposal_id": self.proposal_id,
            "proposal_digest": self.proposal_digest,
            "graph_id": self.graph_id,
            "agent_run_id": self.agent_run_id,
            "base_graph_revision": self.base_graph_revision,
            "base_graph_digest": self.base_graph_digest,
            "registry_version": self.registry_version,
            "registry_digest": self.registry_digest,
            "expected_agent_revision": self.expected_agent_revision,
            "expected_agent_epoch": self.expected_agent_epoch,
            "ownership_permit_digest": self.ownership_permit_digest,
            "authorization_reference": _authorization_dict(
                self.authorization_reference
            ),
            "patch": self.patch.to_public_dict(),
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "request_digest": self.request_digest}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SemanticCommitRequest":
        parsed = require_closed_mapping(
            "SemanticCommitRequest",
            data,
            required=frozenset(
                {
                    "schema_version", "commit_id", "proposal_id",
                    "proposal_digest", "graph_id", "agent_run_id",
                    "base_graph_revision", "base_graph_digest",
                    "registry_version", "registry_digest",
                    "expected_agent_revision", "expected_agent_epoch",
                    "ownership_permit_digest", "authorization_reference",
                    "patch", "request_digest",
                }
            ),
            optional=frozenset(),
        )
        if parsed["schema_version"] != SEMANTIC_COMMIT_REQUEST_SCHEMA_VERSION:
            raise ValueError("semantic commit request schema mismatch")
        result = cls(
            commit_id=parsed["commit_id"],
            proposal_id=parsed["proposal_id"],
            proposal_digest=parsed["proposal_digest"],
            graph_id=parsed["graph_id"],
            agent_run_id=parsed["agent_run_id"],
            base_graph_revision=parsed["base_graph_revision"],
            base_graph_digest=parsed["base_graph_digest"],
            registry_version=parsed["registry_version"],
            registry_digest=parsed["registry_digest"],
            expected_agent_revision=parsed["expected_agent_revision"],
            expected_agent_epoch=parsed["expected_agent_epoch"],
            ownership_permit_digest=parsed["ownership_permit_digest"],
            authorization_reference=_authorization_from_dict(
                parsed["authorization_reference"]
            ),
            patch=SemanticPatch.from_dict(parsed["patch"]),
        )
        supplied = require_sha256("request_digest", parsed["request_digest"])
        if result.request_digest != supplied:
            raise SemanticPatchInvalidError("semantic commit request digest mismatch")
        return result


@dataclass(frozen=True)
class CompiledSemanticPatch:
    proposal_digest: str
    graph_id: str
    base_graph_revision: int
    base_graph_digest: str
    next_graph_revision: int
    next_graph_digest: str
    registry_version: str
    registry_digest: str
    active_nodes: tuple[SemanticNode, ...]
    active_relations: tuple[SemanticRelation, ...]
    added_nodes: tuple[SemanticNode, ...]
    added_relations: tuple[SemanticRelation, ...]
    status_updates: tuple[SemanticNode, ...]
    historical_nodes: tuple[SemanticNode, ...]
    superseded_record_digests: tuple[str, ...]
    compiled_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "compiled_digest",
            canonical_record_digest(
                "macr.semantic.compiled-patch.v1",
                {
                    "proposal_digest": self.proposal_digest,
                    "graph_id": self.graph_id,
                    "base_graph_revision": self.base_graph_revision,
                    "base_graph_digest": self.base_graph_digest,
                    "next_graph_revision": self.next_graph_revision,
                    "next_graph_digest": self.next_graph_digest,
                    "registry_version": self.registry_version,
                    "registry_digest": self.registry_digest,
                    "active_node_digests": [
                        item.record_digest for item in self.active_nodes
                    ],
                    "active_relation_digests": [
                        item.relation_digest for item in self.active_relations
                    ],
                    "added_node_digests": [
                        item.record_digest for item in self.added_nodes
                    ],
                    "added_relation_digests": [
                        item.relation_digest for item in self.added_relations
                    ],
                    "status_update_digests": [
                        item.record_digest for item in self.status_updates
                    ],
                    "superseded_record_digests": list(
                        self.superseded_record_digests
                    ),
                },
            ),
        )


class SemanticPatchCompiler:
    def __init__(self, registry: SemanticRegistry) -> None:
        if not isinstance(registry, SemanticRegistry):
            raise ValueError("registry must be a SemanticRegistry")
        self.registry = registry

    def compile(
        self,
        *,
        head: SemanticGraphHead,
        proposal: SemanticPatchProposalRequest,
        active_nodes: Sequence[SemanticNode],
        active_relations: Sequence[SemanticRelation],
    ) -> CompiledSemanticPatch:
        if not isinstance(head, SemanticGraphHead):
            raise ValueError("head must be a SemanticGraphHead")
        if not isinstance(proposal, SemanticPatchProposalRequest):
            raise ValueError("proposal must be SemanticPatchProposalRequest")
        if proposal.graph_id != head.graph_id or (
            proposal.base_graph_revision != head.graph_revision
            or proposal.base_graph_digest != head.graph_digest
        ):
            raise SemanticGraphHeadStaleError("semantic graph head is stale")
        if (
            proposal.registry_version != head.registry_version
            or proposal.registry_digest != head.registry_digest
            or proposal.registry_version != self.registry.registry_version
            or proposal.registry_digest != self.registry.registry_digest
        ):
            raise SemanticRegistryMismatchError("semantic registry binding mismatch")

        nodes = tuple(active_nodes)
        relations = tuple(active_relations)
        if any(not isinstance(item, SemanticNode) for item in nodes):
            raise ValueError("active_nodes contains invalid record")
        if any(not isinstance(item, SemanticRelation) for item in relations):
            raise ValueError("active_relations contains invalid record")
        if {item.record_digest for item in nodes} != set(
            head.active_node_record_digests
        ) or {item.relation_digest for item in relations} != set(
            head.active_relation_digests
        ):
            raise SemanticGraphDigestMismatchError(
                "active records do not match semantic graph head"
            )
        node_map = {item.node_id: item for item in nodes}
        if len(node_map) != len(nodes):
            raise SemanticNodeConflictError("active graph has duplicate node ID")
        relation_map = {item.relation_id: item for item in relations}
        if len(relation_map) != len(relations):
            raise SemanticPatchInvalidError(
                "active graph has duplicate relation ID"
            )
        consumed: set[str] = set()
        historical: list[SemanticNode] = []
        added_nodes: list[SemanticNode] = []

        supersession = set()
        for reference in proposal.patch.supersession_refs:
            try:
                supersession.add(require_sha256("supersession_ref", reference))
            except ValueError as exc:
                raise SemanticSupersessionInvalidError(
                    "semantic supersession reference is invalid"
                ) from exc

        for node in proposal.patch.add_nodes:
            self._validate_node(node, head)
            old = node_map.get(node.node_id)
            if old is not None:
                if old.record_digest not in supersession:
                    raise SemanticNodeConflictError(
                        "semantic node overwrite requires supersession"
                    )
                consumed.add(old.record_digest)
                historical.append(old)
            node_map[node.node_id] = node
            added_nodes.append(node)

        status_nodes: list[SemanticNode] = []
        for raw_update in proposal.patch.status_updates:
            if not isinstance(raw_update, Mapping):
                raise SemanticPatchInvalidError(
                    "semantic status update must be an object"
                )
            node_id = raw_update.get("node_id")
            old = node_map.get(node_id)
            if old is None:
                raise SemanticPatchInvalidError(
                    "semantic status update node is missing"
                )
            parsed = parse_status_update(raw_update, old)
            if old.record_digest not in supersession:
                raise SemanticSupersessionInvalidError(
                    "semantic status update requires supersession"
                )
            consumed.add(old.record_digest)
            replacement = SemanticNode(
                node_id=old.node_id,
                node_type=old.node_type,
                payload=public_json_value(old.payload),
                scope_ref=old.scope_ref,
                status=parsed.to_status,
                effects=old.effects,
                constraints=old.constraints,
                policy=public_json_value(old.policy),
                provenance=old.provenance,
                temporal=public_json_value(old.temporal),
                external_bindings=old.external_bindings,
            )
            historical.append(old)
            status_nodes.append(replacement)
            added_nodes.append(replacement)
            node_map[old.node_id] = replacement

        if consumed != supersession:
            raise SemanticSupersessionInvalidError(
                "semantic supersession references were not consumed exactly"
            )

        for relation in proposal.patch.add_relations:
            if relation.relation_id in relation_map:
                raise SemanticPatchInvalidError(
                    "semantic relation overwrite is not allowed"
                )
            source = node_map.get(relation.source_ref)
            target = node_map.get(relation.target_ref)
            if source is None or target is None:
                raise SemanticRelationDanglingError(
                    "semantic relation endpoint is missing"
                )
            try:
                self.registry.require_relation(
                    source.node_type,
                    relation.relation_type,
                    target.node_type,
                )
            except SemanticRegistryMismatchError as exc:
                raise SemanticRelationDirectionInvalidError(
                    "semantic relation direction is invalid"
                ) from exc
            relation_map[relation.relation_id] = relation

        for relation in relation_map.values():
            if relation.source_ref not in node_map or relation.target_ref not in node_map:
                raise SemanticRelationDanglingError(
                    "active semantic relation became dangling"
                )

        active_node_tuple = tuple(sorted(node_map.values(), key=lambda item: item.record_digest))
        active_relation_tuple = tuple(
            sorted(relation_map.values(), key=lambda item: item.relation_digest)
        )
        next_digest = calculate_graph_digest(
            registry_version=head.registry_version,
            registry_digest=head.registry_digest,
            active_node_record_digests=tuple(
                item.record_digest for item in active_node_tuple
            ),
            active_relation_digests=tuple(
                item.relation_digest for item in active_relation_tuple
            ),
        )
        return CompiledSemanticPatch(
            proposal_digest=proposal.proposal_digest,
            graph_id=head.graph_id,
            base_graph_revision=head.graph_revision,
            base_graph_digest=head.graph_digest,
            next_graph_revision=head.graph_revision + 1,
            next_graph_digest=next_digest,
            registry_version=head.registry_version,
            registry_digest=head.registry_digest,
            active_nodes=active_node_tuple,
            active_relations=active_relation_tuple,
            added_nodes=tuple(
                sorted(added_nodes, key=lambda item: item.record_digest)
            ),
            added_relations=proposal.patch.add_relations,
            status_updates=tuple(
                sorted(status_nodes, key=lambda item: item.record_digest)
            ),
            historical_nodes=tuple(
                sorted(
                    {item.record_digest: item for item in historical}.values(),
                    key=lambda item: item.record_digest,
                )
            ),
            superseded_record_digests=tuple(sorted(consumed)),
        )

    def _validate_node(
        self,
        node: SemanticNode,
        head: SemanticGraphHead,
    ) -> None:
        self.registry.require_node_type(node.node_type)
        self.registry.require_status(node.status)
        for effect in node.effects:
            try:
                self.registry.require_effect(effect)
            except Exception as exc:
                raise SemanticPatchInvalidError(
                    "semantic node contains unknown effect"
                ) from exc
        if node.scope_ref != head.scope_ref:
            raise SemanticScopeEscalationError(
                "semantic node scope exceeds graph scope"
            )
