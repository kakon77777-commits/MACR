from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .._v07_contracts import (
    public_json_value,
    require_closed_mapping,
    require_sha256,
    require_string_tuple,
)
from .contracts import (
    ClaimStatus,
    ResolutionStatus,
    SemanticLifecycleStatus,
    SemanticNode,
    SemanticNodeType,
    SemanticStatus,
)
from .errors import (
    SemanticPatchInvalidError,
    SemanticStatusTransitionInvalidError,
)


@dataclass(frozen=True)
class ParsedStatusUpdate:
    node_id: str
    from_record_digest: str
    to_status: SemanticStatus
    reason_digest: str
    evidence_refs: tuple[str, ...]


def parse_semantic_status(
    node_type: SemanticNodeType,
    value: object,
) -> SemanticStatus:
    if not isinstance(value, str):
        raise SemanticStatusTransitionInvalidError(
            "semantic status must be text"
        )
    try:
        if node_type in {SemanticNodeType.CLAIM, SemanticNodeType.HYPOTHESIS}:
            return ClaimStatus(value)
        if node_type in {SemanticNodeType.AMBIGUITY, SemanticNodeType.OBLIGATION}:
            return ResolutionStatus(value)
        return SemanticLifecycleStatus(value)
    except ValueError as exc:
        raise SemanticStatusTransitionInvalidError(
            "semantic status does not match node type"
        ) from exc


def parse_status_update(
    update: Mapping[str, object],
    current: SemanticNode,
) -> ParsedStatusUpdate:
    parsed = require_closed_mapping(
        "semantic status update",
        public_json_value(update),
        required=frozenset(
            {
                "node_id",
                "from_record_digest",
                "to_status",
                "reason_digest",
                "evidence_refs",
            }
        ),
        optional=frozenset(),
    )
    if parsed["node_id"] != current.node_id:
        raise SemanticPatchInvalidError(
            "semantic status update node does not match"
        )
    old_digest = require_sha256(
        "from_record_digest",
        parsed["from_record_digest"],
    )
    if old_digest != current.record_digest:
        raise SemanticPatchInvalidError(
            "semantic status update base record is stale"
        )
    status = parse_semantic_status(current.node_type, parsed["to_status"])
    if status == current.status:
        raise SemanticStatusTransitionInvalidError(
            "semantic status update must change status"
        )
    evidence = require_string_tuple(
        "evidence_refs",
        parsed["evidence_refs"],
        maximum=128,
    )
    if (
        current.node_type in {SemanticNodeType.AMBIGUITY, SemanticNodeType.OBLIGATION}
        and status is ResolutionStatus.RESOLVED
        and not evidence
    ):
        raise SemanticPatchInvalidError(
            "semantic resolution requires evidence refs"
        )
    return ParsedStatusUpdate(
        node_id=current.node_id,
        from_record_digest=old_digest,
        to_status=status,
        reason_digest=require_sha256("reason_digest", parsed["reason_digest"]),
        evidence_refs=evidence,
    )
