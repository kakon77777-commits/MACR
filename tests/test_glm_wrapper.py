from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from tests.support import d_drive_tempdir


ROOT = Path(__file__).resolve().parents[1]


class GlmWrapperTests(unittest.TestCase):
    def test_wrapper_preflights_then_invokes_without_loading_key_in_powershell(self):
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
  preflight_seen = Test-Path -LiteralPath '{marker}'
}} | ConvertTo-Json -Compress
exit 0
""".strip(),
                encoding="utf-8",
            )
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
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        document = json.loads(completed.stdout)
        self.assertFalse(document["key_present"])
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
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(completed.returncode, 4)
        self.assertIn("approval_invalid", completed.stdout)
        self.assertNotIn("key file", completed.stderr.lower())


if __name__ == "__main__":
    unittest.main()
