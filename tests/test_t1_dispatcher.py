from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from datetime import timedelta

from macr_runtime.authority import AuthorityScope, DispatchAuthorityStore
from macr_runtime.event_store import SqliteEventStore
from macr_runtime.errors import (
    DispatchAuthorizationError,
    ProviderAdmissionBusyError,
    ProviderUnavailableError,
)
from macr_runtime.execution import DispatchOrigin, InteractionPlane
from macr_runtime.providers.glm import GlmFlashWorkerProvider
from macr_runtime.provider_capability import (
    glm_extended_text_policy,
    glm_standard_policy,
)
from macr_runtime.provider_capability_store import (
    ProviderCapabilityGovernance,
    ProviderCapabilityPolicyStore,
)
from macr_runtime.provider_admission import (
    AdmissionLane,
    ProviderAdmissionKernel,
    ProviderAdmissionRequest,
)
from macr_runtime.registry import ProviderRegistry
from macr_runtime.runtime import task_contract_digest
from macr_runtime.scheduler import PlanQueue, QueueMemberState
from macr_runtime.t1_dispatcher import T1DispatchError, T1Dispatcher
from macr_runtime.t1_manifest import T1ExecutionManifest, T1ExecutionMember
from macr_runtime.token_policy import t1_glm_live_policy
from tests.support import build_test_services, d_drive_tempdir
from tests.test_glm_provider import (
    AllowingApprovalStore,
    FakeTransport,
    StaticKeySource,
    glm_config,
    success_document,
)
from tests.test_scheduler import Clock
from tests.test_t1_manifest import manifest as unapproved_manifest


def t1_services(state_root, clock):
    services = build_test_services(state_root)
    return replace(
        services,
        provider_admission=ProviderAdmissionKernel(
            services.events.path,
            now=clock,
        ),
    )


def approved_manifest(
    provider: GlmFlashWorkerProvider,
    *,
    member_count: int = 3,
    worker_count: int = 3,
) -> T1ExecutionManifest:
    source = unapproved_manifest(
        member_count=member_count,
        worker_count=worker_count,
    )
    members = []
    for original in source.members:
        unsigned = replace(original.task, delegation_approval_sha256=None)
        approval = provider.approval_metadata(unsigned)["required_approval_sha256"]
        task = replace(unsigned, delegation_approval_sha256=approval)
        members.append(
            T1ExecutionMember.create(
                plan_digest=source.plan_digest,
                ordinal=original.ordinal,
                task=task,
                route=original.route,
                token_policy_digest=original.token_policy_digest,
                provider_tier_binding_digest=(
                    provider.capability_binding.binding_digest
                ),
                role_digest=original.role_digest,
                privacy=original.privacy,
                context_class=original.context_class,
                cost_ceiling_usd=original.cost_ceiling_usd,
                target_claims=original.target_claims,
            )
        )
    return T1ExecutionManifest.create(
        plan_digest=source.plan_digest,
        members=tuple(members),
        worker_count=source.worker_count,
        aggregate_cost_ceiling_usd=source.aggregate_cost_ceiling_usd,
        campaign_cost_ceiling_usd=source.campaign_cost_ceiling_usd,
        expires_at=source.expires_at,
        authorized_dispatchers=source.authorized_dispatchers,
    )


def replan_manifest(
    source: T1ExecutionManifest,
    plan_digest: str,
) -> T1ExecutionManifest:
    members = tuple(
        T1ExecutionMember.create(
            plan_digest=plan_digest,
            ordinal=item.ordinal,
            task=item.task,
            route=item.route,
            token_policy_digest=item.token_policy_digest,
            provider_tier_binding_digest=item.provider_tier_binding_digest,
            role_digest=item.role_digest,
            privacy=item.privacy,
            context_class=item.context_class,
            cost_ceiling_usd=item.cost_ceiling_usd,
            target_claims=item.target_claims,
        )
        for item in source.members
    )
    return T1ExecutionManifest.create(
        plan_digest=plan_digest,
        plan_revision=source.plan_revision + 1,
        members=members,
        worker_count=source.worker_count,
        aggregate_cost_ceiling_usd=source.aggregate_cost_ceiling_usd,
        campaign_cost_ceiling_usd=source.campaign_cost_ceiling_usd,
        expires_at=source.expires_at,
        authorized_dispatchers=source.authorized_dispatchers,
    )


class FailingQueue(PlanQueue):
    def enqueue(self, plan):
        del plan
        raise RuntimeError("synthetic staging failure")


class DriftingTokenPolicyRegistry(ProviderRegistry):
    def __init__(self, providers):
        super().__init__(providers)
        self.drifted = False

    def token_policy(self, provider_id, *, store=None):
        policy = super().token_policy(provider_id, store=store)
        if not self.drifted:
            return policy
        return replace(
            policy,
            default_output_tokens=32_768,
            max_output_tokens=32_768,
        )


class DriftOnClaimQueue(PlanQueue):
    def __init__(self, path, registry, *, now):
        super().__init__(path, now=now)
        self.registry = registry

    def claim(self, *args, **kwargs):
        claim = super().claim(*args, **kwargs)
        self.registry.drifted = True
        return claim


class FailingFinishEventStore(SqliteEventStore):
    def finish_run(self, **kwargs):
        del kwargs
        raise RuntimeError("synthetic terminal persistence failure")


class NoResponseTransport(FakeTransport):
    def post_json(self, url, *, headers, payload, timeout_s):
        del url, headers, payload, timeout_s
        raise ProviderUnavailableError(
            "synthetic no response",
            network_attempted=True,
            response_received=False,
            transport_stage="connection",
        )


class T1DispatcherTests(unittest.TestCase):
    def test_unknown_cost_remains_null_in_t1_reconciliation(self) -> None:
        now = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as state_root:
            services = t1_services(state_root, clock)
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=NoResponseTransport(success_document()),
                environ={"MACR_STATE_ROOT": str(state_root)},
                key_source=StaticKeySource(),
                approval_store=AllowingApprovalStore(),
                token_policy=t1_glm_live_policy(),
                admission_guard=services.provider_admission,
            )
            dispatcher = T1Dispatcher(
                ProviderRegistry((provider,)),
                services,
                now=clock,
            )
            subject = approved_manifest(provider)
            bundle = dispatcher.stage(
                subject,
                subject.authorized_dispatchers,
                subject.expires_at,
            )

            result = dispatcher.run_one(
                subject,
                bundle,
                subject.authorized_dispatchers[0],
                DispatchOrigin("test", "process_id", "1234"),
                allow_network=True,
                allow_local=False,
            )
            record = dispatcher.queue.read_member(result.member_id)

        self.assertTrue(result.reconciliation_required)
        self.assertEqual(record.state.value, "reconciliation_required")
        self.assertIsNone(record.observed_cost_usd)

    def test_provider_busy_leaves_t1_member_queued_without_attempt(self) -> None:
        now = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as state_root:
            services = t1_services(state_root, clock)
            transport = FakeTransport(success_document())
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=transport,
                environ={"MACR_STATE_ROOT": str(state_root)},
                key_source=StaticKeySource(),
                approval_store=AllowingApprovalStore(),
                token_policy=t1_glm_live_policy(),
                admission_guard=services.provider_admission,
            )
            dispatcher = T1Dispatcher(
                ProviderRegistry((provider,)),
                services,
                now=clock,
            )
            subject = approved_manifest(provider)
            bundle = dispatcher.stage(
                subject,
                subject.authorized_dispatchers,
                subject.expires_at,
            )
            member = subject.members[0]
            held_request = ProviderAdmissionRequest(
                request_id=str(uuid.uuid4()),
                provider_id=provider.provider_id,
                project_binding_digest=bundle.project_binding_digest,
                lane=AdmissionLane(bundle.admission_lane),
                run_id=str(uuid.uuid4()),
                authorization=bundle.dispatch_authority,
                plane=InteractionPlane.DELEGATION.value,
                task_type=member.task.task_type,
                task_digest=task_contract_digest(member.task),
                member_digest=member.member_digest,
                batch_id=subject.manifest_digest,
                provider_tier_binding_digest=(
                    member.provider_tier_binding_digest
                ),
            )
            held = services.provider_admission.try_admit(
                held_request,
                ttl_seconds=60,
            )

            with self.assertRaises(ProviderAdmissionBusyError):
                dispatcher.run_one(
                    subject,
                    bundle,
                    subject.authorized_dispatchers[0],
                    DispatchOrigin("test", "process_id", "1234"),
                    allow_network=True,
                    allow_local=False,
                )
            records = dispatcher.queue.list_members(subject.plan_digest)
            services.provider_admission.cancel_before_transport(held)

        self.assertEqual(
            [(item.state.value, item.attempts) for item in records],
            [("queued", 0)] * len(subject.members),
        )
        self.assertEqual(transport.posts, [])

    def test_pre_dispatch_runtime_refusal_requeues_member_without_attempt(self) -> None:
        now = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as state_root:
            services = t1_services(state_root, clock)
            transport = FakeTransport(success_document())
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=transport,
                environ={"MACR_STATE_ROOT": str(state_root)},
                key_source=StaticKeySource(),
                approval_store=AllowingApprovalStore(),
                token_policy=t1_glm_live_policy(),
                admission_guard=services.provider_admission,
            )
            registry = DriftingTokenPolicyRegistry((provider,))
            queue = DriftOnClaimQueue(
                services.events.path,
                registry,
                now=clock,
            )
            dispatcher = T1Dispatcher(
                registry,
                services,
                queue=queue,
                now=clock,
            )
            subject = approved_manifest(provider)
            bundle = dispatcher.stage(
                subject,
                subject.authorized_dispatchers,
                subject.expires_at,
            )

            result = dispatcher.run_one(
                subject,
                bundle,
                subject.authorized_dispatchers[0],
                DispatchOrigin("test", "process_id", "1234"),
                allow_network=True,
                allow_local=False,
            )
            record = dispatcher.queue.read_member(result.member_id)
            admission = services.provider_admission.status(
                provider.provider_id
            )

        self.assertEqual(result.queue_state, "queued")
        self.assertFalse(result.provider_attempted)
        self.assertEqual((record.state.value, record.attempts), ("queued", 0))
        self.assertEqual(admission.counts["granted"], 0)
        self.assertEqual(transport.posts, [])

    def test_stage_rechecks_active_head_after_registry_construction(self) -> None:
        now = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as state_root:
            services = t1_services(state_root, clock)
            store = ProviderCapabilityPolicyStore(
                state_root / "settings" / "provider-capability-policies.sqlite3"
            )
            services = replace(services, capability_policies=store)
            authorities = DispatchAuthorityStore(services.events.path, now=clock)
            governance = ProviderCapabilityGovernance(store, authorities)
            for ordinal, policy in enumerate(
                (glm_extended_text_policy(), glm_standard_policy()),
                start=1,
            ):
                store.save_policy(policy)
                binding = policy.binding()
                reference = authorities.issue(
                    source_kind="operator_policy_authority",
                    source_id=f"tier-switch-{ordinal}",
                    scope=AuthorityScope(
                        providers=(binding.provider_id,),
                        planes=("policy_activation",),
                        task_types=("provider_tier_activation",),
                        provider_tier_binding_digests=(binding.binding_digest,),
                    ),
                    expires_at=(now + timedelta(minutes=5)).isoformat(),
                )
                governance.activate(binding.binding_digest, reference)
                if policy.tier_id == "extended_text_candidate":
                    provider = GlmFlashWorkerProvider(
                        glm_config(),
                        transport=FakeTransport(success_document()),
                        environ={"MACR_STATE_ROOT": str(state_root)},
                        key_source=StaticKeySource(),
                        approval_store=AllowingApprovalStore(),
                        token_policy=t1_glm_live_policy(),
                        capability_policy=policy,
                        admission_guard=services.provider_admission,
                    )
                    subject = approved_manifest(provider)
            dispatcher = T1Dispatcher(
                ProviderRegistry((provider,)),
                services,
                now=clock,
            )

            with self.assertRaisesRegex(T1DispatchError, "active.*capability"):
                dispatcher.stage(
                    subject,
                    subject.authorized_dispatchers,
                    subject.expires_at,
                )
            connection = services.events.database.connect()
            try:
                counts = tuple(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in (
                        "batch_authorities",
                        "plan_queue_batches",
                    )
                )
            finally:
                connection.close()

        self.assertEqual(counts, (0, 0))

    def test_mismatched_provider_tier_fails_before_authority_or_queue_write(self) -> None:
        now = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as state_root:
            services = t1_services(state_root, clock)
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=FakeTransport(success_document()),
                environ={"MACR_STATE_ROOT": str(state_root)},
                key_source=StaticKeySource(),
                approval_store=AllowingApprovalStore(),
                token_policy=t1_glm_live_policy(),
                admission_guard=services.provider_admission,
            )
            dispatcher = T1Dispatcher(
                ProviderRegistry((provider,)),
                services,
                now=clock,
            )
            source = approved_manifest(provider)
            wrong_members = tuple(
                T1ExecutionMember.create(
                    plan_digest=source.plan_digest,
                    ordinal=item.ordinal,
                    task=item.task,
                    route=item.route,
                    token_policy_digest=item.token_policy_digest,
                    provider_tier_binding_digest="b" * 64,
                    role_digest=item.role_digest,
                    privacy=item.privacy,
                    context_class=item.context_class,
                    cost_ceiling_usd=item.cost_ceiling_usd,
                    target_claims=item.target_claims,
                )
                for item in source.members
            )
            attacked = T1ExecutionManifest.create(
                plan_digest=source.plan_digest,
                members=wrong_members,
                worker_count=source.worker_count,
                aggregate_cost_ceiling_usd=source.aggregate_cost_ceiling_usd,
                campaign_cost_ceiling_usd=source.campaign_cost_ceiling_usd,
                expires_at=source.expires_at,
                authorized_dispatchers=source.authorized_dispatchers,
            )

            with self.assertRaisesRegex(T1DispatchError, "capability binding"):
                dispatcher.stage(
                    attacked,
                    attacked.authorized_dispatchers,
                    attacked.expires_at,
                )
            connection = services.events.database.connect()
            try:
                counts = tuple(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in (
                        "batch_authorities",
                        "dispatch_authorities",
                        "plan_queue_batches",
                    )
                )
            finally:
                connection.close()

        self.assertEqual(counts, (0, 0, 0))

    def test_worker_claims_one_member_and_uses_complete_runtime_path_once(self) -> None:
        now = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as state_root:
            services = t1_services(state_root, clock)
            transport = FakeTransport(success_document())
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=transport,
                environ={"MACR_STATE_ROOT": str(state_root)},
                key_source=StaticKeySource(),
                approval_store=AllowingApprovalStore(),
                token_policy=t1_glm_live_policy(),
                admission_guard=services.provider_admission,
            )
            dispatcher = T1Dispatcher(
                ProviderRegistry((provider,)),
                services,
                now=clock,
            )
            subject = approved_manifest(provider)
            bundle = dispatcher.stage(
                subject,
                subject.authorized_dispatchers,
                subject.expires_at,
            )

            result = dispatcher.run_one(
                subject,
                bundle,
                "worker-1",
                DispatchOrigin("test", "process_id", "1234"),
                allow_network=True,
                allow_local=False,
            )
            queue_record = dispatcher.queue.read_member(result.member_id)
            events = services.events.read_events(run_id=result.run_id)
            capture = services.vault.read_by_run(result.run_id)
            accounting = services.accounting.read_invocation(result.run_id)
            plan_costs = services.accounting.plan_costs(subject.plan_digest)
            connection = services.events.database.connect()
            try:
                materializations = connection.execute(
                    "SELECT COUNT(*) FROM materializations"
                ).fetchone()[0]
            finally:
                connection.close()
            public_databases = (
                services.events.path.read_bytes()
                + services.accounting.path.read_bytes()
            )

        self.assertEqual(result.queue_state, "completed")
        self.assertEqual(result.acceptance_state, "pending")
        self.assertEqual(queue_record.state.value, "completed")
        self.assertEqual(
            queue_record.provider_tier_binding_digest,
            subject.members[0].provider_tier_binding_digest,
        )
        self.assertEqual(len(transport.posts), 1)
        self.assertEqual(
            [item["event_type"] for item in events],
            ["provider.dispatch_requested", "provider.candidate_completed"],
        )
        self.assertIsNotNone(capture)
        self.assertIsNotNone(accounting)
        self.assertIsNotNone(accounting["terminal_at"])
        self.assertEqual(set(plan_costs), {"production_execution_cost"})
        self.assertEqual(materializations, 0)
        self.assertNotIn(subject.members[0].task.goal.encode(), public_databases)
        self.assertNotIn(b"candidate answer", public_databases)
        self.assertEqual(
            events[0]["payload"]["model_token_policy_digest"],
            subject.members[0].token_policy_digest,
        )
        self.assertEqual(
            events[0]["payload"]["member_digest"],
            subject.members[0].member_digest,
        )
        self.assertEqual(
            events[0]["payload"]["provider_tier_binding_digest"],
            subject.members[0].provider_tier_binding_digest,
        )

    def test_four_worker_slots_can_drain_five_members_without_retry(self) -> None:
        now = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as state_root:
            services = t1_services(state_root, clock)
            transport = FakeTransport(success_document())
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=transport,
                environ={"MACR_STATE_ROOT": str(state_root)},
                key_source=StaticKeySource(),
                approval_store=AllowingApprovalStore(),
                token_policy=t1_glm_live_policy(),
                admission_guard=services.provider_admission,
            )
            dispatcher = T1Dispatcher(
                ProviderRegistry((provider,)),
                services,
                now=clock,
            )
            subject = approved_manifest(
                provider,
                member_count=5,
                worker_count=4,
            )
            bundle = dispatcher.stage(
                subject,
                subject.authorized_dispatchers,
                subject.expires_at,
            )

            results = tuple(
                dispatcher.run_one(
                    subject,
                    bundle,
                    subject.authorized_dispatchers[index % subject.worker_count],
                    DispatchOrigin("test", "process_id", str(2_000 + index)),
                    allow_network=True,
                    allow_local=False,
                )
                for index in range(len(subject.members))
            )
            counts = dispatcher.queue.state_counts()

        self.assertEqual(bundle.worker_count, 4)
        self.assertEqual(len(bundle.member_ids), 5)
        self.assertEqual([item.queue_state for item in results], ["completed"] * 5)
        self.assertEqual(counts["completed"], 5)
        self.assertEqual(counts["queued"], 0)
        self.assertEqual(len(transport.posts), 5)

    def test_unknown_after_dispatch_requires_global_reconciliation_and_blocks_next(self) -> None:
        now = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as state_root:
            services = t1_services(state_root, clock)
            transport = FakeTransport(success_document())
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=transport,
                environ={"MACR_STATE_ROOT": str(state_root)},
                key_source=StaticKeySource(),
                approval_store=AllowingApprovalStore(),
                token_policy=t1_glm_live_policy(),
                admission_guard=services.provider_admission,
            )
            services = replace(
                services,
                events=FailingFinishEventStore(services.events.path),
            )
            dispatcher = T1Dispatcher(
                ProviderRegistry((provider,)),
                services,
                now=clock,
            )
            subject = approved_manifest(provider)
            bundle = dispatcher.stage(
                subject,
                subject.authorized_dispatchers,
                subject.expires_at,
            )

            result = dispatcher.run_one(
                subject,
                bundle,
                "worker-1",
                DispatchOrigin("test", "process_id", "1234"),
                allow_network=True,
                allow_local=False,
            )
            with self.assertRaisesRegex(T1DispatchError, "reconciliation"):
                dispatcher.run_one(
                    subject,
                    bundle,
                    "worker-2",
                    DispatchOrigin("test", "process_id", "5678"),
                    allow_network=True,
                    allow_local=False,
                )
            counts = dispatcher.queue.state_counts()
            dispatcher.queue.resolve_reconciliation(
                result.member_id,
                terminal_state=QueueMemberState.FAILED,
                reconciliation_evidence_digest="e" * 64,
                observed_cost_usd=result.observed_cost_usd or 0.0,
            )
            connection = services.events.database.connect()
            try:
                admission_request_id = connection.execute(
                    """SELECT request_id FROM provider_admission_requests
                    WHERE run_id=?""",
                    (result.run_id,),
                ).fetchone()[0]
            finally:
                connection.close()
            admission_reference = dispatcher.dispatch_authorities.issue(
                source_kind="operator_admission_reconciliation",
                source_id=result.run_id,
                scope=AuthorityScope(
                    providers=(provider.provider_id,),
                    planes=("provider_admission_reconciliation",),
                    task_types=("provider_admission_resolution",),
                    member_digests=(result.member_digest,),
                    provider_tier_binding_digests=(
                        provider.capability_binding.binding_digest,
                    ),
                    project_binding_digests=(
                        bundle.project_binding_digest,
                    ),
                    admission_lanes=(bundle.admission_lane,),
                    provider_admission_policy_digests=(
                        bundle.provider_admission_policy_digest,
                    ),
                    scope_contract_version=3,
                ),
                expires_at=(now + timedelta(minutes=5)).isoformat(),
            )
            services.provider_admission.resolve_reconciliation(
                admission_request_id,
                admission_reference,
                resolution_evidence_digest="f" * 64,
            )
            with self.assertRaisesRegex(DispatchAuthorizationError, "revoked"):
                dispatcher.run_one(
                    subject,
                    bundle,
                    "worker-2",
                    DispatchOrigin("test", "process_id", "5678"),
                    allow_network=True,
                    allow_local=False,
                )
            recovered_services = replace(
                services,
                events=SqliteEventStore(services.events.path),
            )
            recovered = T1Dispatcher(
                ProviderRegistry((provider,)),
                recovered_services,
                now=clock,
            )
            new_subject = replan_manifest(subject, "b" * 64)
            new_bundle = recovered.stage(
                new_subject,
                new_subject.authorized_dispatchers,
                new_subject.expires_at,
            )
            resumed = recovered.run_one(
                new_subject,
                new_bundle,
                "worker-2",
                DispatchOrigin("test", "process_id", "5678"),
                allow_network=True,
                allow_local=False,
            )

        self.assertEqual(result.queue_state, "reconciliation_required")
        self.assertEqual(result.provider_state, "unknown_after_dispatch")
        self.assertEqual(counts["reconciliation_required"], 1)
        self.assertEqual(counts["queued"], 2)
        self.assertEqual(resumed.queue_state, "completed")
        self.assertEqual(len(transport.posts), 2)

    def test_stale_task_approval_refuses_before_any_authority_or_queue_write(self) -> None:
        now = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as state_root:
            services = t1_services(state_root, clock)
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=FakeTransport(success_document()),
                environ={"MACR_STATE_ROOT": str(state_root)},
                key_source=StaticKeySource(),
                approval_store=AllowingApprovalStore(),
                token_policy=t1_glm_live_policy(),
                admission_guard=services.provider_admission,
            )
            dispatcher = T1Dispatcher(
                ProviderRegistry((provider,)),
                services,
                now=clock,
            )
            source = approved_manifest(provider)
            changed_task = replace(source.members[0].task, goal="Changed after approval")
            changed_member = T1ExecutionMember.create(
                plan_digest=source.plan_digest,
                ordinal=0,
                task=changed_task,
                route=source.members[0].route,
                token_policy_digest=source.members[0].token_policy_digest,
                provider_tier_binding_digest=(
                    source.members[0].provider_tier_binding_digest
                ),
                role_digest=source.members[0].role_digest,
                privacy=source.members[0].privacy,
                context_class=source.members[0].context_class,
                cost_ceiling_usd=source.members[0].cost_ceiling_usd,
                target_claims=source.members[0].target_claims,
            )
            changed = T1ExecutionManifest.create(
                plan_digest=source.plan_digest,
                members=(changed_member, *source.members[1:]),
                worker_count=source.worker_count,
                aggregate_cost_ceiling_usd=source.aggregate_cost_ceiling_usd,
                campaign_cost_ceiling_usd=source.campaign_cost_ceiling_usd,
                expires_at=source.expires_at,
                authorized_dispatchers=source.authorized_dispatchers,
            )

            with self.assertRaisesRegex(T1DispatchError, "approval|stale"):
                dispatcher.stage(
                    changed,
                    changed.authorized_dispatchers,
                    changed.expires_at,
                )

            connection = services.events.database.connect()
            try:
                counts = tuple(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in (
                        "batch_authorities",
                        "dispatch_authorities",
                        "plan_queue_batches",
                    )
                )
            finally:
                connection.close()

        self.assertEqual(counts, (0, 0, 0))

    def test_stage_issues_exact_dual_authority_and_enqueues_without_provider(self) -> None:
        now = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as state_root:
            services = t1_services(state_root, clock)
            transport = FakeTransport(success_document())
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=transport,
                environ={"MACR_STATE_ROOT": str(state_root)},
                key_source=StaticKeySource(),
                approval_store=AllowingApprovalStore(),
                token_policy=t1_glm_live_policy(),
                admission_guard=services.provider_admission,
            )
            dispatcher = T1Dispatcher(
                ProviderRegistry((provider,)),
                services,
                now=clock,
            )
            subject = approved_manifest(provider)

            bundle = dispatcher.stage(
                subject,
                subject.authorized_dispatchers,
                subject.expires_at,
            )
            repeated = dispatcher.stage(
                subject,
                subject.authorized_dispatchers,
                subject.expires_at,
            )
            queue = PlanQueue(services.events.path, now=clock)
            batch_scope = queue.authorities.scope(bundle.batch_authority)

            self.assertEqual(bundle, repeated)
            self.assertEqual(queue.state_counts()["queued"], 3)
            self.assertEqual(
                batch_scope.member_digests,
                tuple(item.member_digest for item in subject.members),
            )
            for item in subject.members:
                services.authorities.verify(
                    bundle.dispatch_authority,
                    provider_id=item.route.provider_id,
                    plane=InteractionPlane.DELEGATION.value,
                    task_type=item.task.task_type,
                    batch_id=subject.manifest_digest,
                    member_digest=item.member_digest,
                    provider_tier_binding_digest=(
                        item.provider_tier_binding_digest
                    ),
                    project_binding_digest=bundle.project_binding_digest,
                    admission_lane=bundle.admission_lane,
                    provider_admission_policy_digest=(
                        bundle.provider_admission_policy_digest
                    ),
                )
            self.assertEqual(transport.posts, [])

    def test_staging_failure_revokes_exact_partial_authorities_and_is_visible(self) -> None:
        now = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as state_root:
            services = t1_services(state_root, clock)
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=FakeTransport(success_document()),
                environ={"MACR_STATE_ROOT": str(state_root)},
                key_source=StaticKeySource(),
                approval_store=AllowingApprovalStore(),
                token_policy=t1_glm_live_policy(),
                admission_guard=services.provider_admission,
            )
            dispatcher = T1Dispatcher(
                ProviderRegistry((provider,)),
                services,
                queue=FailingQueue(services.events.path, now=clock),
                now=clock,
            )
            subject = approved_manifest(provider)

            with self.assertRaisesRegex(RuntimeError, "staging failure"):
                dispatcher.stage(
                    subject,
                    subject.authorized_dispatchers,
                    subject.expires_at,
                )

            connection = services.events.database.connect()
            try:
                batch_revoked = connection.execute(
                    "SELECT COUNT(*) FROM batch_authorities WHERE revoked_at IS NOT NULL"
                ).fetchone()[0]
                dispatch_revoked = connection.execute(
                    "SELECT COUNT(*) FROM dispatch_authorities WHERE revoked_at IS NOT NULL"
                ).fetchone()[0]
            finally:
                connection.close()
            events = services.events.read_events()

        self.assertEqual((batch_revoked, dispatch_revoked), (1, 1))
        self.assertEqual(events[-1]["event_type"], "t1.staging_failed")
        self.assertNotIn("synthetic staging failure", str(events[-1]))


if __name__ == "__main__":
    unittest.main()
