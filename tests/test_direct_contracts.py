from __future__ import annotations

import unittest

from macr_runtime.direct_contracts import (
    DirectConversationSpec,
    DirectMessage,
    DirectProviderId,
    DirectRunSettings,
    DirectTurnResult,
    canonical_policy_snapshot,
)


QWYTHOS_MODEL = "hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M"


def operator_settings() -> DirectRunSettings:
    return DirectRunSettings(
        profile_name="operator_managed",
        profile_version=1,
        max_output_tokens=4096,
        timeout_s=300.0,
        temperature=0.6,
        top_p=0.95,
        context_warning_tokens=7000,
        hard_context_tokens=8192,
        budget_behavior="warn_only",
        soft_budget_usd=None,
        provider_improvement_preference="allowed",
    )


class DirectContractTests(unittest.TestCase):
    def test_direct_provider_ids_are_closed_to_grok_and_qwythos(self) -> None:
        self.assertEqual(DirectProviderId("grok"), DirectProviderId.GROK)
        self.assertEqual(
            DirectProviderId("ollama_qwythos"),
            DirectProviderId.QWYTHOS,
        )
        with self.assertRaisesRegex(ValueError, "Direct provider"):
            DirectProviderId("glm_flash_worker")

    def test_message_rejects_unsupported_role_and_blank_content(self) -> None:
        self.assertEqual(
            DirectMessage("user", " exact text ").content,
            " exact text ",
        )
        with self.assertRaisesRegex(ValueError, "role"):
            DirectMessage("tool", "hello")
        with self.assertRaisesRegex(ValueError, "content"):
            DirectMessage("user", " \r\n ")

    def test_conversation_derives_dataset_policy_and_pins_model(self) -> None:
        settings = operator_settings()
        grok = DirectConversationSpec.create(
            provider_id="grok",
            model="grok-4.6",
            system_prompt="",
            settings=settings,
        )
        self.assertEqual(grok.dataset_role, "archive_only")
        self.assertFalse(grok.training_eligible)
        self.assertEqual(grok.encryption, "none")
        self.assertEqual(
            grok.system_prompt_sha256,
            "e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855",
        )
        self.assertEqual(grok.settings_profile_name, "operator_managed")
        self.assertEqual(grok.settings_profile_version, 1)

        qwythos = DirectConversationSpec.create(
            provider_id="ollama_qwythos",
            model=QWYTHOS_MODEL,
            model_digest="a" * 64,
            system_prompt="Visible only",
            settings=settings,
        )
        self.assertEqual(qwythos.dataset_role, "eval_only")
        self.assertFalse(qwythos.training_eligible)
        self.assertEqual(qwythos.model_digest, "a" * 64)

        with self.assertRaisesRegex(ValueError, "model"):
            DirectConversationSpec.create(
                provider_id="grok",
                model="grok-4.3",
                system_prompt="",
                settings=settings,
            )

    def test_run_settings_fail_closed_on_invalid_numeric_or_policy_values(self) -> None:
        baseline = operator_settings().to_dict()
        invalid = (
            ("timeout_s", 0),
            ("max_output_tokens", 0),
            ("temperature", float("nan")),
            ("top_p", 1.1),
            ("context_warning_tokens", 8192),
            ("budget_behavior", "unlimited"),
            ("provider_improvement_preference", "secretly_train"),
        )
        for name, value in invalid:
            with self.subTest(name=name), self.assertRaises(ValueError):
                DirectRunSettings(**{**baseline, name: value})

    def test_policy_snapshot_is_canonical_and_content_free(self) -> None:
        document, digest = canonical_policy_snapshot(operator_settings())
        self.assertEqual(
            document,
            '{"budget_behavior":"warn_only","context_warning_tokens":7000,'
            '"hard_context_tokens":8192,"max_output_tokens":4096,'
            '"profile_name":"operator_managed","profile_version":1,'
            '"provider_improvement_preference":"allowed",'
            '"schema":"macr_direct_policy_v1","soft_budget_usd":null,'
            '"temperature":0.6,"timeout_s":300.0,"top_p":0.95}',
        )
        self.assertEqual(
            digest,
            "775b1d32998b3a03c6c717b7ec18d8e274649bf29e6f9b32ae6cf5269638f90a",
        )
        self.assertNotIn("prompt", document)
        self.assertNotIn("message", document)

    def test_turn_result_requires_uuid_and_terminal_status(self) -> None:
        result = DirectTurnResult(
            run_id="00000000-0000-4000-8000-000000000001",
            conversation_id="00000000-0000-4000-8000-000000000002",
            status="completed",
            assistant_message=None,
            observation={},
            context_warning=False,
            failure_type=None,
        )
        self.assertEqual(result.status, "completed")
        with self.assertRaisesRegex(ValueError, "status"):
            DirectTurnResult(
                run_id=result.run_id,
                conversation_id=result.conversation_id,
                status="candidate_success",
                assistant_message=None,
                observation={},
                context_warning=False,
                failure_type=None,
            )


if __name__ == "__main__":
    unittest.main()
