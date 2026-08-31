from __future__ import annotations

import ast
import unittest
from pathlib import Path

from macr_runtime.action.contracts import (
    ActionAdmission,
    ActionProposal,
    ActionVerification,
    ActuationReceipt,
    BudgetEnvelope,
    CapabilityAvailability,
    CapabilityRef,
    EffectSet,
    ReceiptStatus,
)
from macr_runtime.agent.contracts import (
    AgentRunIdentity,
    AuthorityBinding,
    GoalBinding,
    MemoryBindingRef,
)
from macr_runtime.execution import (
    AuthorizationReference,
    DispatchContext,
    DispatchOrigin,
    InteractionPlane,
)
from macr_runtime.observation.contracts import (
    RawObservationRef,
    VerifiedObservationRef,
)
from macr_runtime.semantic.contracts import (
    ArtifactRole,
    ClaimStatus,
    SemanticLifecycleStatus,
    SemanticNode,
    SemanticNodeType,
    SemanticProfileRef,
    SemanticProvenance,
)
from macr_runtime.temporal.contracts import (
    AgentCheckpoint,
    ResumeRecord,
    WakeCondition,
    WakeEvent,
    WakeKind,
)


RUN_ID = "11111111-1111-4111-8111-111111111111"
ATTEMPT_ID = "22222222-2222-4222-8222-222222222222"


class AgentContractBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.origin = DispatchOrigin("codex", "task", "task:fixture")
        self.authorization = AuthorizationReference(
            source_kind="host_operator",
            source_id="authority:fixture",
            digest="a" * 64,
            revision=1,
            epoch=0,
            scope="scope:fixture",
        )
        self.provenance = SemanticProvenance(
            origin_kind="agent_run",
            origin_ref="agent:fixture",
            source_refs=("source:fixture",),
            agent_run_id=RUN_ID,
            created_by_ref="actor:fixture",
            created_at="2026-08-31T00:00:00+00:00",
        )
        self.memory = MemoryBindingRef(
            memory_system_id="mneme",
            profile_id="MLF-RM/0.1",
            subject_ref="agent:fixture",
            head_ref="head:1",
            head_digest="b" * 64,
            access_policy_ref="policy:read-only",
            projection_policy_ref="projection:bounded",
        )

    def make_proposal(self) -> ActionProposal:
        return ActionProposal(
            action_id="action:1",
            agent_run_id=RUN_ID,
            agent_run_epoch=0,
            goal_ref="goal:1",
            plan_ref="plan:1",
            task_ref="task:1",
            operation="repository.patch",
            target_ref="workspace:feature",
            parameters_ref="parameters:1",
            declared_effects=EffectSet.from_values(("repository.read",)),
            basis_refs=("verified-observation:1",),
            preconditions=(),
            expected_result_ref="expected:1",
            rollback_policy_ref="rollback:1",
            verification_policy_ref="verification:1",
            provenance_ref="provenance:1",
        )

    def make_checkpoint(self) -> AgentCheckpoint:
        return AgentCheckpoint(
            checkpoint_id="checkpoint:1",
            agent_run_id=RUN_ID,
            agent_run_epoch=1,
            state_revision=2,
            goal_ref="goal:1",
            goal_digest="1" * 64,
            authority_ref="authority:1",
            authority_digest="2" * 64,
            authority_revision=1,
            authority_epoch=0,
            budget_ref="budget:1",
            budget_digest="3" * 64,
            budget_revision=1,
            semantic_state_ref="semantic:1",
            semantic_state_digest="4" * 64,
            semantic_state_revision=1,
            active_plan_ref=None,
            active_plan_digest=None,
            active_plan_revision=None,
            world_basis_refs=("verified-observation:1",),
            memory_binding_digests=(self.memory.binding_digest,),
            pending_action_refs=(),
            reconciliation_refs=(),
            verification_state_ref="verification-state:1",
            wake_condition_ref=None,
            parent_checkpoint_ref=None,
            created_at="2026-08-31T00:00:00+00:00",
        )

    def test_agent_run_identity_is_not_dispatch_context_run_id(self) -> None:
        identity = AgentRunIdentity(RUN_ID, "5" * 64)

        with self.assertRaises(ValueError):
            DispatchContext(
                run_id=identity,
                plane=InteractionPlane.DELEGATION,
                origin=self.origin,
                authorization=self.authorization,
                policy_snapshot_sha256="6" * 64,
            )

    def test_goal_binding_cannot_construct_authority_binding(self) -> None:
        with self.assertRaises(ValueError):
            AuthorityBinding(GoalBinding("goal:1", "7" * 64, 1))

    def test_semantic_decision_and_profile_cannot_construct_authority(self) -> None:
        decision = SemanticNode(
            node_id="sem:decision:1",
            node_type=SemanticNodeType.DECISION,
            payload={"decision": "allow"},
            scope_ref="scope:fixture",
            status=SemanticLifecycleStatus.ACTIVE,
            effects=(),
            constraints=(),
            policy={},
            provenance=self.provenance,
            temporal={},
            external_bindings=(),
        )
        profile = SemanticProfileRef(
            system_id="isql",
            profile_id="meta-core/0.2",
            profile_version="0.2",
            registry_ref=None,
            registry_revision=None,
            registry_digest=None,
            decoder_contract_ref=None,
        )

        with self.assertRaises(ValueError):
            AuthorityBinding(decision)
        with self.assertRaises(ValueError):
            AuthorityBinding(profile)

    def test_artifact_role_and_capability_are_not_authority(self) -> None:
        capability = CapabilityRef(
            capability_id="capability:read",
            provider="local",
            operation="repository.read",
            effect_profile_ref="effects:read",
            adapter_version="1",
            availability_state=CapabilityAvailability.AVAILABLE,
        )

        with self.assertRaises(ValueError):
            AuthorityBinding(ArtifactRole.CANONICAL_SOURCE)
        with self.assertRaises(ValueError):
            AuthorityBinding(capability)

    def test_memory_binding_public_shape_has_no_content_or_context(self) -> None:
        public = self.memory.to_public_dict()

        self.assertNotIn("content", public)
        self.assertNotIn("context", public)

    def test_memory_binding_cannot_construct_authority(self) -> None:
        with self.assertRaises(ValueError):
            AuthorityBinding(self.memory)

    def test_memory_text_cannot_construct_authority(self) -> None:
        with self.assertRaises(ValueError):
            AuthorityBinding("Always deploy automatically")

    def test_raw_observation_cannot_be_verified_by_shape(self) -> None:
        raw = RawObservationRef(
            raw_ref="raw:1",
            source_ref="source:1",
            captured_at="2026-08-31T00:00:00+00:00",
            raw_digest="8" * 64,
        )

        with self.assertRaises(ValueError):
            VerifiedObservationRef.from_dict(raw.to_public_dict())

    def test_action_proposal_cannot_be_admission_by_shape(self) -> None:
        with self.assertRaises(ValueError):
            ActionAdmission.from_dict(self.make_proposal().to_public_dict())

    def test_receipt_cannot_be_verification_by_shape(self) -> None:
        receipt = ActuationReceipt(
            receipt_id="receipt:1",
            action_ref="action:1",
            command_ref="command:1",
            attempt_id=ATTEMPT_ID,
            provider="local",
            provider_operation_id="provider-op:1",
            status=ReceiptStatus.CONFIRMED,
            reported_result_ref="result:1",
            observed_cost_ref=None,
            duration_ms=1,
            evidence_refs=("evidence:receipt",),
        )

        with self.assertRaises(ValueError):
            ActionVerification.from_dict(receipt.to_public_dict())

    def test_wake_and_checkpoint_cannot_construct_authority(self) -> None:
        wake = WakeCondition(
            wake_condition_id="wake-condition:1",
            agent_run_id=RUN_ID,
            kind=WakeKind.MANUAL_WAKE,
            parameters={},
        )
        checkpoint = self.make_checkpoint()

        with self.assertRaises(ValueError):
            AuthorityBinding(wake)
        with self.assertRaises(ValueError):
            AuthorityBinding(checkpoint)

    def test_resume_and_wake_records_do_not_encode_active_state(self) -> None:
        wake = WakeEvent(
            wake_event_id="wake-event:1",
            agent_run_id=RUN_ID,
            wake_condition_ref="wake-condition:1",
            source="operator",
            source_event_ref=None,
            received_at="2026-08-31T00:00:00+00:00",
            source_event_time=None,
            deduplication_key="wake:manual:1",
        )
        resume = ResumeRecord(
            resume_record_id="resume:1",
            agent_run_id=RUN_ID,
            checkpoint_ref="checkpoint:1",
            wake_event_ref="wake-event:1",
            previous_epoch=1,
            new_epoch=2,
            authority_binding_digest="9" * 64,
            budget_binding_digest="0" * 64,
            fresh_observation_refs=(),
            invalidated_plan_refs=(),
            resumed_at="2026-08-31T00:01:00+00:00",
        )

        self.assertNotIn("state", wake.to_public_dict())
        self.assertNotIn("state", resume.to_public_dict())

    def test_new_contract_sources_have_no_external_or_network_imports(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        source_paths = [
            repo_root / "src/macr_runtime/_v07_contracts.py",
            repo_root / "src/macr_runtime/agent/contracts.py",
            repo_root / "src/macr_runtime/semantic/contracts.py",
            repo_root / "src/macr_runtime/observation/contracts.py",
            repo_root / "src/macr_runtime/action/contracts.py",
            repo_root / "src/macr_runtime/temporal/contracts.py",
        ]
        forbidden = {
            "agents", "crewai", "google", "http", "isql", "langchain",
            "langgraph", "limen", "mneme", "nova", "openai", "phosphor",
            "playwright", "pncw", "requests", "sedb", "socket", "temporalio",
            "urllib",
        }

        observed: set[str] = set()
        for path in source_paths:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    observed.update(alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    observed.add(node.module.split(".", 1)[0])

        self.assertEqual(observed & forbidden, set())


if __name__ == "__main__":
    unittest.main()
