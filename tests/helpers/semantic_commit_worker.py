from __future__ import annotations

import dataclasses
from datetime import datetime

from macr_runtime.agent.database import AgentDatabase
from macr_runtime.agent.ownership import AgentOwnershipPermit
from macr_runtime.agent.store import AgentStore
from macr_runtime.semantic.commit import (
    SemanticCommitService,
    ownership_permit_digest,
)
from macr_runtime.semantic.patch import SemanticCommitRequest
from macr_runtime.semantic.service import SemanticProposalService
from macr_runtime.semantic.store import SemanticStore
from tests.test_semantic_patch_validation import PROPOSAL_ID


class FixedClock:
    def __init__(self, value: str) -> None:
        self.value = datetime.fromisoformat(value)

    def __call__(self) -> datetime:
        return self.value


def commit_contender(
    database_path: str,
    permit_data: dict[str, object],
    commit_id: str,
    semantic_event_id: str,
    agent_event_id: str,
    start_event,
    results,
) -> None:
    agent_store = AgentStore(database_path)
    semantic_store = SemanticStore(AgentDatabase(database_path))
    proposal = SemanticProposalService(semantic_store).get_proposal(PROPOSAL_ID)
    permit = AgentOwnershipPermit(**permit_data)
    header = agent_store.get_agent_run(permit.agent_run_id).initial_header
    request = SemanticCommitRequest.from_proposal(
        commit_id=commit_id,
        proposal=proposal.proposal,
        expected_agent_revision=5,
        expected_agent_epoch=1,
        ownership_permit_digest=ownership_permit_digest(permit),
        authorization_reference=header.authority.reference,
    )
    service = SemanticCommitService(
        agent_store,
        semantic_store,
        now=FixedClock("2026-09-01T01:00:00+00:00"),
    )
    start_event.wait(timeout=30)
    try:
        receipt = service.commit_patch(
            request,
            permit=permit,
            semantic_event_id=semantic_event_id,
            agent_event_id=agent_event_id,
        )
        results.put(("committed", receipt.commit_id))
    except Exception as exc:
        results.put(("refused", type(exc).__name__, getattr(exc, "code", None)))
