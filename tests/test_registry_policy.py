import unittest
from pathlib import Path

from macr_runtime.config import load_provider_configs
from macr_runtime.contracts import TaskContract
from macr_runtime.errors import ProviderPolicyError
from macr_runtime.registry import ProviderRegistry


ROOT = Path(__file__).resolve().parents[1]


class RegistryPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        configs = load_provider_configs(ROOT / "config" / "providers.json")
        self.registry = ProviderRegistry.from_configs(configs, environ={})

    def test_grok_is_disabled(self) -> None:
        health = self.registry.get("grok").health()
        self.assertEqual(health.status, "disabled")
        self.assertIn("not been applied", health.detail)

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


if __name__ == "__main__":
    unittest.main()
