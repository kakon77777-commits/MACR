# MACR v0.7 Phase A Agent Contract Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Inline execution is fixed by operator direction; do not spawn subagents. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Implement and validate the MACR v0.7 Phase A Agent Contract Kernel without adding Agent runtime behavior, provider activity, storage, scheduling, or external semantic-runtime dependencies.

**Architecture:** Add five small contract packages above the existing MACR v0.6 core: agent, semantic, observation, action, and temporal. All records are frozen dataclasses with closed parsing, bounded JSON-compatible fields, deterministic serialization through macr_runtime.canonical, and family-local JSON Schema resources. Existing AuthorizationReference and DispatchContext semantics remain authoritative; EML-U, ISQL, NOVA, MNEME, ANDO, PNCW, and PHOSPHOR are referenced only through neutral typed bindings.

**Tech Stack:** Python 3.11+, standard-library dataclasses/Enum/uuid/json/importlib.resources/unittest, existing macr_runtime.canonical, existing macr_runtime.execution.AuthorizationReference, PowerShell verification wrappers, JSON Schema Draft 2020-12 documents with no new runtime dependency.

**Spec:** docs/macr-v0.7/MACR_v0.7_FIELD_INTEGRATION_BASELINE_2026-08-31.md

## Global Constraints

- Work only on branch workbench/v0.7-agent-contract-kernel.
- Baseline ancestry must include d3ecaf16de66fb7df326253fbd09df3aa353b5f4.
- Do not spawn subagents or delegate implementation/review.
- Network activity and provider generation must remain false.
- Do not call Grok, GLM, Gemini, MiniMax, Qwythos, Ollama, or any other provider.
- Do not read or import ISQL Origin material.
- Do not read private Residence memory or credentials.
- Keep runtime/test state on D: through existing MACR_STATE_ROOT and MACR_TEST_TMP conventions.
- Add no third-party dependency.
- Do not modify InteractionPlane or add AGENT to the existing dispatch enum.
- Do not change DispatchContext.run_id semantics.
- Do not create AgentRunner, lifecycle runtime, database, semantic graph store, observation adapter, action dispatcher, checkpoint store, scheduler, wake service, or reconciliation engine.
- Do not change project version from 0.6.0a1 during Phase A.
- Do not add new root-level exports to src/macr_runtime/__init__.py; consumers import from the five new subpackages.
- Preserve existing authority semantics; ArtifactRole describes canonicality and never grants execution permission.
- Every public Phase A record implements from_dict() and to_public_dict(); from_dict() rejects unknown and missing required fields.
- Preserve the 12 imported v0.7 design documents byte-for-byte.
- Each task follows RED, GREEN, focused regression, and commit.
- A failed test is evidence to investigate, not permission to weaken a contract.
- Phase A completion requires source, tests, schemas, negative controls, offline inherited regression, and a checkpoint.
- Stop after Phase A. Do not begin Phase B.

---

## Planned File Structure

Create:

~~~text
src/macr_runtime/_v07_contracts.py

src/macr_runtime/agent/__init__.py
src/macr_runtime/agent/contracts.py
src/macr_runtime/agent/schemas/agent-contracts-v1.schema.json

src/macr_runtime/semantic/__init__.py
src/macr_runtime/semantic/contracts.py
src/macr_runtime/semantic/schemas/semantic-contracts-v1.schema.json

src/macr_runtime/observation/__init__.py
src/macr_runtime/observation/contracts.py
src/macr_runtime/observation/schemas/observation-contracts-v1.schema.json

src/macr_runtime/action/__init__.py
src/macr_runtime/action/contracts.py
src/macr_runtime/action/schemas/action-contracts-v1.schema.json

src/macr_runtime/temporal/__init__.py
src/macr_runtime/temporal/contracts.py
src/macr_runtime/temporal/schemas/temporal-contracts-v1.schema.json

tests/test_v07_contract_support.py
tests/test_agent_contracts.py
tests/test_semantic_contracts.py
tests/test_observation_contracts.py
tests/test_action_contracts.py
tests/test_temporal_contracts.py
tests/test_agent_contract_boundaries.py
tests/test_v07_phase_a_manifest.py
tests/gates/v07_phase_a_contract_manifest.json

scripts/verify-v07-phase-a.ps1
docs/checkpoints/v07/PHASE_A_AGENT_CONTRACT_KERNEL.md
~~~

Modify:

~~~text
pyproject.toml
~~~

Responsibilities:

- _v07_contracts.py contains validation and digest helpers used only by the new Phase A packages.
- Each contracts.py owns one contract family and has no runtime side effects.
- Each package __init__.py exports only its own public contract types.
- Each family schema is an interoperability artifact, not a second runtime validator.
- The gate manifest maps required invariant/test IDs to exact unittest methods.
- verify-v07-phase-a.ps1 runs Phase A focused gates, inherited verification, offline assertions, and evidence preparation.

---

### Task 1: Shared Contract Support and Package Skeleton

**Files:**

- Create: src/macr_runtime/_v07_contracts.py
- Create: src/macr_runtime/agent/__init__.py
- Create: src/macr_runtime/semantic/__init__.py
- Create: src/macr_runtime/observation/__init__.py
- Create: src/macr_runtime/action/__init__.py
- Create: src/macr_runtime/temporal/__init__.py
- Modify: pyproject.toml
- Test: tests/test_v07_contract_support.py

**Interfaces:**

- Consumes: macr_runtime.canonical.canonical_json_bytes, sha256_id, aware_iso8601.
- Produces:
  - require_non_empty(name: str, value: object, max_bytes: int = 512) -> str
  - require_optional_non_empty(name: str, value: object | None, max_bytes: int = 512) -> str | None
  - require_sha256(name: str, value: object) -> str
  - require_uuid4(name: str, value: object) -> str
  - require_positive_int(name: str, value: object) -> int
  - require_non_negative_int(name: str, value: object) -> int
  - require_non_negative_number(name: str, value: object) -> int | float
  - require_json_value(name: str, value: object) -> object
  - require_json_object(name: str, value: object) -> dict[str, object]
  - freeze_json_value(name: str, value: object) -> object
  - public_json_value(value: object) -> object
  - require_closed_mapping(name: str, value: object, required: frozenset[str], optional: frozenset[str]) -> dict[str, object]
  - require_string_tuple(name: str, values: object, maximum: int = 128, unique: bool = True) -> tuple[str, ...]
  - canonical_record_digest(namespace: str, payload: object) -> str
  - normalize_timestamp(name: str, value: object) -> str

- [ ] **Step 1: Write failing support tests**

~~~python
class V07ContractSupportTests(unittest.TestCase):
    def test_digest_is_namespaced_and_key_order_independent(self):
        left = canonical_record_digest("macr.v07.test.v1", {"b": 2, "a": 1})
        right = canonical_record_digest("macr.v07.test.v1", {"a": 1, "b": 2})
        self.assertEqual(left, right)
        self.assertNotEqual(
            left,
            canonical_record_digest("macr.v07.other.v1", {"a": 1, "b": 2}),
        )

    def test_json_validation_rejects_nonfinite_and_arbitrary_objects(self):
        with self.assertRaisesRegex(ValueError, "finite JSON"):
            require_json_value("payload", {"x": float("nan")})
        with self.assertRaisesRegex(ValueError, "finite JSON"):
            require_json_value("payload", object())

    def test_integer_validators_reject_boolean(self):
        with self.assertRaises(ValueError):
            require_positive_int("revision", True)

    def test_frozen_json_cannot_drift_after_identity_is_created(self):
        source = {"nested": {"values": [1, 2]}}
        frozen = freeze_json_value("payload", source)
        before = canonical_record_digest("macr.v07.frozen.v1", frozen)
        source["nested"]["values"].append(3)
        self.assertEqual(public_json_value(frozen), {"nested": {"values": [1, 2]}})
        self.assertEqual(canonical_record_digest("macr.v07.frozen.v1", frozen), before)
~~~

- [ ] **Step 2: Run the support tests and confirm RED**

Run:

~~~powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -m unittest tests.test_v07_contract_support -v
~~~

Expected: import failure because macr_runtime._v07_contracts does not exist.

- [ ] **Step 3: Implement minimal shared validators**

~~~python
from __future__ import annotations

import math
import re
import uuid
from collections.abc import Mapping, Sequence

from .canonical import aware_iso8601, canonical_json_bytes, sha256_id

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def require_json_value(name: str, value: object) -> object:
    try:
        canonical_json_bytes(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be finite JSON") from exc
    return value


def canonical_record_digest(namespace: str, payload: object) -> str:
    return sha256_id(namespace, require_json_value("canonical payload", payload))
~~~

Implement every produced interface with bounded inputs and boolean rejection for integer/number validators.

- [ ] **Step 4: Create empty package entry points**

Each new __init__.py initially contains only a package docstring. Public exports are added by the owning family task.

- [ ] **Step 5: Add package-data patterns**

Extend pyproject.toml without changing runtime version:

~~~toml
[tool.setuptools.package-data]
macr_runtime = [
  "direct_ui/*.html",
  "direct_ui/*.js",
  "direct_ui/*.css",
  "agent/schemas/*.json",
  "semantic/schemas/*.json",
  "observation/schemas/*.json",
  "action/schemas/*.json",
  "temporal/schemas/*.json",
]
~~~

- [ ] **Step 6: Run focused tests**

~~~powershell
python -m unittest tests.test_v07_contract_support -v
python -m compileall -q src tests
~~~

Expected: all support tests pass; compileall exit 0.

- [ ] **Step 7: Run canonical regression**

~~~powershell
python -m unittest tests.test_canonical tests.test_contracts tests.test_execution -v
~~~

Expected: all pass.

- [ ] **Step 8: Commit**

~~~powershell
git add pyproject.toml src/macr_runtime/_v07_contracts.py src/macr_runtime/agent/__init__.py src/macr_runtime/semantic/__init__.py src/macr_runtime/observation/__init__.py src/macr_runtime/action/__init__.py src/macr_runtime/temporal/__init__.py tests/test_v07_contract_support.py
git commit -m "feat(agent): add v0.7 contract support"
~~~

---

### Task 2: AgentRun Identity and Binding Contracts

**Files:**

- Create: src/macr_runtime/agent/contracts.py
- Create: src/macr_runtime/agent/schemas/agent-contracts-v1.schema.json
- Modify: src/macr_runtime/agent/__init__.py
- Test: tests/test_agent_contracts.py

**Interfaces:**

- Consumes: Task 1 helpers, AuthorizationReference, and DispatchOrigin.
- Produces:
  - AgentRunState
  - AgentRunIdentity
  - GoalBinding
  - AuthorityBinding
  - BudgetBinding
  - SemanticStateBinding
  - PlanBinding
  - WorldBindingRef
  - MemoryBindingRef
  - AgentRunHeader
  - agent_run_subject_digest(...)
  - is_terminal_agent_run_state(state: AgentRunState) -> bool

- [ ] **Step 1: Write failing AgentRun tests**

~~~python
RUN_A = "11111111-1111-4111-8111-111111111111"
RUN_B = "22222222-2222-4222-8222-222222222222"


def test_same_subject_can_have_distinct_occurrence_ids(self):
    subject = agent_run_subject_digest(
        agent_ref="agent:fixture",
        origin=self.origin,
        goal=self.goal,
        authority=self.authority,
        budget=self.budget,
        world_bindings=(self.world,),
        memory_bindings=(),
    )
    first = AgentRunIdentity(RUN_A, subject)
    second = AgentRunIdentity(RUN_B, subject)
    self.assertNotEqual(first.agent_run_id, second.agent_run_id)
    self.assertEqual(first.subject_digest, second.subject_digest)


def test_memory_binding_is_reference_only_and_digest_bound(self):
    binding = MemoryBindingRef(
        memory_system_id="mneme",
        profile_id="MLF-RM/0.1",
        subject_ref="agent:fixture",
        head_ref="memory-head:1",
        head_digest="a" * 64,
        access_policy_ref="policy:read-only",
        projection_policy_ref="projection:bounded",
    )
    public = binding.to_public_dict()
    self.assertNotIn("content", public)
    self.assertEqual(public["binding_digest"], binding.binding_digest)
~~~

- [ ] **Step 2: Run tests and confirm RED**

~~~powershell
python -m unittest tests.test_agent_contracts -v
~~~

Expected: import failure because macr_runtime.agent.contracts does not exist.

- [ ] **Step 3: Implement enums and bindings**

~~~python
class AgentRunState(str, Enum):
    CREATED = "created"
    ADMITTED = "admitted"
    ACTIVE = "active"
    WAITING = "waiting"
    SUSPENDED = "suspended"
    WAKING = "waking"
    BLOCKED = "blocked"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
~~~

Every binding is frozen, validates refs/digests, provides to_public_dict(), computes a namespaced digest, and contains no raw content.

AuthorityBinding wraps the existing AuthorizationReference. It does not create a second authority store.

GoalBinding, BudgetBinding, SemanticStateBinding, PlanBinding, and WorldBindingRef each contain ref, digest, and revision. revision is at least 1. AuthorityBinding contains the existing AuthorizationReference plus a computed binding_digest. AgentRunIdentity contains agent_run_id and subject_digest only.

- [ ] **Step 4: Implement MemoryBindingRef**

Use this public shape:

~~~text
memory_system_id
profile_id
subject_ref
head_ref
head_digest
access_policy_ref
projection_policy_ref
binding_digest
~~~

head_ref and head_digest must be both present or both absent. Digest namespace is macr.agent.memory-binding.v1.

- [ ] **Step 5: Implement subject identity and AgentRunHeader**

The subject digest includes initial agent_ref, origin, goal, authority, budget, canonically sorted world-binding digests, and canonically sorted memory-binding digests. Caller input order is not semantic.

It excludes occurrence ID, runtime state/revision/epoch, created_at, and current semantic/plan bindings.

AgentRunHeader contains schema_version, identity, agent_ref, origin, state, state_revision, epoch, goal, authority, budget, semantic_state, active_plan, world_bindings, memory_bindings, parent_agent_run_id, delegation_ref, and created_at. It validates state_revision >= 1 and epoch >= 0 but implements no transition engine.

- [ ] **Step 6: Add the closed family schema**

Use:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:evemisslab:macr:agent-contracts:v1",
  "title": "MACR v0.7 Agent Contracts v1",
  "type": "object",
  "$defs": {}
}
~~~

Definitions include every public AgentRun/binding record with additionalProperties false.

- [ ] **Step 7: Export the family API and run tests**

~~~powershell
python -m unittest tests.test_agent_contracts tests.test_execution tests.test_authority -v
python -m compileall -q src tests
~~~

Expected: all pass.

- [ ] **Step 8: Commit**

~~~powershell
git add src/macr_runtime/agent tests/test_agent_contracts.py
git commit -m "feat(agent): add AgentRun contract family"
~~~

---

### Task 3: Semantic Envelope, Profile Binding, and Epistemic Contracts

**Files:**

- Create: src/macr_runtime/semantic/contracts.py
- Create: src/macr_runtime/semantic/schemas/semantic-contracts-v1.schema.json
- Modify: src/macr_runtime/semantic/__init__.py
- Test: tests/test_semantic_contracts.py

**Interfaces:**

- Consumes: Task 1 helpers.
- Produces SemanticNodeType, SemanticLifecycleStatus, ClaimStatus, ResolutionStatus, SemanticRelationType, BindingKind, ArtifactRole, SemanticProfileRef, ExternalSemanticBinding, SemanticProvenance, SemanticNode, SemanticRelation, SemanticEvent, and SemanticPatch.

- [ ] **Step 1: Write failing identity and epistemic tests**

~~~python
def test_same_content_different_provenance_has_same_content_digest(self):
    first = self.make_claim(origin_ref="worker:a")
    second = self.make_claim(origin_ref="worker:b")
    self.assertEqual(first.content_digest, second.content_digest)
    self.assertNotEqual(first.record_digest, second.record_digest)


def test_unresolved_ambiguity_and_obligation_round_trip(self):
    ambiguity = self.make_node("ambiguity", "unresolved")
    obligation = self.make_node("obligation", "unresolved")
    self.assertEqual(ambiguity.to_public_dict()["status"], "unresolved")
    self.assertEqual(obligation.to_public_dict()["status"], "unresolved")


def test_profile_binding_changes_record_not_content_identity(self):
    emlu = self.make_claim(profile=self.profile("eml-u"))
    isql = self.make_claim(profile=self.profile("isql-meta-core"))
    self.assertEqual(emlu.content_digest, isql.content_digest)
    self.assertNotEqual(emlu.record_digest, isql.record_digest)
~~~

- [ ] **Step 2: Write failing closed-vocabulary tests**

Prove unknown node, relation, status, binding kind, and artifact role values raise ValueError. Prove from_dict rejects authorized, committed, and verified boolean shortcuts.

- [ ] **Step 3: Run tests and confirm RED**

~~~powershell
python -m unittest tests.test_semantic_contracts -v
~~~

Expected: import failure for macr_runtime.semantic.contracts.

- [ ] **Step 4: Implement vocabularies**

~~~python
class SemanticNodeType(str, Enum):
    GOAL = "goal"
    TRIGGER = "trigger"
    OBSERVATION = "observation"
    CLAIM = "claim"
    HYPOTHESIS = "hypothesis"
    PLAN = "plan"
    TASK = "task"
    ACTION_PROPOSAL = "action_proposal"
    CONSTRAINT = "constraint"
    DECISION = "decision"
    RECEIPT = "receipt"
    VERIFICATION = "verification"
    CHECKPOINT = "checkpoint"
    FAILURE = "failure"
    WAKE_CONDITION = "wake_condition"
    AMBIGUITY = "ambiguity"
    OBLIGATION = "obligation"


class ClaimStatus(str, Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    SUPPORTED = "supported"
    CONTESTED = "contested"
    VERIFIED = "verified"
    REFUTED = "refuted"
    STALE = "stale"
    SUPERSEDED = "superseded"
    UNRESOLVED = "unresolved"


class ResolutionStatus(str, Enum):
    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"


class SemanticLifecycleStatus(str, Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    STALE = "stale"
    SUPERSEDED = "superseded"
    COMPLETED = "completed"
    FAILED = "failed"
~~~

Relation vocabulary is supports, contradicts, depends_on, derived_from, observes, describes, constrains, motivates, targets, affects, expects, produced, verifies, refutes, supersedes, revises, blocks, resolves, causes, precedes, follows, waits_for.

SemanticNode validates status by node family:

- CLAIM and HYPOTHESIS require ClaimStatus;
- AMBIGUITY and OBLIGATION require ResolutionStatus;
- all other node types require SemanticLifecycleStatus.

- [ ] **Step 5: Implement neutral profile and artifact records**

SemanticProfileRef fields:

~~~text
system_id profile_id profile_version registry_ref registry_revision
registry_digest decoder_contract_ref binding_digest
~~~

ExternalSemanticBinding fields:

~~~text
semantic_ref profile external_object_ref external_object_digest
binding_kind artifact_role binding_digest
~~~

ArtifactRole values are canonical_source, canonical_derived, derived_rebuildable, projection, cache_index, and legacy_compatibility. Do not use the word authority in the type or methods.

- [ ] **Step 6: Implement node, relation, event, and patch**

SemanticNode content identity includes node_type, payload, and scope_ref. Epistemic/lifecycle status is excluded from content identity so one claim keeps the same content digest while its evidence state changes. Record identity includes node_id, status, effects, constraints, policy, provenance, temporal metadata, external bindings, and content_digest.

SemanticEvent is append-only and carries parent refs. SemanticPatch carries a base_graph_digest and proposals only; it has no commit or authority flag.

- [ ] **Step 7: Add schema, exports, and focused tests**

Use schema ID urn:evemisslab:macr:semantic-contracts:v1 and include UNRESOLVED, AMBIGUITY, OBLIGATION, SemanticProfileRef, ExternalSemanticBinding, and ArtifactRole.

~~~powershell
python -m unittest tests.test_semantic_contracts tests.test_v07_contract_support -v
python -m compileall -q src tests
~~~

Expected: all pass.

- [ ] **Step 8: Commit**

~~~powershell
git add src/macr_runtime/semantic tests/test_semantic_contracts.py
git commit -m "feat(agent): add semantic envelope contracts"
~~~

---

### Task 4: Verified Observation Contracts

**Files:**

- Create: src/macr_runtime/observation/contracts.py
- Create: src/macr_runtime/observation/schemas/observation-contracts-v1.schema.json
- Modify: src/macr_runtime/observation/__init__.py
- Test: tests/test_observation_contracts.py

**Interfaces:**

- Consumes: Task 1 helpers.
- Produces FreshnessMode, ObservationVerificationRequirement, ObservationScope, FreshnessPolicy, RawObservationRef, ObservationIntent, VerifiedObservationRef, ObservationBinding, and ReObservationRequest.

- [ ] **Step 1: Write failing raw-versus-verified tests**

~~~python
def test_raw_observation_cannot_construct_verified_reference(self):
    raw = RawObservationRef(
        raw_ref="raw:1",
        source_ref="source:fixture",
        captured_at="2026-08-31T00:00:00+00:00",
        raw_digest="a" * 64,
    )
    self.assertNotIsInstance(raw, VerifiedObservationRef)
    with self.assertRaises(ValueError):
        VerifiedObservationRef.from_dict(raw.to_public_dict())


def test_verified_reference_requires_verification_and_visibility(self):
    with self.assertRaises(ValueError):
        self.make_verified(verification_digest=None)
    with self.assertRaises(ValueError):
        self.make_verified(visibility_commit_ref=None)
~~~

- [ ] **Step 2: Write failing freshness and scope tests**

Cover IMMUTABLE, SOURCE_REVISION, MAX_AGE, EVENT_INVALIDATED, ALWAYS_RECHECK_BEFORE_MUTATION, unknown mode rejection, empty scope, mixed revisions, and unknown fields.

- [ ] **Step 3: Run tests and confirm RED**

~~~powershell
python -m unittest tests.test_observation_contracts -v
~~~

Expected: import failure for macr_runtime.observation.contracts.

- [ ] **Step 4: Implement separate raw and verified paths**

Use exact vocabularies:

~~~python
class FreshnessMode(str, Enum):
    IMMUTABLE = "immutable"
    SOURCE_REVISION = "source_revision"
    MAX_AGE = "max_age"
    EVENT_INVALIDATED = "event_invalidated"
    ALWAYS_RECHECK_BEFORE_MUTATION = "always_recheck_before_mutation"


class ObservationVerificationRequirement(str, Enum):
    VERIFIED = "verified"
~~~

ObservationScope contains scope_ref, resource_refs, region_refs, and a computed scope_digest. Resource and region refs are unique, canonically sorted, bounded tuples; at least one is required.

FreshnessPolicy contains policy_id, mode, source_revision optional, max_age_seconds optional, invalidation_event_refs, and policy_digest. SOURCE_REVISION requires source_revision; MAX_AGE requires a positive finite max_age_seconds; EVENT_INVALIDATED requires at least one event ref; other modes reject those mode-specific fields.

ObservationIntent fields:

~~~text
observation_intent_id agent_run_id goal_ref plan_ref task_ref
world_binding_ref observation_purpose requested_scope
preferred_representation freshness_policy verification_requirement
intent_digest
~~~

VerifiedObservationRef fields:

~~~text
observation_ref_id agent_run_id observation_intent_ref
projection_request_ref projection_result_ref manifest_digest
verification_digest visibility_commit_ref source_identity source_revision
scope_digest projection_profile_digest visible_at observation_digest
~~~

VerifiedObservationRef contains no raw body, screenshot bytes, tool response, or verified boolean.

- [ ] **Step 5: Implement binding and re-observation records**

ObservationBinding binds one exact VerifiedObservationRef to agent_run_id, semantic_node_ref, world_binding_ref, basis_digest, and bound_at.

ReObservationRequest references a prior observation, optional action, requested scope, freshness policy, reason, and request digest.

- [ ] **Step 6: Add schema, exports, and focused tests**

Use schema ID urn:evemisslab:macr:observation-contracts:v1.

~~~powershell
python -m unittest tests.test_observation_contracts tests.test_semantic_contracts -v
python -m compileall -q src tests
~~~

Expected: all pass.

- [ ] **Step 7: Commit**

~~~powershell
git add src/macr_runtime/observation tests/test_observation_contracts.py
git commit -m "feat(agent): add verified observation contracts"
~~~

---

### Task 5: Action, Authority, Effect, Receipt, and Reconciliation Contracts

**Files:**

- Create: src/macr_runtime/action/contracts.py
- Create: src/macr_runtime/action/schemas/action-contracts-v1.schema.json
- Modify: src/macr_runtime/action/__init__.py
- Test: tests/test_action_contracts.py

**Interfaces:**

- Consumes Task 1 helpers and macr_runtime.execution.AuthorizationReference.
- Produces EffectName, EffectSet, CapabilityAvailability, CapabilityRef, BudgetEnvelope, AdmissionDecision, ActionProposal, ActionAdmission, CommandIntent, ActionAttemptState, ActionAttempt, ReceiptStatus, ActuationReceipt, VerificationVerdict, ActionVerification, ReconciliationClassification, and ReconciliationRecord.

- [ ] **Step 1: Write failing effect and authority tests**

~~~python
def test_unknown_effect_fails_closed(self):
    with self.assertRaises(ValueError):
        EffectSet.from_values(("repository.read", "world.unknown_mutation"))


def test_action_proposal_has_no_authorized_field(self):
    payload = self.valid_proposal_payload()
    payload["authorized"] = True
    with self.assertRaisesRegex(ValueError, "unknown fields"):
        ActionProposal.from_dict(payload)


def test_admission_requires_existing_authorization_reference(self):
    with self.assertRaises(ValueError):
        self.make_admission(authorization="user said yes")
~~~

- [ ] **Step 2: Write failing receipt, verification, and reconciliation tests**

~~~python
def test_receipt_and_verification_are_distinct_types(self):
    receipt = self.make_receipt(status=ReceiptStatus.CONFIRMED)
    verification = self.make_verification(
        verdict=VerificationVerdict.DIVERGED
    )
    self.assertNotIsInstance(receipt, ActionVerification)
    self.assertEqual(receipt.status, ReceiptStatus.CONFIRMED)
    self.assertEqual(verification.verdict, VerificationVerdict.DIVERGED)


def test_state_unknown_is_representable_and_not_success(self):
    record = self.make_reconciliation(
        classification=ReconciliationClassification.STATE_UNKNOWN
    )
    self.assertEqual(record.classification.value, "state_unknown")
    self.assertFalse(record.is_resolved)
~~~

- [ ] **Step 3: Run tests and confirm RED**

~~~powershell
python -m unittest tests.test_action_contracts -v
~~~

Expected: import failure for macr_runtime.action.contracts.

- [ ] **Step 4: Implement the closed MVP effect vocabulary**

~~~python
class EffectName(str, Enum):
    REPOSITORY_READ = "repository.read"
    REPOSITORY_WORKING_TREE_WRITE = "repository.working_tree.write"
    REPOSITORY_BRANCH_WRITE = "repository.branch.write"
    PROCESS_EXECUTE = "process.execute"
    SOFTWARE_DOMAIN_INSPECT = "software_domain.inspect"
    SOFTWARE_DOMAIN_PAUSE = "software_domain.pause"
    SOFTWARE_DOMAIN_RESUME = "software_domain.resume"
    SOFTWARE_DOMAIN_TEMPORAL_RATE_WRITE = (
        "software_domain.temporal_rate.write"
    )
~~~

EffectSet canonicalizes a unique sorted tuple, rejects empty/unknown values, exposes to_public_dict(), and computes effect_digest.

Use exact gate vocabularies:

~~~python
class CapabilityAvailability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    DISABLED = "disabled"
    UNSUPPORTED = "unsupported"


class AdmissionDecision(str, Enum):
    ALLOW = "allow"
    ALLOW_WITH_VERIFY = "allow_with_verify"
    REQUIRE_APPROVAL = "require_approval"
    DEFER = "defer"
    DENY = "deny"
    ESCALATE = "escalate"
~~~

- [ ] **Step 5: Implement capability and budget contracts**

BudgetEnvelope exact fields:

~~~text
budget_id agent_run_id provider_calls currency_cost_usd
wall_clock_seconds child_agent_count revision budget_digest
~~~

provider_calls and child_agent_count are non-negative integers. Currency and wall-clock values are finite non-negative numbers. Boolean values are rejected. revision is at least 1.

- [ ] **Step 6: Implement proposal, admission, and command**

ActionProposal contains proposal semantics only:

~~~text
action_id agent_run_id agent_run_epoch goal_ref plan_ref task_ref
operation target_ref parameters_ref declared_effects basis_refs
preconditions expected_result_ref rollback_policy_ref
verification_policy_ref provenance_ref proposal_digest
~~~

ActionAdmission binds:

~~~text
action_id proposal_digest decision effective_effects capability_refs
AuthorizationReference budget_digest budget_revision world_basis_digest
policy_snapshot_digest admission_digest
~~~

CommandIntent contains:

~~~text
command_intent_id action_ref operation target_ref parameter_ref
effective_effects admission_ref idempotency_ref
verification_policy_ref command_digest
~~~

Admission does not imply dispatch.

- [ ] **Step 7: Implement attempt, receipt, verification, and reconciliation**

Use exact state vocabularies:

~~~python
class ActionAttemptState(str, Enum):
    CREATED = "created"
    DISPATCHING = "dispatching"
    DISPATCHED = "dispatched"
    RECEIPT_CAPTURED = "receipt_captured"
    FAILED = "failed"


class ReceiptStatus(str, Enum):
    ACCEPTED = "accepted"
    APPLYING = "applying"
    CONFIRMED = "confirmed"
    PARTIAL = "partial"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    COMPENSATED = "compensated"
    EXPIRED = "expired"


class VerificationVerdict(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    DIVERGED = "diverged"
    UNKNOWN = "unknown"
    STALE = "stale"
~~~

ActionAttempt fields are attempt_id, action_ref, command_ref, provider_ref, state, started_at, finished_at optional, provider_operation_id optional, and attempt_digest.

ActuationReceipt fields are receipt_id, action_ref, command_ref, attempt_id, provider, provider_operation_id optional, status, reported_result_ref optional, observed_cost_ref optional, duration_ms optional, evidence_refs, and receipt_digest. It has no verified field.

ActionVerification fields are verification_id, action_ref, verification_kind, basis_refs, verdict, evidence_refs, verifier_ref, and verification_digest.

Reconciliation classifications:

~~~text
not_executed
executed_as_expected
executed_differently
partially_executed
state_unknown
compensation_required
~~~

ReconciliationRecord requires evidence refs. A resolution authority and resolved_at are allowed only when a resolution exists. STATE_UNKNOWN cannot claim resolved without higher-authority evidence.

- [ ] **Step 8: Add schema and exports**

Use schema ID urn:evemisslab:macr:action-contracts:v1. The schema must not contain combined fields named success_and_verified, authorized, or auto_retry.

- [ ] **Step 9: Run focused and authority regression**

~~~powershell
python -m unittest tests.test_action_contracts tests.test_authority tests.test_batch_authority tests.test_execution -v
python -m compileall -q src tests
~~~

Expected: all pass.

- [ ] **Step 10: Commit**

~~~powershell
git add src/macr_runtime/action tests/test_action_contracts.py
git commit -m "feat(agent): add governed action contracts"
~~~

---

### Task 6: Checkpoint, Suspend, Wake, Resume, and Temporal Contracts

**Files:**

- Create: src/macr_runtime/temporal/contracts.py
- Create: src/macr_runtime/temporal/schemas/temporal-contracts-v1.schema.json
- Modify: src/macr_runtime/temporal/__init__.py
- Test: tests/test_temporal_contracts.py

**Interfaces:**

- Consumes Task 1 helpers and MemoryBindingRef from macr_runtime.agent.contracts.
- Produces WakeKind, DependencyState, AgentCheckpoint, SuspendRecord, WakeCondition, WakeEvent, ResumeRecord, TemporalLease, and PendingDependency.

- [ ] **Step 1: Write failing checkpoint boundary tests**

~~~python
def test_checkpoint_rejects_runtime_handles_and_raw_secrets(self):
    payload = self.valid_checkpoint_payload()
    payload["provider_session_blob"] = object()
    with self.assertRaises(ValueError):
        AgentCheckpoint.from_dict(payload)


def test_checkpoint_memory_is_digest_reference_only(self):
    checkpoint = self.make_checkpoint(
        memory_binding_digests=("a" * 64,)
    )
    public = checkpoint.to_public_dict()
    self.assertEqual(public["memory_binding_digests"], ["a" * 64])
    self.assertNotIn("memory_content", public)
~~~

- [ ] **Step 2: Write failing wake and resume tests**

~~~python
def test_wake_condition_rejects_callable_predicate(self):
    with self.assertRaises(ValueError):
        WakeCondition(
            wake_condition_id="wake:1",
            agent_run_id=RUN_A,
            kind=WakeKind.WORLD_CONDITION,
            parameters={"predicate": lambda: True},
        )


def test_wake_event_cannot_encode_active_transition(self):
    payload = self.valid_wake_event_payload()
    payload["state"] = "active"
    with self.assertRaisesRegex(ValueError, "unknown fields"):
        WakeEvent.from_dict(payload)
~~~

- [ ] **Step 3: Run tests and confirm RED**

~~~powershell
python -m unittest tests.test_temporal_contracts -v
~~~

Expected: import failure for macr_runtime.temporal.contracts.

- [ ] **Step 4: Implement wake and dependency vocabularies**

Wake kinds:

~~~text
at_time
after_duration
external_event
domain_logical_time
world_condition
human_response
dependency_completed
provider_completed
budget_available
manual_wake
~~~

WakeCondition parameters are finite JSON and declarative.

Dependency states are pending, completed, failed, and cancelled.

- [ ] **Step 5: Implement AgentCheckpoint**

AgentCheckpoint exact groups:

~~~text
identity:
  checkpoint_id agent_run_id agent_run_epoch state_revision

goal:
  goal_ref goal_digest

authority:
  authority_ref authority_digest authority_revision authority_epoch

budget:
  budget_ref budget_digest budget_revision

semantic:
  semantic_state_ref semantic_state_digest semantic_state_revision

plan:
  active_plan_ref active_plan_digest active_plan_revision

continuation:
  world_basis_refs memory_binding_digests pending_action_refs
  reconciliation_refs verification_state_ref wake_condition_ref
  parent_checkpoint_ref created_at checkpoint_digest
~~~

No secret, session blob, process handle, callable, model cache, or raw memory field exists.

- [ ] **Step 6: Implement suspend, wake event, resume, lease, and dependency**

SuspendRecord fields are suspend_record_id, agent_run_id, checkpoint_ref, checkpoint_digest, wake_condition_ref optional, reason, suspended_at, and suspend_digest.

WakeEvent fields are wake_event_id, agent_run_id, wake_condition_ref, source, source_event_ref optional, received_at, source_event_time optional, deduplication_key, and wake_event_digest. There is no AgentRun state field.

ResumeRecord fields are resume_record_id, agent_run_id, checkpoint_ref, wake_event_ref, previous_epoch, new_epoch, authority_binding_digest, budget_binding_digest, fresh_observation_refs, invalidated_plan_refs, resumed_at, and resume_digest.

PendingDependency fields are dependency_id, agent_run_id, dependency_kind, target_ref, state, completion_ref optional, created_at, updated_at, and dependency_digest.

TemporalLease validates UUIDv4 lease_id, agent_run_id, owner_id, epoch >= 0, non-empty fencing_token, aware acquired_at/expires_at, and expires_at later than acquired_at.

ResumeRecord records revalidation refs/digests but does not set AgentRun state to ACTIVE.

- [ ] **Step 7: Add schema, exports, and focused tests**

Use schema ID urn:evemisslab:macr:temporal-contracts:v1.

~~~powershell
python -m unittest tests.test_temporal_contracts tests.test_agent_contracts tests.test_canonical -v
python -m compileall -q src tests
~~~

Expected: all pass.

- [ ] **Step 8: Commit**

~~~powershell
git add src/macr_runtime/temporal tests/test_temporal_contracts.py
git commit -m "feat(agent): add temporal continuation contracts"
~~~

---

### Task 7: Cross-Contract Boundaries and Required Gate Manifest

**Files:**

- Create: tests/test_agent_contract_boundaries.py
- Create: tests/test_v07_phase_a_manifest.py
- Create: tests/gates/v07_phase_a_contract_manifest.json
- Test: tests/test_agent_contract_boundaries.py
- Test: tests/test_v07_phase_a_manifest.py

**Interfaces:**

- Consumes all five Phase A contract families.
- Produces executable non-collapse evidence and manifest schema macr-v07-phase-a-test-manifest/v1.

- [ ] **Step 1: Write boundary tests**

~~~python
class AgentContractBoundaryTests(unittest.TestCase):
    def test_agent_run_id_is_not_dispatch_run_id_shortcut(self):
        self.assertFalse(hasattr(AgentRunIdentity, "to_dispatch_context"))

    def test_goal_text_and_semantic_decision_are_not_authority(self):
        decision = self.make_semantic_decision()
        self.assertNotIsInstance(decision, AuthorizationReference)

    def test_artifact_role_is_not_execution_authority(self):
        self.assertNotIsInstance(
            ArtifactRole.CANONICAL_SOURCE,
            AuthorizationReference,
        )

    def test_wake_event_and_checkpoint_are_not_authority_sources(self):
        self.assertNotIsInstance(self.wake_event, AuthorizationReference)
        self.assertNotIsInstance(self.checkpoint, AuthorizationReference)

    def test_unresolved_obligation_blocks_test_completion_fixture(self):
        with self.assertRaisesRegex(ValueError, "blocking obligation"):
            TestCompletionFixture(
                required_verification=self.verification,
                obligations=(self.unresolved_obligation,),
            )
~~~

TestCompletionFixture is test-local only. Do not add completion runtime source.

- [ ] **Step 2: Add import/dependency architecture tests**

Parse the new source files with ast and reject imports whose root is:

~~~text
langgraph langchain agents crewai temporalio playwright
mneme nova isql phosphor pncw sedb limen
~~~

Allow standard library and macr_runtime internal imports only.

- [ ] **Step 3: Run boundary tests and repair only owning contracts**

~~~powershell
python -m unittest tests.test_agent_contract_boundaries -v
~~~

Expected: initial failures identify a missing closed parser or boundary. Fix only that contract family; do not create runtime code.

- [ ] **Step 4: Create the gate manifest**

~~~json
{
  "schema": "macr-v07-phase-a-test-manifest/v1",
  "phase": "A",
  "required": [
    {
      "id": "AR-C01",
      "severity": "S1",
      "test": "tests.test_agent_contracts.AgentContractTests.test_valid_agent_run_header"
    }
  ]
}
~~~

Include every required ID from the approved handoff plus:

~~~text
SEM-X01 semantic profile neutrality
SEM-X02 artifact role is not authority
SEM-X03 unresolved state
SEM-X04 ambiguity preserved
SEM-X05 obligation preserved
SEM-X06 correction lineage
MEM-X01 memory binding is reference-only
MEM-X02 memory is not context
MEM-X03 memory text is not authority
~~~

- [ ] **Step 5: Write manifest integrity tests**

Prove exact schema/phase, unique IDs, unique unittest names, every named test exists, every S0/S1 entry runs in the wrapper, and no required entry is skipped. Load all five JSON Schema resources with importlib.resources, verify the expected unique schema IDs, require Draft 2020-12, reject unresolved internal references, and assert every modeled object definition sets additionalProperties to false.

- [ ] **Step 6: Run all Phase A contract tests**

~~~powershell
python -m unittest tests.test_v07_contract_support tests.test_agent_contracts tests.test_semantic_contracts tests.test_observation_contracts tests.test_action_contracts tests.test_temporal_contracts tests.test_agent_contract_boundaries tests.test_v07_phase_a_manifest -v
~~~

Expected: all pass.

- [ ] **Step 7: Run existing boundary regressions**

~~~powershell
python -m unittest tests.test_canonical tests.test_contracts tests.test_execution tests.test_authority tests.test_batch_authority tests.test_planning_contracts tests.test_coordinator_contract -v
~~~

Expected: all pass.

- [ ] **Step 8: Commit**

~~~powershell
git add tests/test_agent_contract_boundaries.py tests/test_v07_phase_a_manifest.py tests/gates/v07_phase_a_contract_manifest.json
git commit -m "test(agent): enforce Phase A contract boundaries"
~~~

---

### Task 8: Phase A Verification Wrapper, Evidence, and Stop Checkpoint

**Files:**

- Create: scripts/verify-v07-phase-a.ps1
- Create: docs/checkpoints/v07/PHASE_A_AGENT_CONTRACT_KERNEL.md
- Modify: tests/test_v07_phase_a_manifest.py
- Test: scripts/verify-v07-phase-a.ps1

**Interfaces:**

- Consumes the Phase A manifest and source/tests from Tasks 1–7.
- Produces an offline gate, one machine-readable PHASE_A_SUMMARY line, and one exact checkpoint.

- [ ] **Step 1: Write wrapper-presence tests first**

Extend manifest tests to read scripts/verify-v07-phase-a.ps1 and assert it names all eight new test modules and scripts/verify.ps1.

Run:

~~~powershell
python -m unittest tests.test_v07_phase_a_manifest -v
~~~

Expected: RED because the wrapper does not exist.

- [ ] **Step 2: Implement the Phase A wrapper**

The wrapper:

1. sets MACR_ROOT, MACR_STATE_ROOT, MACR_TEST_TMP, PYTHONPATH, and PYTHONDONTWRITEBYTECODE;
2. requires no provider credential;
3. runs the eight focused Phase A modules;
4. runs compileall;
5. calls scripts/verify.ps1 for inherited regression;
6. checks doctor network_activity is false;
7. records provider_generation false because no provider path is invoked;
8. checks git diff --check;
9. checks tracked worktree cleanliness;
10. emits one compact PHASE_A_SUMMARY JSON line.

Do not call verify-v06.ps1 inside the wrapper. Run it separately on the exact clean candidate.

- [ ] **Step 3: Run the focused wrapper**

~~~powershell
.\scripts\verify-v07-phase-a.ps1
~~~

Expected: exit 0, all Phase A tests pass, inherited regression passes, network_activity false, provider_generation false.

- [ ] **Step 4: Run complete inherited v0.6 gate**

~~~powershell
.\scripts\verify-v06.ps1
~~~

Expected: exit 0, V06_SUMMARY emitted, network_activity false, provider_generation false, git_clean true.

If the discovered test count is larger than 482, record the new exact count. Never copy the old count into the checkpoint.

- [ ] **Step 5: Run schema/package smoke**

Build in D-drive temporary state:

~~~powershell
python -m pip wheel . --no-deps --no-build-isolation --wheel-dir $env:MACR_TEST_TMP
~~~

Inspect the wheel members and assert all five schema JSON files are present. Do not publish the wheel.

- [ ] **Step 6: Commit verification infrastructure**

~~~powershell
git add scripts/verify-v07-phase-a.ps1 tests/test_v07_phase_a_manifest.py
git commit -m "test(agent): add Phase A verification gate"
~~~

- [ ] **Step 7: Run source-frozen gates**

~~~powershell
.\scripts\verify-v07-phase-a.ps1
.\scripts\verify-v06.ps1
git diff --check
git status --short
~~~

Record exact outputs. Any red required gate keeps Phase A incomplete.

- [ ] **Step 8: Write the exact Phase A checkpoint**

The checkpoint records:

~~~text
baseline commit
candidate commit and tree
branch
source files and schema IDs
test files and exact counts
focused gate
verify.ps1
verify-v06.ps1
compileall
wheel schema members
network activity
provider generation
known deferred items
NotMeasured
Phase A verdict
Phase B explicitly not started
~~~

- [ ] **Step 9: Commit the checkpoint**

~~~powershell
git add docs/checkpoints/v07/PHASE_A_AGENT_CONTRACT_KERNEL.md
git commit -m "docs(agent): seal Phase A contract checkpoint"
~~~

- [ ] **Step 10: Verify the final checkpoint commit**

~~~powershell
.\scripts\verify-v07-phase-a.ps1
.\scripts\verify-v06.ps1
git diff --check
git status --short
~~~

Expected: both wrappers exit 0, exact commit/tree recorded, no Phase B source, and no network/provider activity.

- [ ] **Step 11: Stop**

Report:

~~~text
Phase A = IMPLEMENTED / VALIDATED
Phase B = NOT STARTED
Agent runtime = NOT IMPLEMENTED
Live integration = NOT MEASURED
~~~

Do not create state.py, store.py, lifecycle.py, runner.py, planner.py, scheduler.py, or database migrations.

---

## Plan Self-Review Checklist

- [x] Every field-integration delta has an owning task.
- [x] External semantic/memory/runtime systems remain non-dependencies.
- [x] ISQL Origin is excluded.
- [x] MemoryBindingRef is reference-only.
- [x] UNRESOLVED, AMBIGUITY, and OBLIGATION have positive and negative tests.
- [x] ArtifactRole cannot be confused with AuthorizationReference.
- [x] Receipt and Verification remain separate types.
- [x] WakeEvent cannot encode ACTIVE.
- [x] Checkpoint contains no secret, process handle, model cache, or raw memory.
- [x] No InteractionPlane change.
- [x] No version bump.
- [x] No provider call.
- [x] Manifest discovers every required test ID.
- [x] Full inherited regression is rerun on the exact final commit.
- [x] Phase B is not started.

---

## Execution Mode

Operator direction fixes execution to:

> Inline Execution in this Codex task using superpowers:executing-plans.

No subagent-driven development and no delegated reviewer are authorized.
