import unittest
from pathlib import Path

from macr_runtime.config import AuthMode, ProviderConfig, load_provider_configs
from macr_runtime.errors import ConfigurationError


ROOT = Path(__file__).resolve().parents[1]


class ProviderConfigTests(unittest.TestCase):
    def test_repository_config_loads(self) -> None:
        configs = load_provider_configs(ROOT / "config" / "providers.json")
        self.assertEqual([item.id for item in configs], ["minimax", "grok", "claude_subscription"])
        claude = configs[2]
        self.assertFalse(claude.api_usage_allowed)
        self.assertEqual(claude.auth_mode, AuthMode.SUBSCRIPTION_CLIENT)

    def test_enabled_api_provider_requires_environment_names(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "lacks"):
            ProviderConfig(
                id="bad",
                kind="minimax_openai_compatible",
                enabled=True,
                auth_mode=AuthMode.API_KEY,
                api_usage_allowed=True,
            )

    def test_public_summary_never_contains_secret_value(self) -> None:
        config = load_provider_configs(ROOT / "config" / "providers.json")[0]
        summary = config.public_summary({"MINIMAX_API_KEY": "stub"})
        self.assertNotIn("stub", str(summary))
        self.assertTrue(summary["environment_present"]["MINIMAX_API_KEY"])

    def test_string_policy_boolean_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "must be boolean"):
            ProviderConfig.from_dict(
                {
                    "id": "ambiguous",
                    "kind": "grok_responses_pending",
                    "enabled": "false",
                    "auth_mode": "pending",
                    "api_usage_allowed": False,
                }
            )

    def test_unknown_privacy_level_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "approved_privacy is invalid"):
            ProviderConfig(
                id="bad-privacy",
                kind="grok_responses_pending",
                enabled=False,
                auth_mode=AuthMode.PENDING,
                api_usage_allowed=False,
                approved_privacy=("secret_magic",),
            )


if __name__ == "__main__":
    unittest.main()
