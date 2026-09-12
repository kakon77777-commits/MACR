from ...errors import MacrError


class HostedAgentCellError(MacrError):
    """Hosted Agent Cell cannot safely continue."""


class HostedAgentCellPolicyError(HostedAgentCellError):
    """A cell policy, provider, tool, or scope is not authorized."""


class HostedAgentCellStateError(HostedAgentCellError):
    """Persisted cell or AgentRun state violates an invariant."""


class HostedAgentCellBudgetError(HostedAgentCellError):
    """A finite cell budget is exhausted before the next operation."""


class HostedAgentContextError(HostedAgentCellError):
    """Provider-ready context cannot be built or reconstructed exactly."""


class HostedToolDeniedError(HostedAgentCellError):
    """A model-proposed tool call was denied before execution."""


class HostedModelProtocolError(HostedAgentCellError):
    """A model decision is malformed or violates the closed grammar."""


class HostedAgentReconciliationRequired(HostedAgentCellError):
    """A preallocated model/tool operation lacks terminal evidence."""


class HostedAgentCheckpointError(HostedAgentCellError):
    """A cell checkpoint cannot be trusted for rehydration."""
