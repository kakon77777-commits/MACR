from __future__ import annotations

import hashlib
import json
import uuid
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from macr_runtime.authority import AuthorityScope
from macr_runtime.config import ConnectionScope
from macr_runtime.contracts import (
    DelegationClass,
    PrivacyLevel,
    ProviderResult,
    ResultStatus,
    ReturnContract,
    ReturnFormat,
    TaskConstraints,
    TaskContract,
)
from macr_runtime.execution import (
    AuthorizationReference,
    DispatchContext,
    DispatchOrigin,
    InteractionPlane,
    ProviderExecution,
    ProviderState,
    ProviderUsage,
    RawProviderObservation,
)
from macr_runtime.errors import LegacyPreTierIncompatibleError, ProviderProtocolError
from macr_runtime.providers.base import BaseProvider, ProviderHealth
from macr_runtime.provider_capability import ProviderTierBinding, glm_standard_policy
from macr_runtime.provider_capability import glm_extended_text_policy
from macr_runtime.provider_capability_store import ProviderCapabilityPolicyStore
from macr_runtime.providers.glm import GlmFlashWorkerProvider
from macr_runtime.registry import ProviderRegistry
from macr_runtime.runtime import MacrRuntime, dispatch_resource_key

from tests.support import build_test_services, d_drive_tempdir
from tests.test_glm_provider import (
    AllowingApprovalStore,
    FakeTransport,
    StaticKeySource,
    glm_config,
    success_document,
)


class ObservedProvider(BaseProvider):
    connection_scope = ConnectionScope.EXTERNAL_HTTPS

    def __init__(
        self,
        provider_id: str,
        *,
        answer: str,
        status: ResultStatus = ResultStatus.CANDIDATE_SUCCESS,
        finish_reason: str = "stop",
        cost_usd: float | None = 0.000008,
        model: str | None = None,
        capability_binding=None,
    ) -> None:
        self.provider_id = provider_id
        self.answer = answer
        self.status = status
        self.finish_reason = finish_reason
        self.cost_usd = cost_usd
        self.model = model
        self.capability_binding = capability_binding
        self.calls = 0

    def health(self) -> ProviderHealth:
        return ProviderHealth(self.provider_id, True, "configured_offline")

    def invoke(self, task: TaskContract) -> ProviderResult:
        return self.invoke_observed(task).result

    def invoke_observed(self, task: TaskContract) -> ProviderExecution:
        self.calls += 1
        observation = RawProviderObservation(
            provider_id=self.provider_id,
            model="test-model",
            response_id="response-1",
            finish_reason=self.finish_reason,
            usage=ProviderUsage(20, 10, 8, 0),
            currency_cost_usd=self.cost_usd,
            cost_kind="estimated" if self.cost_usd is not None else None,
            pricing_basis_version="test-pricing-v1" if self.cost_usd is not None else None,
            duration_ms=100,
            answer_bytes=self.answer.encode("utf-8"),
            provider_state=(
                ProviderState.COMPLETED
                if self.finish_reason == "stop"
                else ProviderState.INCOMPLETE
            ),
        )
        result = ProviderResult(
            task_id=task.task_id,
            status=self.status,
            answer=self.answer if self.status is ResultStatus.CANDIDATE_SUCCESS else "",
            warnings=(
                ()
                if self.status is ResultStatus.CANDIDATE_SUCCESS
                else ("finish_reason_not_stop",)
            ),
        )
        return ProviderExecution.from_observation(observation, result)


class ExplodingProvider(BaseProvider):
    provider_id = "crash_provider"
    connection_scope = ConnectionScope.EXTERNAL_HTTPS

    def __init__(self) -> None:
        self.calls = 0

    def health(self) -> ProviderHealth:
        return ProviderHealth(self.provider_id, True, "configured_offline")

    def invoke(self, task: TaskContract) -> ProviderResult:
        del task
        raise AssertionError("invoke_observed must be used")

    def invoke_observed(self, task: TaskContract) -> ProviderExecution:
        del task
        self.calls += 1
        raise RuntimeError("PRIVATE simulated provider crash")


class HttpFailingProvider(ExplodingProvider):
    provider_id = "http_failure_provider"

    def invoke_observed(self, task: TaskContract) -> ProviderExecution:
        del task
        self.calls += 1
        raise ProviderProtocolError(
            "provider HTTP response rejected; PRIVATE body omitted",
            network_attempted=True,
            response_received=True,
            provider_http_status=429,
            provider_error_code="1303",
            transport_stage="http_response",
        )


class ApprovalRejectingProvider(ObservedProvider):
    def validate_approval(self, task):
        del task
        raise LegacyPreTierIncompatibleError(
            "legacy_pre_tier_incompatible"
        )


def delegated_task(
    *,
    task_id: str,
    return_contract: ReturnContract | None = None,
    goal: str = "Return one bounded candidate.",
) -> TaskContract:
    return TaskContract(
        task_id=task_id,
        goal=goal,
        task_type="delegated_routine",
        delegable=True,
        delegation_class=DelegationClass.NON_SENSITIVE_ROUTINE,
        constraints=TaskConstraints(
            max_cost_usd=0.10,
            max_latency_s=30,
            max_output_tokens=65_536,
            internet=True,
        ),
        required_capabilities=("text_generation",),
        return_contract=return_contract or ReturnContract(),
    )


def issue_context(
    services,
    provider_id: str,
    task: TaskContract,
    *,
    provider_tier_binding_digest: str | None = None,
) -> DispatchContext:
    reference = services.authorities.issue(
        source_kind="test",
        source_id=f"{provider_id}:{task.task_id}:{uuid.uuid4()}",
        scope=AuthorityScope(
            providers=(provider_id,),
            planes=(InteractionPlane.DELEGATION.value,),
            task_types=(task.task_type,),
            provider_tier_binding_digests=(
                (provider_tier_binding_digest,)
                if provider_tier_binding_digest is not None
                else ()
            ),
        ),
        expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    )
    return DispatchContext(
        run_id=str(uuid.uuid4()),
        plane=InteractionPlane.DELEGATION,
        origin=DispatchOrigin("test", "process_id", "1234"),
        authorization=reference,
        policy_snapshot_sha256="a" * 64,
        provider_tier_binding_digest=provider_tier_binding_digest,
    )


class RuntimeV05Tests(unittest.TestCase):
    def test_cached_extended_binding_is_rejected_after_active_head_is_standard(self) -> None:
        cached = glm_extended_text_policy().binding()
        provider = ObservedProvider(
            "glm_flash_worker",
            answer="candidate",
            model="glm-5.3-flash",
            capability_binding=cached,
        )
        task = delegated_task(task_id="stale-cached-tier")
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            capability_store = ProviderCapabilityPolicyStore(
                state_root / "settings" / "provider-capability-policies.sqlite3"
            )
            services = replace(
                services,
                capability_policies=capability_store,
            )
            context = issue_context(
                services,
                provider.provider_id,
                task,
                provider_tier_binding_digest=cached.binding_digest,
            )

            result = MacrRuntime(ProviderRegistry((provider,)), services).invoke(
                provider.provider_id,
                task,
                context,
            )
            events = services.events.read_events(run_id=context.run_id)

        self.assertEqual(result.failure_code, "ProviderPolicyError")
        self.assertEqual(result.failure_stage, "provider_capability")
        self.assertEqual(provider.calls, 0)
        self.assertEqual(events, ())

    def test_legacy_provider_approval_refuses_before_lease_or_event(self) -> None:
        binding = ProviderTierBinding(
            provider_id="approval_provider",
            model_id="test-model",
            tier_id="standard",
            revision=1,
            complete_policy_digest="e" * 64,
            max_latency_s=300,
        )
        provider = ApprovalRejectingProvider(
            "approval_provider",
            answer="candidate",
            capability_binding=binding,
        )
        task = delegated_task(task_id="legacy-provider-approval")
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            context = issue_context(
                services,
                provider.provider_id,
                task,
                provider_tier_binding_digest=binding.binding_digest,
            )

            result = MacrRuntime(ProviderRegistry((provider,)), services).invoke(
                provider.provider_id,
                task,
                context,
            )
            events = services.events.read_events(run_id=context.run_id)
            lease = services.leases.read(
                dispatch_resource_key(provider.provider_id, task)
            )

        self.assertEqual(result.failure_code, "LegacyPreTierIncompatibleError")
        self.assertEqual(result.failure_stage, "provider_approval")
        self.assertEqual(provider.calls, 0)
        self.assertEqual(events, ())
        self.assertIsNone(lease)

    def test_provider_capability_binding_mismatch_refuses_before_authority(self) -> None:
        expected = glm_standard_policy().binding()
        provider = ObservedProvider(
            "test_provider",
            answer="candidate",
            capability_binding=expected,
        )
        task = delegated_task(task_id="tier-policy-mismatch")
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            context = issue_context(
                services,
                provider.provider_id,
                task,
                provider_tier_binding_digest="b" * 64,
            )

            result = MacrRuntime(ProviderRegistry((provider,)), services).invoke(
                provider.provider_id,
                task,
                context,
            )
            events = services.events.read_events(run_id=context.run_id)

        self.assertEqual(result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertEqual(result.failure_code, "ProviderPolicyError")
        self.assertEqual(result.failure_stage, "provider_capability")
        self.assertEqual(provider.calls, 0)
        self.assertEqual(events, ())

    def test_dispatch_event_binds_exact_provider_tier_digest(self) -> None:
        binding = ProviderTierBinding(
            provider_id="test_provider",
            model_id="test-model",
            tier_id="standard",
            revision=1,
            complete_policy_digest="e" * 64,
            max_latency_s=300,
        )
        provider = ObservedProvider(
            "test_provider",
            answer="candidate",
            capability_binding=binding,
        )
        task = delegated_task(task_id="tier-policy-evidence")
        binding_digest = binding.binding_digest
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            context = issue_context(
                services,
                provider.provider_id,
                task,
                provider_tier_binding_digest=binding_digest,
            )
            result = MacrRuntime(ProviderRegistry((provider,)), services).invoke(
                provider.provider_id,
                task,
                context,
            )
            events = services.events.read_events(run_id=context.run_id)
            dispatch = events[0]
            terminal = events[-1]

        self.assertEqual(result.status, ResultStatus.CANDIDATE_SUCCESS)
        self.assertEqual(dispatch["payload"]["dispatch_contract_version"], 2)
        self.assertEqual(
            dispatch["payload"]["provider_tier_binding_digest"],
            binding_digest,
        )
        self.assertEqual(
            terminal["payload"]["provider_tier_binding_digest"],
            binding_digest,
        )
        self.assertEqual(terminal["payload"]["terminal_contract_version"], 3)

    def test_model_token_policy_refuses_before_authority_or_provider(self) -> None:
        provider = ObservedProvider(
            "minimax",
            answer="candidate",
            model="MiniMax-M2.7",
        )
        task = delegated_task(task_id="token-policy-refusal")
        task = TaskContract.from_dict(
            {
                **task.to_dict(),
                "constraints": {
                    **task.constraints.to_dict(),
                    "max_output_tokens": 2_049,
                    "max_context_tokens": 180_000,
                },
            }
        )
        missing = AuthorizationReference(
            source_kind="missing",
            source_id="missing",
            digest="b" * 64,
            revision=1,
            epoch=0,
            scope=json.dumps({"missing": True}),
        )
        context = DispatchContext(
            run_id=str(uuid.uuid4()),
            plane=InteractionPlane.DELEGATION,
            origin=DispatchOrigin("test", "process_id", "1234"),
            authorization=missing,
            policy_snapshot_sha256="a" * 64,
        )
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            result = MacrRuntime(ProviderRegistry((provider,)), services).invoke(
                provider.provider_id,
                task,
                context,
            )
            events = services.events.read_events(run_id=context.run_id)

        self.assertEqual(result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertEqual(result.failure_code, "ProviderPolicyError")
        self.assertEqual(result.failure_stage, "token_policy")
        self.assertEqual(result.provider_meta["failure_type"], "ProviderPolicyError")
        self.assertEqual(result.provider_meta["failure_stage"], "token_policy")
        self.assertEqual(provider.calls, 0)
        self.assertEqual(events, ())

    def test_dispatch_event_binds_exact_model_token_policy_digest(self) -> None:
        provider = ObservedProvider(
            "grok",
            answer="candidate",
            model="grok-4.6",
        )
        base = delegated_task(task_id="token-policy-evidence")
        task = replace(
            base,
            constraints=replace(base.constraints, max_output_tokens=32_768),
        )
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            context = issue_context(services, provider.provider_id, task)
            result = MacrRuntime(ProviderRegistry((provider,)), services).invoke(
                provider.provider_id,
                task,
                context,
            )
            dispatch = services.events.read_events(run_id=context.run_id)[0]
            policy = services.token_policies.effective_policy(
                "grok",
                "grok-4.6",
            )

        self.assertEqual(result.status, ResultStatus.CANDIDATE_SUCCESS)
        self.assertEqual(
            dispatch["payload"]["model_token_policy_digest"],
            policy.policy_digest,
        )

    def test_external_cloud_output_below_quality_floor_refuses_before_dispatch(self) -> None:
        provider = ObservedProvider(
            "grok",
            answer="candidate",
            model="grok-4.6",
        )
        base = delegated_task(task_id="cloud-output-quality-floor")
        task = replace(
            base,
            constraints=replace(base.constraints, max_output_tokens=4_096),
        )
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            context = issue_context(services, provider.provider_id, task)
            result = MacrRuntime(ProviderRegistry((provider,)), services).invoke(
                provider.provider_id,
                task,
                context,
            )
            events = services.events.read_events(run_id=context.run_id)

        self.assertEqual(result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertEqual(result.failure_code, "ProviderOutputBudgetTooSmallError")
        self.assertEqual(result.failure_stage, "token_policy")
        self.assertEqual(
            result.provider_meta["policy_violation"]["code"],
            "output_budget_below_quality_floor",
        )
        self.assertEqual(
            result.provider_meta["policy_violation"]["minimum_max_output_tokens"],
            32_768,
        )
        self.assertEqual(provider.calls, 0)
        self.assertEqual(events, ())

    def test_qwythos_output_and_grok_context_are_model_local_fail_closed(self) -> None:
        cases = (
            (
                ObservedProvider(
                    "ollama_qwythos",
                    answer="candidate",
                    model="hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M",
                ),
                4_097,
                8_192,
            ),
            (
                ObservedProvider("grok", answer="candidate", model="grok-4.6"),
                16_384,
                400_001,
            ),
        )
        for provider, output_tokens, context_tokens in cases:
            with self.subTest(provider=provider.provider_id):
                task = delegated_task(task_id=f"{provider.provider_id}-token-refusal")
                task = TaskContract.from_dict(
                    {
                        **task.to_dict(),
                        "constraints": {
                            **task.constraints.to_dict(),
                            "max_output_tokens": output_tokens,
                            "max_context_tokens": context_tokens,
                        },
                    }
                )
                with d_drive_tempdir() as state_root:
                    services = build_test_services(state_root)
                    context = issue_context(services, provider.provider_id, task)
                    result = MacrRuntime(
                        ProviderRegistry((provider,)),
                        services,
                    ).invoke(provider.provider_id, task, context)
                    events = services.events.read_events(run_id=context.run_id)

                self.assertEqual(result.status, ResultStatus.CANDIDATE_FAILURE)
                self.assertEqual(result.provider_meta["failure_stage"], "token_policy")
                self.assertEqual(provider.calls, 0)
                self.assertEqual(events, ())
    def test_non_stop_run_is_accounted_captured_and_terminal_once(self) -> None:
        provider = ObservedProvider(
            "glm_flash_worker",
            answer="PARTIAL",
            status=ResultStatus.CANDIDATE_FAILURE,
            finish_reason="length",
        )
        task = delegated_task(task_id="non-stop-runtime")
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            context = issue_context(services, provider.provider_id, task)
            result = MacrRuntime(
                ProviderRegistry((provider,)),
                services,
            ).invoke(provider.provider_id, task, context)
            events = services.events.read_events(run_id=context.run_id)
            accounting = services.accounting.read_invocation(context.run_id)
            capture = services.vault.read_by_run(context.run_id)

        self.assertEqual(result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(
            [event["event_type"] for event in events],
            ["provider.dispatch_requested", "provider.candidate_completed"],
        )
        self.assertEqual(accounting["finish_reason"], "length")
        self.assertGreater(accounting["currency_cost_usd"], 0)
        self.assertEqual(accounting["candidate_status"], "candidate_failure")
        self.assertEqual(capture.sha256, hashlib.sha256(b"PARTIAL").hexdigest())

    def test_glm_reasoning_exhaustion_reaches_typed_terminal_accounting(self) -> None:
        document = success_document()
        document["choices"][0]["finish_reason"] = "length"
        document["choices"][0]["message"]["content"] = ""
        document["usage"]["completion_tokens"] = 65_536
        document["usage"]["completion_tokens_details"]["reasoning_tokens"] = 65_536
        document["usage"]["total_tokens"] = 65_556
        provider = GlmFlashWorkerProvider(
            glm_config(),
            transport=FakeTransport(document),
            environ={},
            key_source=StaticKeySource(),
            approval_store=AllowingApprovalStore(),
        )
        base = delegated_task(task_id="glm-reasoning-exhaustion-runtime")
        unsigned = replace(
            base,
            constraints=replace(
                base.constraints,
                max_cost_usd=0.10,
                privacy=PrivacyLevel.PUBLIC,
            ),
            delegation_approval_sha256=None,
        )
        approval = provider.approval_metadata(unsigned)[
            "required_approval_sha256"
        ]
        task = replace(unsigned, delegation_approval_sha256=approval)
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            context = issue_context(
                services,
                provider.provider_id,
                task,
                provider_tier_binding_digest=(
                    provider.capability_binding.binding_digest
                ),
            )
            result = MacrRuntime(
                ProviderRegistry((provider,)),
                services,
            ).invoke(provider.provider_id, task, context)
            accounting = services.accounting.read_invocation(context.run_id)
            terminal = services.events.read_events(run_id=context.run_id)[-1]

        self.assertEqual(
            result.failure_code,
            "ProviderReasoningBudgetExhaustedError",
        )
        self.assertEqual(result.failure_stage, "provider_response_validation")
        self.assertEqual(
            accounting["failure_code"],
            "ProviderReasoningBudgetExhaustedError",
        )
        self.assertEqual(
            accounting["failure_stage"],
            "provider_response_validation",
        )
        self.assertEqual(
            terminal["payload"]["failure_type"],
            "ProviderReasoningBudgetExhaustedError",
        )
        self.assertEqual(
            terminal["payload"]["failure_stage"],
            "provider_response_validation",
        )

    def test_missing_authority_refuses_before_dispatch_or_provider(self) -> None:
        provider = ObservedProvider("test_provider", answer="candidate")
        task = delegated_task(task_id="missing-authority")
        missing = AuthorizationReference(
            source_kind="missing",
            source_id="missing",
            digest="b" * 64,
            revision=1,
            epoch=0,
            scope=json.dumps({"missing": True}),
        )
        context = DispatchContext(
            run_id=str(uuid.uuid4()),
            plane=InteractionPlane.DELEGATION,
            origin=DispatchOrigin("test", "process_id", "1234"),
            authorization=missing,
            policy_snapshot_sha256="a" * 64,
        )
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            result = MacrRuntime(ProviderRegistry((provider,)), services).invoke(
                provider.provider_id,
                task,
                context,
            )
            events = services.events.read_events(run_id=context.run_id)

        self.assertEqual(result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertEqual(result.failure_code, "DispatchAuthorizationError")
        self.assertEqual(result.failure_stage, "admission")
        self.assertEqual(result.provider_meta["failure_type"], "DispatchAuthorizationError")
        self.assertEqual(provider.calls, 0)
        self.assertEqual(events, ())

    def test_stale_epoch_refuses_before_lease_or_provider(self) -> None:
        provider = ObservedProvider("test_provider", answer="candidate")
        task = delegated_task(task_id="stale-epoch")
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            context = issue_context(services, provider.provider_id, task)
            services.authorities.advance_epoch(reason_digest="c" * 64, state="open")
            result = MacrRuntime(ProviderRegistry((provider,)), services).invoke(
                provider.provider_id,
                task,
                context,
            )
            events = services.events.read_events(run_id=context.run_id)
            lease = services.leases.read(dispatch_resource_key(provider.provider_id, task))

        self.assertEqual(result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertEqual(provider.calls, 0)
        self.assertEqual(events, ())
        self.assertIsNone(lease)

    def test_lease_contention_refuses_before_provider(self) -> None:
        provider = ObservedProvider("test_provider", answer="candidate")
        task = delegated_task(task_id="lease-contention")
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            context = issue_context(services, provider.provider_id, task)
            resource = dispatch_resource_key(provider.provider_id, task)
            services.leases.acquire(resource, str(uuid.uuid4()), ttl_seconds=300)
            result = MacrRuntime(ProviderRegistry((provider,)), services).invoke(
                provider.provider_id,
                task,
                context,
            )
            events = services.events.read_events(run_id=context.run_id)

        self.assertEqual(result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertEqual(result.provider_meta["failure_type"], "DispatchLeaseError")
        self.assertEqual(provider.calls, 0)
        self.assertEqual(events, ())

    def test_unexpected_provider_crash_is_terminal_and_unknown_after_dispatch(self) -> None:
        provider = ExplodingProvider()
        task = delegated_task(task_id="provider-crash")
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            context = issue_context(services, provider.provider_id, task)
            result = MacrRuntime(ProviderRegistry((provider,)), services).invoke(
                provider.provider_id,
                task,
                context,
            )
            accounting = services.accounting.read_invocation(context.run_id)
            events = services.events.read_events(run_id=context.run_id)

        self.assertEqual(result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(result.failure_code, "RuntimeError")
        self.assertEqual(result.failure_stage, "provider_execution")
        self.assertIn("RuntimeError", result.warnings[0])
        self.assertEqual(accounting["billing_state"], "unknown_after_dispatch")
        self.assertEqual(accounting["candidate_status"], "candidate_failure")
        self.assertEqual(len(events), 2)
        self.assertNotIn("PRIVATE", str(result.to_dict()))

    def test_transport_failure_preserves_safe_boundary_evidence(self) -> None:
        provider = HttpFailingProvider()
        task = delegated_task(task_id="provider-http-failure")
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            context = issue_context(services, provider.provider_id, task)
            result = MacrRuntime(ProviderRegistry((provider,)), services).invoke(
                provider.provider_id,
                task,
                context,
            )
            accounting = services.accounting.read_invocation(context.run_id)
            events = services.events.read_events(run_id=context.run_id)

        expected = {
            "network_attempted": True,
            "response_received": True,
            "provider_http_status": 429,
            "provider_error_code": "1303",
            "transport_stage": "http_response",
        }
        self.assertEqual(result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertEqual(result.failure_code, "ProviderProtocolError")
        self.assertTrue(expected.items() <= result.provider_meta.items())
        self.assertIsInstance(result.provider_meta["metrics"]["duration_ms"], int)
        self.assertNotIn("PRIVATE", str(result.to_dict()))
        self.assertTrue(expected.keys() <= accounting.keys())
        self.assertEqual(
            {key: accounting[key] for key in expected},
            expected,
        )
        terminal = events[-1]["payload"]
        self.assertEqual(
            {key: terminal[key] for key in expected},
            expected,
        )
        self.assertIsInstance(terminal["duration_ms"], int)
        self.assertEqual(accounting["billing_state"], "unknown_after_dispatch")

    def test_return_contract_invalidity_preserves_raw_candidate(self) -> None:
        provider = ObservedProvider("test_provider", answer="WRONG")
        task = delegated_task(
            task_id="return-invalid",
            return_contract=ReturnContract(
                summary=False,
                evidence=False,
                format=ReturnFormat.EXACT_TEXT,
                exact_text="EXPECTED",
            ),
        )
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            context = issue_context(services, provider.provider_id, task)
            result = MacrRuntime(ProviderRegistry((provider,)), services).invoke(
                provider.provider_id,
                task,
                context,
            )
            capture = services.vault.read_by_run(context.run_id)
            terminal = services.events.read_events(run_id=context.run_id)[-1]

        self.assertEqual(result.status, ResultStatus.CANDIDATE_FAILURE)
        self.assertEqual(result.answer, "")
        self.assertEqual(result.failure_code, "ReturnContractError")
        self.assertEqual(result.failure_stage, "return_contract")
        self.assertEqual(capture.sha256, hashlib.sha256(b"WRONG").hexdigest())
        self.assertEqual(terminal["payload"]["return_contract_state"], "invalid")
        self.assertEqual(terminal["payload"]["return_contract_reason"], "exact_text_mismatch")

    def test_successful_exact_text_is_captured_and_valid(self) -> None:
        provider = ObservedProvider("test_provider", answer="EXPECTED")
        task = delegated_task(
            task_id="return-valid",
            return_contract=ReturnContract(
                summary=False,
                evidence=False,
                format=ReturnFormat.EXACT_TEXT,
                exact_text="EXPECTED",
            ),
        )
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            context = issue_context(services, provider.provider_id, task)
            result = MacrRuntime(ProviderRegistry((provider,)), services).invoke(
                provider.provider_id,
                task,
                context,
            )
            terminal = services.events.read_events(run_id=context.run_id)[-1]

        self.assertEqual(result.status, ResultStatus.CANDIDATE_SUCCESS)
        self.assertEqual(result.answer, "EXPECTED")
        self.assertEqual(terminal["payload"]["return_contract_state"], "valid")

    def test_sensitive_prompt_answer_and_key_never_enter_databases(self) -> None:
        sensitive_answer = "SENSITIVE ANSWER TOKEN"
        provider = ObservedProvider("test_provider", answer=sensitive_answer)
        task = delegated_task(
            task_id="database-content-boundary",
            goal="SENSITIVE PROMPT TOKEN",
            return_contract=ReturnContract(
                summary=False,
                evidence=False,
                format=ReturnFormat.EXACT_TEXT,
                exact_text=sensitive_answer,
            ),
        )
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            context = issue_context(services, provider.provider_id, task)
            result = MacrRuntime(ProviderRegistry((provider,)), services).invoke(
                provider.provider_id,
                task,
                context,
            )
            runtime_bytes = (state_root / "runtime" / "dispatch.sqlite3").read_bytes()
            accounting_bytes = (
                state_root / "accounting" / "accounting.sqlite3"
            ).read_bytes()

        self.assertEqual(result.status, ResultStatus.CANDIDATE_SUCCESS)
        for forbidden in (
            b"SENSITIVE PROMPT TOKEN",
            b"SENSITIVE ANSWER TOKEN",
            b"test-secret-key",
        ):
            self.assertNotIn(forbidden, runtime_bytes)
            self.assertNotIn(forbidden, accounting_bytes)


if __name__ == "__main__":
    unittest.main()
