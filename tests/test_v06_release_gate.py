from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "scripts" / "verify-v06.ps1"
SUMMARY = ROOT / "tests" / "helpers" / "v06_gate_summary.py"


class V06ReleaseGateTests(unittest.TestCase):
    def test_a1_docs_bind_model_local_tokens_t1_operability_and_offline_route(self) -> None:
        active = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                ROOT / "README.md",
                ROOT / "docs" / "ARCHITECTURE.md",
                ROOT / "docs" / "DIRECT_CHAT.md",
                ROOT / "docs" / "PROVIDER_STATUS.md",
                ROOT / "docs" / "STORAGE_AND_MIGRATION.md",
                ROOT / "docs" / "PROVENANCE.md",
            )
        )
        for marker in (
            "0.7.0a0",
            "0.6.0a1",
            "model-token-policies.sqlite3",
            "grok-4.6",
            "400,000",
            "glm-5.3-flash",
            "512,000",
            "MiniMax-M2.7",
            "2,048",
            "Qwythos-9B-v2",
            "8,192",
            "queue-status",
            "t1-stage",
            "t1-worker",
            "reconciliation_required",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, active)
        checkpoint = (ROOT / "docs" / "V060A1_OFFLINE_CHECKPOINT.md").read_text(
            encoding="utf-8"
        )
        runbook = (ROOT / "docs" / "V060A1_LIVE_GATE_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        for marker in (
            "offline-only",
            "initial concurrent census RED",
            "quiet-window GREEN",
            "three-process complete-path mock",
            "NotMeasured",
            "no live provider call",
        ):
            self.assertIn(marker, checkpoint)
        for marker in (
            "USD 0.005",
            "USD 0.015",
            "USD 0.020",
            "128,000",
            "8,192",
            "no retry",
            "exact live manifest",
            "not authorized",
        ):
            self.assertIn(marker, runbook)

    def test_verifier_names_every_required_offline_gate(self) -> None:
        text = VERIFY.read_text(encoding="utf-8")
        for marker in (
            "verify.ps1",
            "test_multiprocess_runtime",
            "test_observatory_db",
            "test_openrouter_discovery",
            "test_planning_contracts",
            "test_model_identity",
            "test_qualification",
            "test_target_leases",
            "test_t1_manifest",
            "test_t1_dispatcher",
            "test_accounting",
            "test_differential",
            "Test-MacrQuietCensus.ps1",
            "ConsecutiveZeroSamples",
            "MACR_V06_QUIET_CENSUS",
            "diff --check",
            "network_activity",
            "V06_SUMMARY=",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)
        quiet = (ROOT / "scripts" / "Test-MacrQuietCensus.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("Test-MacrInvokerProcesses.ps1", quiet)

    def test_summary_is_content_free_deterministic_and_exact_schema_bound(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SUMMARY)],
            cwd=ROOT,
            env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")},
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        document = json.loads(completed.stdout)
        self.assertEqual(document["runtime_schema_version"], 7)
        self.assertEqual(document["observatory_schema_version"], 2)
        self.assertEqual(document["accounting_schema_version"], 3)
        self.assertEqual(document["version"], "0.7.0a0")
        self.assertEqual(document["direct_conversation_schema_version"], 2)
        self.assertEqual(document["model_token_policy_schema_version"], 1)
        self.assertEqual(document["model_token_policy_count"], 7)
        self.assertEqual(document["provider_capability_policy_schema_version"], 1)
        self.assertEqual(document["provider_capability_policy_count"], 2)
        self.assertEqual(document["t1_manifest_schema_version"], 2)
        self.assertRegex(
            document["provider_capability_policy_digest"],
            r"^[0-9a-f]{64}$",
        )
        self.assertEqual(document["t1_complete_path_processes"], 3)
        self.assertEqual(document["quiet_census_samples"], 5)
        self.assertFalse(document["network_activity"])
        self.assertFalse(document["provider_generation"])
        self.assertEqual(document["queue_worker_counts"], [1, 2, 3, 4, 8])
        self.assertEqual(document["sqlite_bootstrap_processes"], 32)
        self.assertRegex(document["planner_replay_digest"], r"^[0-9a-f]{64}$")
        self.assertRegex(document["summary_digest"], r"^[0-9a-f]{64}$")
        forbidden = ("prompt", "answer", "credential", "api_key")
        encoded = completed.stdout.casefold()
        self.assertTrue(all(item not in encoded for item in forbidden))

    def test_checkpoint_and_live_runbook_keep_authority_boundaries_explicit(self) -> None:
        live = (ROOT / "docs" / "V06_LIVE_GATE_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        for marker in (
            "未執行",
            "80AF74FB9FB20FF805E168F13A40E4DC585DA20AEA3778347FDDE6CC29128299",
            "74",
            "census",
            "T0",
            "T1",
            "three-member",
            "差分",
            "不得自動重試",
            "不授權",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, live)
        active_docs = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                ROOT / "README.md",
                ROOT / "docs" / "ARCHITECTURE.md",
                ROOT / "docs" / "STORAGE_AND_MIGRATION.md",
            )
        )
        self.assertIn("runtime operational SQLite 7", active_docs)
        self.assertIn("verify-v06.ps1", active_docs)
        checkpoint = (ROOT / "docs" / "V06_OFFLINE_CHECKPOINT.md").read_text(
            encoding="utf-8"
        )
        for marker in (
            "historical rejected candidate",
            "6c66eff1ce200c4d07506310794ea9ac89a42895",
            "5172fb7b0d72d3a733ec06bf7aa1d7f598b68e2f",
            "443 passed",
            "106 passed",
            "38b6087445be0e0232bf4f415d87ccd7fe2adbb4dc5ddc18af80ff5b0a680832",
            "twin Critical                  0",
            "twin Important                 0",
        ):
            with self.subTest(checkpoint_marker=marker):
                self.assertIn(marker, checkpoint)
        release = (ROOT / "docs" / "V06_RELEASE.md").read_text(
            encoding="utf-8"
        )
        for marker in (
            "v0.6.0a0",
            "feature/macr-v0.5-direct-chat-ui",
            "publication branch   main",
            "offline candidate",
            "no configured Git remote",
            "unexecuted live gate",
        ):
            with self.subTest(release_marker=marker):
                self.assertIn(marker, release)


if __name__ == "__main__":
    unittest.main()
