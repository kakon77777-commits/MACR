from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from macr_runtime.config import AuthMode, ConnectionScope, ProviderConfig
from macr_runtime.contracts import (
    DelegationClass,
    PrivacyLevel,
    ReturnContract,
    ReturnFormat,
    ResultStatus,
    TaskConstraints,
    TaskContract,
    VerificationSpec,
    WorkspaceSpec,
)
from macr_runtime.errors import (
    ConfigurationError,
    LegacyPreTierIncompatibleError,
    ProviderOutputBudgetTooSmallError,
    ProviderPolicyError,
    ProviderUnavailableError,
)
from macr_runtime.providers.glm import (
    GlmFixedKeySource,
    GlmFlashWorkerProvider as _GlmFlashWorkerProvider,
)
from macr_runtime.glm_approval import GlmApprovalStore
from macr_runtime.provider_capability import (
    glm_extended_text_policy,
    glm_standard_policy,
)
from macr_runtime.token_policy import ModelTokenPolicyResolver, t1_glm_live_policy
from tests.support import d_drive_tempdir


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


class DenyingApprovalStore:
    def inspect(self, approval_sha256):
        del approval_sha256
        raise ProviderPolicyError("GLM host approval record is missing")


class AllowingApprovalStore:
    def inspect(self, approval_sha256):
        return {"approval_sha256": approval_sha256, "approved_by": "host_operator"}

    def verify(self, approval_sha256, *, signing_key):
        del signing_key
        return {"approval_sha256": approval_sha256, "approved_by": "host_operator"}


class RejectingMacApprovalStore(AllowingApprovalStore):
    def verify(self, approval_sha256, *, signing_key):
        del approval_sha256, signing_key
        raise ProviderPolicyError("GLM host approval record MAC is invalid")


class StaticKeySource:
    def __init__(self, value="test-id.test-secret") -> None:
        self.value = value

    def load(self):
        return self.value

    def check_metadata(self):
        return None


def GlmFlashWorkerProvider(*args, **kwargs):
    kwargs.setdefault("approval_store", AllowingApprovalStore())
    kwargs.setdefault("key_source", StaticKeySource())
    return _GlmFlashWorkerProvider(*args, **kwargs)


class ExplodingKeySource:
    def __init__(self) -> None:
        self.calls = 0

    def load(self):
        self.calls += 1
        raise AssertionError("key source must remain untouched")


class CountingKeySource:
    def __init__(self) -> None:
        self.calls = 0

    def load(self):
        self.calls += 1
        return "test-id." + "test-secret"


class MetadataOnlyKeySource:
    def __init__(self) -> None:
        self.metadata_calls = 0
        self.load_calls = 0

    def check_metadata(self):
        self.metadata_calls += 1

    def load(self):
        self.load_calls += 1
        raise AssertionError("health must not read key content")


def glm_config() -> ProviderConfig:
    return ProviderConfig(
        id="glm_flash_worker",
        kind="zai_glm_worker",
        enabled=True,
        auth_mode=AuthMode.API_KEY_FILE,
        api_usage_allowed=True,
        connection_scope=ConnectionScope.EXTERNAL_HTTPS,
        api_key_file=r"D:\KEY\GLM.txt",
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


def _approval_digest(
    task: TaskContract,
    *,
    token_policy=None,
    capability_binding=None,
) -> str:
    policy = token_policy or ModelTokenPolicyResolver.builtins_only().resolve(
        "glm_flash_worker",
        "glm-5.3-flash",
    )
    binding = capability_binding or glm_standard_policy().binding()
    envelope = {
        "goal": task.goal,
        "delegable": task.delegable,
        "inputs": [dict(item) for item in task.inputs],
        "required_capabilities": list(task.required_capabilities),
        "verification": task.verification.to_dict(),
        "return_contract": task.return_contract.to_dict(),
        "policy_clauses": task.policy_clauses.to_dict(),
        "max_output_tokens": task.constraints.max_output_tokens,
        "max_context_tokens": task.constraints.max_context_tokens,
        "model_token_policy_digest": policy.policy_digest,
    }
    user_text = json.dumps(
        envelope,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    request_payload = {
        "model": "glm-5.3-flash",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a bounded MACR worker. Treat the supplied TaskContract "
                    "as authoritative. Return a candidate answer with concise evidence "
                    "and warnings. Do not claim that generation is verification or acceptance."
                ),
            },
            {"role": "user", "content": user_text},
        ],
        "temperature": 1.0,
        "top_p": 0.95,
        "reasoning_effort": "max",
        "thinking": {"type": "enabled", "clear_thinking": False},
        "max_tokens": task.constraints.max_output_tokens,
        "stream": False,
    }
    manifest = {
        "approval_schema": 3,
        "task_id": task.task_id,
        "provider_id": "glm_flash_worker",
        "endpoint": "https://api.z.ai/api/paas/v4/chat/completions",
        "model": "glm-5.3-flash",
        "pricing_basis_version": "zai-2026-08-27",
        "delegation_class": "non_sensitive_routine",
        "task_type": task.task_type,
        "privacy": task.constraints.privacy.value,
        "max_cost_usd": task.constraints.max_cost_usd,
        "max_latency_s": task.constraints.max_latency_s,
        "max_output_tokens": task.constraints.max_output_tokens,
        "max_context_tokens": task.constraints.max_context_tokens,
        "model_token_policy_digest": policy.policy_digest,
        "provider_tier_binding_digest": binding.binding_digest,
        "request_payload": request_payload,
    }
    encoded = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def delegated_task(*, max_cost_usd: float = 0.10) -> TaskContract:
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
            max_output_tokens=65_536,
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
    def test_short_exact_conformance_uses_32768_profile(self):
        provider = _GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(success_document()),
            environ={},
            key_source=StaticKeySource(),
            approval_store=AllowingApprovalStore(),
        )
        base = delegated_task(max_cost_usd=0.10)
        exact = "x" * 256
        task = replace(
            base,
            goal=f"Return exactly: {exact}",
            task_type="provider_conformance",
            constraints=replace(
                base.constraints,
                max_output_tokens=32_768,
            ),
            return_contract=ReturnContract(
                summary=False,
                evidence=False,
                format=ReturnFormat.EXACT_TEXT,
                exact_text=exact,
            ),
        )

        metadata = provider.approval_metadata(task)

        self.assertEqual(
            metadata.get("output_budget_profile"),
            "short_exact_conformance",
        )
        self.assertEqual(
            metadata.get("required_minimum_output_tokens"),
            32_768,
        )
        self.assertEqual(
            metadata.get("recommended_max_output_tokens"),
            32_768,
        )

    def test_quality_first_work_rejects_32768_and_recommends_65536(self):
        key_source = CountingKeySource()
        transport = FakeTransport(success_document())
        provider = _GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={},
            key_source=key_source,
            approval_store=AllowingApprovalStore(),
        )
        base = delegated_task(max_cost_usd=0.10)
        task = replace(
            base,
            constraints=replace(
                base.constraints,
                max_output_tokens=32_768,
            ),
        )

        with self.assertRaises(ProviderOutputBudgetTooSmallError) as raised:
            provider.approval_metadata(task)

        diagnostic = raised.exception.safe_diagnostic()
        self.assertEqual(
            diagnostic.get("output_budget_profile"),
            "quality_first_work",
        )
        self.assertEqual(
            diagnostic.get("recommended_max_output_tokens"),
            65_536,
        )
        self.assertEqual(key_source.calls, 0)
        self.assertEqual(transport.posts, [])
        serialized = str(diagnostic)
        self.assertNotIn(base.goal, serialized)
        self.assertNotIn("alpha", serialized)

    def test_257_byte_exact_conformance_uses_quality_first_profile(self):
        provider = _GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(success_document()),
            environ={},
            key_source=StaticKeySource(),
            approval_store=AllowingApprovalStore(),
        )
        base = delegated_task(max_cost_usd=0.10)
        task = replace(
            base,
            task_type="provider_conformance",
            constraints=replace(
                base.constraints,
                max_output_tokens=65_536,
            ),
            return_contract=ReturnContract(
                summary=False,
                evidence=False,
                format=ReturnFormat.EXACT_TEXT,
                exact_text="x" * 257,
            ),
        )

        metadata = provider.approval_metadata(task)

        self.assertEqual(
            metadata["output_budget_profile"],
            "quality_first_work",
        )
        self.assertEqual(metadata["required_minimum_output_tokens"], 65_536)

    def test_delegated_short_exact_return_still_requires_quality_first_output(self):
        provider = _GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(success_document()),
            environ={},
            key_source=StaticKeySource(),
            approval_store=AllowingApprovalStore(),
        )
        base = delegated_task(max_cost_usd=0.10)
        task = replace(
            base,
            constraints=replace(
                base.constraints,
                max_output_tokens=32_768,
            ),
            return_contract=ReturnContract(
                summary=False,
                evidence=False,
                format=ReturnFormat.EXACT_TEXT,
                exact_text="OK",
            ),
        )

        with self.assertRaises(ProviderOutputBudgetTooSmallError) as raised:
            provider.approval_metadata(task)

        self.assertEqual(
            raised.exception.safe_diagnostic()["output_budget_profile"],
            "quality_first_work",
        )

    def test_quality_first_work_binds_exact_65536_request(self):
        provider = _GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(success_document()),
            environ={},
            key_source=StaticKeySource(),
            approval_store=AllowingApprovalStore(),
        )
        base = delegated_task(max_cost_usd=0.10)
        task = replace(
            base,
            constraints=replace(
                base.constraints,
                max_output_tokens=65_536,
            ),
        )

        metadata = provider.approval_metadata(task)

        self.assertEqual(
            metadata.get("output_budget_profile"),
            "quality_first_work",
        )
        self.assertEqual(
            metadata.get("required_minimum_output_tokens"),
            65_536,
        )
        self.assertEqual(
            metadata.get("recommended_max_output_tokens"),
            65_536,
        )

    def test_constructor_rejects_rogue_unpublished_capability_policy(self):
        rogue = replace(
            glm_extended_text_policy(),
            tier_id="rogue_unbounded",
            max_latency_s=3_600,
            patch_allowed=True,
            write_scope_allowed=True,
            verification_required=False,
        )

        with self.assertRaisesRegex(ConfigurationError, "supported"):
            _GlmFlashWorkerProvider(
                glm_config(),
                transport=FakeTransport(success_document()),
                environ={},
                key_source=StaticKeySource(),
                approval_store=AllowingApprovalStore(),
                capability_policy=rogue,
            )

    def test_legacy_pre_tier_approval_is_distinctly_incompatible(self):
        with d_drive_tempdir() as state_root:
            provider = _GlmFlashWorkerProvider(
                glm_config(),
                transport=FakeTransport(success_document()),
                environ={"MACR_STATE_ROOT": str(state_root)},
                key_source=StaticKeySource(),
            )
            base = replace(delegated_task(), delegation_approval_sha256=None)
            metadata = provider.approval_metadata(base)
            task = replace(
                base,
                delegation_approval_sha256=metadata["required_approval_sha256"],
            )
            GlmApprovalStore(state_root).create(
                metadata["required_approval_sha256"],
                signing_key="test-id.test-secret",
                expires_in_days=1,
            )

            with self.assertRaisesRegex(
                LegacyPreTierIncompatibleError,
                "legacy_pre_tier_incompatible",
            ):
                provider.validate_approval(task)

    @staticmethod
    def _approve_with_provider(
        provider: _GlmFlashWorkerProvider,
        task: TaskContract,
    ) -> TaskContract:
        metadata = provider.approval_metadata(
            replace(task, delegation_approval_sha256=None)
        )
        return replace(
            task,
            delegation_approval_sha256=metadata["required_approval_sha256"],
        )

    def test_standard_300_and_extended_900_reach_transport_without_clamp(self):
        cases = (
            (glm_standard_policy().binding(), "delegated_routine", 300),
            (
                glm_extended_text_policy().binding(),
                "delegated_analysis",
                900,
            ),
        )
        for binding, task_type, timeout_s in cases:
            with self.subTest(binding=binding.tier_id):
                transport = FakeTransport(success_document())
                provider = _GlmFlashWorkerProvider(
                    glm_config(),
                    transport=transport,
                    environ={},
                    key_source=StaticKeySource(),
                    approval_store=AllowingApprovalStore(),
                    capability_binding=binding,
                )
                base = delegated_task()
                task = replace(
                    base,
                    task_type=task_type,
                    constraints=replace(base.constraints, max_latency_s=timeout_s),
                    delegation_approval_sha256=None,
                )
                task = self._approve_with_provider(provider, task)

                provider.invoke(task)

                self.assertEqual(transport.posts[0]["timeout_s"], timeout_s)

    def test_latency_above_exact_tier_ceiling_fails_before_key_or_transport(self):
        cases = (
            (glm_standard_policy().binding(), 301),
            (glm_extended_text_policy().binding(), 901),
        )
        for binding, timeout_s in cases:
            with self.subTest(binding=binding.tier_id):
                transport = FakeTransport(success_document())
                key_source = ExplodingKeySource()
                provider = _GlmFlashWorkerProvider(
                    glm_config(),
                    transport=transport,
                    environ={},
                    key_source=key_source,
                    approval_store=AllowingApprovalStore(),
                    capability_binding=binding,
                )
                base = delegated_task()
                task = replace(
                    base,
                    constraints=replace(base.constraints, max_latency_s=timeout_s),
                    delegation_approval_sha256=None,
                )

                with self.assertRaisesRegex(ProviderPolicyError, "latency.*tier"):
                    provider.approval_metadata(task)

                self.assertEqual(key_source.calls, 0)
                self.assertEqual(transport.posts, [])

    def test_approval_schema_binds_task_latency_and_outer_tier_identity(self):
        standard = _GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(success_document()),
            environ={},
            key_source=StaticKeySource(),
            approval_store=AllowingApprovalStore(),
            capability_binding=glm_standard_policy().binding(),
        )
        extended = _GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(success_document()),
            environ={},
            key_source=StaticKeySource(),
            approval_store=AllowingApprovalStore(),
            capability_binding=glm_extended_text_policy().binding(),
        )
        base = replace(delegated_task(), delegation_approval_sha256=None)
        digests = {
            standard.approval_metadata(base)["required_approval_sha256"],
            standard.approval_metadata(replace(base, task_id="different-task"))[
                "required_approval_sha256"
            ],
            standard.approval_metadata(
                replace(
                    base,
                    constraints=replace(base.constraints, max_latency_s=31),
                )
            )["required_approval_sha256"],
            extended.approval_metadata(base)["required_approval_sha256"],
        }

        self.assertEqual(len(digests), 4)
        metadata = standard.approval_metadata(base)
        self.assertEqual(metadata["approval_schema"], 3)
        self.assertEqual(metadata["task_id"], base.task_id)
        self.assertEqual(metadata["max_latency_s"], 30.0)
        self.assertEqual(
            metadata["provider_tier_binding_digest"],
            glm_standard_policy().binding().binding_digest,
        )

    def test_external_host_approval_is_required_before_key_resolution(self):
        key_source = ExplodingKeySource()
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(success_document()),
            environ={},
            key_source=key_source,
            approval_store=DenyingApprovalStore(),
        )

        with self.assertRaisesRegex(ProviderPolicyError, "host approval record"):
            provider.invoke(delegated_task())

        self.assertEqual(key_source.calls, 0)

    def test_invalid_approval_mac_fails_after_local_key_read_but_before_transport(self):
        key_source = CountingKeySource()
        transport = FakeTransport(success_document())
        provider = _GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={},
            key_source=key_source,
            approval_store=RejectingMacApprovalStore(),
        )

        with self.assertRaisesRegex(ProviderPolicyError, "MAC"):
            provider.invoke(delegated_task())

        self.assertEqual(key_source.calls, 1)
        self.assertEqual(transport.posts, [])

    def test_fixed_key_source_accepts_only_files_beneath_canonical_root(self):
        with d_drive_tempdir() as root:
            key_root = root / "key-root"
            key_root.mkdir()
            inside = key_root / "GLM.txt"
            inside.write_text("test-id." + "test-secret", encoding="utf-8")
            outside = root / "outside.txt"
            outside.write_text("test-id." + "outside-secret", encoding="utf-8")

            loaded = GlmFixedKeySource(key_root, inside).load()
            with self.assertRaisesRegex(ProviderUnavailableError, "canonical key root"):
                GlmFixedKeySource(key_root, outside).load()

        self.assertEqual(loaded, "test-id." + "test-secret")

    def test_fixed_key_source_rejects_reparse_leaf_when_supported(self):
        with d_drive_tempdir() as root:
            key_root = root / "key-root"
            key_root.mkdir()
            target = key_root / "target.txt"
            target.write_text("test-id." + "test-secret", encoding="utf-8")
            link = key_root / "GLM.txt"
            try:
                link.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"symbolic links unavailable: {type(exc).__name__}")

            with self.assertRaisesRegex(ProviderUnavailableError, "reparse"):
                GlmFixedKeySource(key_root, link).load()

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
        self.assertEqual(payload["max_tokens"], 65_536)
        self.assertFalse(payload["stream"])
        self.assertNotIn("tools", payload)
        self.assertNotIn("tool_choice", payload)

        envelope = json.loads(payload["messages"][1]["content"])
        self.assertEqual(envelope["goal"], "Classify the supplied public labels.")
        self.assertTrue(envelope["delegable"])
        self.assertEqual(envelope["inputs"][0]["content"], "alpha\nbeta")
        self.assertEqual(
            envelope["policy_clauses"],
            delegated_task().policy_clauses.to_dict(),
        )
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
            replace(
                glm_config(),
                auth_mode=AuthMode.API_KEY,
                api_key_file=None,
                api_key_env="OTHER_KEY",
            ),
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

        execution = provider.invoke_observed(delegated_task())

        self.assertEqual(len(transport.posts), 1)
        self.assertEqual(execution.result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertTrue(any("tool calls" in item for item in execution.result.warnings))

    def test_non_stop_finish_reason_is_rejected_without_retry(self):
        document = success_document()
        document["choices"][0]["finish_reason"] = "length"
        document["choices"][0]["message"]["content"] = "PARTIAL PRIVATE ANSWER"
        transport = FakeTransport(document)
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )

        execution = provider.invoke_observed(delegated_task())

        self.assertEqual(len(transport.posts), 1)
        self.assertEqual(execution.result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertEqual(execution.result.answer, "")
        self.assertEqual(execution.observation.finish_reason, "length")
        self.assertEqual(execution.observation.model, "glm-5.3-flash")
        self.assertEqual(execution.observation.usage.input_tokens, 20)
        self.assertEqual(
            execution.observation.answer_bytes,
            b"PARTIAL PRIVATE ANSWER",
        )

    def test_reasoning_exhaustion_is_reported_as_a_distinct_failure(self):
        document = success_document()
        document["choices"][0]["finish_reason"] = "length"
        document["choices"][0]["message"]["content"] = ""
        document["usage"]["completion_tokens"] = 65_536
        document["usage"]["completion_tokens_details"]["reasoning_tokens"] = 65_536
        document["usage"]["total_tokens"] = 65_556
        transport = FakeTransport(document)
        provider = _GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={},
            key_source=StaticKeySource(),
            approval_store=AllowingApprovalStore(),
        )
        base = delegated_task(max_cost_usd=0.10)
        task = replace(base, delegation_approval_sha256=None)
        task = self._approve_with_provider(provider, task)

        execution = provider.invoke_observed(task)

        self.assertEqual(execution.result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertEqual(execution.result.answer, "")
        self.assertEqual(execution.observation.answer_bytes, b"")
        self.assertEqual(execution.observation.usage.output_tokens, 65_536)
        self.assertEqual(execution.observation.usage.reasoning_tokens, 65_536)
        self.assertEqual(
            execution.result.provider_meta["failure_type"],
            "ProviderReasoningBudgetExhaustedError",
        )
        self.assertEqual(
            execution.result.failure_code,
            "ProviderReasoningBudgetExhaustedError",
        )
        self.assertEqual(
            execution.result.failure_stage,
            "provider_response_validation",
        )
        self.assertEqual(
            execution.result.provider_meta["failure_stage"],
            "provider_response_validation",
        )
        self.assertTrue(
            any(
                "reasoning exhausted" in warning.lower()
                for warning in execution.result.warnings
            )
        )

    def test_max_reasoning_rejects_output_below_cloud_quality_floor(self):
        provider = _GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(success_document()),
            environ={},
            key_source=StaticKeySource(),
            approval_store=AllowingApprovalStore(),
        )
        base = delegated_task(max_cost_usd=0.10)
        low_output = replace(
            base,
            constraints=replace(base.constraints, max_output_tokens=32_768),
            delegation_approval_sha256=None,
        )
        recommended_output = replace(
            base,
            constraints=replace(base.constraints, max_output_tokens=65_536),
            delegation_approval_sha256=None,
        )

        recommended_metadata = provider.approval_metadata(recommended_output)

        with self.assertRaises(ProviderOutputBudgetTooSmallError) as caught:
            provider.approval_metadata(low_output)

        self.assertEqual(
            caught.exception.safe_diagnostic()["minimum_max_output_tokens"],
            65_536,
        )
        self.assertEqual(recommended_metadata["requested_max_output_tokens"], 65_536)
        self.assertEqual(recommended_metadata["minimum_task_output_tokens"], 32_768)
        self.assertEqual(
            recommended_metadata["required_minimum_output_tokens"],
            65_536,
        )
        self.assertEqual(recommended_metadata["reasoning_effort"], "max")

    def test_t1_policy_accepts_quality_first_output(self):
        provider = _GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(success_document()),
            environ={},
            key_source=StaticKeySource(),
            approval_store=AllowingApprovalStore(),
            token_policy=t1_glm_live_policy(),
        )
        base = delegated_task(max_cost_usd=0.10)
        task = replace(
            base,
            constraints=replace(base.constraints, max_output_tokens=65_536),
            delegation_approval_sha256=None,
        )

        metadata = provider.approval_metadata(task)

        self.assertEqual(metadata["minimum_task_output_tokens"], 32_768)
        self.assertEqual(metadata["required_minimum_output_tokens"], 65_536)
        self.assertEqual(metadata["max_output_tokens"], 65_536)

    def test_forged_glm_provider_ceiling_cannot_create_a_floor_exception(self):
        canonical = ModelTokenPolicyResolver.builtins_only().resolve(
            "glm_flash_worker",
            "glm-5.3-flash",
        )
        forged = replace(
            canonical,
            minimum_task_output_tokens=2_048,
            default_output_tokens=2_048,
            max_output_tokens=2_048,
            provider_output_ceiling_tokens=2_048,
        )

        with self.assertRaisesRegex(ConfigurationError, "provider ceiling"):
            _GlmFlashWorkerProvider(
                glm_config(),
                transport=FakeTransport(success_document()),
                environ={},
                key_source=StaticKeySource(),
                approval_store=AllowingApprovalStore(),
                token_policy=forged,
            )

    def test_impossible_reasoning_usage_is_not_mislabeled_as_exhaustion(self):
        document = success_document()
        document["choices"][0]["finish_reason"] = "length"
        document["choices"][0]["message"]["content"] = ""
        document["usage"]["completion_tokens"] = 65_536
        document["usage"]["completion_tokens_details"]["reasoning_tokens"] = 65_537
        document["usage"]["total_tokens"] = 65_556
        provider = _GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(document),
            environ={},
            key_source=StaticKeySource(),
            approval_store=AllowingApprovalStore(),
        )
        base = delegated_task(max_cost_usd=0.10)
        task = replace(base, delegation_approval_sha256=None)
        task = self._approve_with_provider(provider, task)

        execution = provider.invoke_observed(task)

        self.assertEqual(
            execution.result.provider_meta["failure_type"],
            "ProviderProtocolError",
        )

    def test_malformed_usage_preserves_other_observed_fields(self):
        document = success_document()
        document["usage"]["prompt_tokens"] = "twenty"
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(document),
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )

        execution = provider.invoke_observed(delegated_task())

        self.assertEqual(execution.result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertEqual(execution.result.answer, "")
        self.assertIsNone(execution.observation.usage.input_tokens)
        self.assertEqual(execution.observation.usage.output_tokens, 10)
        self.assertIsNone(execution.observation.currency_cost_usd)
        self.assertEqual(execution.observation.finish_reason, "stop")
        self.assertEqual(
            execution.observation.answer_bytes,
            b"candidate classification",
        )
        self.assertEqual(
            execution.result.provider_meta["failure_type"],
            "ProviderProtocolError",
        )

    def test_returned_model_mismatch_is_observed_before_rejection(self):
        document = success_document()
        document["model"] = "unexpected-model"
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(document),
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )

        execution = provider.invoke_observed(delegated_task())

        self.assertEqual(execution.result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertEqual(execution.observation.model, "unexpected-model")
        self.assertEqual(
            execution.observation.answer_bytes,
            b"candidate classification",
        )
        self.assertNotIn("unexpected-model", " ".join(execution.result.warnings))

    def test_inconsistent_usage_total_is_rejected(self):
        document = success_document()
        document["usage"]["total_tokens"] = 29
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(document),
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )

        execution = provider.invoke_observed(delegated_task())

        self.assertEqual(execution.result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertTrue(any("total_tokens" in item for item in execution.result.warnings))

    def test_reported_completion_tokens_cannot_exceed_requested_bound(self):
        document = success_document()
        document["usage"]["completion_tokens"] = 65_537
        document["usage"]["total_tokens"] = 65_557
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(document),
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )

        execution = provider.invoke_observed(delegated_task())

        self.assertEqual(execution.result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertTrue(any("output bound" in item for item in execution.result.warnings))

    def test_blank_candidate_content_is_rejected(self):
        document = success_document()
        document["choices"][0]["message"]["content"] = "   "
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(document),
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )

        execution = provider.invoke_observed(delegated_task())

        self.assertEqual(execution.result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertTrue(any("no text content" in item for item in execution.result.warnings))

    def test_malformed_key_is_rejected_before_transport(self):
        transport = FakeTransport(success_document())
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={},
            key_source=StaticKeySource("not-a-zai-key"),
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

    def test_health_checks_only_key_metadata_without_reading_content(self):
        key_source = MetadataOnlyKeySource()
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(success_document()),
            environ={},
            key_source=key_source,
        )

        health = provider.health()

        self.assertTrue(health.ready)
        self.assertEqual(health.status, "configured_offline")
        self.assertEqual(key_source.metadata_calls, 1)
        self.assertEqual(key_source.load_calls, 0)

    def test_non_routine_task_type_is_rejected_before_transport(self):
        transport = FakeTransport(success_document())
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )

        with self.assertRaisesRegex(ProviderPolicyError, "active tier"):
            provider.invoke(replace(delegated_task(), task_type="frontier_research"))

        self.assertEqual(transport.posts, [])

    def test_obvious_local_path_marker_is_rejected_before_credential_or_transport(self):
        transport = FakeTransport(success_document())
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={},
        )

        for goal in (
            r"Summarize D:\private-research\theory.txt",
            r"Summarize d:\private-research\theory.txt",
            r"Summarize D:/private-research/theory.txt",
            r"Read \\server\share\secret.txt",
            r"Read \\\\server\\share\\secret.txt",
            r"Read file:///D:/private-research/theory.txt",
            r"Read file://server/share/secret.txt",
            r"Read file:///etc/private.txt",
            r"Read file:/etc/private.txt",
            r"Read file:C:\private.txt",
            r"Read file:relative/private.txt",
            r"Read D:\text\secret.txt",
            r"Read D:\delta_u\secret.txt",
            r"Read prefix-D:\private\secret.txt",
            r"Read D:\text~1\secret.txt",
            r"Read D:\text{domain}\secret.txt",
            r"Read D:\text(archive)\secret.txt",
            r"Read D:\text[archive]\secret.txt",
            r"Read D:\text$cache\secret.txt",
            r"Read D:\text@cache\secret.txt",
            r"Read D:\text資料\secret.txt",
            r"Read D:\text\{secret}\file.txt",
            r"Read D:\text\(secret)\file.txt",
            r"Read \\伺服器\分享\secret.txt",
            r"Read //server/share/secret.txt",
        ):
            with self.subTest(goal=goal):
                task = replace(delegated_task(), goal=goal)
                with self.assertRaisesRegex(ProviderPolicyError, "sensitive marker"):
                    provider.invoke(task)

        self.assertEqual(transport.posts, [])

    def test_obvious_credential_marker_is_rejected_before_transport(self):
        transport = FakeTransport(success_document())
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={},
        )

        for goal in (
            "api_key = hidden",
            "api key: hidden",
            "access-token: hidden",
            "access token = hidden",
            "private_key=hidden",
            "private key: hidden",
            "-----BEGIN " + "PRIVATE" + " KEY-----",
            "-----BEGIN RSA " + "PRIVATE" + " KEY-----",
            "-----BEGIN OPENSSH " + "PRIVATE" + " KEY-----",
            "-----BEGIN EC " + "PRIVATE" + " KEY-----",
        ):
            with self.subTest(goal=goal):
                with self.assertRaisesRegex(ProviderPolicyError, "sensitive marker"):
                    provider.approval_metadata(
                        replace(delegated_task(), goal=goal)
                    )

        self.assertEqual(transport.posts, [])

    def test_latex_and_https_are_not_mistaken_for_local_paths(self):
        transport = FakeTransport(success_document())
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            environ={},
        )

        for goal in (
            "Summarize https://example.com/public-paper.",
            "Summarize HTTPS://EXAMPLE.COM/public-paper.",
            "Summarize x://example.invalid/public.",
            "Summarize https://example.com/D:/public/paper.txt.",
            r"Analyze \min\{u>s:\delta_u<\delta_s\}.",
            r"Analyze \forall B:\neg R(A,B).",
            r"Analyze \{x\in D:\neg C_k(x)\}.",
            r"Analyze D:\quad y^2=x^3+x^2+8x-16.",
            r"Analyze \mathsf D:\text{domain}.",
            r"Analyze $\forall B:\neg R(A,B)$ and $\{x\in D:\neg C_k(x)\}$.",
            r"Analyze \\min\\{u>s:\\delta_u<\\delta_s\\}.",
            r"Analyze \\forall B:\\neg R(A,B).",
        ):
            with self.subTest(goal=goal):
                metadata = provider.approval_metadata(
                    replace(delegated_task(), goal=goal)
                )
                self.assertEqual(metadata["provider_id"], "glm_flash_worker")

        for command in (
            "delta",
            "exists",
            "forall",
            "neg",
            "qquad",
            "quad",
            "text",
            "texttt",
        ):
            for slash in ("\\", "\\\\"):
                with self.subTest(command=command, slash=slash):
                    metadata = provider.approval_metadata(
                        replace(
                            delegated_task(),
                            goal=f"Analyze X:{slash}{command}.",
                        )
                    )
                    self.assertEqual(metadata["provider_id"], "glm_flash_worker")

        task = replace(
            delegated_task(),
            inputs=(
                {
                    "type": "text",
                    "name": "public-mathematics",
                    "content": r"E_k=\\{x\\in D:\\neg C_k(x)\\}.",
                },
            ),
        )
        metadata = provider.approval_metadata(task)
        self.assertEqual(metadata["provider_id"], "glm_flash_worker")

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

        execution = provider.invoke_observed(delegated_task())

        self.assertEqual(len(transport.posts), 1)
        self.assertEqual(execution.result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertTrue(any("web search" in item for item in execution.result.warnings))

    def test_postflight_over_budget_is_retained_as_failed_candidate(self):
        document = success_document()
        document["usage"]["prompt_tokens"] = 1_000_000
        document["usage"]["total_tokens"] = 1_000_010
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(document),
            environ={"ZAI_API_KEY": "test-id.test-secret"},
        )

        result = provider.invoke(delegated_task(max_cost_usd=0.10))

        self.assertEqual(result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertGreater(result.cost["currency_cost_usd"], 0.10)
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
        self.assertEqual(
            metadata["model_token_policy_digest"],
            ModelTokenPolicyResolver.builtins_only()
            .resolve("glm_flash_worker", "glm-5.3-flash")
            .policy_digest,
        )
        self.assertEqual(metadata["hard_context_tokens"], 512_000)
        self.assertGreater(metadata["request_bytes"], 0)
        self.assertGreater(metadata["conservative_cost_ceiling_usd"], 0)

    def test_policy_change_invalidates_existing_approval_before_key_access(self):
        ordinary = ModelTokenPolicyResolver.builtins_only().resolve(
            "glm_flash_worker",
            "glm-5.3-flash",
        )
        task = delegated_task()
        provider = _GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(success_document()),
            environ={},
            key_source=ExplodingKeySource(),
            approval_store=AllowingApprovalStore(),
            token_policy=t1_glm_live_policy(),
        )
        self.assertEqual(
            task.delegation_approval_sha256,
            _approval_digest(task, token_policy=ordinary),
        )
        with self.assertRaisesRegex(ProviderPolicyError, "approval digest"):
            provider.invoke(task)

    def test_task_contract_refuses_output_above_t1_max(self):
        with self.assertRaisesRegex(ValueError, "between 1 and 65536"):
            replace(
                delegated_task().constraints,
                max_output_tokens=65_537,
            )

    def test_ordinary_glm_policy_accepts_expanded_external_envelope_offline(self):
        base_task = delegated_task(max_cost_usd=0.10)
        task = replace(
            base_task,
            constraints=replace(
                base_task.constraints,
                max_output_tokens=65_536,
                max_context_tokens=512_000,
            ),
            delegation_approval_sha256=None,
        )
        metadata = GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(success_document()),
            environ={},
        ).approval_metadata(task)

        self.assertEqual(metadata["max_output_tokens"], 65_536)
        self.assertEqual(metadata["hard_context_tokens"], 512_000)
        self.assertEqual(len(metadata["required_approval_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
