from __future__ import annotations

import hashlib
import json
import sqlite3
import os
import subprocess
import sys
from dataclasses import replace
import unittest
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path

from macr_runtime.agent.cell import (
    AgentStoreOwnershipVerifier,
    HostedActionGate,
    HostedAgentBlobStore,
    HostedAgentCellPolicy,
    HostedAgentCellRunner,
    HostedAgentCellStatus,
    HostedAgentCellStore,
    HostedAgentCheckpointError,
    HostedAgentCellStateError,
    HostedAgentReconciliationRequired,
    HostedContextKind,
    HostedContextSection,
    HostedModelRequest,
    HostedRawModelResponse,
    HostedWorkspaceTools,
)
from macr_runtime.agent.contracts import AgentRunState
from macr_runtime.agent.errors import AgentOwnershipConflictError
from macr_runtime.candidate_vault import CandidateVault
from macr_runtime.contracts import DelegationClass, PrivacyLevel
from macr_runtime.semantic.projection import SemanticContextProjector
from macr_runtime.temporal import AgentCheckpoint
from tests.support import d_drive_tempdir
from tests.test_agent_state import RUN_ID
from tests.test_semantic_projection import committed_world, context_request


NOW = datetime(2026, 9, 1, 1, 0, tzinfo=timezone.utc)


class ExactAuthorityVerifier:
    def __init__(self, digest: str) -> None:
        self.digest = digest
        self.cell_calls = []
        self.tool_calls = []

    def verify_cell(
        self,
        reference,
        *,
        agent_run_id,
        policy_digest,
        operation,
    ) -> None:
        if reference.digest != self.digest or agent_run_id != RUN_ID:
            raise RuntimeError("cell authority rejected")
        self.cell_calls.append((policy_digest, operation))

    def verify(
        self,
        reference,
        *,
        agent_run_id,
        tool,
        target_digest,
        policy_digest,
    ) -> None:
        if reference.digest != self.digest or agent_run_id != RUN_ID:
            raise RuntimeError("tool authority rejected")
        self.tool_calls.append((tool.tool_id, target_digest, policy_digest))


class ReadThenAnswerPort:
    provider_id = "grok"
    model_id = "grok-4.6"

    def __init__(self) -> None:
        self.calls = 0
        self.contexts = []

    def invoke(self, request, context_bytes):
        self.calls += 1
        context = json.loads(context_bytes)
        self.contexts.append(context)
        if self.calls == 1:
            raw = b"""{ "kind": "tool_request", "tool_id": "workspace.read_text", "arguments": {"path": "docs/fact.txt"} }"""
        else:
            tool_section = next(
                item
                for item in reversed(context["context_sections"])
                if item["kind"] == "tool_result"
            )
            result_ref = json.loads(tool_section["body"])["result_ref"]
            raw = json.dumps(
                {
                    "kind": "final_candidate",
                    "final_candidate": "The verified fixture value is 42.",
                    "evidence_refs": [result_ref["evidence_ref"]],
                },
                indent=2,
            ).encode("utf-8")
        return HostedRawModelResponse(
            provider_invocation_id=request.provider_invocation_id,
            provider_id=self.provider_id,
            model_id=self.model_id,
            raw_decision=raw,
            currency_cost_usd=0.0,
            duration_ms=5,
            network_attempted=False,
            response_received=False,
        )


class FinalFromBriefPort:
    provider_id = "grok"
    model_id = "grok-4.6"

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, request, context_bytes):
        self.calls += 1
        context = json.loads(context_bytes)
        evidence_ref = context["context_sections"][0]["evidence_ref"]
        raw = json.dumps(
            {
                "kind": "final_candidate",
                "final_candidate": "Checkpoint continuity is intact.",
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


class MalformedPaidPort:
    provider_id = "grok"
    model_id = "grok-4.6"

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, request, context_bytes):
        del context_bytes
        self.calls += 1
        return HostedRawModelResponse(
            request.provider_invocation_id,
            self.provider_id,
            self.model_id,
            b"not-json",
            0.25,
            25,
            True,
            True,
        )


class OverCostFinalPort:
    provider_id = "grok"
    model_id = "grok-4.6"

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, request, context_bytes):
        self.calls += 1
        context = json.loads(context_bytes)
        evidence_ref = context["context_sections"][0]["evidence_ref"]
        raw = json.dumps(
            {
                "kind": "final_candidate",
                "final_candidate": "This over-cost answer must not complete.",
                "evidence_refs": [evidence_ref],
            }
        ).encode("utf-8")
        return HostedRawModelResponse(
            request.provider_invocation_id,
            self.provider_id,
            self.model_id,
            raw,
            0.2,
            10,
            True,
            True,
        )


class NeverCallPort:
    provider_id = "grok"
    model_id = "grok-4.6"

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, request, context_bytes):  # pragma: no cover - must not run
        del request, context_bytes
        self.calls += 1
        raise AssertionError("completion recovery called the model")


class PrivacyProbePort:
    provider_id = "grok"
    model_id = "grok-4.6"

    def __init__(self) -> None:
        self.calls = 0
        self.contexts = []

    def invoke(self, request, context_bytes):
        self.calls += 1
        context = json.loads(context_bytes)
        self.contexts.append(context)
        self.assert_secret_absent(context)
        if self.calls == 1:
            proposal = {
                "kind": "tool_request",
                "tool_id": "workspace.list_files",
                "arguments": {"prefix": "docs", "limit": 20},
            }
        elif self.calls == 2:
            proposal = {
                "kind": "tool_request",
                "tool_id": "workspace.search_text",
                "arguments": {
                    "prefix": "docs",
                    "query": "PUBLIC_RESULT_CANARY_8f31",
                    "max_matches": 5,
                },
            }
        else:
            result_ref = json.loads(
                next(
                    item
                    for item in reversed(context["context_sections"])
                    if item["kind"] == "tool_result"
                )["body"]
            )["result_ref"]["evidence_ref"]
            proposal = {
                "kind": "final_candidate",
                "final_candidate": "FINAL_CANDIDATE_CANARY_5c27",
                "evidence_refs": [result_ref],
            }
        return HostedRawModelResponse(
            request.provider_invocation_id,
            self.provider_id,
            self.model_id,
            json.dumps(proposal).encode("utf-8"),
            0.0,
            1,
            False,
            False,
        )

    @staticmethod
    def assert_secret_absent(context) -> None:
        if "SECRET_FILE_CANARY_f991" in json.dumps(context):
            raise AssertionError("secret traversal reached hosted context")


class BoundedToolPort:
    provider_id = "grok"
    model_id = "grok-4.6"

    def __init__(self, tool_id: str, arguments: dict[str, object]) -> None:
        self.tool_id = tool_id
        self.arguments = arguments
        self.calls = 0
        self.tool_payload = None

    def invoke(self, request, context_bytes):
        self.calls += 1
        context = json.loads(context_bytes)
        if self.calls == 1:
            proposal = {
                "kind": "tool_request",
                "tool_id": self.tool_id,
                "arguments": self.arguments,
            }
        else:
            body = json.loads(
                next(
                    item
                    for item in reversed(context["context_sections"])
                    if item["kind"] == "tool_result"
                )["body"]
            )
            self.tool_payload = body["payload"]
            proposal = {
                "kind": "final_candidate",
                "final_candidate": "Bounded traversal observation captured.",
                "evidence_refs": [body["result_ref"]["evidence_ref"]],
            }
        return HostedRawModelResponse(
            request.provider_invocation_id,
            self.provider_id,
            self.model_id,
            json.dumps(proposal).encode("utf-8"),
            0.0,
            1,
            False,
            False,
        )


class ConcurrentAppendFinalPort:
    provider_id = "grok"
    model_id = "grok-4.6"

    def __init__(self, store, permit, section) -> None:
        self.store = store
        self.permit = permit
        self.section = section
        self.append_refused = False
        self.calls = 0

    def invoke(self, request, context_bytes):
        del context_bytes
        self.calls += 1
        try:
            self.store.append_context_section(self.permit, self.section)
        except HostedAgentReconciliationRequired:
            self.append_refused = True
        raw = json.dumps(
            {
                "kind": "final_candidate",
                "final_candidate": "This cites context the model never observed.",
                "evidence_refs": [self.section.evidence_ref],
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


class HostedAgentCellRunnerTests(unittest.TestCase):
    def build_world(
        self,
        temp,
        *,
        brief=None,
        policy_overrides=None,
        tool_overrides=None,
    ):
        agent, semantic, head, _ = committed_world(temp)
        permit = agent.get_agent_ownership(RUN_ID)
        self.assertIsNotNone(permit)
        workspace = temp / "workspace"
        (workspace / "docs").mkdir(parents=True)
        (workspace / "docs" / "fact.txt").write_text(
            "fixture_value=42\n",
            encoding="utf-8",
        )
        tools = HostedWorkspaceTools(
            workspace,
            allowed_prefixes=("docs",),
            **(tool_overrides or {}),
        )
        verifier = ExactAuthorityVerifier(
            agent.get_agent_run(RUN_ID).initial_header.authority.reference.digest
        )
        blobs = HostedAgentBlobStore(temp / "agent-cells")
        store = HostedAgentCellStore(
            agent.store,
            blobs,
            verifier,
            now=lambda: NOW,
        )
        action_gate = HostedActionGate(
            tools,
            verifier,
            AgentStoreOwnershipVerifier(agent.store, now=lambda: NOW),
        )
        runner = HostedAgentCellRunner(
            agent,
            store,
            SemanticContextProjector(agent.store, semantic),
            CandidateVault(
                temp / "candidates",
                temp / "runtime" / "dispatch.sqlite3",
            ),
            action_gate,
            now=lambda: NOW,
        )
        policy = HostedAgentCellPolicy(
            agent_run_id=RUN_ID,
            provider_id="grok",
            model_id="grok-4.6",
            model_token_policy_digest="d" * 64,
            provider_execution_profile_digest="f" * 64,
            prompt_compiler_version="macr-hosted-context-turn/v1",
            project_ref="project:fixture",
            delegation_class=DelegationClass.NON_SENSITIVE_ROUTINE,
            privacy=PrivacyLevel.INTERNAL_APPROVED,
            provider_tier_binding_digest=None,
            project_binding_digest=None,
            admission_lane=None,
            provider_admission_policy_digest=None,
            tool_catalog_digest=tools.catalog.catalog_digest,
            allowed_tool_ids=(
                "workspace.list_files",
                "workspace.read_text",
                "workspace.search_text",
            ),
            max_steps=4,
            max_provider_calls=4,
            max_tool_calls=2,
            max_active_wall_seconds=60,
            max_currency_cost_usd=0.0,
            max_provider_call_cost_usd=0.0,
            max_latency_s=900,
            max_output_tokens=65_536,
            max_provider_context_tokens=400_000,
            max_context_bytes=1024 * 1024,
            max_raw_model_response_bytes=1024 * 1024,
            max_tool_result_bytes=1024 * 1024,
            max_final_output_bytes=1024 * 1024,
        )
        if policy_overrides:
            policy = replace(policy, **policy_overrides)
        brief = brief or "Read the approved fixture and report its exact value."
        section = HostedContextSection(
            section_id="22222222-2222-4222-8222-222222222222",
            agent_run_id=RUN_ID,
            kind=HostedContextKind.OPERATOR_BRIEF,
            label="Operator brief",
            body=brief,
            source_ref="operator:fixture",
            source_digest=hashlib.sha256(brief.encode("utf-8")).hexdigest(),
            created_at=NOW.isoformat(),
        )
        runner.attach(
            permit,
            policy,
            context_request(head),
            (section,),
        )
        return agent, store, runner, permit, verifier

    def test_list_and_search_report_every_bounded_truncation(self) -> None:
        with d_drive_tempdir() as temp:
            _, _, runner, permit, _ = self.build_world(
                temp,
                tool_overrides={"max_walk_entries": 2},
            )
            for index in range(6):
                (
                    runner.action_gate.tools.root / "docs" / f"file-{index}.txt"
                ).write_text(
                    f"value-{index}\n",
                    encoding="utf-8",
                )
            model = BoundedToolPort(
                "workspace.list_files",
                {"prefix": "docs", "limit": 20},
            )

            result = runner.run_activation(permit, model)

        self.assertEqual(result.status, "completed")
        self.assertEqual(model.calls, 2)
        self.assertTrue(model.tool_payload["truncated"])
        self.assertEqual(model.tool_payload["examined_entries"], 2)
        self.assertLessEqual(len(model.tool_payload["files"]), 2)

        with d_drive_tempdir() as temp:
            _, _, runner, permit, _ = self.build_world(
                temp,
                policy_overrides={"max_tool_result_bytes": 220},
            )
            (runner.action_gate.tools.root / "docs" / "large-line.txt").write_text(
                "needle " + "x" * 1000 + "\n",
                encoding="utf-8",
            )
            model = BoundedToolPort(
                "workspace.search_text",
                {"prefix": "docs", "query": "needle", "max_matches": 10},
            )

            result = runner.run_activation(permit, model)

        self.assertEqual(result.status, "completed")
        self.assertEqual(model.calls, 2)
        self.assertTrue(model.tool_payload["truncated"])
        self.assertEqual(model.tool_payload["matches"], [])

    def test_swapped_workspace_root_refuses_before_model_or_tool_admission(
        self,
    ) -> None:
        with d_drive_tempdir() as temp:
            agent, store, runner, permit, verifier = self.build_world(temp)
            other_root = temp / "other-project"
            (other_root / "docs").mkdir(parents=True)
            other_tools = HostedWorkspaceTools(
                other_root,
                allowed_prefixes=("docs",),
            )
            runner.action_gate = HostedActionGate(
                other_tools,
                verifier,
                AgentStoreOwnershipVerifier(agent.store, now=lambda: NOW),
            )
            model = ReadThenAnswerPort()

            with self.assertRaisesRegex(ValueError, "tool catalog"):
                runner.run_activation(permit, model)
            connection = sqlite3.connect(store.database.path)
            try:
                model_dispatches = connection.execute(
                    "SELECT COUNT(*) FROM hosted_model_dispatches"
                ).fetchone()[0]
                tool_requests = connection.execute(
                    "SELECT COUNT(*) FROM hosted_tool_requests"
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(model.calls, 0)
        self.assertEqual((model_dispatches, tool_requests), (0, 0))

    def test_pending_model_cannot_append_or_cite_unobserved_context(self) -> None:
        with d_drive_tempdir() as temp:
            _, store, runner, permit, verifier = self.build_world(temp)
            body = "CONCURRENT_CONTEXT_CANARY_901b"
            section = HostedContextSection(
                section_id="99999999-9999-4999-8999-999999999999",
                agent_run_id=RUN_ID,
                kind=HostedContextKind.PROJECT_FACT,
                label="Concurrent context",
                body=body,
                source_ref="operator:concurrent",
                source_digest=hashlib.sha256(body.encode("utf-8")).hexdigest(),
                created_at=NOW.isoformat(),
            )
            model = ConcurrentAppendFinalPort(store, permit, section)

            with self.assertRaisesRegex(
                HostedAgentCellStateError,
                "unknown evidence",
            ):
                runner.run_activation(permit, model)
            state = store.read_state(RUN_ID)
            connection = sqlite3.connect(store.database.path)
            try:
                sections = connection.execute(
                    "SELECT COUNT(*) FROM hosted_context_sections"
                ).fetchone()[0]
                terminals = connection.execute(
                    "SELECT COUNT(*) FROM hosted_model_terminals"
                ).fetchone()[0]
                intents = connection.execute(
                    "SELECT COUNT(*) FROM hosted_agent_completion_intents"
                ).fetchone()[0]
            finally:
                connection.close()
            private_bytes = b"".join(
                path.read_bytes() for path in store.blobs.root.rglob("*.bin")
            )

        self.assertTrue(model.append_refused)
        self.assertEqual(model.calls, 1)
        self.assertEqual(sections, 1)
        self.assertEqual(terminals, 1)
        self.assertEqual(intents, 0)
        self.assertIs(state.status, HostedAgentCellStatus.RUNNING)
        self.assertNotIn(body.encode("utf-8"), private_bytes)
        self.assertIn(
            (state.policy_digest, "context_append"),
            verifier.cell_calls,
        )

    def test_provider_call_budget_survives_fresh_process_rehydration(self) -> None:
        with d_drive_tempdir() as temp:
            agent, store, runner, permit, _ = self.build_world(
                temp,
                policy_overrides={"max_provider_calls": 1},
            )
            first_model = ReadThenAnswerPort()
            first = runner.run_activation(permit, first_model)
            config = {
                "agent_db": str(agent.store.database.path),
                "blob_root": str(store.blobs.root),
                "candidate_root": str(runner.candidate_vault.root),
                "runtime_db": str(runner.candidate_vault.database.path),
                "workspace": str(runner.action_gate.tools.root),
                "authority_digest": agent.get_agent_run(
                    RUN_ID
                ).initial_header.authority.reference.digest,
                "agent_run_id": RUN_ID,
                "mode": "expect_budget_exhausted",
            }
            environment = {
                **os.environ,
                "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
            }
            worker = (
                Path(__file__).resolve().parent
                / "helpers"
                / "hosted_agent_rehydrate_worker.py"
            )
            second = subprocess.run(
                [sys.executable, str(worker)],
                input=json.dumps(config),
                text=True,
                capture_output=True,
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                timeout=30,
                check=False,
            )
            final_state = store.read_state(RUN_ID)

        self.assertEqual(first.status, "checkpointed")
        self.assertEqual(first.failure_code, "provider_calls_exhausted")
        self.assertEqual(first_model.calls, 1)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(
            json.loads(second.stdout)["failure_code"],
            "provider_calls_exhausted",
        )
        self.assertEqual(final_state.provider_calls, 1)
        self.assertEqual(final_state.tool_calls, 1)
        self.assertIs(final_state.status, HostedAgentCellStatus.CHECKPOINTED)

    def test_last_allowed_model_call_can_complete_its_final_decision(self) -> None:
        with d_drive_tempdir() as temp:
            agent, store, runner, permit, _ = self.build_world(
                temp,
                policy_overrides={
                    "max_steps": 1,
                    "max_provider_calls": 1,
                    "max_tool_calls": 1,
                },
            )
            model = FinalFromBriefPort()

            result = runner.run_activation(permit, model)
            final_state = store.read_state(RUN_ID)
            agent_state = agent.get_agent_run(RUN_ID)

        self.assertEqual(result.status, "completed")
        self.assertEqual(model.calls, 1)
        self.assertEqual(final_state.provider_calls, 1)
        self.assertEqual(final_state.tool_calls, 0)
        self.assertIs(final_state.status, HostedAgentCellStatus.COMPLETED)
        self.assertIs(agent_state.state, AgentRunState.COMPLETED)

    def test_model_wall_overrun_denies_tool_before_durable_admission(self) -> None:
        with d_drive_tempdir() as temp:
            _, store, runner, permit, _ = self.build_world(
                temp,
                policy_overrides={"max_active_wall_seconds": 0.001},
            )
            model = ReadThenAnswerPort()

            result = runner.run_activation(permit, model)
            state = store.read_state(RUN_ID)
            connection = sqlite3.connect(store.database.path)
            try:
                denied = connection.execute(
                    """SELECT COUNT(*) FROM hosted_tool_requests
                    WHERE decision='denied'"""
                ).fetchone()[0]
                admitted = connection.execute(
                    """SELECT COUNT(*) FROM hosted_tool_requests
                    WHERE decision='admitted'"""
                ).fetchone()[0]
                claims = connection.execute(
                    "SELECT COUNT(*) FROM hosted_tool_execution_claims"
                ).fetchone()[0]
                results = connection.execute(
                    "SELECT COUNT(*) FROM hosted_tool_results"
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(result.status, "checkpointed")
        self.assertEqual(result.failure_code, "active_wall_exhausted")
        self.assertEqual(model.calls, 1)
        self.assertEqual(state.provider_calls, 1)
        self.assertEqual(state.tool_calls, 0)
        self.assertEqual((denied, admitted, claims, results), (1, 0, 0, 0))

    def test_over_cost_final_is_recorded_but_cannot_complete_agent(self) -> None:
        with d_drive_tempdir() as temp:
            agent, store, runner, permit, _ = self.build_world(
                temp,
                policy_overrides={
                    "max_currency_cost_usd": 0.1,
                    "max_provider_call_cost_usd": 0.1,
                },
            )
            model = OverCostFinalPort()

            result = runner.run_activation(permit, model)
            state = store.read_state(RUN_ID)
            projection = agent.get_agent_run(RUN_ID)
            connection = sqlite3.connect(store.database.path)
            try:
                terminal = connection.execute(
                    """SELECT terminal_state, currency_cost_usd, failure_code
                    FROM hosted_model_terminals"""
                ).fetchone()
                intents = connection.execute(
                    "SELECT COUNT(*) FROM hosted_agent_completion_intents"
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(result.status, "checkpointed")
        self.assertEqual(result.failure_code, "ModelCostCeilingExceeded")
        self.assertEqual(model.calls, 1)
        self.assertEqual(state.currency_cost_usd, 0.2)
        self.assertIs(state.status, HostedAgentCellStatus.CHECKPOINTED)
        self.assertIs(projection.state, AgentRunState.ACTIVE)
        self.assertEqual(
            terminal,
            ("failed", 0.2, "ModelCostCeilingExceeded"),
        )
        self.assertEqual(intents, 0)

    def test_agent_database_remains_content_free_after_private_tool_flow(self) -> None:
        brief = (
            "OPERATOR_BRIEF_CANARY_a813 synthetic credential "
            "CREDENTIAL_VALUE_CANARY_244b and path D:\\PRIVATE_PATH_CANARY_72de."
        )
        with d_drive_tempdir() as temp:
            agent, store, runner, permit, _ = self.build_world(
                temp,
                brief=brief,
            )
            workspace = runner.action_gate.tools.root
            (workspace / "docs" / "public.txt").write_text(
                "PUBLIC_RESULT_CANARY_8f31\n",
                encoding="utf-8",
            )
            (workspace / "docs" / ".env").write_text(
                "SECRET_FILE_CANARY_f991\n",
                encoding="utf-8",
            )
            (workspace / "docs" / "secrets").mkdir()
            (workspace / "docs" / "secrets" / "key.txt").write_text(
                "SECRET_FILE_CANARY_f991\n",
                encoding="utf-8",
            )
            model = PrivacyProbePort()

            completed = runner.run_activation(permit, model)
            connection = sqlite3.connect(agent.store.database.path)
            connection.execute("PRAGMA wal_checkpoint(FULL)").fetchall()
            connection.close()
            database_files = tuple(
                path
                for path in (
                    Path(agent.store.database.path),
                    Path(str(agent.store.database.path) + "-wal"),
                    Path(str(agent.store.database.path) + "-shm"),
                )
                if path.is_file()
            )
            database_bytes = b"".join(path.read_bytes() for path in database_files)
            private_blob_bytes = b"".join(
                path.read_bytes() for path in store.blobs.root.rglob("*.bin")
            )
            candidate_bytes = runner.candidate_vault.read(
                completed.candidate.capture_id
            )

        self.assertEqual(completed.status, "completed")
        self.assertEqual(model.calls, 3)
        for canary in (
            b"OPERATOR_BRIEF_CANARY_a813",
            b"CREDENTIAL_VALUE_CANARY_244b",
            b"PRIVATE_PATH_CANARY_72de",
            b'"prefix":"docs"',
            b"PUBLIC_RESULT_CANARY_8f31",
            b"FINAL_CANDIDATE_CANARY_5c27",
            b"SECRET_FILE_CANARY_f991",
        ):
            self.assertNotIn(canary, database_bytes)
        self.assertIn(b"OPERATOR_BRIEF_CANARY_a813", private_blob_bytes)
        self.assertIn(b'"prefix":"docs"', private_blob_bytes)
        self.assertIn(b"PUBLIC_RESULT_CANARY_8f31", private_blob_bytes)
        self.assertNotIn(b"SECRET_FILE_CANARY_f991", private_blob_bytes)
        self.assertEqual(candidate_bytes, b"FINAL_CANDIDATE_CANARY_5c27")

    def fresh_runner(self, agent, store, runner, verifier):
        fresh_store = HostedAgentCellStore(
            agent.store,
            store.blobs,
            verifier,
            now=lambda: NOW,
        )
        action_gate = HostedActionGate(
            runner.action_gate.tools,
            verifier,
            AgentStoreOwnershipVerifier(agent.store, now=lambda: NOW),
        )
        return HostedAgentCellRunner(
            agent,
            fresh_store,
            runner.semantic_projector,
            CandidateVault(
                runner.candidate_vault.root,
                runner.candidate_vault.database.path,
            ),
            action_gate,
            now=lambda: NOW,
        )

    def test_read_tool_then_final_candidate_completes_agent_run(self) -> None:
        with d_drive_tempdir() as temp:
            agent, store, runner, permit, verifier = self.build_world(temp)
            model = ReadThenAnswerPort()

            result = runner.run_activation(permit, model)
            agent_projection = agent.get_agent_run(RUN_ID)
            candidate_bytes = runner.candidate_vault.read(result.candidate.capture_id)
            reopened = HostedAgentCellStore(
                agent.store,
                store.blobs,
                verifier,
                now=lambda: NOW,
            ).read_state(RUN_ID)
            database_files = tuple(
                path
                for path in (
                    Path(agent.store.database.path),
                    Path(str(agent.store.database.path) + "-wal"),
                    Path(str(agent.store.database.path) + "-shm"),
                )
                if path.is_file()
            )
            database_bytes = b"".join(path.read_bytes() for path in database_files)

        self.assertEqual(result.status, "completed")
        self.assertIs(result.cell_state.status, HostedAgentCellStatus.COMPLETED)
        self.assertIs(reopened.status, HostedAgentCellStatus.COMPLETED)
        self.assertIs(agent_projection.state, AgentRunState.COMPLETED)
        self.assertEqual(model.calls, 2)
        self.assertEqual(result.cell_state.provider_calls, 2)
        self.assertEqual(result.cell_state.tool_calls, 1)
        self.assertEqual(candidate_bytes, b"The verified fixture value is 42.")
        self.assertNotIn(b"fixture_value=42", database_bytes)
        self.assertNotIn(b"The verified fixture value is 42.", database_bytes)

    def test_context_cache_hit_then_deletion_rebuilds_identical_bytes(self) -> None:
        with d_drive_tempdir() as temp:
            agent, store, runner, permit, _ = self.build_world(temp)
            state = store.read_state(RUN_ID)
            policy = store.read_policy(RUN_ID)
            request = store.read_semantic_request(RUN_ID)
            projection = runner.semantic_projector.project(request)
            agent_state = agent.get_agent_run(RUN_ID)

            first = runner.context.build(
                permit=permit,
                state=state,
                policy=policy,
                semantic_projection=projection,
                tool_catalog=runner.action_gate.tools.catalog,
                agent_run_epoch=agent_state.epoch,
                agent_state_revision=agent_state.state_revision,
                created_at=NOW.isoformat(),
            )
            second = runner.context.build(
                permit=permit,
                state=state,
                policy=policy,
                semantic_projection=projection,
                tool_catalog=runner.action_gate.tools.catalog,
                agent_run_epoch=agent_state.epoch,
                agent_state_revision=agent_state.state_revision,
                created_at=NOW.isoformat(),
            )
            removed = store.clear_context_cache(RUN_ID)
            rebuilt = runner.context.build(
                permit=permit,
                state=state,
                policy=policy,
                semantic_projection=projection,
                tool_catalog=runner.action_gate.tools.catalog,
                agent_run_epoch=agent_state.epoch,
                agent_state_revision=agent_state.state_revision,
                created_at=NOW.isoformat(),
            )

        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertGreaterEqual(removed, 1)
        self.assertFalse(rebuilt.cache_hit)
        self.assertEqual(rebuilt.payload, first.payload)
        self.assertEqual(rebuilt.envelope_digest, first.envelope_digest)

    def test_checkpoint_rehydrates_with_new_epoch_and_no_prior_replay(self) -> None:
        with d_drive_tempdir() as temp:
            agent, store, runner, permit, verifier = self.build_world(temp)
            checkpoint = runner.checkpoint_activation(permit)
            before = agent.get_agent_run(RUN_ID)
            self.assertIsNone(agent.get_agent_ownership(RUN_ID))
            fresh = self.fresh_runner(agent, store, runner, verifier)
            model = FinalFromBriefPort()

            completed = fresh.rehydrate_and_run(
                RUN_ID,
                "owner:rehydrated",
                ttl_seconds=300,
                model=model,
            )
            after = agent.get_agent_run(RUN_ID)

        self.assertEqual(checkpoint.status, "checkpointed")
        self.assertGreater(after.epoch, before.epoch)
        self.assertEqual(model.calls, 1)
        self.assertEqual(completed.cell_state.provider_calls, 1)
        self.assertIs(completed.cell_state.status, HostedAgentCellStatus.COMPLETED)

    def test_checkpoint_rehydrates_in_fresh_python_process(self) -> None:
        with d_drive_tempdir() as temp:
            agent, store, runner, permit, _ = self.build_world(temp)
            checkpoint = runner.checkpoint_activation(permit)
            config = {
                "agent_db": str(agent.store.database.path),
                "blob_root": str(store.blobs.root),
                "candidate_root": str(runner.candidate_vault.root),
                "runtime_db": str(runner.candidate_vault.database.path),
                "workspace": str(runner.action_gate.tools.root),
                "authority_digest": agent.get_agent_run(
                    RUN_ID
                ).initial_header.authority.reference.digest,
                "agent_run_id": RUN_ID,
            }
            environment = {
                **os.environ,
                "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
            }
            worker = (
                Path(__file__).resolve().parent
                / "helpers"
                / "hosted_agent_rehydrate_worker.py"
            )
            completed = subprocess.run(
                [sys.executable, str(worker)],
                input=json.dumps(config),
                text=True,
                capture_output=True,
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                timeout=30,
                check=False,
            )
            final_state = store.read_state(RUN_ID)

        self.assertEqual(checkpoint.status, "checkpointed")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout)["status"],
            "completed",
        )
        self.assertIs(final_state.status, HostedAgentCellStatus.COMPLETED)

    def test_second_rehydration_owner_loses_before_cell_mutation(self) -> None:
        with d_drive_tempdir() as temp:
            agent, store, runner, permit, _ = self.build_world(temp)
            checkpoint = runner.checkpoint_activation(permit)
            projection = agent.get_agent_run(RUN_ID)
            first = agent.acquire_agent_run(
                RUN_ID,
                "owner:first-rehydrator",
                expected_revision=projection.state_revision,
                expected_epoch=projection.epoch,
                ttl_seconds=300,
            )
            after_first = agent.get_agent_run(RUN_ID)
            with self.assertRaises(AgentOwnershipConflictError):
                agent.acquire_agent_run(
                    RUN_ID,
                    "owner:second-rehydrator",
                    expected_revision=after_first.state_revision,
                    expected_epoch=after_first.epoch,
                    ttl_seconds=300,
                )
            before_rehydrate = store.read_state(RUN_ID)
            rehydrated = store.rehydrate(first, checkpoint.checkpoint_digest)

        self.assertIs(
            before_rehydrate.status,
            HostedAgentCellStatus.CHECKPOINTED,
        )
        self.assertIs(rehydrated.status, HostedAgentCellStatus.RUNNING)

    def test_malformed_received_decision_preserves_cost_and_stops(self) -> None:
        with d_drive_tempdir() as temp:
            _, store, runner, permit, _ = self.build_world(
                temp,
                policy_overrides={
                    "max_currency_cost_usd": 0.25,
                    "max_provider_call_cost_usd": 0.25,
                },
            )
            model = MalformedPaidPort()

            result = runner.run_activation(permit, model)
            state = store.read_state(RUN_ID)
            connection = sqlite3.connect(store.database.path)
            terminal = connection.execute(
                """SELECT terminal_state, currency_cost_usd,
                          network_attempted, response_received
                FROM hosted_model_terminals"""
            ).fetchone()
            connection.close()

        self.assertEqual(result.status, "checkpointed")
        self.assertEqual(result.failure_code, "HostedModelProtocolError")
        self.assertEqual(model.calls, 1)
        self.assertEqual(state.provider_calls, 1)
        self.assertEqual(state.tool_calls, 0)
        self.assertEqual(state.currency_cost_usd, 0.25)
        self.assertEqual(terminal, ("failed", 0.25, 1, 1))

    def test_pending_model_dispatch_enters_reconciliation_without_retry(self) -> None:
        with d_drive_tempdir() as temp:
            agent, store, runner, permit, _ = self.build_world(temp)
            state = store.read_state(RUN_ID)
            policy = store.read_policy(RUN_ID)
            semantic = runner.semantic_projector.project(
                store.read_semantic_request(RUN_ID)
            )
            agent_state = agent.get_agent_run(RUN_ID)
            context = runner.context.build(
                permit=permit,
                state=state,
                policy=policy,
                semantic_projection=semantic,
                tool_catalog=runner.action_gate.tools.catalog,
                agent_run_epoch=agent_state.epoch,
                agent_state_revision=agent_state.state_revision,
                created_at=NOW.isoformat(),
            )
            request = HostedModelRequest(
                provider_invocation_id=("66666666-6666-4666-8666-666666666666"),
                agent_run_id=RUN_ID,
                agent_run_epoch=agent_state.epoch,
                agent_state_revision=agent_state.state_revision,
                step_index=state.next_step,
                provider_id=policy.provider_id,
                model_id=policy.model_id,
                context_blob_ref=context.blob.blob_ref,
                context_digest=context.envelope_digest,
                context_bytes=len(context.payload),
                policy_digest=policy.policy_digest,
                model_token_policy_digest=(policy.model_token_policy_digest),
                provider_execution_profile_digest=(
                    policy.provider_execution_profile_digest
                ),
                prompt_compiler_version=policy.prompt_compiler_version,
                delegation_class=policy.delegation_class,
                privacy=policy.privacy,
                provider_tier_binding_digest=(policy.provider_tier_binding_digest),
                project_binding_digest=policy.project_binding_digest,
                admission_lane=policy.admission_lane,
                provider_admission_policy_digest=(
                    policy.provider_admission_policy_digest
                ),
                max_latency_s=policy.max_latency_s,
                max_output_tokens=policy.max_output_tokens,
                max_provider_context_tokens=(policy.max_provider_context_tokens),
                cost_ceiling_usd=policy.max_provider_call_cost_usd,
            )
            store.begin_model_attempt(permit, request)
            never = NeverCallPort()

            result = runner.run_activation(permit, never)
            ownership_after = agent.get_agent_ownership(RUN_ID)

        self.assertEqual(result.status, "reconciliation_required")
        self.assertEqual(never.calls, 0)
        self.assertIs(
            result.cell_state.status,
            HostedAgentCellStatus.RECONCILIATION_REQUIRED,
        )
        self.assertIsNone(ownership_after)

    def test_self_consistent_projection_tamper_is_rejected_by_event_replay(
        self,
    ) -> None:
        with d_drive_tempdir() as temp:
            _, store, _, _, _ = self.build_world(temp)
            current = store.read_state(RUN_ID)
            forged = replace(current, provider_calls=1)
            connection = sqlite3.connect(store.database.path)
            connection.execute(
                """UPDATE hosted_agent_cells
                SET provider_calls=?, state_digest=? WHERE agent_run_id=?""",
                (forged.provider_calls, forged.state_digest, RUN_ID),
            )
            connection.commit()
            connection.close()

            with self.assertRaisesRegex(
                HostedAgentCellStateError,
                "event history",
            ):
                store.read_state(RUN_ID)

    def test_cache_row_cannot_substitute_a_context_blob(self) -> None:
        with d_drive_tempdir() as temp:
            agent, store, runner, permit, _ = self.build_world(temp)
            state = store.read_state(RUN_ID)
            policy = store.read_policy(RUN_ID)
            semantic = runner.semantic_projector.project(
                store.read_semantic_request(RUN_ID)
            )
            agent_state = agent.get_agent_run(RUN_ID)
            first = runner.context.build(
                permit=permit,
                state=state,
                policy=policy,
                semantic_projection=semantic,
                tool_catalog=runner.action_gate.tools.catalog,
                agent_run_epoch=agent_state.epoch,
                agent_state_revision=agent_state.state_revision,
                created_at=NOW.isoformat(),
            )
            connection = sqlite3.connect(store.database.path)
            context_blob = connection.execute(
                """SELECT blob_ref FROM hosted_agent_blobs
                WHERE agent_run_id=? AND role='context' LIMIT 1""",
                (RUN_ID,),
            ).fetchone()[0]
            connection.execute(
                """UPDATE hosted_context_envelopes SET blob_ref=?
                WHERE envelope_digest=?""",
                (context_blob, first.envelope_digest),
            )
            connection.commit()
            connection.close()

            with self.assertRaisesRegex(
                HostedAgentCellStateError,
                "crosses AgentRun or role",
            ):
                runner.context.build(
                    permit=permit,
                    state=state,
                    policy=policy,
                    semantic_projection=semantic,
                    tool_catalog=runner.action_gate.tools.catalog,
                    agent_run_epoch=agent_state.epoch,
                    agent_state_revision=agent_state.state_revision,
                    created_at=NOW.isoformat(),
                )

    def test_checkpoint_body_swap_fails_exact_digest_binding(self) -> None:
        with d_drive_tempdir() as temp:
            agent, store, runner, permit, _ = self.build_world(temp)
            checkpointed = runner.checkpoint_activation(permit)
            connection = sqlite3.connect(store.database.path)
            original_json = connection.execute(
                "SELECT checkpoint_json FROM hosted_agent_checkpoints"
            ).fetchone()[0]
            original = AgentCheckpoint.from_dict(json.loads(original_json))
            forged = replace(
                original,
                checkpoint_id="77777777-7777-4777-8777-777777777777",
            )
            connection.execute(
                "UPDATE hosted_agent_checkpoints SET checkpoint_json=?",
                (json.dumps(forged.to_public_dict(), sort_keys=True),),
            )
            connection.commit()
            connection.close()
            projection = agent.get_agent_run(RUN_ID)
            new_permit = agent.acquire_agent_run(
                RUN_ID,
                "owner:checkpoint-attack",
                expected_revision=projection.state_revision,
                expected_epoch=projection.epoch,
                ttl_seconds=300,
            )

            with self.assertRaises(HostedAgentCheckpointError):
                store.rehydrate(
                    new_permit,
                    checkpointed.checkpoint_digest,
                )

    def test_completion_crash_points_recover_without_model_replay(self) -> None:
        for fault in (
            "after_completion_intent",
            "after_candidate_capture",
            "after_cell_completion_prepare",
            "after_agent_run_complete",
        ):
            with self.subTest(fault=fault), d_drive_tempdir() as temp:
                agent, store, runner, permit, verifier = self.build_world(temp)
                model = ReadThenAnswerPort()

                def inject(name):
                    if name == fault:
                        raise RuntimeError(fault)

                with mock.patch.object(runner, "_fault", side_effect=inject):
                    with self.assertRaisesRegex(RuntimeError, fault):
                        runner.run_activation(permit, model)

                fresh = self.fresh_runner(agent, store, runner, verifier)
                never = NeverCallPort()
                projection = agent.get_agent_run(RUN_ID)
                if projection.state is AgentRunState.COMPLETED:
                    recovered = fresh.recover_terminal_completion(RUN_ID)
                else:
                    current_owner = agent.get_agent_ownership(RUN_ID)
                    if current_owner is not None:
                        agent.release_agent_run(current_owner)
                    projection = agent.get_agent_run(RUN_ID)
                    recovery_permit = agent.acquire_agent_run(
                        RUN_ID,
                        "owner:completion-recovery",
                        expected_revision=projection.state_revision,
                        expected_epoch=projection.epoch,
                        ttl_seconds=300,
                    )
                    recovered = fresh.run_activation(recovery_permit, never)
                connection = sqlite3.connect(runner.candidate_vault.database.path)
                capture_count = connection.execute(
                    """SELECT COUNT(*) FROM candidate_captures
                    WHERE provider_id='hosted_agent_cell'"""
                ).fetchone()[0]
                connection.close()

                self.assertEqual(model.calls, 2)
                self.assertEqual(never.calls, 0)
                self.assertEqual(recovered.status, "completed")
                self.assertEqual(capture_count, 1)
                self.assertIs(
                    agent.get_agent_run(RUN_ID).state,
                    AgentRunState.COMPLETED,
                )

    def test_completion_recovery_rejects_same_bytes_with_foreign_provenance(
        self,
    ) -> None:
        with d_drive_tempdir() as temp:
            agent, store, runner, permit, _ = self.build_world(temp)
            model = FinalFromBriefPort()

            def inject(name):
                if name == "after_completion_intent":
                    raise RuntimeError(name)

            with mock.patch.object(runner, "_fault", side_effect=inject):
                with self.assertRaisesRegex(RuntimeError, "after_completion_intent"):
                    runner.run_activation(permit, model)
            intent = store.read_completion_intent(RUN_ID)
            self.assertIsNotNone(intent)
            runner.candidate_vault.capture(
                "hosted_agent_cell",
                intent["candidate_run_id"],
                b"Checkpoint continuity is intact.",
                task_digest="f" * 64,
                approval_digest="e" * 64,
            )

            with self.assertRaisesRegex(
                HostedAgentCellStateError,
                "provenance",
            ):
                runner.run_activation(permit, NeverCallPort())
            projection = agent.get_agent_run(RUN_ID)
            state = store.read_state(RUN_ID)

        self.assertIs(projection.state, AgentRunState.ACTIVE)
        self.assertIs(state.status, HostedAgentCellStatus.RUNNING)


if __name__ == "__main__":
    unittest.main()
