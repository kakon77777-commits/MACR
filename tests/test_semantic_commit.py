from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timezone

from macr_runtime.agent.database import AgentDatabase
from macr_runtime.agent.service import AgentStateService
from macr_runtime.agent.store import AgentStore
from macr_runtime.execution import AuthorizationReference
from macr_runtime.semantic.commit import (
    SemanticAttachReceipt,
    SemanticCommitReceipt,
    SemanticCommitService,
    ownership_permit_digest,
)
from macr_runtime.semantic.errors import (
    SemanticAgentBindingConflictError,
    SemanticCommitAuthorityInvalidError,
    SemanticPatchConflictError,
)
from macr_runtime.semantic.patch import SemanticCommitRequest
from macr_runtime.semantic.service import SemanticProposalService
from macr_runtime.semantic.store import SemanticStore
from tests.support import d_drive_tempdir
from tests.test_agent_service import Clock
from tests.test_agent_state import RUN_ID, make_header
from tests.test_semantic_patch_validation import GRAPH_ID, proposal_for


ATTACH_OPERATION_ID = "77777777-7777-4777-8777-777777777777"
ATTACH_EVENT_ID = "88888888-8888-4888-8888-888888888888"
COMMIT_ID = "99999999-9999-4999-8999-999999999999"
SEMANTIC_EVENT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
COMMIT_AGENT_EVENT_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def active_world(temp):
    clock = Clock(datetime(2026, 9, 1, 1, 0, tzinfo=timezone.utc))
    path = temp / "agent.sqlite3"
    agent_store = AgentStore(path)
    agent = AgentStateService(agent_store, now=clock)
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
        "owner:semantic",
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
    head = semantic.create_graph(
        graph_id=GRAPH_ID,
        scope_ref="project:phase-c",
        created_by_agent_run_id=RUN_ID,
        created_at="2026-09-01T01:00:00+00:00",
    )
    proposal_service = SemanticProposalService(semantic)
    proposal_record = proposal_service.propose_patch(
        proposal_for(),
        created_at="2026-09-01T01:00:00+00:00",
    )
    return agent, semantic, header, permit, head, proposal_record, clock


def attach(commit_service, agent, header, permit, head):
    return commit_service.attach_graph(
        agent_run_id=RUN_ID,
        graph_id=GRAPH_ID,
        graph_revision=1,
        graph_digest=head.graph_digest,
        expected_agent_revision=4,
        expected_agent_epoch=1,
        permit=permit,
        authorization_reference=header.authority.reference,
        operation_id=ATTACH_OPERATION_ID,
        agent_event_id=ATTACH_EVENT_ID,
    )


class SemanticCommitTests(unittest.TestCase):
    def test_attach_binds_current_head_once_without_advancing_graph(self) -> None:
        with d_drive_tempdir() as temp:
            agent, semantic, header, permit, head, _, clock = active_world(temp)
            service = SemanticCommitService(
                agent.store,
                semantic,
                now=clock,
            )

            attached = attach(service, agent, header, permit, head)
            repeated = service.attach_graph(
                agent_run_id=RUN_ID,
                graph_id=GRAPH_ID,
                graph_revision=1,
                graph_digest=head.graph_digest,
                expected_agent_revision=4,
                expected_agent_epoch=1,
                permit=permit,
                authorization_reference=header.authority.reference,
                operation_id=ATTACH_OPERATION_ID,
                agent_event_id=ATTACH_EVENT_ID,
            )
            after_head = semantic.get_graph_head(GRAPH_ID)
            events = agent.list_agent_events(RUN_ID)
            binding = agent.store.get_agent_semantic_binding(RUN_ID)

        self.assertIsInstance(attached, SemanticAttachReceipt)
        self.assertEqual(attached.agent_state_revision, 5)
        self.assertEqual(repeated, attached)
        self.assertEqual(after_head, head)
        self.assertEqual(binding, head.to_semantic_state_binding())
        self.assertEqual(len(events), 5)

    def test_attach_operation_id_conflicting_reuse_fails_without_drift(self) -> None:
        with d_drive_tempdir() as temp:
            agent, semantic, header, permit, head, _, clock = active_world(temp)
            service = SemanticCommitService(agent.store, semantic, now=clock)
            receipt = attach(service, agent, header, permit, head)
            before_agent = agent.get_agent_run(RUN_ID)
            before_events = agent.list_agent_events(RUN_ID)

            with self.assertRaises(SemanticAgentBindingConflictError):
                service.attach_graph(
                    agent_run_id=RUN_ID,
                    graph_id=GRAPH_ID,
                    graph_revision=1,
                    graph_digest="f" * 64,
                    expected_agent_revision=4,
                    expected_agent_epoch=1,
                    permit=permit,
                    authorization_reference=header.authority.reference,
                    operation_id=ATTACH_OPERATION_ID,
                    agent_event_id=ATTACH_EVENT_ID,
                )

            after_agent = agent.get_agent_run(RUN_ID)
            after_events = agent.list_agent_events(RUN_ID)

        self.assertEqual(receipt.agent_state_revision, 5)
        self.assertEqual(after_agent, before_agent)
        self.assertEqual(after_events, before_events)

    def test_commit_advances_graph_and_agent_once_and_exact_repeat_returns_receipt(self) -> None:
        with d_drive_tempdir() as temp:
            agent, semantic, header, permit, head, proposal_record, clock = active_world(temp)
            service = SemanticCommitService(agent.store, semantic, now=clock)
            attach(service, agent, header, permit, head)
            request = SemanticCommitRequest.from_proposal(
                commit_id=COMMIT_ID,
                proposal=proposal_record.proposal,
                expected_agent_revision=5,
                expected_agent_epoch=1,
                ownership_permit_digest=ownership_permit_digest(permit),
                authorization_reference=header.authority.reference,
            )

            receipt = service.commit_patch(
                request,
                permit=permit,
                semantic_event_id=SEMANTIC_EVENT_ID,
                agent_event_id=COMMIT_AGENT_EVENT_ID,
            )
            repeated = service.commit_patch(
                request,
                permit=permit,
                semantic_event_id=SEMANTIC_EVENT_ID,
                agent_event_id=COMMIT_AGENT_EVENT_ID,
            )
            graph = semantic.get_graph_head(GRAPH_ID)
            agent_projection = agent.get_agent_run(RUN_ID)
            binding = agent.store.get_agent_semantic_binding(RUN_ID)

        self.assertIsInstance(receipt, SemanticCommitReceipt)
        self.assertEqual(repeated, receipt)
        self.assertEqual(graph.graph_revision, 2)
        self.assertEqual(agent_projection.state_revision, 6)
        self.assertEqual(binding.ref, graph.graph_ref)
        self.assertEqual(binding.digest, graph.graph_digest)
        self.assertEqual(binding.revision, 2)
        self.assertEqual(receipt.graph_revision, 2)
        self.assertEqual(receipt.agent_state_revision, 6)

    def test_wrong_external_authority_fails_even_when_semantic_patch_looks_authoritative(self) -> None:
        with d_drive_tempdir() as temp:
            agent, semantic, header, permit, head, proposal_record, clock = active_world(temp)
            service = SemanticCommitService(agent.store, semantic, now=clock)
            attach(service, agent, header, permit, head)
            forged = AuthorizationReference(
                source_kind="semantic_decision",
                source_id="decision:claims-authority",
                digest="f" * 64,
                revision=1,
                epoch=0,
                scope="agent:phase-c",
            )
            request = SemanticCommitRequest.from_proposal(
                commit_id=COMMIT_ID,
                proposal=proposal_record.proposal,
                expected_agent_revision=5,
                expected_agent_epoch=1,
                ownership_permit_digest=ownership_permit_digest(permit),
                authorization_reference=forged,
            )

            with self.assertRaises(SemanticCommitAuthorityInvalidError):
                service.commit_patch(
                    request,
                    permit=permit,
                    semantic_event_id=SEMANTIC_EVENT_ID,
                    agent_event_id=COMMIT_AGENT_EVENT_ID,
                )

            self.assertEqual(semantic.get_graph_head(GRAPH_ID), head)
            self.assertEqual(agent.get_agent_run(RUN_ID).state_revision, 5)

    def test_commit_id_conflicting_reuse_fails_without_second_revision(self) -> None:
        with d_drive_tempdir() as temp:
            agent, semantic, header, permit, head, proposal_record, clock = active_world(temp)
            service = SemanticCommitService(agent.store, semantic, now=clock)
            attach(service, agent, header, permit, head)
            request = SemanticCommitRequest.from_proposal(
                commit_id=COMMIT_ID,
                proposal=proposal_record.proposal,
                expected_agent_revision=5,
                expected_agent_epoch=1,
                ownership_permit_digest=ownership_permit_digest(permit),
                authorization_reference=header.authority.reference,
            )
            service.commit_patch(
                request,
                permit=permit,
                semantic_event_id=SEMANTIC_EVENT_ID,
                agent_event_id=COMMIT_AGENT_EVENT_ID,
            )
            conflict = dataclasses.replace(request, expected_agent_revision=6)

            with self.assertRaises(SemanticPatchConflictError):
                service.commit_patch(
                    conflict,
                    permit=permit,
                    semantic_event_id=SEMANTIC_EVENT_ID,
                    agent_event_id=COMMIT_AGENT_EVENT_ID,
                )

            self.assertEqual(semantic.get_graph_head(GRAPH_ID).graph_revision, 2)


if __name__ == "__main__":
    unittest.main()
