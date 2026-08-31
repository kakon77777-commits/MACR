from __future__ import annotations

import json
import unittest
from importlib.resources import files

from macr_runtime.temporal.contracts import (
    AgentCheckpoint,
    DependencyState,
    PendingDependency,
    ResumeRecord,
    SuspendRecord,
    TemporalLease,
    WakeCondition,
    WakeEvent,
    WakeKind,
)


RUN_ID = "11111111-1111-4111-8111-111111111111"
LEASE_ID = "22222222-2222-4222-8222-222222222222"


class TemporalContractTests(unittest.TestCase):
    def make_checkpoint(self, **overrides: object) -> AgentCheckpoint:
        values: dict[str, object] = {
            "checkpoint_id": "checkpoint:1",
            "agent_run_id": RUN_ID,
            "agent_run_epoch": 2,
            "state_revision": 18,
            "goal_ref": "goal:1",
            "goal_digest": "a" * 64,
            "authority_ref": "authority:1",
            "authority_digest": "b" * 64,
            "authority_revision": 4,
            "authority_epoch": 3,
            "budget_ref": "budget:1",
            "budget_digest": "c" * 64,
            "budget_revision": 2,
            "semantic_state_ref": "semantic-state:1",
            "semantic_state_digest": "d" * 64,
            "semantic_state_revision": 7,
            "active_plan_ref": "plan:1",
            "active_plan_digest": "e" * 64,
            "active_plan_revision": 5,
            "world_basis_refs": ("verified-observation:2", "verified-observation:1"),
            "memory_binding_digests": ("f" * 64, "1" * 64),
            "pending_action_refs": ("action:1",),
            "reconciliation_refs": (),
            "verification_state_ref": "verification-state:1",
            "wake_condition_ref": "wake-condition:1",
            "parent_checkpoint_ref": "checkpoint:0",
            "created_at": "2026-08-31T08:00:00+08:00",
        }
        values.update(overrides)
        return AgentCheckpoint(**values)

    def test_checkpoint_round_trip_is_reference_only_and_digest_bound(self) -> None:
        checkpoint = self.make_checkpoint()

        public = checkpoint.to_public_dict()
        rebuilt = AgentCheckpoint.from_dict(public)

        self.assertEqual(rebuilt, checkpoint)
        self.assertEqual(public["created_at"], "2026-08-31T00:00:00+00:00")
        self.assertEqual(public["memory_binding_digests"], sorted(("f" * 64, "1" * 64)))
        serialized = json.dumps(public)
        self.assertNotIn("memory_content", serialized)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("process_handle", serialized)
        self.assertNotIn("provider_session", serialized)

    def test_checkpoint_rejects_runtime_handles_and_unknown_fields(self) -> None:
        public = self.make_checkpoint().to_public_dict()
        public["provider_session_blob"] = {"socket": 7}
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            AgentCheckpoint.from_dict(public)

        public = self.make_checkpoint().to_public_dict()
        public["checkpoint_digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "digest does not match"):
            AgentCheckpoint.from_dict(public)

    def test_checkpoint_plan_fields_are_all_present_or_all_absent(self) -> None:
        no_plan = self.make_checkpoint(
            active_plan_ref=None,
            active_plan_digest=None,
            active_plan_revision=None,
        )
        self.assertIsNone(no_plan.active_plan_ref)

        with self.assertRaisesRegex(ValueError, "active plan fields"):
            self.make_checkpoint(active_plan_ref=None)

    def test_suspend_record_round_trip_binds_checkpoint(self) -> None:
        record = SuspendRecord(
            suspend_record_id="suspend:1",
            agent_run_id=RUN_ID,
            checkpoint_ref="checkpoint:1",
            checkpoint_digest=self.make_checkpoint().checkpoint_digest,
            wake_condition_ref="wake-condition:1",
            reason="waiting for dependency",
            suspended_at="2026-08-31T08:05:00+08:00",
        )

        self.assertEqual(SuspendRecord.from_dict(record.to_public_dict()), record)

    def test_wake_condition_rejects_callable_and_deep_freezes_parameters(self) -> None:
        with self.assertRaises(ValueError):
            WakeCondition(
                wake_condition_id="wake-condition:bad",
                agent_run_id=RUN_ID,
                kind=WakeKind.WORLD_CONDITION,
                parameters={"predicate": lambda: True},
            )

        source = {"dependency": {"ids": ["dep:1"]}}
        condition = WakeCondition(
            wake_condition_id="wake-condition:1",
            agent_run_id=RUN_ID,
            kind=WakeKind.DEPENDENCY_COMPLETED,
            parameters=source,
        )
        source["dependency"]["ids"].append("dep:2")
        self.assertEqual(
            condition.to_public_dict()["parameters"],
            {"dependency": {"ids": ["dep:1"]}},
        )

    def test_wake_condition_time_bounds_must_be_ordered(self) -> None:
        with self.assertRaisesRegex(ValueError, "expires_at"):
            WakeCondition(
                wake_condition_id="wake-condition:1",
                agent_run_id=RUN_ID,
                kind=WakeKind.AT_TIME,
                parameters={"at": "2026-08-31T00:00:00+00:00"},
                not_before="2026-08-31T02:00:00+00:00",
                expires_at="2026-08-31T01:00:00+00:00",
            )

    def test_wake_event_is_deduplicated_data_not_active_transition(self) -> None:
        event = WakeEvent(
            wake_event_id="wake-event:1",
            agent_run_id=RUN_ID,
            wake_condition_ref="wake-condition:1",
            source="scheduler",
            source_event_ref="timer:1",
            received_at="2026-08-31T08:10:00+08:00",
            source_event_time="2026-08-31T08:09:59+08:00",
            deduplication_key="wake:timer:1",
        )

        public = event.to_public_dict()
        self.assertEqual(WakeEvent.from_dict(public), event)
        self.assertNotIn("state", public)
        public["state"] = "active"
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            WakeEvent.from_dict(public)

        with self.assertRaises(ValueError):
            WakeEvent(
                wake_event_id="wake-event:bad",
                agent_run_id=RUN_ID,
                wake_condition_ref="wake-condition:1",
                source="scheduler",
                source_event_ref=None,
                received_at="2026-08-31T00:00:00+00:00",
                source_event_time=None,
                deduplication_key="",
            )

    def test_resume_record_requires_strictly_new_epoch_and_round_trips(self) -> None:
        record = ResumeRecord(
            resume_record_id="resume:1",
            agent_run_id=RUN_ID,
            checkpoint_ref="checkpoint:1",
            wake_event_ref="wake-event:1",
            previous_epoch=2,
            new_epoch=3,
            authority_binding_digest="2" * 64,
            budget_binding_digest="3" * 64,
            fresh_observation_refs=("verified-observation:3",),
            invalidated_plan_refs=("plan:1",),
            resumed_at="2026-08-31T08:11:00+08:00",
        )

        self.assertEqual(ResumeRecord.from_dict(record.to_public_dict()), record)
        self.assertNotIn("state", record.to_public_dict())
        with self.assertRaisesRegex(ValueError, "new_epoch"):
            ResumeRecord(
                resume_record_id="resume:bad",
                agent_run_id=RUN_ID,
                checkpoint_ref="checkpoint:1",
                wake_event_ref="wake-event:1",
                previous_epoch=2,
                new_epoch=2,
                authority_binding_digest="2" * 64,
                budget_binding_digest="3" * 64,
                fresh_observation_refs=(),
                invalidated_plan_refs=(),
                resumed_at="2026-08-31T00:00:00+00:00",
            )

    def test_temporal_lease_requires_ordered_time_and_current_epoch_shape(self) -> None:
        lease = TemporalLease(
            lease_id=LEASE_ID,
            agent_run_id=RUN_ID,
            owner_id="owner:runtime:1",
            epoch=3,
            fencing_token="fence:3:1",
            acquired_at="2026-08-31T00:00:00+00:00",
            expires_at="2026-08-31T00:10:00+00:00",
        )
        self.assertEqual(TemporalLease.from_dict(lease.to_public_dict()), lease)

        with self.assertRaises(ValueError):
            TemporalLease(
                lease_id=LEASE_ID,
                agent_run_id=RUN_ID,
                owner_id="owner:runtime:1",
                epoch=-1,
                fencing_token="fence:bad",
                acquired_at="2026-08-31T00:00:00+00:00",
                expires_at="2026-08-31T00:10:00+00:00",
            )
        with self.assertRaisesRegex(ValueError, "expires_at"):
            TemporalLease(
                lease_id=LEASE_ID,
                agent_run_id=RUN_ID,
                owner_id="owner:runtime:1",
                epoch=1,
                fencing_token="fence:1",
                acquired_at="2026-08-31T00:10:00+00:00",
                expires_at="2026-08-31T00:00:00+00:00",
            )

    def test_pending_dependency_completion_ref_matches_state(self) -> None:
        pending = PendingDependency(
            dependency_id="dependency:1",
            agent_run_id=RUN_ID,
            dependency_kind="provider_operation",
            target_ref="provider-op:1",
            state=DependencyState.PENDING,
            completion_ref=None,
            created_at="2026-08-31T00:00:00+00:00",
            updated_at="2026-08-31T00:00:00+00:00",
        )
        completed = PendingDependency(
            dependency_id="dependency:1",
            agent_run_id=RUN_ID,
            dependency_kind="provider_operation",
            target_ref="provider-op:1",
            state=DependencyState.COMPLETED,
            completion_ref="receipt:1",
            created_at="2026-08-31T00:00:00+00:00",
            updated_at="2026-08-31T00:01:00+00:00",
        )
        self.assertEqual(PendingDependency.from_dict(pending.to_public_dict()), pending)
        self.assertEqual(PendingDependency.from_dict(completed.to_public_dict()), completed)

        with self.assertRaises(ValueError):
            PendingDependency(
                dependency_id="dependency:bad",
                agent_run_id=RUN_ID,
                dependency_kind="provider_operation",
                target_ref="provider-op:1",
                state=DependencyState.COMPLETED,
                completion_ref=None,
                created_at="2026-08-31T00:00:00+00:00",
                updated_at="2026-08-31T00:01:00+00:00",
            )

    def test_temporal_schema_is_packaged_closed_and_nonreplaying(self) -> None:
        schema_path = files("macr_runtime.temporal").joinpath(
            "schemas/temporal-contracts-v1.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(
            schema["$id"],
            "urn:evemisslab:macr:temporal-contracts:v1",
        )
        self.assertFalse(schema["$defs"]["AgentCheckpoint"]["additionalProperties"])
        self.assertFalse(schema["$defs"]["WakeEvent"]["additionalProperties"])
        self.assertNotIn("state", schema["$defs"]["WakeEvent"]["properties"])
        self.assertNotIn("provider_session_blob", json.dumps(schema))
        self.assertEqual(
            schema["$defs"]["TemporalLease"]["properties"]["expires_at"]["format"],
            "date-time",
        )
        self.assertEqual(len(schema["$defs"]["AgentCheckpoint"]["allOf"]), 1)
        self.assertEqual(len(schema["$defs"]["PendingDependency"]["allOf"]), 2)


if __name__ == "__main__":
    unittest.main()
