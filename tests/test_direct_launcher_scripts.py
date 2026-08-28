from __future__ import annotations

import json
import subprocess
import time
import unittest
import uuid
from pathlib import Path

from tests.support import DEFAULT_TEST_ROOT


ROOT = Path(__file__).resolve().parents[1]
START = ROOT / "scripts" / "start-direct-chat.ps1"
INSTALL = ROOT / "scripts" / "install-direct-chat-shortcut.ps1"


def run_powershell(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8-sig",
    )


class DirectLauncherScriptTests(unittest.TestCase):
    def test_start_script_dry_run_is_content_free_and_d_drive_bound(self) -> None:
        result = run_powershell("-File", str(START), "-DryRun")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "direct_chat_launch_dry_run")
        self.assertTrue(report["repo_root"].upper().startswith("D:\\"))
        self.assertTrue(report["state_root"].upper().startswith("D:\\"))
        self.assertTrue(report["credential_helper_present"])
        self.assertTrue(report["hidden_child"])
        self.assertFalse(report["network_activity"])
        serialized = json.dumps(report)
        self.assertNotIn("xai-", serialized)
        self.assertNotIn("bootstrap", serialized.lower())

    def test_shortcut_dry_run_and_real_file_have_no_secret_arguments(self) -> None:
        DEFAULT_TEST_ROOT.mkdir(parents=True, exist_ok=True)
        shortcut = DEFAULT_TEST_ROOT / f"macr-direct-shortcut-{uuid.uuid4()}.lnk"
        try:
            dry = run_powershell(
                "-File",
                str(INSTALL),
                "-ShortcutPath",
                str(shortcut),
                "-DryRun",
            )
            self.assertEqual(dry.returncode, 0, dry.stderr)
            dry_report = json.loads(dry.stdout)
            self.assertFalse(dry_report["created"])
            self.assertFalse(shortcut.exists())
            self.assertIn("start-direct-chat.ps1", dry_report["arguments"])
            self.assertNotIn("xai-", json.dumps(dry_report))

            actual = run_powershell(
                "-File",
                str(INSTALL),
                "-ShortcutPath",
                str(shortcut),
            )
            self.assertEqual(actual.returncode, 0, actual.stderr)
            self.assertTrue(shortcut.is_file())
            actual_report = json.loads(actual.stdout)
            self.assertTrue(actual_report["created"])

            escaped = str(shortcut).replace("'", "''")
            inspect_command = (
                "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut('"
                + escaped
                + "'); $o=[pscustomobject]@{target=$s.TargetPath;arguments=$s.Arguments;"
                "working_directory=$s.WorkingDirectory}; $j=$o|ConvertTo-Json -Compress; "
                "[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($s); "
                "[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($w); "
                "[GC]::Collect(); [GC]::WaitForPendingFinalizers(); $j"
            )
            inspected = run_powershell("-Command", inspect_command)
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            descriptor = json.loads(inspected.stdout)
            self.assertTrue(descriptor["target"].lower().endswith("powershell.exe"))
            self.assertIn("-WindowStyle Hidden", descriptor["arguments"])
            self.assertIn("start-direct-chat.ps1", descriptor["arguments"])
            self.assertTrue(descriptor["working_directory"].upper().startswith("D:\\"))
            self.assertNotIn("xai-", json.dumps(descriptor))

            for _ in range(100):
                try:
                    shortcut.unlink()
                    break
                except PermissionError:
                    time.sleep(0.1)
            self.assertFalse(shortcut.exists(), "Windows retained the test .lnk lock")
        finally:
            if shortcut.exists():
                for _ in range(100):
                    try:
                        shortcut.unlink()
                        break
                    except PermissionError:
                        time.sleep(0.1)


if __name__ == "__main__":
    unittest.main()
