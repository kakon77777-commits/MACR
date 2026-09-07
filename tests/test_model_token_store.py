from __future__ import annotations

import dataclasses
import hashlib
import sqlite3
import unittest

from macr_runtime.canonical import canonical_json_bytes, sha256_id
from macr_runtime.errors import (
    DirectStoreConflict,
    LegacyOutputPolicyIncompatibleError,
    StoragePolicyError,
)
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

    def test_legacy_v1_override_is_audit_visible_and_cannot_activate_or_apply(self) -> None:
        with d_drive_tempdir() as temp:
            database = temp / "settings" / "model-token-policies.sqlite3"
            store = ModelTokenPolicyStore(database)
            current_base = ModelTokenPolicyResolver.builtins_only().resolve(
                "grok",
                "grok-4.6",
            )
            legacy_base = current_base.to_dict()
            legacy_base.pop("minimum_task_output_tokens")
            legacy_override = dataclasses.replace(
                grok_override(revision=1),
                base_policy_digest=sha256_id(
                    "model_token_policy_v1",
                    legacy_base,
                ),
            )
            body = canonical_json_bytes(legacy_override.to_dict()).decode("utf-8")
            body_digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
            connection = sqlite3.connect(database)
            connection.execute(
                """INSERT INTO model_token_overrides(
                    provider_id, model_id, revision, body_json,
                    body_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    legacy_override.provider_id,
                    legacy_override.model_id,
                    legacy_override.revision,
                    body,
                    body_digest,
                    "2026-08-30T00:00:00+00:00",
                ),
            )
            connection.commit()
            connection.close()

            before = store.status_snapshot()
            with self.assertRaisesRegex(
                LegacyOutputPolicyIncompatibleError,
                "legacy_pre_quality_floor",
            ):
                store.activate("grok", "grok-4.6", 1)

            connection = sqlite3.connect(database)
            connection.execute(
                """INSERT INTO model_token_active(
                    provider_id, model_id, revision, updated_at
                ) VALUES (?, ?, ?, ?)""",
                ("grok", "grok-4.6", 1, "2026-08-30T00:00:01+00:00"),
            )
            connection.commit()
            connection.close()

            active = store.status_snapshot()
            with self.assertRaisesRegex(
                LegacyOutputPolicyIncompatibleError,
                "legacy_pre_quality_floor",
            ):
                store.effective_policy("grok", "grok-4.6")
            connection = sqlite3.connect(database)
            preserved = connection.execute(
                """SELECT body_json, body_sha256 FROM model_token_overrides
                WHERE provider_id = 'grok' AND model_id = 'grok-4.6'
                  AND revision = 1"""
            ).fetchone()
            connection.close()

        self.assertEqual(before["legacy_pre_quality_floor_count"], 1)
        self.assertEqual(before["active_legacy_pre_quality_floor_count"], 0)
        self.assertEqual(active["legacy_pre_quality_floor_count"], 1)
        self.assertEqual(active["active_legacy_pre_quality_floor_count"], 1)
        self.assertEqual(active["current_count"], 0)
        self.assertEqual(active["invalid_count"], 0)
        self.assertEqual(preserved, (body, body_digest))

    def test_status_counts_unknown_override_without_exposing_or_raising(self) -> None:
        with d_drive_tempdir() as temp:
            database = temp / "settings" / "model-token-policies.sqlite3"
            store = ModelTokenPolicyStore(database)
            unknown = ModelTokenOverride(
                provider_id="unknown_provider",
                model_id="unknown-model",
                revision=1,
                context_warning_tokens=1_000,
                hard_context_tokens=2_000,
                default_output_tokens=100,
                max_output_tokens=200,
                base_policy_digest="f" * 64,
            )
            body = canonical_json_bytes(unknown.to_dict()).decode("utf-8")
            body_digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
            connection = sqlite3.connect(database)
            connection.execute(
                """INSERT INTO model_token_overrides(
                    provider_id, model_id, revision, body_json,
                    body_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    unknown.provider_id,
                    unknown.model_id,
                    unknown.revision,
                    body,
                    body_digest,
                    "2026-08-30T00:00:00+00:00",
                ),
            )
            connection.commit()
            connection.close()

            status = store.status_snapshot()

        self.assertEqual(status["invalid_count"], 1)
        self.assertEqual(status["total_count"], 1)

    def test_known_provider_random_base_digest_is_invalid_not_legacy(self) -> None:
        with d_drive_tempdir() as temp:
            database = temp / "settings" / "model-token-policies.sqlite3"
            store = ModelTokenPolicyStore(database)
            forged = dataclasses.replace(
                grok_override(revision=3),
                base_policy_digest="f" * 64,
            )
            body = canonical_json_bytes(forged.to_dict()).decode("utf-8")
            body_digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
            connection = sqlite3.connect(database)
            connection.execute(
                """INSERT INTO model_token_overrides(
                    provider_id, model_id, revision, body_json,
                    body_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    forged.provider_id,
                    forged.model_id,
                    forged.revision,
                    body,
                    body_digest,
                    "2026-08-30T00:00:00+00:00",
                ),
            )
            connection.commit()
            connection.close()

            before = store.status_snapshot()
            with self.assertRaisesRegex(DirectStoreConflict, "base policy digest"):
                store.activate("grok", "grok-4.6", 3)
            connection = sqlite3.connect(database)
            active_rows = connection.execute(
                "SELECT COUNT(*) FROM model_token_active"
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO model_token_active(
                    provider_id, model_id, revision, updated_at
                ) VALUES (?, ?, ?, ?)""",
                ("grok", "grok-4.6", 3, "2026-08-30T00:00:01+00:00"),
            )
            connection.commit()
            connection.close()
            after = store.status_snapshot()
            with self.assertRaisesRegex(DirectStoreConflict, "base policy digest"):
                store.effective_policy("grok", "grok-4.6")

        self.assertEqual(before["legacy_pre_quality_floor_count"], 0)
        self.assertEqual(before["invalid_count"], 1)
        self.assertEqual(before["active_invalid_count"], 0)
        self.assertEqual(active_rows, 0)
        self.assertEqual(after["legacy_pre_quality_floor_count"], 0)
        self.assertEqual(after["invalid_count"], 1)
        self.assertEqual(after["active_invalid_count"], 1)


if __name__ == "__main__":
    unittest.main()
