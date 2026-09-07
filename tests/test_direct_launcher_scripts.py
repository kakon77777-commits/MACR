from __future__ import annotations

import json
import time
import unittest
import uuid
from pathlib import Path

from tests.helpers.process_capture import (
    CapturedProcess,
    assert_canaries_absent,
    run_bytes,
)
from tests.support import DEFAULT_TEST_ROOT


ROOT = Path(__file__).resolve().parents[1]
START = ROOT / "scripts" / "start-direct-chat.ps1"
INSTALL = ROOT / "scripts" / "install-direct-chat-shortcut.ps1"
READ_KEY = ROOT / "scripts" / "read-grok-key.ps1"


def run_powershell(*arguments: str) -> CapturedProcess:
    return run_bytes(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", *arguments],
        cwd=ROOT,
    )


class DirectLauncherScriptTests(unittest.TestCase):
    def test_grok_key_loader_accepts_secret_and_rejects_uuid_identifier(self) -> None:
        DEFAULT_TEST_ROOT.mkdir(parents=True, exist_ok=True)
        legacy_path = DEFAULT_TEST_ROOT / f"grok-legacy-{uuid.uuid4()}.txt"
        uuid_path = DEFAULT_TEST_ROOT / f"grok-uuid-{uuid.uuid4()}.txt"
        invalid_path = DEFAULT_TEST_ROOT / f"grok-invalid-{uuid.uuid4()}.txt"
        legacy_token = "xai-" + ("A" * 24)
        uuid_token = "00000000-0000-4000-8000-000000000999"
        legacy_path.write_text(legacy_token + "\n", encoding="utf-8")
        uuid_path.write_text(uuid_token, encoding="utf-8")
        invalid_path.write_text("not a valid token", encoding="utf-8")
        try:
            legacy = run_powershell(
                "-File",
                str(READ_KEY),
                "-CredentialPath",
                str(legacy_path),
            )
            self.assertEqual(legacy.returncode, 0, legacy.stderr)
            self.assertEqual(legacy.stdout.rstrip("\r\n"), legacy_token)

            identifier = run_powershell(
                "-File",
                str(READ_KEY),
                "-CredentialPath",
                str(uuid_path),
            )
            self.assertNotEqual(identifier.returncode, 0)
            assert_canaries_absent(identifier, (uuid_token.encode("ascii"),))

            escaped_script = str(READ_KEY).replace("'", "''")
            escaped_path = str(legacy_path).replace("'", "''")
            capture_command = (
                "$value=& '"
                + escaped_script
                + "' -CredentialPath '"
                + escaped_path
                + "'; if ($null -eq $value) { exit 7 }; "
                "[Console]::Out.Write($value)"
            )
            captured = run_powershell("-Command", capture_command)
            self.assertEqual(captured.returncode, 0, captured.stderr)
            self.assertEqual(captured.stdout, legacy_token)

            invalid = run_powershell(
                "-File",
                str(READ_KEY),
                "-CredentialPath",
                str(invalid_path),
            )
            self.assertNotEqual(invalid.returncode, 0)
            assert_canaries_absent(invalid, (b"not a valid token",))
        finally:
            for path in (legacy_path, uuid_path, invalid_path):
                path.unlink(missing_ok=True)

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
        assert_canaries_absent(result, (b"xai-", b"bootstrap"))

    def test_start_script_keeps_qwythos_available_when_grok_key_is_invalid(self) -> None:
        DEFAULT_TEST_ROOT.mkdir(parents=True, exist_ok=True)
        identifier_path = DEFAULT_TEST_ROOT / f"grok-id-{uuid.uuid4()}.txt"
        identifier_path.write_text(
            "00000000-0000-4000-8000-000000000999",
            encoding="utf-8",
        )
        try:
            result = run_powershell(
                "-File",
                str(START),
                "-DryRun",
                "-CredentialPath",
                str(identifier_path),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report["grok_credential_usable"])
            self.assertTrue(report["direct_service_would_start"])
            self.assertNotIn(
                "00000000-0000-4000-8000-000000000999",
                result.stdout,
            )
            assert_canaries_absent(
                result,
                (b"00000000-0000-4000-8000-000000000999",),
            )
        finally:
            identifier_path.unlink(missing_ok=True)

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
