from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from tests.support import d_drive_tempdir


ROOT = Path(__file__).resolve().parents[1]


class GlmWrapperTests(unittest.TestCase):
    def test_wrapper_loads_d_drive_key_for_one_process_without_printing_it(self):
        with d_drive_tempdir() as root:
            script_dir = root / "scripts"
            script_dir.mkdir()
            wrapper = script_dir / "invoke-glm.ps1"
            shutil.copy2(ROOT / "scripts" / "invoke-glm.ps1", wrapper)
            marker = script_dir / "preflight.marker"
            (script_dir / "macr.ps1").write_text(
                f"""
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Rest)
if ($Rest[0] -eq 'glm-preflight') {{
  if ($env:ZAI_API_KEY) {{ exit 9 }}
  [System.IO.File]::WriteAllText('{marker}', 'ok')
  [pscustomobject]@{{ status = 'approved' }} | ConvertTo-Json -Compress
  exit 0
}}
[pscustomobject]@{{
  arguments = @($Rest)
  key_present = [bool]$env:ZAI_API_KEY
  key_shape_valid = [bool]($env:ZAI_API_KEY -match '^[^.\\s]+\\.[^.\\s]+$')
  preflight_seen = Test-Path -LiteralPath '{marker}'
}} | ConvertTo-Json -Compress
exit 0
""".strip(),
                encoding="utf-8",
            )
            key_path = root / "GLM.txt"
            secret = "test-id." + "test-secret"
            key_path.write_text(secret, encoding="utf-8")
            task_path = root / "task.json"
            task_path.write_text("{}", encoding="utf-8")

            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(wrapper),
                    "-TaskPath",
                    str(task_path),
                    "-KeyPath",
                    str(key_path),
                    "-KeyRoot",
                    str(root),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn(secret, completed.stdout)
        document = json.loads(completed.stdout)
        self.assertTrue(document["key_present"])
        self.assertTrue(document["key_shape_valid"])
        self.assertTrue(document["preflight_seen"])
        self.assertEqual(
            document["arguments"],
            ["invoke", "glm_flash_worker", str(task_path), "--allow-network"],
        )

    def test_wrapper_preflight_failure_happens_before_missing_key_read(self):
        with d_drive_tempdir() as root:
            script_dir = root / "scripts"
            script_dir.mkdir()
            wrapper = script_dir / "invoke-glm.ps1"
            shutil.copy2(ROOT / "scripts" / "invoke-glm.ps1", wrapper)
            (script_dir / "macr.ps1").write_text(
                """
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Rest)
if ($Rest[0] -eq 'glm-preflight') {
  [pscustomobject]@{ status = 'approval_invalid' } | ConvertTo-Json -Compress
  exit 4
}
throw 'invoke must not run'
""".strip(),
                encoding="utf-8",
            )
            task_path = root / "invalid-task.json"
            task_path.write_text("{}", encoding="utf-8")

            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(wrapper),
                    "-TaskPath",
                    str(task_path),
                    "-KeyPath",
                    str(root / "missing-key.txt"),
                    "-KeyRoot",
                    str(root),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(completed.returncode, 4)
        self.assertIn("approval_invalid", completed.stdout)
        self.assertNotIn("key file", completed.stderr.lower())

    def test_wrapper_rejects_key_outside_canonical_key_root(self):
        with d_drive_tempdir() as root:
            script_dir = root / "scripts"
            script_dir.mkdir()
            wrapper = script_dir / "invoke-glm.ps1"
            shutil.copy2(ROOT / "scripts" / "invoke-glm.ps1", wrapper)
            (script_dir / "macr.ps1").write_text(
                """
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Rest)
if ($Rest[0] -eq 'glm-preflight') { exit 0 }
throw 'invoke must not run'
""".strip(),
                encoding="utf-8",
            )
            key_root = root / "key-root"
            key_root.mkdir()
            outside_key = root / "outside.txt"
            outside_key.write_text("test-id." + "test-secret", encoding="utf-8")
            task_path = root / "task.json"
            task_path.write_text("{}", encoding="utf-8")

            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(wrapper),
                    "-TaskPath",
                    str(task_path),
                    "-KeyPath",
                    str(outside_key),
                    "-KeyRoot",
                    str(key_root),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("beneath the canonical key root", completed.stderr.lower())


if __name__ == "__main__":
    unittest.main()
