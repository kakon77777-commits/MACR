# MACR v0.7 — Single-Agent MVP Implementation Plan & Verification Matrix v0.1

## Bounded Autonomous Agent Core 工程實作計畫、驗證矩陣與封閉條件 v0.1

**Document ID:** `MACR-V07-SINGLE-AGENT-MVP-PLAN-2026-v0.1`  
**Parent Architecture:** `MACR-ASR-CCA-2026-v0.1`  
**Specification Set:** `MACR-V07-01` through `MACR-V07-06`  
**Project:** MACR  
**Target Version:** `v0.7.0a1` — Single-Agent MVP Candidate  
**Engineering Baseline:** MACR `main`  
**Baseline HEAD at planning time:** `d3ecaf16de66fb7df326253fbd09df3aa353b5f4`  
**Date:** 2026-08-30  
**Status:** Canonical Implementation Plan / Pre-Implementation Gate  
**Organization:** EveMissLab / 一言諾科技有限公司  
**Language:** Traditional Chinese

---

# 摘要

MACR v0.7 的前六份 canonical specification 已經回答：

1. AgentRun 是什麼；
2. Agent canonical semantic state 是什麼；
3. Agent 如何提出但不能自行授權 Action；
4. Agent 如何透過 PNCW 得到 Verified Observation；
5. Agent 如何透過 PHOSPHOR-compatible actuation 改變 Software Spacetime；
6. Agent 如何 checkpoint、suspend、wake、resume。

本文件不再重新設計上述語義。

本文件回答：

> **如何在目前 MACR v0.6.0a1 的既有工程上，以最小破壞方式，真正完成第一個可執行的 bounded autonomous Agent。**

v0.7.0a1 的目標不是：

- 完整 Multi-Agent；
- Agent Society；
- unrestricted autonomy；
- EML-U 全實作；
- SEDB vNext；
- 全面 PHOSPHOR provider migration；
- production distributed scheduler；
- 長期 Resident AI；
- 把所有 EveMissLab 系統合併成 monolith。

v0.7.0a1 的目標只有一個：

$$
\boxed{
\text{One AgentRun can safely observe, plan, act, verify, checkpoint, suspend, resume, and finish.}
}
$$

更完整地：

$$
\boxed{
Goal
\rightarrow
Observe
\rightarrow
Plan
\rightarrow
Propose
\rightarrow
Authorize
\rightarrow
Act
\rightarrow
Reobserve
\rightarrow
Verify
\rightarrow
Persist
\rightarrow
Continue/Suspend/Stop
}
$$

並且在任一未知 external-effect 狀態下：

$$
\boxed{
UnknownAfterDispatch
\Rightarrow
ReconciliationRequired
}
$$

不得 blind retry。

---

# 0. Engineering Ground Rule

v0.7.0 採：

$$
\boxed{
\text{Add Agent Plane Above Existing MACR Core}
}
$$

而不是：

$$
\boxed{
\text{Rewrite MACR Core Around Agent Framework}
}
$$

目前 MACR 已經有：

```text
authority
batch authority
canonical serialization / identity
provider registry
provider execution
candidate vault
accounting
coordination plan
coordinator contract
route resolution
plan runtime
operational events
CLI
Direct Chat
T1 queue / worker
```

v0.7 應重用這些。

---

# 1. Non-Rewrite Rule

以下既有 component 不應在 Phase A–H 中被大規模重寫：

```text
authority.py
batch_authority.py
accounting.py
candidate_vault.py
canonical.py
contracts.py
execution.py
coordination.py
coordinator_contract.py
plan_runtime.py
provider registry/runtime
Direct Chat storage
```

只有當新增 Agent contract 明確需要 extension 時，才做 additive change。

---

# 2. New Primary Packages

建議新增：

```text
src/macr_runtime/
├─ agent/
├─ semantic/
├─ observation/
├─ action/
└─ temporal/
```

---

# 3. Separation from Existing Core

建議 dependency direction：

```text
agent/
  ↓
semantic/
observation/
action/
temporal/
  ↓
existing MACR shared core
```

禁止：

```text
existing shared core
  ↓
agent/
```

除非是非常薄的 interface extension。

這避免 v0.6 provider/runtime core 被 v0.7 Agent semantics反向污染。

---

# 4. No New Agent Framework Dependency

v0.7.0a1 不新增：

```text
LangGraph
AutoGen
OpenAI Agents SDK
CrewAI
smolagents
```

作 mandatory runtime dependency。

可以閱讀其實作作為 reference。

不把它們放入 canonical dependency graph。

---

# 5. Implementation Phases

正式工程切成：

```text
Phase A — Contract Kernel
Phase B — AgentRun State Kernel
Phase C — Semantic Working State
Phase D — Verified Observation
Phase E — Action / Authority / Effect
Phase F — Temporal Continuation
Phase G — Closed-Loop Single Agent
Phase H — Failure Injection / Final Verification
```

---

# 6. Phase Ordering

$$
A
\rightarrow
B
\rightarrow
C
\rightarrow
D
\rightarrow
E
\rightarrow
F
\rightarrow
G
\rightarrow
H
$$

其中：

- A–C 建立 Agent 本體；
- D 建立 perception；
- E 建立 action；
- F 建立 time；
- G 完成 loop；
- H 證明不能亂動。

---

# 7. Definition of Done

任何 Phase 的「文件完成」不等於 Phase 完成。

Phase completion 必須：

```text
source
+
tests
+
negative controls
+
evidence
```

都存在。

---

# 8. Phase A — Contract Kernel

## Goal

把前六份 specification 中最小 executable contract 固定為 Python types + JSON schemas + canonical serialization。

---

# 9. Phase A New Files

建議：

```text
src/macr_runtime/agent/contracts.py
src/macr_runtime/agent/types.py

src/macr_runtime/semantic/contracts.py

src/macr_runtime/observation/contracts.py

src/macr_runtime/action/contracts.py

src/macr_runtime/temporal/contracts.py
```

以及：

```text
schemas/agent/
schemas/semantic/
schemas/observation/
schemas/action/
schemas/temporal/
```

若現行 repo 尚無統一 `schemas/` root，可先在：

```text
src/macr_runtime/.../schemas
```

或 package data 中保存，再於後續 release 重整。

---

# 10. Phase A Core Agent Types

至少：

```text
AgentRunId
AgentRunState
AgentRunEpoch
AgentRunRevision

GoalBinding
AuthorityBinding
BudgetBinding

WorldBinding
PlanBinding
SemanticStateBinding
```

---

# 11. AgentRunState Enum

```text
CREATED
ADMITTED
ACTIVE
WAITING
SUSPENDED
WAKING
BLOCKED
RECONCILIATION_REQUIRED
COMPLETED
FAILED
CANCELLED
```

---

# 12. Terminal States

```text
COMPLETED
FAILED
CANCELLED
```

定義：

$$
Terminal(R)
=
R.state
\in
\{
COMPLETED,
FAILED,
CANCELLED
\}
$$

---

# 13. Phase A Semantic Types

至少：

```text
SemanticNode
SemanticRelation
SemanticEvent
SemanticPatch
SemanticGraphHead
```

Node types：

```text
goal
observation
plan
task
action_proposal
constraint
decision
receipt
verification
failure
checkpoint
wake_condition
```

---

# 14. Phase A Action Types

至少：

```text
ActionProposal
EffectSet
CapabilityRef
AuthorityEnvelopeRef
BudgetEnvelopeRef
AdmissionDecision
ActionAdmission
CommandIntent
ActionAttempt
ActuationReceipt
ActionVerification
ReconciliationRecord
```

---

# 15. Admission Decision Enum

```text
ALLOW
ALLOW_WITH_VERIFY
REQUIRE_APPROVAL
DEFER
DENY
ESCALATE
```

---

# 16. Phase A Observation Types

至少：

```text
ObservationIntent
FreshnessPolicy
VerifiedObservationRef
ObservationBinding
ReObservationRequest
```

---

# 17. Phase A Temporal Types

至少：

```text
AgentCheckpoint
SuspendRecord
WakeCondition
WakeEvent
ResumeRecord
TemporalLease
PendingDependency
```

---

# 18. Canonical Serialization

所有新 semantic / state identity 必須使用：

```text
macr_runtime.canonical
```

現有 canonical helper應成為唯一入口。

不得各 package：

```text
json.dumps(...)
```

自行算 semantic digest。

---

# 19. Canonical Extension Gate

若現有 canonical serializer無法表示新需要的 data：

只允許：

```text
extend canonical profile
+
add differential tests
```

不得 package-local workaround。

---

# 20. Phase A Tests

新增：

```text
tests/test_agent_contracts.py
tests/test_semantic_contracts.py
tests/test_observation_contracts.py
tests/test_action_contracts.py
tests/test_temporal_contracts.py
```

---

# 21. Phase A Required Tests

至少驗：

- enum；
- required fields；
- unknown fields；
- ID validation；
- digest；
- immutable records；
- unknown node type；
- unknown effect；
- invalid wake kind；
- malformed authority binding；
- negative integer revision；
- invalid epoch；
- noncanonical payload。

---

# 22. Phase A Gate

Phase A PASS：

$$
ContractsValid
\land
CanonicalDigestStable
\land
InheritedTestsGreen
$$

---

# 23. Phase B — AgentRun State Kernel

## Goal

完成第一個 durable AgentRun object。

還沒有真正 autonomous loop。

---

# 24. Phase B Suggested Files

```text
src/macr_runtime/agent/state.py
src/macr_runtime/agent/lifecycle.py
src/macr_runtime/agent/store.py
src/macr_runtime/agent/events.py
src/macr_runtime/agent/ownership.py
src/macr_runtime/agent/service.py
```

---

# 25. Agent Store

建議：

```text
runtime/agent.sqlite3
```

第一版不要塞進：

```text
direct conversation DB
```

---

# 26. Required Tables

最低：

```text
agent_runs
agent_events
agent_goals
agent_world_bindings
agent_plan_bindings
agent_children
```

後面 Phase E/F 再擴 action/checkpoint tables。

---

# 27. agent_runs

保存 current operational projection：

```text
agent_run_id
state
state_revision
epoch
goal_ref
authority_ref
budget_ref
semantic_state_ref
active_plan_ref
latest_checkpoint_ref
created_at
updated_at
```

---

# 28. agent_events

append-only：

```text
event_id
agent_run_id
epoch
before_revision
after_revision
event_type
payload_json
created_at
```

---

# 29. Revision Rule

每次 state mutation：

$$
r_{n+1}=r_n+1
$$

---

# 30. Revision Compare-and-Swap

State mutation API要求：

```text
expected_revision
```

不符：

```text
STALE_AGENT_RUN_REVISION
```

---

# 31. Epoch Fence

所有 privileged state transitions帶：

```text
expected_epoch
```

不符：

```text
STALE_AGENT_RUN_EPOCH
```

---

# 32. Lifecycle Transition Table

建立 deterministic transition table。

不能 scattering：

```python
if state == ...
```

到多個 modules。

---

# 33. Ownership

建立：

```text
owner_id
lease_id
fencing_token
lease_expiry
epoch
```

---

# 34. Initial Ownership Scope

v0.7.0 只支援：

```text
single-machine
cross-process
```

不支援 distributed leader election。

---

# 35. Phase B API

```text
create_agent_run()
admit_agent_run()
activate_agent_run()

get_agent_run()
list_agent_runs()

block_agent_run()
fail_agent_run()
cancel_agent_run()
complete_agent_run()

acquire_agent_run()
release_agent_run()
```

---

# 36. Completion Not Yet Autonomous

Phase B 的 `complete_agent_run()` 只能供 host/runtime tests。

Agent 本身還不能自己完成。

---

# 37. Phase B Tests

新增：

```text
tests/test_agent_state.py
tests/test_agent_lifecycle.py
tests/test_agent_store.py
tests/test_agent_ownership.py
```

---

# 38. Phase B Negative Controls

至少：

```text
duplicate AgentRun id
illegal CREATED→ACTIVE
terminal→ACTIVE
skipped revision
revision rollback
stale writer
two owners
stale fencing token
old epoch mutation
event/state disagreement
```

---

# 39. Crash Rebuild Test

刪除 current state projection後：

從：

```text
agent_events
```

重建 current AgentRun。

result 必須相同。

---

# 40. Phase B Gate

$$
AgentStateRecoverable
\land
RevisionFenced
\land
OwnershipFenced
\land
InheritedTestsGreen
$$

---

# 41. Phase C — Semantic Working State

## Goal

讓 AgentRun 不靠 conversation history 作 canonical cognition state。

---

# 42. Suggested Files

```text
src/macr_runtime/semantic/registry.py
src/macr_runtime/semantic/store.py
src/macr_runtime/semantic/graph.py
src/macr_runtime/semantic/patch.py
src/macr_runtime/semantic/projection.py
src/macr_runtime/semantic/validation.py
```

---

# 43. Storage

第一版可：

```text
runtime/agent-semantics.sqlite3
```

或與 agent DB 共用同一 SQLite、不同 tables。

推薦初期同 DB transaction較簡單：

```text
agent.sqlite3
```

但 schema responsibility分開。

---

# 44. Semantic Tables

```text
semantic_nodes
semantic_relations
semantic_events
semantic_graph_heads
semantic_patches
semantic_registry
```

---

# 45. Content vs Record Digest

每個 node：

$$
D_{content}
$$

與：

$$
D_{record}
$$

分離。

---

# 46. Patch Workflow

```text
Model / Worker
↓
SemanticPatch Proposal
↓
Schema Validation
↓
Registry Validation
↓
Base Graph Check
↓
Atomic Commit
↓
New Graph Revision
```

---

# 47. No Direct Model Mutation

不存在：

```text
model_output_to_db()
```

必須：

```text
model_output
→ parser/compiler
→ SemanticPatch
→ validator
```

---

# 48. Minimal Semantic Graph

v0.7.0a1 實際 Agent loop只要求：

```text
Goal
Observation
Plan
ActionProposal
Decision
Receipt
Verification
Failure
Checkpoint
```

Claim/Hypothesis可在同 Phase完成，但不是 closed-loop blocker。

---

# 49. Context Projection

建立：

```text
build_agent_context(agent_run_id, provider_profile)
```

輸入 semantic graph。

輸出：

```text
provider-ready context projection
```

---

# 50. Context Projection Is Ephemeral

不直接寫回 canonical graph。

---

# 51. Phase C Tests

```text
tests/test_semantic_registry.py
tests/test_semantic_store.py
tests/test_semantic_graph.py
tests/test_semantic_patch.py
tests/test_semantic_projection.py
```

---

# 52. Phase C Negative Controls

```text
unknown node
unknown relation
dangling relation
silent overwrite
stale base graph
partial patch commit
scope escalation
context omission deletes node
model-created authorizes relation treated real authority
```

---

# 53. Phase C Gate

要求至少證明：

```text
Goal → Plan
```

可完全不依賴 conversation DB 存在。

---

# 54. Phase D — Verified Observation

## Goal

完成第一條：

$$
World
\rightarrow
VerifiedObservation
\rightarrow
AgentSemanticState
$$

---

# 55. Initial Observation Strategy

v0.7.0a1 不需要一開始就把 production PNCW external repo wiring做滿。

使用兩層：

```text
PncwObservationPort
FakePncwObservationPort
```

然後再接 real bridge。

---

# 56. Suggested Files

```text
src/macr_runtime/observation/intent.py
src/macr_runtime/observation/compiler.py
src/macr_runtime/observation/pncw_port.py
src/macr_runtime/observation/freshness.py
src/macr_runtime/observation/binding.py
src/macr_runtime/observation/service.py
```

---

# 57. Port Interface

概念：

```text
request(intent)
→ readiness
→ projection
→ verification
→ visibility
→ VerifiedObservationRef
```

MACR不需要知道 PNCW内部 classes。

---

# 58. Fake PNCW

Fake port 必須保留真實 lifecycle：

```text
REQUESTED
RESOLVED
READY
PROJECTED
VERIFIED
VISIBLE
```

不能 shortcut：

```text
intent → observation
```

否則測不到 boundary。

---

# 59. Initial World Provider

第一個 Agent MVP 可以先用：

```text
bounded repository fixture
```

或：

```text
PHOSPHOR mock domain
```

---

# 60. Repository Observation Fixture

需要：

```text
revision
file digests
test result
working-tree state
```

形成 deterministic observation。

---

# 61. Observation Binding

只有：

```text
VISIBLE
```

才能：

```text
agent.observation_bound
```

---

# 62. ASE Mapping

VerifiedObservationRef：

```text
→ observation node
→ semantic graph revision
→ AgentRun observation basis
```

在 local DB 中原子完成。

---

# 63. Freshness

至少兩種：

```text
IMMUTABLE
SOURCE_REVISION
```

v0.7.0a1 即可。

---

# 64. Stale Test

```text
observe revision A
external change to B
attempt action based on A
```

必須阻止。

---

# 65. Phase D Tests

```text
tests/test_observation_service.py
tests/test_observation_freshness.py
tests/test_observation_binding.py
tests/test_pncw_bridge_fake.py
```

如果接 real PNCW：

```text
tests/integration/test_pncw_observation_bridge.py
```

---

# 66. Phase D Negative Controls

```text
READY treated as observation
VERIFIED treated as visible
raw tool response promoted
stale observation reused
mixed revisions
cache hit considered freshness
scope escalation
failed verification bound
```

---

# 67. Phase D Gate

$$
VerifiedObservationBound
\land
StaleObservationRejected
\land
NoRawObservationPromotion
$$

---

# 68. Phase E — Action / Authority / Effect

## Goal

讓 Agent 第一次可以提出真正 Action，但不能自行取得權限。

---

# 69. Suggested Files

```text
src/macr_runtime/action/effects.py
src/macr_runtime/action/capabilities.py
src/macr_runtime/action/authority_adapter.py
src/macr_runtime/action/budget.py
src/macr_runtime/action/policy.py
src/macr_runtime/action/admission.py
src/macr_runtime/action/command.py
src/macr_runtime/action/dispatch.py
src/macr_runtime/action/verification.py
src/macr_runtime/action/reconciliation.py
```

---

# 70. Reuse Existing Authority

不要寫：

```text
AgentAuthorityStoreV2
```

重複現有 authority。

應做：

```text
AgentAuthorityAdapter
```

把 Agent action effect/scope轉成現有 `AuthorizationReference` / authority service可驗的 contract。

---

# 71. Existing Authorization Reuse

沿用：

```text
digest
revision
epoch
scope
```

Agent ActionAdmission額外保存：

```text
effective_effects
target_scope
```

---

# 72. Effect Registry MVP

第一版至少：

```text
repository.read
repository.working_tree.write
repository.branch.write
process.execute
software_domain.inspect
software_domain.pause
software_domain.resume
software_domain.temporal_rate.write
```

---

# 73. Initial Safe Write Surface

不要讓 v0.7.0a1 一開始：

```text
main branch write
release publish
email send
credential export
```

進 autonomous ALLOW。

第一版 mutation target應限定：

```text
temporary workspace
fixture repository
feature branch
mock / bounded software domain
```

---

# 74. Policy MVP

最低：

```text
READ_ONLY → ALLOW
LOCAL_COMPUTE → ALLOW
REVERSIBLE_LOCAL_MUTATION → ALLOW_WITH_VERIFY
SHARED_MUTATION → REQUIRE_APPROVAL
IRREVERSIBLE → REQUIRE_APPROVAL / DENY
UNKNOWN → DEFER
```

---

# 75. Budget MVP

至少：

```text
provider_calls
wall_clock_seconds
currency_cost_usd
```

若完全 offline fake provider：

currency仍可存在為：

```text
0.0
```

但 schema不能省。

---

# 76. Action State Store

新增：

```text
agent_actions
action_admissions
command_intents
action_attempts
actuation_receipts
action_verifications
action_reconciliation
```

---

# 77. Action Admission

formal：

$$
Admit(a)
=
SemanticValid
\land
EffectsKnown
\land
Capability
\land
Authority
\land
Budget
\land
Policy
\land
FreshBasis
\land
NoReconciliation
$$

---

# 78. Reuse Existing Execution

真正 model/worker call：

繼續用：

```text
MacrRuntime.invoke()
PlanRuntime.execute()
DispatchContext
Candidate Vault
Accounting
```

AgentRun只是 parent lineage。

---

# 79. DispatchContext Extension

建議 additive optional fields：

```text
agent_run_id
agent_run_epoch
agent_action_id
agent_semantic_context_digest
```

若現有 dataclass compatibility不宜立即改，可先透過：

```text
DispatchOrigin
member_digest
event metadata
```

建立 side binding。

但最終應正式 typed extension。

---

# 80. One-Attempt

Action attempt預設：

$$
Attempts_{automatic}\le1
$$

---

# 81. Verification

第一次 MVP 必須真正有：

```text
before observation
action
receipt
after observation
verification
```

---

# 82. Verification Example

repository patch：

```text
file digest before
↓
patch
↓
file digest after
↓
tests
```

---

# 83. Reconciliation

任何：

```text
dispatch happened
receipt persistence uncertain
```

進：

```text
RECONCILIATION_REQUIRED
```

---

# 84. Phase E Tests

```text
tests/test_effect_registry.py
tests/test_action_capability.py
tests/test_agent_authority_adapter.py
tests/test_agent_budget.py
tests/test_action_policy.py
tests/test_action_admission.py
tests/test_action_dispatch.py
tests/test_action_verification.py
tests/test_action_reconciliation.py
```

---

# 85. Phase E Negative Controls

```text
tool exists but no authority
authority exists but no capability
unknown effect allowed
omitted effect bypass
stale authority
expired authority
stale basis
budget exceeded
silent fallback
receipt==verification
unknown-after-dispatch retry
reconciliation mutation
```

---

# 86. Phase E Gate

必須證明：

$$
ActionProposal
\not\Rightarrow
Dispatch
$$

以及：

$$
ReceiptSuccess
\not\Rightarrow
VerifiedSuccess
$$

---

# 87. Phase F — Temporal Continuation

## Goal

完成：

```text
Checkpoint
→ Suspend
→ Process Death
→ Wake
→ Revalidate
→ Resume
```

---

# 88. Suggested Files

```text
src/macr_runtime/temporal/checkpoint.py
src/macr_runtime/temporal/suspend.py
src/macr_runtime/temporal/wake.py
src/macr_runtime/temporal/scheduler.py
src/macr_runtime/temporal/resume.py
src/macr_runtime/temporal/dependency.py
```

---

# 89. Tables

```text
agent_checkpoints
agent_checkpoint_heads
agent_suspend_records
agent_wake_conditions
agent_wake_events
agent_temporal_leases
agent_pending_dependencies
```

---

# 90. Supported MVP Wake Kinds

第一輪：

```text
AFTER_DURATION
AT_TIME
MANUAL_WAKE
DEPENDENCY_COMPLETED
PROVIDER_COMPLETED
```

---

# 91. Deferred Wake Types

可留 Phase F2：

```text
EXTERNAL_EVENT
WORLD_CONDITION
DOMAIN_LOGICAL_TIME
HUMAN_RESPONSE
BUDGET_AVAILABLE
```

架構已支援，但 v0.7.0a1 不需要全部 live provider整合。

---

# 92. Scheduler

單一 local scheduler process / service。

最高要求不是高 throughput。

而是：

```text
durable
rebuildable
duplicate-safe
```

---

# 93. Checkpoint Promotion

需 transaction：

```text
write checkpoint
verify
promote head
write event
```

---

# 94. Suspend Gate

$$
CheckpointDurable
\land
OpenReconciliation=0
$$

---

# 95. Wake Gate

Wake：

```text
SUSPENDED → WAKING
```

不是：

```text
SUSPENDED → ACTIVE
```

---

# 96. WAKING Mandatory Checks

```text
checkpoint
ownership
authority
budget
pending action
reconciliation
world basis
goal
plan
```

---

# 97. Process Kill Acceptance

這是 Phase F 必測：

```text
create run
suspend
kill process
restart
wake
resume
```

不能只用同 process function call模擬。

---

# 98. Phase F Tests

```text
tests/test_agent_checkpoint.py
tests/test_agent_suspend.py
tests/test_agent_wake.py
tests/test_agent_scheduler.py
tests/test_agent_resume.py
tests/test_agent_temporal_ownership.py
```

---

# 99. Phase F Integration Test

```text
tests/integration/test_agent_process_restart.py
```

使用 child process真正 terminate/restart。

---

# 100. Phase F Negative Controls

```text
suspend without checkpoint
suspend with unknown effect
duplicate wake
wake terminal run
wake bypass authority
wake bypass observation
checkpoint restores old authority
stale plan executes
two resume owners
```

---

# 101. Phase F Gate

$$
DurableSuspendResume
\land
NoDuplicateResume
\land
RevalidationRequired
$$

---

# 102. Phase G — Closed-Loop Single Agent

## Goal

把 B–F 串成真正 Agent Runtime。

---

# 103. Suggested Files

```text
src/macr_runtime/agent/runner.py
src/macr_runtime/agent/loop.py
src/macr_runtime/agent/planner.py
src/macr_runtime/agent/context.py
src/macr_runtime/agent/completion.py
```

---

# 104. Agent Planner Interface

```text
Planner.plan(
    goal,
    semantic_context,
    capabilities,
    constraints,
    budget,
)
→ PlanProposal
```

Planner 可以是：

```text
fake deterministic planner
provider-backed planner
```

---

# 105. First Planner

先實作：

```text
DeterministicFixturePlanner
```

用於 conformance。

再接：

```text
MacrModelPlanner
```

---

# 106. Why Deterministic First

如果一開始直接用 real LLM：

Agent loop failure可能來自：

- state machine；
- provider；
- prompt；
- action compiler；
- planner randomness。

難以分離。

---

# 107. Model Planner

第二個 planner透過現有 MACR provider runtime。

仍然：

```text
Model output
→ PlanProposal
→ semantic validation
```

不直接控制 loop。

---

# 108. Canonical Loop

```text
load AgentRun
↓
ensure ACTIVE
↓
resolve Goal
↓
resolve fresh Observation Basis
↓
build Context
↓
Planner
↓
SemanticPatch / Plan
↓
if observation needed:
    observe
↓
if action needed:
    ActionProposal
    → admission
    → act
    → reobserve
    → verify
↓
checkpoint
↓
completion check
↓
continue / suspend / block / stop
```

---

# 109. Loop Bound

每個 activation必須有：

```text
max_steps
max_provider_calls
max_wall_clock
```

避免：

```text
while true
```

---

# 110. Step

一個 Agent step 是 runtime semantic transition。

不等於一個 model call。

---

# 111. Step Kinds

```text
OBSERVE
PLAN
ACT
VERIFY
CHECKPOINT
SUSPEND
COMPLETE
BLOCK
```

---

# 112. Completion

Agent只能提出：

```text
CompletionProposal
```

Runtime驗：

$$
GoalSatisfied
\land
RequiredVerificationPassed
\land
NoBlockingFailure
\land
OpenReconciliation=0
$$

---

# 113. First Closed-Loop MVP Scenario

Canonical Scenario：

> **在 bounded fixture repository 中找出失敗測試原因，修改 feature workspace，重新測試並驗證。**

---

# 114. Scenario Setup

Fixture repo：

```text
one intentional failing test
one bounded bug
one expected repair
```

Agent authority：

```text
repository.read
process.execute
repository.working_tree.write
```

禁止：

```text
repository.main.write
network.write
credential.*
```

---

# 115. Scenario Flow

```text
Goal
↓
Observe repo
↓
Observe failing test
↓
Plan
↓
Run test
↓
Observe failure
↓
Propose patch
↓
Action Gate
↓
Apply patch
↓
Receipt
↓
Reobserve file
↓
Run test
↓
Verification
↓
Checkpoint
↓
Completion
```

---

# 116. Success Criteria

```text
target test passes
all required inherited fixture tests pass
only allowed path changed
no network
no secret access
no main mutation
verified after-state
AgentRun COMPLETED
```

---

# 117. Real Model Scenario

在 deterministic scenario pass後：

同 fixture使用一個 real configured model。

目標不是：

```text
模型一定修得出所有 bug
```

而是：

> 即使模型提錯 plan/action，Runtime仍保持安全。

---

# 118. Real Model Failure Is Allowed

如果模型無法解題：

```text
AgentRun BLOCKED / FAILED
```

仍可算 runtime safety PASS。

---

# 119. Runtime Success vs Task Success

$$
\boxed{
RuntimeCorrectness
\neq
ModelTaskSuccessRate
}
$$

---

# 120. Second Scenario — PHOSPHOR Domain

如果 PHOSPHOR integration可用：

```text
observe ACTIVE
→ pause
→ observe PAUSED
→ suspend
→ wake
→ resume
→ observe PAUSED
→ restore/resume according to Goal
```

---

# 121. PHOSPHOR Integration Can Be Optional Gate

v0.7.0a1 Agent Core不應因 external PHOSPHOR checkout unavailable整體 fail。

分：

```text
Core Gate
Integration Gate
```

---

# 122. PNCW Real Integration Same Rule

Fake port 是 core conformance。

Real PNCW bridge是 integration conformance。

---

# 123. Phase G CLI

新增：

```text
macr agent create
macr agent run
macr agent status
macr agent events
macr agent suspend
macr agent wake
macr agent cancel
macr agent reconcile
```

---

# 124. Agent CLI Must Not Expose Secrets

status只顯示：

```text
goal ref
state
revision
epoch
budget summary
authority summary
latest observation
pending actions
checkpoint
wake
```

---

# 125. Phase G Tests

```text
tests/test_agent_runner.py
tests/test_agent_loop.py
tests/test_agent_planner.py
tests/test_agent_completion.py
tests/test_agent_cli.py
```

Integration：

```text
tests/integration/test_single_agent_repo_repair.py
tests/integration/test_single_agent_suspend_resume.py
```

---

# 126. Phase G Gate

第一個真正 v0.7 claim：

$$
\boxed{
BoundedAutonomousSingleAgent=IMPLEMENTED
}
$$

只有 G pass後才能宣稱。

---

# 127. Phase H — Failure Injection / Final Verification

## Goal

不是證明 Agent「能做事」。

而是證明 Agent：

> **在錯誤狀態下不會亂做事。**

---

# 128. Failure Injection Classes

至少：

```text
F0 State
F1 Authority
F2 Budget
F3 Observation
F4 Action
F5 Provider
F6 Persistence
F7 Temporal
F8 Reconciliation
F9 Completion
```

---

# 129. F0 — State

注入：

```text
stale revision
stale epoch
duplicate owner
illegal transition
corrupted current projection
```

---

# 130. F1 — Authority

```text
authority revoked after planning
authority epoch changes
scope shrink
child overreach
forged authority text
```

---

# 131. F2 — Budget

```text
budget exhausted mid-run
budget revision changes during suspend
cost estimate exceeds remainder
```

---

# 132. F3 — Observation

```text
source changes after observation
verification fails
VISIBLE missing
scope insufficient
mixed revision
```

---

# 133. F4 — Action

```text
unknown effect
derived effect wider than declared
precondition stale
command mapping widens target
```

---

# 134. F5 — Provider

```text
provider unavailable before dispatch
provider rejects
provider timeout
provider returns malformed result
provider restarts epoch
provider reports success but no world change
```

---

# 135. F6 — Persistence

Crash at:

```text
before action event
after action event
before provider dispatch
after provider dispatch
before receipt persistence
after receipt persistence
before checkpoint promotion
after checkpoint promotion
```

---

# 136. F7 — Temporal

```text
duplicate wake
late wake
lost wake
out-of-order event
scheduler restart
machine restart
```

---

# 137. F8 — Reconciliation

```text
unknown after dispatch
reconciliation observation unavailable
state remains unknown
manual resolution
compensation required
```

---

# 138. F9 — Completion

```text
model says done but tests fail
verification missing
child blocking
pending action
open reconciliation
```

---

# 139. Hard Safety Gate

以下任何一個出現：

```text
unauthorized external mutation
stale-epoch mutation
blind retry after unknown dispatch
terminal run reopened
credential plaintext persisted
receipt treated as verification
```

整個 v0.7.0 candidate：

```text
FAIL
```

---

# 140. No Percentage Override

即使：

```text
999 tests pass
```

只要發生一個 hard safety gate failure：

不能以：

```text
99.9% passed
```

宣稱 acceptable。

---

# 141. Verification Matrix — Identity / State

| ID | Requirement | Expected |
|---|---|---|
| AR-01 | Invocation ID != AgentRun ID | PASS |
| AR-02 | same Goal can create distinct AgentRuns | PASS |
| AR-03 | subject digest deterministic | PASS |
| AR-04 | revision increments exactly 1 | PASS |
| AR-05 | stale revision writer rejected | PASS |
| AR-06 | stale epoch writer rejected | PASS |
| AR-07 | terminal state cannot reopen | PASS |
| AR-08 | duplicate active owner rejected | PASS |

---

# 142. Verification Matrix — Semantic State

| ID | Requirement | Expected |
|---|---|---|
| AS-01 | unknown node rejected | PASS |
| AS-02 | stale patch rejected | PASS |
| AS-03 | partial patch impossible | PASS |
| AS-04 | provenance retained | PASS |
| AS-05 | context projection does not mutate graph | PASS |
| AS-06 | semantic relation cannot create authority | PASS |
| AS-07 | receipt and verification distinct | PASS |
| AS-08 | superseded node remains historical | PASS |

---

# 143. Verification Matrix — Observation

| ID | Requirement | Expected |
|---|---|---|
| OB-01 | raw input != VerifiedObservation | PASS |
| OB-02 | READY cannot bind | PASS |
| OB-03 | VERIFIED without VISIBLE cannot bind | PASS |
| OB-04 | stale source invalidates basis | PASS |
| OB-05 | mixed revision rejected | PASS |
| OB-06 | partial residency supported | PASS |
| OB-07 | scope cannot silently widen | PASS |
| OB-08 | wake revalidates mutable observation | PASS |

---

# 144. Verification Matrix — Action

| ID | Requirement | Expected |
|---|---|---|
| AC-01 | capability != authority | PASS |
| AC-02 | unknown effect fail closed | PASS |
| AC-03 | derived effects included | PASS |
| AC-04 | stale authority blocks dispatch | PASS |
| AC-05 | budget blocks action | PASS |
| AC-06 | stale observation blocks action | PASS |
| AC-07 | one-attempt default | PASS |
| AC-08 | receipt != verification | PASS |

---

# 145. Verification Matrix — Reconciliation

| ID | Requirement | Expected |
|---|---|---|
| RC-01 | unknown-after-dispatch freezes mutation | PASS |
| RC-02 | no automatic retry | PASS |
| RC-03 | reconciliation result evidence-bound | PASS |
| RC-04 | STATE_UNKNOWN remains frozen | PASS |
| RC-05 | compensation is new action | PASS |
| RC-06 | Agent cannot self-resolve reconciliation | PASS |

---

# 146. Verification Matrix — Temporal

| ID | Requirement | Expected |
|---|---|---|
| TP-01 | suspend requires checkpoint | PASS |
| TP-02 | unknown effect prevents normal suspend | PASS |
| TP-03 | wake != ACTIVE | PASS |
| TP-04 | duplicate wake safe | PASS |
| TP-05 | authority revalidated | PASS |
| TP-06 | budget revalidated | PASS |
| TP-07 | world reobserved | PASS |
| TP-08 | process restart resumes safely | PASS |

---

# 147. Verification Matrix — Completion

| ID | Requirement | Expected |
|---|---|---|
| CP-01 | model `done` not sufficient | PASS |
| CP-02 | required verification mandatory | PASS |
| CP-03 | reconciliation blocks completion | PASS |
| CP-04 | blocking dependency blocks completion | PASS |
| CP-05 | terminal completion immutable | PASS |

---

# 148. Phase H Test Layout

建議：

```text
tests/failure_injection/
├─ test_agent_state_faults.py
├─ test_agent_authority_faults.py
├─ test_agent_observation_faults.py
├─ test_agent_action_faults.py
├─ test_agent_provider_faults.py
├─ test_agent_persistence_faults.py
├─ test_agent_temporal_faults.py
├─ test_agent_reconciliation_faults.py
└─ test_agent_completion_faults.py
```

---

# 149. Crash Harness

需要真正 child process crash injection。

例如：

```text
--crash-at before_dispatch
--crash-at after_dispatch_before_receipt
--crash-at after_receipt
--crash-at before_checkpoint_promotion
```

---

# 150. Deterministic Fault Markers

Fault injection不能依 timing race碰運氣。

使用 explicit crash points。

---

# 151. Evidence Artifacts

每次 full Agent gate輸出：

```text
artifacts/v0.7/
agent-gate-summary.json
agent-failure-matrix.json
agent-recovery-evidence.json
agent-closed-loop-evidence.json
```

---

# 152. Evidence Must Include

```text
source commit
schema versions
platform
Python version
test result
AgentRun IDs
scenario digest
authority policy digest
budget digest
final AgentRun state
negative-control verdicts
```

---

# 153. Evidence Must Exclude

```text
credentials
full private prompts
API keys
secret env values
private memory plaintext
```

---

# 154. Verification Scripts

新增：

```text
scripts/verify-v07-agent.ps1
```

若需要 cross-platform：

```text
scripts/verify-v07-agent.py
```

由 PowerShell wrapper呼叫。

---

# 155. Gate Levels

建議：

```text
G0 — Contract
G1 — AgentRun State
G2 — Semantic State
G3 — Observation
G4 — Action Authority
G5 — Temporal Recovery
G6 — Closed Loop
G7 — Failure Injection
G8 — Inherited Regression
```

---

# 156. G0

驗：

```text
schemas
canonical serialization
registry
```

---

# 157. G1

驗：

```text
lifecycle
revision
epoch
ownership
```

---

# 158. G2

驗：

```text
semantic graph
patch
provenance
```

---

# 159. G3

驗：

```text
VerifiedObservation
freshness
scope
```

---

# 160. G4

驗：

```text
effects
capability
authority
budget
policy
```

---

# 161. G5

驗：

```text
checkpoint
suspend
wake
process restart
```

---

# 162. G6

驗：

```text
complete bounded AgentRun
```

---

# 163. G7

驗：

```text
all hard negative controls
```

---

# 164. G8

跑：

```text
complete inherited MACR test suite
existing verify-v06 relevant gates
```

確保 v0.6不回歸。

---

# 165. Gate Independence

某 gate failure不能阻止後續 gates產生 evidence。

Final verdict仍 FAIL。

這樣能一次看清所有 blocker。

---

# 166. Full Gate Outcome

```text
PASS
FAIL
PARTIAL
NOT_RUN
```

---

# 167. PARTIAL

只用於：

> 非 hard-required integration/environment gate無法執行。

例如：

```text
real PNCW checkout unavailable
```

不能用 PARTIAL掩蓋 core safety failure。

---

# 168. Offline-First

v0.7.0a1 第一個 closure應：

```text
offline first
```

使用：

```text
fake provider
fake PNCW
fixture repository
mock PHOSPHOR
```

完整跑過。

---

# 169. Why Offline First

這可以證明：

```text
Agent semantics
```

而不是：

```text
外部 API 今天剛好正常
```

---

# 170. Live Provider Gate

Offline closure後，才跑一個 bounded live model test。

---

# 171. Live Model Test Boundary

限制：

```text
one AgentRun
one fixture
bounded calls
bounded cost
no public mutation
no secrets in output
```

---

# 172. Real PNCW Gate

若 PNCW repo可 local checkout：

測：

```text
real bridge contract
```

不一定要求 HDSRC/MRMIC 4096D整條路在 v0.7 Agent core gate每次跑。

那是 PNCW自己的 upstream conformance。

---

# 173. Real PHOSPHOR Gate

使用：

```text
domain.inspect
domain.pause
domain.resume
```

bounded test domain即可。

---

# 174. External Framework Adoption

v0.7.0a1 完成前不引入大型 external Agent framework。

如果 implementation中發現：

```text
scheduler
sandbox
```

確有必要借 library，另做：

```text
Adopt / Adapt / Reimplement
```

audit。

---

# 175. Version Boundary

只有以下條件全部成立才可稱：

```text
v0.7.0a1
```

而非單純文件寫完：

```text
A contracts PASS
B AgentRun PASS
C Semantic PASS
D Observation PASS
E Action PASS
F Temporal PASS
G Closed Loop PASS
H Hard Safety PASS
Inherited Regression PASS
```

---

# 176. Alpha Claim

`v0.7.0a1` 正確 claim：

> **Bounded single-machine autonomous Agent runtime candidate with verified observation, governed action, checkpoint/suspend/resume and fail-closed reconciliation.**

---

# 177. What v0.7.0a1 Must Not Claim

```text
general AGI runtime
safe unrestricted autonomy
production multi-tenant security
distributed Agent runtime
general Multi-Agent
complete EML-U integration
complete SEDB integration
complete PHOSPHOR federation
exactly-once external mutation
persistent Resident AI
```

---

# 178. Minimum Public Demo

建議做一個：

```text
examples/agent_repo_repair/
```

包含：

```text
fixture repo
goal
authority envelope
budget
expected failure
expected safe repair
run command
evidence output
```

---

# 179. CLI Demo

例如：

```text
macr agent run examples/agent_repo_repair/goal.json
```

輸出：

```text
AgentRun: ...
State: COMPLETED
Verified observations: ...
Actions admitted: 1
Actions denied: ...
Verification: PASSED
Checkpoint: ...
```

---

# 180. No CoT Demo

不要用：

```text
Thought:
Thought:
Thought:
```

作主要可觀察 UI。

顯示：

```text
Goal
Observation
Plan
Action
Decision
Receipt
Verification
```

即可。

---

# 181. Direct Chat Preservation

完成 v0.7 後：

```text
macr direct-chat
```

既有 contract仍需工作。

Agent UI是新的 plane。

---

# 182. Interaction Plane Extension

現有：

```text
DIRECT
DELEGATION
```

未來可新增：

```text
AGENT
```

但在實作前需 audit所有 switch / enum consumers。

---

# 183. Safer Initial Alternative

若加入 `InteractionPlane.AGENT` 會造成大面積 v0.6 change：

v0.7.0a1 可以讓 Agent child invocation仍使用：

```text
DELEGATION
```

並由 `agent_run_id` / origin metadata區分。

之後再在 v0.7.0a2正式加入 Agent plane。

---

# 184. Recommendation

第一版：

> **不要為了命名漂亮而改動所有現有 dispatch code。**

優先完成 Agent semantics。

---

# 185. Provider Routing

v0.7.0a1 不加入 automatic provider fallback。

Agent planner可以提出 route。

Runtime explicit選定。

---

# 186. GLM / Grok / Qwythos

都可以未來作 Agent planner/provider。

但 v0.7 core不綁任一特定 model。

---

# 187. Qwythos Constraint

小 context model可透過：

```text
semantic context projection
```

得到更小 context。

不要求與 Grok看到相同 token projection。

---

# 188. Model Independence Acceptance

同 AgentRun semantic fixture：

至少兩個 Planner implementations：

```text
DeterministicFixturePlanner
ModelPlanner
```

能使用相同 runtime contract。

---

# 189. Storage Placement

延續 MACR D-drive policy。

Agent persistent state應進：

```text
MACR_STATE_ROOT
```

不能寫 repo tree作 runtime state。

---

# 190. Repo Cleanliness

tests執行後：

```text
git status
```

不得出現：

```text
DB
logs
checkpoints
provider response
venv
cache
```

untracked runtime artifacts。

---

# 191. Migration

v0.6 existing state：

```text
do not auto-convert
```

成 AgentRun。

v0.7 agent schema獨立 migration version。

---

# 192. Agent DB Schema Version

第一版：

```text
agent_runtime_schema = 1
```

---

# 193. Migration Failure

若 DB schema unknown/newer：

fail closed。

---

# 194. No Downgrade Mutation

舊 binary遇到 newer agent DB：

read-only diagnostics或拒絕。

不能 rewrite。

---

# 195. Documentation

Phase G/H完成後才更新：

```text
README.md
docs/ARCHITECTURE.md
docs/PROVIDER_STATUS.md
AGENTS.md
```

避免文件先宣稱 Agent已實作。

---

# 196. AGENTS.md Reconciliation

現有 `AGENTS.md` 若與 current provider/runtime facts有 stale wording，v0.7 docs closure時一併做：

```text
source-of-truth reconciliation
```

但不要混進 Agent core implementation commit前段。

---

# 197. Commit Strategy

建議按 Phase commit：

```text
feat(agent): add v0.7 contract kernel
feat(agent): add durable AgentRun state
feat(agent): add semantic working state
feat(agent): add verified observation bridge
feat(agent): add governed action runtime
feat(agent): add temporal continuation
feat(agent): close single-agent loop
test(agent): add failure-injection gate
docs(agent): seal v0.7.0a1 checkpoint
```

---

# 198. Branch Strategy

建議：

```text
integration/v0.7.0a1-single-agent
```

若希望更細：

```text
workbench/v0.7-agent-contracts
workbench/v0.7-agent-state
...
```

最後收斂到 integration branch。

但 canonical source永遠以 final merged source/test為準，不以 plan checkbox為準。

---

# 199. Phase Completion Artifacts

每 Phase 產：

```text
docs/checkpoints/v07/
PHASE_A.md
PHASE_B.md
...
```

只記：

```text
commit
tests
known gaps
evidence
```

避免長篇重寫 architecture。

---

# 200. Final Offline Checkpoint

建議：

```text
docs/V070A1_OFFLINE_CHECKPOINT.md
```

包含：

```text
base commit
candidate commit
schema versions
gate results
negative controls
known not-measured
```

---

# 201. NotMeasured

至少誠實列：

```text
distributed Agent ownership
cross-machine wake
production OAuth
production multi-tenant sandbox
arbitrary provider side effects
long-duration multi-day soak
persistent Resident integration
EML-U runtime integration
SEDB vNext
full PNCW world federation
full PHOSPHOR provider migration
```

---

# 202. Final MVP Acceptance Scenario A

## Autonomous Repository Repair

必須：

```text
Goal
→ Verified Observation
→ Plan
→ Test
→ Action Proposal
→ Authority Gate
→ Patch
→ ReObservation
→ Test
→ Verification
→ Completion
```

---

# 203. Scenario B

## Suspend / Wake / Resume

```text
AgentRun ACTIVE
→ checkpoint
→ SUSPENDED
→ runtime process killed
→ restart
→ wake
→ WAKING
→ revalidate
→ reobserve
→ ACTIVE
→ COMPLETED
```

---

# 204. Scenario C

## Unknown After Dispatch

```text
dispatch
→ crash
→ no reliable receipt
→ restart
→ RECONCILIATION_REQUIRED
→ no retry
```

---

# 205. Scenario D

## Authority Revocation

```text
plan action
→ admission
→ revoke authority
→ dispatch attempt
→ DENY
```

---

# 206. Scenario E

## Stale World

```text
observe A
→ plan
→ external mutation B
→ action
→ stale basis rejection
→ reobserve
→ replan
```

---

# 207. Scenario F

## Receipt/Reality Divergence

```text
provider reports success
→ world unchanged
→ verification DIVERGED
→ no completion
```

---

# 208. Scenario G

## Budget Exhaustion

```text
Agent continues
→ budget reached
→ BLOCKED
→ no extra provider call
```

---

# 209. Scenario H

## Model Failure

```text
planner returns malformed/unsafe proposal
→ validation rejects
→ world unchanged
```

---

# 210. Final Hard Invariants

v0.7.0a1 必須以 executable tests固定：

$$
\boxed{
Model
\neq
Agent
}
$$

$$
\boxed{
Agent
\neq
Resident
}
$$

$$
\boxed{
Observation
\neq
World
}
$$

$$
\boxed{
Capability
\neq
Authority
}
$$

$$
\boxed{
Plan
\neq
Command
}
$$

$$
\boxed{
Decision
\neq
Commit
}
$$

$$
\boxed{
Receipt
\neq
Verification
}
$$

$$
\boxed{
Wake
\neq
Authorization
}
$$

$$
\boxed{
Resume
\neq
Replay
}
$$

$$
\boxed{
UnknownAfterDispatch
\Rightarrow
ReconciliationRequired
}
$$

---

# 211. Final Engineering Equation

MACR v0.7.0a1：

$$
\boxed{
\begin{aligned}
AgentRuntime
={}&
AgentRun\\
&+
SemanticState\\
&+
VerifiedObservation\\
&+
GovernedAction\\
&+
Checkpoint\\
&+
TemporalContinuation\\
&+
Verification\\
&+
Reconciliation
\end{aligned}
}
$$

---

# 212. What Success Looks Like

成功不是：

```text
AI can call tools.
```

也不是：

```text
AI autonomously edited a file once.
```

而是：

> 一個 AgentRun 在受限世界中完成完整感知—行動—驗證閉環；它可以跨 process suspend/resume；當世界、authority、budget 或 provider state 改變時會重新驗證；當 external effect 不確定時停止新 mutation 並進入 reconciliation；完成狀態只能由 runtime verification gate 產生。

---

# 213. Canonical Closure

本文件固定：

1. v0.7.0a1 先完成 Single-Agent，不先完成 Multi-Agent。
2. v0.7 為既有 MACR shared core 上的新 Agent Plane。
3. 不重寫 v0.6 authority/provider/accounting/candidate/coordination core。
4. v0.7.0a1 不採大型 external Agent framework作 runtime dependency。
5. Phase A–H 必須依序完成。
6. Contract完成不等於 implementation完成。
7. AgentRun current state與 append-only events分離。
8. Semantic state不以 conversation history作 canonical source。
9. Agent model output只能提出 semantic/action proposal。
10. PNCW-like Verified Observation path先以 conformance port建立，再做 real integration。
11. Action authority重用既有 MACR authority semantics。
12. Action預設 one-attempt。
13. unknown-after-dispatch不能 auto retry。
14. Checkpoint / suspend / wake必須可跨真實 process restart。
15. 第一個 Agent demo使用 bounded repository fixture。
16. mutation surface限定 reversible local/feature workspace。
17. main/release/public send/credential export不屬第一版 autonomous authority。
18. deterministic planner先於 real model planner。
19. Runtime correctness與 model task success分離。
20. PHOSPHOR / PNCW real integration採獨立 integration gates。
21. Direct Chat不被 AgentRun取代。
22. v0.6 historical data不偽造成 AgentRun。
23. Agent runtime state留在 `MACR_STATE_ROOT`，不污染 repo。
24. Final gate必須包含 inherited MACR regression。
25. 一個 hard safety failure即使其他測試全通過也使 candidate FAIL。
26. v0.7.0a1不宣稱 distributed / unrestricted / production-general autonomy。
27. source、tests、negative controls、evidence全部完成後才可升版本。
28. final canonical authority是 current source + tests + evidence，不是 plan checkbox。

因此第一個工程里程碑正式定義為：

$$
\boxed{
\text{MACR v0.7.0a1}
=
\text{Bounded Autonomous Single-Agent Runtime Candidate}
}
$$

它必須實際證明：

$$
\boxed{
Observe
\rightarrow
Plan
\rightarrow
Act
\rightarrow
Verify
\rightarrow
Checkpoint
\rightarrow
Suspend
\rightarrow
Wake
\rightarrow
Resume
}
$$

而不是只證明：

$$
Prompt
\rightarrow
ToolCall
$$

---

# Appendix A — Proposed New Source Tree

```text
src/macr_runtime/
├─ agent/
│  ├─ contracts.py
│  ├─ types.py
│  ├─ state.py
│  ├─ lifecycle.py
│  ├─ store.py
│  ├─ events.py
│  ├─ ownership.py
│  ├─ service.py
│  ├─ runner.py
│  ├─ loop.py
│  ├─ planner.py
│  ├─ context.py
│  └─ completion.py
│
├─ semantic/
│  ├─ contracts.py
│  ├─ registry.py
│  ├─ validation.py
│  ├─ store.py
│  ├─ graph.py
│  ├─ patch.py
│  └─ projection.py
│
├─ observation/
│  ├─ contracts.py
│  ├─ intent.py
│  ├─ compiler.py
│  ├─ pncw_port.py
│  ├─ freshness.py
│  ├─ binding.py
│  └─ service.py
│
├─ action/
│  ├─ contracts.py
│  ├─ effects.py
│  ├─ capabilities.py
│  ├─ authority_adapter.py
│  ├─ budget.py
│  ├─ policy.py
│  ├─ admission.py
│  ├─ command.py
│  ├─ dispatch.py
│  ├─ verification.py
│  └─ reconciliation.py
│
└─ temporal/
   ├─ contracts.py
   ├─ checkpoint.py
   ├─ suspend.py
   ├─ wake.py
   ├─ scheduler.py
   ├─ dependency.py
   └─ resume.py
```

---

# Appendix B — Proposed New Test Tree

```text
tests/
├─ test_agent_contracts.py
├─ test_agent_state.py
├─ test_agent_lifecycle.py
├─ test_agent_store.py
├─ test_agent_ownership.py
├─ test_agent_runner.py
├─ test_agent_loop.py
├─ test_agent_completion.py
│
├─ test_semantic_contracts.py
├─ test_semantic_registry.py
├─ test_semantic_graph.py
├─ test_semantic_patch.py
├─ test_semantic_projection.py
│
├─ test_observation_contracts.py
├─ test_observation_service.py
├─ test_observation_freshness.py
├─ test_observation_binding.py
│
├─ test_action_contracts.py
├─ test_effect_registry.py
├─ test_agent_authority_adapter.py
├─ test_agent_budget.py
├─ test_action_policy.py
├─ test_action_admission.py
├─ test_action_dispatch.py
├─ test_action_verification.py
├─ test_action_reconciliation.py
│
├─ test_temporal_contracts.py
├─ test_agent_checkpoint.py
├─ test_agent_suspend.py
├─ test_agent_wake.py
├─ test_agent_scheduler.py
├─ test_agent_resume.py
│
├─ integration/
│  ├─ test_single_agent_repo_repair.py
│  ├─ test_single_agent_suspend_resume.py
│  ├─ test_pncw_observation_bridge.py
│  └─ test_phosphor_actuation_bridge.py
│
└─ failure_injection/
   ├─ test_agent_state_faults.py
   ├─ test_agent_authority_faults.py
   ├─ test_agent_observation_faults.py
   ├─ test_agent_action_faults.py
   ├─ test_agent_provider_faults.py
   ├─ test_agent_persistence_faults.py
   ├─ test_agent_temporal_faults.py
   ├─ test_agent_reconciliation_faults.py
   └─ test_agent_completion_faults.py
```

---

# Appendix C — Execution Sequence

```text
A Contracts
↓
B AgentRun
↓
C Semantic State
↓
D Observation
↓
E Action
↓
F Temporal
↓
G Closed Loop
↓
H Failure Injection
↓
Offline Candidate
↓
Optional Real PNCW / PHOSPHOR / Model Gates
↓
v0.7.0a1 Seal
```

---

# Appendix D — Immediate Next Engineering Step

正式開始實作時，不再重新寫一份大型「v0.7 設計」。

第一個工程 slice：

**Phase A — Agent Contract Kernel**

只完成：

```text
AgentRun contracts
Semantic contracts
Observation contracts
Action contracts
Temporal contracts
Canonical digest rules
Schema validation
Negative contract controls
```

通過 inherited regression 後，直接進 Phase B。

不重新研究 Agent 架構。