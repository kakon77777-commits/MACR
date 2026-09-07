from __future__ import annotations

import dataclasses
import unittest

from macr_runtime.errors import ProviderPolicyError
from macr_runtime.token_policy import (
    ModelTokenOverride,
    ModelTokenPolicy,
    ModelTokenPolicyResolver,
    builtin_model_token_policies,
    t1_glm_live_policy,
)


QWYTHOS_MODEL = "hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M"


class ModelTokenPolicyTests(unittest.TestCase):
    def test_external_and_local_models_have_distinct_exact_policies(self) -> None:
        resolver = ModelTokenPolicyResolver.builtins_only()
        grok = resolver.resolve("grok", "grok-4.6")
        glm = resolver.resolve("glm_flash_worker", "glm-5.3-flash")
        gemini = resolver.resolve("google_gemini", "gemini-3.7-flash")
        minimax = resolver.resolve("minimax", "MiniMax-M2.7")
        local = resolver.resolve("ollama_qwythos", QWYTHOS_MODEL)

        self.assertEqual(
            (grok.context_warning_tokens, grok.hard_context_tokens),
            (180_000, 400_000),
        )
        self.assertEqual(
            (grok.default_output_tokens, grok.max_output_tokens),
            (32_768, 65_536),
        )
        self.assertEqual(
            (glm.hard_context_tokens, glm.default_output_tokens),
            (512_000, 16_384),
        )
        self.assertEqual(
            (gemini.hard_context_tokens, gemini.max_output_tokens),
            (512_000, 65_536),
        )
        self.assertEqual(
            (minimax.hard_context_tokens, minimax.max_output_tokens),
            (180_000, 2_048),
        )
        self.assertEqual(
            (local.hard_context_tokens, local.default_output_tokens),
            (8_192, 4_096),
        )
        self.assertEqual(grok.minimum_task_output_tokens, 32_768)
        self.assertEqual(glm.minimum_task_output_tokens, 16_384)
        self.assertEqual(gemini.minimum_task_output_tokens, 16_384)
        self.assertEqual(minimax.minimum_task_output_tokens, 2_048)
        self.assertEqual(local.minimum_task_output_tokens, 1)
        self.assertEqual(len(builtin_model_token_policies()), 7)
        self.assertEqual(len({item.policy_digest for item in builtin_model_token_policies()}), 7)

    def test_unknown_model_and_duplicate_registry_fail_closed(self) -> None:
        resolver = ModelTokenPolicyResolver.builtins_only()
        with self.assertRaisesRegex(ProviderPolicyError, "exact model token policy"):
            resolver.resolve("minimax", "unconfigured-model")
        policy = builtin_model_token_policies()[0]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            ModelTokenPolicyResolver((policy, policy))

    def test_policy_invariants_and_operator_override_ceiling(self) -> None:
        grok = ModelTokenPolicyResolver.builtins_only().resolve(
            "grok",
            "grok-4.6",
        )
        invalid_changes = (
            {"context_warning_tokens": grok.hard_context_tokens},
            {"hard_context_tokens": grok.provider_context_ceiling_tokens + 1},
            {"default_output_tokens": 8_192},
            {"default_output_tokens": grok.max_output_tokens + 1},
            {"max_output_tokens": grok.provider_output_ceiling_tokens + 1},
        )
        for changes in invalid_changes:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                dataclasses.replace(grok, **changes)

        override = ModelTokenOverride(
            provider_id="grok",
            model_id="grok-4.6",
            revision=2,
            context_warning_tokens=200_000,
            hard_context_tokens=450_000,
            default_output_tokens=40_000,
            max_output_tokens=48_000,
            base_policy_digest=grok.policy_digest,
        )
        effective = override.apply(grok)
        self.assertEqual(effective.policy_source, "operator_override:2")
        self.assertEqual(effective.max_output_tokens, 48_000)
        self.assertEqual(effective.connection_scope, grok.connection_scope)
        with self.assertRaisesRegex(ValueError, "fields must be exact"):
            ModelTokenOverride.from_dict(
                {**override.to_dict(), "connection_scope": "loopback_http"}
            )
        with self.assertRaisesRegex(ValueError, "base policy"):
            dataclasses.replace(
                override,
                base_policy_digest="f" * 64,
            ).apply(grok)

    def test_t1_live_policy_is_separate_and_stricter_than_general_glm(self) -> None:
        general = ModelTokenPolicyResolver.builtins_only().resolve(
            "glm_flash_worker",
            "glm-5.3-flash",
        )
        live = t1_glm_live_policy()

        self.assertEqual(
            (live.hard_context_tokens, live.max_output_tokens),
            (128_000, 16_384),
        )
        self.assertEqual(live.minimum_task_output_tokens, 16_384)
        self.assertNotEqual(live.policy_digest, general.policy_digest)
        self.assertEqual(live.policy_source, "t1_live_preset")


if __name__ == "__main__":
    unittest.main()
