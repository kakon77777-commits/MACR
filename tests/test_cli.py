from __future__ import annotations

import contextlib
import io
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from macr_runtime.cli import _doctor, _invoke
from tests.support import d_drive_tempdir, write_fake_google_credential


ROOT = Path(__file__).resolve().parents[1]


class DoctorTests(unittest.TestCase):
    def test_strict_ignores_intentionally_disabled_providers(self) -> None:
        with d_drive_tempdir() as temp:
            credential = write_fake_google_credential(temp / "credential.json")
            environment = {
                "MINIMAX_API_KEY": "test-key",
                "MINIMAX_BASE_URL": "https://api.minimax.io/v1",
                "MINIMAX_MODEL": "test-model",
                "XAI_API_KEY": "test-key",
                "ZAI_API_KEY": "test-id." + "test-secret",
                "GOOGLE_APPLICATION_CREDENTIALS": str(credential),
                "GOOGLE_CLOUD_PROJECT": "test-project",
            }
            output = io.StringIO()
            with patch.dict(os.environ, environment, clear=False):
                with contextlib.redirect_stdout(output):
                    status = _doctor(
                        str(ROOT / "config" / "providers.json"),
                        strict=True,
                    )
        self.assertEqual(status, 0)
        self.assertNotIn("test-key", output.getvalue())

    def test_strict_fails_when_enabled_provider_is_not_ready(self) -> None:
        without_minimax = {
            key: value
            for key, value in os.environ.items()
            if key not in {"MINIMAX_API_KEY", "MINIMAX_BASE_URL", "MINIMAX_MODEL"}
        }
        with patch.dict(os.environ, without_minimax, clear=True):
            with contextlib.redirect_stdout(io.StringIO()):
                status = _doctor(str(ROOT / "config" / "providers.json"), strict=True)
        self.assertEqual(status, 2)

    def test_invoke_requires_explicit_network_opt_in_before_reading_task(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = _invoke(
                "minimax",
                "this-file-must-not-be-read.json",
                str(ROOT / "config" / "providers.json"),
                allow_network=False,
                allow_local=False,
            )
        self.assertEqual(status, 3)
        self.assertIn("network_opt_in_required", output.getvalue())

    def test_local_provider_requires_local_opt_in_before_reading_task(self) -> None:
        output = io.StringIO()
        state_root = ROOT / "state-must-not-be-created"
        environment = {
            "MACR_ROOT": str(ROOT),
            "MACR_STATE_ROOT": str(state_root),
            "CODEX_HOME_TARGET": r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
        }
        with patch.dict(os.environ, environment, clear=False):
            with contextlib.redirect_stdout(output):
                status = _invoke(
                    "ollama_qwythos",
                    "this-file-must-not-be-read.json",
                    str(ROOT / "config" / "providers.json"),
                    allow_network=True,
                    allow_local=False,
                )
        self.assertEqual(status, 3)
        self.assertIn("local_opt_in_required", output.getvalue())
        self.assertFalse(state_root.exists())

    def test_external_provider_rejects_local_only_opt_in_before_reading_task(self) -> None:
        output = io.StringIO()
        state_root = ROOT / "state-must-not-be-created"
        environment = {
            "MACR_ROOT": str(ROOT),
            "MACR_STATE_ROOT": str(state_root),
            "CODEX_HOME_TARGET": r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
        }
        with patch.dict(os.environ, environment, clear=False):
            with contextlib.redirect_stdout(output):
                status = _invoke(
                    "grok",
                    "this-file-must-not-be-read.json",
                    str(ROOT / "config" / "providers.json"),
                    allow_network=False,
                    allow_local=True,
                )
        self.assertEqual(status, 3)
        self.assertIn("network_opt_in_required", output.getvalue())
        self.assertFalse(state_root.exists())


if __name__ == "__main__":
    unittest.main()
