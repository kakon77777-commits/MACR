from __future__ import annotations

import json
import multiprocessing
import unittest
from dataclasses import replace

from macr_runtime.agent.cell import (
    HostedAgentCellPolicy,
    HostedAgentCellSchema,
    HostedDecisionKind,
    HostedModelDecision,
)
from macr_runtime.agent.cell.errors import HostedAgentCellStateError
from macr_runtime.agent.database import AgentDatabase
from macr_runtime.contracts import DelegationClass, PrivacyLevel
from tests.support import d_drive_tempdir


RUN_ID = "11111111-1111-4111-8111-111111111111"
CELL_TABLES = {
    "hosted_agent_cells",
    "hosted_agent_cell_events",
    "hosted_agent_blobs",
    "hosted_context_sections",
    "hosted_context_envelopes",
    "hosted_model_dispatches",
    "hosted_model_terminals",
    "hosted_tool_requests",
    "hosted_tool_results",
    "hosted_tool_execution_claims",
    "hosted_agent_checkpoints",
    "hosted_agent_rehydrations",
    "hosted_agent_completions",
    "hosted_agent_completion_intents",
}


def _hosted_schema_bootstrap_worker(path: str, start_event, results) -> None:
    start_event.wait(timeout=30)
    try:
        database = AgentDatabase(path)
        schema = HostedAgentCellSchema(database)
        connection = database.connect()
        try:
            versions = tuple(
                tuple(row)
                for row in connection.execute(
                    "SELECT component, version FROM schema_meta ORDER BY component"
                )
            )
        finally:
            connection.close()
        results.put(("ok", schema.SCHEMA_VERSION, versions))
    except Exception as exc:  # pragma: no cover - parent reports exact failure
        results.put((type(exc).__name__, str(exc)))


def ids():
    values = iter(
        (
            "22222222-2222-4222-8222-222222222222",
            "33333333-3333-4333-8333-333333333333",
        )
    )
    return lambda: next(values)


class HostedAgentCellContractTests(unittest.TestCase):
    def test_schema_is_separate_exact_and_version_tamper_fails_closed(self) -> None:
        with d_drive_tempdir() as temp:
            database = AgentDatabase(temp / "agent.sqlite3")
            schema = HostedAgentCellSchema(database)
            connection = database.connect()
            try:
                versions = {
                    row["component"]: row["version"]
                    for row in connection.execute(
                        "SELECT component, version FROM schema_meta"
                    )
                }
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name LIKE 'hosted_%'"
                    )
                }
                connection.execute(
                    "UPDATE schema_meta SET version=2 "
                    "WHERE component='hosted_agent_cell'"
                )
            finally:
                connection.close()

            with self.assertRaisesRegex(
                HostedAgentCellStateError,
                "schema version",
            ):
                HostedAgentCellSchema(database)

        self.assertIs(schema.database, database)
        self.assertEqual(
            versions,
            {"agent_runtime": 2, "hosted_agent_cell": 1},
        )
        self.assertEqual(tables, CELL_TABLES)

    def test_fresh_schema_bootstrap_is_safe_for_32_synchronized_processes(self) -> None:
        context = multiprocessing.get_context("spawn")
        with d_drive_tempdir() as temp:
            path = temp / "agent.sqlite3"
            start_event = context.Event()
            results = context.Queue()
            processes = [
                context.Process(
                    target=_hosted_schema_bootstrap_worker,
                    args=(str(path), start_event, results),
                )
                for _ in range(32)
            ]
            for process in processes:
                process.start()
            start_event.set()
            observations = [results.get(timeout=60) for _ in processes]
            for process in processes:
                process.join(timeout=60)
                self.assertEqual(process.exitcode, 0)
            results.close()

        expected_versions = (
            ("agent_runtime", 2),
            ("hosted_agent_cell", 1),
        )
        self.assertEqual(
            observations,
            [("ok", 1, expected_versions)] * 32,
        )

    def test_model_proposal_whitespace_is_compiled_by_host(self) -> None:
        compact = b'{"kind":"tool_request","tool_id":"workspace.read_text","arguments":{"path":"docs/a.txt"}}'
        spaced = b"""{
          "kind": "tool_request",
          "tool_id": "workspace.read_text",
          "arguments": { "path": "docs/a.txt" }
        }"""

        first = HostedModelDecision.from_json_bytes(compact, id_factory=ids())
        second = HostedModelDecision.from_json_bytes(spaced, id_factory=ids())

        self.assertIs(first.kind, HostedDecisionKind.TOOL_REQUEST)
        self.assertEqual(first.proposal_digest, second.proposal_digest)
        self.assertEqual(first.decision_digest, second.decision_digest)
        self.assertEqual(
            HostedModelDecision.from_private_dict(first.to_private_dict()),
            first,
        )

    def test_model_cannot_supply_host_ids_or_digests(self) -> None:
        forged = {
            "kind": "tool_request",
            "tool_id": "workspace.read_text",
            "arguments": {"path": "docs/a.txt"},
            "decision_id": "22222222-2222-4222-8222-222222222222",
            "decision_digest": "a" * 64,
        }
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            HostedModelDecision.from_json_bytes(json.dumps(forged).encode("utf-8"))

    def test_model_grammar_rejects_fence_prose_multiple_and_duplicates(self) -> None:
        invalid = (
            b'```json\n{"kind":"final_candidate"}\n```',
            b'Here is JSON: {"kind":"final_candidate"}',
            b'{"kind":"final_candidate"}{"kind":"final_candidate"}',
            b'{"kind":"tool_request","kind":"final_candidate"}',
        )
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                HostedModelDecision.from_json_bytes(raw)

    def test_policy_is_exact_provider_local_and_finitely_bounded(self) -> None:
        policy = HostedAgentCellPolicy(
            agent_run_id=RUN_ID,
            provider_id="grok",
            model_id="grok-4.6",
            model_token_policy_digest="a" * 64,
            provider_execution_profile_digest="f" * 64,
            prompt_compiler_version="macr-hosted-context-turn/v1",
            project_ref="project:test",
            delegation_class=DelegationClass.NON_SENSITIVE_ROUTINE,
            privacy=PrivacyLevel.INTERNAL_APPROVED,
            provider_tier_binding_digest=None,
            project_binding_digest=None,
            admission_lane=None,
            provider_admission_policy_digest=None,
            tool_catalog_digest="b" * 64,
            allowed_tool_ids=("workspace.read_text",),
            max_steps=8,
            max_provider_calls=8,
            max_tool_calls=4,
            max_active_wall_seconds=600,
            max_currency_cost_usd=1.0,
            max_provider_call_cost_usd=0.25,
            max_latency_s=900,
            max_output_tokens=65_536,
            max_provider_context_tokens=400_000,
            max_context_bytes=1_000_000,
            max_raw_model_response_bytes=200_000,
            max_tool_result_bytes=500_000,
            max_final_output_bytes=500_000,
        )

        self.assertEqual(
            HostedAgentCellPolicy.from_dict(policy.to_public_dict()),
            policy,
        )
        self.assertEqual(policy.provider_id, "grok")
        self.assertEqual(policy.max_steps, 8)
        with self.assertRaisesRegex(ValueError, "per-call"):
            replace(
                policy,
                max_currency_cost_usd=0.1,
                max_provider_call_cost_usd=0.2,
            )
        with self.assertRaisesRegex(ValueError, "opaque"):
            replace(
                policy,
                project_ref=r"D:\\private-project",
            )


if __name__ == "__main__":
    unittest.main()
