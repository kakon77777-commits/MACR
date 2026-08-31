from __future__ import annotations

import argparse
import json
from datetime import datetime

from macr_runtime.agent import (
    AGENT_RUN_SCHEMA_VERSION,
    AgentDatabase,
    AgentEventType,
    AgentRunHeader,
    AgentRunIdentity,
    AgentRunState,
    AgentStateService,
    AgentStore,
    AuthorityBinding,
    BudgetBinding,
    GoalBinding,
    agent_run_subject_digest,
)
from macr_runtime.canonical import canonical_json_bytes, sha256_id
from macr_runtime.execution import AuthorizationReference, DispatchOrigin
from macr_runtime.semantic import (
    SemanticCommitRequest,
    SemanticCommitService,
    SemanticContextProjector,
    SemanticContextRequest,
    SemanticLifecycleStatus,
    SemanticNode,
    SemanticNodeType,
    SemanticPatch,
    SemanticPatchProposalRequest,
    SemanticProjectionProfile,
    SemanticProposalService,
    SemanticProvenance,
    SemanticRelation,
    SemanticRelationType,
    SemanticStore,
    ownership_permit_digest,
)


RUN_ID = "11111111-1111-4111-8111-111111111111"
GRAPH_ID = "44444444-4444-4444-8444-444444444444"


class FixedClock:
    def __init__(self, value: str) -> None:
        self.value = datetime.fromisoformat(value)

    def __call__(self) -> datetime:
        return self.value


def make_header() -> AgentRunHeader:
    origin = DispatchOrigin("structural-smoke", "run", "phase-c-replay")
    goal = GoalBinding("goal:phase-c-replay", "b" * 64, 1)
    authority = AuthorityBinding(
        AuthorizationReference(
            source_kind="host_test",
            source_id="authority:phase-c-replay",
            digest="a" * 64,
            revision=1,
            epoch=0,
            scope="agent:phase-c-replay",
        )
    )
    budget = BudgetBinding("budget:phase-c-replay", "c" * 64, 1)
    identity = AgentRunIdentity(
        RUN_ID,
        agent_run_subject_digest(
            agent_ref="agent:phase-c-replay",
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
        agent_ref="agent:phase-c-replay",
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
        created_at="2026-09-01T00:00:00+00:00",
    )


def make_patch(base_graph_digest: str) -> SemanticPatch:
    provenance = SemanticProvenance(
        origin_kind="structural_smoke",
        origin_ref="smoke:phase-c",
        source_refs=("source:phase-c-smoke",),
        agent_run_id=RUN_ID,
        created_by_ref="host:structural-smoke",
        created_at="2026-09-01T01:00:00+00:00",
    )
    goal = SemanticNode(
        node_id="goal:one",
        node_type=SemanticNodeType.GOAL,
        payload={"label": "Goal"},
        scope_ref="project:phase-c",
        status=SemanticLifecycleStatus.ACTIVE,
        effects=(),
        constraints=(),
        policy={},
        provenance=provenance,
        temporal={},
        external_bindings=(),
    )
    plan = SemanticNode(
        node_id="plan:one",
        node_type=SemanticNodeType.PLAN,
        payload={"label": "Plan"},
        scope_ref="project:phase-c",
        status=SemanticLifecycleStatus.ACTIVE,
        effects=(),
        constraints=(),
        policy={},
        provenance=provenance,
        temporal={},
        external_bindings=(),
    )
    relation = SemanticRelation(
        relation_id="relation:goal-plan",
        source_ref=goal.node_id,
        relation_type=SemanticRelationType.MOTIVATES,
        target_ref=plan.node_id,
        qualifiers={},
        provenance=provenance,
    )
    return SemanticPatch(
        patch_id="patch:goal-plan",
        base_graph_digest=base_graph_digest,
        add_nodes=(plan, goal),
        add_relations=(relation,),
        status_updates=(),
        supersession_refs=(),
        producer_ref="candidate:structural-smoke",
    )


def run(database_path: str) -> dict[str, object]:
    clock = FixedClock("2026-09-01T01:00:00+00:00")
    agent_store = AgentStore(database_path)
    agent = AgentStateService(agent_store, now=clock)
    header = make_header()
    agent.create_agent_run(
        header, event_id="10000000-0000-4000-8000-000000000001"
    )
    agent.admit_agent_run(
        RUN_ID,
        expected_revision=1,
        expected_epoch=0,
        reason_code="INITIAL_ADMISSION",
        reason_digest="d" * 64,
        event_id="10000000-0000-4000-8000-000000000002",
    )
    permit = agent.ownership.acquire(
        RUN_ID,
        "owner:phase-c-replay",
        expected_revision=2,
        expected_epoch=0,
        ttl_seconds=300,
        event_id="10000000-0000-4000-8000-000000000003",
        lease_id="20000000-0000-4000-8000-000000000001",
    )
    agent.activate_agent_run(
        permit,
        expected_revision=3,
        expected_epoch=1,
        reason_code="SEMANTIC_READY",
        reason_digest="e" * 64,
        event_id="10000000-0000-4000-8000-000000000004",
    )
    semantic = SemanticStore(AgentDatabase(database_path))
    initial = semantic.create_graph(
        graph_id=GRAPH_ID,
        scope_ref="project:phase-c",
        created_by_agent_run_id=RUN_ID,
        created_at="2026-09-01T01:00:00+00:00",
    )
    proposal_request = SemanticPatchProposalRequest(
        proposal_id="30000000-0000-4000-8000-000000000001",
        graph_id=GRAPH_ID,
        agent_run_id=RUN_ID,
        base_graph_revision=1,
        base_graph_digest=initial.graph_digest,
        registry_version=semantic.registry.registry_version,
        registry_digest=semantic.registry.registry_digest,
        patch=make_patch(initial.graph_digest),
    )
    proposal = SemanticProposalService(semantic).propose_patch(
        proposal_request,
        created_at="2026-09-01T01:00:00+00:00",
    )
    commits = SemanticCommitService(agent_store, semantic, now=clock)
    attach_receipt = commits.attach_graph(
        agent_run_id=RUN_ID,
        graph_id=GRAPH_ID,
        graph_revision=1,
        graph_digest=initial.graph_digest,
        expected_agent_revision=4,
        expected_agent_epoch=1,
        permit=permit,
        authorization_reference=header.authority.reference,
        operation_id="40000000-0000-4000-8000-000000000001",
        agent_event_id="10000000-0000-4000-8000-000000000005",
    )
    commit_request = SemanticCommitRequest.from_proposal(
        commit_id="50000000-0000-4000-8000-000000000001",
        proposal=proposal.proposal,
        expected_agent_revision=5,
        expected_agent_epoch=1,
        ownership_permit_digest=ownership_permit_digest(permit),
        authorization_reference=header.authority.reference,
    )
    commit_receipt = commits.commit_patch(
        commit_request,
        permit=permit,
        semantic_event_id="60000000-0000-4000-8000-000000000001",
        agent_event_id="10000000-0000-4000-8000-000000000006",
    )
    head = semantic.get_graph_head(GRAPH_ID)
    profile = SemanticProjectionProfile(
        profile_id="goal-to-plan",
        profile_version="1.0.0",
        require_goal_plan_connection=True,
        include_unresolved_obligations=True,
        include_blocking_ambiguities=True,
    )
    context_request = SemanticContextRequest(
        agent_run_id=RUN_ID,
        graph_id=GRAPH_ID,
        graph_revision=head.graph_revision,
        graph_digest=head.graph_digest,
        profile=profile,
        required_root_node_ids=("goal:one", "plan:one"),
        allowed_node_types=tuple(SemanticNodeType),
        max_nodes=8,
        max_relations=8,
    )
    projection = SemanticContextProjector(agent_store, semantic).project(
        context_request
    )
    projection_bytes = projection.canonical_bytes()
    before_agent = agent.get_agent_run(RUN_ID)
    before_binding = agent_store.get_agent_semantic_binding(RUN_ID)
    events = agent.list_agent_events(RUN_ID)
    event_ids = [record.event.event_id for record in events]
    semantic_binding_event_count = sum(
        record.event.event_type is AgentEventType.SEMANTIC_STATE_ADVANCED
        for record in events
    )
    if not agent.release_agent_run(permit):
        raise RuntimeError("Agent ownership release failed")

    connection = semantic.database.connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM semantic_graph_heads WHERE graph_id = ?", (GRAPH_ID,)
        )
        connection.execute(
            "DELETE FROM agent_runs WHERE agent_run_id = ?", (RUN_ID,)
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    reopened_agent_store = AgentStore(database_path)
    reopened_semantic = SemanticStore(AgentDatabase(database_path))
    rebuilt_head = reopened_semantic.rebuild_graph_head(GRAPH_ID)
    rebuilt_agent = reopened_agent_store.rebuild_projection(
        RUN_ID, observed_at="2026-09-01T02:00:00+00:00"
    )
    rebuilt_binding = reopened_agent_store.get_agent_semantic_binding(RUN_ID)
    rebuilt_projection = SemanticContextProjector(
        reopened_agent_store, reopened_semantic
    ).project(context_request)
    rebuilt_bytes = rebuilt_projection.canonical_bytes()
    reopened_commits = SemanticCommitService(
        reopened_agent_store, reopened_semantic, now=clock
    )
    reopened_attach_receipt = reopened_commits.attach_graph(
        agent_run_id=RUN_ID,
        graph_id=GRAPH_ID,
        graph_revision=1,
        graph_digest=initial.graph_digest,
        expected_agent_revision=4,
        expected_agent_epoch=1,
        permit=permit,
        authorization_reference=header.authority.reference,
        operation_id="40000000-0000-4000-8000-000000000001",
        agent_event_id="10000000-0000-4000-8000-000000000005",
    )
    reopened_commit_receipt = reopened_commits.commit_patch(
        commit_request,
        permit=permit,
        semantic_event_id="60000000-0000-4000-8000-000000000001",
        agent_event_id="10000000-0000-4000-8000-000000000006",
    )

    if head != rebuilt_head:
        raise RuntimeError("semantic graph head reconstruction differs")
    if before_agent != rebuilt_agent or before_binding != rebuilt_binding:
        raise RuntimeError("Agent semantic binding reconstruction differs")
    if projection_bytes != rebuilt_bytes:
        raise RuntimeError("semantic context reconstruction differs")
    if (
        reopened_attach_receipt != attach_receipt
        or reopened_commit_receipt != commit_receipt
    ):
        raise RuntimeError("semantic receipt readback differs after reopen")
    if (
        reopened_attach_receipt.graph_revision != 1
        or reopened_commit_receipt.graph_revision != 2
    ):
        raise RuntimeError("semantic receipts do not bind the expected revisions")

    connection = reopened_semantic.database.connect()
    try:
        graph_revision_count = connection.execute(
            "SELECT COUNT(*) FROM semantic_graph_revisions WHERE graph_id = ?",
            (GRAPH_ID,),
        ).fetchone()[0]
        semantic_event_count = connection.execute(
            "SELECT COUNT(*) FROM semantic_events WHERE graph_id = ?",
            (GRAPH_ID,),
        ).fetchone()[0]
    finally:
        connection.close()
    replay_digest = sha256_id(
        "macr.semantic.structural-replay.v1",
        {
            "agent": rebuilt_agent.to_public_dict(),
            "binding": rebuilt_binding.to_public_dict(),
            "head": rebuilt_head.to_public_dict(),
            "projection_digest": rebuilt_projection.projection_digest,
            "event_ids": event_ids,
            "attach_receipt": reopened_attach_receipt.to_public_dict(),
            "commit_receipt": reopened_commit_receipt.to_public_dict(),
        },
    )
    return {
        "schema": "macr-v07-phase-c-structural-replay/v1",
        "agent_schema_version": AgentDatabase.SCHEMA_VERSION,
        "semantic_schema_version": semantic.schema.SCHEMA_VERSION,
        "agent_state_revision": rebuilt_agent.state_revision,
        "agent_epoch": rebuilt_agent.epoch,
        "agent_state_digest": rebuilt_agent.state_digest,
        "semantic_binding_digest": rebuilt_binding.binding_digest,
        "graph_revision": rebuilt_head.graph_revision,
        "graph_digest": rebuilt_head.graph_digest,
        "graph_revision_count": graph_revision_count,
        "semantic_event_count": semantic_event_count,
        "agent_event_count": len(events),
        "semantic_binding_event_count": semantic_binding_event_count,
        "agent_event_ids": event_ids,
        "attach_receipt_digest": reopened_attach_receipt.receipt_digest,
        "commit_receipt_digest": reopened_commit_receipt.receipt_digest,
        "projection_digest": rebuilt_projection.projection_digest,
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
