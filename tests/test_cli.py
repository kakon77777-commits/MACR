from __future__ import annotations

import contextlib
import io
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from macr_runtime.cli import _doctor, _invoke


ROOT = Path(__file__).resolve().parents[1]


class DoctorTests(unittest.TestCase):
    def test_strict_ignores_intentionally_disabled_providers(self) -> None:
        environment = {
            "MINIMAX_API_KEY": "test-key",
            "MINIMAX_BASE_URL": "https://api.minimax.io/v1",
            "MINIMAX_MODEL": "test-model",
        }
        with patch.dict(os.environ, environment, clear=False):
            with contextlib.redirect_stdout(io.StringIO()):
                status = _doctor(str(ROOT / "config" / "providers.json"), strict=True)
        self.assertEqual(status, 0)

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
                None,
                allow_network=False,
            )
        self.assertEqual(status, 3)
        self.assertIn("network_opt_in_required", output.getvalue())


if __name__ == "__main__":
    unittest.main()
