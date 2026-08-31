from __future__ import annotations

from typing import ClassVar

from ..errors import MacrError


class AgentStateKernelError(MacrError):
    """Base class for sanitized Phase B Agent state failures."""

    code: ClassVar[str] = "AGENT_STATE_KERNEL_ERROR"


class AgentRunAlreadyExistsError(AgentStateKernelError):
    code = "AGENT_RUN_ALREADY_EXISTS"


class AgentRunNotFoundError(AgentStateKernelError):
    code = "AGENT_RUN_NOT_FOUND"


class IllegalAgentRunTransitionError(AgentStateKernelError):
    code = "ILLEGAL_AGENT_RUN_TRANSITION"


class StaleAgentRunRevisionError(AgentStateKernelError):
    code = "STALE_AGENT_RUN_REVISION"


class StaleAgentRunEpochError(AgentStateKernelError):
    code = "STALE_AGENT_RUN_EPOCH"


class AgentOwnershipConflictError(AgentStateKernelError):
    code = "AGENT_OWNERSHIP_CONFLICT"


class AgentLeaseExpiredError(AgentStateKernelError):
    code = "AGENT_LEASE_EXPIRED"


class StaleAgentFencingTokenError(AgentStateKernelError):
    code = "STALE_AGENT_FENCING_TOKEN"


class AgentEventIntegrityError(AgentStateKernelError):
    code = "AGENT_EVENT_INTEGRITY_ERROR"


class AgentProjectionConflictError(AgentStateKernelError):
    code = "AGENT_PROJECTION_CONFLICT"


class AgentRebuildBlockedError(AgentStateKernelError):
    code = "AGENT_REBUILD_BLOCKED"
