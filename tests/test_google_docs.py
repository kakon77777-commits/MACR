from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GoogleDocumentationTests(unittest.TestCase):
    def test_docs_name_exact_active_and_disabled_models(self) -> None:
        text = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in (
                "README.md",
                "docs/ARCHITECTURE.md",
                "docs/PROVIDER_STATUS.md",
            )
        )
        for value in (
            "gemini-3.7-flash",
            "gemini-3.1-flash-image",
            "google_veo_fast",
            "google_tts",
            "google_lyria",
            r"D:\AI_RESIDENCE\AI_Runtime\macr-state\artifacts\google",
            "MODEL != RESIDENT",
        ):
            self.assertIn(value, text)

    def test_docs_do_not_claim_promotional_credits_guarantee_free_use(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        self.assertNotIn("credits guarantee free", text)
        self.assertIn("cloud billing", text)

    def test_secret_scan_includes_gitignored_files(self) -> None:
        text = (ROOT / "scripts" / "verify.ps1").read_text(encoding="utf-8")
        self.assertIn("--no-ignore", text)


if __name__ == "__main__":
    unittest.main()
