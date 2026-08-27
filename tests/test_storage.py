import unittest
from pathlib import Path

from macr_runtime.errors import StoragePolicyError
from macr_runtime.storage import StorageLayout


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
            layout.accounting_db_path,
            state_root / "accounting" / "accounting.sqlite3",
        )
        self.assertEqual(layout.candidate_root, state_root / "candidates")
        self.assertEqual(layout.quarantine_root, state_root / "quarantine")

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
