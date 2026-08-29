from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timezone

from macr_runtime.event_store import SqliteEventStore
from macr_runtime.execution import DispatchOrigin, InteractionPlane
from macr_runtime.providers.glm import GlmFlashWorkerProvider
from macr_runtime.registry import ProviderRegistry
from macr_runtime.scheduler import PlanQueue
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


def approved_manifest(provider: GlmFlashWorkerProvider) -> T1ExecutionManifest:
    source = unapproved_manifest()
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
        aggregate_cost_ceiling_usd=source.aggregate_cost_ceiling_usd,
        campaign_cost_ceiling_usd=source.campaign_cost_ceiling_usd,
        expires_at=source.expires_at,
        authorized_dispatchers=source.authorized_dispatchers,
    )


class FailingQueue(PlanQueue):
    def enqueue(self, plan):
        del plan
        raise RuntimeError("synthetic staging failure")


class FailingFinishEventStore(SqliteEventStore):
    def finish_run(self, **kwargs):
        del kwargs
        raise RuntimeError("synthetic terminal persistence failure")


class T1DispatcherTests(unittest.TestCase):
    def test_worker_claims_one_member_and_uses_complete_runtime_path_once(self) -> None:
        now = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as state_root:
            transport = FakeTransport(success_document())
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=transport,
                environ={"MACR_STATE_ROOT": str(state_root)},
                key_source=StaticKeySource(),
                approval_store=AllowingApprovalStore(),
                token_policy=t1_glm_live_policy(),
            )
            services = build_test_services(state_root)
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

    def test_unknown_after_dispatch_requires_global_reconciliation_and_blocks_next(self) -> None:
        now = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as state_root:
            transport = FakeTransport(success_document())
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=transport,
                environ={"MACR_STATE_ROOT": str(state_root)},
                key_source=StaticKeySource(),
                approval_store=AllowingApprovalStore(),
                token_policy=t1_glm_live_policy(),
            )
            services = build_test_services(state_root)
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

        self.assertEqual(result.queue_state, "reconciliation_required")
        self.assertEqual(result.provider_state, "unknown_after_dispatch")
        self.assertEqual(counts["reconciliation_required"], 1)
        self.assertEqual(counts["queued"], 2)
        self.assertEqual(len(transport.posts), 1)

    def test_stale_task_approval_refuses_before_any_authority_or_queue_write(self) -> None:
        now = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as state_root:
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=FakeTransport(success_document()),
                environ={"MACR_STATE_ROOT": str(state_root)},
                key_source=StaticKeySource(),
                approval_store=AllowingApprovalStore(),
                token_policy=t1_glm_live_policy(),
            )
            services = build_test_services(state_root)
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
                role_digest=source.members[0].role_digest,
                privacy=source.members[0].privacy,
                context_class=source.members[0].context_class,
                cost_ceiling_usd=source.members[0].cost_ceiling_usd,
                target_claims=source.members[0].target_claims,
            )
            changed = T1ExecutionManifest.create(
                plan_digest=source.plan_digest,
                members=(changed_member, *source.members[1:]),
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
            transport = FakeTransport(success_document())
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=transport,
                environ={"MACR_STATE_ROOT": str(state_root)},
                key_source=StaticKeySource(),
                approval_store=AllowingApprovalStore(),
                token_policy=t1_glm_live_policy(),
            )
            services = build_test_services(state_root)
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
                )
            self.assertEqual(transport.posts, [])

    def test_staging_failure_revokes_exact_partial_authorities_and_is_visible(self) -> None:
        now = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as state_root:
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=FakeTransport(success_document()),
                environ={"MACR_STATE_ROOT": str(state_root)},
                key_source=StaticKeySource(),
                approval_store=AllowingApprovalStore(),
                token_policy=t1_glm_live_policy(),
            )
            services = build_test_services(state_root)
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
