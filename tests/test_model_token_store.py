from __future__ import annotations

import dataclasses
import sqlite3
import unittest

from macr_runtime.errors import DirectStoreConflict, StoragePolicyError
from macr_runtime.model_token_store import ModelTokenPolicyStore
from macr_runtime.token_policy import ModelTokenOverride, ModelTokenPolicyResolver

from tests.support import d_drive_tempdir


QWYTHOS_MODEL = "hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M"


def grok_override(revision: int = 2) -> ModelTokenOverride:
    base = ModelTokenPolicyResolver.builtins_only().resolve("grok", "grok-4.6")
    return ModelTokenOverride(
        provider_id="grok",
        model_id="grok-4.6",
        revision=revision,
        context_warning_tokens=200_000,
        hard_context_tokens=450_000,
        default_output_tokens=40_000,
        max_output_tokens=48_000,
        base_policy_digest=base.policy_digest,
    )


class ModelTokenPolicyStoreTests(unittest.TestCase):
    def test_override_is_model_local_append_only_and_survives_reopen(self) -> None:
        with d_drive_tempdir() as temp:
            database = temp / "settings" / "model-token-policies.sqlite3"
            store = ModelTokenPolicyStore(database)
            override = grok_override()
            self.assertTrue(store.save_override(override, activate=True))
            self.assertFalse(store.save_override(override, activate=True))

            grok = store.effective_policy("grok", "grok-4.6")
            local = store.effective_policy("ollama_qwythos", QWYTHOS_MODEL)
            reopened = ModelTokenPolicyStore(database)

            self.assertEqual(grok.max_output_tokens, 48_000)
            self.assertEqual(local.max_output_tokens, 4_096)
            self.assertEqual(
                reopened.effective_policy("grok", "grok-4.6"),
                grok,
            )
            self.assertEqual(len(reopened.list_effective()), 7)

    def test_conflicting_revision_and_tampered_body_fail_closed(self) -> None:
        with d_drive_tempdir() as temp:
            database = temp / "model-token-policies.sqlite3"
            store = ModelTokenPolicyStore(database)
            override = grok_override()
            store.save_override(override, activate=True)
            with self.assertRaisesRegex(DirectStoreConflict, "conflict"):
                store.save_override(
                    dataclasses.replace(override, max_output_tokens=47_000),
                    activate=False,
                )

            connection = sqlite3.connect(database)
            connection.execute(
                "UPDATE model_token_overrides SET body_json = ?",
                ('{"tampered":true}',),
            )
            connection.commit()
            connection.close()
            with self.assertRaisesRegex(DirectStoreConflict, "digest"):
                ModelTokenPolicyStore(database).effective_policy(
                    "grok",
                    "grok-4.6",
                )

    def test_store_path_must_be_absolute_on_d(self) -> None:
        with self.assertRaisesRegex(StoragePolicyError, "D:"):
            ModelTokenPolicyStore(r"C:\temp\model-token-policies.sqlite3")


if __name__ == "__main__":
    unittest.main()
