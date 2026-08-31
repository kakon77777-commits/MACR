from __future__ import annotations

import json
import unittest
from importlib.resources import files

from macr_runtime.action.contracts import (
    ActionAdmission,
    ActionAttempt,
    ActionAttemptState,
    ActionProposal,
    ActionVerification,
    ActuationReceipt,
    AdmissionDecision,
    BudgetEnvelope,
    CapabilityAvailability,
    CapabilityRef,
    CommandIntent,
    EffectName,
    EffectSet,
    ReceiptStatus,
    ReconciliationClassification,
    ReconciliationRecord,
    VerificationVerdict,
)
from macr_runtime.execution import AuthorizationReference


RUN_ID = "11111111-1111-4111-8111-111111111111"
ATTEMPT_ID = "22222222-2222-4222-8222-222222222222"


class ActionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.read_effects = EffectSet.from_values(("repository.read",))
        self.write_effects = EffectSet.from_values(
            ("repository.working_tree.write", "repository.read")
        )
        self.capability = CapabilityRef(
            capability_id="capability:repo-write",
            provider="local-workspace",
            operation="repository.patch",
            effect_profile_ref="effects:repo-write-v1",
            adapter_version="1.0",
            availability_state=CapabilityAvailability.AVAILABLE,
        )
        self.budget = BudgetEnvelope(
            budget_id="budget:agent:1",
            agent_run_id=RUN_ID,
            provider_calls=3,
            currency_cost_usd=1.25,
            wall_clock_seconds=120.0,
            child_agent_count=0,
            revision=1,
        )
        self.authorization = AuthorizationReference(
            source_kind="host_operator",
            source_id="authority:agent:1",
            digest="a" * 64,
            revision=2,
            epoch=1,
            scope="repository:fixture",
        )

    def make_proposal(self, **overrides: object) -> ActionProposal:
        values: dict[str, object] = {
            "action_id": "action:1",
            "agent_run_id": RUN_ID,
            "agent_run_epoch": 1,
            "goal_ref": "goal:1",
            "plan_ref": "plan:1",
            "task_ref": "task:1",
            "operation": "repository.patch",
            "target_ref": "workspace:feature",
            "parameters_ref": "parameters:patch:1",
            "declared_effects": self.write_effects,
            "basis_refs": ("verified-observation:before",),
            "preconditions": ("precondition:head-a",),
            "expected_result_ref": "expected:test-green",
            "rollback_policy_ref": "rollback:restore-worktree",
            "verification_policy_ref": "verification:tests-and-digest",
            "provenance_ref": "provenance:agent-step-1",
        }
        values.update(overrides)
        return ActionProposal(**values)

    def make_admission(self, **overrides: object) -> ActionAdmission:
        proposal = self.make_proposal()
        values: dict[str, object] = {
            "action_id": proposal.action_id,
            "proposal_digest": proposal.proposal_digest,
            "decision": AdmissionDecision.ALLOW_WITH_VERIFY,
            "effective_effects": self.write_effects,
            "capability_refs": (self.capability,),
            "authorization": self.authorization,
            "budget_digest": self.budget.budget_digest,
            "budget_revision": self.budget.revision,
            "world_basis_digest": "b" * 64,
            "policy_snapshot_digest": "c" * 64,
        }
        values.update(overrides)
        return ActionAdmission(**values)

    def make_command(self) -> CommandIntent:
        admission = self.make_admission()
        return CommandIntent(
            command_intent_id="command:1",
            action_ref=admission.action_id,
            operation="repository.patch",
            target_ref="workspace:feature",
            parameter_ref="parameters:patch:1",
            effective_effects=admission.effective_effects,
            admission_ref=admission.admission_digest,
            idempotency_ref="idempotency:action:1",
            verification_policy_ref="verification:tests-and-digest",
        )

    def make_receipt(self, status: ReceiptStatus = ReceiptStatus.CONFIRMED) -> ActuationReceipt:
        return ActuationReceipt(
            receipt_id="receipt:1",
            action_ref="action:1",
            command_ref="command:1",
            attempt_id=ATTEMPT_ID,
            provider="local-workspace",
            provider_operation_id="provider-op:1",
            status=status,
            reported_result_ref="result:patch:1",
            observed_cost_ref="cost:zero",
            duration_ms=25,
            evidence_refs=("evidence:provider:1",),
        )

    def make_verification(
        self,
        verdict: VerificationVerdict = VerificationVerdict.PASSED,
    ) -> ActionVerification:
        return ActionVerification(
            verification_id="action-verification:1",
            action_ref="action:1",
            verification_kind="independent_repo_check",
            basis_refs=("verified-observation:after",),
            verdict=verdict,
            evidence_refs=("evidence:test-run",),
            verifier_ref="verifier:fixture",
        )

    def test_effect_set_is_closed_sorted_and_digest_bound(self) -> None:
        effects = EffectSet.from_values(
            ("repository.working_tree.write", "repository.read")
        )

        self.assertEqual(
            effects.effects,
            (EffectName.REPOSITORY_READ, EffectName.REPOSITORY_WORKING_TREE_WRITE),
        )
        self.assertEqual(EffectSet.from_dict(effects.to_public_dict()), effects)
        with self.assertRaises(ValueError):
            EffectSet.from_values(("repository.read", "world.unknown_mutation"))
        with self.assertRaisesRegex(ValueError, "duplicates"):
            EffectSet.from_values(("repository.read", "repository.read"))

    def test_capability_round_trip_preserves_availability_without_authority(self) -> None:
        rebuilt = CapabilityRef.from_dict(self.capability.to_public_dict())

        self.assertEqual(rebuilt, self.capability)
        self.assertEqual(rebuilt.availability_state, CapabilityAvailability.AVAILABLE)
        self.assertFalse(hasattr(rebuilt, "authorization"))

    def test_budget_rejects_boolean_negative_and_invalid_revision(self) -> None:
        self.assertEqual(BudgetEnvelope.from_dict(self.budget.to_public_dict()), self.budget)
        for field_name, value in (
            ("provider_calls", True),
            ("currency_cost_usd", -0.01),
            ("wall_clock_seconds", float("inf")),
            ("child_agent_count", -1),
            ("revision", 0),
        ):
            values = dict(
                budget_id="budget:bad",
                agent_run_id=RUN_ID,
                provider_calls=1,
                currency_cost_usd=1.0,
                wall_clock_seconds=1.0,
                child_agent_count=0,
                revision=1,
            )
            values[field_name] = value
            with self.subTest(field=field_name):
                with self.assertRaises(ValueError):
                    BudgetEnvelope(**values)

    def test_action_proposal_is_closed_and_has_no_authorized_field(self) -> None:
        proposal = self.make_proposal()

        self.assertEqual(ActionProposal.from_dict(proposal.to_public_dict()), proposal)
        public = proposal.to_public_dict()
        public["authorized"] = True
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            ActionProposal.from_dict(public)

    def test_proposal_digest_changes_with_effect_or_basis(self) -> None:
        baseline = self.make_proposal()
        read_only = self.make_proposal(declared_effects=self.read_effects)
        different_basis = self.make_proposal(basis_refs=("verified-observation:other",))

        self.assertNotEqual(baseline.proposal_digest, read_only.proposal_digest)
        self.assertNotEqual(baseline.proposal_digest, different_basis.proposal_digest)

    def test_admission_requires_existing_authorization_reference(self) -> None:
        admission = self.make_admission()

        self.assertEqual(ActionAdmission.from_dict(admission.to_public_dict()), admission)
        self.assertIs(admission.authorization, self.authorization)
        with self.assertRaises(ValueError):
            self.make_admission(authorization="user said yes")

    def test_admission_is_not_dispatch_and_binds_exact_budget_and_world(self) -> None:
        admission = self.make_admission()
        public = admission.to_public_dict()

        self.assertNotIn("dispatched", public)
        self.assertNotIn("provider_result", public)
        self.assertEqual(public["budget_digest"], self.budget.budget_digest)
        self.assertEqual(public["world_basis_digest"], "b" * 64)

    def test_allow_decision_requires_capability_but_deny_can_record_none(self) -> None:
        with self.assertRaisesRegex(ValueError, "capability"):
            self.make_admission(capability_refs=())

        denied = self.make_admission(
            decision=AdmissionDecision.DENY,
            capability_refs=(),
        )
        self.assertEqual(denied.capability_refs, ())

    def test_command_intent_round_trip_has_no_provider_attempt_state(self) -> None:
        command = self.make_command()
        public = command.to_public_dict()

        self.assertEqual(CommandIntent.from_dict(public), command)
        self.assertNotIn("attempt_id", public)
        self.assertNotIn("provider", public)

    def test_action_and_attempt_identity_are_distinct(self) -> None:
        attempt = ActionAttempt(
            attempt_id=ATTEMPT_ID,
            action_ref="action:1",
            command_ref="command:1",
            provider_ref="provider:local",
            state=ActionAttemptState.DISPATCHED,
            started_at="2026-08-31T00:00:00+00:00",
            finished_at=None,
            provider_operation_id="provider-op:1",
        )

        self.assertNotEqual(attempt.attempt_id, attempt.action_ref)
        self.assertEqual(ActionAttempt.from_dict(attempt.to_public_dict()), attempt)
        with self.assertRaises(ValueError):
            ActionAttempt(
                attempt_id=ATTEMPT_ID,
                action_ref="action:1",
                command_ref="command:1",
                provider_ref="provider:local",
                state=ActionAttemptState.RECEIPT_CAPTURED,
                started_at="2026-08-31T00:00:00+00:00",
                finished_at=None,
                provider_operation_id="provider-op:1",
            )

    def test_receipt_and_verification_are_distinct_types(self) -> None:
        receipt = self.make_receipt(ReceiptStatus.CONFIRMED)
        verification = self.make_verification(VerificationVerdict.DIVERGED)

        self.assertNotIsInstance(receipt, ActionVerification)
        self.assertEqual(receipt.status, ReceiptStatus.CONFIRMED)
        self.assertEqual(verification.verdict, VerificationVerdict.DIVERGED)
        self.assertNotIn("verified", receipt.to_public_dict())
        self.assertEqual(ActuationReceipt.from_dict(receipt.to_public_dict()), receipt)
        self.assertEqual(
            ActionVerification.from_dict(verification.to_public_dict()),
            verification,
        )

    def test_state_unknown_is_unresolved_and_cannot_carry_resolution_authority(self) -> None:
        record = ReconciliationRecord(
            reconciliation_id="reconciliation:1",
            agent_run_id=RUN_ID,
            action_id="action:1",
            classification=ReconciliationClassification.STATE_UNKNOWN,
            evidence_refs=("evidence:timeout",),
            resolved_by=None,
            authority_ref=None,
            resolved_at=None,
        )

        self.assertFalse(record.is_resolved)
        self.assertEqual(ReconciliationRecord.from_dict(record.to_public_dict()), record)
        with self.assertRaises(ValueError):
            ReconciliationRecord(
                reconciliation_id="reconciliation:bad",
                agent_run_id=RUN_ID,
                action_id="action:1",
                classification=ReconciliationClassification.STATE_UNKNOWN,
                evidence_refs=("evidence:guess",),
                resolved_by="agent:self",
                authority_ref=self.authorization,
                resolved_at="2026-08-31T00:00:00+00:00",
            )

    def test_resolved_reconciliation_requires_evidence_actor_authority_and_time(self) -> None:
        resolved = ReconciliationRecord(
            reconciliation_id="reconciliation:2",
            agent_run_id=RUN_ID,
            action_id="action:1",
            classification=ReconciliationClassification.EXECUTED_AS_EXPECTED,
            evidence_refs=("evidence:world-observation",),
            resolved_by="operator:fixture",
            authority_ref=self.authorization,
            resolved_at="2026-08-31T08:00:00+08:00",
        )
        self.assertTrue(resolved.is_resolved)

        for field_name, value in (
            ("evidence_refs", ()),
            ("resolved_by", None),
            ("authority_ref", None),
            ("resolved_at", None),
        ):
            values = dict(
                reconciliation_id="reconciliation:bad",
                agent_run_id=RUN_ID,
                action_id="action:1",
                classification=ReconciliationClassification.EXECUTED_AS_EXPECTED,
                evidence_refs=("evidence:world-observation",),
                resolved_by="operator:fixture",
                authority_ref=self.authorization,
                resolved_at="2026-08-31T00:00:00+00:00",
            )
            values[field_name] = value
            with self.subTest(field=field_name):
                with self.assertRaises(ValueError):
                    ReconciliationRecord(**values)

    def test_unknown_reconciliation_classification_is_rejected(self) -> None:
        public = ReconciliationRecord(
            reconciliation_id="reconciliation:1",
            agent_run_id=RUN_ID,
            action_id="action:1",
            classification=ReconciliationClassification.STATE_UNKNOWN,
            evidence_refs=("evidence:timeout",),
            resolved_by=None,
            authority_ref=None,
            resolved_at=None,
        ).to_public_dict()
        public["classification"] = "probably_executed"
        with self.assertRaises(ValueError):
            ReconciliationRecord.from_dict(public)

    def test_action_schema_is_packaged_closed_and_noncollapsed(self) -> None:
        schema_path = files("macr_runtime.action").joinpath(
            "schemas/action-contracts-v1.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(schema["$id"], "urn:evemisslab:macr:action-contracts:v1")
        self.assertFalse(schema["$defs"]["ActionProposal"]["additionalProperties"])
        self.assertFalse(schema["$defs"]["ActuationReceipt"]["additionalProperties"])
        serialized = json.dumps(schema)
        self.assertNotIn("success_and_verified", serialized)
        self.assertNotIn("auto_retry", serialized)
        self.assertNotIn('"authorized"', serialized)
        self.assertEqual(len(schema["$defs"]["ActionAttempt"]["allOf"]), 2)
        self.assertEqual(len(schema["$defs"]["ActionAdmission"]["allOf"]), 1)
        self.assertEqual(len(schema["$defs"]["ReconciliationRecord"]["allOf"]), 2)


if __name__ == "__main__":
    unittest.main()
