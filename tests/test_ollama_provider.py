from __future__ import annotations

import unittest

from macr_runtime.config import AuthMode, ConnectionScope, ProviderConfig
from macr_runtime.contracts import PrivacyLevel, TaskConstraints, TaskContract
from macr_runtime.errors import (
    ConfigurationError,
    ProviderPolicyError,
    ProviderProtocolError,
    ProviderUnavailableError,
)
from macr_runtime.providers.ollama import OllamaChatProvider, _resolve_keep_alive


MODEL = "hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M"


class FakeTransport:
    def __init__(self, get_response, post_response):
        self.get_response = get_response
        self.post_response = post_response
        self.gets = []
        self.posts = []

    def get_json(self, url, *, headers, timeout_s):
        self.gets.append(
            {"url": url, "headers": dict(headers), "timeout_s": timeout_s}
        )
        return self.get_response

    def post_json(self, url, *, headers, payload, timeout_s):
        self.posts.append(
            {
                "url": url,
                "headers": dict(headers),
                "payload": dict(payload),
                "timeout_s": timeout_s,
            }
        )
        return self.post_response


def ollama_config(base_url: str = "http://127.0.0.1:11434") -> ProviderConfig:
    return ProviderConfig(
        id="ollama_qwythos",
        kind="ollama_local_chat",
        enabled=True,
        auth_mode=AuthMode.NONE,
        api_usage_allowed=True,
        connection_scope=ConnectionScope.LOOPBACK_HTTP,
        base_url=base_url,
        model=MODEL,
        endpoint_path="/api/chat",
        allowed_hosts=("127.0.0.1",),
        capabilities=("text_generation",),
        approved_privacy=(PrivacyLevel.LOCAL_ONLY.value,),
    )


def local_task(max_output_tokens: int = 64) -> TaskContract:
    return TaskContract(
        task_id="ollama-test-001",
        goal="return a local candidate",
        task_type="provider_test",
        constraints=TaskConstraints(
            max_cost_usd=0,
            max_latency_s=180,
            max_output_tokens=max_output_tokens,
            internet=False,
            privacy=PrivacyLevel.LOCAL_ONLY,
        ),
        required_capabilities=("text_generation",),
    )


def success_response() -> dict:
    return {
        "model": MODEL,
        "done": True,
        "done_reason": "stop",
        "message": {
            "role": "assistant",
            "content": "local candidate",
            "thinking": "omit",
        },
        "total_duration": 2_000_000_000,
        "load_duration": 1_000_000_000,
        "prompt_eval_count": 20,
        "prompt_eval_duration": 250_000_000,
        "eval_count": 10,
        "eval_duration": 500_000_000,
    }


class OllamaProviderTests(unittest.TestCase):
    def test_local_request_checks_exact_model_and_normalizes_metrics(self):
        transport = FakeTransport(
            get_response={"models": [{"name": MODEL}]},
            post_response=success_response(),
        )
        result = OllamaChatProvider(
            ollama_config(),
            transport=transport,
            environ={"MACR_OLLAMA_KEEP_ALIVE": "5m"},
        ).invoke(local_task(max_output_tokens=64))
        self.assertEqual(
            transport.gets[0]["url"],
            "http://127.0.0.1:11434/api/tags",
        )
        self.assertEqual(transport.gets[0]["headers"], {})
        payload = transport.posts[0]["payload"]
        self.assertFalse(payload["stream"])
        self.assertFalse(payload["think"])
        self.assertEqual(payload["keep_alive"], "5m")
        self.assertEqual(payload["options"]["num_ctx"], 8192)
        self.assertEqual(payload["options"]["num_predict"], 64)
        self.assertEqual(result.answer, "local candidate")
        self.assertEqual(result.cost["currency_cost_usd"], 0.0)
        self.assertEqual(result.provider_meta["metrics"]["duration_ms"], 2000)
        self.assertEqual(result.provider_meta["metrics"]["load_duration_ms"], 1000)
        self.assertEqual(result.provider_meta["metrics"]["eval_duration_ms"], 500)
        self.assertNotIn("omit", str(result.to_dict()))

    def test_external_or_cloud_ollama_url_is_rejected(self):
        config = ollama_config(base_url="https://ollama.com/api")
        with self.assertRaisesRegex(ConfigurationError, "127.0.0.1:11434"):
            OllamaChatProvider(config, transport=FakeTransport({}, {}), environ={})

    def test_missing_exact_model_fails_before_generation(self):
        transport = FakeTransport({"models": [{"name": "another-model"}]}, {})
        provider = OllamaChatProvider(ollama_config(), transport=transport, environ={})
        with self.assertRaisesRegex(ProviderUnavailableError, "not installed"):
            provider.invoke(local_task())
        self.assertEqual(transport.posts, [])

    def test_local_policy_gates_fail_before_any_transport(self):
        cases = (
            TaskConstraints(
                max_cost_usd=0,
                internet=True,
                privacy=PrivacyLevel.LOCAL_ONLY,
            ),
            TaskConstraints(
                max_cost_usd=0,
                internet=False,
                privacy=PrivacyLevel.PUBLIC,
            ),
            TaskConstraints(
                max_cost_usd=0.01,
                internet=False,
                privacy=PrivacyLevel.LOCAL_ONLY,
            ),
        )
        for index, constraints in enumerate(cases):
            with self.subTest(index=index):
                transport = FakeTransport({"models": []}, {})
                provider = OllamaChatProvider(
                    ollama_config(),
                    transport=transport,
                    environ={},
                )
                task = TaskContract(
                    task_id=f"ollama-policy-{index}",
                    goal="fail before transport",
                    task_type="policy_test",
                    constraints=constraints,
                )
                with self.assertRaises(ProviderPolicyError):
                    provider.invoke(task)
                self.assertEqual(transport.gets, [])
                self.assertEqual(transport.posts, [])

    def test_missing_capability_fails_before_transport(self):
        transport = FakeTransport({"models": [{"name": MODEL}]}, success_response())
        provider = OllamaChatProvider(ollama_config(), transport=transport, environ={})
        base = local_task()
        task = TaskContract(
            task_id=base.task_id,
            goal=base.goal,
            task_type=base.task_type,
            constraints=base.constraints,
            required_capabilities=("filesystem_write",),
        )
        with self.assertRaisesRegex(ProviderPolicyError, "lacks required capabilities"):
            provider.invoke(task)
        self.assertEqual(transport.gets, [])

    def test_keep_alive_allowlist(self):
        for value in ("0", "1m", "5m", "60m"):
            with self.subTest(value=value):
                self.assertEqual(
                    _resolve_keep_alive({"MACR_OLLAMA_KEEP_ALIVE": value}),
                    value,
                )
        for value in ("-1", "61m", "1h", "forever"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ProviderPolicyError, "1m..60m"):
                    _resolve_keep_alive({"MACR_OLLAMA_KEEP_ALIVE": value})

    def test_malformed_chat_response_is_rejected(self):
        transport = FakeTransport(
            {"models": [{"name": MODEL}]},
            {"model": MODEL, "done": True, "message": {"content": 42}},
        )
        provider = OllamaChatProvider(ollama_config(), transport=transport, environ={})
        with self.assertRaisesRegex(ProviderProtocolError, "message.content"):
            provider.invoke(local_task())

    def test_returned_model_mismatch_and_tool_calls_are_rejected(self):
        base_response = {
            "model": "another-model",
            "done": True,
            "message": {"content": "candidate"},
        }
        transport = FakeTransport(
            {"models": [{"name": MODEL}]},
            base_response,
        )
        provider = OllamaChatProvider(ollama_config(), transport=transport, environ={})
        with self.assertRaisesRegex(ProviderProtocolError, "model mismatch"):
            provider.invoke(local_task())

        base_response["model"] = MODEL
        base_response["message"] = {
            "content": "candidate",
            "tool_calls": [
                {"function": {"name": "unexpected", "arguments": {}}}
            ],
        }
        with self.assertRaisesRegex(ProviderProtocolError, "tool calls"):
            provider.invoke(local_task())

    def test_health_is_offline_and_does_not_contact_transport(self):
        transport = FakeTransport({"models": [{"name": MODEL}]}, success_response())
        provider = OllamaChatProvider(ollama_config(), transport=transport, environ={})
        health = provider.health()
        self.assertTrue(health.ready)
        self.assertEqual(health.status, "configured_offline")
        self.assertEqual(transport.gets, [])
        self.assertEqual(transport.posts, [])


if __name__ == "__main__":
    unittest.main()
