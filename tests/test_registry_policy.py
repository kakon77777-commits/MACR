import unittest
from pathlib import Path

from macr_runtime.config import load_provider_configs
from macr_runtime.contracts import TaskContract
from macr_runtime.errors import ProviderPolicyError
from macr_runtime.model_token_store import ModelTokenPolicyStore
from macr_runtime.providers.glm import GlmFlashWorkerProvider
from macr_runtime.registry import ProviderRegistry
from macr_runtime.token_policy import ModelTokenOverride, t1_glm_live_policy
from tests.support import d_drive_tempdir, write_fake_google_credential


ROOT = Path(__file__).resolve().parents[1]


class StaticKeySource:
    def load(self):
        return "test-id." + "test-secret"

    def check_metadata(self):
        return None


class RegistryPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        configs = load_provider_configs(ROOT / "config" / "providers.json")
        self.registry = ProviderRegistry.from_configs(
            configs,
            environ={
                "XAI_API_KEY": "test-key",
            },
            key_sources={"glm_flash_worker": StaticKeySource()},
        )

    def test_grok_profiles_are_configured_offline(self) -> None:
        health = self.registry.get("grok").health()
        self.assertTrue(health.ready)
        self.assertEqual(health.status, "configured_offline")
        self.assertEqual(self.registry.get("grok").config.model, "grok-4.6")
        self.assertEqual(
            self.registry.get("grok_standard").config.model,
            "grok-4.3",
        )
        ollama_health = self.registry.get("ollama_qwythos").health()
        self.assertTrue(ollama_health.ready)
        self.assertEqual(ollama_health.status, "configured_offline")
        self.assertEqual(
            self.registry.token_policy("grok").hard_context_tokens,
            400_000,
        )
        self.assertEqual(
            self.registry.token_policy("ollama_qwythos").max_output_tokens,
            4_096,
        )

    def test_claude_api_route_is_not_available(self) -> None:
        provider = self.registry.get("claude_subscription")
        with self.assertRaises(ProviderPolicyError):
            provider.invoke(
                TaskContract(
                    task_id="claude-policy-001",
                    goal="do not call an API",
                    task_type="policy_test",
                )
            )

    def test_glm_flash_worker_is_configured_offline(self) -> None:
        provider = self.registry.get("glm_flash_worker")
        health = provider.health()

        self.assertTrue(health.ready)
        self.assertEqual(health.status, "configured_offline")
        self.assertEqual(provider.config.model, "glm-5.3-flash")

    def test_glm_adapter_receives_exact_active_model_override(self) -> None:
        configs = load_provider_configs(ROOT / "config" / "providers.json")
        with d_drive_tempdir() as root:
            store = ModelTokenPolicyStore(root / "model-token-policies.sqlite3")
            base = store.effective_policy("glm_flash_worker", "glm-5.3-flash")
            store.save_override(
                ModelTokenOverride(
                    provider_id=base.provider_id,
                    model_id=base.model_id,
                    revision=1,
                    context_warning_tokens=100_000,
                    hard_context_tokens=128_000,
                    default_output_tokens=8_192,
                    max_output_tokens=8_192,
                    base_policy_digest=base.policy_digest,
                ),
                activate=True,
            )
            registry = ProviderRegistry.from_configs(
                configs,
                environ={"MACR_STATE_ROOT": str(root)},
                key_sources={"glm_flash_worker": StaticKeySource()},
                token_policy_store=store,
            )

        provider = registry.get("glm_flash_worker")
        self.assertEqual(provider.token_policy.max_output_tokens, 8_192)
        self.assertEqual(provider.token_policy.policy_source, "operator_override:1")

    def test_explicit_t1_policy_wins_over_ordinary_store_policy(self) -> None:
        configs = load_provider_configs(ROOT / "config" / "providers.json")
        config = next(item for item in configs if item.id == "glm_flash_worker")
        with d_drive_tempdir() as root:
            store = ModelTokenPolicyStore(root / "model-token-policies.sqlite3")
            provider = GlmFlashWorkerProvider(
                config,
                environ={"MACR_STATE_ROOT": str(root)},
                key_source=StaticKeySource(),
                token_policy=t1_glm_live_policy(),
            )
            effective = ProviderRegistry((provider,)).token_policy(
                "glm_flash_worker",
                store=store,
            )

        self.assertEqual(effective.policy_source, "t1_live_preset")
        self.assertEqual(effective.max_output_tokens, 8_192)

    def test_google_gemini_is_configured_offline(self) -> None:
        configs = load_provider_configs(ROOT / "config" / "providers.json")
        with d_drive_tempdir() as root:
            credential = write_fake_google_credential(root / "credential.json")
            registry = ProviderRegistry.from_configs(
                configs,
                environ={
                    "XAI_API_KEY": "test-key",
                    "GOOGLE_APPLICATION_CREDENTIALS": str(credential),
                    "GOOGLE_CLOUD_PROJECT": "test-project",
                },
            )
            health = registry.get("google_gemini").health()
        self.assertTrue(health.ready)
        self.assertEqual(health.status, "configured_offline")
        self.assertEqual(
            registry.get("google_gemini").config.model,
            "gemini-3.7-flash",
        )

    def test_google_image_is_offline_and_future_profiles_are_disabled(self) -> None:
        configs = load_provider_configs(ROOT / "config" / "providers.json")
        with d_drive_tempdir() as root:
            credential = write_fake_google_credential(root / "credential.json")
            registry = ProviderRegistry.from_configs(
                configs,
                environ={
                    "XAI_API_KEY": "test-key",
                    "GOOGLE_APPLICATION_CREDENTIALS": str(credential),
                    "GOOGLE_CLOUD_PROJECT": "test-project",
                    "MACR_STATE_ROOT": str(root),
                },
            )
            health = registry.get("google_image").health()
            self.assertTrue(health.ready)
            self.assertEqual(health.status, "configured_offline")
            self.assertFalse(registry.requires_model_token_policy("google_image"))
            for provider_id in (
                "google_veo_fast",
                "google_tts",
                "google_lyria",
            ):
                provider = registry.get(provider_id)
                self.assertEqual(provider.health().status, "disabled")
                with self.assertRaises(ProviderPolicyError):
                    provider.invoke(
                        TaskContract(
                            task_id=f"{provider_id}-disabled",
                            goal="remain disabled",
                            task_type="policy_test",
                        )
                    )


if __name__ == "__main__":
    unittest.main()
