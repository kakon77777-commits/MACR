# MACR v0.7 — AgentRun Canonical State Specification v0.1

## AgentRun 規範狀態、生命週期、持久化與恢復契約 v0.1

**Document ID:** `MACR-V07-AGENTRUN-STATE-2026-v0.1`  
**Parent Architecture:** `MACR-ASR-CCA-2026-v0.1`  
**Project:** MACR  
**Target:** MACR v0.7.0 — Bounded Autonomous Agent Core  
**Baseline:** MACR v0.6.0a1  
**Date:** 2026-08-30  
**Status:** Canonical State Specification / Pre-Implementation  
**Organization:** EveMissLab / 一言諾科技有限公司  
**Language:** Traditional Chinese

---

# 摘要

MACR v0.6 的主要執行單位是 bounded invocation：

```text
TaskContract
→ DispatchContext
→ Provider Attempt
→ Candidate Capture
→ Verification
→ Acceptance
```

其中 `run_id` 標記一次 provider / plan execution occurrence。

MACR v0.7 新增的 `AgentRun` 不取代這套結構。

AgentRun 是位於其上的 **long-lived governed execution object**：

$$
\boxed{
\mathrm{AgentRun}
\supset
\{
\mathrm{InvocationRun}_1,
\mathrm{InvocationRun}_2,
\dots,
\mathrm{InvocationRun}_n
\}
}
$$

一個 AgentRun 可以跨越：

- 多次模型 inference；
- 多個 provider；
- 多個 worker；
- 多個 world observation；
- 多次 plan revision；
- 多個 action proposal；
- suspend / wake；
- checkpoint / resume；
- authority revision；
- budget revision；
- world-state change；
- reconciliation；
- verification。

因此：

$$
\boxed{
\mathrm{ProviderRun}
\neq
\mathrm{AgentRun}
}
$$

AgentRun 的目的不是永久保存模型的所有內部 reasoning，而是保存足夠的 canonical state，使 Runtime 可以回答：

> 這個 Agent 現在在做什麼？

> 為什麼它被允許繼續？

> 它目前相信哪些經驗證的世界狀態？

> 它有哪些尚未完成或尚未確認的 action？

> 如果 process 現在消失，重新啟動後應如何安全恢復？

> 是否存在未知外部 effect，使系統不得自動繼續？

本文件固定 MACR v0.7.0 AgentRun 的：

- identity；
- subject binding；
- state machine；
- revision；
- authority binding；
- budget binding；
- world binding；
- semantic-state binding；
- child invocation relation；
- checkpoint；
- suspend；
- wake；
- resume；
- stale detection；
- reconciliation；
- completion；
- cancellation；
- event model；
- persistence invariants；
- negative controls。

---

# 0. Canonical Decision

MACR v0.7.0 將 `AgentRun` 定義為：

> **一個有明確 Goal、Authority、Budget、World Bindings 與恢復狀態，能跨多個 bounded invocation 持續存在的 governed execution occurrence。**

形式化：

$$
\mathcal R_t
=
(
I,
S_t,
G_t,
A_t,
B_t,
W_t,
C_t,
P_t,
X_t,
V_t,
K_t
)
$$

其中：

- $I$：AgentRun immutable identity；
- $S_t$：run lifecycle state；
- $G_t$：goal binding；
- $A_t$：authority binding；
- $B_t$：budget state；
- $W_t$：world bindings / observation basis；
- $C_t$：semantic working-state reference；
- $P_t$：plan state；
- $X_t$：pending / completed execution state；
- $V_t$：verification state；
- $K_t$：checkpoint / continuation state。

AgentRun 本身不是 foundation model session。

$$
\boxed{
\mathrm{AgentRun}
\neq
\mathrm{ModelSession}
}
$$

AgentRun 也不是 conversation。

$$
\boxed{
\mathrm{AgentRun}
\neq
\mathrm{Conversation}
}
$$

---

# 1. Relationship to MACR v0.6

v0.6 已有：

```text
DispatchOrigin
AuthorizationReference
DispatchContext
run_id
plan_digest
plan_revision
role_slot_id
route_id
model_token_policy_digest
VerificationState
AcceptanceState
```

v0.7 不修改這些欄位的既有語義。

而是加入：

```text
AgentRun
  ├─ InvocationRun
  ├─ InvocationRun
  ├─ Observation
  ├─ Action
  ├─ Checkpoint
  └─ InvocationRun
```

因此現行 invocation：

```text
DispatchContext.run_id
```

繼續表示：

> **one bounded provider/runtime invocation**

而：

```text
AgentRun.agent_run_id
```

表示：

> **one durable autonomous execution lineage**

不得把兩者使用同一 ID。

---

# 2. AgentRun Identity

AgentRun 使用 occurrence identity。

建議：

```text
agent_run_id = UUIDv4
```

理由：

AgentRun 是 runtime occurrence，不是純 semantic object。

同一個 Goal、同一 Agent、同一 World 可以被重新執行兩次：

$$
R_1 \neq R_2
$$

因此不應以 Goal digest 直接作為 AgentRun identity。

但 AgentRun 必須另外保存一個 deterministic subject digest。

定義：

$$
D_R
=
H(
AgentRef,
GoalRef,
GoalRevision,
Origin,
AdmissionPolicy,
InitialAuthority,
InitialBudget,
WorldBindingSet
)
$$

即：

```text
agent_run_id
```

回答：

> 這是哪一次 execution？

而：

```text
subject_digest
```

回答：

> 這次 execution 一開始被授權來完成的是什麼？

因此：

$$
\boxed{
\mathrm{OccurrenceIdentity}
\neq
\mathrm{SemanticSubjectIdentity}
}
$$

---

# 3. Immutable AgentRun Header

AgentRun 建立後以下欄位不可修改：

```text
schema
agent_run_id
agent_ref
origin
created_at
initial_goal_ref
initial_goal_revision
initial_authority_ref
initial_budget_ref
subject_digest
parent_agent_run_id
delegation_ref
```

可修改的 current fields 必須透過 revision/event 更新，不得覆寫 immutable history。

---

# 4. AgentRun v1 Minimum Schema

建議 canonical JSON：

```json
{
  "schema": "macr-agent-run/v1",
  "agent_run_id": "b7c74956-393e-4aa8-a73e-915e378731f5",
  "agent_ref": "agent:project-maintainer",
  "subject_digest": "sha256:...",
  "origin": {
    "host": "macr-ui",
    "identifier_kind": "request",
    "native_id": "..."
  },

  "state": "ACTIVE",
  "state_revision": 8,
  "epoch": 2,

  "goal": {
    "goal_ref": "goal:...",
    "goal_revision": 2,
    "goal_digest": "sha256:..."
  },

  "authority": {
    "authorization_ref": "auth:...",
    "authorization_digest": "sha256:...",
    "authorization_revision": 4,
    "authorization_epoch": 7
  },

  "budget": {
    "budget_ref": "budget:...",
    "budget_revision": 3,
    "budget_digest": "sha256:..."
  },

  "semantic_state_ref": "semgraph:...",
  "active_plan_ref": "plan:...",
  "active_plan_revision": 3,

  "world_bindings": [],
  "latest_verified_observations": [],

  "pending_actions": [],
  "open_reconciliation_refs": [],

  "latest_checkpoint_ref": "checkpoint:...",
  "wake_condition_ref": null,

  "parent_agent_run_id": null,
  "delegation_ref": null,

  "created_at": "...",
  "updated_at": "..."
}
```

其中 `updated_at` 是 metadata，不參與 semantic identity。

---

# 5. State Revision

每一次 canonical AgentRun state change 必須增加：

$$
r_{t+1}=r_t+1
$$

即：

```text
state_revision
```

必須嚴格單調遞增。

不允許：

```text
revision 4
→ revision 6
```

在沒有 revision 5 event 的情況下直接跳躍。

也不允許：

```text
revision 6
→ revision 5
```

回寫歷史。

---

# 6. Epoch

`state_revision` 表示 state history。

`epoch` 表示 runtime continuity boundary。

例如：

```text
process restart
authority reset
reconciliation resolution
explicit recovery
ownership transfer
```

可能造成新的 AgentRun epoch。

因此：

$$
\boxed{
\mathrm{Revision}
\neq
\mathrm{Epoch}
}
$$

revision：

> 同一 run 的 state 更新。

epoch：

> 哪一代 runtime execution continuity。

任何 stale worker 如果攜帶舊 epoch：

$$
e_{worker}<e_{current}
$$

必須 fail closed。

---

# 7. AgentRun State Machine

v0.7.0 最小 lifecycle：

```text
CREATED
   ↓
ADMITTED
   ↓
ACTIVE
```

ACTIVE 可轉：

```text
ACTIVE → WAITING
ACTIVE → SUSPENDED
ACTIVE → BLOCKED
ACTIVE → RECONCILIATION_REQUIRED
ACTIVE → COMPLETED
ACTIVE → FAILED
ACTIVE → CANCELLED
```

恢復路徑：

```text
WAITING
→ ACTIVE

SUSPENDED
→ WAKING
→ ACTIVE
```

BLOCKED：

```text
BLOCKED
→ ACTIVE

BLOCKED
→ CANCELLED

BLOCKED
→ FAILED
```

Reconciliation：

```text
RECONCILIATION_REQUIRED
→ ACTIVE

RECONCILIATION_REQUIRED
→ FAILED

RECONCILIATION_REQUIRED
→ CANCELLED
```

但任何：

```text
RECONCILIATION_REQUIRED → ACTIVE
```

都必須存在 explicit reconciliation resolution receipt。

---

# 8. State Definitions

## 8.1 CREATED

AgentRun object 已建立，但尚未取得 execution admission。

禁止：

- provider invocation；
- world mutation；
- child Agent；
- external side effects。

---

## 8.2 ADMITTED

已完成 initial：

- goal validation；
- authority validation；
- budget validation；
- policy validation；
- initial world-binding validation。

但 execution loop 尚未正式取得 active ownership。

---

## 8.3 ACTIVE

Runtime 可以：

- observation；
- planning；
- worker invocation；
- action proposal；
- authorized actuation；
- verification；
- checkpoint。

---

## 8.4 WAITING

短期等待 runtime-known dependency。

例如：

- child worker 尚未完成；
- deterministic local job；
- verified internal queue dependency。

WAITING 不應被用來表示長期 durable wait。

---

## 8.5 SUSPENDED

AgentRun 已形成 durable checkpoint，主動停止 active execution。

可等待：

- wall-clock time；
- external event；
- human response；
- world-state condition；
- budget refresh；
- external service availability。

SUSPENDED 時不得有 live mutation ownership。

---

## 8.6 WAKING

一個 temporary recovery state。

WAKING 必須完成：

```text
checkpoint verify
authority revalidation
budget revalidation
world binding refresh
stale observation detection
pending action audit
```

才能回 ACTIVE。

---

## 8.7 BLOCKED

Runtime 確定目前不存在未知 side effect，但缺少繼續條件。

例如：

```text
CAPABILITY_MISSING
AUTHORITY_REQUIRED
HUMAN_APPROVAL_REQUIRED
DEPENDENCY_UNAVAILABLE
BUDGET_EXHAUSTED
```

BLOCKED 不等於 FAILED。

---

## 8.8 RECONCILIATION_REQUIRED

存在一個或多個：

> 已 dispatch，但實際 external effect 無法確定。

這是比 BLOCKED 更強的 freeze state。

$$
\boxed{
\mathrm{ReconciliationRequired}
\Rightarrow
\mathrm{NoNewMutation}
}
$$

直到 reconciliation resolution 完成。

---

## 8.9 COMPLETED

Goal completion gate 已通過。

不是模型自己宣稱完成。

COMPLETED 是 terminal state。

---

## 8.10 FAILED

Run 無法安全完成，且 policy 決定結束。

terminal。

---

## 8.11 CANCELLED

由人類、parent、host policy 或 authority owner 明確取消。

terminal。

---

# 9. Illegal Transitions

以下永遠非法：

```text
CREATED → ACTIVE
CREATED → COMPLETED
SUSPENDED → ACTIVE
RECONCILIATION_REQUIRED → ACTIVE without receipt
COMPLETED → ACTIVE
FAILED → ACTIVE
CANCELLED → ACTIVE
```

Terminal state 不得 reopen。

若需要重新執行：

$$
\boxed{
\mathrm{NewExecution}
\Rightarrow
\mathrm{NewAgentRun}
}
$$

---

# 10. Why Completed Runs Cannot Resume

避免：

```text
completed yesterday
→ new external world state
→ silently resume same authority
```

因此：

$$
\boxed{
\mathrm{Completed}
=
\mathrm{ClosedExecutionLineage}
}
$$

未來「繼續這個任務」應建立：

```text
new AgentRun
parent / continuation reference = old AgentRun
```

而不是 reopen。

---

# 11. Goal Binding

AgentRun 必須始終存在 active goal binding：

```text
goal_ref
goal_revision
goal_digest
```

Goal mutation 不允許 in-place 改寫。

只能：

```text
Goal Revision 1
→ Goal Revision 2
```

並保存 reason。

---

# 12. Goal Revision Classes

可區分：

```text
REFINEMENT
SCOPE_REDUCTION
SCOPE_EXPANSION
CLARIFICATION
SUCCESS_CRITERIA_CHANGE
CANCELLATION
```

其中：

```text
SCOPE_EXPANSION
```

不能直接沿用舊 authority。

$$
\boxed{
\mathrm{GoalScopeExpansion}
\Rightarrow
\mathrm{AuthorityReAdmission}
}
$$

---

# 13. Agent-Proposed Goal Revision

Agent 可以提出：

```text
GoalRevisionProposal
```

但：

$$
\boxed{
\mathrm{GoalProposal}
\neq
\mathrm{GoalRevision}
}
$$

尤其 scope expansion 必須由 host policy 或 human authority 接受。

---

# 14. Authority Binding

MACR v0.7 AgentRun 應延續 v0.6 `AuthorizationReference` 的核心：

```text
source_kind
source_id
digest
revision
epoch
scope
```

AgentRun 不複製 authority 內容。

只保存 immutable reference / digest。

---

# 15. Current Authority

AgentRun current authority：

$$
A_t
=
(
source,
digest,
revision,
epoch,
scope
)
$$

每一次 privileged action 必須重新驗證：

```text
current authority
==
action-bound authority
```

不能只在 AgentRun admission 時檢查一次。

---

# 16. Authority Expiration

若 authority：

- expiry 到期；
- revision 變更；
- epoch 變更；
- 被撤銷；
- scope 不再包含 action；

AgentRun 可以繼續：

```text
observation
planning
proposal
checkpoint
```

但不得繼續 privileged actuation。

依 policy 轉入：

```text
BLOCKED
```

或：

```text
SUSPENDED
```

---

# 17. Authority Cannot Be Stored as Prompt Text

以下不是 authority：

```text
"You have permission."
"User said yes earlier."
"Always deploy automatically."
```

即使存在於：

- conversation；
- memory；
- retrieved document；
- semantic graph。

也只是 information。

$$
\boxed{
\mathrm{TextualClaim}
\neq
\mathrm{AuthorizationReference}
}
$$

---

# 18. Budget Binding

AgentRun 必須有 explicit budget object。

最低支援：

```text
provider_calls
input_tokens
output_tokens
reasoning_tokens
currency_cost
wall_clock
child_agent_count
```

後續可以增加：

```text
CPU
GPU
RAM
storage
network
external effects
```

---

# 19. Budget Snapshot

每個 checkpoint 都保存：

```text
budget_ref
budget_revision
budget_digest
observed_consumption_ref
```

不得只保存：

```text
remaining = 50
```

因為剩餘額度必須可追到原始 budget policy 與已使用 accounting evidence。

---

# 20. Budget Exhaustion

若：

$$
Usage_t \ge Limit
$$

不得自行透支。

AgentRun 轉：

```text
BLOCKED
```

或依 completion policy：

```text
FAILED
```

Agent 不得自行建立新的更高 budget revision。

---

# 21. World Binding

AgentRun 不擁有 World。

AgentRun 只保存：

```text
WorldBindingRef[]
```

最小：

```json
{
  "world_binding_id": "world:github:repo:...",
  "provider": "github",
  "resource_ref": "repo:owner/name",
  "observation_contract": "pncw-projection-request/v1",
  "mutation_mode": "proposal_only",
  "authority_ref": "auth:...",
  "binding_revision": 3
}
```

---

# 22. Latest Observation Is Not World State

AgentRun 可以保存：

```text
latest_verified_observation_ref
```

但必須標示：

```text
observed_at
source_revision
projection_identity
verification_identity
```

因此：

$$
\boxed{
O_t
\neq
W_{now}
}
$$

一個 observation 在下一秒可能 stale。

---

# 23. Observation Basis

任何 Plan 必須能指出它依賴哪些 observation：

```text
basis_observation_refs
```

例如：

```text
plan 7
basis:
  repo HEAD abc123
  tests failed 3
  file digest xyz
```

如果 world 已變：

$$
Basis(P_t)\neq CurrentWorld
$$

Plan 至少必須被標記：

```text
STALE
```

重新驗證或重建。

---

# 24. Semantic Working State

AgentRun 只保存：

```text
semantic_state_ref
semantic_state_digest
semantic_state_revision
```

而不把整個 semantic graph 內嵌在主 state row。

原因：

- graph 可能很大；
- 可使用其他 storage；
- 可獨立 version；
- 可讓 SEDB / EML-U future adapter 接入。

---

# 25. Plan Binding

AgentRun 最多只能有一個 canonical active plan revision：

```text
active_plan_ref
active_plan_revision
active_plan_digest
```

但可保存多個：

```text
plan candidates
rejected plans
superseded plans
```

---

# 26. Plan Supersession

Plan revision：

$$
P_1
\rightarrow
P_2
$$

不刪除 $P_1$。

`P_2` 必須保存：

```text
parent_plan_ref
revision_reason
basis_change
```

---

# 27. Invocation Runs

每次模型／worker invocation 繼續使用現有：

```text
run_id
```

AgentRun 保存 relation：

```text
agent_run_id
→ invocation_run_id
```

而不是改寫現行 `DispatchContext.run_id`。

---

# 28. Invocation Binding

v0.7 新增的 DispatchContext extension 建議：

```text
agent_run_id
agent_run_epoch
agent_run_state_revision
goal_digest
semantic_context_digest
```

但這些只是 provenance / fencing binding。

它們不應使 provider invocation 自動取得 AgentRun 全部 authority。

---

# 29. Invocation Result Never Directly Mutates Agent State

模型輸出：

```text
candidate
```

經：

```text
capture
return contract
verification
```

後才可以形成 Agent semantic-state update proposal。

因此：

$$
\boxed{
\mathrm{ModelOutput}
\neq
\mathrm{AgentCanonicalState}
}
$$

---

# 30. Pending Action

任何 external-effect action 在 dispatch 前建立：

```text
PendingAction
```

包含：

```text
action_id
proposal_digest
authority_digest
budget_digest
world_basis_refs
expected_effects
idempotency_policy
rollback_policy
verification_policy
dispatch_state
```

---

# 31. Action Lifecycle

建議：

```text
PROPOSED
→ ADMITTED
→ DISPATCHING
→ DISPATCHED
→ RECEIPT_CAPTURED
→ VERIFYING
→ VERIFIED
```

或：

```text
PROPOSED → DENIED
ADMITTED → CANCELLED
DISPATCHED → RECONCILIATION_REQUIRED
VERIFYING → DIVERGED
```

AgentRun state 與 Action state 必須分開。

---

# 32. Why Dispatching and Dispatched Must Be Separate

如果 process crash 在：

```text
before provider call
```

與：

```text
after provider call but before local persistence
```

其安全意義完全不同。

所以：

$$
\boxed{
\mathrm{NotDispatched}
\neq
\mathrm{UnknownAfterDispatch}
}
$$

延續 MACR v0.6 semantics。

---

# 33. Unknown After Dispatch

若無法證明：

```text
provider never received operation
```

就不得標記：

```text
FAILED_RETRYABLE
```

而必須：

```text
RECONCILIATION_REQUIRED
```

AgentRun 同時進入：

```text
RECONCILIATION_REQUIRED
```

並 freeze 新 mutation。

---

# 34. Global Reconciliation Freeze

如果 AgentRun 有：

$$
|OpenReconciliation|>0
$$

則：

$$
\boxed{
NewExternalMutation=Forbidden
}
$$

允許：

```text
read
observe
reconcile
human communication
checkpoint
diagnostics
```

但禁止新的可能干擾 reconciliation 的 external mutation。

---

# 35. Reconciliation Resolution

Resolution 必須明確分類，例如：

```text
NOT_EXECUTED
EXECUTED_AS_EXPECTED
EXECUTED_DIFFERENTLY
PARTIALLY_EXECUTED
STATE_UNKNOWN
COMPENSATION_REQUIRED
```

只有前四類在完成必要 re-observation / verification 後，才可能重新 ACTIVE。

`STATE_UNKNOWN` 仍維持 freeze。

---

# 36. Reconciliation Receipt

最小：

```json
{
  "schema": "macr-agent-reconciliation/v1",
  "reconciliation_id": "rec:...",
  "agent_run_id": "...",
  "action_id": "...",
  "classification": "EXECUTED_AS_EXPECTED",
  "evidence_refs": [],
  "resolved_by": "host_operator",
  "authority_ref": "...",
  "resolved_at": "...",
  "resolution_digest": "..."
}
```

---

# 37. Checkpoint Definition

Checkpoint 是 AgentRun 在某一 revision 的 durable continuation artifact。

$$
K_t
=
H(
RunIdentity,
RunEpoch,
StateRevision,
Goal,
Authority,
Budget,
WorldBasis,
SemanticState,
Plan,
PendingActions,
VerificationState,
WakeCondition
)
$$

---

# 38. Checkpoint Is Not a Full Memory Dump

Checkpoint 不要求保存：

- 所有 conversation；
- 所有 retrieved documents；
- 所有 model output；
- private CoT；
- 全部 World；
- provider credentials。

它保存：

> **能安全恢復 execution 所必需的 canonical references。**

---

# 39. Checkpoint v1 Schema

```json
{
  "schema": "macr-agent-checkpoint/v1",
  "checkpoint_id": "cp:...",
  "agent_run_id": "...",
  "agent_run_epoch": 2,
  "state_revision": 18,

  "goal_ref": "goal:...",
  "goal_digest": "sha256:...",

  "authority_ref": "auth:...",
  "authority_digest": "sha256:...",
  "authority_revision": 4,
  "authority_epoch": 7,

  "budget_ref": "budget:...",
  "budget_digest": "sha256:...",
  "budget_revision": 3,

  "semantic_state_ref": "semgraph:...",
  "semantic_state_digest": "sha256:...",

  "active_plan_ref": "plan:...",
  "active_plan_revision": 5,

  "world_basis_refs": [],
  "pending_action_refs": [],
  "reconciliation_refs": [],

  "verification_state_ref": "verify:...",
  "wake_condition_ref": null,

  "parent_checkpoint_ref": "cp:...",
  "created_at": "...",
  "checkpoint_digest": "sha256:..."
}
```

---

# 40. Checkpoint Chain

Checkpoint 採 append-only lineage：

```text
K1
↓
K2
↓
K3
```

每一個 checkpoint 保存：

```text
parent_checkpoint_ref
```

若 lineage diverges：

```text
K2
├─ K3a
└─ K3b
```

Runtime 不得自行 last-write-wins。

應視為：

```text
CHECKPOINT_DIVERGED
```

需要 explicit resolution。

---

# 41. Checkpoint Atomicity

Checkpoint promotion 必須遵循：

```text
write candidate checkpoint
→ validate
→ fsync / durable commit
→ update AgentRun checkpoint pointer
```

不能：

```text
update pointer
→ later write checkpoint
```

否則 crash 可能產生 dangling canonical state。

---

# 42. Suspend

AgentRun 只有在：

```text
latest checkpoint durable
pending unknown effects = 0
```

時才能正常 SUSPENDED。

形式：

$$
SuspendAllowed
=
CheckpointDurable
\land
OpenReconciliation=0
$$

若有 unknown effect，狀態必須是：

```text
RECONCILIATION_REQUIRED
```

而不是 SUSPENDED。

---

# 43. Wake Condition

Wake Condition 是 data，不是 executable hidden closure。

最小種類：

```text
AT_TIME
AFTER_DURATION
EXTERNAL_EVENT
WORLD_CONDITION
HUMAN_RESPONSE
DEPENDENCY_COMPLETED
BUDGET_AVAILABLE
MANUAL_WAKE
```

---

# 44. WakeCondition v1

```json
{
  "schema": "macr-agent-wake-condition/v1",
  "wake_condition_id": "wake:...",
  "kind": "EXTERNAL_EVENT",
  "predicate_ref": "predicate:...",
  "not_before": null,
  "expires_at": "...",
  "source_scope": "github",
  "created_under_authority_ref": "auth:...",
  "created_at": "...",
  "digest": "sha256:..."
}
```

---

# 45. Wake Event

Wake event 只表示：

> 某個條件可能已成熟。

不是：

> 上次的 plan 現在仍然正確。

因此：

$$
\boxed{
\mathrm{WakeEvent}
\neq
\mathrm{ResumeAuthority}
}
$$

---

# 46. Resume Pipeline

所有 resume 必須：

```text
1. load AgentRun
2. verify terminal status == false
3. load latest checkpoint
4. verify checkpoint digest
5. verify checkpoint lineage
6. acquire new runtime ownership
7. advance epoch if required
8. revalidate current authority
9. revalidate budget
10. inspect pending actions
11. inspect open reconciliation
12. resolve world bindings
13. reobserve mutable world basis
14. invalidate stale observations/plans
15. rebuild active model context
16. transition WAKING → ACTIVE
```

不得跳過 8–14。

---

# 47. Resume Is Rehydration, Not Replay

$$
\boxed{
\mathrm{Resume}
=
\mathrm{Rehydrate}
+
\mathrm{Revalidate}
+
\mathrm{Reobserve}
}
$$

而不是：

$$
\mathrm{Resume}
=
\mathrm{ReplayLastStep}
$$

---

# 48. Stale Observation

如果 checkpoint 保存：

```text
repo HEAD = A
```

醒來後：

```text
repo HEAD = B
```

則所有以 A 為必要 basis 的 plan/action：

```text
STALE
```

不得盲目執行。

---

# 49. Stale Authority

如果：

```text
checkpoint authority epoch = 5
current authority epoch = 6
```

不能把舊 authority 恢復回去。

AgentRun 可以：

```text
rebind to new authority
```

但必須重新 admission。

---

# 50. Stale Budget

類似地：

```text
budget revision 2
```

不能蓋回 current：

```text
budget revision 4
```

checkpoint 永遠不是 authority/budget rollback mechanism。

---

# 51. Runtime Ownership

同一 AgentRun 同一 epoch 預設只能有一個 active orchestration owner。

需要：

```text
owner_id
lease
fencing_token
epoch
```

避免兩個 process 同時 resume 同一 AgentRun。

---

# 52. Fencing

任何 state mutation 都要驗證：

$$
token_{writer}
=
token_{current}
$$

否則 stale writer fail closed。

尤其：

- action dispatch；
- checkpoint promotion；
- completion；
- suspend；
- reconciliation resolution。

---

# 53. Child AgentRun

Child AgentRun 有自己的：

```text
agent_run_id
state_revision
epoch
goal
authority
budget
checkpoint
```

parent 只保存：

```text
child_agent_run_ref
delegation_ref
join_policy
```

---

# 54. Parent Failure Does Not Imply Child Authority

如果 parent crash：

child 不自動取得：

- parent ownership；
- parent budget；
- parent world mutation authority。

依 delegation policy：

```text
child continue bounded
child suspend
child cancel
```

---

# 55. Parent Completion and Children

Parent 不能 COMPLETED，如果存在必須 join 的 child：

```text
ACTIVE
WAITING
RECONCILIATION_REQUIRED
```

除非 delegation contract 明示 child 是 detached。

---

# 56. Completion Gate

Agent 自己輸出：

```text
done
```

只能形成：

```text
CompletionProposal
```

Runtime completion：

$$
Complete(R)
=
GoalSatisfied
\land
RequiredVerificationPassed
\land
RequiredReceiptsPresent
\land
OpenReconciliation=0
\land
BlockingChildren=0
\land
PolicySatisfied
$$

---

# 57. Completion Evidence

COMPLETED event 必須保存：

```text
goal_revision
completion_evidence_refs
verification_refs
final_world_observation_refs
final_plan_revision
budget_summary_ref
child_summary_refs
```

---

# 58. Failed

FAILED 不代表 evidence 被刪除。

Final state 必須保留：

```text
failure_class
last_safe_checkpoint
open/closed action summary
verification state
budget state
world basis
```

---

# 59. Cancel

Cancellation 有兩個時間點。

### Before dispatch

可以直接取消 pending action。

### After dispatch

如果 external effect 未知：

不能直接把整個 run 標記 CANCELLED 並忘掉 action。

必須先：

```text
RECONCILIATION_REQUIRED
```

完成 resolution 後才能 terminal cancellation。

---

# 60. AgentRun Event Stream

v0.7 最小 event set：

```text
agent.run_created
agent.run_admitted
agent.run_activated

agent.goal_revised

agent.authority_rebound
agent.budget_rebound

agent.observation_bound
agent.semantic_state_advanced
agent.plan_activated
agent.plan_superseded

agent.action_proposed
agent.action_admitted
agent.action_denied
agent.action_dispatched
agent.action_receipt_captured
agent.action_verified
agent.action_diverged

agent.checkpoint_created
agent.checkpoint_promoted

agent.waiting
agent.suspended
agent.wake_received
agent.waking
agent.resumed

agent.blocked

agent.reconciliation_required
agent.reconciliation_resolved

agent.child_spawned
agent.child_joined

agent.completed
agent.failed
agent.cancelled
```

---

# 61. Event Requirements

每個 event 最少：

```text
event_id
agent_run_id
agent_run_epoch
before_revision
after_revision
event_type
timestamp
bounded payload
```

state-changing event 必須滿足：

$$
afterRevision
=
beforeRevision+1
$$

---

# 62. Current State Is a Projection

AgentRun current row / SQLite state 是 event history 的 operational projection。

因此：

$$
\boxed{
\mathrm{CurrentStateProjection}
\neq
\mathrm{HistoricalEvidence}
}
$$

current row 可重建。

event / receipt evidence 不應因 rebuild 消失。

---

# 63. Public State and Private Content

AgentRun operational database 不應存：

- full prompt；
- full answer；
- secret；
- API key；
- raw private memory；
- raw large document；
- hidden reasoning。

而保存：

```text
IDs
digests
bounded status
counts
safe metadata
references
```

content 由：

- Candidate Vault；
- semantic store；
- SEDB；
- ANLA；
- Residence；
- project workspace；

各自管理。

---

# 64. State Integrity

每個 canonical state snapshot 可有：

```text
state_digest
```

定義時排除：

```text
updated_at
non-semantic runtime telemetry
```

避免 timestamps 讓 semantic state identity 無意義變動。

---

# 65. Deterministic Canonicalization

AgentRun contract 不應依 Python / JavaScript 各自 default JSON encoding 建 digest。

正式實作前應固定：

```text
canonical JSON profile
```

或：

```text
canonical CBOR
```

至少必須明定：

- Unicode normalization；
- key ordering；
- integer representation；
- decimal/float policy；
- null；
- array ordering；
- timestamps。

---

# 66. State Storage Proposal

v0.7.0 可以繼續 SQLite。

建議：

```text
agent_runs
agent_events
agent_goals
agent_world_bindings
agent_plan_bindings
agent_action_bindings
agent_checkpoints
agent_wake_conditions
agent_reconciliation
agent_children
```

但這只是 physical design。

Canonical contract 不依賴 SQLite。

---

# 67. Crash Recovery Classes

Crash 後至少分類：

```text
C0 — no canonical mutation begun
C1 — state event committed, projection not refreshed
C2 — checkpoint candidate written, not promoted
C3 — checkpoint promoted
C4 — action admitted, not dispatched
C5 — provider dispatch definitely not performed
C6 — provider dispatch performed and receipt known
C7 — provider dispatch performed, effect unknown
C8 — receipt known, outcome verification incomplete
```

其中：

```text
C7
```

必須：

```text
RECONCILIATION_REQUIRED
```

---

# 68. Exactly-Once Is Not Universally Claimed

MACR 不應宣稱任意 external provider 都 exactly-once。

可實作的是：

- exactly-once local state promotion；
- idempotent internal events；
- bounded provider attempt；
- idempotency key when provider supports；
- explicit uncertain-effect classification。

因此：

$$
\boxed{
\mathrm{ExactlyOnceRuntimeState}
\not\Rightarrow
\mathrm{ExactlyOnceExternalWorld}
}
$$

---

# 69. Retry

只有：

$$
KnownNoExternalEffect=1
$$

時才自動 retry。

其他情況：

```text
RECONCILE
```

---

# 70. Replay

MACR 可以支援 deterministic replay of:

```text
state transitions
policy decisions
canonical plan compilation
semantic transformations
```

但不能假裝重播 external world side effects。

因此：

$$
\boxed{
\mathrm{StateReplay}
\neq
\mathrm{WorldReplay}
}
$$

---

# 71. AgentRun vs Conversation

一個 AgentRun 可有：

```text
0 conversations
1 conversation
many conversations
```

例如 background repository maintenance agent 不需要 chat conversation。

而 Direct Chat 可以沒有 AgentRun。

---

# 72. AgentRun vs Workspace

一個 AgentRun 可以綁定 MRMIC workspace。

但：

$$
\boxed{
\mathrm{Workspace}
\neq
\mathrm{AgentRun}
}
$$

workspace 可以在 AgentRun 結束後仍保存。

AgentRun 也可以完全沒有 Canvas workspace。

---

# 73. AgentRun vs Resident

AgentRun 可以：

```text
resident_ref = null
```

這是正常狀態。

只有真正需要私人 identity continuity 時才透過 LIMEN resolve。

---

# 74. AgentRun vs Semantic Graph

Semantic graph 可以跨 AgentRun 保存。

例如：

```text
project semantic knowledge
```

被多個 AgentRun 使用。

因此：

$$
\boxed{
\mathrm{SemanticStateObject}
\neq
\mathrm{AgentRunIdentity}
}
$$

---

# 75. Minimal API Surface

v0.7.0 初始 internal API 建議：

```text
create_agent_run()
admit_agent_run()
activate_agent_run()

get_agent_run()
list_agent_runs()

revise_goal()
rebind_authority()
rebind_budget()

bind_observation()
advance_semantic_state()
activate_plan()

propose_action()
admit_action()
record_dispatch()
record_receipt()
record_verification()

create_checkpoint()
promote_checkpoint()

suspend_agent_run()
receive_wake()
resume_agent_run()

block_agent_run()

require_reconciliation()
resolve_reconciliation()

complete_agent_run()
fail_agent_run()
cancel_agent_run()
```

---

# 76. API Authority

這些 API 本身也不能全部由 Agent 呼叫。

例如：

Agent 可以：

```text
propose_action
request_checkpoint
propose_goal_revision
```

但：

```text
rebind_authority
expand_budget
resolve_reconciliation
force_complete
```

應屬 host/operator/policy authority。

---

# 77. Agent-Facing vs Host-Facing APIs

正式分離：

### Agent-facing

```text
observe
plan
propose
checkpoint_request
suspend_request
completion_proposal
```

### Host/runtime-facing

```text
admit
authorize
dispatch
commit checkpoint
wake
reconcile
complete
cancel
```

---

# 78. Agent Self-Termination

Agent 可以提出：

```text
STOP
```

但 Runtime 仍分類：

```text
goal completed
blocked
budget stop
voluntary suspend
failure
```

避免所有 STOP 都被當成成功。

---

# 79. Invariants

v0.7.0 必須硬驗以下 invariants。

### I-01

$$
\mathrm{InvocationRunID}
\neq
\mathrm{AgentRunID}
$$

### I-02

$$
\mathrm{AgentRun}
\neq
\mathrm{ModelSession}
$$

### I-03

$$
\mathrm{GoalProposal}
\neq
\mathrm{GoalRevision}
$$

### I-04

$$
\mathrm{Capability}
\neq
\mathrm{Authority}
$$

### I-05

$$
\mathrm{Checkpoint}
\neq
\mathrm{AuthorityRollback}
$$

### I-06

$$
\mathrm{Wake}
\neq
\mathrm{ResumeAuthority}
$$

### I-07

$$
\mathrm{Observation}
\neq
\mathrm{CurrentWorld}
$$

### I-08

$$
\mathrm{Plan}
\neq
\mathrm{Command}
$$

### I-09

$$
\mathrm{Receipt}
\neq
\mathrm{OutcomeVerification}
$$

### I-10

$$
\mathrm{UnknownAfterDispatch}
\Rightarrow
\mathrm{ReconciliationRequired}
$$

### I-11

$$
\mathrm{OpenReconciliation}>0
\Rightarrow
\mathrm{NoNewExternalMutation}
$$

### I-12

$$
\mathrm{TerminalAgentRun}
\not\rightarrow
\mathrm{Active}
$$

### I-13

$$
\mathrm{StateRevision}_{t+1}
=
\mathrm{StateRevision}_t+1
$$

### I-14

$$
\mathrm{StaleEpochWriter}
\Rightarrow
\mathrm{Reject}
$$

### I-15

$$
\mathrm{Resume}
\Rightarrow
\mathrm{Revalidate}
+
\mathrm{Reobserve}
$$

---

# 80. v0.7.0 Acceptance Test Matrix

最低必須驗證：

## Identity

- AgentRun UUID 與 invocation UUID 分離；
- same goal 建立兩次 AgentRun 得到兩個 run identity；
- subject digest deterministic。

## Lifecycle

- legal transitions pass；
- illegal shortcut fail closed；
- terminal reopen rejected。

## Revision

- revision strictly increments；
- stale revision writer rejected；
- epoch fence works。

## Authority

- expired authority blocks actuation；
- old epoch authority rejected；
- retrieved text cannot grant authority。

## Budget

- over-budget action rejected；
- Agent cannot self-expand budget；
- checkpoint cannot restore older budget.

## World

- stale world observation invalidates dependent plan；
- world binding revision mismatch detected。

## Action

- admitted but not dispatched can cancel safely；
- known no-dispatch failure may retry；
- unknown-after-dispatch enters reconciliation；
- new mutation blocked during reconciliation。

## Checkpoint

- candidate checkpoint cannot become current before validation；
- corrupted checkpoint rejected；
- divergent checkpoint lineage rejected；
- latest valid checkpoint resumes。

## Wake

- wake from stale checkpoint requires re-observation；
- expired authority after wake blocks actuation；
- wake does not automatically execute old action.

## Completion

- model `done` does not directly complete；
- unresolved reconciliation blocks completion；
- required verification failure blocks success；
- verified completion becomes terminal.

---

# 81. Required Negative Controls

至少包含：

```text
NC-01 duplicate AgentRun ID
NC-02 invalid state transition
NC-03 revision rollback
NC-04 skipped revision
NC-05 stale epoch writer
NC-06 stale authority
NC-07 authority text forgery
NC-08 budget revision rollback
NC-09 stale observation blind action
NC-10 checkpoint tampering
NC-11 checkpoint dangling pointer
NC-12 divergent checkpoint lineage
NC-13 duplicate active owner
NC-14 unknown-after-dispatch retry
NC-15 mutation during reconciliation
NC-16 reconciliation self-resolution by Agent
NC-17 scope-expanding goal revision without re-admission
NC-18 Agent self-budget expansion
NC-19 child authority greater than parent
NC-20 terminal AgentRun resume
NC-21 wake directly invokes stale plan
NC-22 provider receipt falsely treated as verified outcome
NC-23 cancellation hides unknown action effect
NC-24 model output directly mutates AgentRun state
```

---

# 82. Persistence Safety Boundary

AgentRun v0.7.0 第一版可以仍為 single-machine local runtime。

不宣稱：

- distributed consensus；
- cross-machine fencing；
- Byzantine tolerance；
- globally distributed Agent ownership；
- exactly-once arbitrary cloud mutation；
- encrypted persistence；
- multi-tenant production security。

這些屬後續版本。

---

# 83. Relationship to PNCW

AgentRun 不自己驗證世界 projection。

保存：

```text
VerifiedObservationRef
```

PNCW 負責：

```text
readiness
projection
verification
visibility
```

MACR 只判斷：

```text
這個 observation 是否仍可作為 current planning basis？
```

---

# 84. Relationship to PHOSPHOR Spacetime

AgentRun：

```text
何時要做什麼
```

與：

```text
CommandIntent 如何進入世界
```

應保持分離。

PHOSPHOR 可提供：

- temporal/causal IR；
- CommandIntent；
- authority gate adapter；
- actuation receipt；
- measured outcome。

---

# 85. Relationship to EML-U

本規格的：

```text
Goal
Observation
Plan
Action
Constraint
Receipt
Verification
Checkpoint
```

未來可投影成 EML-U Semantic Nodes。

但 v0.7.0 不要求 EML-U runtime。

---

# 86. Relationship to SEDB

AgentRun scheduler / ownership state 留在 MACR。

SEDB 可保存：

- long-term semantic evolution；
- claims；
- decisions；
- world distinctions；
- receipts；
- provenance。

不直接讓 SEDB 決定 Agent lifecycle。

---

# 87. Relationship to LIMEN

若：

```text
resident_ref == null
```

不需要 LIMEN。

若 Agent 要讀 private Residence：

```text
AgentRun
→ LIMEN resolve
→ immutable identity/access envelope
→ minimum private projection
```

AgentRun 只保存 envelope reference。

---

# 88. Proposed File/Module Boundary

未來 MACR source 可新增：

```text
src/macr_runtime/agent/
├─ state.py
├─ lifecycle.py
├─ store.py
├─ events.py
├─ checkpoint.py
├─ wake.py
├─ reconciliation.py
├─ ownership.py
├─ goal.py
├─ budget.py
└─ contracts.py
```

不要求現在就採這個 exact path，但 responsibility 建議保持分離。

---

# 89. Proposed Database Boundary

建議新增：

```text
runtime/agent.sqlite3
```

而不是直接塞進 Direct Chat database。

Direct conversation schema 與 AgentRun schema 必須分離。

$$
\boxed{
\mathrm{DirectConversationStore}
\neq
\mathrm{AgentRuntimeStore}
}
$$

---

# 90. Migration

MACR v0.6 沒有 AgentRun。

因此 v0.7 migration 不應把 historical provider invocation 自動偽造成 AgentRun。

舊資料保持：

```text
legacy delegated execution
direct conversation
```

只有 v0.7 建立後的新 Agent execution 使用 AgentRun。

---

# 91. Observability CLI

v0.7.0 最小可提供：

```text
macr agent list
macr agent status <agent-run-id>
macr agent events <agent-run-id>
macr agent checkpoint <agent-run-id>
macr agent suspend <agent-run-id>
macr agent wake <agent-run-id>
macr agent reconcile <agent-run-id>
macr agent cancel <agent-run-id>
```

普通 status 不輸出：

- prompt；
- candidate answer；
- credentials；
- private memory content。

---

# 92. Example Runtime

Goal：

```text
Find and repair the failing tests in repository X.
```

AgentRun：

```text
CREATED
→ ADMITTED
→ ACTIVE
```

Step 1：

```text
observe repository
```

取得：

```text
VerifiedObservation O1
```

Plan：

```text
P1
```

Run tests：

```text
Invocation R1
```

得到 failure。

讀 code：

```text
O2
```

建立：

```text
ActionProposal A1
```

authority gate：

```text
branch-local write allowed
```

執行 patch：

```text
Invocation / Actuation R2
```

receipt：

```text
patch applied
```

重新測試：

```text
R3
```

重新觀察 repo：

```text
O3
```

verification：

```text
tests passed
diff bounded
no forbidden paths
```

checkpoint：

```text
K4
```

completion：

```text
COMPLETED
```

---

# 93. Crash Example

若 crash 發生於：

```text
GitHub API update request sent
→ process dies
→ no receipt persisted
```

重啟後不能：

```text
send same update again
```

而應：

```text
AgentRun
→ RECONCILIATION_REQUIRED
→ reobserve GitHub resource
→ classify actual outcome
→ resolution receipt
→ new epoch
→ resume
```

這就是 AgentRun state machine 相較一般 Agent loop 的核心必要性。

---

# 94. Formal Resume Safety

安全 resume 條件：

$$
SafeResume(R,K,t)
=
Integrity(K)
\land
CurrentAuthorityCompatible(K,t)
\land
CurrentBudgetCompatible(K,t)
\land
NoUnknownEffect(R)
\land
WorldBasisRevalidated(R,t)
$$

若：

$$
SafeResume=0
$$

則不得：

```text
WAKING → ACTIVE
```

---

# 95. Formal Mutation Safety

Agent action $a$ 可 dispatch：

$$
Dispatchable(a,R,t)
=
Active(R)
\land
Capability(a)
\land
Authority(a,R,t)
\land
Budget(a,R,t)
\land
Policy(a,R,t)
\land
FreshBasis(a,R,t)
\land
OpenReconciliation(R)=0
$$

這應成為 v0.7.0 最重要的 runtime theorem-like invariant。

---

# 96. Canonical Closure

本文件固定：

1. AgentRun 是 v0.7 的 long-lived execution unit。
2. AgentRun 不取代現行 provider invocation `run_id`。
3. AgentRun 使用 occurrence identity + deterministic subject digest。
4. state revision 與 runtime epoch 分離。
5. authority revision/epoch 必須在 actuation 時重新驗證。
6. checkpoint 不可回復舊 authority 或舊 budget。
7. resume 必須 rehydrate + revalidate + reobserve。
8. wake 不等於 authorization。
9. observation 不等於 current World。
10. model output 不直接成為 Agent canonical state。
11. unknown-after-dispatch 必須進 reconciliation。
12. open reconciliation 時禁止新的 external mutation。
13. terminal AgentRun 不得 reopen。
14. completion 是 runtime verification gate，不是模型文字。
15. Direct Chat、provider invocation、AgentRun 的 storage 與語義保持分離。
16. AgentRun current state 是 operational projection；event/receipt history 是 evidence。
17. hidden chain-of-thought 不屬於 AgentRun canonical persistence。
18. v0.7.0 可先 single-machine / SQLite 實作，不宣稱 distributed guarantees。

因此：

$$
\boxed{
\mathrm{AgentRun}
=
\mathrm{Durable}
+
\mathrm{Governed}
+
\mathrm{Revisable}
+
\mathrm{Recoverable}
+
\mathrm{Fenced}
\;
\mathrm{ExecutionLineage}
}
$$

而 MACR v0.7.0 的 Agent autonomy 將不再建立於：

```text
while true:
    ask_model()
    call_tool()
```

而建立於：

$$
\boxed{
State
+
Authority
+
WorldBasis
+
ActionLifecycle
+
Checkpoint
+
Reconciliation
+
Verification
}
$$

這構成 MACR Agent-Spacetime Runtime 的第一個正式工程核心。

---

# Appendix A — Core Contract Set

v0.7.0 AgentRun 最低需要：

```text
macr-agent-run/v1
macr-agent-goal/v1
macr-agent-budget/v1
macr-agent-world-binding/v1
macr-agent-action/v1
macr-agent-checkpoint/v1
macr-agent-wake-condition/v1
macr-agent-reconciliation/v1
macr-agent-event/v1
```

後續文件分別細化。

---

# Appendix B — Compatibility with MACR v0.6

保留：

```text
DispatchOrigin
AuthorizationReference
DispatchContext
ProviderExecution
VerificationState
AcceptanceState
TaskContract
CoordinationPlan
PlanRevision
Candidate Vault
Accounting
Operational Events
T1 Reconciliation Semantics
```

新增 AgentRun 後：

```text
AgentRun
  ↓
Action / Cognitive Step
  ↓
Plan / TaskContract
  ↓
DispatchContext
  ↓
Invocation run_id
  ↓
Provider / Worker
```

因此 v0.7 是向上增加 orchestration layer，而不是推翻 v0.6 execution core。

---

# Appendix C — Next Canonical Specification

下一份：

**MACR v0.7 — Agent Semantic Envelope Specification v0.1**

它將正式定義：

```text
Goal
Observation
Claim
Hypothesis
Plan
Task
ActionProposal
Constraint
Decision
Receipt
Verification
Checkpoint
Failure
WakeCondition
```

如何成為：

$$
Tree\ IR
+
Graph\ IR
+
Event\ IR
$$

相容的 provisional semantic model，並保持未來遷移至 EML-U Canonical Semantic IR 的能力。