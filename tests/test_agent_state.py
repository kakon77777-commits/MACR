from __future__ import annotations

import json
import unittest

from macr_runtime.agent.contracts import (
    AGENT_RUN_SCHEMA_VERSION,
    AgentRunHeader,
    AgentRunIdentity,
    AgentRunState,
    AuthorityBinding,
    BudgetBinding,
    GoalBinding,
    agent_run_subject_digest,
)
from macr_runtime.agent.state import (
    AGENT_PROJECTION_SCHEMA_VERSION,
    AgentRunProjection,
)
from macr_runtime.execution import AuthorizationReference, DispatchOrigin


RUN_ID = "11111111-1111-4111-8111-111111111111"


def make_header(**overrides: object) -> AgentRunHeader:
    origin = DispatchOrigin("codex", "task", "task:phase-b-fixture")
    goal = GoalBinding("goal:phase-b", "b" * 64, 1)
    authority = AuthorityBinding(
        AuthorizationReference(
            source_kind="host_operator",
            source_id="authority:phase-b",
            digest="a" * 64,
            revision=1,
            epoch=0,
            scope="agent:phase-b",
        )
    )
    budget = BudgetBinding("budget:phase-b", "c" * 64, 1)
    identity = AgentRunIdentity(
        agent_run_id=RUN_ID,
        subject_digest=agent_run_subject_digest(
            agent_ref="agent:phase-b",
            origin=origin,
            goal=goal,
            authority=authority,
            budget=budget,
            world_bindings=(),
            memory_bindings=(),
        ),
    )
    values: dict[str, object] = {
        "schema_version": AGENT_RUN_SCHEMA_VERSION,
        "identity": identity,
        "agent_ref": "agent:phase-b",
        "origin": origin,
        "state": AgentRunState.CREATED,
        "state_revision": 1,
        "epoch": 0,
        "goal": goal,
        "authority": authority,
        "budget": budget,
        "semantic_state": None,
        "active_plan": None,
        "world_bindings": (),
        "memory_bindings": (),
        "parent_agent_run_id": None,
        "delegation_ref": None,
        "created_at": "2026-08-31T08:00:00+08:00",
    }
    values.update(overrides)
    return AgentRunHeader(**values)


class AgentStateTests(unittest.TestCase):
    def test_creation_projection_is_exact_and_digest_bound(self) -> None:
        projection = AgentRunProjection.from_creation_header(make_header())

        self.assertEqual(projection.schema_version, AGENT_PROJECTION_SCHEMA_VERSION)
        self.assertEqual(projection.state, AgentRunState.CREATED)
        self.assertEqual(projection.state_revision, 1)
        self.assertEqual(projection.epoch, 0)
        self.assertEqual(projection.updated_at, "2026-08-31T00:00:00+00:00")
        self.assertRegex(projection.state_digest, r"^[0-9a-f]{64}$")
        self.assertEqual(projection.initial_header, make_header())

    def test_creation_guard_rejects_each_phase_a_valid_noninitial_header(self) -> None:
        cases = (
            make_header(state=AgentRunState.ACTIVE),
            make_header(state_revision=2),
            make_header(epoch=1),
        )

        for header in cases:
            with self.subTest(
                state=header.state.value,
                revision=header.state_revision,
                epoch=header.epoch,
            ):
                with self.assertRaisesRegex(ValueError, "CREATED/revision 1/epoch 0"):
                    AgentRunProjection.from_creation_header(header)

    def test_updated_at_is_not_part_of_state_identity(self) -> None:
        header = make_header()
        first = AgentRunProjection.from_creation_header(
            header,
            updated_at="2026-08-31T00:00:01+00:00",
        )
        second = AgentRunProjection.from_creation_header(
            header,
            updated_at="2026-08-31T00:00:02+00:00",
        )

        self.assertNotEqual(first.updated_at, second.updated_at)
        self.assertEqual(first.state_digest, second.state_digest)

    def test_state_revision_and_epoch_each_change_state_identity(self) -> None:
        header = make_header()
        baseline = AgentRunProjection.from_creation_header(header)
        changed_state = AgentRunProjection(
            initial_header=header,
            state=AgentRunState.ADMITTED,
            state_revision=1,
            epoch=0,
            updated_at=header.created_at,
        )
        changed_revision = AgentRunProjection(
            initial_header=header,
            state=AgentRunState.CREATED,
            state_revision=2,
            epoch=0,
            updated_at=header.created_at,
        )
        changed_epoch = AgentRunProjection(
            initial_header=header,
            state=AgentRunState.CREATED,
            state_revision=1,
            epoch=1,
            updated_at=header.created_at,
        )

        self.assertNotEqual(baseline.state_digest, changed_state.state_digest)
        self.assertNotEqual(baseline.state_digest, changed_revision.state_digest)
        self.assertNotEqual(baseline.state_digest, changed_epoch.state_digest)

    def test_public_round_trip_is_closed_and_content_free(self) -> None:
        projection = AgentRunProjection.from_creation_header(make_header())
        public = projection.to_public_dict()

        self.assertEqual(AgentRunProjection.from_dict(public), projection)
        serialized = json.dumps(public, sort_keys=True)
        for forbidden in ("prompt", "answer", "api_key", "memory_content"):
            self.assertNotIn(forbidden, serialized)

        with self.assertRaisesRegex(ValueError, "unknown fields"):
            AgentRunProjection.from_dict({**public, "extra": "forbidden"})

    def test_projection_is_immutable(self) -> None:
        projection = AgentRunProjection.from_creation_header(make_header())

        with self.assertRaises(AttributeError):
            projection.epoch = 9  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
