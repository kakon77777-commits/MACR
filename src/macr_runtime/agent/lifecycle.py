from __future__ import annotations

from types import MappingProxyType

from .contracts import AgentRunState
from .errors import IllegalAgentRunTransitionError


PHASE_B_TRANSITIONS = MappingProxyType(
    {
        AgentRunState.CREATED: frozenset(
            {
                AgentRunState.ADMITTED,
                AgentRunState.CANCELLED,
            }
        ),
        AgentRunState.ADMITTED: frozenset(
            {
                AgentRunState.ACTIVE,
                AgentRunState.FAILED,
                AgentRunState.CANCELLED,
            }
        ),
        AgentRunState.ACTIVE: frozenset(
            {
                AgentRunState.BLOCKED,
                AgentRunState.COMPLETED,
                AgentRunState.FAILED,
                AgentRunState.CANCELLED,
            }
        ),
        AgentRunState.BLOCKED: frozenset(
            {
                AgentRunState.ACTIVE,
                AgentRunState.FAILED,
                AgentRunState.CANCELLED,
            }
        ),
    }
)


def require_phase_b_transition(
    source: AgentRunState,
    target: AgentRunState,
) -> AgentRunState:
    if not isinstance(source, AgentRunState) or not isinstance(target, AgentRunState):
        raise ValueError("source and target must be AgentRunState values")
    if target not in PHASE_B_TRANSITIONS.get(source, frozenset()):
        raise IllegalAgentRunTransitionError(
            f"AgentRun transition {source.value} -> {target.value} is not allowed"
        )
    return target
