import unittest
from pathlib import Path

from macr_runtime.errors import StoragePolicyError
from macr_runtime.storage import StorageLayout
from tests.support import d_drive_tempdir


class StorageLayoutTests(unittest.TestCase):
    def test_defaults_use_only_d_residence(self) -> None:
        layout = StorageLayout.from_environment({})
        self.assertEqual(layout.source_root, r"D:\Ai\work together\MACR")
        self.assertEqual(
            layout.state_root,
            r"D:\AI_RESIDENCE\AI_Runtime\macr-state",
        )
        self.assertEqual(
            layout.codex_home_target,
            r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
        )
        state_root = Path(layout.state_root)
        self.assertEqual(
            layout.runtime_db_path,
            state_root / "runtime" / "dispatch.sqlite3",
        )
        self.assertEqual(
            layout.agent_db_path,
            state_root / "runtime" / "agent.sqlite3",
        )
        self.assertEqual(
            layout.accounting_db_path,
            state_root / "accounting" / "accounting.sqlite3",
        )
        self.assertEqual(layout.candidate_root, state_root / "candidates")
        self.assertEqual(layout.quarantine_root, state_root / "quarantine")
        self.assertEqual(layout.direct_root, state_root / "direct")
        self.assertEqual(layout.settings_root, state_root / "settings")
        self.assertEqual(
            layout.direct_db_path,
            state_root / "direct" / "conversations.sqlite3",
        )
        self.assertEqual(
            layout.settings_db_path,
            state_root / "settings" / "settings.sqlite3",
        )
        self.assertEqual(
            layout.model_token_policy_db_path,
            state_root / "settings" / "model-token-policies.sqlite3",
        )
        self.assertEqual(
            layout.provider_capability_policy_db_path,
            state_root / "settings" / "provider-capability-policies.sqlite3",
        )
        self.assertEqual(
            layout.direct_instance_path,
            state_root / "direct" / "instance.json",
        )
        self.assertEqual(
            layout.observatory_db_path,
            state_root / "observatory" / "observatory.sqlite3",
        )
        self.assertEqual(
            layout.observatory_snapshot_root,
            state_root / "observatory" / "snapshots",
        )
        self.assertEqual(layout.observatory_db_path.drive.upper(), "D:")

    def test_state_tree_includes_v05_runtime_roots(self) -> None:
        with d_drive_tempdir() as state_root:
            layout = StorageLayout(
                source_root=r"D:\Ai\work together\MACR",
                state_root=str(state_root),
                codex_home_target=r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
            )

            roots = layout.ensure_state_tree()

            self.assertEqual(
                {path.name for path in roots},
                {
                    "ledger",
                    "artifacts",
                    "cache",
                    "test-tmp",
                    "runtime",
                    "accounting",
                    "candidates",
                    "quarantine",
                    "direct",
                    "settings",
                    "observatory",
                },
            )
            self.assertTrue(all(path.is_dir() for path in roots))

    def test_rejects_c_source_root(self) -> None:
        with self.assertRaisesRegex(StoragePolicyError, "must be on D:"):
            StorageLayout(
                source_root=r"C:\MACR",
                state_root=r"D:\AI_RESIDENCE\AI_Runtime\macr-state",
                codex_home_target=r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
            )

    def test_rejects_historical_r_state_root(self) -> None:
        with self.assertRaisesRegex(StoragePolicyError, "must be on D:"):
            StorageLayout(
                source_root=r"D:\Ai\work together\MACR",
                state_root=r"R:\AI_Runtime\macr-state",
                codex_home_target=r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
            )

    def test_rejects_relative_state_root(self) -> None:
        with self.assertRaisesRegex(StoragePolicyError, "absolute Windows path"):
            StorageLayout(
                source_root=r"D:\Ai\work together\MACR",
                state_root="state",
                codex_home_target=r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
            )


if __name__ == "__main__":
    unittest.main()
