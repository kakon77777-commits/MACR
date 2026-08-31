from __future__ import annotations

import unittest

from macr_runtime.agent.contracts import AgentRunState
from macr_runtime.agent.errors import (
    AgentEventIntegrityError,
    AgentLeaseExpiredError,
    AgentOwnershipConflictError,
    AgentProjectionConflictError,
    AgentRebuildBlockedError,
    AgentRunAlreadyExistsError,
    AgentRunNotFoundError,
    IllegalAgentRunTransitionError,
    StaleAgentFencingTokenError,
    StaleAgentRunEpochError,
    StaleAgentRunRevisionError,
)
from macr_runtime.agent.lifecycle import (
    PHASE_B_TRANSITIONS,
    require_phase_b_transition,
)
from macr_runtime.errors import MacrError


class AgentLifecycleTests(unittest.TestCase):
    def test_phase_b_transition_table_is_exact(self) -> None:
        observed = {
            (source, target)
            for source, targets in PHASE_B_TRANSITIONS.items()
            for target in targets
        }
        expected = {
            (AgentRunState.CREATED, AgentRunState.ADMITTED),
            (AgentRunState.CREATED, AgentRunState.CANCELLED),
            (AgentRunState.ADMITTED, AgentRunState.ACTIVE),
            (AgentRunState.ADMITTED, AgentRunState.FAILED),
            (AgentRunState.ADMITTED, AgentRunState.CANCELLED),
            (AgentRunState.ACTIVE, AgentRunState.BLOCKED),
            (AgentRunState.ACTIVE, AgentRunState.COMPLETED),
            (AgentRunState.ACTIVE, AgentRunState.FAILED),
            (AgentRunState.ACTIVE, AgentRunState.CANCELLED),
            (AgentRunState.BLOCKED, AgentRunState.ACTIVE),
            (AgentRunState.BLOCKED, AgentRunState.FAILED),
            (AgentRunState.BLOCKED, AgentRunState.CANCELLED),
        }

        self.assertEqual(observed, expected)

    def test_legal_transition_returns_exact_target(self) -> None:
        self.assertIs(
            require_phase_b_transition(
                AgentRunState.CREATED,
                AgentRunState.ADMITTED,
            ),
            AgentRunState.ADMITTED,
        )
        self.assertIs(
            require_phase_b_transition(
                AgentRunState.BLOCKED,
                AgentRunState.ACTIVE,
            ),
            AgentRunState.ACTIVE,
        )

    def test_illegal_and_terminal_reopen_transitions_fail_closed(self) -> None:
        cases = (
            (AgentRunState.CREATED, AgentRunState.ACTIVE),
            (AgentRunState.COMPLETED, AgentRunState.ACTIVE),
            (AgentRunState.FAILED, AgentRunState.ACTIVE),
            (AgentRunState.CANCELLED, AgentRunState.ACTIVE),
            (AgentRunState.ACTIVE, AgentRunState.SUSPENDED),
        )

        for source, target in cases:
            with self.subTest(source=source.value, target=target.value):
                with self.assertRaisesRegex(
                    IllegalAgentRunTransitionError,
                    f"{source.value}.*{target.value}",
                ) as caught:
                    require_phase_b_transition(source, target)
                self.assertEqual(caught.exception.code, "ILLEGAL_AGENT_RUN_TRANSITION")

    def test_transition_rejects_non_enum_arguments(self) -> None:
        with self.assertRaisesRegex(ValueError, "AgentRunState"):
            require_phase_b_transition("created", AgentRunState.ADMITTED)  # type: ignore[arg-type]

    def test_phase_b_errors_have_stable_codes_and_root(self) -> None:
        expected = {
            AgentRunAlreadyExistsError: "AGENT_RUN_ALREADY_EXISTS",
            AgentRunNotFoundError: "AGENT_RUN_NOT_FOUND",
            IllegalAgentRunTransitionError: "ILLEGAL_AGENT_RUN_TRANSITION",
            StaleAgentRunRevisionError: "STALE_AGENT_RUN_REVISION",
            StaleAgentRunEpochError: "STALE_AGENT_RUN_EPOCH",
            AgentOwnershipConflictError: "AGENT_OWNERSHIP_CONFLICT",
            AgentLeaseExpiredError: "AGENT_LEASE_EXPIRED",
            StaleAgentFencingTokenError: "STALE_AGENT_FENCING_TOKEN",
            AgentEventIntegrityError: "AGENT_EVENT_INTEGRITY_ERROR",
            AgentProjectionConflictError: "AGENT_PROJECTION_CONFLICT",
            AgentRebuildBlockedError: "AGENT_REBUILD_BLOCKED",
        }

        for error_type, code in expected.items():
            with self.subTest(error_type=error_type.__name__):
                error = error_type("sanitized")
                self.assertIsInstance(error, MacrError)
                self.assertEqual(error.code, code)
                self.assertEqual(str(error), "sanitized")


if __name__ == "__main__":
    unittest.main()
