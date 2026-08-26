import unittest
from pathlib import Path

from macr_runtime.config import load_provider_configs
from macr_runtime.contracts import TaskContract
from macr_runtime.errors import ProviderPolicyError
from macr_runtime.registry import ProviderRegistry
from tests.support import d_drive_tempdir, write_fake_google_credential


ROOT = Path(__file__).resolve().parents[1]


class RegistryPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        configs = load_provider_configs(ROOT / "config" / "providers.json")
        self.registry = ProviderRegistry.from_configs(
            configs,
            environ={"XAI_API_KEY": "test-key"},
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


if __name__ == "__main__":
    unittest.main()
