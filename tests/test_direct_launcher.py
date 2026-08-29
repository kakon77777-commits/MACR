from __future__ import annotations

import json
import unittest
from pathlib import Path

from macr_runtime.direct_launcher import (
    DirectInstanceLease,
    build_direct_application,
    smoke_direct_chat,
)
from macr_runtime.errors import LegacyLedgerError
from macr_runtime.storage import StorageLayout
from tests.support import d_drive_tempdir


ROOT = Path(__file__).resolve().parents[1]


def layout_for(state_root: Path) -> StorageLayout:
    return StorageLayout(
        source_root=str(ROOT),
        state_root=str(state_root),
        codex_home_target=r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
    )


class DirectLauncherTests(unittest.TestCase):
    def test_builds_local_application_without_provider_call(self) -> None:
        with d_drive_tempdir() as state_root:
            layout = layout_for(state_root)
            application = build_direct_application(
                layout,
                environ={"XAI_API_KEY": "xai-test-only"},
            )
            try:
                self.assertEqual(application.server.address.host, "127.0.0.1")
                self.assertGreater(application.server.address.port, 0)
                self.assertEqual(
                    application.settings.active_profile().profile_name,
                    "operator_managed",
                )
                self.assertEqual(
                    application.runtime.token_policies.path,
                    layout.model_token_policy_db_path,
                )
                self.assertEqual(application.conversations.list(), ())
                self.assertEqual(application.registry.provider_ids(), ("grok", "ollama_qwythos"))
            finally:
                application.server.server_close()

    def test_unmigrated_legacy_source_refuses_before_direct_databases(self) -> None:
        with d_drive_tempdir() as state_root:
            layout = layout_for(state_root)
            layout.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            layout.ledger_path.write_text(
                json.dumps({"event_id": "legacy-unsealed"}) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(LegacyLedgerError, "migration"):
                build_direct_application(
                    layout,
                    environ={"XAI_API_KEY": "xai-test-only"},
                )
            self.assertFalse(layout.direct_db_path.exists())
            self.assertFalse(layout.settings_db_path.exists())
            self.assertFalse(layout.model_token_policy_db_path.exists())

    def test_instance_lease_has_one_cross_handle_holder_and_recovers(self) -> None:
        with d_drive_tempdir() as state_root:
            lock_path = state_root / "direct" / "instance.lock"
            first = DirectInstanceLease(lock_path)
            second = DirectInstanceLease(lock_path)
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.release()
            self.assertTrue(second.acquire())
            second.release()

    def test_smoke_starts_bootstraps_and_stops_without_generation(self) -> None:
        with d_drive_tempdir() as state_root:
            report = smoke_direct_chat(
                layout_for(state_root),
                environ={"XAI_API_KEY": "xai-test-only"},
            )
            self.assertEqual(
                report,
                {
                    "status": "direct_chat_smoke_ok",
                    "version": "0.6.0a1",
                    "ui_version": "0.1",
                    "host": "127.0.0.1",
                    "asset_status": 200,
                    "bootstrap_status": 200,
                    "network_activity": False,
                    "provider_generation": False,
                },
            )


if __name__ == "__main__":
    unittest.main()
