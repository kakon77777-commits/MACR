from __future__ import annotations

import dataclasses
import hashlib
import json
import unittest
from unittest.mock import patch

from macr_runtime.authority import AuthorityScope
from macr_runtime.accounting import CostClass
from macr_runtime.canonical import sha256_id
from macr_runtime.config import AuthMode, ConnectionScope, ProviderConfig
from macr_runtime.contracts import ProviderResult, ResultStatus, TaskContract
from macr_runtime.coordination import PlanExecutionMode
from macr_runtime.errors import DispatchAuthorizationError
from macr_runtime.execution import (
    AcceptanceState,
    DispatchOrigin,
    InteractionPlane,
    ProviderExecution,
    VerificationState,
)
from macr_runtime.plan_runtime import (
    PlanExecutionError,
    PlanRuntime,
    VerificationReport,
)
from macr_runtime.registry import ProviderRegistry
from macr_runtime.provider_admission import (
    AdmissionLane,
    ProjectAdmissionBinding,
    ProviderAdmissionDirectory,
)
from macr_runtime.providers.grok import GrokResponsesProvider
from macr_runtime.route_resolution import ExecutionRouteProposal

from tests.support import build_test_services, d_drive_tempdir
from tests.test_coordination import make_plan
from tests.test_grok_provider import (
    FakeTransport as GrokFakeTransport,
    cloud_task as grok_task,
    grok_config,
    success_document as grok_success_document,
)


def task_digest(task: TaskContract) -> str:
    encoded = json.dumps(
        task.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def task() -> TaskContract:
    return TaskContract(
        task_id="t0-plan-task",
        goal="Return one bounded candidate.",
        task_type="t0_verified_task",
    )


def executable_plan():
    item = task()
    return dataclasses.replace(
        make_plan(),
        task_digest=task_digest(item),
        execution_mode=PlanExecutionMode.EXECUTION_ELIGIBLE,
    )


def proposal(plan) -> ExecutionRouteProposal:
    canonical = {
        "route_id": plan.bindings[0].route_id,
        "route_snapshot_id": plan.route_snapshot_id,
        "policy_snapshot_id": plan.policy_snapshot_ids[0],
        "provider_id": "fake_provider",
        "provider_kind": "test_provider",
        "provider_model_id": "fake-model",
        "connection_scope": "external_https",
        "endpoint_identity": "https://example.invalid/v1",
        "parameter_profile_digest": (
            plan.bindings[0].parameter_profile_digest
        ),
        "prompt_compiler_version": "worker-v1",
        "data_policy_snapshot_id": plan.policy_snapshot_ids[0],
        "resolution_state": "proposal_only",
        "authority_issued": False,
        "network_activity": False,
    }
    return ExecutionRouteProposal(
        proposal_digest=sha256_id(
            "execution_route_proposal_v1",
            canonical,
        ),
        **canonical,
    )


def grok_proposal(plan) -> ExecutionRouteProposal:
    canonical = {
        "route_id": plan.bindings[0].route_id,
        "route_snapshot_id": plan.route_snapshot_id,
        "policy_snapshot_id": plan.policy_snapshot_ids[0],
        "provider_id": "grok",
        "provider_kind": "grok_responses",
        "provider_model_id": "grok-4.6",
        "connection_scope": "external_https",
        "endpoint_identity": "https://api.x.ai/v1",
        "parameter_profile_digest": (
            plan.bindings[0].parameter_profile_digest
        ),
        "prompt_compiler_version": "worker-v1",
        "data_policy_snapshot_id": plan.policy_snapshot_ids[0],
        "resolution_state": "proposal_only",
        "authority_issued": False,
        "network_activity": False,
    }
    return ExecutionRouteProposal(
        proposal_digest=sha256_id(
            "execution_route_proposal_v1",
            canonical,
        ),
        **canonical,
    )


class FakeProvider:
    provider_id = "fake_provider"
    connection_scope = ConnectionScope.EXTERNAL_HTTPS

    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail
        self.config = ProviderConfig(
            id=self.provider_id,
            kind="test_provider",
            enabled=True,
            auth_mode=AuthMode.API_KEY_FILE,
            api_usage_allowed=True,
            connection_scope=ConnectionScope.EXTERNAL_HTTPS,
            api_key_file=r"D:\KEY\TEST.txt",
            base_url="https://example.invalid/v1",
            model="fake-model",
            endpoint_path="/invoke",
            allowed_hosts=("example.invalid",),
            capabilities=("text_generation",),
        )

    def invoke_observed(self, contract: TaskContract) -> ProviderExecution:
        self.calls += 1
        if self.fail:
            raise RuntimeError("injected provider failure")
        result = ProviderResult(
            task_id=contract.task_id,
            status=ResultStatus.CANDIDATE_SUCCESS,
            answer="MACR_T0_OK",
            cost={
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "reasoning_tokens": 0,
                    "cached_tokens": 0,
                },
                "currency_cost_usd": 0.001,
                "cost_kind": "estimated",
                "pricing_basis_version": "test-v1",
            },
            provider_meta={
                "model": "fake-model",
                "response_id": "fake-response",
                "finish_reason": "stop",
                "metrics": {"duration_ms": 10},
            },
        )
        return ProviderExecution.from_result(self.provider_id, result)


class StaticVerifier:
    def __init__(self, state: VerificationState) -> None:
        self.state = state
        self.calls = 0

    def verify(self, graph, candidate_bytes, *, plan, contract):
        self.calls += 1
        evidence = hashlib.sha256(
            graph.graph_digest.encode("ascii") + candidate_bytes
        ).hexdigest()
        return VerificationReport(
            graph_digest=graph.graph_digest,
            state=self.state,
            evidence_digest=evidence,
            node_result_digests=(evidence,),
            bounded_diagnostics=(
                "all_controls_passed"
                if self.state is VerificationState.PASSED
                else "injected_verifier_failure",
            ),
        )


def issue_authority(services, plan, *, member_digest: str | None = None):
    return services.authorities.issue(
        source_kind="test_host",
        source_id="t0-execution",
        scope=AuthorityScope(
            providers=("fake_provider",),
            planes=(InteractionPlane.DELEGATION.value,),
            task_types=("t0_verified_task",),
            member_digests=(member_digest or plan.plan_digest,),
        ),
        expires_at="2099-01-01T00:00:00+00:00",
    )


ORIGIN = DispatchOrigin("test-host", "test_case", "plan-runtime")


class PlanRuntimeTests(unittest.TestCase):
    def test_grok_plan_execution_binds_shared_provider_admission(self) -> None:
        contract = grok_task(max_output_tokens=65_536)
        plan = dataclasses.replace(
            make_plan(),
            task_digest=task_digest(contract),
            execution_mode=PlanExecutionMode.EXECUTION_ELIGIBLE,
        )
        project = ProjectAdmissionBinding(
            "grok-plan-project",
            1,
            "operator_enrolled",
        )
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            directory = ProviderAdmissionDirectory.offline_test(
                services.events.path
            )
            services = dataclasses.replace(
                services,
                provider_admission=directory.get("glm_flash_worker"),
                provider_admissions=directory,
            )
            kernel = directory.get("grok")
            transport = GrokFakeTransport(
                grok_success_document("grok-4.6")
            )
            provider = GrokResponsesProvider(
                grok_config("grok", "grok-4.6", "high"),
                transport=transport,
                environ={"XAI_API_KEY": "test-key"},
                admission_guard=kernel,
                offline_test_transport=True,
            )
            authority = services.authorities.issue(
                source_kind="test_host",
                source_id="grok-plan-execution",
                scope=AuthorityScope(
                    providers=("grok",),
                    planes=(InteractionPlane.DELEGATION.value,),
                    task_types=(contract.task_type,),
                    member_digests=(plan.plan_digest,),
                    project_binding_digests=(project.binding_digest,),
                    admission_lanes=(AdmissionLane.ROUTINE.value,),
                    provider_admission_policy_digests=(
                        kernel.policy.policy_digest,
                    ),
                    scope_contract_version=3,
                ),
                expires_at="2099-01-01T00:00:00+00:00",
            )
            runtime = PlanRuntime(
                ProviderRegistry((provider,)),
                services,
                StaticVerifier(VerificationState.PASSED),
            )

            result = runtime.execute(
                plan,
                contract,
                grok_proposal(plan),
                authority,
                ORIGIN,
                admission_project=project,
                admission_lane=AdmissionLane.ROUTINE,
            )
            events = services.events.read_events(run_id=result.run_id)
            status = kernel.status("grok")
            with self.assertRaisesRegex(
                PlanExecutionError,
                "operator-bound admission",
            ):
                runtime.execute(
                    plan,
                    contract,
                    grok_proposal(plan),
                    authority,
                    ORIGIN,
                )

        self.assertEqual(result.provider_status, "candidate_success")
        self.assertEqual(len(transport.posts), 1)
        self.assertEqual(status.counts["completed"], 1)
        self.assertEqual(
            events[0]["payload"]["project_binding_digest"],
            project.binding_digest,
        )
        self.assertEqual(
            events[0]["payload"]["provider_admission_policy_digest"],
            kernel.policy.policy_digest,
        )

    def test_t0_requires_exact_plan_digest_authority_before_provider(self) -> None:
        plan = executable_plan()
        provider = FakeProvider()
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            stale = issue_authority(services, plan, member_digest="f" * 64)
            runtime = PlanRuntime(
                ProviderRegistry((provider,)),
                services,
                StaticVerifier(VerificationState.PASSED),
            )
            with self.assertRaisesRegex(
                DispatchAuthorizationError,
                "scope|plan digest",
            ):
                runtime.execute(
                    plan,
                    task(),
                    proposal(plan),
                    stale,
                    ORIGIN,
                )
            events = services.events.read_events()

        self.assertEqual(provider.calls, 0)
        self.assertEqual(events, ())

    def test_t0_candidate_verification_and_acceptance_are_separate(self) -> None:
        plan = executable_plan()
        provider = FakeProvider()
        verifier = StaticVerifier(VerificationState.PASSED)
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            authority = issue_authority(services, plan)
            result = PlanRuntime(
                ProviderRegistry((provider,)),
                services,
                verifier,
            ).execute(
                plan,
                task(),
                proposal(plan),
                authority,
                ORIGIN,
            )
            events = services.events.read_events(run_id=result.run_id)
            capture = services.vault.read_by_run(result.run_id)
            plan_costs = services.accounting.plan_costs(plan.plan_digest)

        self.assertEqual(provider.calls, 1)
        self.assertEqual(verifier.calls, 1)
        self.assertEqual(result.provider_state, "completed")
        self.assertEqual(result.capture_state, "captured")
        self.assertEqual(result.return_contract_state, "valid")
        self.assertIs(result.verification_state, VerificationState.PASSED)
        self.assertIs(result.acceptance_state, AcceptanceState.PENDING)
        self.assertEqual(result.persistence_state, "complete")
        self.assertIsNotNone(capture)
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0]["payload"]["plan_digest"], plan.plan_digest)
        self.assertEqual(events[-1]["event_type"], "plan.verification_completed")
        self.assertEqual(
            plan_costs[CostClass.PRODUCTION_EXECUTION_COST.value],
            0.001,
        )
        self.assertEqual(
            plan_costs[CostClass.VERIFICATION_COST.value],
            0.0,
        )

    def test_verifier_failure_does_not_rewrite_provider_or_acceptance_state(self) -> None:
        plan = executable_plan()
        provider = FakeProvider()
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            result = PlanRuntime(
                ProviderRegistry((provider,)),
                services,
                StaticVerifier(VerificationState.FAILED),
            ).execute(
                plan,
                task(),
                proposal(plan),
                issue_authority(services, plan),
                ORIGIN,
            )

        self.assertEqual(result.provider_state, "completed")
        self.assertIs(result.verification_state, VerificationState.FAILED)
        self.assertIs(result.acceptance_state, AcceptanceState.PENDING)

    def test_shadow_plan_task_mismatch_and_provider_failure_fail_closed_without_retry(self) -> None:
        executable = executable_plan()
        provider = FakeProvider(fail=True)
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            runtime = PlanRuntime(
                ProviderRegistry((provider,)),
                services,
                StaticVerifier(VerificationState.PASSED),
            )
            with self.assertRaisesRegex(PlanExecutionError, "shadow"):
                runtime.execute(
                    make_plan(),
                    task(),
                    proposal(make_plan()),
                    issue_authority(services, executable),
                    ORIGIN,
                )
            with self.assertRaisesRegex(PlanExecutionError, "task digest"):
                runtime.execute(
                    dataclasses.replace(executable, task_digest="e" * 64),
                    task(),
                    proposal(executable),
                    issue_authority(services, executable),
                    ORIGIN,
                )
            result = runtime.execute(
                executable,
                task(),
                proposal(executable),
                issue_authority(services, executable),
                ORIGIN,
            )

        self.assertEqual(provider.calls, 1)
        self.assertEqual(result.provider_state, "malformed")
        self.assertIs(result.verification_state, VerificationState.NOT_RUN)
        self.assertIs(result.acceptance_state, AcceptanceState.PENDING)

    def test_post_provider_persistence_failure_is_distinct_and_never_retried(self) -> None:
        plan = executable_plan()
        provider = FakeProvider()
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            runtime = PlanRuntime(
                ProviderRegistry((provider,)),
                services,
                StaticVerifier(VerificationState.PASSED),
            )
            with patch.object(
                services.events,
                "finish_run",
                side_effect=RuntimeError("injected terminal persistence failure"),
            ):
                result = runtime.execute(
                    plan,
                    task(),
                    proposal(plan),
                    issue_authority(services, plan),
                    ORIGIN,
                )

        self.assertEqual(provider.calls, 1)
        self.assertEqual(result.provider_state, "unknown_after_dispatch")
        self.assertEqual(result.persistence_state, "failed")
        self.assertEqual(result.failure_type, "RuntimeError")
        self.assertIs(result.verification_state, VerificationState.NOT_RUN)
        self.assertIs(result.acceptance_state, AcceptanceState.PENDING)


if __name__ == "__main__":
    unittest.main()
