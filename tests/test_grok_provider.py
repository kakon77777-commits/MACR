from __future__ import annotations

import unittest
from typing import Any, Mapping

from macr_runtime.config import AuthMode, ConnectionScope, ProviderConfig
from macr_runtime.contracts import (
    PrivacyLevel,
    ResultStatus,
    TaskConstraints,
    TaskContract,
)
from macr_runtime.errors import (
    ProviderPolicyError,
    ProviderProtocolError,
    ProviderUnavailableError,
)
from macr_runtime.providers.grok import GrokResponsesProvider


class FakeTransport:
    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = response
        self.posts: list[dict[str, Any]] = []

    def get_json(self, url, *, headers, timeout_s):
        raise AssertionError("Grok adapter must not issue GET requests")

    def post_json(self, url, *, headers, payload, timeout_s):
        self.posts.append(
            {
                "url": url,
                "headers": dict(headers),
                "payload": dict(payload),
                "timeout_s": timeout_s,
            }
        )
        return self.response


def grok_config(
    provider_id: str,
    model: str,
    reasoning_effort: str | None,
) -> ProviderConfig:
    return ProviderConfig(
        id=provider_id,
        kind="grok_responses",
        enabled=True,
        auth_mode=AuthMode.API_KEY,
        api_usage_allowed=True,
        connection_scope=ConnectionScope.EXTERNAL_HTTPS,
        api_key_env="XAI_API_KEY",
        base_url="https://api.x.ai/v1",
        model=model,
        reasoning_effort=reasoning_effort,
        endpoint_path="/responses",
        allowed_hosts=("api.x.ai",),
        capabilities=("text_generation",),
        approved_privacy=(PrivacyLevel.PUBLIC.value,),
    )


def cloud_task(
    max_cost_usd: float = 0.01,
    max_output_tokens: int = 64,
) -> TaskContract:
    return TaskContract(
        task_id="grok-test-001",
        goal="return a bounded candidate",
        task_type="provider_test",
        constraints=TaskConstraints(
            max_cost_usd=max_cost_usd,
            max_latency_s=30,
            max_output_tokens=max_output_tokens,
            internet=True,
            privacy=PrivacyLevel.PUBLIC,
        ),
        required_capabilities=("text_generation",),
    )


def success_document(model: str) -> dict[str, Any]:
    return {
        "id": "resp-test-1",
        "model": model,
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "candidate"}],
            }
        ],
        "usage": {
            "input_tokens": 20,
            "input_tokens_details": {"cached_tokens": 5},
            "output_tokens": 10,
            "output_tokens_details": {"reasoning_tokens": 6},
            "cost_in_usd_ticks": 2_500_000,
            "num_server_side_tools_used": 0,
        },
    }


class GrokProviderTests(unittest.TestCase):
    def test_frontier_request_is_stateless_high_reasoning_and_normalized(self):
        transport = FakeTransport(success_document("grok-4.6"))
        result = GrokResponsesProvider(
            grok_config("grok", "grok-4.6", "high"),
            transport=transport,
            environ={"XAI_API_KEY": "test-key"},
        ).invoke(cloud_task(max_cost_usd=0.01, max_output_tokens=64))
        call = transport.posts[0]
        self.assertEqual(call["url"], "https://api.x.ai/v1/responses")
        self.assertEqual(call["payload"]["model"], "grok-4.6")
        self.assertFalse(call["payload"]["store"])
        self.assertEqual(call["payload"]["reasoning"], {"effort": "high"})
        self.assertEqual(call["payload"]["max_output_tokens"], 64)
        self.assertNotIn("tools", call["payload"])
        self.assertEqual(call["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(result.answer, "candidate")
        self.assertEqual(result.cost["currency_cost_usd"], 0.00025)
        self.assertEqual(result.provider_meta["metrics"]["cached_tokens"], 5)
        self.assertNotIn("test-key", str(result.to_dict()))

    def test_standard_profile_uses_4_3_without_reasoning_override(self):
        transport = FakeTransport(success_document(model="grok-4.3"))
        GrokResponsesProvider(
            grok_config("grok_standard", "grok-4.3", None),
            transport=transport,
            environ={"XAI_API_KEY": "test-key"},
        ).invoke(cloud_task())
        payload = transport.posts[0]["payload"]
        self.assertEqual(payload["model"], "grok-4.3")
        self.assertNotIn("reasoning", payload)

    def test_returned_model_mismatch_is_rejected_without_fallback(self):
        transport = FakeTransport(success_document(model="grok-4.3"))
        provider = GrokResponsesProvider(
            grok_config("grok", "grok-4.6", "high"),
            transport=transport,
            environ={"XAI_API_KEY": "test-key"},
        )
        with self.assertRaisesRegex(ProviderProtocolError, "model mismatch"):
            provider.invoke(cloud_task())
        self.assertEqual(len(transport.posts), 1)

    def test_missing_key_fails_before_transport(self):
        transport = FakeTransport(success_document(model="grok-4.6"))
        provider = GrokResponsesProvider(
            grok_config("grok", "grok-4.6", "high"),
            transport=transport,
            environ={},
        )
        with self.assertRaisesRegex(ProviderUnavailableError, "XAI_API_KEY"):
            provider.invoke(cloud_task())
        self.assertEqual(transport.posts, [])

    def test_nonzero_server_tools_are_rejected(self):
        document = success_document(model="grok-4.6")
        document["usage"]["num_server_side_tools_used"] = 1
        provider = GrokResponsesProvider(
            grok_config("grok", "grok-4.6", "high"),
            transport=FakeTransport(document),
            environ={"XAI_API_KEY": "test-key"},
        )
        with self.assertRaisesRegex(ProviderProtocolError, "server-side tools"):
            provider.invoke(cloud_task())

    def test_budget_overrun_is_a_failure_with_actual_cost(self):
        provider = GrokResponsesProvider(
            grok_config("grok", "grok-4.6", "high"),
            transport=FakeTransport(success_document(model="grok-4.6")),
            environ={"XAI_API_KEY": "test-key"},
        )
        result = provider.invoke(cloud_task(max_cost_usd=0.0001))
        self.assertEqual(result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertEqual(result.answer, "candidate")
        self.assertEqual(result.cost["currency_cost_usd"], 0.00025)
        self.assertTrue(any("exceeded" in warning for warning in result.warnings))

    def test_cloud_policy_gates_fail_before_transport(self):
        cases = (
            TaskConstraints(
                max_cost_usd=0.01,
                internet=False,
                privacy=PrivacyLevel.PUBLIC,
            ),
            TaskConstraints(
                max_cost_usd=0.01,
                internet=True,
                privacy=PrivacyLevel.LOCAL_ONLY,
            ),
            TaskConstraints(
                max_cost_usd=0,
                internet=True,
                privacy=PrivacyLevel.PUBLIC,
            ),
        )
        for index, constraints in enumerate(cases):
            with self.subTest(index=index):
                transport = FakeTransport(success_document(model="grok-4.6"))
                provider = GrokResponsesProvider(
                    grok_config("grok", "grok-4.6", "high"),
                    transport=transport,
                    environ={"XAI_API_KEY": "test-key"},
                )
                task = TaskContract(
                    task_id=f"grok-policy-{index}",
                    goal="fail before transport",
                    task_type="policy_test",
                    constraints=constraints,
                )
                with self.assertRaises(ProviderPolicyError):
                    provider.invoke(task)
                self.assertEqual(transport.posts, [])

    def test_missing_capability_fails_before_transport(self):
        transport = FakeTransport(success_document(model="grok-4.6"))
        provider = GrokResponsesProvider(
            grok_config("grok", "grok-4.6", "high"),
            transport=transport,
            environ={"XAI_API_KEY": "test-key"},
        )
        base = cloud_task()
        task = TaskContract(
            task_id=base.task_id,
            goal=base.goal,
            task_type=base.task_type,
            constraints=base.constraints,
            required_capabilities=("filesystem_write",),
        )
        with self.assertRaisesRegex(ProviderPolicyError, "lacks required capabilities"):
            provider.invoke(task)
        self.assertEqual(transport.posts, [])

    def test_invalid_output_shape_and_cost_are_rejected(self):
        invalid_documents = (
            {"model": "grok-4.6", "usage": {}},
            {
                "model": "grok-4.6",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "candidate"}],
                    }
                ],
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cost_in_usd_ticks": True,
                    "num_server_side_tools_used": 0,
                },
            },
        )
        for document in invalid_documents:
            with self.subTest(document=document):
                provider = GrokResponsesProvider(
                    grok_config("grok", "grok-4.6", "high"),
                    transport=FakeTransport(document),
                    environ={"XAI_API_KEY": "test-key"},
                )
                with self.assertRaises(ProviderProtocolError):
                    provider.invoke(cloud_task())

    def test_health_is_offline_and_reports_key_presence_only(self):
        transport = FakeTransport(success_document(model="grok-4.6"))
        provider = GrokResponsesProvider(
            grok_config("grok", "grok-4.6", "high"),
            transport=transport,
            environ={"XAI_API_KEY": "test-key"},
        )
        health = provider.health()
        self.assertTrue(health.ready)
        self.assertEqual(health.status, "configured_offline")
        self.assertEqual(transport.posts, [])
        self.assertNotIn("test-key", str(health.to_dict()))


if __name__ == "__main__":
    unittest.main()
