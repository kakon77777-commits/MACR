from __future__ import annotations

from typing import ClassVar

from ..errors import MacrError


class SemanticStateError(MacrError):
    code: ClassVar[str] = "SEMANTIC_STATE_ERROR"


class SemanticSchemaUnsupportedError(SemanticStateError):
    code = "SEMANTIC_SCHEMA_UNSUPPORTED"


class SemanticRegistryUnknownError(SemanticStateError):
    code = "SEMANTIC_REGISTRY_UNKNOWN"


class SemanticRegistryMismatchError(SemanticStateError):
    code = "SEMANTIC_REGISTRY_MISMATCH"


class SemanticGraphNotFoundError(SemanticStateError):
    code = "SEMANTIC_GRAPH_NOT_FOUND"


class SemanticGraphAlreadyExistsError(SemanticStateError):
    code = "SEMANTIC_GRAPH_ALREADY_EXISTS"


class SemanticGraphHeadStaleError(SemanticStateError):
    code = "SEMANTIC_GRAPH_HEAD_STALE"


class SemanticGraphDigestMismatchError(SemanticStateError):
    code = "SEMANTIC_GRAPH_DIGEST_MISMATCH"


class SemanticPatchAlreadyExistsError(SemanticStateError):
    code = "SEMANTIC_PATCH_ALREADY_EXISTS"


class SemanticPatchConflictError(SemanticStateError):
    code = "SEMANTIC_PATCH_CONFLICT"


class SemanticPatchInvalidError(SemanticStateError):
    code = "SEMANTIC_PATCH_INVALID"


class SemanticNodeConflictError(SemanticStateError):
    code = "SEMANTIC_NODE_CONFLICT"


class SemanticRelationDanglingError(SemanticStateError):
    code = "SEMANTIC_RELATION_DANGLING"


class SemanticRelationDirectionInvalidError(SemanticStateError):
    code = "SEMANTIC_RELATION_DIRECTION_INVALID"


class SemanticStatusTransitionInvalidError(SemanticStateError):
    code = "SEMANTIC_STATUS_TRANSITION_INVALID"


class SemanticSupersessionInvalidError(SemanticStateError):
    code = "SEMANTIC_SUPERSESSION_INVALID"


class SemanticScopeEscalationError(SemanticStateError):
    code = "SEMANTIC_SCOPE_ESCALATION"


class SemanticCommitAuthorityInvalidError(SemanticStateError):
    code = "SEMANTIC_COMMIT_AUTHORITY_INVALID"


class SemanticCommitPermitInvalidError(SemanticStateError):
    code = "SEMANTIC_COMMIT_PERMIT_INVALID"


class SemanticAgentBindingConflictError(SemanticStateError):
    code = "SEMANTIC_AGENT_BINDING_CONFLICT"


class SemanticProjectionIncompleteError(SemanticStateError):
    code = "SEMANTIC_PROJECTION_INCOMPLETE"


class SemanticProjectionConflictError(SemanticStateError):
    code = "SEMANTIC_PROJECTION_CONFLICT"
