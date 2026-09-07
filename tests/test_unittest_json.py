from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

from tests.helpers.process_capture import run_bytes


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests" / "helpers" / "unittest_json.py"


class UnittestJsonRunnerTests(unittest.TestCase):
    def _run(self, *modules: str):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        return run_bytes(
            (sys.executable, str(RUNNER), *modules),
            cwd=ROOT,
            env=env,
        )

    @staticmethod
    def _summary(stdout: str) -> dict[str, object]:
        lines = [line for line in stdout.splitlines() if line.startswith("UNITTEST_SUMMARY=")]
        if len(lines) != 1:
            raise AssertionError(f"expected one UNITTEST_SUMMARY line, got {lines!r}")
        return json.loads(lines[0].split("=", 1)[1])

    def test_success_emits_machine_readable_count(self) -> None:
        capture = self._run("tests.test_process_capture")

        self.assertEqual(capture.returncode, 0, capture.stderr)
        self.assertEqual(capture.stderr_bytes, b"")
        self.assertEqual(
            self._summary(capture.stdout),
            {
                "errors": 0,
                "failures": 0,
                "skipped": 0,
                "successful": True,
                "tests_run": 5,
            },
        )

    def test_import_error_is_reported_without_localized_count_parsing(self) -> None:
        capture = self._run("tests.module_that_does_not_exist")

        self.assertNotEqual(capture.returncode, 0)
        self.assertEqual(capture.stderr_bytes, b"")
        self.assertIn("FAILED", capture.stdout)
        summary = self._summary(capture.stdout)
        self.assertEqual(summary["tests_run"], 1)
        self.assertEqual(summary["errors"], 1)
        self.assertFalse(summary["successful"])

    def test_discovery_mode_reports_exact_machine_readable_count(self) -> None:
        subject = ROOT / "tests" / "fixtures" / "unittest-json-subject"
        capture = self._run(
            "--discover-start",
            str(subject),
            "--top-level",
            str(subject),
        )

        self.assertEqual(capture.returncode, 0, capture.stderr)
        self.assertEqual(self._summary(capture.stdout)["tests_run"], 2)


if __name__ == "__main__":
    unittest.main()
