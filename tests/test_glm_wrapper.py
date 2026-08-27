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
            (script_dir / "macr.ps1").write_text(
                """
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Rest)
[pscustomobject]@{
  arguments = @($Rest)
  key_present = [bool]$env:ZAI_API_KEY
  key_shape_valid = [bool]($env:ZAI_API_KEY -match '^[^.\\s]+\\.[^.\\s]+$')
} | ConvertTo-Json -Compress
exit 0
""".strip(),
                encoding="utf-8",
            )
            key_path = root / "GLM.txt"
            secret = "test-id.test-secret"
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
        self.assertEqual(
            document["arguments"],
            ["invoke", "glm_flash_worker", str(task_path), "--allow-network"],
        )


if __name__ == "__main__":
    unittest.main()
