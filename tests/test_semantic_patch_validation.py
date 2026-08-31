from __future__ import annotations

import unittest

from macr_runtime.execution import AuthorizationReference
from macr_runtime.semantic.contracts import (
    ResolutionStatus,
    SemanticLifecycleStatus,
    SemanticNode,
    SemanticNodeType,
    SemanticPatch,
    SemanticProvenance,
    SemanticRelation,
    SemanticRelationType,
)
from macr_runtime.semantic.errors import (
    SemanticGraphHeadStaleError,
    SemanticPatchInvalidError,
    SemanticRegistryMismatchError,
)
from macr_runtime.semantic.graph import SemanticGraphHead
from macr_runtime.semantic.patch import (
    SemanticCommitRequest,
    SemanticPatchProposalRequest,
)
from macr_runtime.semantic.registry import SemanticRegistry


GRAPH_ID = "11111111-1111-4111-8111-111111111111"
RUN_ID = "22222222-2222-4222-8222-222222222222"
PROPOSAL_ID = "33333333-3333-4333-8333-333333333333"
COMMIT_ID = "44444444-4444-4444-8444-444444444444"


def provenance() -> SemanticProvenance:
    return SemanticProvenance(
        origin_kind="host_fixture",
        origin_ref="fixture:phase-c",
        source_refs=("source:phase-c",),
        agent_run_id=RUN_ID,
        created_by_ref="host:test",
        created_at="2026-09-01T00:00:00+00:00",
    )


def semantic_node(
    node_id: str,
    node_type: SemanticNodeType,
    *,
    status=None,
    scope_ref: str = "project:phase-c",
    payload: dict[str, object] | None = None,
    effects: tuple[str, ...] = (),
) -> SemanticNode:
    if status is None:
        status = SemanticLifecycleStatus.ACTIVE
    return SemanticNode(
        node_id=node_id,
        node_type=node_type,
        payload={"label": node_id} if payload is None else payload,
        scope_ref=scope_ref,
        status=status,
        effects=effects,
        constraints=(),
        policy={},
        provenance=provenance(),
        temporal={},
        external_bindings=(),
    )


def goal_plan_patch(base_digest: str) -> SemanticPatch:
    goal = semantic_node("goal:one", SemanticNodeType.GOAL)
    plan = semantic_node("plan:one", SemanticNodeType.PLAN)
    relation = SemanticRelation(
        relation_id="relation:goal-plan",
        source_ref=goal.node_id,
        relation_type=SemanticRelationType.MOTIVATES,
        target_ref=plan.node_id,
        qualifiers={},
        provenance=provenance(),
    )
    return SemanticPatch(
        patch_id="patch:goal-plan",
        base_graph_digest=base_digest,
        add_nodes=(plan, goal),
        add_relations=(relation,),
        status_updates=(),
        supersession_refs=(),
        producer_ref="model:candidate-only",
    )


def empty_head() -> SemanticGraphHead:
    return SemanticGraphHead.create_empty(
        graph_id=GRAPH_ID,
        scope_ref="project:phase-c",
        registry=SemanticRegistry.from_builtin(),
        created_by_agent_run_id=RUN_ID,
        created_at="2026-09-01T00:00:00+00:00",
    )


def proposal_for(
    patch: SemanticPatch | None = None,
    *,
    head: SemanticGraphHead | None = None,
) -> SemanticPatchProposalRequest:
    selected_head = empty_head() if head is None else head
    registry = SemanticRegistry.from_builtin()
    selected_patch = (
        goal_plan_patch(selected_head.graph_digest) if patch is None else patch
    )
    return SemanticPatchProposalRequest(
        proposal_id=PROPOSAL_ID,
        graph_id=selected_head.graph_id,
        agent_run_id=RUN_ID,
        base_graph_revision=selected_head.graph_revision,
        base_graph_digest=selected_head.graph_digest,
        registry_version=registry.registry_version,
        registry_digest=registry.registry_digest,
        patch=selected_patch,
    )


class SemanticPatchValidationTests(unittest.TestCase):
    def test_proposal_is_authority_free_digest_bound_and_round_trips(self) -> None:
        proposal = proposal_for()
        public = proposal.to_public_dict()

        self.assertEqual(SemanticPatchProposalRequest.from_dict(public), proposal)
        self.assertRegex(proposal.proposal_digest, r"^[0-9a-f]{64}$")
        for forbidden in (
            "authorization_reference",
            "ownership_permit_digest",
            "expected_agent_revision",
            "expected_agent_epoch",
            "commit_id",
            "authorized",
        ):
            self.assertNotIn(forbidden, public)

    def test_commit_request_binds_stored_proposal_and_external_authority(self) -> None:
        proposal = proposal_for()
        authorization = AuthorizationReference(
            source_kind="host_operator",
            source_id="authority:phase-c",
            digest="a" * 64,
            revision=1,
            epoch=0,
            scope="agent:phase-c",
        )
        request = SemanticCommitRequest.from_proposal(
            commit_id=COMMIT_ID,
            proposal=proposal,
            expected_agent_revision=4,
            expected_agent_epoch=1,
            ownership_permit_digest="b" * 64,
            authorization_reference=authorization,
        )

        self.assertEqual(SemanticCommitRequest.from_dict(request.to_public_dict()), request)
        self.assertEqual(request.proposal_digest, proposal.proposal_digest)
        self.assertEqual(request.patch.patch_digest, proposal.patch.patch_digest)
        self.assertEqual(request.authorization_reference, authorization)

    def test_patch_base_and_proposal_base_must_match(self) -> None:
        patch = goal_plan_patch("f" * 64)
        with self.assertRaisesRegex(SemanticPatchInvalidError, "base"):
            proposal_for(patch)

    def test_tampered_serialized_request_fails_its_proposal_digest(self) -> None:
        proposal = proposal_for()
        public = proposal.to_public_dict()
        public["base_graph_revision"] = 2
        with self.assertRaises(SemanticPatchInvalidError):
            SemanticPatchProposalRequest.from_dict(public)

        public = proposal.to_public_dict()
        public["registry_digest"] = "f" * 64
        with self.assertRaises(SemanticPatchInvalidError):
            SemanticPatchProposalRequest.from_dict(public)


if __name__ == "__main__":
    unittest.main()
