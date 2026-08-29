from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "superpowers" / "specs" / "2026-08-28-macr-v0.6-dynamic-coordination-design.md"
PLAN = ROOT / "docs" / "superpowers" / "plans" / "2026-08-28-macr-v0.6-dynamic-coordination.md"


class V06BaselineTests(unittest.TestCase):
    def test_design_binds_exact_a4_checkpoint_and_sealed_legacy_source(self) -> None:
        text = DESIGN.read_text(encoding="utf-8")
        self.assertIn(
            "8b897eadb0f2f82ff02676ff5ead017067d6bb85",
            text,
        )
        self.assertIn(
            "7b938ca69652c876b9be1c5cbebc80a7971e2921",
            text,
        )
        self.assertIn("version            = 0.5.0a4", text)
        self.assertIn("legacy JSONL       = 74 parsed/distinct events", text)
        self.assertIn(
            "80AF74FB9FB20FF805E168F13A40E4DC585DA20AEA3778347FDDE6CC29128299",
            text,
        )
        self.assertIn("legacy read-only   = true", text)

    def test_plan_uses_a4_integration_and_does_not_repeat_stale_68_event_runbook(self) -> None:
        text = PLAN.read_text(encoding="utf-8")
        self.assertIn(
            "8b897eadb0f2f82ff02676ff5ead017067d6bb85",
            text,
        )
        self.assertIn("0.5.0a4 != 0.6.0a0", text)
        self.assertNotIn("exact 68-event reconciliation", text)
        self.assertIn("verify the existing sealed 74-event source", text)

    def test_a4_direct_plane_sources_remain_in_v06_baseline(self) -> None:
        required = (
            "src/macr_runtime/direct_runtime.py",
            "src/macr_runtime/direct_server.py",
            "src/macr_runtime/direct_store.py",
            "src/macr_runtime/direct_ui/index.html",
            "scripts/start-direct-chat.ps1",
            "scripts/install-direct-chat-shortcut.ps1",
        )
        self.assertEqual(
            [relative for relative in required if not (ROOT / relative).is_file()],
            [],
        )


if __name__ == "__main__":
    unittest.main()
