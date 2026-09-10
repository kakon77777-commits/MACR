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
    ProviderAdmissionKernel,
    ProviderAdmissionRequest,
    glm_provider_admission_policy,
)
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


class NoResponseTransport(FakeTransport):
    def post_json(self, url, *, headers, payload, timeout_s):
        del url, headers, payload, timeout_s
        raise ProviderUnavailableError(
            "synthetic no response",
            network_attempted=True,
            response_received=False,
            transport_stage="connection",
        )


class ProviderAdmissionRuntimeTests(unittest.TestCase):
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

        self.assertEqual(result.status.value, "candidate_failure")
        self.assertEqual(key_source.calls, 1)
        self.assertEqual(transport.posts, [])
        self.assertEqual(status.counts["completed"], 1)
        self.assertEqual(status.counts["reconciliation_required"], 0)
        self.assertEqual(status.circuit_state, "closed")

    def _context_and_reference(
        self,
        services,
        task,
        project: ProjectAdmissionBinding,
        lane: AdmissionLane,
        *,
        run_id: str | None = None,
    ):
        policy = glm_provider_admission_policy()
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
            kernel = ProviderAdmissionKernel(services.events.path)
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
        self.assertEqual(status.circuit_state, "open")

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


if __name__ == "__main__":
    unittest.main()
