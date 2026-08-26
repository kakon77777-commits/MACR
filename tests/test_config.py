import unittest
from pathlib import Path

from macr_runtime.config import (
    AuthMode,
    ConnectionScope,
    ProviderConfig,
    load_provider_configs,
)
from macr_runtime.errors import ConfigurationError


ROOT = Path(__file__).resolve().parents[1]


class ProviderConfigTests(unittest.TestCase):
    def test_repository_config_loads(self) -> None:
        configs = load_provider_configs(ROOT / "config" / "providers.json")
        self.assertEqual(
            [item.id for item in configs],
            [
                "minimax",
                "grok",
                "grok_standard",
                "ollama_qwythos",
                "claude_subscription",
            ],
        )
        claude = configs[4]
        self.assertFalse(claude.api_usage_allowed)
        self.assertEqual(claude.auth_mode, AuthMode.SUBSCRIPTION_CLIENT)

    def test_grok_profiles_are_enabled_and_fixed(self) -> None:
        configs = load_provider_configs(ROOT / "config" / "providers.json")
        by_id = {item.id: item for item in configs}
        self.assertTrue(by_id["grok"].enabled)
        self.assertEqual(by_id["grok"].model, "grok-4.6")
        self.assertEqual(by_id["grok"].reasoning_effort, "high")
        self.assertTrue(by_id["grok_standard"].enabled)
        self.assertEqual(by_id["grok_standard"].model, "grok-4.3")
        self.assertIsNone(by_id["grok_standard"].reasoning_effort)
        self.assertEqual(
            by_id["ollama_qwythos"].base_url,
            "http://127.0.0.1:11434",
        )
        self.assertEqual(
            by_id["ollama_qwythos"].connection_scope,
            ConnectionScope.LOOPBACK_HTTP,
        )

    def test_enabled_api_provider_requires_environment_names(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "lacks"):
            ProviderConfig(
                id="bad",
                kind="minimax_openai_compatible",
                enabled=True,
                auth_mode=AuthMode.API_KEY,
                api_usage_allowed=True,
                connection_scope=ConnectionScope.EXTERNAL_HTTPS,
                allowed_hosts=("example.invalid",),
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

    def test_schema_v1_is_rejected_with_migration_message(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "schema_version 1.*migrate.*2"):
            load_provider_configs(ROOT / "tests" / "fixtures" / "providers-v1.json")

    def test_static_and_environment_values_are_mutually_exclusive(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "base_url.*base_url_env"):
            ProviderConfig.from_dict(
                {
                    "id": "ambiguous",
                    "kind": "grok_responses",
                    "enabled": True,
                    "auth_mode": "api_key",
                    "api_usage_allowed": True,
                    "connection_scope": "external_https",
                    "api_key_env": "TEST_KEY",
                    "base_url": "https://api.x.ai/v1",
                    "base_url_env": "TEST_BASE",
                    "model": "grok-4.6",
                    "allowed_hosts": ["api.x.ai"],
                }
            )

    def test_external_base_url_requires_https_and_allowlisted_host(self) -> None:
        for base_url in ("http://api.x.ai/v1", "https://not-xai.invalid/v1"):
            with self.subTest(base_url=base_url):
                config = ProviderConfig.from_dict(
                    {
                        "id": "external",
                        "kind": "grok_responses",
                        "enabled": True,
                        "auth_mode": "api_key",
                        "api_usage_allowed": True,
                        "connection_scope": "external_https",
                        "api_key_env": "TEST_KEY",
                        "base_url": base_url,
                        "model": "grok-4.6",
                        "allowed_hosts": ["api.x.ai"],
                    }
                )
                with self.assertRaises(ConfigurationError):
                    config.resolve_base_url({})

    def test_loopback_scope_rejects_localhost_and_credentials(self) -> None:
        for base_url in (
            "http://localhost:11434",
            "http://user:password@127.0.0.1:11434",
        ):
            with self.subTest(base_url=base_url):
                config = ProviderConfig.from_dict(
                    {
                        "id": "local",
                        "kind": "ollama_local_chat",
                        "enabled": True,
                        "auth_mode": "none",
                        "api_usage_allowed": True,
                        "connection_scope": "loopback_http",
                        "base_url": base_url,
                        "model": "local-model",
                        "allowed_hosts": ["127.0.0.1"],
                    }
                )
                with self.assertRaises(ConfigurationError):
                    config.resolve_base_url({})

    def test_service_account_provider_requires_named_environment(self) -> None:
        with self.assertRaisesRegex(
            ConfigurationError,
            "credential_path_env, project_env",
        ):
            ProviderConfig(
                id="google",
                kind="google_vertex_gemini",
                enabled=True,
                auth_mode=AuthMode.SERVICE_ACCOUNT,
                api_usage_allowed=True,
                connection_scope=ConnectionScope.EXTERNAL_HTTPS,
                base_url="https://aiplatform.googleapis.com",
                model="gemini-3.7-flash",
                location="global",
                allowed_hosts=(
                    "aiplatform.googleapis.com",
                    "oauth2.googleapis.com",
                ),
            )

    def test_service_account_environment_is_public_metadata_only(self) -> None:
        config = ProviderConfig(
            id="google",
            kind="google_vertex_gemini",
            enabled=True,
            auth_mode=AuthMode.SERVICE_ACCOUNT,
            api_usage_allowed=True,
            connection_scope=ConnectionScope.EXTERNAL_HTTPS,
            credential_path_env="GOOGLE_APPLICATION_CREDENTIALS",
            project_env="GOOGLE_CLOUD_PROJECT",
            base_url="https://aiplatform.googleapis.com",
            model="gemini-3.7-flash",
            location="global",
            allowed_hosts=(
                "aiplatform.googleapis.com",
                "oauth2.googleapis.com",
            ),
        )
        summary = config.public_summary(
            {
                "GOOGLE_APPLICATION_CREDENTIALS": r"D:\KEY\GOOGLE_VERTEX.json",
                "GOOGLE_CLOUD_PROJECT": "private-project",
            }
        )
        self.assertEqual(
            summary["required_environment"],
            ["GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT"],
        )
        self.assertNotIn("private-project", str(summary))
        self.assertNotIn("GOOGLE_VERTEX.json", str(summary))


if __name__ == "__main__":
    unittest.main()
