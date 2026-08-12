import unittest

from macr_runtime.errors import StoragePolicyError
from macr_runtime.storage import StorageLayout


class StorageLayoutTests(unittest.TestCase):
    def test_defaults_use_only_d_and_r(self) -> None:
        layout = StorageLayout.from_environment({})
        self.assertTrue(layout.source_root.startswith("D:\\"))
        self.assertTrue(layout.state_root.startswith("R:\\"))
        self.assertTrue(layout.codex_home_target.startswith("R:\\"))

    def test_rejects_c_source_root(self) -> None:
        with self.assertRaisesRegex(StoragePolicyError, "must be on D: or R:"):
            StorageLayout(
                source_root=r"C:\MACR",
                state_root=r"R:\AI_Runtime\macr-state",
                codex_home_target=r"R:\AI_Runtime\codex-home",
            )

    def test_rejects_relative_state_root(self) -> None:
        with self.assertRaisesRegex(StoragePolicyError, "absolute Windows path"):
            StorageLayout(
                source_root=r"D:\Ai\work together\MACR",
                state_root="state",
                codex_home_target=r"R:\AI_Runtime\codex-home",
            )


if __name__ == "__main__":
    unittest.main()
