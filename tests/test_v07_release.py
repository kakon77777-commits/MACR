from __future__ import annotations

import json
import tomllib
import unittest
from pathlib import Path

import macr_runtime


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.7.0a0"


class V07PhaseCAlphaReleaseTests(unittest.TestCase):
    def test_active_runtime_and_operator_surfaces_use_one_phase_c_alpha_version(self) -> None:
        project = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(project["project"]["version"], VERSION)
        self.assertEqual(macr_runtime.__version__, VERSION)
        active = {
            "cli": ROOT / "src/macr_runtime/cli.py",
            "launcher": ROOT / "src/macr_runtime/direct_launcher.py",
            "ui": ROOT / "src/macr_runtime/direct_ui/index.html",
            "shortcut": ROOT / "scripts/install-direct-chat-shortcut.ps1",
            "readme": ROOT / "README.md",
            "architecture": ROOT / "docs/ARCHITECTURE.md",
            "direct": ROOT / "docs/DIRECT_CHAT.md",
            "provider": ROOT / "docs/PROVIDER_STATUS.md",
            "storage": ROOT / "docs/STORAGE_AND_MIGRATION.md",
        }
        for name, path in active.items():
            with self.subTest(surface=name):
                self.assertIn(VERSION, path.read_text(encoding="utf-8"))
        config = json.loads(
            (ROOT / "config/providers.json").read_text(encoding="utf-8")
        )
        disabled = "\n".join(
            item.get("disabled_reason") or "" for item in config["providers"]
        )
        self.assertIn(VERSION, disabled)

    def test_release_record_is_bound_to_phase_c_and_preserves_a1_reservation(self) -> None:
        release = (ROOT / "docs/V070A0_PHASE_C_RELEASE.md").read_text(
            encoding="utf-8"
        )
        for marker in (
            "MACR v0.7 Phase-C Alpha",
            "0.7.0a0",
            "84a562fe58de8a279d427f6dd33ddc05410d1b1c",
            "b0bbbc2210e50d47d6447d1e7bdf32c4aaa2e05f",
            "0.7.0a1",
            "Phase D",
            "NOT STARTED",
            "Agent loop",
            "NOT IMPLEMENTED",
            "Live use",
            "NOT MEASURED",
            "v0.7.0a0",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, release)
        provenance = (ROOT / "docs/PROVENANCE.md").read_text(encoding="utf-8")
        self.assertIn("v0.7.0a0 Phase-C Alpha release", provenance)
        self.assertIn("0.7.0a1 remains reserved", provenance)

    def test_claude_code_direct_provider_access_is_deferred_not_activated(self) -> None:
        provider = (ROOT / "docs/PROVIDER_STATUS.md").read_text(encoding="utf-8")
        release = (ROOT / "docs/V070A0_PHASE_C_RELEASE.md").read_text(
            encoding="utf-8"
        )
        combined = provider + "\n" + release
        for marker in (
            "Claude Code direct provider access",
            "deferred",
            "subscription-client",
            "ANTHROPIC_API_KEY",
            "same provider registry",
            "accounting",
            "NotMeasured",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, combined)
        config = json.loads(
            (ROOT / "config/providers.json").read_text(encoding="utf-8")
        )
        claude = next(
            item for item in config["providers"]
            if item["id"] == "claude_subscription"
        )
        self.assertFalse(claude["enabled"])
        self.assertFalse(claude["api_usage_allowed"])


if __name__ == "__main__":
    unittest.main()
