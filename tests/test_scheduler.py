from __future__ import annotations

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from macr_runtime.batch_authority import (
    BatchAuthorityStore,
    BatchMemberScope,
    BatchScope,
)
from macr_runtime.errors import DispatchAuthorizationError, DispatchLeaseError
from macr_runtime.scheduler import (
    PlanQueue,
    QueueMember,
    QueueMemberState,
    T1QueuePlan,
    TargetClaim,
)

from tests.support import d_drive_tempdir


class Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def _member(
    ordinal: int,
    *,
    target: TargetClaim | None = None,
    cost: float = 0.05,
) -> QueueMember:
    seed = format(ordinal + 1, "x")
    return QueueMember(
        member_digest=seed * 64,
        provider_id="glm_flash_worker",
        route_id="a" * 64,
        role_digest="b" * 64,
        privacy="public_text",
        context_class="non_sensitive_routine",
        cost_ceiling_usd=cost,
        target_claims=() if target is None else (target,),
    )


def _authorize(
    database,
    clock: Clock,
    members: tuple[QueueMember, ...],
    *,
    aggregate: float | None = None,
    plan_digest: str = "f" * 64,
) -> T1QueuePlan:
    total = sum(item.cost_ceiling_usd for item in members)
    aggregate = total if aggregate is None else aggregate
    scope = BatchScope(
        plan_digest=plan_digest,
        ordered_members=tuple(
            BatchMemberScope(
                member_digest=item.member_digest,
                provider_id=item.provider_id,
                route_id=item.route_id,
                role_digest=item.role_digest,
                privacy=item.privacy,
                context_class=item.context_class,
                cost_ceiling_usd=item.cost_ceiling_usd,
            )
            for item in members
        ),
        aggregate_cost_ceiling_usd=aggregate,
        expires_at=(clock.value + timedelta(hours=1)).isoformat(),
        authorized_dispatchers=("dispatcher-a", "dispatcher-b"),
    )
    reference = BatchAuthorityStore(database, now=clock).issue(scope)
    return T1QueuePlan(
        plan_digest=scope.plan_digest,
        members=members,
        aggregate_cost_ceiling_usd=aggregate,
        authority=reference,
    )


class PlanQueueTests(unittest.TestCase):
    def test_plan_scoped_claim_never_consumes_another_manifest(self) -> None:
        now = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as temp:
            database = temp / "dispatch.sqlite3"
            queue = PlanQueue(database, now=clock)
            first_plan = _authorize(
                database,
                clock,
                (_member(0),),
                plan_digest="e" * 64,
            )
            second_plan = _authorize(
                database,
                clock,
                (_member(1),),
                plan_digest="f" * 64,
            )
            queue.enqueue(first_plan)
            queue.enqueue(second_plan)

            claim = queue.claim(
                "dispatcher-a",
                plan_digest=second_plan.plan_digest,
            )

            assert claim is not None
            self.assertEqual(claim.plan_digest, second_plan.plan_digest)
            self.assertEqual(
                queue.list_members(first_plan.plan_digest)[0].state,
                QueueMemberState.QUEUED,
            )

    def test_global_reconciliation_listing_spans_plans_and_is_bounded(self) -> None:
        now = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as temp:
            database = temp / "dispatch.sqlite3"
            queue = PlanQueue(database, now=clock)
            plan_a = _authorize(
                database,
                clock,
                (_member(0),),
                plan_digest="e" * 64,
            )
            plan_b = _authorize(
                database,
                clock,
                (_member(1),),
                plan_digest="f" * 64,
            )
            queue.enqueue(plan_b)
            queue.enqueue(plan_a)
            first = queue.claim("dispatcher-a", lease_seconds=60)
            second = queue.claim("dispatcher-b", lease_seconds=60)
            assert first is not None and second is not None
            queue.require_reconciliation(
                first.member_id,
                first.dispatcher_id,
                first.fencing_token,
                terminal_evidence_digest="c" * 64,
                observed_cost_usd=0.001,
            )
            queue.require_reconciliation(
                second.member_id,
                second.dispatcher_id,
                second.fencing_token,
                terminal_evidence_digest="d" * 64,
                observed_cost_usd=0.002,
            )

            first_page = queue.list_by_state(
                QueueMemberState.RECONCILIATION_REQUIRED,
                limit=1,
            )
            second_page = queue.list_by_state(
                QueueMemberState.RECONCILIATION_REQUIRED,
                limit=1,
                after_member_id=first_page[0].member_id,
            )
            counts = queue.state_counts()

            self.assertEqual(len(first_page), 1)
            self.assertEqual(len(second_page), 1)
            self.assertLess(first_page[0].plan_digest, second_page[0].plan_digest)
            self.assertEqual(counts["reconciliation_required"], 2)
            self.assertEqual(sum(counts.values()), 2)
            with self.assertRaisesRegex(ValueError, "limit"):
                queue.list_by_state(QueueMemberState.QUEUED, limit=0)
            with self.assertRaisesRegex(ValueError, "limit"):
                queue.list_by_state(QueueMemberState.QUEUED, limit=1_001)
            with self.assertRaisesRegex(DispatchLeaseError, "cursor"):
                queue.list_by_state(
                    QueueMemberState.QUEUED,
                    after_member_id=first_page[0].member_id,
                )

    def test_target_claim_rejects_unsafe_paths_and_canonicalizes_aliases(self) -> None:
        self.assertEqual(
            TargetClaim.for_path(r"Src\Module.py").target_key,
            TargetClaim.for_path("src/module.py").target_key,
        )
        for target in (
            "src/../module.py",
            "../module.py",
            r"D:\module.py",
            r"\\server\share\module.py",
            "/absolute/module.py",
            "src/NUL.txt",
            "src/module.py:stream",
        ):
            with self.subTest(target=target):
                with self.assertRaisesRegex(ValueError, "target"):
                    TargetClaim.for_path(target)

    def test_queue_lifecycle_is_fenced_and_one_attempt_only(self) -> None:
        now = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as temp:
            database = temp / "dispatch.sqlite3"
            members = (_member(0), _member(1))
            plan = _authorize(database, clock, members)
            queue = PlanQueue(database, now=clock)

            member_ids = queue.enqueue(plan)
            self.assertEqual(member_ids, queue.enqueue(plan))
            first = queue.claim("dispatcher-a", lease_seconds=60)
            second = queue.claim("dispatcher-b", lease_seconds=60)
            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            assert first is not None and second is not None
            self.assertNotEqual(first.member_id, second.member_id)
            self.assertEqual(first.attempts, 1)
            self.assertEqual(second.attempts, 1)
            self.assertIsNone(queue.claim("dispatcher-a", lease_seconds=60))

            renewed = queue.renew(
                first.member_id,
                "dispatcher-a",
                first.fencing_token,
                lease_seconds=120,
            )
            self.assertNotEqual(renewed.lease_expires_at, first.lease_expires_at)
            queue.complete(
                first.member_id,
                "dispatcher-a",
                first.fencing_token,
                terminal_evidence_digest="c" * 64,
                observed_cost_usd=0.01,
            )
            queue.fail(
                second.member_id,
                "dispatcher-b",
                second.fencing_token,
                terminal_evidence_digest="d" * 64,
                observed_cost_usd=0.02,
            )

            states = tuple(item.state for item in queue.list_members(plan.plan_digest))
            self.assertEqual(
                states,
                (QueueMemberState.COMPLETED, QueueMemberState.FAILED),
            )
            with self.assertRaisesRegex(DispatchLeaseError, "terminal"):
                queue.complete(
                    first.member_id,
                    "dispatcher-a",
                    first.fencing_token,
                    terminal_evidence_digest="e" * 64,
                    observed_cost_usd=0,
                )

    def test_expired_claim_requires_reconciliation_and_is_never_requeued(self) -> None:
        now = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as temp:
            database = temp / "dispatch.sqlite3"
            plan = _authorize(database, clock, (_member(0),))
            queue = PlanQueue(database, now=clock)
            queue.enqueue(plan)
            claim = queue.claim("dispatcher-a", lease_seconds=30)
            assert claim is not None

            clock.value = now + timedelta(minutes=1)
            self.assertIsNone(queue.claim("dispatcher-a", lease_seconds=30))
            record = queue.read_member(claim.member_id)

            self.assertEqual(record.state, QueueMemberState.RECONCILIATION_REQUIRED)
            self.assertEqual(record.attempts, 1)

    def test_expiry_reconciliation_commits_before_later_budget_refusal(self) -> None:
        now = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as temp:
            database = temp / "dispatch.sqlite3"
            plan = _authorize(
                database,
                clock,
                (_member(0, cost=0.05), _member(1, cost=0.05)),
                aggregate=0.05,
            )
            queue = PlanQueue(database, now=clock)
            queue.enqueue(plan)
            first = queue.claim("dispatcher-a", lease_seconds=30)
            assert first is not None

            clock.value = now + timedelta(minutes=1)
            with self.assertRaisesRegex(DispatchLeaseError, "aggregate cost"):
                queue.claim("dispatcher-b", lease_seconds=30)

            self.assertEqual(
                queue.read_member(first.member_id).state,
                QueueMemberState.RECONCILIATION_REQUIRED,
            )

    def test_same_target_requires_named_competing_alternatives(self) -> None:
        now = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        target = TargetClaim.for_path("src/module.py")
        with d_drive_tempdir() as temp:
            database = temp / "dispatch.sqlite3"
            colliding = (_member(0, target=target), _member(1, target=target))
            plan = _authorize(database, clock, colliding)
            queue = PlanQueue(database, now=clock)
            with self.assertRaisesRegex(DispatchLeaseError, "target collision"):
                queue.enqueue(plan)

            alternatives = (
                _member(
                    0,
                    target=TargetClaim.for_path(
                        "src/module.py",
                        alternative_group="codec-alternatives",
                        materialize_automatically=True,
                    ),
                ),
                _member(
                    1,
                    target=TargetClaim.for_path(
                        "src/module.py",
                        alternative_group="codec-alternatives",
                        materialize_automatically=False,
                    ),
                ),
            )
            allowed = _authorize(database, clock, alternatives)
            self.assertEqual(len(queue.enqueue(allowed)), 2)

        with d_drive_tempdir() as temp:
            database = temp / "dispatch.sqlite3"
            both_auto = (
                _member(
                    0,
                    target=TargetClaim.for_path(
                        "src/module.py",
                        alternative_group="codec-alternatives",
                        materialize_automatically=True,
                    ),
                ),
                _member(
                    1,
                    target=TargetClaim.for_path(
                        "src/module.py",
                        alternative_group="codec-alternatives",
                        materialize_automatically=True,
                    ),
                ),
            )
            queue = PlanQueue(database, now=clock)
            with self.assertRaisesRegex(DispatchLeaseError, "automatic"):
                queue.enqueue(_authorize(database, clock, both_auto))

    def test_queue_verifies_authority_and_hard_aggregate_ceiling(self) -> None:
        now = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as temp:
            database = temp / "dispatch.sqlite3"
            members = (_member(0, cost=0.05), _member(1, cost=0.05))
            plan = _authorize(database, clock, members, aggregate=0.05)
            queue = PlanQueue(database, now=clock)
            queue.enqueue(plan)
            first = queue.claim("dispatcher-a", lease_seconds=60)
            self.assertIsNotNone(first)
            with self.assertRaisesRegex(DispatchLeaseError, "aggregate cost"):
                queue.claim("dispatcher-b", lease_seconds=60)
            with self.assertRaisesRegex(DispatchAuthorizationError, "dispatcher"):
                queue.claim("dispatcher-z", lease_seconds=60)

    def test_database_contains_only_target_digest_not_raw_path(self) -> None:
        now = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as temp:
            database = temp / "dispatch.sqlite3"
            raw_path = "src/private-module.py"
            members = (_member(0, target=TargetClaim.for_path(raw_path)),)
            queue = PlanQueue(database, now=clock)
            queue.enqueue(_authorize(database, clock, members))

            self.assertNotIn(raw_path.encode("utf-8"), database.read_bytes())

    def test_database_rejects_invalid_queue_state_and_boolean_marker(self) -> None:
        now = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as temp:
            database = temp / "dispatch.sqlite3"
            member = _member(0, target=TargetClaim.for_path("src/module.py"))
            queue = PlanQueue(database, now=clock)
            queue.enqueue(_authorize(database, clock, (member,)))

            connection = sqlite3.connect(database)
            try:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "UPDATE plan_queue_members SET state = 'lost'"
                    )
                connection.rollback()
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """
                        UPDATE plan_target_claims
                        SET materialize_automatically = 2
                        """
                    )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
