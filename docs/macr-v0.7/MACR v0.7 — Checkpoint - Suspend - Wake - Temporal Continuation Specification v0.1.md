# MACR v0.7 — Checkpoint / Suspend / Wake / Temporal Continuation Specification v0.1

## Agent 檢查點、暫停、喚醒、時間語意與持續執行契約 v0.1

**Document ID:** `MACR-V07-CSWTC-2026-v0.1`  
**Parent Architecture:** `MACR-ASR-CCA-2026-v0.1`  
**Parent State Spec:** `MACR-V07-AGENTRUN-STATE-2026-v0.1`  
**Parent Semantic Spec:** `MACR-V07-ASE-2026-v0.1`  
**Parent Action Spec:** `MACR-V07-AAEC-2026-v0.1`  
**Observation Bridge:** `MACR-PNCW-VOBS-BRIDGE-2026-v0.1`  
**Actuation Bridge:** `MACR-PHOSPHOR-GAB-2026-v0.1`  
**Project:** MACR  
**Target:** MACR v0.7.x — Agent-Spacetime Runtime  
**Date:** 2026-08-30  
**Status:** Canonical Temporal Runtime Specification / Pre-Implementation  
**Organization:** EveMissLab / 一言諾科技有限公司  
**Language:** Traditional Chinese

---

# 摘要

一般 request/response AI 的生命週期近似：

$$
Request
\rightarrow
Compute
\rightarrow
Response
\rightarrow
End
$$

真正的 Agent Runtime 則必須支援：

$$
\boxed{
Run
\rightarrow
Observe
\rightarrow
Act
\rightarrow
Checkpoint
\rightarrow
Suspend
\rightarrow
Wake
\rightarrow
Reobserve
\rightarrow
Continue
}
$$

Agent 可以在完全不進行模型 inference 的狀態下持續存在。

它可以：

- 等待一個時間點；
- 等待另一個 Agent；
- 等待 provider 完成；
- 等待外部世界改變；
- 等待人類決策；
- 等待 budget 恢復；
- 等待 domain logical time；
- 等待一個 causal event；
- 在程序重新啟動後恢復；
- 在模型已被替換後繼續同一 AgentRun。

因此：

$$
\boxed{
\mathrm{AgentPersistence}
\neq
\mathrm{ContinuousInference}
}
$$

而：

$$
\boxed{
\mathrm{AgentTime}
\neq
\mathrm{ModelComputeTime}
}
$$

本規格正式定義 MACR v0.7 的：

- checkpoint；
- checkpoint lineage；
- suspend；
- waiting；
- wake condition；
- wake event；
- wall-clock time；
- duration；
- domain logical time；
- external event；
- provider completion；
- human response；
- dependency completion；
- wake admission；
- waking；
- rehydration；
- authority revalidation；
- budget revalidation；
- observation revalidation；
- plan invalidation；
- resume；
- temporal fencing；
- crash recovery；
- long-running action；
- event loss；
- duplicated wake；
- temporal reconciliation；
- completion continuity。

---

# 0. Canonical Decision

MACR v0.7 將 Agent 定義為：

> **可以跨越非計算時間持續存在的 governed execution lineage。**

因此：

$$
\boxed{
\mathrm{AgentRunLifetime}
\supseteq
\mathrm{InferenceLifetime}
}
$$

AgentRun 可以存在數秒、數小時、數天甚至更久，而不要求任何 provider session 持續存在。

---

# 1. Core Temporal Invariants

## T-01

$$
\boxed{
\mathrm{Time}
\neq
\mathrm{Compute}
}
$$

## T-02

$$
\boxed{
\mathrm{Suspend}
\neq
\mathrm{Terminate}
}
$$

## T-03

$$
\boxed{
\mathrm{Wake}
\neq
\mathrm{Resume}
}
$$

## T-04

$$
\boxed{
\mathrm{Wake}
\neq
\mathrm{Authorization}
}
$$

## T-05

$$
\boxed{
\mathrm{Resume}
\neq
\mathrm{Replay}
}
$$

## T-06

$$
\boxed{
\mathrm{Checkpoint}
\neq
\mathrm{MemoryDump}
}
$$

## T-07

$$
\boxed{
\mathrm{Checkpoint}
\neq
\mathrm{AuthoritySnapshotRollback}
}
$$

## T-08

$$
\boxed{
\mathrm{WallClock}
\neq
\mathrm{DomainLogicalTime}
}
$$

## T-09

$$
\boxed{
\mathrm{EventOccurred}
\neq
\mathrm{GoalAuthorized}
}
$$

## T-10

$$
\boxed{
\mathrm{OldObservation}
\neq
\mathrm{CurrentWorld}
}
$$

---

# 2. Temporal Agent State

定義 AgentRun temporal state：

$$
\mathcal T_A
=
(
K,
C,
W,
D,
E,
L
)
$$

其中：

- $K$：latest checkpoint；
- $C$：current temporal lifecycle state；
- $W$：wake condition set；
- $D$：delayed continuation state；
- $E$：received external event references；
- $L$：logical / wall-clock bindings。

---

# 3. Waiting vs Suspended

兩者不得混用。

## WAITING

用於短期、runtime-local dependency。

例如：

```text
child worker running
local test process running
local verifier pending
```

Runtime process通常仍持有 active AgentRun lease。

## SUSPENDED

用於 durable continuation。

例如：

```text
tomorrow continue
wait for GitHub event
wait for human approval
wait for remote provider completion
wait until logical time 500
```

此時 AgentRun 不需要 active process。

---

# 4. Formal Difference

$$
Waiting
=
ActiveOwnership
+
TemporaryDependency
$$

而：

$$
Suspended
=
DurableCheckpoint
+
NoActiveMutationOwnership
+
WakeCondition
$$

---

# 5. Suspend Preconditions

正常 suspend 必須至少：

$$
CheckpointDurable=1
$$

$$
OpenUnknownEffect=0
$$

$$
TemporalConditionValid=1
$$

因此：

$$
\boxed{
SuspendAllowed
=
CheckpointDurable
\land
NoOpenReconciliation
\land
WakeStateValid
}
$$

---

# 6. Unknown Effects Block Normal Suspension

如果 external action 已 dispatch，但結果未知：

```text
UNKNOWN_AFTER_DISPATCH
```

AgentRun 不得單純：

```text
SUSPENDED
```

而必須：

```text
RECONCILIATION_REQUIRED
```

必要時 reconciliation subsystem 本身可以等待外部事件，但不能把未知 effect 隱藏在普通 suspended state 裡。

---

# 7. Checkpoint

Checkpoint 定義為：

> **AgentRun 某一 canonical revision 上，可供安全重新建構 execution continuation 的 immutable durable artifact。**

不是 RAM snapshot。

不是 Python process dump。

不是 model KV cache。

不是完整 conversation export。

---

# 8. Checkpoint Formal State

$$
K_t
=
(
R,
E,
G,
A,
B,
S,
P,
O,
X,
V,
W
)
$$

其中：

- $R$：AgentRun identity / revision；
- $E$：AgentRun epoch；
- $G$：Goal；
- $A$：Authority reference；
- $B$：Budget reference；
- $S$：Semantic state；
- $P$：Plan；
- $O$：Observation basis；
- $X$：pending execution；
- $V$：verification；
- $W$：wake / continuation information。

---

# 9. Checkpoint Content Principle

Checkpoint 保存：

> **references required for recovery**

而不是：

> **every byte the Agent has ever encountered**

---

# 10. Required Checkpoint Fields

```text
checkpoint_id
agent_run_id
agent_run_epoch
state_revision

goal_ref
goal_digest

authority_ref
authority_digest
authority_revision
authority_epoch

budget_ref
budget_digest
budget_revision

semantic_state_ref
semantic_state_digest
semantic_state_revision

active_plan_ref
active_plan_digest
active_plan_revision

world_basis_refs
pending_action_refs
pending_external_operation_refs
open_reconciliation_refs

verification_state_ref
wake_condition_ref

parent_checkpoint_ref
created_at
checkpoint_digest
```

---

# 11. Checkpoint Must Not Contain

```text
API key plaintext
OAuth token
authorization header
hidden chain-of-thought
provider secret
entire private Residence database
arbitrary unbounded context
live process handles
stale socket descriptors
```

---

# 12. Provider Session Is Not Checkpoint State

若 Agent 使用：

```text
Grok
GLM
Qwythos
Gemini
```

checkpoint 不依賴 provider conversation session 永久存在。

因此：

$$
\boxed{
\mathrm{Checkpoint}
\neq
\mathrm{ProviderSession}
}
$$

---

# 13. Model Replacement

一個 AgentRun 可以：

```text
before suspend: Grok
after wake: GLM
```

只要 semantic / authority / task contracts允許。

因此：

$$
\boxed{
\mathrm{AgentContinuity}
\neq
\mathrm{ModelContinuity}
}
$$

---

# 14. Checkpoint Lineage

Checkpoint 必須是 append-only lineage：

```text
K1
↓
K2
↓
K3
```

每一個：

```text
parent_checkpoint_ref
```

指向前一個 promoted checkpoint。

---

# 15. No Historical Rewrite

若 $K_3$ 錯誤：

不能修改 $K_3$。

建立：

```text
K4
supersedes K3
```

或 recovery record。

---

# 16. Divergent Checkpoints

若：

```text
K2
├─ K3a
└─ K3b
```

且兩者都宣稱 current head：

```text
CHECKPOINT_DIVERGENCE
```

不得 last-write-wins。

---

# 17. Checkpoint Promotion

建議：

```text
BUILD
↓
VALIDATE
↓
DURABLY_WRITE
↓
PROMOTE
↓
UPDATE AGENT HEAD
```

---

# 18. Candidate Checkpoint

建立中的 checkpoint：

```text
CANDIDATE
```

不是 current recovery authority。

---

# 19. Promotion Atomicity

AgentRun current checkpoint pointer 只有在 checkpoint durable 後才更新。

$$
\boxed{
PromotePointer
\Rightarrow
CheckpointDurable
}
$$

---

# 20. Checkpoint Digest

$$
D_K
=
H(
Run,
Epoch,
Revision,
Goal,
Authority,
Budget,
SemanticState,
Plan,
WorldBasis,
PendingActions,
Verification,
WakeCondition
)
$$

timestamps 不必作 semantic digest核心。

---

# 21. Checkpoint Frequency

不要求每一個 reasoning step 都 checkpoint。

可依：

```text
after external mutation
before suspend
after plan revision
after major observation
before risky action
periodic durability policy
```

建立。

---

# 22. Mandatory Checkpoint Boundaries

v0.7 至少：

```text
before SUSPENDED
after verified external mutation
after reconciliation resolution
before long-running asynchronous handoff
before runtime ownership release
```

---

# 23. Suspend

Suspend 是 AgentRun lifecycle transition：

```text
ACTIVE
→ SUSPENDED
```

且必須形成：

```text
agent.suspended
```

event。

---

# 24. Suspend Record

```json
{
  "schema": "macr-agent-suspend/v1",
  "agent_run_id": "...",
  "checkpoint_ref": "cp:...",
  "wake_condition_ref": "wake:...",
  "suspended_from_revision": 42,
  "reason": "WAIT_EXTERNAL_EVENT",
  "suspended_at": "...",
  "digest": "sha256:..."
}
```

---

# 25. Suspend Reason

最低：

```text
WAIT_TIME
WAIT_EVENT
WAIT_HUMAN
WAIT_DEPENDENCY
WAIT_PROVIDER
WAIT_WORLD_CONDITION
WAIT_BUDGET
MANUAL_SUSPEND
```

---

# 26. Suspend Does Not Preserve Active Lease

正常 suspend 後：

```text
active_owner = none
```

避免一個已 suspend 的 AgentRun 還持有 mutation lease。

---

# 27. Suspend Does Preserve Lineage

AgentRun identity 不變。

$$
\boxed{
Suspend(R)
\Rightarrow
SameAgentRunID
}
$$

---

# 28. Wake Condition

WakeCondition 描述：

> 哪種未來 evidence 可以使 AgentRun 進入重新評估 continuation 的流程。

---

# 29. Wake Condition Types

```text
AT_TIME
AFTER_DURATION
EXTERNAL_EVENT
DOMAIN_LOGICAL_TIME
WORLD_CONDITION
HUMAN_RESPONSE
DEPENDENCY_COMPLETED
PROVIDER_COMPLETED
BUDGET_AVAILABLE
MANUAL_WAKE
```

---

# 30. Wake Condition Is Declarative

不能保存：

```text
arbitrary Python closure
```

應保存 machine-readable predicate / reference。

---

# 31. WakeCondition v1

```json
{
  "schema": "macr-agent-wake-condition/v1",
  "wake_condition_id": "wake:...",
  "agent_run_id": "...",
  "kind": "AT_TIME",

  "clock": {
    "kind": "WALL_CLOCK",
    "domain_ref": null
  },

  "predicate": {
    "at": "2026-08-31T08:00:00+08:00"
  },

  "source_scope": null,
  "not_before": null,
  "expires_at": null,

  "created_under_authority_ref": "auth:...",
  "created_at": "...",
  "digest": "sha256:..."
}
```

---

# 32. Wall-Clock Time

Wall-clock：

$$
T_W
$$

表示現實時間。

例如：

```text
tomorrow 08:00
in 4 hours
2026-09-01 17:00
```

---

# 33. Duration

`AFTER_DURATION`：

$$
t_{wake}
=
t_{suspend}
+
\Delta t
$$

---

# 34. Duration Must Bind Origin

不能只保存：

```text
4 hours
```

而失去：

```text
from when?
```

必須保存 suspend anchor / computed target。

---

# 35. Domain Logical Time

PHOSPHOR domain可具有：

$$
T_D
$$

其進度不必等於 wall-clock。

---

# 36. Logical-Time Wake

例如：

```text
wake when domain local_time >= 500
```

必須保存：

```text
domain_ref
domain_epoch
logical predicate
```

---

# 37. Domain Time Is Epoch-Bound

provider/domain重啟可能改變 logical-time lineage。

因此：

```text
domain epoch changed
```

不能 blind interpret old logical target。

---

# 38. Logical-Time Revalidation

Wake 時：

```text
resolve current domain
verify lineage
verify epoch
read logical time
```

再決定 predicate 是否成立。

---

# 39. Time Rate Change

若 suspend期間 domain temporal rate 被更改：

logical wake semantics仍以 logical condition 為準。

不能重新解釋為 original wall-clock estimate。

---

# 40. Event Wake

External event可來自：

```text
GitHub
Gmail
MRMIC
PHOSPHOR
filesystem watcher
database
child Agent
provider
human UI
```

---

# 41. Event Does Not Directly Resume

Event只產生：

```text
WakeEvent
```

然後：

```text
SUSPENDED
→ WAKING
```

---

# 42. WakeEvent v1

```json
{
  "schema": "macr-agent-wake-event/v1",
  "wake_event_id": "wake-event:...",
  "agent_run_id": "...",
  "wake_condition_ref": "wake:...",
  "source": "github",
  "source_event_ref": "...",
  "received_at": "...",
  "source_event_time": "...",
  "deduplication_key": "...",
  "digest": "sha256:..."
}
```

---

# 43. Duplicate Wake

同一 external event可能被重送。

因此：

$$
Wake(e)^n
=
Wake(e)
$$

對同一 deduplication identity應 idempotent。

---

# 44. Duplicate Wake Does Not Create Parallel Resume

如果 Agent 已 WAKING / ACTIVE：

重複 wake event只記錄 evidence或去重。

---

# 45. Multiple Wake Conditions

AgentRun 可以等待：

```text
time OR human response
```

或：

```text
dependency A AND dependency B
```

---

# 46. Composite Wake

建議 future：

```text
ANY_OF
ALL_OF
```

但 v0.7.0 最小可以先支援單條件 + runtime fan-in。

---

# 47. Wake Expiry

WakeCondition 可以過期。

例如：

```text
wait for approval until Friday
```

過期後：

```text
BLOCKED
FAILED
or alternative plan
```

由 policy決定。

---

# 48. Human Wake

Human response：

```text
approval
rejection
clarification
new instruction
manual resume
```

都可以喚醒。

---

# 49. Human Message Is Not Automatically Approval

Human回：

```text
OK
```

必須解析並綁 exact pending subject。

否則不能拿來批准任意 action。

---

# 50. Provider Completion Wake

長期 provider job：

```text
command
→ accepted
→ async execution
```

Agent 可以 suspend。

provider completion：

```text
wake
```

---

# 51. Provider Completion Must Be Queryable

正常 durable async suspension最好要求：

```text
durable operation id
status query contract
provider identity
provider epoch semantics
```

---

# 52. Provider Event Loss

若 completion webhook/event遺失：

Agent不能永遠卡死。

可有：

```text
fallback status query
timeout wake
manual reconciliation
```

---

# 53. Provider Completion Is Not Outcome Verification

即使 provider說：

```text
completed
```

醒來後仍：

```text
PNCW reobserve
→ verify
```

---

# 54. Dependency Wake

Child Agent完成：

```text
child.completed
```

可喚醒 parent。

---

# 55. Child Completion Does Not Mean Parent Goal Complete

Child只回傳 bounded result。

Parent仍需 join / verify。

---

# 56. Budget Wake

若 Agent因 budget exhausted suspend/block：

budget owner新增 budget revision後：

```text
budget_available
```

可以觸發 wake。

---

# 57. Budget Wake Requires Rebinding

Wake後：

```text
old budget revision
```

不能直接繼續。

必須 bind current budget revision。

---

# 58. World Condition Wake

例如：

```text
wake when GitHub CI finishes
wake when file exists
wake when domain becomes ACTIVE
```

條件本身應由 observation mechanism檢查。

---

# 59. Condition Wake Is Not Polling by Definition

實作可用：

```text
event subscription
scheduled probe
provider notification
periodic observation
```

但 semantic contract只有 condition。

---

# 60. Polling Frequency

Polling屬 scheduler policy。

不能寫死在 Goal semantics。

---

# 61. Wake Admission

收到 WakeEvent 後：

```text
validate event
validate condition
validate run state
acquire ownership
```

才進：

```text
WAKING
```

---

# 62. WAKING

WAKING 是 security / recovery state，不是 cosmetic transition。

Agent此時禁止 external mutation。

---

# 63. WAKING Pipeline

```text
1. verify AgentRun is non-terminal
2. verify wake event / manual wake legitimacy
3. load latest promoted checkpoint
4. verify checkpoint digest
5. verify checkpoint lineage
6. acquire active ownership lease
7. establish new or current AgentRun epoch
8. revalidate authority
9. revalidate budget
10. inspect pending external operations
11. inspect reconciliation state
12. resolve world bindings
13. revalidate mutable observations
14. invalidate stale plans/actions
15. rehydrate semantic working state
16. rebuild model context if needed
17. decide ACTIVE / BLOCKED / RECONCILIATION_REQUIRED
```

---

# 64. Rehydration

Rehydration：

> 從 canonical references 重新建立 runtime working state。

不是：

> 復原舊 process記憶體。

---

# 65. Rehydrate Semantic State

讀：

```text
semantic_state_ref
semantic_state_digest
semantic_state_revision
```

驗 integrity。

---

# 66. Rehydrate Plan

active plan可能：

```text
still valid
stale
superseded
invalid
```

不能直接設回 ACTIVE。

---

# 67. Rehydrate Observation Basis

每個 mutable VerifiedObservationRef：

```text
freshness check
```

必要時重新走 PNCW。

---

# 68. Rehydrate Pending Action

分類：

```text
NOT_DISPATCHED
DISPATCHED_KNOWN
OUTCOME_KNOWN
OUTCOME_UNKNOWN
```

---

# 69. Outcome Unknown Dominates Resume

若任一：

```text
OUTCOME_UNKNOWN
```

則：

```text
WAKING
→ RECONCILIATION_REQUIRED
```

而不是 ACTIVE。

---

# 70. Authority Revalidation

checkpoint authority只能回答：

> 當時使用的是哪個 authority。

不能回答：

> 現在仍有效嗎？

---

# 71. Current Authority Wins

$$
Auth_{current}
$$

永遠優先於 checkpoint中的：

$$
Auth_{historical}
$$

---

# 72. Authority Revoked During Suspend

醒來：

```text
AUTHORITY_DENIED / BLOCKED
```

不能把 checkpoint舊 authority restore。

---

# 73. Authority Expanded During Suspend

即使新 authority更大：

Agent也不自動擴大 action scope。

仍受 current Goal / Plan限制。

---

# 74. Budget Revalidation

同理：

$$
Budget_{checkpoint}
\neq
Budget_{current}
$$

resume使用 current budget。

---

# 75. World Re-observation

這是 resume 的核心。

$$
\boxed{
Resume
\Rightarrow
MutableWorldRevalidation
}
$$

---

# 76. Observation Freshness Classes

可分類：

```text
IMMUTABLE_VALID
CURRENT
STALE
UNKNOWN
UNAVAILABLE
CONFLICT
```

---

# 77. Stale Observation

相關 plan：

```text
STALE
```

相關 undispatched action：

```text
STALE
```

重新 observation / planning。

---

# 78. Stale Does Not Fail Agent

AgentRun可以：

```text
WAKING
→ ACTIVE
```

並建立新 plan。

---

# 79. Plan Revalidation

Plan有效條件：

$$
GoalRevisionCurrent
\land
BasisFresh
\land
ConstraintsCurrent
$$

---

# 80. Goal Revalidation

若 suspend期間 Goal被 human revised：

resume不能繼續 old Goal plan。

---

# 81. Goal Cancellation

如果 current Goal 已 cancelled：

```text
WAKING
→ CANCELLED
```

而不是 ACTIVE。

---

# 82. Plan Supersession During Suspend

如果 external host已建立新 canonical plan：

old checkpoint plan只保留歷史。

---

# 83. Model Context Rebuild

Context Builder依 current：

```text
goal
semantic graph
fresh observations
constraints
pending action
budget
authority
```

重新投影。

---

# 84. No Need to Restore Same Token Context

$$
\boxed{
Resume
\neq
TokenContextRestoration
}
$$

這允許不同 model / context size接手。

---

# 85. Context Digest

可保存：

```text
last_context_projection_digest
```

作 diagnostics，但不作 canonical Agent identity。

---

# 86. Temporal Continuation Decision

WAKING最後必須做：

```text
CONTINUE
BLOCK
RECONCILE
COMPLETE
FAIL
CANCEL
```

---

# 87. Continue

只有：

$$
SafeResume=1
$$

才：

```text
WAKING → ACTIVE
```

---

# 88. SafeResume Formal Definition

$$
\boxed{
\begin{aligned}
SafeResume(R,K,t)
={}&
CheckpointIntegrity(K)\\
&\land OwnershipFenceValid(R)\\
&\land AuthorityCurrent(R,t)\\
&\land BudgetCurrent(R,t)\\
&\land NoUnknownExternalEffect(R)\\
&\land RequiredWorldBasisValid(R,t)\\
&\land GoalCurrent(R,t)
\end{aligned}
}
$$

---

# 89. Resume Event

```text
agent.resumed
```

記錄：

```text
previous checkpoint
wake event
new epoch
new authority revision
new budget revision
fresh observation refs
invalidated plan refs
```

---

# 90. AgentRun Epoch

Process restart不一定每次都要新 epoch。

但任何 execution ownership continuity break可以提升 epoch。

---

# 91. Epoch Policy

建議以下至少升 epoch：

```text
reconciliation resolution
explicit crash recovery
ownership transfer
provider-state ambiguity recovery
manual forced recovery
```

普通：

```text
short WAITING
```

不必。

---

# 92. Stale Runtime Writer

舊 process帶：

$$
epoch=e
$$

current：

$$
epoch=e+1
$$

所有 state mutation拒絕。

---

# 93. Temporal Fencing

每個 long-lived operation可綁：

```text
agent_run_epoch
authority_epoch
provider_epoch
```

形成：

$$
F=(E_A,E_{Auth},E_P)
$$

---

# 94. Provider Epoch Change

如果 suspend期間 provider restart：

pending command mapping stale。

需要重新 capability / status resolution。

---

# 95. Async Provider Operation Across Epoch

如果 operation id可跨 provider epoch查詢：

可以 resolution。

否則：

```text
RECONCILIATION_REQUIRED
```

---

# 96. Crash Recovery

程序 crash後：

```text
discover non-terminal AgentRuns
```

但不能全部直接 resume。

---

# 97. Recovery Classification

至少：

```text
SAFE_SUSPENDED
SAFE_WAITING_RECOVERY
PENDING_NOT_DISPATCHED
PENDING_RECEIPT_KNOWN
UNKNOWN_AFTER_DISPATCH
CHECKPOINT_INVALID
LINEAGE_DIVERGED
TERMINAL
```

---

# 98. SAFE_SUSPENDED

等待 wake。

不主動 resume，除非 wake condition已成熟。

---

# 99. WAITING Recovery

如果原 process死掉：

WAITING 的 local dependency通常不再可信。

應：

```text
re-resolve dependency
```

可能轉：

```text
ACTIVE
BLOCKED
FAILED
```

---

# 100. Unknown After Dispatch

永遠：

```text
RECONCILIATION_REQUIRED
```

---

# 101. Orphaned Local Process

如果 AgentRun等待 local test process，但 host restart後 process不存在：

這是：

```text
DEPENDENCY_LOST
```

而不是「測試完成」。

---

# 102. Exactly-Once Wake

不宣稱所有 external event只投遞一次。

實作：

```text
at-least-once possible
+
dedup
+
idempotent wake admission
```

---

# 103. Event Ordering

兩個 source event：

```text
E1
E2
```

arrival order可能不同於 source event time。

---

# 104. Event Time vs Receive Time

保存：

```text
source_event_time
received_at
```

兩者分離。

---

# 105. Causal Order

若 provider可提供 sequence/revision：

優先用 canonical causal identity。

---

# 106. Out-of-Order Events

舊 revision event：

```text
STALE_EVENT
```

不能 rollback current world belief。

---

# 107. Future Event

若 malformed event宣稱不合理 future timestamp：

不直接改 Agent clock。

---

# 108. Clock Trust

Wall-clock來源本身可以分：

```text
host clock
provider clock
domain clock
external timestamp
```

不假設完全一致。

---

# 109. Time Skew

可記：

$$
\Delta t
=
t_{source}
-
t_{host}
$$

但不把時間偏差自動當 domain drift。

---

# 110. PHOSPHOR Temporal Drift

PHOSPHOR的：

```text
drift
temporal_debt
max_skew
```

是 domain temporal semantics。

與 distributed clock skew不同。

---

# 111. Long-Running Agent

AgentRun可以數天存在，但需要：

```text
checkpoint compaction
event retention
observation supersession
budget windows
authority expiry
```

---

# 112. Long-Lived Authority

不建議用無期限 broad authority。

可：

```text
short authority lease
+
wake-time reauthorization
```

---

# 113. Long-Lived Budget

budget也可分：

```text
lifetime ceiling
daily ceiling
per wake ceiling
per action ceiling
```

---

# 114. Per-Wake Budget

每次 resume可以重新建立：

```text
continuation budget slice
```

但不得超過 parent budget envelope。

---

# 115. Sleep Does Not Reset Budget

$$
\boxed{
Suspend
\not\Rightarrow
UsageReset
}
$$

除非 budget policy明確按 period重置。

---

# 116. Sleep Does Not Reset Authority

同理，suspend不重新授權。

---

# 117. Sleep Does Not Freeze World

這是核心：

$$
\boxed{
AgentSuspended
\not\Rightarrow
WorldSuspended
}
$$

---

# 118. World Can Change Without Agent

$$
W(t+\Delta t)
\neq
W(t)
$$

即使 Agent完全沒有 inference。

---

# 119. Therefore Re-observation Is Mandatory

這就是 Agent-Spacetime 與普通 workflow resume 最大不同之一。

---

# 120. EML Temporal Compatibility

EML 1.5 conceptual temporal state：

$$
\mathcal S_{\mathrm{temporal}}
=
\mathcal S_{\mathrm{program}}
\times
\mathcal T
\times
\mathcal D
$$

MACR Agent temporal state可視為其 Agent Runtime specialization。

---

# 121. Delayed Decision

EML conceptual delayed decision：

$$
d=
(
id,
issue,
t_{ready},
resolver,
priority
)
$$

MACR 對應：

```text
WakeCondition
PendingDecision
ResolverRef
Priority
```

但不依賴 EML-U runtime。

---

# 122. EML Current Boundary

MACR 不宣稱 EML現有 temporal runtime已提供：

```text
durable cross-process suspension
distributed wake
exactly-once resumption
host migration
```

這些是 MACR 自己現在要實作的 runtime問題。

---

# 123. Temporal Semantic Reuse

採用的是：

```text
time-aware state
delayed decisions
non-busy waiting
observable temporal transitions
```

不是直接依賴 EML scheduler。

---

# 124. PHOSPHOR Compatibility

PHOSPHOR提供：

```text
domain logical time
time class
requested/realized rate
drift
temporal debt
event jump
replay/speculative/frozen modes
```

MACR負責 Agent continuation。

---

# 125. PHOSPHOR Does Not Own Agent Wake

PHOSPHOR event可以觸發 wake，但 MACR owns AgentRun lifecycle。

---

# 126. PNCW Compatibility

Wake後 world re-observation透過：

```text
MACR × PNCW Verified Observation Bridge
```

而不是直接相信 event payload。

---

# 127. Event Payload vs World State

$$
\boxed{
\mathrm{WakeEventPayload}
\neq
\mathrm{VerifiedWorldState}
}
$$

---

# 128. Example — Wait Until Tomorrow

Goal：

```text
review repository tomorrow morning
```

Agent：

```text
checkpoint
→ wake AT_TIME
→ SUSPENDED
```

明日：

```text
WakeEvent
→ WAKING
→ authority check
→ repository re-observation
→ ACTIVE
```

---

# 129. Example — Wait for CI

```text
patch
→ push branch
→ CI pending
→ checkpoint
→ SUSPENDED
```

GitHub event：

```text
workflow completed
```

喚醒。

但：

```text
fresh GitHub observation
```

確認 exact workflow / commit / result後，才能 verification。

---

# 130. Example — Wait for Human Approval

Agent準備：

```text
release candidate
```

action：

```text
REQUIRE_APPROVAL
```

Agent：

```text
checkpoint
→ SUSPENDED
```

Human approval event：

```text
exact proposal digest approved
```

WAKING：

```text
authority still valid?
artifact unchanged?
world unchanged?
```

全部通過才執行。

---

# 131. Example — Approval but Artifact Changed

如果 suspend期間 release artifact digest變了：

舊 approval invalid。

```text
BLOCKED
```

需要新 approval。

---

# 132. Example — Provider Async Job

```text
start long simulation
→ receipt ACCEPTED
→ durable operation id
→ checkpoint
→ SUSPENDED
```

Provider completion event喚醒。

重新 query / observe simulation result。

---

# 133. Example — Lost Completion Event

timeout wake觸發：

```text
query operation id
```

若 completed：

繼續 verification。

若 unknown：

reconciliation。

---

# 134. Example — Domain Logical Time

Agent：

```text
wake when simulation local_time >= 1000
```

PHOSPHOR domain以 4x speed運作。

Agent不需要每秒 inference。

---

# 135. Example — Domain Rate Changes

外部 actor把 rate改 4x → 0.5x。

logical condition仍：

```text
local_time >= 1000
```

不變。

---

# 136. Example — Domain Restart

domain epoch改變。

舊 logical-time wake需重新檢查 lineage。

不能假裝同一 timeline。

---

# 137. Example — World Changes During Sleep

Agent checkpoint認為：

```text
branch HEAD = A
```

醒來：

```text
HEAD = D
```

old plan：

```text
STALE
```

重新規劃。

---

# 138. Example — Authority Expires During Sleep

Wake後：

```text
AUTHORITY_STALE
```

Agent可以觀察 / report，但不能 mutate。

---

# 139. Example — Budget Exhausted During Sleep

另一 child Agent使用了 shared budget。

Parent醒來發現：

```text
remaining < required
```

轉 BLOCKED。

---

# 140. Example — Duplicate Event

同一 webhook送三次：

```text
wake_event_digest same
```

只允許一個 WAKING transition。

---

# 141. Example — Conflicting Events

收到：

```text
job completed
job cancelled
```

同一 operation不同 revisions。

Runtime依 source sequence / fresh query resolution。

不能選第一個文字看起來比較合理的。

---

# 142. Temporal Failure Taxonomy

```text
INVALID_WAKE_CONDITION
WAKE_EXPIRED
WAKE_EVENT_INVALID
WAKE_DUPLICATE
WAKE_SOURCE_UNAVAILABLE
CHECKPOINT_INVALID
CHECKPOINT_DIVERGED
AUTHORITY_STALE_ON_WAKE
BUDGET_STALE_ON_WAKE
WORLD_STALE_ON_WAKE
DEPENDENCY_LOST
PROVIDER_OPERATION_UNKNOWN
DOMAIN_EPOCH_CHANGED
TEMPORAL_CONFLICT
EVENT_ORDER_CONFLICT
RESUME_FENCE_FAILURE
```

---

# 143. Recovery Decisions

對 temporal failure：

```text
RETRY_OBSERVATION
WAIT
BLOCK
RECONCILE
REPLAN
FAIL
CANCEL
HUMAN_REVIEW
```

---

# 144. No Blind Temporal Retry

例如 wake source unavailable：

可以 retry read。

但不能重送已 dispatch action。

---

# 145. Scheduler

MACR v0.7 可以實作 local scheduler。

但 scheduler只負責：

```text
when to evaluate wake
```

不負責：

```text
whether Agent has authority to act
```

---

# 146. Scheduler Is Not Agent

$$
\boxed{
Scheduler
\neq
Agent
}
$$

---

# 147. Scheduler Persistence

至少保存：

```text
wake_condition
next_evaluation
agent_run_id
checkpoint_ref
scheduler_revision
```

---

# 148. Scheduler Crash

重啟後可以重建 future wake queue。

---

# 149. Missed Wake

如果 host offline時錯過時間：

restart：

```text
now >= target
```

產生 late wake。

---

# 150. Late Wake

WakeEvent可標：

```text
lateness_ms
```

供 policy判斷是否仍有意義。

---

# 151. Expired Task

例如：

```text
buy before 10:00
```

11:00才醒。

不能照舊執行。

---

# 152. Temporal Relevance

Goal / action可以有：

```text
deadline
not_after
freshness window
```

late wake需重新判斷。

---

# 153. Recurring Agent

v0.7.0 可以先不把 recurring schedule變成同一永不結束 AgentRun。

更安全的模式：

```text
Schedule
→ create new AgentRun per occurrence
```

---

# 154. Why

避免：

```text
one AgentRun forever
```

造成 authority、budget、history、goal scope無界膨脹。

---

# 155. Persistent Steward Agent

未來確實可以有長期 Agent identity。

但 execution仍可以：

```text
Resident/Agent identity
→ AgentRun 1
→ AgentRun 2
→ AgentRun 3
```

---

# 156. Identity vs Execution Continuity

$$
\boxed{
\mathrm{PersistentAgentIdentity}
\neq
\mathrm{SingleInfiniteAgentRun}
}
$$

---

# 157. Run Rotation

未來可依：

```text
goal boundary
time window
budget window
major authority revision
checkpoint size
```

開新 AgentRun。

---

# 158. Continuation Relation

新 AgentRun可以：

```text
continues_from = old AgentRun
```

但舊 run保持 terminal。

---

# 159. Temporal Event Log

最低 event：

```text
agent.checkpoint_created
agent.checkpoint_promoted

agent.waiting

agent.suspend_requested
agent.suspended

agent.wake_condition_created
agent.wake_received
agent.wake_deduplicated
agent.wake_expired

agent.waking
agent.temporal_revalidated
agent.world_revalidated
agent.plan_invalidated
agent.resumed

agent.dependency_lost
agent.temporal_blocked
```

---

# 160. Temporal Event Privacy

Event只保存：

```text
refs
digests
timestamps
state
bounded reason
```

不保存 private response body。

---

# 161. Causal Parents

Wake event：

```text
caused_by external event
```

Resume：

```text
caused_by wake event
```

Action：

```text
caused_by resumed plan
```

形成 causal chain。

---

# 162. Checkpoint Event Is Not Checkpoint Content

event只引用：

```text
checkpoint_ref
```

不重複整個 artifact。

---

# 163. Observability

`macr agent status` 應可顯示：

```text
state
suspended since
wake condition
next wake
checkpoint
authority expiry
budget
open pending operations
```

---

# 164. Timeline View

可顯示：

```text
ACTIVE
09:10 checkpoint
09:11 SUSPENDED
12:43 event received
12:43 WAKING
12:44 observation stale
12:45 replan
12:46 ACTIVE
```

不需要顯示 CoT。

---

# 165. Manual Wake

Operator 可以：

```text
macr agent wake <run>
```

但 manual wake也只是：

```text
WakeEvent(MANUAL)
```

不能 bypass WAKING gates。

---

# 166. Force Resume

不建議提供普通：

```text
--force
```

跳過 reconciliation / authority / freshness。

若未來提供 emergency override，必須是高權限獨立 recovery contract。

---

# 167. Cancel While Suspended

可以：

```text
SUSPENDED → CANCELLED
```

前提：

```text
no unresolved unknown external effect
```

---

# 168. Cancel with Pending Async Operation

如果 remote operation仍 running：

cancellation需要決定：

```text
cancel remote job
detach
wait
reconcile
```

不能只刪 AgentRun。

---

# 169. Detached Operation

若 policy允許：

```text
AgentRun terminal
remote operation detached
```

必須有 external ownership handoff。

---

# 170. Terminal State and Wake

對：

```text
COMPLETED
FAILED
CANCELLED
```

後收到 wake：

```text
IGNORED_TERMINAL
```

不得 reopen。

---

# 171. New Work After Completion

建立：

```text
new AgentRun
```

可引用 old evidence。

---

# 172. Checkpoint Retention

不是所有 checkpoint都永久保留 full materialization。

可以：

```text
keep lineage metadata
compact semantic payload
archive old artifacts
```

---

# 173. Compaction

Compaction不能破壞：

```text
recovery
audit
evidence provenance
```

---

# 174. Semantic Compaction

多個舊 checkpoints可 archive，但 current + major boundaries保留。

---

# 175. ANLA Future Integration

Checkpoint大型歷史可由 archive system保存。

MACR只保存 refs / digests。

---

# 176. SEDB Future Integration

SEDB可保存：

```text
temporal decisions
wake history
checkpoint provenance
world evolution
```

但 scheduler state仍由 MACR own。

---

# 177. LIMEN Integration

Resident-bound Agent wake時：

```text
LIMEN identity/access envelope
```

也必須重新驗。

---

# 178. Private Memory Rehydration

checkpoint只保存：

```text
private_projection_ref
```

wake後重新 access gate。

---

# 179. No Permanent Private Read Lease

長時間 suspend不應讓舊 private memory lease永久有效。

---

# 180. MRMIC Integration

MRMIC portal / runtime presence event可以成 wake source。

例如：

```text
resource focused
provider resource changed
human entered workspace
```

---

# 181. Presence Is Ephemeral

MRMIC runtime presence不是 durable truth。

因此 wake後不能把舊 presence snapshot當 current identity evidence。

---

# 182. PNCW Integration

所有 mutable world continuation：

```text
wake
→ PNCW reobserve
```

是 canonical path。

---

# 183. PHOSPHOR Integration

Domain logical-time / lifecycle / provider events：

作 temporal trigger source。

---

# 184. GCM Integration

未來 GCM可以決定：

```text
wake後用多少 compute
哪個 model
哪個 route
```

但不決定 wake authority。

---

# 185. Minimal v0.7.0 Implementation

至少實作：

```text
CheckpointStore
CheckpointValidator
CheckpointPromoter

WakeCondition
WakeEvent
WakeDeduplicator

LocalTemporalScheduler

SuspendService
WakeService
ResumeService

OwnershipFence
TemporalRevalidator
```

---

# 186. First Supported Wake Types

建議 v0.7.0：

```text
AT_TIME
AFTER_DURATION
MANUAL_WAKE
DEPENDENCY_COMPLETED
PROVIDER_COMPLETED
```

接著再加入：

```text
EXTERNAL_EVENT
WORLD_CONDITION
DOMAIN_LOGICAL_TIME
HUMAN_RESPONSE
```

---

# 187. Why This Order

前五種最容易在 single-machine reference runtime 建立 deterministic tests。

後四種需要更完整 external bridge。

---

# 188. Initial Physical Storage

可新增：

```text
runtime/agent.sqlite3
```

表：

```text
agent_checkpoints
agent_checkpoint_heads
agent_wake_conditions
agent_wake_events
agent_temporal_leases
agent_pending_dependencies
```

---

# 189. Scheduler Storage

可同 DB，也可獨立。

但 schema responsibility應分。

---

# 190. Single-Machine Boundary

v0.7.0 第一版只宣稱：

```text
single-machine durable continuation
```

不宣稱：

```text
distributed scheduler
multi-machine exactly-once wake
global leader election
cross-datacenter Agent migration
```

---

# 191. Cross-Process Support

同一 machine 可允許：

```text
scheduler process
agent worker process
provider process
```

但需 SQLite transaction + fencing。

---

# 192. Process Crash Test

測：

```text
checkpoint
suspend
kill process
restart
wake
resume
```

---

# 193. Machine Restart Test

測：

```text
system shutdown
restart
rebuild wake queue
late wake
rehydrate
```

---

# 194. Authority Expiry Test

```text
suspend
authority expires
wake
```

必須 BLOCKED。

---

# 195. World Stale Test

```text
checkpoint world rev A
sleep
external mutation rev B
wake
```

必須 invalidate plan。

---

# 196. Duplicate Wake Test

同 event $n$ 次：

只能一個 resume ownership。

---

# 197. Event Reorder Test

new event先、old event後：

current state不得 rollback。

---

# 198. Unknown Action Test

```text
dispatch
crash
restart
wake
```

必須 reconciliation。

---

# 199. Provider Completion Test

```text
async job
suspend
provider complete
wake
verify
```

---

# 200. Lost Provider Event Test

```text
async job completes
event dropped
timeout wake
status query
```

仍可 closure。

---

# 201. Domain Logical Time Test

```text
suspend until local_time >= 100
```

不同 temporal rate下均正確。

---

# 202. Domain Epoch Test

logical wake等待中 domain restart。

必須重新 resolve，不 blind trigger。

---

# 203. Model Swap Test

```text
Grok before suspend
Qwythos after wake
```

AgentRun semantic continuity仍成立。

---

# 204. Context Window Change Test

resume使用更小 model context。

Context Builder只能裁剪 projection，不改 canonical graph。

---

# 205. Required Negative Controls

```text
NC-TEMP-01 suspend without durable checkpoint
NC-TEMP-02 suspend with unknown external effect
NC-TEMP-03 wake directly transitions SUSPENDED→ACTIVE
NC-TEMP-04 wake bypasses authority revalidation
NC-TEMP-05 wake bypasses budget revalidation
NC-TEMP-06 wake bypasses world freshness
NC-TEMP-07 checkpoint restores expired authority
NC-TEMP-08 checkpoint restores older budget
NC-TEMP-09 checkpoint stores secret plaintext
NC-TEMP-10 divergent checkpoints last-write-win
NC-TEMP-11 duplicate wake creates two owners
NC-TEMP-12 terminal AgentRun wakes
NC-TEMP-13 old provider epoch reused
NC-TEMP-14 event payload treated verified world state
NC-TEMP-15 wall-clock confused with domain logical time
NC-TEMP-16 domain rate interpreted as CPU rate
NC-TEMP-17 provider completion treated outcome verification
NC-TEMP-18 lost provider event causes duplicate actuation
NC-TEMP-19 stale plan executes after wake
NC-TEMP-20 cancelled goal resumes
NC-TEMP-21 child completion auto-completes parent
NC-TEMP-22 human generic reply treated approval
NC-TEMP-23 late wake executes expired action
NC-TEMP-24 sleep resets budget usage
NC-TEMP-25 sleep refreshes authority automatically
NC-TEMP-26 replay/speculative time treated live time
NC-TEMP-27 old event revision rolls current state backward
NC-TEMP-28 process memory treated checkpoint authority
NC-TEMP-29 same model session required for resume
NC-TEMP-30 scheduler treated mutation authority
```

---

# 206. Acceptance Matrix

## Checkpoint

- immutable；
- digest verified；
- append-only lineage；
- atomic promotion；
- no secret payload；
- divergent heads rejected。

## Suspend

- durable checkpoint required；
- no open unknown effect；
- active ownership released。

## Wake

- typed condition；
- durable event；
- duplicate safe；
- terminal-safe。

## WAKING

- authority revalidated；
- budget revalidated；
- pending action audited；
- observations refreshed；
- plan revalidated。

## Resume

- fencing；
- no replay semantics；
- same AgentRun identity；
- model independence。

## Temporal

- wall-clock / logical-time separation；
- provider/domain epoch；
- late wake handling；
- expiry handling。

## Async

- durable operation ID；
- event loss recovery；
- no duplicate actuation。

## Crash

- process restart；
- machine restart；
- unknown dispatch reconciliation。

---

# 207. Formal Suspend Safety

$$
\boxed{
SafeSuspend(R)
=
CheckpointDurable(R)
\land
OpenReconciliation(R)=0
\land
WakeConditionValid(R)
\land
OwnershipReleasePossible(R)
}
$$

---

# 208. Formal Wake Validity

$$
ValidWake(e,R)
=
RunNonTerminal(R)
\land
ConditionMatches(e,R)
\land
EventIntegrity(e)
\land
NotDuplicate(e)
$$

---

# 209. Formal Resume Safety

$$
\boxed{
\begin{aligned}
SafeResume(R,t)
={}&
ValidCheckpoint(R)\\
&\land ValidOwnershipFence(R)\\
&\land CurrentAuthority(R,t)\\
&\land CurrentBudget(R,t)\\
&\land NoUnknownExternalEffect(R)\\
&\land FreshRequiredWorldBasis(R,t)\\
&\land CurrentGoal(R,t)
\end{aligned}
}
$$

---

# 210. Formal Temporal Continuation

Agent state transition：

$$
R_t
\xrightarrow{Suspend}
K_t
$$

世界繼續演化：

$$
W_t
\rightarrow
W_{t+\Delta}
$$

收到 wake：

$$
e_{t+\Delta}
$$

重新觀察：

$$
O_{t+\Delta}
=
\Pi(W_{t+\Delta})
$$

然後：

$$
R_{t+\Delta}
=
Resume(
K_t,
O_{t+\Delta},
Auth_{current},
Budget_{current}
)
$$

因此：

$$
\boxed{
R_{t+\Delta}
\neq
Replay(K_t)
}
$$

---

# 211. Agent-Spacetime Principle

真正的 Agent autonomy 不是：

$$
while\ true:
\ model()
$$

而是：

$$
\boxed{
Observe
\rightarrow
Act
\rightarrow
Persist
\rightarrow
Wait
\rightarrow
Wake
\rightarrow
Reobserve
}
$$

---

# 212. Canonical Closure

本文件固定：

1. AgentRun 可以跨非計算時間持續存在。
2. Agent persistence 不依賴 continuous inference。
3. Checkpoint 是 durable continuation artifact，不是 memory dump。
4. Checkpoint 不保存 hidden CoT 或 secret plaintext。
5. Checkpoint 不可回復舊 authority / budget。
6. Checkpoint 採 append-only lineage。
7. divergent checkpoint heads fail closed。
8. Suspend 需要 durable checkpoint。
9. Unknown-after-dispatch 狀態不得包裝成普通 SUSPENDED。
10. WAITING 與 SUSPENDED 分離。
11. WakeCondition 必須 declarative。
12. Wake 只進入 WAKING，不直接 ACTIVE。
13. Wake 不等於 authorization。
14. Resume 必須 rehydrate + revalidate + reobserve。
15. Wall-clock time 與 domain logical time分離。
16. Agent time 與 provider compute time分離。
17. Domain temporal rate 與 CPU service rate分離。
18. Provider completion event不等於 outcome verification。
19. Event payload不等於 verified world state。
20. Duplicate wake不得產生平行 resume。
21. Provider/domain epoch改變必須使舊 temporal binding重新驗證。
22. Agent suspend不會凍結外部 World。
23. Mutable world basis在 wake後必須 freshness check。
24. stale plan不得 blind execute。
25. Authority在 suspend期間可能撤銷或到期。
26. Budget在 suspend期間可能改變。
27. Goal在 suspend期間可能 revision / cancel。
28. long-running provider operation必須有 durable correlation identity。
29. lost completion event不得造成 duplicate actuation。
30. terminal AgentRun不得被 wake reopen。
31. recurring activity不必使用單一無限 AgentRun。
32. persistent Agent identity與 individual AgentRun分離。
33. v0.7.0 第一版只需證明 single-machine durable continuation。
34. EML temporal semantics作 conceptual foundation，不成為 runtime dependency。
35. PHOSPHOR提供 Software Spacetime time/domain semantics，但 MACR擁有 AgentRun continuation。
36. PNCW負責 wake後 mutable world re-observation。
37. Scheduler負責「何時重新評估」，不擁有 mutation authority。

因此：

$$
\boxed{
\mathrm{Agent}\in\mathrm{Time}
}
$$

在 MACR v0.7 中不再只是哲學描述，而成為 executable contract：

$$
\boxed{
Checkpoint
+
Suspend
+
Wake
+
Revalidation
+
ReObservation
+
Resume
}
$$

這構成 MACR Agent-Spacetime Runtime 的第六個 canonical engineering core。

---

# Appendix A — Canonical Contracts

```text
macr-agent-checkpoint/v1
macr-agent-suspend/v1
macr-agent-wake-condition/v1
macr-agent-wake-event/v1
macr-agent-temporal-lease/v1
macr-agent-pending-dependency/v1
macr-agent-resume-record/v1
macr-spacetime-trigger/v1
```

---

# Appendix B — Core Wake Kinds

```text
AT_TIME
AFTER_DURATION
EXTERNAL_EVENT
DOMAIN_LOGICAL_TIME
WORLD_CONDITION
HUMAN_RESPONSE
DEPENDENCY_COMPLETED
PROVIDER_COMPLETED
BUDGET_AVAILABLE
MANUAL_WAKE
```

---

# Appendix C — Canonical Temporal Flow

```text
ACTIVE
↓
Checkpoint
↓
Suspend Admission
↓
SUSPENDED
↓
Time / Event / Human / Provider / World
↓
WakeEvent
↓
WAKING
↓
Checkpoint Integrity
↓
Ownership Fence
↓
Authority Revalidation
↓
Budget Revalidation
↓
Pending-Action Audit
↓
PNCW World ReObservation
↓
Plan Revalidation
↓
ACTIVE / BLOCKED / RECONCILIATION_REQUIRED / CANCELLED
```

---

# Appendix D — First v0.7.0 Temporal MVP

Minimum demonstration:

```text
1. Create AgentRun
2. Observe repository/domain
3. Perform one bounded verified task
4. Create checkpoint
5. Suspend for AFTER_DURATION
6. Kill runtime process
7. Restart runtime
8. Rebuild wake schedule
9. Receive late/on-time wake
10. Enter WAKING
11. Revalidate authority/budget
12. Reobserve mutable world
13. Rebuild context
14. Resume with same AgentRun
15. Complete task
```

第二個 acceptance scenario：

```text
1. Dispatch asynchronous bounded provider action
2. Save durable operation reference
3. Suspend
4. Receive provider completion event
5. Wake
6. Query/reobserve actual state
7. Verify
8. Complete without duplicate dispatch
```

第三個 negative scenario：

```text
1. Dispatch action
2. Crash before receipt persistence
3. Restart
4. Detect unknown-after-dispatch
5. Enter RECONCILIATION_REQUIRED
6. Do not automatically retry
```

---

# Appendix E — Next Canonical Specification

下一份：

**MACR v0.7 — Single-Agent MVP Implementation Plan & Verification Matrix v0.1**

將把目前已完成的六份 canonical specification：

```text
01 AgentRun State
02 Agent Semantic Envelope
03 Action / Authority / Effect
04 PNCW Verified Observation Bridge
05 PHOSPHOR Governed Actuation Bridge
06 Checkpoint / Suspend / Wake
```

正式壓縮成：

```text
Phase A — Contracts
Phase B — AgentRun Kernel
Phase C — Semantic State
Phase D — Observation
Phase E — Action Gate
Phase F — Temporal Continuation
Phase G — Closed-Loop Agent
Phase H — Failure Injection / Verification
```

並固定第一個真正可執行的 MACR v0.7.0 Single-Agent MVP。