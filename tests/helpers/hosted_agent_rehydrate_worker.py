from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from macr_runtime.agent.cell import (
    AgentStoreOwnershipVerifier,
    HostedActionGate,
    HostedAgentBlobStore,
    HostedAgentCellRunner,
    HostedAgentCellStore,
    HostedRawModelResponse,
    HostedWorkspaceTools,
)
from macr_runtime.agent.database import AgentDatabase
from macr_runtime.agent.service import AgentStateService
from macr_runtime.agent.store import AgentStore
from macr_runtime.candidate_vault import CandidateVault
from macr_runtime.semantic.projection import SemanticContextProjector
from macr_runtime.semantic.store import SemanticStore


NOW = datetime(2026, 9, 1, 1, 0, tzinfo=timezone.utc)


class Authority:
    def __init__(self, digest: str, agent_run_id: str) -> None:
        self.digest = digest
        self.agent_run_id = agent_run_id

    def verify_cell(self, reference, **kwargs) -> None:
        if (
            reference.digest != self.digest
            or kwargs["agent_run_id"] != self.agent_run_id
        ):
            raise RuntimeError("authority rejected")

    def verify(self, reference, **kwargs) -> None:
        if (
            reference.digest != self.digest
            or kwargs["agent_run_id"] != self.agent_run_id
        ):
            raise RuntimeError("authority rejected")


class FinalPort:
    provider_id = "grok"
    model_id = "grok-4.6"

    def invoke(self, request, context_bytes):
        context = json.loads(context_bytes)
        evidence_ref = context["context_sections"][0]["evidence_ref"]
        raw = json.dumps(
            {
                "kind": "final_candidate",
                "final_candidate": "Fresh process rehydration succeeded.",
                "evidence_refs": [evidence_ref],
            }
        ).encode("utf-8")
        return HostedRawModelResponse(
            request.provider_invocation_id,
            self.provider_id,
            self.model_id,
            raw,
            0.0,
            1,
            False,
            False,
        )


class NeverPort:
    provider_id = "grok"
    model_id = "grok-4.6"

    def invoke(self, request, context_bytes):  # pragma: no cover - subprocess guard
        del request, context_bytes
        raise AssertionError("persisted budget must stop before model invocation")


def main() -> int:
    config = json.loads(sys.stdin.read())
    agent_db = Path(config["agent_db"])
    agent_store = AgentStore(agent_db)
    agent = AgentStateService(agent_store, now=lambda: NOW)
    semantic = SemanticStore(AgentDatabase(agent_db))
    blobs = HostedAgentBlobStore(config["blob_root"])
    authority = Authority(config["authority_digest"], config["agent_run_id"])
    cell_store = HostedAgentCellStore(
        agent_store,
        blobs,
        authority,
        now=lambda: NOW,
    )
    tools = HostedWorkspaceTools(
        config["workspace"],
        allowed_prefixes=("docs",),
    )
    runner = HostedAgentCellRunner(
        agent,
        cell_store,
        SemanticContextProjector(agent_store, semantic),
        CandidateVault(config["candidate_root"], config["runtime_db"]),
        HostedActionGate(
            tools,
            authority,
            AgentStoreOwnershipVerifier(agent_store, now=lambda: NOW),
        ),
        now=lambda: NOW,
    )
    model = (
        NeverPort() if config.get("mode") == "expect_budget_exhausted" else FinalPort()
    )
    result = runner.rehydrate_and_run(
        config["agent_run_id"],
        "owner:fresh-process",
        ttl_seconds=300,
        model=model,
    )
    print(
        json.dumps(
            {
                "status": result.cell_state.status.value,
                "activation_status": result.status,
                "failure_code": result.failure_code,
                "cell_state": result.cell_state.to_public_dict(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
