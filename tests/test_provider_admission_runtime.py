from __future__ import annotations

import uuid
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from macr_runtime.authority import AuthorityScope
from macr_runtime.errors import (
    ProviderAdmissionBusyError,
    ProviderAdmissionRequiredError,
    ProviderUnavailableError,
)
from macr_runtime.execution import (
    DispatchContext,
    DispatchOrigin,
    InteractionPlane,
)
from macr_runtime.provider_admission import (
    AdmissionLane,
    ProjectAdmissionBinding,
    ProviderAdmissionDirectory,
    ProviderAdmissionKernel,
    ProviderAdmissionPolicyTransitionBinding,
    ProviderAdmissionRequest,
    glm_provider_admission_policy,
    glm_provider_admission_policy_v2,
)
from macr_runtime.providers.grok import GrokResponsesProvider
from macr_runtime.providers.glm import GlmFlashWorkerProvider
from macr_runtime.registry import ProviderRegistry
from macr_runtime.runtime import MacrRuntime, task_contract_digest
from tests.support import build_test_services, d_drive_tempdir
from tests.test_glm_provider import (
    AllowingApprovalStore,
    CountingKeySource,
    FakeTransport,
    RejectingMacApprovalStore,
    delegated_task,
    glm_config,
    success_document,
)
from tests.test_grok_provider import (
    FakeTransport as GrokFakeTransport,
    cloud_task as grok_task,
    grok_config,
    success_document as grok_success_document,
)


class NoResponseTransport(FakeTransport):
    def post_json(self, url, *, headers, payload, timeout_s):
        del url, headers, payload, timeout_s
        raise ProviderUnavailableError(
            "synthetic no response",
            network_attempted=True,
            response_received=False,
            transport_stage="connection",
        )


class GrokNoResponseTransport(GrokFakeTransport):
    def post_json(self, url, *, headers, payload, timeout_s):
        del url, headers, payload, timeout_s
        raise ProviderUnavailableError(
            "synthetic Grok no response",
            network_attempted=True,
            response_received=False,
            transport_stage="connection",
        )


class NoOpAdmissionGuard:
    def begin_transport(self, permit, request):
        del permit, request


class ProviderAdmissionRuntimeTests(unittest.TestCase):
    def test_policy_migration_preserves_unknown_billing_and_null_cost(self) -> None:
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            predecessor = glm_provider_admission_policy_v2()
            kernel = ProviderAdmissionKernel(
                services.events.path,
                policy=predecessor,
            )
            services = replace(services, provider_admission=kernel)
            provider = self._provider(
                kernel,
                NoResponseTransport(success_document()),
                CountingKeySource(),
            )
            task = delegated_task()
            project = ProjectAdmissionBinding(
                "legacy-project",
                1,
                "operator_asserted",
            )
            context, _ = self._context_and_reference(
                services,
                task,
                project,
                AdmissionLane.ROUTINE,
                admission_policy=predecessor,
            )
            result = MacrRuntime(
                ProviderRegistry((provider,)),
                services,
            ).invoke(provider.provider_id, task, context)
            before = services.accounting.read_invocation(context.run_id)
            successor = glm_provider_admission_policy()
            binding = ProviderAdmissionPolicyTransitionBinding.create(
                predecessor,
                successor,
                target=8,
                reconciliation_snapshot_digest=(
                    kernel.reconciliation_isolation_snapshot_digest()
                ),
                reconciliation_isolation_evidence_digest="9" * 64,
            )
            now = datetime.now(timezone.utc)
            reference = services.authorities.issue(
                source_kind="operator_capacity_authority",
                source_id="runtime-policy-v2-to-v3",
                scope=AuthorityScope(
                    providers=(provider.provider_id,),
                    planes=("provider_capacity_activation",),
                    task_types=("provider_admission_policy_transition",),
                    provider_admission_target_digests=(
                        binding.binding_digest,
                    ),
                    scope_contract_version=3,
                ),
                expires_at=(now + timedelta(minutes=10)).isoformat(),
            )

            migrated = kernel.supersede_policy(
                binding,
                successor,
                reference,
            )
            after = services.accounting.read_invocation(context.run_id)

        self.assertEqual(result.failure_code, "ProviderUnavailableError")
        self.assertEqual(before, after)
        self.assertEqual(after["billing_state"], "unknown_after_dispatch")
        self.assertIsNone(after["currency_cost_usd"])
        self.assertEqual(migrated.circuit_state, "closed")
        self.assertEqual(migrated.counts["reconciliation_required"], 1)

    def _grok_context_and_reference(
        self,
        services,
        task,
        project: ProjectAdmissionBinding,
        *,
        run_id: str | None = None,
    ):
        kernel = services.provider_admission_for("grok")
        assert kernel is not None
        run = run_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        reference = services.authorities.issue(
            source_kind="operator_test",
            source_id=f"grok-admission-{run}",
            scope=AuthorityScope(
                providers=("grok",),
                planes=(InteractionPlane.DELEGATION.value,),
                task_types=(task.task_type,),
                project_binding_digests=(project.binding_digest,),
                admission_lanes=(AdmissionLane.ROUTINE.value,),
                provider_admission_policy_digests=(
                    kernel.policy.policy_digest,
                ),
                scope_contract_version=3,
            ),
            expires_at=(now + timedelta(minutes=10)).isoformat(),
        )
        return DispatchContext(
            run_id=run,
            plane=InteractionPlane.DELEGATION,
            origin=DispatchOrigin("test", "process_id", "1234"),
            authorization=reference,
            policy_snapshot_sha256="f" * 64,
            project_binding_digest=project.binding_digest,
            admission_lane=AdmissionLane.ROUTINE.value,
            provider_admission_policy_digest=kernel.policy.policy_digest,
        )

    def test_delegated_grok_success_uses_separate_shared_capacity(self) -> None:
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            directory = ProviderAdmissionDirectory.offline_test(
                services.events.path
            )
            services = replace(
                services,
                provider_admission=directory.get("glm_flash_worker"),
                provider_admissions=directory,
            )
            transport = GrokFakeTransport(grok_success_document("grok-4.6"))
            grok_kernel = directory.get("grok")
            provider = GrokResponsesProvider(
                grok_config("grok", "grok-4.6", "high"),
                transport=transport,
                environ={"XAI_API_KEY": "test-key"},
                admission_guard=grok_kernel,
                offline_test_transport=True,
            )
            task = grok_task(max_output_tokens=32_768)
            project = ProjectAdmissionBinding(
                "frontier-project",
                1,
                "operator_asserted",
            )
            context = self._grok_context_and_reference(
                services,
                task,
                project,
            )

            result = MacrRuntime(
                ProviderRegistry((provider,)),
                services,
            ).invoke(provider.provider_id, task, context)
            grok_status = grok_kernel.status("grok")
            glm_status = directory.get("glm_flash_worker").status(
                "glm_flash_worker"
            )
            accounting = services.accounting.read_invocation(context.run_id)

        self.assertEqual(result.status.value, "candidate_success")
        self.assertEqual(len(transport.posts), 1)
        self.assertEqual(grok_status.counts["completed"], 1)
        self.assertEqual(grok_status.circuit_state, "closed")
        self.assertEqual(glm_status.counts["completed"], 0)
        self.assertEqual(accounting["network_attempted"], 1)
        self.assertEqual(accounting["response_received"], 1)

    def test_delegated_grok_missing_key_cancels_unused_grant(self) -> None:
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            directory = ProviderAdmissionDirectory.offline_test(
                services.events.path
            )
            services = replace(
                services,
                provider_admission=directory.get("glm_flash_worker"),
                provider_admissions=directory,
            )
            transport = GrokFakeTransport(grok_success_document("grok-4.6"))
            kernel = directory.get("grok")
            provider = GrokResponsesProvider(
                grok_config("grok", "grok-4.6", "high"),
                transport=transport,
                environ={},
                admission_guard=kernel,
                offline_test_transport=True,
            )
            task = grok_task()
            project = ProjectAdmissionBinding(
                "frontier-project",
                1,
                "operator_asserted",
            )
            context = self._grok_context_and_reference(
                services,
                task,
                project,
            )

            result = MacrRuntime(
                ProviderRegistry((provider,)),
                services,
            ).invoke(provider.provider_id, task, context)
            status = kernel.status("grok")
            accounting = services.accounting.read_invocation(context.run_id)

        self.assertEqual(result.failure_code, "ProviderUnavailableError")
        self.assertEqual(status.counts["cancelled"], 1)
        self.assertEqual(status.counts["reconciliation_required"], 0)
        self.assertEqual(accounting["billing_state"], "zero_local")
        self.assertEqual(transport.posts, [])

    def test_delegated_grok_received_malformed_response_releases_capacity(self) -> None:
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            directory = ProviderAdmissionDirectory.offline_test(
                services.events.path
            )
            services = replace(
                services,
                provider_admission=directory.get("glm_flash_worker"),
                provider_admissions=directory,
            )
            transport = GrokFakeTransport({"model": "grok-4.6", "usage": {}})
            kernel = directory.get("grok")
            provider = GrokResponsesProvider(
                grok_config("grok", "grok-4.6", "high"),
                transport=transport,
                environ={"XAI_API_KEY": "test-key"},
                admission_guard=kernel,
                offline_test_transport=True,
            )
            task = grok_task()
            project = ProjectAdmissionBinding(
                "frontier-project",
                1,
                "operator_asserted",
            )
            context = self._grok_context_and_reference(
                services,
                task,
                project,
            )

            result = MacrRuntime(
                ProviderRegistry((provider,)),
                services,
            ).invoke(provider.provider_id, task, context)
            status = kernel.status("grok")

        self.assertEqual(result.failure_code, "ProviderProtocolError")
        self.assertEqual(status.counts["completed"], 1)
        self.assertEqual(status.counts["reconciliation_required"], 0)
        self.assertEqual(status.circuit_state, "closed")

    def test_delegated_grok_no_response_opens_reconciliation(self) -> None:
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            directory = ProviderAdmissionDirectory.offline_test(
                services.events.path
            )
            services = replace(
                services,
                provider_admission=directory.get("glm_flash_worker"),
                provider_admissions=directory,
            )
            kernel = directory.get("grok")
            provider = GrokResponsesProvider(
                grok_config("grok", "grok-4.6", "high"),
                transport=GrokNoResponseTransport(
                    grok_success_document("grok-4.6")
                ),
                environ={"XAI_API_KEY": "test-key"},
                admission_guard=kernel,
                offline_test_transport=True,
            )
            task = grok_task()
            project = ProjectAdmissionBinding(
                "frontier-project",
                1,
                "operator_asserted",
            )
            context = self._grok_context_and_reference(
                services,
                task,
                project,
            )

            result = MacrRuntime(
                ProviderRegistry((provider,)),
                services,
            ).invoke(provider.provider_id, task, context)
            status = kernel.status("grok")

        self.assertEqual(result.failure_code, "ProviderUnavailableError")
        self.assertEqual(status.counts["reconciliation_required"], 1)
        self.assertEqual(status.circuit_state, "closed")
        self.assertEqual(status.last_signal, "unknown_after_dispatch_isolated")

    def test_known_local_approval_failure_releases_capacity_without_transport(self) -> None:
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            kernel = ProviderAdmissionKernel(services.events.path)
            services = replace(services, provider_admission=kernel)
            transport = FakeTransport(success_document())
            key_source = CountingKeySource()
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=transport,
                key_source=key_source,
                approval_store=RejectingMacApprovalStore(),
                admission_guard=kernel,
                offline_test_transport=True,
            )
            task = delegated_task()
            project = ProjectAdmissionBinding(
                "project-a",
                1,
                "operator_asserted",
            )
            context, _ = self._context_and_reference(
                services,
                task,
                project,
                AdmissionLane.ROUTINE,
            )

            result = MacrRuntime(
                ProviderRegistry((provider,)),
                services,
            ).invoke(provider.provider_id, task, context)
            status = kernel.status(provider.provider_id)
            accounting = services.accounting.read_invocation(context.run_id)

        self.assertEqual(result.status.value, "candidate_failure")
        self.assertEqual(key_source.calls, 1)
        self.assertEqual(transport.posts, [])
        self.assertEqual(status.counts["completed"], 1)
        self.assertEqual(status.counts["reconciliation_required"], 0)
        self.assertEqual(status.circuit_state, "closed")
        self.assertEqual(accounting["billing_state"], "zero_local")
        self.assertEqual(accounting["currency_cost_usd"], 0.0)

    def _context_and_reference(
        self,
        services,
        task,
        project: ProjectAdmissionBinding,
        lane: AdmissionLane,
        *,
        run_id: str | None = None,
        admission_policy=None,
    ):
        policy = admission_policy or glm_provider_admission_policy()
        tier = "ad88c6730fd2ad6f6fddc834b698cfc6572944a7584ac7fa7823e58d394de793"
        run = run_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        reference = services.authorities.issue(
            source_kind="operator_test",
            source_id=f"runtime-admission-{run}",
            scope=AuthorityScope(
                providers=("glm_flash_worker",),
                planes=(InteractionPlane.DELEGATION.value,),
                task_types=(task.task_type,),
                member_digests=(task.delegation_approval_sha256,),
                provider_tier_binding_digests=(tier,),
                project_binding_digests=(project.binding_digest,),
                admission_lanes=(lane.value,),
                provider_admission_policy_digests=(policy.policy_digest,),
                scope_contract_version=3,
            ),
            expires_at=(now + timedelta(minutes=10)).isoformat(),
        )
        return DispatchContext(
            run_id=run,
            plane=InteractionPlane.DELEGATION,
            origin=DispatchOrigin("test", "process_id", "1234"),
            authorization=reference,
            policy_snapshot_sha256="f" * 64,
            member_digest=task.delegation_approval_sha256,
            provider_tier_binding_digest=tier,
            project_binding_digest=project.binding_digest,
            admission_lane=lane.value,
            provider_admission_policy_digest=policy.policy_digest,
        ), reference

    def _provider(self, kernel, transport, key_source):
        return GlmFlashWorkerProvider(
            glm_config(),
            transport=transport,
            key_source=key_source,
            approval_store=AllowingApprovalStore(),
            admission_guard=kernel,
            offline_test_transport=True,
        )

    def test_runtime_success_uses_one_permit_and_persists_admission_identity(self) -> None:
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            kernel = ProviderAdmissionKernel(services.events.path)
            services = replace(services, provider_admission=kernel)
            transport = FakeTransport(success_document())
            key_source = CountingKeySource()
            provider = self._provider(kernel, transport, key_source)
            task = delegated_task()
            project = ProjectAdmissionBinding(
                "project-a",
                1,
                "operator_asserted",
            )
            context, _ = self._context_and_reference(
                services,
                task,
                project,
                AdmissionLane.ROUTINE,
            )

            result = MacrRuntime(
                ProviderRegistry((provider,)),
                services,
            ).invoke(provider.provider_id, task, context)
            status = kernel.status(provider.provider_id)
            events = services.events.read_events(run_id=context.run_id)

        self.assertEqual(result.status.value, "candidate_success")
        self.assertEqual(key_source.calls, 1)
        self.assertEqual(len(transport.posts), 1)
        self.assertEqual(status.counts["completed"], 1)
        self.assertEqual(status.counts["granted"], 0)
        self.assertEqual(status.counts["dispatched"], 0)
        self.assertEqual(
            events[0]["payload"]["project_binding_digest"],
            project.binding_digest,
        )
        self.assertEqual(events[0]["payload"]["admission_lane"], "routine")
        self.assertEqual(
            events[0]["payload"]["provider_admission_policy_digest"],
            glm_provider_admission_policy().policy_digest,
        )

    def test_busy_runtime_performs_no_key_transport_event_or_accounting(self) -> None:
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            admission_policy = replace(
                glm_provider_admission_policy(),
                effective_target=1,
                per_project_cap=1,
            )
            kernel = ProviderAdmissionKernel(
                services.events.path,
                policy=admission_policy,
            )
            services = replace(services, provider_admission=kernel)
            transport = FakeTransport(success_document())
            key_source = CountingKeySource()
            provider = self._provider(kernel, transport, key_source)
            task = delegated_task()
            first_project = ProjectAdmissionBinding(
                "project-a",
                1,
                "operator_asserted",
            )
            second_project = ProjectAdmissionBinding(
                "project-b",
                1,
                "operator_asserted",
            )
            first_context, first_reference = self._context_and_reference(
                services,
                task,
                first_project,
                AdmissionLane.BULK,
                admission_policy=admission_policy,
            )
            held_request = ProviderAdmissionRequest(
                request_id=str(uuid.uuid4()),
                provider_id=provider.provider_id,
                project_binding_digest=first_project.binding_digest,
                lane=AdmissionLane.BULK,
                run_id=first_context.run_id,
                authorization=first_reference,
                plane=first_context.plane.value,
                task_type=task.task_type,
                task_digest=task_contract_digest(task),
                member_digest=task.delegation_approval_sha256,
                batch_id=None,
                provider_tier_binding_digest=(
                    first_context.provider_tier_binding_digest
                ),
            )
            held = kernel.try_admit(held_request, ttl_seconds=60)
            second_context, _ = self._context_and_reference(
                services,
                task,
                second_project,
                AdmissionLane.ROUTINE,
                admission_policy=admission_policy,
            )

            with self.assertRaises(ProviderAdmissionBusyError):
                MacrRuntime(
                    ProviderRegistry((provider,)),
                    services,
                ).invoke(provider.provider_id, task, second_context)
            kernel.cancel_before_transport(held)
            events = services.events.read_events(run_id=second_context.run_id)
            accounting = services.accounting.read_invocation(second_context.run_id)

        self.assertEqual(key_source.calls, 0)
        self.assertEqual(transport.posts, [])
        self.assertEqual(events, ())
        self.assertIsNone(accounting)

    def test_pregranted_permit_is_cancelled_on_early_token_refusal(self) -> None:
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            kernel = ProviderAdmissionKernel(services.events.path)
            services = replace(services, provider_admission=kernel)
            transport = FakeTransport(success_document())
            key_source = CountingKeySource()
            provider = self._provider(kernel, transport, key_source)
            base = delegated_task()
            task = replace(
                base,
                constraints=replace(
                    base.constraints,
                    max_output_tokens=4_096,
                ),
            )
            project = ProjectAdmissionBinding(
                "project-a",
                1,
                "operator_asserted",
            )
            context, reference = self._context_and_reference(
                services,
                task,
                project,
                AdmissionLane.ROUTINE,
            )
            request = ProviderAdmissionRequest(
                request_id=str(uuid.uuid4()),
                provider_id=provider.provider_id,
                project_binding_digest=project.binding_digest,
                lane=AdmissionLane.ROUTINE,
                run_id=context.run_id,
                authorization=reference,
                plane=context.plane.value,
                task_type=task.task_type,
                task_digest=task_contract_digest(task),
                member_digest=task.delegation_approval_sha256,
                batch_id=None,
                provider_tier_binding_digest=(
                    context.provider_tier_binding_digest
                ),
            )
            permit = kernel.try_admit(request, ttl_seconds=60)

            result = MacrRuntime(
                ProviderRegistry((provider,)),
                services,
            ).invoke(
                provider.provider_id,
                task,
                context,
                provider_admission_permit=permit,
                provider_admission_request=request,
            )
            record = kernel.read_request(request.request_id)
            status = kernel.status(provider.provider_id)

        self.assertEqual(result.failure_stage, "token_policy")
        self.assertEqual(record.state, "cancelled")
        self.assertEqual(status.counts["granted"], 0)
        self.assertEqual(key_source.calls, 0)
        self.assertEqual(transport.posts, [])

    def test_no_response_terminal_keeps_capacity_in_reconciliation(self) -> None:
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            kernel = ProviderAdmissionKernel(services.events.path)
            services = replace(services, provider_admission=kernel)
            provider = self._provider(
                kernel,
                NoResponseTransport(success_document()),
                CountingKeySource(),
            )
            task = delegated_task()
            project = ProjectAdmissionBinding(
                "project-a",
                1,
                "operator_asserted",
            )
            context, _ = self._context_and_reference(
                services,
                task,
                project,
                AdmissionLane.BULK,
            )

            result = MacrRuntime(
                ProviderRegistry((provider,)),
                services,
            ).invoke(provider.provider_id, task, context)
            status = kernel.status(provider.provider_id)

        self.assertEqual(result.failure_code, "ProviderUnavailableError")
        self.assertEqual(status.counts["reconciliation_required"], 1)
        self.assertEqual(status.circuit_state, "closed")
        self.assertEqual(status.last_signal, "unknown_after_dispatch_isolated")

    def test_direct_glm_call_without_permit_fails_before_key_or_transport(self) -> None:
        with d_drive_tempdir() as temp:
            kernel = ProviderAdmissionKernel(
                temp / "runtime" / "dispatch.sqlite3"
            )
            transport = FakeTransport(success_document())
            key_source = CountingKeySource()
            provider = self._provider(kernel, transport, key_source)

            with self.assertRaises(ProviderAdmissionRequiredError):
                provider.invoke(delegated_task())

        self.assertEqual(key_source.calls, 0)
        self.assertEqual(transport.posts, [])

    def test_structural_guard_shim_cannot_bypass_shared_kernel(self) -> None:
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            kernel = ProviderAdmissionKernel(services.events.path)
            transport = FakeTransport(success_document())
            key_source = CountingKeySource()
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=transport,
                key_source=key_source,
                approval_store=AllowingApprovalStore(),
                admission_guard=NoOpAdmissionGuard(),
            )
            task = delegated_task()
            project = ProjectAdmissionBinding(
                "project-a",
                1,
                "operator_asserted",
            )
            services = replace(services, provider_admission=kernel)
            context, reference = self._context_and_reference(
                services,
                task,
                project,
                AdmissionLane.ROUTINE,
            )
            request = ProviderAdmissionRequest(
                request_id=str(uuid.uuid4()),
                provider_id=provider.provider_id,
                project_binding_digest=project.binding_digest,
                lane=AdmissionLane.ROUTINE,
                run_id=context.run_id,
                authorization=reference,
                plane=context.plane.value,
                task_type=task.task_type,
                task_digest=task_contract_digest(task),
                member_digest=task.delegation_approval_sha256,
                batch_id=None,
                provider_tier_binding_digest=(
                    context.provider_tier_binding_digest
                ),
            )
            permit = kernel.try_admit(request, ttl_seconds=60)

            with self.assertRaises(ProviderAdmissionRequiredError):
                provider.invoke(
                    task,
                    admission_permit=permit,
                    admission_request=request,
                )
            kernel.cancel_before_transport(permit)

        self.assertEqual(key_source.calls, 0)
        self.assertEqual(transport.posts, [])

    def test_runtime_rejects_provider_bound_to_another_real_kernel(self) -> None:
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            shared = ProviderAdmissionKernel(services.events.path)
            other = ProviderAdmissionKernel(
                temp / "other-runtime" / "dispatch.sqlite3"
            )
            services = replace(services, provider_admission=shared)
            transport = FakeTransport(success_document())
            key_source = CountingKeySource()
            provider = self._provider(other, transport, key_source)
            task = delegated_task()
            project = ProjectAdmissionBinding(
                "project-a",
                1,
                "operator_asserted",
            )
            context, _ = self._context_and_reference(
                services,
                task,
                project,
                AdmissionLane.ROUTINE,
            )

            result = MacrRuntime(
                ProviderRegistry((provider,)),
                services,
            ).invoke(provider.provider_id, task, context)

        self.assertEqual(result.failure_stage, "admission")
        self.assertEqual(key_source.calls, 0)
        self.assertEqual(transport.posts, [])

    def test_direct_adapter_rejects_alternate_concrete_runtime(self) -> None:
        with d_drive_tempdir() as temp:
            alternate = ProviderAdmissionKernel(
                temp / "alternate" / "runtime" / "dispatch.sqlite3"
            )
            transport = FakeTransport(success_document())
            key_source = CountingKeySource()
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=transport,
                environ={
                    "MACR_STATE_ROOT": str(temp / "canonical-state"),
                },
                key_source=key_source,
                approval_store=AllowingApprovalStore(),
                admission_guard=alternate,
            )
            task = delegated_task()
            project = ProjectAdmissionBinding(
                "project-a",
                1,
                "operator_asserted",
            )
            run_id = str(uuid.uuid4())
            reference = alternate.authorities.issue(
                source_kind="operator_test",
                source_id="redirected-concrete-kernel",
                scope=AuthorityScope(
                    providers=(provider.provider_id,),
                    planes=(InteractionPlane.DELEGATION.value,),
                    task_types=(task.task_type,),
                    member_digests=(task.delegation_approval_sha256,),
                    provider_tier_binding_digests=(
                        provider.capability_binding.binding_digest,
                    ),
                    project_binding_digests=(project.binding_digest,),
                    admission_lanes=(AdmissionLane.ROUTINE.value,),
                    provider_admission_policy_digests=(
                        alternate.policy.policy_digest,
                    ),
                    scope_contract_version=3,
                ),
                expires_at=(
                    datetime.now(timezone.utc) + timedelta(minutes=10)
                ).isoformat(),
            )
            request = ProviderAdmissionRequest(
                request_id=str(uuid.uuid4()),
                provider_id=provider.provider_id,
                project_binding_digest=project.binding_digest,
                lane=AdmissionLane.ROUTINE,
                run_id=run_id,
                authorization=reference,
                plane=InteractionPlane.DELEGATION.value,
                task_type=task.task_type,
                task_digest=task_contract_digest(task),
                member_digest=task.delegation_approval_sha256,
                batch_id=None,
                provider_tier_binding_digest=(
                    provider.capability_binding.binding_digest
                ),
            )
            permit = alternate.try_admit(request, ttl_seconds=60)

            with self.assertRaisesRegex(
                ProviderAdmissionRequiredError,
                "canonical runtime",
            ):
                provider.invoke(
                    task,
                    admission_permit=permit,
                    admission_request=request,
                )
            alternate.cancel_before_transport(permit)

        self.assertEqual(key_source.calls, 0)
        self.assertEqual(transport.posts, [])

    def test_transport_binding_refusal_is_known_pre_network(self) -> None:
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            kernel = ProviderAdmissionKernel(services.events.path)
            services = replace(services, provider_admission=kernel)
            transport = FakeTransport(success_document())
            key_source = CountingKeySource()
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=transport,
                environ={
                    "MACR_STATE_ROOT": str(temp / "canonical-state"),
                },
                key_source=key_source,
                approval_store=AllowingApprovalStore(),
                admission_guard=kernel,
            )
            task = delegated_task()
            project = ProjectAdmissionBinding(
                "project-a",
                1,
                "operator_asserted",
            )
            context, _ = self._context_and_reference(
                services,
                task,
                project,
                AdmissionLane.ROUTINE,
            )

            result = MacrRuntime(
                ProviderRegistry((provider,)),
                services,
            ).invoke(provider.provider_id, task, context)
            accounting = services.accounting.read_invocation(context.run_id)
            status = kernel.status(provider.provider_id)

        self.assertEqual(result.failure_code, "ProviderAdmissionRequiredError")
        self.assertEqual(result.failure_stage, "admission")
        self.assertFalse(result.provider_meta["network_attempted"])
        self.assertIsNone(accounting)
        self.assertEqual(status.counts["completed"], 0)
        self.assertEqual(status.counts["reconciliation_required"], 0)
        self.assertEqual(key_source.calls, 0)
        self.assertEqual(transport.posts, [])


if __name__ == "__main__":
    unittest.main()
