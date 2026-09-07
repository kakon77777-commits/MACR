from __future__ import annotations

import unittest
from dataclasses import replace
from typing import Any, Mapping

from macr_runtime.config import AuthMode, ConnectionScope, ProviderConfig
from macr_runtime.contracts import PrivacyLevel
from macr_runtime.direct_contracts import DirectMessage
from macr_runtime.direct_providers import (
    DirectProviderRegistry,
    GrokDirectAdapter,
    QwythosDirectAdapter,
)
from macr_runtime.direct_settings import operator_managed_settings
from macr_runtime.errors import (
    ConfigurationError,
    ProviderOutputBudgetTooSmallError,
    ProviderProtocolError,
    ProviderUnavailableError,
)
from macr_runtime.execution import ProviderState


MODEL = "hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M"
DIGEST = "c" * 64
VALID_XAI_KEY = "xai-" + ("A" * 24)


def grok_settings():
    return replace(
        operator_managed_settings(),
        max_output_tokens=32_768,
        context_warning_tokens=180_000,
        hard_context_tokens=400_000,
    )


class FakeTransport:
    def __init__(
        self,
        *,
        get_response: Mapping[str, Any] | None = None,
        post_response: Mapping[str, Any] | None = None,
    ) -> None:
        self.get_response = get_response or {}
        self.post_response = post_response or {}
        self.gets: list[dict[str, Any]] = []
        self.posts: list[dict[str, Any]] = []

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


def grok_config() -> ProviderConfig:
    return ProviderConfig(
        id="grok",
        kind="grok_responses",
        enabled=True,
        auth_mode=AuthMode.API_KEY,
        api_usage_allowed=True,
        connection_scope=ConnectionScope.EXTERNAL_HTTPS,
        api_key_env="XAI_API_KEY",
        base_url="https://api.x.ai/v1",
        model="grok-4.6",
        reasoning_effort="high",
        endpoint_path="/responses",
        allowed_hosts=("api.x.ai",),
        capabilities=("text_generation",),
        approved_privacy=(PrivacyLevel.PUBLIC.value,),
    )


def qwythos_config() -> ProviderConfig:
    return ProviderConfig(
        id="ollama_qwythos",
        kind="ollama_local_chat",
        enabled=True,
        auth_mode=AuthMode.NONE,
        api_usage_allowed=True,
        connection_scope=ConnectionScope.LOOPBACK_HTTP,
        base_url="http://127.0.0.1:11434",
        model=MODEL,
        endpoint_path="/api/chat",
        allowed_hosts=("127.0.0.1",),
        capabilities=("text_generation",),
        approved_privacy=(PrivacyLevel.LOCAL_ONLY.value,),
    )


def grok_response(*, model: str = "grok-4.6", tools: int = 0) -> dict[str, Any]:
    return {
        "id": "resp-direct-1",
        "model": model,
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "Grok answer"}],
            }
        ],
        "usage": {
            "input_tokens": 21,
            "input_tokens_details": {"cached_tokens": 4},
            "output_tokens": 11,
            "output_tokens_details": {"reasoning_tokens": 7},
            "cost_in_usd_ticks": 3_000_000,
            "num_server_side_tools_used": tools,
        },
    }


def tags_response() -> dict[str, Any]:
    return {
        "models": [
            {
                "name": MODEL,
                "model": MODEL,
                "modified_at": "2026-08-29T00:00:00Z",
                "size": 6_000_000_000,
                "digest": DIGEST,
                "details": {
                    "parent_model": "",
                    "format": "gguf",
                    "family": "qwen2",
                    "families": ["qwen2"],
                    "parameter_size": "9B",
                    "quantization_level": "Q4_K_M",
                },
            }
        ]
    }


def qwythos_response() -> dict[str, Any]:
    return {
        "model": MODEL,
        "created_at": "2026-08-29T00:00:10Z",
        "message": {
            "role": "assistant",
            "content": "Qwythos answer",
            "thinking": "not exposed",
        },
        "done": True,
        "done_reason": "stop",
        "total_duration": 2_000_000_000,
        "load_duration": 1_000_000_000,
        "prompt_eval_count": 20,
        "prompt_eval_duration": 250_000_000,
        "eval_count": 10,
        "eval_duration": 500_000_000,
    }


class DirectProviderTests(unittest.TestCase):
    def test_grok_request_is_native_exact_and_has_no_hidden_worker_prompt(self) -> None:
        transport = FakeTransport(post_response=grok_response())
        adapter = GrokDirectAdapter(
            grok_config(),
            transport=transport,
            environ={"XAI_API_KEY": VALID_XAI_KEY},
            monotonic=iter((10.0, 10.25)).__next__,
        )
        messages = (
            DirectMessage("system", "Visible system only"),
            DirectMessage("user", "first question"),
            DirectMessage("assistant", "prior answer"),
            DirectMessage("user", "second question"),
        )

        reply = adapter.invoke(messages, grok_settings())

        call = transport.posts[0]
        self.assertEqual(call["url"], "https://api.x.ai/v1/responses")
        self.assertEqual(
            call["payload"],
            {
                "model": "grok-4.6",
                "input": [item.to_dict() for item in messages],
                "store": False,
                "max_output_tokens": 32_768,
                "reasoning": {"effort": "high"},
            },
        )
        serialized = str(call["payload"])
        self.assertNotIn("MACR worker", serialized)
        self.assertNotIn("evidence", serialized.lower())
        self.assertNotIn("tools", call["payload"])
        self.assertEqual(
            call["headers"]["Authorization"],
            f"Bearer {VALID_XAI_KEY}",
        )
        self.assertIsNone(reply.validation_error)
        self.assertEqual(reply.observation.answer_bytes, b"Grok answer")
        self.assertEqual(reply.observation.model, "grok-4.6")
        self.assertEqual(reply.observation.finish_reason, "stop")
        self.assertEqual(reply.observation.usage.reasoning_tokens, 7)
        self.assertEqual(reply.observation.currency_cost_usd, 0.0003)
        self.assertEqual(reply.observation.duration_ms, 250)
        self.assertNotIn(VALID_XAI_KEY, str(reply.to_public_dict()))

    def test_blank_system_prompt_means_no_system_message(self) -> None:
        transport = FakeTransport(post_response=grok_response())
        GrokDirectAdapter(
            grok_config(),
            transport=transport,
            environ={"XAI_API_KEY": VALID_XAI_KEY},
        ).invoke(
            (DirectMessage("user", "question"),),
            grok_settings(),
        )
        self.assertEqual(
            transport.posts[0]["payload"]["input"],
            [{"role": "user", "content": "question"}],
        )

    def test_grok_preserves_observation_while_marking_protocol_rejection(self) -> None:
        for response, reason in (
            (grok_response(model="grok-4.3"), "model_mismatch"),
            (grok_response(tools=1), "unexpected_tools"),
        ):
            with self.subTest(reason=reason):
                reply = GrokDirectAdapter(
                    grok_config(),
                    transport=FakeTransport(post_response=response),
                    environ={"XAI_API_KEY": VALID_XAI_KEY},
                ).invoke(
                    (DirectMessage("user", "question"),),
                    grok_settings(),
                )
                self.assertEqual(reply.validation_error, reason)
                self.assertEqual(reply.observation.answer_bytes, b"Grok answer")
                self.assertEqual(reply.observation.usage.input_tokens, 21)

    def test_grok_missing_key_fails_before_transport(self) -> None:
        transport = FakeTransport(post_response=grok_response())
        adapter = GrokDirectAdapter(
            grok_config(),
            transport=transport,
            environ={},
        )
        with self.assertRaisesRegex(ProviderUnavailableError, "XAI_API_KEY"):
            adapter.invoke(
                (DirectMessage("user", "question"),),
                grok_settings(),
            )
        self.assertEqual(transport.posts, [])

    def test_grok_output_floor_fails_before_key_or_transport(self) -> None:
        transport = FakeTransport(post_response=grok_response())
        adapter = GrokDirectAdapter(
            grok_config(),
            transport=transport,
            environ={},
        )

        with self.assertRaises(ProviderOutputBudgetTooSmallError):
            adapter.invoke(
                (DirectMessage("user", "question"),),
                operator_managed_settings(),
            )

        self.assertEqual(transport.posts, [])

    def test_grok_uuid_identifier_is_not_accepted_as_an_api_secret(self) -> None:
        transport = FakeTransport(post_response=grok_response())
        adapter = GrokDirectAdapter(
            grok_config(),
            transport=transport,
            environ={
                "XAI_API_KEY": "00000000-0000-4000-8000-000000000999"
            },
        )
        health = adapter.health()
        self.assertFalse(health.ready)
        self.assertEqual(health.status, "configuration_incomplete")
        with self.assertRaisesRegex(ProviderUnavailableError, "format"):
            adapter.invoke(
                (DirectMessage("user", "question"),),
                grok_settings(),
            )
        self.assertEqual(transport.posts, [])

    def test_qwythos_health_pins_digest_and_request_is_native(self) -> None:
        transport = FakeTransport(
            get_response=tags_response(),
            post_response=qwythos_response(),
        )
        adapter = QwythosDirectAdapter(
            qwythos_config(),
            transport=transport,
            environ={"MACR_OLLAMA_KEEP_ALIVE": "5m"},
        )
        identity = adapter.model_identity()
        self.assertEqual(identity, {"model": MODEL, "model_digest": DIGEST})
        health = adapter.health()
        self.assertTrue(health.ready)
        self.assertEqual(health.status, "available_local")

        messages = (
            DirectMessage("user", "first"),
            DirectMessage("assistant", "second"),
            DirectMessage("user", "third"),
        )
        reply = adapter.invoke(messages, operator_managed_settings())
        payload = transport.posts[0]["payload"]
        self.assertEqual(payload["model"], MODEL)
        self.assertEqual(payload["messages"], [item.to_dict() for item in messages])
        self.assertFalse(payload["stream"])
        self.assertFalse(payload["think"])
        self.assertEqual(payload["keep_alive"], "5m")
        self.assertEqual(
            payload["options"],
            {
                "num_ctx": 8192,
                "num_predict": 4096,
                "temperature": 0.6,
                "top_p": 0.95,
                "top_k": 20,
            },
        )
        self.assertIsNone(reply.validation_error)
        self.assertEqual(reply.observation.answer_bytes, b"Qwythos answer")
        self.assertEqual(reply.observation.cost_kind, "zero_local")
        self.assertEqual(reply.observation.currency_cost_usd, 0.0)
        self.assertNotIn("not exposed", str(reply.to_public_dict()))

    def test_qwythos_missing_model_and_tool_calls_are_typed(self) -> None:
        missing = QwythosDirectAdapter(
            qwythos_config(),
            transport=FakeTransport(get_response={"models": []}),
            environ={},
        )
        with self.assertRaisesRegex(ProviderUnavailableError, "not installed"):
            missing.model_identity()

        response = qwythos_response()
        response["message"]["tool_calls"] = [
            {"function": {"name": "unexpected", "arguments": {}}}
        ]
        reply = QwythosDirectAdapter(
            qwythos_config(),
            transport=FakeTransport(
                get_response=tags_response(),
                post_response=response,
            ),
            environ={},
        ).invoke(
            (DirectMessage("user", "question"),),
            operator_managed_settings(),
        )
        self.assertEqual(reply.validation_error, "unexpected_tools")
        self.assertEqual(reply.observation.answer_bytes, b"Qwythos answer")

    def test_registry_exposes_only_exact_direct_profiles(self) -> None:
        registry = DirectProviderRegistry.from_configs(
            (grok_config(), qwythos_config()),
            transports={
                "grok": FakeTransport(post_response=grok_response()),
                "ollama_qwythos": FakeTransport(get_response=tags_response()),
            },
            environ={"XAI_API_KEY": VALID_XAI_KEY},
        )
        self.assertEqual(registry.provider_ids(), ("grok", "ollama_qwythos"))
        self.assertIsInstance(registry.get("grok"), GrokDirectAdapter)
        with self.assertRaisesRegex(KeyError, "not a Direct provider"):
            registry.get("glm_flash_worker")

        with self.assertRaisesRegex(ConfigurationError, "requires both"):
            DirectProviderRegistry.from_configs(
                (grok_config(),),
                environ={"XAI_API_KEY": VALID_XAI_KEY},
            )

    def test_message_sequence_rejects_hidden_or_invalid_shapes(self) -> None:
        adapter = GrokDirectAdapter(
            grok_config(),
            transport=FakeTransport(post_response=grok_response()),
            environ={"XAI_API_KEY": VALID_XAI_KEY},
        )
        invalid = (
            (),
            (DirectMessage("assistant", "answer first"),),
            (
                DirectMessage("user", "question"),
                DirectMessage("system", "late hidden prompt"),
            ),
            (
                DirectMessage("system", "one"),
                DirectMessage("system", "two"),
                DirectMessage("user", "question"),
            ),
        )
        for messages in invalid:
            with self.subTest(messages=messages), self.assertRaises(
                ProviderProtocolError
            ):
                adapter.invoke(messages, operator_managed_settings())


if __name__ == "__main__":
    unittest.main()
