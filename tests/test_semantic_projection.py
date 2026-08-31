from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timezone

from macr_runtime.agent.database import AgentDatabase
from macr_runtime.agent.service import AgentStateService
from macr_runtime.agent.store import AgentStore
from macr_runtime.semantic.commit import (
    SemanticCommitService,
    ownership_permit_digest,
)
from macr_runtime.semantic.contracts import (
    ResolutionStatus,
    SemanticNodeType,
    SemanticPatch,
    SemanticRelation,
    SemanticRelationType,
)
from macr_runtime.semantic.errors import (
    SemanticProjectionConflictError,
    SemanticProjectionIncompleteError,
)
from macr_runtime.semantic.patch import SemanticCommitRequest
from macr_runtime.semantic.projection import (
    SemanticContextProjection,
    SemanticContextProjector,
    SemanticContextRequest,
    SemanticProjectionProfile,
)
from macr_runtime.semantic.service import SemanticProposalService
from macr_runtime.semantic.store import SemanticStore
from tests.support import d_drive_tempdir
from tests.test_agent_service import Clock
from tests.test_agent_state import RUN_ID, make_header
from tests.test_semantic_commit import (
    ATTACH_EVENT_ID,
    ATTACH_OPERATION_ID,
    COMMIT_AGENT_EVENT_ID,
    COMMIT_ID,
    SEMANTIC_EVENT_ID,
)
from tests.test_semantic_patch_validation import (
    GRAPH_ID,
    goal_plan_patch,
    proposal_for,
    semantic_node,
)


def projection_profile() -> SemanticProjectionProfile:
    return SemanticProjectionProfile(
        profile_id="goal-to-plan",
        profile_version="1.0.0",
        require_goal_plan_connection=True,
        include_unresolved_obligations=True,
        include_blocking_ambiguities=True,
    )


def projection_patch(base_digest: str, *, extras: str = "none") -> SemanticPatch:
    base = goal_plan_patch(base_digest)
    nodes = list(base.add_nodes)
    relations = list(base.add_relations)
    if extras == "task":
        nodes.append(semantic_node("task:optional", SemanticNodeType.TASK))
    if extras == "blocking":
        ambiguity = semantic_node(
            "ambiguity:blocking",
            SemanticNodeType.AMBIGUITY,
            status=ResolutionStatus.UNRESOLVED,
        )
        obligation = semantic_node(
            "obligation:open",
            SemanticNodeType.OBLIGATION,
            status=ResolutionStatus.UNRESOLVED,
        )
        nodes.extend((ambiguity, obligation))
        relations.extend(
            (
                SemanticRelation(
                    relation_id="relation:ambiguity-plan",
                    source_ref=ambiguity.node_id,
                    relation_type=SemanticRelationType.BLOCKS,
                    target_ref="plan:one",
                    qualifiers={},
                    provenance=ambiguity.provenance,
                ),
                SemanticRelation(
                    relation_id="relation:obligation-plan",
                    source_ref=obligation.node_id,
                    relation_type=SemanticRelationType.BLOCKS,
                    target_ref="plan:one",
                    qualifiers={},
                    provenance=obligation.provenance,
                ),
            )
        )
    return SemanticPatch(
        patch_id=f"patch:projection:{extras}",
        base_graph_digest=base_digest,
        add_nodes=tuple(nodes),
        add_relations=tuple(relations),
        status_updates=(),
        supersession_refs=(),
        producer_ref="model:candidate-only",
    )


def committed_world(temp, *, extras: str = "none"):
    clock = Clock(datetime(2026, 9, 1, 1, 0, tzinfo=timezone.utc))
    path = temp / "agent.sqlite3"
    store = AgentStore(path)
    agent = AgentStateService(store, now=clock)
    header = make_header()
    agent.create_agent_run(header)
    agent.admit_agent_run(
        RUN_ID,
        expected_revision=1,
        expected_epoch=0,
        reason_code="INITIAL_ADMISSION",
        reason_digest="a" * 64,
    )
    permit = agent.acquire_agent_run(
        RUN_ID,
        "owner:projection",
        expected_revision=2,
        expected_epoch=0,
        ttl_seconds=300,
    )
    agent.activate_agent_run(
        permit,
        expected_revision=3,
        expected_epoch=1,
        reason_code="SEMANTIC_READY",
        reason_digest="b" * 64,
    )
    semantic = SemanticStore(AgentDatabase(path))
    initial = semantic.create_graph(
        graph_id=GRAPH_ID,
        scope_ref="project:phase-c",
        created_by_agent_run_id=RUN_ID,
        created_at="2026-09-01T01:00:00+00:00",
    )
    proposal = proposal_for(
        projection_patch(initial.graph_digest, extras=extras),
        head=initial,
    )
    proposal_record = SemanticProposalService(semantic).propose_patch(
        proposal,
        created_at="2026-09-01T01:00:00+00:00",
    )
    commits = SemanticCommitService(store, semantic, now=clock)
    commits.attach_graph(
        agent_run_id=RUN_ID,
        graph_id=GRAPH_ID,
        graph_revision=1,
        graph_digest=initial.graph_digest,
        expected_agent_revision=4,
        expected_agent_epoch=1,
        permit=permit,
        authorization_reference=header.authority.reference,
        operation_id=ATTACH_OPERATION_ID,
        agent_event_id=ATTACH_EVENT_ID,
    )
    request = SemanticCommitRequest.from_proposal(
        commit_id=COMMIT_ID,
        proposal=proposal_record.proposal,
        expected_agent_revision=5,
        expected_agent_epoch=1,
        ownership_permit_digest=ownership_permit_digest(permit),
        authorization_reference=header.authority.reference,
    )
    receipt = commits.commit_patch(
        request,
        permit=permit,
        semantic_event_id=SEMANTIC_EVENT_ID,
        agent_event_id=COMMIT_AGENT_EVENT_ID,
    )
    return agent, semantic, semantic.get_graph_head(GRAPH_ID), receipt


def context_request(
    head,
    *,
    max_nodes: int = 8,
    max_relations: int = 8,
    required_roots: tuple[str, ...] = ("goal:one", "plan:one"),
    allowed_types: tuple[SemanticNodeType, ...] = tuple(SemanticNodeType),
) -> SemanticContextRequest:
    return SemanticContextRequest(
        agent_run_id=RUN_ID,
        graph_id=GRAPH_ID,
        graph_revision=head.graph_revision,
        graph_digest=head.graph_digest,
        profile=projection_profile(),
        required_root_node_ids=required_roots,
        allowed_node_types=allowed_types,
        max_nodes=max_nodes,
        max_relations=max_relations,
    )


class SemanticProjectionTests(unittest.TestCase):
    def test_goal_plan_projection_is_deterministic_round_trippable_and_read_only(self) -> None:
        with d_drive_tempdir() as temp:
            agent, semantic, head, _ = committed_world(temp)
            projector = SemanticContextProjector(agent.store, semantic)
            request = context_request(head)
            observer = semantic.database.connect()
            try:
                before_version = observer.execute("PRAGMA data_version").fetchone()[0]
                before_agent = agent.get_agent_run(RUN_ID)
                first = projector.project(request)
                second = projector.project(request)
                after_agent = agent.get_agent_run(RUN_ID)
                after_version = observer.execute("PRAGMA data_version").fetchone()[0]
            finally:
                observer.close()

        self.assertEqual(first, second)
        self.assertEqual(
            SemanticContextProjection.from_dict(first.to_public_dict()), first
        )
        self.assertEqual(first.canonical_bytes(), second.canonical_bytes())
        self.assertRegex(first.projection_digest, r"^[0-9a-f]{64}$")
        self.assertEqual([item.node_id for item in first.nodes], ["goal:one", "plan:one"])
        self.assertEqual(len(first.relations), 1)
        self.assertEqual(first.omitted_node_record_digests, ())
        self.assertEqual(first.omitted_relation_digests, ())
        self.assertEqual(after_agent, before_agent)
        self.assertEqual(after_version, before_version)

    def test_request_bounds_reject_bool_zero_negative_and_above_hard_limit(self) -> None:
        with d_drive_tempdir() as temp:
            _, _, head, _ = committed_world(temp)
            for value in (True, 0, -1, 129):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    context_request(head, max_nodes=value)
                with self.subTest(relation_value=value), self.assertRaises(ValueError):
                    context_request(head, max_relations=value)

    def test_wrong_graph_binding_and_missing_or_disallowed_root_fail_explicitly(self) -> None:
        with d_drive_tempdir() as temp:
            agent, semantic, head, _ = committed_world(temp)
            projector = SemanticContextProjector(agent.store, semantic)
            wrong_digest = dataclasses.replace(
                context_request(head), graph_digest="f" * 64
            )
            with self.assertRaises(SemanticProjectionConflictError):
                projector.project(wrong_digest)
            with self.assertRaises(SemanticProjectionIncompleteError):
                projector.project(
                    context_request(
                        head,
                        required_roots=("goal:one", "plan:missing"),
                    )
                )
            with self.assertRaises(SemanticProjectionIncompleteError):
                projector.project(
                    context_request(
                        head,
                        allowed_types=(SemanticNodeType.GOAL,),
                    )
                )

    def test_optional_node_omission_is_explicit_and_does_not_change_graph(self) -> None:
        with d_drive_tempdir() as temp:
            agent, semantic, head, _ = committed_world(temp, extras="task")
            revision_before = semantic.get_graph_revision(GRAPH_ID, 2)
            projected = SemanticContextProjector(agent.store, semantic).project(
                context_request(head, max_nodes=2)
            )
            revision_after = semantic.get_graph_revision(GRAPH_ID, 2)

        self.assertEqual(revision_after, revision_before)
        self.assertEqual(len(projected.nodes), 2)
        self.assertEqual(len(projected.omitted_node_record_digests), 1)
        self.assertIn(
            next(
                digest for digest in revision_before.active_node_record_digests
                if digest not in {item.record_digest for item in projected.nodes}
            ),
            projected.omitted_node_record_digests,
        )

    def test_required_goal_plan_blocking_ambiguity_and_obligation_never_silently_overflow(self) -> None:
        with d_drive_tempdir() as temp:
            agent, semantic, head, _ = committed_world(temp, extras="blocking")
            projector = SemanticContextProjector(agent.store, semantic)
            with self.assertRaises(SemanticProjectionIncompleteError):
                projector.project(context_request(head, max_nodes=3))
            with self.assertRaises(SemanticProjectionIncompleteError):
                projector.project(
                    context_request(head, max_nodes=4, max_relations=2)
                )
            complete = projector.project(
                context_request(head, max_nodes=4, max_relations=3)
            )

        self.assertEqual(len(complete.nodes), 4)
        self.assertEqual(len(complete.relations), 3)
        self.assertEqual(complete.omitted_node_record_digests, ())
        self.assertEqual(complete.omitted_relation_digests, ())


if __name__ == "__main__":
    unittest.main()
