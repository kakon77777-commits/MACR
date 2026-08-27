from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace
from typing import Any, Mapping

from macr_runtime.config import AuthMode, ConnectionScope, ProviderConfig
from macr_runtime.contracts import (
    DelegationClass,
    PrivacyLevel,
    ReturnContract,
    ResultStatus,
    TaskConstraints,
    TaskContract,
    VerificationSpec,
    WorkspaceSpec,
)
from macr_runtime.errors import (
    ConfigurationError,
    ProviderPolicyError,
    ProviderProtocolError,
    ProviderUnavailableError,
)
from macr_runtime.providers.glm import GlmFlashWorkerProvider


class FakeTransport:
    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = response
        self.posts: list[dict[str, Any]] = []

    def get_json(self, url, *, headers, timeout_s):
        raise AssertionError("GLM worker must not issue GET requests")

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


def glm_config() -> ProviderConfig:
    return ProviderConfig(
        id="glm_flash_worker",
        kind="zai_glm_worker",
        enabled=True,
        auth_mode=AuthMode.API_KEY,
        api_usage_allowed=True,
        connection_scope=ConnectionScope.EXTERNAL_HTTPS,
        api_key_env="ZAI_API_KEY",
        base_url="https://api.z.ai/api/paas/v4",
        model="glm-5.3-flash",
        reasoning_effort="max",
        endpoint_path="/chat/completions",
        allowed_hosts=("api.z.ai",),
        capabilities=("text_generation",),
        approved_privacy=(
            PrivacyLevel.PUBLIC.value,
            PrivacyLevel.INTERNAL_APPROVED.value,
        ),
    )


def _approval_digest(task: TaskContract) -> str:
    envelope = {
        "goal": task.goal,
        "delegable": task.delegable,
        "inputs": [dict(item) for item in task.inputs],
        "required_capabilities": list(task.required_capabilities),
        "verification": task.verification.to_dict(),
        "return_contract": task.return_contract.to_dict(),
        "max_output_tokens": task.constraints.max_output_tokens,
    }
    manifest = {
        "approval_schema": 1,
        "provider_id": "glm_flash_worker",
        "endpoint": "https://api.z.ai/api/paas/v4/chat/completions",
        "model": "glm-5.3-flash",
        "pricing_basis_version": "zai-2026-08-27",
        "delegation_class": "non_sensitive_routine",
        "task_type": task.task_type,
        "privacy": task.constraints.privacy.value,
        "max_cost_usd": task.constraints.max_cost_usd,
        "max_output_tokens": task.constraints.max_output_tokens,
        "envelope": envelope,
    }
    encoded = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def delegated_task(*, max_cost_usd: float = 0.01) -> TaskContract:
    task = TaskContract(
        task_id="glm-worker-test",
        goal="Classify the supplied public labels.",
        task_type="delegated_routine",
        delegable=True,
        delegation_class=DelegationClass.NON_SENSITIVE_ROUTINE,
        inputs=(
            {
                "type": "text",
                "name": "approved-labels",
                "content": "alpha\nbeta",
            },
        ),
        constraints=TaskConstraints(
            max_cost_usd=max_cost_usd,
            max_latency_s=30,
            max_output_tokens=256,
            internet=True,
            privacy=PrivacyLevel.PUBLIC,
        ),
        required_capabilities=("text_generation",),
    )
    return replace(task, delegation_approval_sha256=_approval_digest(task))


def success_document() -> dict[str, Any]:
    return {
        "id": "glm-response-1",
        "model": "glm-5.3-flash",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "candidate classification",
                    "reasoning_content": "private reasoning omitted",
                },
            }
        ],
        "usage": {
            "prompt_tokens": 20,
            "completion_tokens": 10,
            "total_tokens": 30,
            "prompt_tokens_details": {"cached_tokens": 0},
            "completion_tokens_details": {"reasoning_tokens": 6},
        },
    }


class GlmFlashWorkerProviderTests(unittest.TestCase):
    def test_delegated_text_builds_sanitized_fixed_request_and_estimated_cost(self):
        transport = FakeTransport(success_document())
        result = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        ).invoke(delegated_task())

        self.assertEqual(len(transport.posts), 1)
        call = transport.posts[0]
        self.assertEqual(
            call["url"],
            "https://api.z.ai/api/paas/v4/chat/completions",
        )
        self.assertEqual(
            call["headers"]["Authorization"],
            "Bearer test-id.test-secret",
        )
        payload = call["payload"]
        self.assertEqual(payload["model"], "glm-5.3-flash")
        self.assertEqual(payload["temperature"], 1.0)
        self.assertEqual(payload["top_p"], 0.95)
        self.assertEqual(payload["reasoning_effort"], "max")
        self.assertEqual(
            payload["thinking"],
            {"type": "enabled", "clear_thinking": False},
        )
        self.assertEqual(payload["max_tokens"], 256)
        self.assertFalse(payload["stream"])
        self.assertNotIn("tools", payload)
        self.assertNotIn("tool_choice", payload)

        envelope = json.loads(payload["messages"][1]["content"])
        self.assertEqual(envelope["goal"], "Classify the supplied public labels.")
        self.assertTrue(envelope["delegable"])
        self.assertEqual(envelope["inputs"][0]["content"], "alpha\nbeta")
        self.assertNotIn("workspace", envelope)
        self.assertNotIn("max_cost_usd", str(envelope))

        self.assertEqual(result.status, ResultStatus.CANDIDATE_SUCCESS)
        self.assertEqual(result.answer, "candidate classification")
        self.assertEqual(result.cost["currency_cost_usd"], 0.000008)
        self.assertEqual(result.cost["promotional_price_estimated_usd"], 0.000004)
        self.assertEqual(result.cost["promotional_price_observed_on"], "2026-08-27")
        self.assertNotIn("current_price_estimated_usd", result.cost)
        self.assertEqual(result.provider_meta["metrics"]["reasoning_tokens"], 6)
        self.assertNotIn("test-secret", str(result.to_dict()))

    def test_explicit_delegation_is_required_before_transport(self):
        transport = FakeTransport(success_document())
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )

        with self.assertRaisesRegex(ProviderPolicyError, "delegable=true"):
            provider.invoke(replace(delegated_task(), delegable=False))

        self.assertEqual(transport.posts, [])

    def test_write_scope_is_rejected_before_transport(self):
        transport = FakeTransport(success_document())
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )
        task = replace(
            delegated_task(),
            workspace=WorkspaceSpec(repo="current", write_scope=("src/**",)),
        )

        with self.assertRaisesRegex(ProviderPolicyError, "write_scope"):
            provider.invoke(task)

        self.assertEqual(transport.posts, [])

    def test_patch_return_authority_is_rejected_before_transport(self):
        transport = FakeTransport(success_document())
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )
        task = replace(
            delegated_task(),
            return_contract=ReturnContract(summary=True, patch=True, evidence=True),
        )

        with self.assertRaisesRegex(ProviderPolicyError, "patch authority"):
            provider.invoke(task)

        self.assertEqual(transport.posts, [])

    def test_independent_verification_is_required_before_transport(self):
        transport = FakeTransport(success_document())
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )
        task = replace(
            delegated_task(),
            verification=VerificationSpec(required=False, methods=()),
        )

        with self.assertRaisesRegex(ProviderPolicyError, "verification"):
            provider.invoke(task)

        self.assertEqual(transport.posts, [])

    def test_non_text_input_is_rejected_before_transport(self):
        transport = FakeTransport(success_document())
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )
        task = replace(
            delegated_task(),
            inputs=(
                {
                    "type": "file",
                    "path": "private.txt",
                    "sha256": "0" * 64,
                },
            ),
        )

        with self.assertRaisesRegex(ProviderPolicyError, "text inputs"):
            provider.invoke(task)

        self.assertEqual(transport.posts, [])

    def test_local_only_privacy_is_rejected_before_transport(self):
        transport = FakeTransport(success_document())
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )
        task = replace(
            delegated_task(),
            constraints=replace(
                delegated_task().constraints,
                privacy=PrivacyLevel.LOCAL_ONLY,
            ),
        )

        with self.assertRaisesRegex(ProviderPolicyError, "local_only"):
            provider.invoke(task)

        self.assertEqual(transport.posts, [])

    def test_budget_must_cover_conservative_request_ceiling_before_transport(self):
        transport = FakeTransport(success_document())
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )

        with self.assertRaisesRegex(ProviderPolicyError, "conservative ceiling"):
            provider.invoke(delegated_task(max_cost_usd=0.000001))

        self.assertEqual(transport.posts, [])

    def test_mutated_model_route_or_reasoning_is_rejected_at_construction(self):
        cases = (
            replace(glm_config(), id="renamed_worker"),
            replace(glm_config(), model="glm-other"),
            replace(glm_config(), base_url="https://api.z.ai/api/coding/paas/v4"),
            replace(glm_config(), endpoint_path="/other"),
            replace(glm_config(), reasoning_effort="high"),
            replace(glm_config(), api_key_env="OTHER_KEY"),
            replace(glm_config(), auth_mode=AuthMode.NONE),
            replace(
                glm_config(),
                approved_privacy=(
                    PrivacyLevel.PUBLIC.value,
                    PrivacyLevel.INTERNAL_APPROVED.value,
                    PrivacyLevel.LOCAL_ONLY.value,
                ),
            ),
            replace(
                glm_config(),
                capabilities=("text_generation", "filesystem_write"),
            ),
        )
        for config in cases:
            with self.subTest(config=config):
                with self.assertRaisesRegex(ConfigurationError, "fixed direct profile"):
                    GlmFlashWorkerProvider(
                        config,
                        transport=FakeTransport(success_document()),
                        environ={"ZAI_API_KEY": "test-id.test-secret"},
                    )

    def test_tool_calls_are_rejected_after_one_request(self):
        document = success_document()
        document["choices"][0]["message"]["tool_calls"] = [
            {"id": "tool-1", "type": "function"}
        ]
        transport = FakeTransport(document)
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )

        with self.assertRaisesRegex(ProviderProtocolError, "tool calls"):
            provider.invoke(delegated_task())

        self.assertEqual(len(transport.posts), 1)

    def test_non_stop_finish_reason_is_rejected_without_retry(self):
        document = success_document()
        document["choices"][0]["finish_reason"] = "length"
        transport = FakeTransport(document)
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )

        with self.assertRaisesRegex(ProviderProtocolError, "finish_reason"):
            provider.invoke(delegated_task())

        self.assertEqual(len(transport.posts), 1)

    def test_inconsistent_usage_total_is_rejected(self):
        document = success_document()
        document["usage"]["total_tokens"] = 29
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(document),
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )

        with self.assertRaisesRegex(ProviderProtocolError, "total_tokens"):
            provider.invoke(delegated_task())

    def test_reported_completion_tokens_cannot_exceed_requested_bound(self):
        document = success_document()
        document["usage"]["completion_tokens"] = 257
        document["usage"]["total_tokens"] = 277
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(document),
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )

        with self.assertRaisesRegex(ProviderProtocolError, "output bound"):
            provider.invoke(delegated_task())

    def test_blank_candidate_content_is_rejected(self):
        document = success_document()
        document["choices"][0]["message"]["content"] = "   "
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(document),
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )

        with self.assertRaisesRegex(ProviderProtocolError, "no text content"):
            provider.invoke(delegated_task())

    def test_malformed_key_is_rejected_before_transport(self):
        transport = FakeTransport(success_document())
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={"ZAI_API_KEY": "not-a-zai-key"},
        )

        with self.assertRaisesRegex(ProviderUnavailableError, "shape"):
            provider.invoke(delegated_task())

        self.assertEqual(transport.posts, [])

    def test_outbound_envelope_omits_local_task_identity(self):
        transport = FakeTransport(success_document())
        GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        ).invoke(delegated_task())

        envelope = json.loads(
            transport.posts[0]["payload"]["messages"][1]["content"]
        )
        self.assertNotIn("task_id", envelope)
        self.assertNotIn("task_type", envelope)

    def test_text_generation_capability_must_be_explicit_before_transport(self):
        transport = FakeTransport(success_document())
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )
        task = replace(delegated_task(), required_capabilities=())

        with self.assertRaisesRegex(ProviderPolicyError, "exactly text_generation"):
            provider.invoke(task)

        self.assertEqual(transport.posts, [])

    def test_health_reports_api_policy_denial_without_transport(self):
        transport = FakeTransport(success_document())
        provider = GlmFlashWorkerProvider(
            replace(glm_config(), api_usage_allowed=False),
            transport=transport,
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )

        health = provider.health()

        self.assertFalse(health.ready)
        self.assertEqual(health.status, "policy_denied")
        self.assertEqual(transport.posts, [])

    def test_non_routine_task_type_is_rejected_before_transport(self):
        transport = FakeTransport(success_document())
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )

        with self.assertRaisesRegex(ProviderPolicyError, "routine task type"):
            provider.invoke(replace(delegated_task(), task_type="frontier_research"))

        self.assertEqual(transport.posts, [])

    def test_obvious_local_path_marker_is_rejected_before_credential_or_transport(self):
        transport = FakeTransport(success_document())
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={},
        )
        task = replace(
            delegated_task(),
            goal=r"Summarize D:\private-research\theory.txt",
        )

        with self.assertRaisesRegex(ProviderPolicyError, "sensitive marker"):
            provider.invoke(task)

        self.assertEqual(transport.posts, [])

    def test_nonempty_web_search_metadata_is_rejected_without_retry(self):
        document = success_document()
        document["web_search"] = {"queries": ["unexpected"]}
        transport = FakeTransport(document)
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )

        with self.assertRaisesRegex(ProviderProtocolError, "web search"):
            provider.invoke(delegated_task())

        self.assertEqual(len(transport.posts), 1)

    def test_postflight_over_budget_is_retained_as_failed_candidate(self):
        document = success_document()
        document["usage"]["prompt_tokens"] = 100_000
        document["usage"]["total_tokens"] = 100_010
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(document),
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )

        result = provider.invoke(delegated_task(max_cost_usd=0.01))

        self.assertEqual(result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertGreater(result.cost["currency_cost_usd"], 0.01)
        self.assertTrue(any("exceeded" in warning for warning in result.warnings))

    def test_exact_approval_digest_is_required_before_credential_resolution(self):
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(success_document()),
            environ={},
        )
        task = replace(delegated_task(), delegation_approval_sha256=None)

        with self.assertRaisesRegex(ProviderPolicyError, "approval digest"):
            provider.invoke(task)

    def test_content_change_invalidates_existing_approval_before_credential_resolution(self):
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(success_document()),
            environ={},
        )
        task = replace(delegated_task(), goal="Changed after approval")

        with self.assertRaisesRegex(ProviderPolicyError, "approval digest"):
            provider.invoke(task)

    def test_approval_metadata_matches_independent_manifest_digest_without_key(self):
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(success_document()),
            environ={},
        )
        task = replace(delegated_task(), delegation_approval_sha256=None)

        metadata = provider.approval_metadata(task)

        self.assertEqual(metadata["required_approval_sha256"], _approval_digest(task))
        self.assertEqual(metadata["provider_id"], "glm_flash_worker")
        self.assertEqual(metadata["model"], "glm-5.3-flash")
        self.assertGreater(metadata["envelope_bytes"], 0)
        self.assertGreater(metadata["conservative_cost_ceiling_usd"], 0)


if __name__ == "__main__":
    unittest.main()
