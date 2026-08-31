from __future__ import annotations

import argparse
import json
from datetime import datetime

from macr_runtime.agent import (
    AGENT_RUN_SCHEMA_VERSION,
    AgentDatabase,
    AgentRunHeader,
    AgentRunIdentity,
    AgentRunState,
    AgentStateService,
    AgentStore,
    AuthorityBinding,
    BudgetBinding,
    GoalBinding,
    ProjectionInspectionStatus,
    agent_run_subject_digest,
)
from macr_runtime.canonical import canonical_json_bytes, sha256_id
from macr_runtime.execution import AuthorizationReference, DispatchOrigin


RUN_ID = "11111111-1111-4111-8111-111111111111"


class FixedClock:
    def __init__(self, value: str) -> None:
        self.value = datetime.fromisoformat(value)

    def __call__(self) -> datetime:
        return self.value


def make_header() -> AgentRunHeader:
    origin = DispatchOrigin("structural-smoke", "run", "phase-b-replay")
    goal = GoalBinding("goal:structural-smoke", "b" * 64, 1)
    authority = AuthorityBinding(
        AuthorizationReference(
            source_kind="host_test",
            source_id="authority:structural-smoke",
            digest="a" * 64,
            revision=1,
            epoch=0,
            scope="agent:structural-smoke",
        )
    )
    budget = BudgetBinding("budget:structural-smoke", "c" * 64, 1)
    identity = AgentRunIdentity(
        RUN_ID,
        agent_run_subject_digest(
            agent_ref="agent:structural-smoke",
            origin=origin,
            goal=goal,
            authority=authority,
            budget=budget,
            world_bindings=(),
            memory_bindings=(),
        ),
    )
    return AgentRunHeader(
        schema_version=AGENT_RUN_SCHEMA_VERSION,
        identity=identity,
        agent_ref="agent:structural-smoke",
        origin=origin,
        state=AgentRunState.CREATED,
        state_revision=1,
        epoch=0,
        goal=goal,
        authority=authority,
        budget=budget,
        semantic_state=None,
        active_plan=None,
        world_bindings=(),
        memory_bindings=(),
        parent_agent_run_id=None,
        delegation_ref=None,
        created_at="2026-08-31T00:00:00+00:00",
    )


def run(database_path: str) -> dict[str, object]:
    clock = FixedClock("2026-08-31T01:00:00+00:00")
    service = AgentStateService(AgentStore(database_path), now=clock)
    service.create_agent_run(
        make_header(),
        event_id="10000000-0000-4000-8000-000000000001",
    )
    service.admit_agent_run(
        RUN_ID,
        expected_revision=1,
        expected_epoch=0,
        reason_code="INITIAL_ADMISSION",
        reason_digest="d" * 64,
        event_id="10000000-0000-4000-8000-000000000002",
    )
    permit = service.ownership.acquire(
        RUN_ID,
        "owner:structural-smoke",
        expected_revision=2,
        expected_epoch=0,
        ttl_seconds=300,
        event_id="10000000-0000-4000-8000-000000000003",
        lease_id="20000000-0000-4000-8000-000000000001",
    )
    service.activate_agent_run(
        permit,
        expected_revision=3,
        expected_epoch=1,
        reason_code="OWNER_READY",
        reason_digest="e" * 64,
        event_id="10000000-0000-4000-8000-000000000004",
    )
    service.block_agent_run(
        permit,
        expected_revision=4,
        expected_epoch=1,
        reason_code="DEPENDENCY_UNAVAILABLE",
        reason_digest="f" * 64,
        event_id="10000000-0000-4000-8000-000000000005",
    )
    service.activate_agent_run(
        permit,
        expected_revision=5,
        expected_epoch=1,
        reason_code="DEPENDENCY_READY",
        reason_digest="1" * 64,
        event_id="10000000-0000-4000-8000-000000000006",
    )
    completed = service.complete_agent_run(
        permit,
        expected_revision=6,
        expected_epoch=1,
        evidence_ref="evidence:structural-smoke",
        evidence_digest="2" * 64,
        event_id="10000000-0000-4000-8000-000000000007",
    )
    before = canonical_json_bytes(completed.to_public_dict())
    before_inspection = service.store.inspect_projection(RUN_ID)
    events = service.list_agent_events(RUN_ID)
    event_ids = [record.event.event_id for record in events]

    connection = service.store.database.connect()
    try:
        connection.execute(
            "DELETE FROM agent_runs WHERE agent_run_id = ?",
            (RUN_ID,),
        )
    finally:
        connection.close()
    missing = service.store.inspect_projection(RUN_ID)
    rebuilt = service.store.rebuild_projection(
        RUN_ID,
        observed_at="2026-08-31T02:00:00+00:00",
    )
    after = canonical_json_bytes(rebuilt.to_public_dict())
    after_inspection = service.store.inspect_projection(RUN_ID)
    ownership = service.get_agent_ownership(RUN_ID)

    if before_inspection.status is not ProjectionInspectionStatus.EXACT_MATCH:
        raise RuntimeError("pre-rebuild projection was not exact")
    if missing.status is not ProjectionInspectionStatus.MISSING:
        raise RuntimeError("projection deletion was not observed")
    if after_inspection.status is not ProjectionInspectionStatus.EXACT_MATCH:
        raise RuntimeError("rebuilt projection was not exact")
    if before != after or completed.state_digest != rebuilt.state_digest:
        raise RuntimeError("rebuild equivalence failed")
    if ownership is not None:
        raise RuntimeError("terminal AgentRun retained ownership")

    replay_digest = sha256_id(
        "macr.agent.structural-replay.v1",
        {
            "projection": rebuilt.to_public_dict(),
            "event_ids": event_ids,
        },
    )
    return {
        "schema": "macr-v07-phase-b-structural-replay/v1",
        "agent_schema_version": AgentDatabase.SCHEMA_VERSION,
        "final_state": rebuilt.state.value,
        "state_revision": rebuilt.state_revision,
        "epoch": rebuilt.epoch,
        "state_digest": rebuilt.state_digest,
        "event_count": len(events),
        "event_ids": event_ids,
        "replay_digest": replay_digest,
        "reconstruction_equivalent": True,
        "network_activity": False,
        "provider_generation": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.database), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
