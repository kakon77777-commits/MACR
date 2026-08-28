from __future__ import annotations

import unittest
from dataclasses import replace

from macr_runtime.direct_settings import DirectSettingsStore
from macr_runtime.errors import DirectStoreConflict, StoragePolicyError
from tests.support import d_drive_tempdir


class DirectSettingsStoreTests(unittest.TestCase):
    def test_guarded_default_and_operator_override_are_separate_versions(self) -> None:
        with d_drive_tempdir() as root:
            path = root / "settings" / "settings.sqlite3"
            store = DirectSettingsStore(path)

            guarded = store.active_profile()
            self.assertEqual(guarded.profile_name, "guarded")
            self.assertEqual(guarded.profile_version, 1)
            self.assertEqual(guarded.budget_behavior, "hard_cap")

            operator = store.ensure_operator_managed()
            self.assertEqual(operator.profile_name, "operator_managed")
            self.assertEqual(operator.profile_version, 1)
            self.assertEqual(operator.budget_behavior, "warn_only")
            self.assertEqual(store.active_profile(), operator)

            reopened = DirectSettingsStore(path)
            self.assertEqual(reopened.active_profile(), operator)
            self.assertEqual(
                [(item.profile_name, item.profile_version) for item in reopened.profiles()],
                [("guarded", 1), ("operator_managed", 1)],
            )

    def test_profile_record_is_append_only_and_conflicts_fail(self) -> None:
        with d_drive_tempdir() as root:
            store = DirectSettingsStore(root / "settings.sqlite3")
            operator = store.ensure_operator_managed()

            self.assertFalse(store.save_profile(operator, activate=True))
            with self.assertRaisesRegex(DirectStoreConflict, "profile conflicts"):
                store.save_profile(
                    replace(operator, temperature=0.7),
                    activate=False,
                )

            custom = replace(
                operator,
                profile_name="custom",
                profile_version=1,
                max_output_tokens=2048,
            )
            self.assertTrue(store.save_profile(custom, activate=False))
            self.assertEqual(store.active_profile(), operator)
            store.activate("custom", 1)
            self.assertEqual(store.active_profile(), custom)

    def test_database_path_must_be_absolute_on_d_before_creation(self) -> None:
        with self.assertRaisesRegex(StoragePolicyError, "absolute on D"):
            DirectSettingsStore("settings.sqlite3")
        with self.assertRaisesRegex(StoragePolicyError, "absolute on D"):
            DirectSettingsStore(r"C:\MACR\settings.sqlite3")


if __name__ == "__main__":
    unittest.main()
