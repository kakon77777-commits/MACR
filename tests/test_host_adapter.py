from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from macr_runtime.authority import AuthorityScope
from macr_runtime.config import ConnectionScope
from macr_runtime.contracts import ProviderResult, ResultStatus
from macr_runtime.errors import DispatchAuthorizationError, ProviderPolicyError
from macr_runtime.execution import (
    DispatchOrigin,
    InteractionPlane,
    ProviderExecution,
    ProviderState,
    ProviderUsage,
    RawProviderObservation,
)
from macr_runtime.host_adapter import (
    HostBindingEvidence,
    HostInvocationGrant,
    HostKind,
    MacrHostAdapter,
    VerifiedHostBinding,
)
from macr_runtime.provider_admission import (
    AdmissionLane,
    ProjectAdmissionBinding,
    ProviderAdmissionKernel,
    glm_provider_admission_policy,
)
from macr_runtime.provider_capability import ProviderTierBinding
from macr_runtime.providers.base import BaseProvider, ProviderHealth
from macr_runtime.registry import ProviderRegistry
from tests.support import build_test_services, d_drive_tempdir
from tests.test_runtime_v05 import delegated_task
from tests.test_glm_provider import (
    AllowingApprovalStore,
    CountingKeySource,
    FakeTransport,
    delegated_task as glm_task,
    glm_config,
    success_document,
)
from macr_runtime.providers.glm import GlmFlashWorkerProvider


class StaticHostVerifier:
    def __init__(self, host_kind: HostKind, native_id: str) -> None:
        self.host_kind = host_kind
        self.native_id = native_id

    def verify(self) -> HostBindingEvidence:
        return HostBindingEvidence(
            host_kind=self.host_kind,
            identifier_kind=(
                "codex_thread_id"
                if self.host_kind is HostKind.CODEX
                else "claude_code_session_id"
            ),
            native_id=self.native_id,
            verifier_digest="a" * 64,
        )


class ExactGrantVerifier:
    def __init__(self, accepted_digest: str) -> None:
        self.accepted_digest = accepted_digest
        self.calls = 0

    def verify(self, grant, preparation) -> None:
        self.calls += 1
        if grant.grant_digest != self.accepted_digest:
            raise DispatchAuthorizationError("host invocation grant is invalid")
        if grant.provider_id != preparation.provider_id:
            raise DispatchAuthorizationError("host invocation grant provider mismatch")
        if grant.connection_scope != preparation.connection_scope:
            raise DispatchAuthorizationError("host invocation connectivity mismatch")
        if (
            grant.provider_tier_binding_digest
            != preparation.provider_tier_binding_digest
        ):
            raise DispatchAuthorizationError("host invocation tier mismatch")


class HostTestProvider(BaseProvider):
    provider_id = "host_test_provider"
    connection_scope = ConnectionScope.EXTERNAL_HTTPS

    def __init__(self) -> None:
        self.calls = 0
        self.capability_binding = ProviderTierBinding(
            provider_id=self.provider_id,
            model_id="host-test-model",
            tier_id="standard",
            revision=1,
            complete_policy_digest="b" * 64,
            max_latency_s=300,
        )

    def health(self):
        return ProviderHealth(self.provider_id, True, "configured_offline")

    def approval_metadata(self, task):
        return {
            "required_approval_sha256": task.delegation_approval_sha256,
            "provider_tier_binding_digest": self.capability_binding.binding_digest,
            "conservative_cost_ceiling_usd": task.constraints.max_cost_usd,
        }

    def validate_approval(self, task):
        return self.approval_metadata(task)

    def invoke(self, task):
        return self.invoke_observed(task).result

    def invoke_observed(self, task):
        self.calls += 1
        result = ProviderResult(
            task_id=task.task_id,
            status=ResultStatus.CANDIDATE_SUCCESS,
            answer="candidate",
        )
        observation = RawProviderObservation(
            provider_id=self.provider_id,
            model="host-test-model",
            response_id="response-1",
            finish_reason="stop",
            usage=ProviderUsage(10, 5, 0, 0),
            currency_cost_usd=0.001,
            cost_kind="estimated",
            pricing_basis_version="test-v1",
            duration_ms=10,
            answer_bytes=b"candidate",
            provider_state=ProviderState.COMPLETED,
        )
        return ProviderExecution.from_observation(observation, result)


class HostAdapterTests(unittest.TestCase):
    def test_glm_host_adapter_binds_project_lane_and_admission_policy(self) -> None:
        task = glm_task()
        project = ProjectAdmissionBinding(
            "host-project",
            1,
            "operator_enrolled",
        )
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            kernel = ProviderAdmissionKernel(services.events.path)
            services = replace(services, provider_admission=kernel)
            transport = FakeTransport(success_document())
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=transport,
                key_source=CountingKeySource(),
                approval_store=AllowingApprovalStore(),
                admission_guard=kernel,
                offline_test_transport=True,
            )
            tier = provider.capability_binding.binding_digest
            policy = glm_provider_admission_policy()
            reference = services.authorities.issue(
                source_kind="operator_host_grant",
                source_id="glm-host-admission",
                scope=AuthorityScope(
                    providers=(provider.provider_id,),
                    planes=(InteractionPlane.DELEGATION.value,),
                    task_types=(task.task_type,),
                    member_digests=(task.delegation_approval_sha256,),
                    provider_tier_binding_digests=(tier,),
                    project_binding_digests=(project.binding_digest,),
                    admission_lanes=(AdmissionLane.ROUTINE.value,),
                    provider_admission_policy_digests=(policy.policy_digest,),
                    scope_contract_version=3,
                ),
                expires_at=(
                    datetime.now(timezone.utc) + timedelta(minutes=5)
                ).isoformat(),
            )
            grant = HostInvocationGrant(
                authorization=reference,
                provider_id=provider.provider_id,
                connection_scope="external_https",
                provider_tier_binding_digest=tier,
                grant_digest="c" * 64,
                project_binding_digest=project.binding_digest,
                admission_lane=AdmissionLane.ROUTINE.value,
                provider_admission_policy_digest=policy.policy_digest,
            )
            adapter = MacrHostAdapter(
                ProviderRegistry((provider,)),
                services,
                host_verifier=StaticHostVerifier(
                    HostKind.CLAUDE_CODE,
                    "22222222-2222-4222-8222-222222222222",
                ),
                grant_verifier=ExactGrantVerifier("c" * 64),
                admission_project=project,
                admission_lane=AdmissionLane.ROUTINE,
            )

            result = adapter.invoke(provider.provider_id, task, grant)
            events = services.events.read_events()

        self.assertEqual(result.status, ResultStatus.CANDIDATE_SUCCESS)
        self.assertEqual(len(transport.posts), 1)
        self.assertEqual(
            events[0]["payload"]["project_binding_digest"],
            project.binding_digest,
        )

    def test_host_adapter_contracts_are_lazy_root_exports(self) -> None:
        import macr_runtime

        self.assertIs(macr_runtime.MacrHostAdapter, MacrHostAdapter)
        self.assertIs(macr_runtime.HostKind, HostKind)

    def test_verified_binding_cannot_be_constructed_from_caller_dto(self) -> None:
        with self.assertRaises(TypeError):
            VerifiedHostBinding(
                host_kind=HostKind.CLAUDE_CODE,
                identifier_kind="claude_code_session_id",
                native_id=str(uuid.uuid4()),
                verifier_digest="a" * 64,
            )

    def test_codex_and_claude_preflight_have_equal_policy_rights(self) -> None:
        task = delegated_task(task_id="host-preflight")
        provider = HostTestProvider()
        registry = ProviderRegistry((provider,))
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            before = services.events.read_events()
            codex = MacrHostAdapter(
                registry,
                services,
                host_verifier=StaticHostVerifier(
                    HostKind.CODEX,
                    "11111111-1111-4111-8111-111111111111",
                ),
                grant_verifier=ExactGrantVerifier("c" * 64),
            ).preflight(provider.provider_id, task)
            claude = MacrHostAdapter(
                registry,
                services,
                host_verifier=StaticHostVerifier(
                    HostKind.CLAUDE_CODE,
                    "22222222-2222-4222-8222-222222222222",
                ),
                grant_verifier=ExactGrantVerifier("c" * 64),
            ).preflight(provider.provider_id, task)
            after = services.events.read_events()

        self.assertEqual(codex.provider_id, claude.provider_id)
        self.assertEqual(codex.task_digest, claude.task_digest)
        self.assertEqual(
            codex.provider_tier_binding_digest,
            claude.provider_tier_binding_digest,
        )
        self.assertEqual(codex.approval_digest, claude.approval_digest)
        self.assertEqual(codex.cost_ceiling_usd, claude.cost_ceiling_usd)
        self.assertNotEqual(codex.host_binding_digest, claude.host_binding_digest)
        self.assertNotEqual(codex.request_digest, claude.request_digest)
        self.assertEqual(before, after)
        self.assertEqual(provider.calls, 0)

    def test_invoke_consumes_preissued_grant_and_records_exact_host_origin(self) -> None:
        task = delegated_task(task_id="host-invoke")
        provider = HostTestProvider()
        registry = ProviderRegistry((provider,))
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            binding_digest = provider.capability_binding.binding_digest
            reference = services.authorities.issue(
                source_kind="operator_host_grant",
                source_id="host-invoke-grant",
                scope=AuthorityScope(
                    providers=(provider.provider_id,),
                    planes=(InteractionPlane.DELEGATION.value,),
                    task_types=(task.task_type,),
                    member_digests=(),
                    provider_tier_binding_digests=(binding_digest,),
                ),
                expires_at=(
                    datetime.now(timezone.utc) + timedelta(minutes=5)
                ).isoformat(),
            )
            grant = HostInvocationGrant(
                authorization=reference,
                provider_id=provider.provider_id,
                connection_scope="external_https",
                provider_tier_binding_digest=binding_digest,
                grant_digest="c" * 64,
            )
            verifier = ExactGrantVerifier("c" * 64)
            adapter = MacrHostAdapter(
                registry,
                services,
                host_verifier=StaticHostVerifier(
                    HostKind.CLAUDE_CODE,
                    "22222222-2222-4222-8222-222222222222",
                ),
                grant_verifier=verifier,
            )

            with patch.object(
                services.authorities,
                "issue",
                side_effect=AssertionError("adapter must not issue authority"),
            ):
                result = adapter.invoke(provider.provider_id, task, grant)
            events = services.events.read_events()
            accounting = services.accounting.read_invocation(events[0]["run_id"])

        self.assertEqual(result.status, ResultStatus.CANDIDATE_SUCCESS)
        self.assertEqual(verifier.calls, 1)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(events[0]["payload"]["origin_host"], "claude_code")
        self.assertEqual(
            events[0]["payload"]["origin_identifier_kind"],
            "claude_code_session_id",
        )
        self.assertEqual(accounting["origin_host"], "claude_code")
        self.assertEqual(
            accounting["provider_tier_binding_digest"],
            binding_digest,
        )

    def test_invoke_without_preissued_grant_fails_before_state_or_provider(self) -> None:
        task = delegated_task(task_id="host-missing-grant")
        provider = HostTestProvider()
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            adapter = MacrHostAdapter(
                ProviderRegistry((provider,)),
                services,
                host_verifier=StaticHostVerifier(
                    HostKind.CODEX,
                    "11111111-1111-4111-8111-111111111111",
                ),
                grant_verifier=ExactGrantVerifier("c" * 64),
            )

            with self.assertRaisesRegex(DispatchAuthorizationError, "pre-issued"):
                adapter.invoke(provider.provider_id, task, None)

            self.assertEqual(services.events.read_events(), ())
            self.assertEqual(provider.calls, 0)

    def test_untrusted_environment_or_hook_data_is_not_an_adapter_input(self) -> None:
        task = delegated_task(task_id="host-forgery")
        provider = HostTestProvider()
        with d_drive_tempdir() as state_root:
            services = build_test_services(state_root)
            adapter = MacrHostAdapter(
                ProviderRegistry((provider,)),
                services,
                host_verifier={
                    "CLAUDE_CODE_SESSION_ID": str(uuid.uuid4()),
                    "session_id": str(uuid.uuid4()),
                    "CLAUDE_ENV_FILE": "attacker-controlled",
                },
                grant_verifier=ExactGrantVerifier("c" * 64),
            )

            with self.assertRaisesRegex(ProviderPolicyError, "host-owned verifier"):
                adapter.preflight(provider.provider_id, task)

            self.assertEqual(services.events.read_events(), ())
            self.assertEqual(provider.calls, 0)


if __name__ == "__main__":
    unittest.main()
