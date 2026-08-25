from __future__ import annotations

import unittest
from typing import Any, Mapping

from macr_runtime.config import AuthMode, ConnectionScope, ProviderConfig
from macr_runtime.contracts import PrivacyLevel, TaskConstraints, TaskContract
from macr_runtime.errors import ProviderPolicyError, ProviderProtocolError
from macr_runtime.providers.minimax import MiniMaxProvider
from macr_runtime.providers.common import BOUNDED_WORKER_INSTRUCTION
from macr_runtime.providers.http_json import UrllibJsonTransport


class FakeTransport:
    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def post_json(self, url, *, headers, payload, timeout_s):
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "payload": dict(payload),
                "timeout_s": timeout_s,
            }
        )
        return self.response


def provider_config() -> ProviderConfig:
    return ProviderConfig(
        id="minimax",
        kind="minimax_openai_compatible",
        enabled=True,
        auth_mode=AuthMode.API_KEY,
        api_usage_allowed=True,
        connection_scope=ConnectionScope.EXTERNAL_HTTPS,
        api_key_env="MACR_TEST_PROVIDER_KEY",
        base_url_env="MACR_TEST_PROVIDER_BASE_URL",
        model_env="MACR_TEST_PROVIDER_MODEL",
        endpoint_path="/chat/completions",
        allowed_hosts=("example.invalid",),
        approved_privacy=(PrivacyLevel.INTERNAL_APPROVED.value,),
    )


def cloud_task() -> TaskContract:
    return TaskContract(
        task_id="provider-test-001",
        goal="return a bounded test candidate",
        task_type="testing",
        constraints=TaskConstraints(
            max_cost_usd=0.01,
            max_latency_s=5,
            internet=True,
            privacy=PrivacyLevel.INTERNAL_APPROVED,
        ),
    )


class MiniMaxProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = {
            "MACR_TEST_PROVIDER_KEY": "test-key",
            "MACR_TEST_PROVIDER_BASE_URL": "https://example.invalid/v1",
            "MACR_TEST_PROVIDER_MODEL": "test-model",
        }

    def test_offline_transport_normalizes_candidate(self) -> None:
        transport = FakeTransport(
            {
                "id": "response-001",
                "choices": [{"message": {"content": "candidate answer"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
            }
        )
        provider = MiniMaxProvider(provider_config(), transport=transport, environ=self.env)
        result = provider.invoke(cloud_task())
        self.assertEqual(result.status.value, "candidate_success")
        self.assertEqual(result.answer, "candidate answer")
        self.assertEqual(len(transport.calls), 1)
        call = transport.calls[0]
        self.assertEqual(call["url"], "https://example.invalid/v1/chat/completions")
        self.assertEqual(call["payload"]["model"], "test-model")
        self.assertEqual(call["headers"]["Authorization"], "Bearer test-key")
        self.assertNotIn("test-key", str(result.to_dict()))

    def test_worker_instruction_is_shared_constant(self) -> None:
        transport = FakeTransport(
            {"choices": [{"message": {"content": "candidate"}}]}
        )
        MiniMaxProvider(provider_config(), transport=transport, environ=self.env).invoke(
            cloud_task()
        )
        self.assertEqual(
            transport.calls[0]["payload"]["messages"][0]["content"],
            BOUNDED_WORKER_INSTRUCTION,
        )

    def test_missing_environment_fails_health_without_network(self) -> None:
        transport = FakeTransport({})
        provider = MiniMaxProvider(provider_config(), transport=transport, environ={})
        health = provider.health()
        self.assertFalse(health.ready)
        self.assertEqual(health.status, "configuration_incomplete")
        self.assertEqual(transport.calls, [])

    def test_local_only_task_is_denied_before_network(self) -> None:
        transport = FakeTransport({})
        provider = MiniMaxProvider(provider_config(), transport=transport, environ=self.env)
        task = TaskContract(
            task_id="local-only-001",
            goal="must remain local",
            task_type="testing",
            constraints=TaskConstraints(
                internet=True,
                privacy=PrivacyLevel.LOCAL_ONLY,
            ),
        )
        with self.assertRaises(ProviderPolicyError):
            provider.invoke(task)
        self.assertEqual(transport.calls, [])

    def test_invalid_response_shape_is_rejected(self) -> None:
        provider = MiniMaxProvider(
            provider_config(),
            transport=FakeTransport({"unexpected": True}),
            environ=self.env,
        )
        with self.assertRaises(ProviderProtocolError):
            provider.invoke(cloud_task())

    def test_zero_cost_budget_is_denied_before_network(self) -> None:
        transport = FakeTransport({})
        provider = MiniMaxProvider(provider_config(), transport=transport, environ=self.env)
        task = TaskContract(
            task_id="zero-budget-001",
            goal="must not authorize a billable call",
            task_type="policy_test",
            constraints=TaskConstraints(
                max_cost_usd=0,
                max_latency_s=5,
                internet=True,
                privacy=PrivacyLevel.INTERNAL_APPROVED,
            ),
        )
        with self.assertRaisesRegex(ProviderPolicyError, "positive"):
            provider.invoke(task)
        self.assertEqual(transport.calls, [])

    def test_oversized_request_is_rejected_before_network(self) -> None:
        transport = UrllibJsonTransport(max_request_bytes=10)
        with self.assertRaisesRegex(ProviderProtocolError, "request exceeded"):
            transport.post_json(
                "https://example.invalid/v1/chat/completions",
                headers={"Authorization": "Bearer test-key"},
                payload={"input": "larger than ten bytes"},
                timeout_s=1,
            )

    def test_unapproved_host_is_denied_before_network(self) -> None:
        transport = FakeTransport({})
        environment = dict(self.env)
        environment["MACR_TEST_PROVIDER_BASE_URL"] = "https://not-minimax.invalid/v1"
        provider = MiniMaxProvider(
            provider_config(),
            transport=transport,
            environ=environment,
        )
        with self.assertRaisesRegex(ProviderPolicyError, "not allowlisted"):
            provider.invoke(cloud_task())
        self.assertEqual(transport.calls, [])

    def test_missing_capability_is_denied_before_network(self) -> None:
        transport = FakeTransport({})
        provider = MiniMaxProvider(provider_config(), transport=transport, environ=self.env)
        task = TaskContract(
            task_id="capability-gate-001",
            goal="must not route tool work to a text-only adapter",
            task_type="policy_test",
            constraints=TaskConstraints(
                max_cost_usd=0.01,
                max_latency_s=5,
                internet=True,
                privacy=PrivacyLevel.INTERNAL_APPROVED,
            ),
            required_capabilities=("filesystem_write",),
        )
        with self.assertRaisesRegex(ProviderPolicyError, "lacks required capabilities"):
            provider.invoke(task)
        self.assertEqual(transport.calls, [])


if __name__ == "__main__":
    unittest.main()
