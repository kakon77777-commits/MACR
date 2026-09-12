from __future__ import annotations

import importlib
import json
import shutil
import subprocess
import unittest
from pathlib import Path

import macr_runtime.agent.cell as cell


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests/gates/v07_hosted_agent_cell_contract_manifest.json"


class V07HostedAgentCellGateTests(unittest.TestCase):
    def test_wrapper_manifest_is_exact_offline_and_non_release(self) -> None:
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        self.assertIsNotNone(powershell)
        completed = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-File",
                str(ROOT / "scripts/verify-v07-hosted-agent-cell.ps1"),
                "-ManifestOnly",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        lines = [line for line in completed.stdout.splitlines() if line]
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("HOSTED_AGENT_CELL_MANIFEST="))
        document = json.loads(lines[0].removeprefix("HOSTED_AGENT_CELL_MANIFEST="))
        self.assertEqual(
            document["contract_manifest"],
            "tests/gates/v07_hosted_agent_cell_contract_manifest.json",
        )
        self.assertEqual(
            document["inherited_gate"],
            "scripts/verify-v07-phase-c.ps1",
        )
        self.assertFalse(document["network_activity"])
        self.assertFalse(document["provider_generation"])
        self.assertFalse(document["shared_state_migration"])
        self.assertFalse(document["shared_policy_activation"])
        self.assertFalse(document["canonical_v070a1_closed"])

    def test_required_tests_exist_and_are_not_skipped(self) -> None:
        document = json.loads(MANIFEST.read_text(encoding="utf-8"))
        identifiers = [item["id"] for item in document["required"]]
        tests = [item["test"] for item in document["required"]]
        self.assertEqual(
            document["schema"],
            "macr-v07-hosted-agent-cell-test-manifest/v1",
        )
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(len(tests), len(set(tests)))
        for entry in document["required"]:
            module_name, class_name, method_name = entry["test"].rsplit(".", 2)
            module = importlib.import_module(module_name)
            method = getattr(getattr(module, class_name), method_name)
            self.assertTrue(callable(method), entry["id"])
            self.assertFalse(getattr(method, "__unittest_skip__", False), entry["id"])

    def test_public_cell_exports_are_exactly_available(self) -> None:
        expected = {
            "HostedAgentCellPolicy",
            "HostedAgentCellRunner",
            "HostedAgentCellStore",
            "HostedWorkspaceTools",
            "MacrRuntimeHostedModelPort",
            "HostedTurnPreparation",
            "HOSTED_TURN_PROMPT_COMPILER_VERSION",
        }
        self.assertTrue(expected <= set(cell.__all__))
        for name in expected:
            self.assertTrue(hasattr(cell, name), name)
        self.assertFalse(hasattr(cell, "AutomaticRetry"))
        self.assertFalse(hasattr(cell, "AutonomousAcceptance"))


if __name__ == "__main__":
    unittest.main()
