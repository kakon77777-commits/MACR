"""MACR v0.7 Agent contract family."""

from .contracts import (
    AGENT_RUN_SCHEMA_VERSION,
    AgentRunHeader,
    AgentRunIdentity,
    AgentRunState,
    AuthorityBinding,
    BudgetBinding,
    GoalBinding,
    MemoryBindingRef,
    PlanBinding,
    SemanticStateBinding,
    WorldBindingRef,
    agent_run_subject_digest,
    is_terminal_agent_run_state,
)
from .database import AgentDatabase
from .events import (
    AGENT_EVENT_SCHEMA_VERSION,
    AgentEventType,
    AgentStateEvent,
    apply_agent_event,
    replay_agent_events,
)
from .lifecycle import PHASE_B_TRANSITIONS, require_phase_b_transition
from .ownership import AgentOwnershipPermit, AgentOwnershipStore
from .service import AgentStateService
from .state import (
    AGENT_PROJECTION_SCHEMA_VERSION,
    AgentRunProjection,
)
from .store import (
    AgentEventRecord,
    AgentStore,
    ProjectionInspection,
    ProjectionInspectionStatus,
)

__all__ = [
    "AGENT_RUN_SCHEMA_VERSION",
    "AGENT_EVENT_SCHEMA_VERSION",
    "AGENT_PROJECTION_SCHEMA_VERSION",
    "AgentDatabase",
    "AgentEventRecord",
    "AgentEventType",
    "AgentOwnershipPermit",
    "AgentOwnershipStore",
    "AgentRunProjection",
    "AgentRunHeader",
    "AgentRunIdentity",
    "AgentRunState",
    "AgentStateEvent",
    "AgentStateService",
    "AgentStore",
    "AuthorityBinding",
    "BudgetBinding",
    "GoalBinding",
    "MemoryBindingRef",
    "PlanBinding",
    "PHASE_B_TRANSITIONS",
    "ProjectionInspection",
    "ProjectionInspectionStatus",
    "SemanticStateBinding",
    "WorldBindingRef",
    "agent_run_subject_digest",
    "apply_agent_event",
    "is_terminal_agent_run_state",
    "replay_agent_events",
    "require_phase_b_transition",
]
