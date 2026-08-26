from __future__ import annotations

import unittest
import warnings
from types import SimpleNamespace

from macr_runtime.config import AuthMode, ConnectionScope, ProviderConfig
from macr_runtime.errors import ProviderProtocolError, ProviderUnavailableError
from macr_runtime.providers.google_core import (
    GoogleGenerationRequest,
    GoogleSdkTransport,
    GoogleUsage,
    estimate_gemini_cost,
    estimate_image_cost,
)


class FakeModels:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.error is not None:
            raise self.error
        return self.response


class FakeClientFactory:
    def __init__(self, response=None, error: Exception | None = None):
        self.models = FakeModels(response, error)
        self.kwargs = None

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(models=self.models)


def sdk_part(
    *,
    text=None,
    thought=False,
    inline_data=None,
    function_call=None,
    executable_code=None,
):
    return SimpleNamespace(
        text=text,
        thought=thought,
        inline_data=inline_data,
        function_call=function_call,
        executable_code=executable_code,
        code_execution_result=None,
        tool_call=None,
        tool_response=None,
    )


def sdk_response(
    *,
    model="gemini-3.7-flash",
    parts=None,
    candidates_count=1,
    prompt_tokens=10,
    finish_reason="STOP",
):
    candidate = SimpleNamespace(
        content=SimpleNamespace(parts=list(parts or ())),
        finish_reason=finish_reason,
    )
    return SimpleNamespace(
        model_version=model,
        response_id="google-response-1",
        candidates=[candidate for _ in range(candidates_count)],
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_tokens,
            candidates_token_count=4,
            thoughts_token_count=2,
            cached_content_token_count=0,
            total_token_count=16,
        ),
    )


def google_config() -> ProviderConfig:
    return ProviderConfig(
        id="google-test",
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
        endpoint_path="/v1",
        allowed_hosts=("aiplatform.googleapis.com", "oauth2.googleapis.com"),
    )


def text_request() -> GoogleGenerationRequest:
    return GoogleGenerationRequest(
        model="gemini-3.7-flash",
        system_instruction="bounded",
        goal="Return exactly: GOOGLE_OK",
        media=(),
        max_output_tokens=64,
        thinking_level="medium",
        response_modalities=("TEXT",),
        image_size=None,
    )


def transport_for(response=None, error=None):
    factory = FakeClientFactory(response=response, error=error)
    transport = GoogleSdkTransport(
        google_config(),
        environ={
            "GOOGLE_APPLICATION_CREDENTIALS": r"D:\KEY\fake.json",
            "GOOGLE_CLOUD_PROJECT": "test-project",
        },
        client_factory=factory,
        credential_loader=lambda path: object(),
    )
    return transport, factory


class GoogleCoreTests(unittest.TestCase):
    def test_constructs_one_attempt_tool_free_request_and_normalizes_text(self):
        transport, factory = transport_for(
            sdk_response(
                parts=[
                    sdk_part(text="hidden", thought=True),
                    sdk_part(text="GOOGLE_OK"),
                ]
            )
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            response = transport.generate(text_request(), timeout_s=30)
        dependency_warnings = [
            item
            for item in caught
            if "_UnionGenericAlias" in str(item.message)
        ]
        self.assertEqual(dependency_warnings, [])
        self.assertEqual(response.model, "gemini-3.7-flash")
        self.assertEqual(response.text, "GOOGLE_OK")
        self.assertEqual(response.images, ())
        self.assertEqual(factory.kwargs["project"], "test-project")
        http_options = factory.kwargs["http_options"]
        self.assertEqual(http_options.retry_options.attempts, 1)
        call = factory.models.calls[0]
        self.assertEqual(call["model"], "gemini-3.7-flash")
        self.assertIsNone(call["config"].tools)
        self.assertEqual(call["config"].max_output_tokens, 64)
        self.assertTrue(
            str(call["config"].thinking_config.thinking_level)
            .upper()
            .endswith("MEDIUM")
        )
        self.assertEqual(call["contents"].parts[0].text, "Return exactly: GOOGLE_OK")

    def test_rejects_candidate_shape_tools_wrong_modality_and_model(self):
        invalid = (
            sdk_response(parts=[sdk_part(text="one")], candidates_count=2),
            sdk_response(parts=[]),
            sdk_response(parts=[sdk_part(function_call=object())]),
            sdk_response(parts=[sdk_part(executable_code=object())]),
            sdk_response(
                parts=[
                    sdk_part(
                        inline_data=SimpleNamespace(
                            mime_type="image/jpeg",
                            data=b"x",
                        )
                    )
                ]
            ),
            sdk_response(model="gemini-other", parts=[sdk_part(text="one")]),
        )
        for document in invalid:
            with self.subTest(document=document):
                transport, _ = transport_for(document)
                with self.assertRaises(ProviderProtocolError):
                    transport.generate(text_request(), timeout_s=30)

    def test_usage_boolean_is_rejected(self):
        document = sdk_response(parts=[sdk_part(text="candidate")], prompt_tokens=True)
        transport, _ = transport_for(document)
        with self.assertRaisesRegex(ProviderProtocolError, "prompt_token_count"):
            transport.generate(text_request(), timeout_s=30)

    def test_empty_max_tokens_response_reports_safe_finish_reason(self):
        transport, _ = transport_for(
            sdk_response(parts=[], finish_reason="MAX_TOKENS")
        )
        with self.assertRaisesRegex(ProviderProtocolError, "MAX_TOKENS"):
            transport.generate(text_request(), timeout_s=30)

    def test_sdk_exception_text_is_sanitized(self):
        transport, _ = transport_for(error=RuntimeError("SECRET remote body"))
        with self.assertRaises(ProviderUnavailableError) as caught:
            transport.generate(text_request(), timeout_s=30)
        self.assertNotIn("SECRET", str(caught.exception))

    def test_gemini_pricing_includes_thought_tokens(self):
        cost = estimate_gemini_cost(
            GoogleUsage(prompt_tokens=1000, output_tokens=500, thought_tokens=100)
        )
        self.assertAlmostEqual(
            cost,
            1000 * 0.75 / 1_000_000 + 600 * 3.75 / 1_000_000,
        )

    def test_image_pricing_has_exact_1k_floor(self):
        cost = estimate_image_cost(
            GoogleUsage(prompt_tokens=1000),
            image_count=1,
            image_size="1K",
        )
        self.assertGreaterEqual(cost, 0.067)
        with self.assertRaises(ProviderProtocolError):
            estimate_image_cost(GoogleUsage(), image_count=1, image_size="2K")


if __name__ == "__main__":
    unittest.main()
