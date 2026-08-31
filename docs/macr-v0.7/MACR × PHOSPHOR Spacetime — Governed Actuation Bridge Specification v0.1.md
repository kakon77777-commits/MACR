# MACR × PHOSPHOR Spacetime — Governed Actuation Bridge Specification v0.1

## MACR Agent 與 PHOSPHOR Software Spacetime 受治理致動橋接規格 v0.1

**Document ID:** `MACR-PHOSPHOR-GAB-2026-v0.1`  
**Parent Architecture:** `MACR-ASR-CCA-2026-v0.1`  
**Parent State Spec:** `MACR-V07-AGENTRUN-STATE-2026-v0.1`  
**Parent Semantic Spec:** `MACR-V07-ASE-2026-v0.1`  
**Parent Action Spec:** `MACR-V07-AAEC-2026-v0.1`  
**Observation Bridge:** `MACR-PNCW-VOBS-BRIDGE-2026-v0.1`  
**Projects:** MACR / PHOSPHOR Spacetime  
**Target:** MACR v0.7.x / PHOSPHOR integration line  
**Date:** 2026-08-30  
**Status:** Canonical Integration Contract / Pre-Implementation  
**Organization:** EveMissLab / 一言諾科技有限公司  
**Language:** Traditional Chinese

---

# 摘要

MACR v0.7 讓 Agent 能夠持續觀察、規劃並提出行動。

但：

$$
\boxed{
\mathrm{AgentWants}
\neq
\mathrm{WorldChanges}
}
$$

MACR 的 Action / Authority / Effect Contract 已將：

$$
\mathrm{ActionProposal}
\neq
\mathrm{AuthorizedAction}
\neq
\mathrm{CommandIntent}
\neq
\mathrm{Actuation}
$$

分離。

PHOSPHOR Spacetime 則已建立一套 Software Spacetime reference runtime，其核心流程為：

```text
Observation
↓
Software Spacetime IR
↓
Governance
↓
Policy Proposal
↓
Deterministic Validation
↓
Command Intent
↓
Authority Gate
↓
Provider ABI
↓
Measured Reality
```

本 Bridge 的目的，是在不破壞 MACR 與 PHOSPHOR 各自 authority ownership 的前提下，把：

```text
MACR ActionProposal
↓
MACR Admission
↓
MACR CommandIntent
```

銜接至：

```text
PHOSPHOR Governance
↓
PHOSPHOR CommandIntent
↓
Provider
↓
Actuation Receipt
```

再由：

```text
PNCW ReObservation
↓
MACR Outcome Verification
```

完成整個 Agent action closed loop。

因此最終：

$$
\boxed{
\begin{aligned}
AgentIntent
&\rightarrow ActionProposal\\
&\rightarrow Admission\\
&\rightarrow CommandIntent\\
&\rightarrow Actuation\\
&\rightarrow Receipt\\
&\rightarrow ReObservation\\
&\rightarrow Verification
\end{aligned}
}
$$

PHOSPHOR 不成為 MACR 的 authority root。

MACR 也不把 PHOSPHOR 降格成單純 shell executor。

本文件將兩者定位為：

> **MACR 管理 Agent 行動語意、AgentRun、delegated authority 與跨 provider orchestration；PHOSPHOR 管理 Software Spacetime 中 command、temporal/causal governance、provider capability、actuation 與 measured reality。**

---

# 0. Canonical Decision

MACR × PHOSPHOR Bridge 的正式關係：

$$
\boxed{
MACR.ActionProposal
\rightarrow
MACR.Admission
\rightarrow
Bridge
\rightarrow
PHOSPHOR.CommandIntent
\rightarrow
ProviderABI
}
$$

而不是：

$$
\boxed{
Agent
\rightarrow
ProviderAPI
}
$$

---

# 1. Responsibility Boundary

## MACR 擁有

```text
AgentRun
Goal
Plan
ActionProposal
EffectSet
Capability Resolution
Delegated Authority
Budget
Admission Decision
Reconciliation
Agent completion
```

## PHOSPHOR 擁有

```text
Software Spacetime IR
domain lifecycle
temporal state
causal/governance state
CommandIntent contract
provider capability descriptions
provider epoch/health
actuation
measured reality
actuation receipt
```

---

# 2. PHOSPHOR Is Not the Agent

$$
\boxed{
\mathrm{PHOSPHOR}
\neq
\mathrm{AgentPlanner}
}
$$

PHOSPHOR 可以有 rule governor / AI adapter，但在 MACR integration 中不應偷偷建立第二套 autonomous goal authority。

---

# 3. MACR Is Not the Provider

$$
\boxed{
\mathrm{MACR}
\neq
\mathrm{NativeProvider}
}
$$

MACR 不應直接假裝理解：

- Linux cgroup；
- Windows Job Object；
- Unity runtime；
- WASM runtime；
- HDUS；
- PHOSPHOR VM；

所有 native semantics。

這些屬 Provider / PHOSPHOR adapter。

---

# 4. Current PHOSPHOR Engineering Boundary

現行 `ssm-control-v0.1` 已定義：

```text
DRAFT
VALIDATED
AUTHORIZED
DISPATCHED
EXECUTED
REJECTED
FAILED
EXPIRED
CANCELLED
```

作為 CommandIntent state。

目前 action vocabulary 包含：

```text
domain.inspect
domain.pause
domain.resume
domain.set_temporal_rate
domain.set_resource_budget
domain.set_observation_profile
domain.snapshot
domain.restore
```

因此本 Bridge v0.1 不宣稱：

```text
GitHub write
Gmail send
generic filesystem mutation
arbitrary browser action
```

已經是現行 PHOSPHOR executable actions。

---

# 5. Bridge Strategy

因此採：

```text
NATIVE_MAPPING
EXTENSION_MAPPING
MACR_DIRECT_PROVIDER
UNSUPPORTED
```

四種 route。

---

# 6. NATIVE_MAPPING

若 MACR operation 已對應 PHOSPHOR current action：

例如：

```text
software_domain.pause
```

可編譯：

```text
domain.pause
```

---

# 7. EXTENSION_MAPPING

若語義適合 PHOSPHOR，但 current schema 尚未包含：

```text
future provider action
future domain actuation
```

應標：

```text
EXTENSION_REQUIRED
```

不能偷偷塞進 `arguments` 偽裝成現有 action。

---

# 8. MACR_DIRECT_PROVIDER

某些 provider 在 v0.7 初期可仍由 MACR 現有 adapter 執行。

例如：

```text
GitHub
Google API
local provider
```

此時 PHOSPHOR semantics 可以作為 architectural reference，而非 mandatory runtime hop。

---

# 9. UNSUPPORTED

無安全 mapping 時：

```text
UNSUPPORTED_ACTUATION_ROUTE
```

fail closed。

---

# 10. No Fake Integration

禁止：

```text
operation = github.merge
```

卻映射：

```text
PHOSPHOR action = domain.inspect
arguments.realAction = github.merge
```

這會破壞 schema / authority semantics。

---

# 11. Bridge Contract

建議新增：

```json
{
  "schema": "macr-phosphor-actuation-bridge/v1",
  "bridge_id": "bridge:...",
  "macr_command_ref": "cmd:...",
  "route_kind": "NATIVE_MAPPING",
  "phosphor_command_ref": "ssm-command:...",
  "mapping_profile": "macr-phosphor-v1",
  "mapping_digest": "sha256:..."
}
```

---

# 12. Desired / Requested / Realized / Observed

這是 Bridge 最重要的不變量之一。

定義：

$$
D=\mathrm{Desired}
$$

$$
Q=\mathrm{Requested}
$$

$$
R=\mathrm{Realized}
$$

$$
O=\mathrm{Observed}
$$

必須：

$$
\boxed{
D
\neq
Q
\neq
R
\neq
O
}
$$

---

# 13. Desired

Agent semantic goal：

```text
讓 domain 以 0.5x logical temporal rate 運作
```

屬 Desired。

---

# 14. Requested

真正送出的 CommandIntent：

```text
domain.set_temporal_rate(rate=0.5)
```

屬 Requested。

---

# 15. Realized

Provider 實際回報：

```text
realized_rate = 0.47
```

屬 Realized。

---

# 16. Observed

後續重新觀察：

```text
observed effective rate = 0.46
```

屬 Observed。

---

# 17. Why Separation Matters

若：

$$
D=0.5
$$

$$
Q=0.5
$$

$$
R=0.47
$$

$$
O=0.46
$$

不能簡化為：

```text
success=true
```

---

# 18. Actuation Skew

定義：

$$
Skew_{DR}=distance(D,R)
$$

$$
Skew_{RO}=distance(R,O)
$$

以及：

$$
Skew_{DO}=distance(D,O)
$$

可作 verification evidence。

---

# 19. CommandIntent Mapping

MACR CommandIntent：

$$
C_M
$$

編譯：

$$
\Phi_{MP}(C_M)
=
C_P
$$

其中 $C_P$ 為 PHOSPHOR CommandIntent。

---

# 20. Mapping Must Preserve

至少：

```text
actor
target
operation
arguments
required capabilities
authority reference
evidence references
idempotency
expiry
```

---

# 21. Mapping Must Not Add Authority

$$
\boxed{
Authority(\Phi(C))
\subseteq
Authority(C)
}
$$

不能在轉譯中擴大。

---

# 22. Mapping Must Not Add Effects

若 MACR effective effects：

$$
E_M
$$

而 PHOSPHOR command / provider 導出的：

$$
E_P
$$

必須：

$$
E_P
\subseteq
E_M
$$

---

# 23. Mapping Fidelity

Bridge outcome：

```text
EXACT
BOUNDED
UNSUPPORTED
```

---

# 24. EXACT

語義可無損映射。

---

# 25. BOUNDED

只有已知 bounded subset 等價。

必須記錄限制。

---

# 26. UNSUPPORTED

無合法 mapping。

不得 approximation execute。

---

# 27. Actor

PHOSPHOR current actor type：

```text
human
ai
governor
system
```

MACR AgentRun 一般映射：

```text
actor_type = ai
```

但 `actor_id` 應指 runtime agent identity / execution principal，而不是 foundation model name。

---

# 28. Model Is Not Actor

例如：

```text
model = grok-4.6
```

不能自動成為：

```text
actor_id = grok-4.6
```

因為：

$$
\boxed{
\mathrm{Model}
\neq
\mathrm{AgentActor}
}
$$

---

# 29. Target Domain

PHOSPHOR command 必須 target：

```text
target_domain_id
```

MACR WorldBinding 必須能 map 至 software-spacetime domain。

---

# 30. Domain Binding

建議：

```json
{
  "schema": "macr-phosphor-domain-binding/v1",
  "world_binding_ref": "world:...",
  "phosphor_domain_id": "domain:...",
  "provider_ref": "provider:...",
  "binding_revision": 1,
  "digest": "sha256:..."
}
```

---

# 31. Missing Domain Binding

若 MACR action target 無 PHOSPHOR domain：

```text
NO_DOMAIN_BINDING
```

不得猜。

---

# 32. Software Spacetime IR

PHOSPHOR `ssm-ir-v0.1` 將 world 分為 domains。

每個 domain 包含：

```text
domain_id
parent_domain_id
kind
lifecycle
temporal
resources
observation
causality
governance
capabilities
evidence
```

Bridge 應把這視為 domain-state evidence，而不是 Agent semantic state本身。

---

# 33. Domain Lifecycle

現行 domain lifecycle：

```text
DISCOVERED
REGISTERED
ATTACHED
ACTIVE
PAUSED
FROZEN
DEGRADED
DETACHED
FAILED
```

---

# 34. Domain Lifecycle Is Not AgentRun Lifecycle

$$
\boxed{
\mathrm{DomainState}
\neq
\mathrm{AgentRunState}
}
$$

AgentRun 可以 ACTIVE，而 target domain PAUSED。

---

# 35. Temporal State

PHOSPHOR domain temporal fields包括：

```text
time_class
reference_clock
local_time
requested_rate
realized_rate
drift
temporal_debt
max_skew
event_jump_allowed
approximation_allowed
```

這對 Agent-Spacetime 特別重要。

---

# 36. Time Class

現行：

```text
ANCHORED
ELASTIC
EVENT_JUMP
REPLAY
SPECULATIVE
FROZEN
UNKNOWN
```

---

# 37. Time != Compute

Bridge 必須保留：

$$
\boxed{
\mathrm{LogicalTime}
\neq
\mathrm{CPUServiceRate}
}
$$

不能把提高 CPU budget 當成 logical time 加速。

---

# 38. Agent Time vs Domain Time

Agent wall-clock：

$$
T_A
$$

domain logical time：

$$
T_D
$$

必須分離。

---

# 39. Scheduled Agent Action

例如：

> domain logical time 到 100 時執行。

與：

> 現實時間 21:00 執行。

不是同一 trigger。

---

# 40. Temporal Trigger Schema

建議：

```json
{
  "schema": "macr-spacetime-trigger/v1",
  "clock_kind": "DOMAIN_LOGICAL",
  "domain_ref": "domain:...",
  "condition": {
    "local_time_gte": 100
  }
}
```

---

# 41. Wall-Clock Trigger

```text
clock_kind = WALL_CLOCK
```

---

# 42. Event Trigger

```text
clock_kind = EVENT
```

實際上不是 clock，而是 causal wake。

---

# 43. Suspend

Agent 等待 domain 事件時：

```text
AgentRun → SUSPENDED
```

而不是：

```text
while not condition:
    call model
```

---

# 44. Wake

PHOSPHOR event / domain change可以觸發 MACR wake candidate。

但：

$$
\boxed{
\mathrm{DomainEvent}
\neq
\mathrm{AgentAuthorization}
}
$$

---

# 45. Wake Pipeline

```text
PHOSPHOR Event
↓
MACR Wake Event
↓
AgentRun WAKING
↓
Authority revalidation
↓
PNCW ReObservation
↓
Plan revalidation
↓
ACTIVE
```

---

# 46. Causality

Software-spacetime actions 不應只保存 timestamp。

需要：

```text
cause
predecessor
command
provider receipt
subsequent observation
```

---

# 47. Causal Chain

建議：

```text
ActionProposal
↓
Admission
↓
CommandIntent
↓
ProviderAttempt
↓
Receipt
↓
ObservedState
↓
Verification
```

建立 causal refs。

---

# 48. Temporal Order != Causal Order

$$
\boxed{
t(A)<t(B)
\not\Rightarrow
A\rightarrow B
}
$$

兩件事情時間相鄰不證明因果。

---

# 49. CommandIntent State Machine

PHOSPHOR current states：

```text
DRAFT
↓
VALIDATED
↓
AUTHORIZED
↓
DISPATCHED
↓
EXECUTED
```

failure / terminal：

```text
REJECTED
FAILED
EXPIRED
CANCELLED
```

---

# 50. MACR Admission vs PHOSPHOR VALIDATED

MACR：

```text
Action admitted
```

不等於：

```text
PHOSPHOR VALIDATED
```

Bridge compile 後仍需 PHOSPHOR schema/domain validation。

---

# 51. MACR Authorized vs PHOSPHOR AUTHORIZED

MACR authority 是 Agent delegated authority。

PHOSPHOR authority gate可能再檢查：

```text
domain capability
provider privilege
runtime policy
provider epoch
host constraints
```

因此：

$$
\boxed{
MACR\_AUTHORIZED
\not\Rightarrow
PHOSPHOR\_AUTHORIZED
}
$$

---

# 52. Double-Gate Is Intentional

合法 execution：

$$
A_M
\land
A_P
$$

其中：

- $A_M$：MACR Agent authority；
- $A_P$：PHOSPHOR/domain/provider authority。

---

# 53. No Authority Collapse

不能只做其中一個：

```text
MACR says yes, bypass PHOSPHOR
```

也不能：

```text
PHOSPHOR says provider supports, bypass MACR
```

---

# 54. Capability

PHOSPHOR provider contract對 capability 描述：

```text
name
support
bounds
precision
latency_class
privilege
reversibility
side_effect_class
projection_semantics
```

---

# 55. Support

```text
SUPPORTED
PARTIAL
UNSUPPORTED
```

---

# 56. PARTIAL

PARTIAL 不等於可以直接呼叫。

Bridge 必須確認 action 在 bounds 內。

---

# 57. Capability Bounds

例如：

```text
temporal rate ∈ [0.1, 4.0]
```

Agent request：

```text
10.0
```

即使 capability name 存在仍：

```text
OUT_OF_BOUNDS
```

---

# 58. Privilege

PHOSPHOR provider privilege：

```text
USER
ELEVATED
ADMIN
RUNTIME_INSTRUMENTED
KERNEL
HARDWARE_PRIVILEGED
```

---

# 59. Privilege != Authority

Provider 說某 capability requires ADMIN：

不是在授權 Agent ADMIN。

只是說：

> 執行此 capability 所需 provider privilege 等級。

---

# 60. Reversibility

現行：

```text
READ_ONLY
LOCAL_REVERSIBLE
LOCAL_COMPENSATABLE
EXTERNAL_REVERSIBLE
EXTERNAL_COMPENSATABLE
EXTERNAL_IRREVERSIBLE
```

這可直接餵回 MACR Risk / Rollback Policy。

---

# 61. Reversibility Mapping

MACR Action Gate 應將 PHOSPHOR reversibility納入：

$$
Risk(a)
$$

而非只由 Agent 自行宣告。

---

# 62. Provider Description Is Evidence

Provider capability 可修正 MACR declared effect/risk。

例如 Agent 宣稱：

```text
reversible
```

但 provider contract：

```text
EXTERNAL_IRREVERSIBLE
```

則以更保守語義處理。

---

# 63. Side Effect Class

Provider contract 的：

```text
side_effect_class
```

應 map 到 MACR effect registry。

不能丟失。

---

# 64. Projection Semantics

Provider capability 可標：

```text
EXACT
APPROXIMATE
HEURISTIC
UNSUPPORTED
```

這對 control outcome 很重要。

---

# 65. Approximate Actuation

例如：

```text
requested temporal rate = 0.5
```

provider 只保證 approximate。

則 expected outcome 不應要求：

$$
realized=0.5
$$

exact equality。

---

# 66. Tolerance

Action verification policy可以指定：

$$
|realized-requested|
\le
\varepsilon
$$

---

# 67. Provider Health

Provider state：

```text
HEALTHY
DEGRADED
STALE
FAILED
DETACHED
```

---

# 68. Provider Health Gate

預設：

```text
FAILED
DETACHED
```

禁止 dispatch。

---

# 69. DEGRADED

可以依 action risk：

```text
ALLOW
DEFER
REQUIRE_APPROVAL
```

---

# 70. STALE Provider

必須重新 resolve capability / epoch。

---

# 71. Provider Epoch

Provider contract 有：

```text
instance_id
epoch
```

Receipt 也保存 provider epoch。

這與 MACR fencing 概念可直接對齊。

---

# 72. Provider Restart

如果：

```text
provider epoch 4
→ provider restart
→ epoch 5
```

舊 pending command不能 blind dispatch。

---

# 73. Command Provider Binding

Command 應綁：

```text
provider_id
instance_id
provider_epoch
capability_snapshot_digest
```

---

# 74. Stale Provider Binding

dispatch-time 不一致：

```text
PROVIDER_EPOCH_STALE
```

需要 re-admission / recompile。

---

# 75. Provider Selection

如果 GCM / planner 選 provider：

$$
Select(P)
$$

仍需：

```text
provider capability check
provider health
provider epoch
MACR authority
PHOSPHOR authority
```

---

# 76. No Automatic Provider Substitution

Provider A fail：

不得直接改 Provider B。

因為：

$$
Capabilities_A
\neq
Capabilities_B
$$

以及：

$$
Effects_A
\neq
Effects_B
$$

---

# 77. Reroute

需要：

```text
new route proposal
new capability snapshot
new admission
new CommandIntent
```

---

# 78. Provider ABI

PHOSPHOR Provider ABI 負責：

```text
CommandIntent
→ native provider operation
```

---

# 79. ABI Cannot Change Semantic Goal

如果 command：

```text
domain.pause
```

ABI 不能改成：

```text
domain.detach
```

---

# 80. ABI Native Arguments

Provider-specific argument formatting可不同。

Semantic action不能不同。

---

# 81. Dispatch Fencing

需要至少：

```text
agent_run_epoch
authority_epoch
provider_epoch
fencing token
command id
idempotency key
```

---

# 82. Fencing Composition

一個 action 必須同時通過：

$$
F_A
\land
F_{Auth}
\land
F_P
$$

其中：

- AgentRun fence；
- Authority fence；
- Provider fence。

---

# 83. Dispatch State

MACR 與 PHOSPHOR 都可以保存 state，但 source of truth 必須明確。

建議：

- MACR owns Agent action orchestration state；
- PHOSPHOR owns command/provider actuation state。

---

# 84. State Correlation

使用：

```text
MACR action_id
MACR command_id
PHOSPHOR command_id
provider attempt_id
receipt_id
```

建立 correlation。

---

# 85. Never Reuse IDs Across Layers

$$
\boxed{
ActionID
\neq
CommandID
\neq
AttemptID
\neq
ReceiptID
}
$$

---

# 86. Actuation Receipt

PHOSPHOR current receipt 已包含：

```text
receipt_id
command_id
provider
status
started_at
finished_at
before
desired
requested
realized
observed_after
actuation_skew
fence_epoch
idempotency_key
error
evidence_refs
```

這非常適合 MACR bridge。

---

# 87. Receipt Status

現行：

```text
ACCEPTED
APPLYING
CONFIRMED
PARTIAL
FAILED
ROLLED_BACK
COMPENSATED
EXPIRED
```

---

# 88. CONFIRMED

在 Bridge 中：

```text
CONFIRMED
```

仍不能直接等於 MACR：

```text
VERIFIED
```

---

# 89. Why

PHOSPHOR receipt是 actuation layer evidence。

MACR final success仍應由 PNCW / independent re-observation確認。

---

# 90. before

`before`：

> provider / PHOSPHOR 所認知的 action 前狀態。

---

# 91. desired

`desired`：

> upstream policy / Agent desired semantic outcome。

---

# 92. requested

`requested`：

> provider 被要求的 exact actuation。

---

# 93. realized

`realized`：

> provider report 真正施加的狀態。

---

# 94. observed_after

`observed_after`：

> actuation subsystem當下觀察到的結果。

---

# 95. Independent Observation Still Required

即使 receipt有：

```text
observed_after
```

仍可以要求：

```text
PNCW Verified ReObservation
```

尤其高風險操作。

---

# 96. Receipt Projection

Bridge 將 PHOSPHOR receipt映射為 ASE：

```text
receipt node
```

保存 identity / refs，不必複製所有 provider detail。

---

# 97. Receipt Is Immutable Evidence

不得因後續 verification失敗修改 receipt。

---

# 98. Failure

PHOSPHOR `FAILED` 可以分：

```text
known no effect
partial effect
unknown effect
```

Bridge 必須保留差異。

---

# 99. FAILED Does Not Imply No Effect

$$
\boxed{
ProviderFailed
\not\Rightarrow
WorldUnchanged
}
$$

---

# 100. Unknown Effect

若不能確定：

```text
UNKNOWN_AFTER_DISPATCH
```

MACR：

```text
RECONCILIATION_REQUIRED
```

---

# 101. Host Failure vs AI Failure

PHOSPHOR 已保留：

$$
\boxed{
\mathrm{AI\ Failure}
\neq
\mathrm{Host\ Failure}
}
$$

Bridge 必須延續。

---

# 102. AI Failure

例如：

```text
planner malformed proposal
model timeout before command
```

---

# 103. Host Failure

例如：

```text
provider runtime crashed
kernel control unavailable
host disconnected
```

---

# 104. Provider Failure

第三類：

```text
native operation rejected
```

也應獨立。

---

# 105. Failure Taxonomy

建議：

```text
MACR_SEMANTIC_FAILURE
MACR_AUTHORITY_FAILURE
MACR_BUDGET_FAILURE

PHOSPHOR_VALIDATION_FAILURE
PHOSPHOR_GOVERNANCE_FAILURE

PROVIDER_UNAVAILABLE
PROVIDER_STALE
PROVIDER_REJECTED
PROVIDER_PARTIAL

HOST_FAILURE

UNKNOWN_AFTER_DISPATCH
VERIFICATION_DIVERGENCE
```

---

# 106. Temporal Action

某 action 不一定立即執行。

可有：

```text
execute_at
not_before
deadline
domain_time_condition
event_condition
```

---

# 107. Scheduled Command

MACR 可以 admission：

```text
future CommandIntent
```

但 dispatch-time仍必須重新驗：

```text
authority
budget
provider epoch
world freshness
```

---

# 108. Admission Is Not Reservation Forever

$$
\boxed{
FutureAdmission
\neq
PermanentAuthorization
}
$$

---

# 109. Deadline

若：

$$
t>deadline
$$

CommandIntent：

```text
EXPIRED
```

不得執行。

---

# 110. Domain Pause

Agent action：

```text
pause simulation
```

可以 native map 到：

```text
domain.pause
```

---

# 111. Domain Resume

需確認：

```text
domain lifecycle = PAUSED/FROZEN-compatible
```

不能 blind resume FAILED domain。

---

# 112. Temporal Rate Change

需要：

```text
current temporal state
provider bounds
authority
risk
```

---

# 113. Resource Budget Change

`domain.set_resource_budget` 特別重要：

Agent 不應藉此繞過 MACR自己的 budget。

---

# 114. Two Budgets

MACR Agent budget：

$$
B_A
$$

PHOSPHOR domain resource budget：

$$
B_D
$$

必須分開。

---

# 115. Agent Budget vs Domain Budget

$$
\boxed{
B_A
\neq
B_D
}
$$

提高 domain CPU 不等於提高 Agent USD budget。

---

# 116. Budget Mutation Is an Action

若 Agent 要改 domain resource budget：

這本身是：

```text
ActionProposal
```

需要 authority。

---

# 117. Snapshot

`domain.snapshot` 可以作 reversible action前置。

---

# 118. Snapshot Does Not Make External Action Reversible

建立 snapshot：

```text
local world state
```

不代表外部：

```text
email sent
release published
```

可被回退。

---

# 119. Restore

`domain.restore` 是新的 actuation。

不是時間倒轉。

---

# 120. Restore != Erase History

$$
\boxed{
Restore(State)
\neq
Delete(Events)
}
$$

---

# 121. Compensation

若 action無 transactional rollback：

需要：

```text
CompensatingAction
```

---

# 122. Compensation Again Uses Bridge

```text
Failure
↓
Compensation Proposal
↓
MACR Admission
↓
PHOSPHOR Command
↓
Provider
↓
Receipt
↓
ReObservation
```

---

# 123. No Magical Rollback

禁止：

```text
receipt.status = ROLLED_BACK
```

但實際沒有 rollback action/evidence。

---

# 124. Causal Verification

Action verification最好檢查：

- target state changed；
- change符合 expected；
- no forbidden collateral change；
- provider receipt與world一致。

---

# 125. Independent Verification

最终：

```text
PNCW VerifiedObservationRef
```

作為外部 world basis。

---

# 126. Bridge Closed Loop

```text
ASE ActionProposal
↓
MACR Action Gate
↓
MACR CommandIntent
↓
Bridge Mapping
↓
PHOSPHOR CommandIntent
↓
PHOSPHOR Validation
↓
PHOSPHOR Authority Gate
↓
Provider ABI
↓
Provider
↓
PHOSPHOR Actuation Receipt
↓
ASE Receipt
↓
PNCW ReObservation
↓
ASE Observation
↓
MACR Verification
```

---

# 127. Measured Reality

PHOSPHOR 的重點不是：

> command 被呼叫。

而是：

> 執行後實際發生了什麼。

因此：

$$
\boxed{
Execution
\neq
MeasuredReality
}
$$

---

# 128. Measurement

可包括：

```text
realized temporal rate
CPU/memory usage
domain lifecycle
provider state
latency
drift
resource realization
```

---

# 129. Measurement Is Observation Candidate

Measured reality可以形成：

```text
evidence
```

但若要成為 MACR canonical planning basis：

最好再經 Verified Observation Bridge。

---

# 130. PHOSPHOR Evidence Levels

Software Spacetime IR evidence ref可標：

```text
observed
inferred
hypothesized
verified
unknown
```

Bridge 必須保留此 epistemic distinction。

---

# 131. Inferred != Observed

$$
\boxed{
\mathrm{Inferred}
\neq
\mathrm{Observed}
}
$$

---

# 132. Hypothesized != Verified

同理：

$$
\boxed{
\mathrm{Hypothesized}
\neq
\mathrm{Verified}
}
$$

---

# 133. ASE Mapping

PHOSPHOR evidence映射：

```text
observed → Observation/Evidence
inferred → Claim
hypothesized → Hypothesis
verified → Verification-supported Claim
unknown → Unknown state
```

不能全變 observation。

---

# 134. Governance Summary

PHOSPHOR governance可以輸出：

```text
PolicyProposal
```

但：

$$
\boxed{
PHOSPHOR.PolicyProposal
\neq
MACR.ActionAuthority
}
$$

---

# 135. AI Adapter

PHOSPHOR 中若使用 AI Adapter：

其 proposal仍不能繞回修改 MACR authority envelope。

---

# 136. Circular Authority Prohibited

禁止：

```text
MACR Agent asks PHOSPHOR AI
→ PHOSPHOR AI says allowed
→ MACR treats that as authority
```

---

# 137. Authority Root Must Remain External

Authority root應是：

```text
host operator
system policy
verified delegated authority
```

而非 model consensus。

---

# 138. Policy Proposal Loop

合法：

```text
PHOSPHOR AI proposal
↓
deterministic validation
↓
MACR/PHOSPHOR authority
↓
CommandIntent
```

---

# 139. Command Expiry

PHOSPHOR schema已支援：

```text
expires_at
```

Bridge應與 MACR action expiry一致或更嚴格。

---

# 140. Expiry Monotonic Restriction

Bridge不能延長 expiry。

$$
Expiry_P
\le
Expiry_M
$$

---

# 141. Idempotency

MACR idempotency policy映射 PHOSPHOR：

```text
idempotency_key
```

---

# 142. Idempotency Does Not Mean Safe Retry

仍：

$$
\boxed{
IdempotentClaim
\neq
ProvenExactlyOnce
}
$$

---

# 143. Provider Epoch + Idempotency

即使 idempotency key相同：

provider epoch改變後，應重新確認 provider semantics。

---

# 144. Command Cancellation

只有：

```text
NOT_DISPATCHED
```

或 provider支持 cancellable state時可合理 cancel。

---

# 145. Cancel After Effect

如果 effect已發生：

```text
cancel
```

只停止後續，不倒轉已發生狀態。

---

# 146. Long-Running Actuation

status可能：

```text
ACCEPTED
APPLYING
CONFIRMED
```

跨時間完成。

AgentRun不必一直 ACTIVE。

---

# 147. Async Actuation

可：

```text
dispatch
→ checkpoint
→ SUSPENDED
→ provider completion event
→ wake
→ reobserve
```

---

# 148. Async Does Not Lose Reconciliation

若 provider completion event丟失：

resume必須 query / observe，而不是重送 command。

---

# 149. Agent Suspend During Actuation

只有當：

```text
actuation handle durable
outcome queryable
```

或 policy明確允許，才能正常 suspend。

否則可能需要 WAITING / special pending state。

---

# 150. Pending External Operation

AgentRun checkpoint應保存：

```text
action_ref
command_ref
provider_ref
attempt_ref
expected completion
status query contract
```

---

# 151. Wake from Provider Event

provider event只是：

```text
wake candidate
```

醒來後仍：

```text
query state
reobserve
verify
```

---

# 152. Causal Parent

Provider completion event可綁：

```text
causal_parent = command_id
```

---

# 153. Domain Event

Software Spacetime domain event可成：

```text
wake source
observation trigger
verification evidence
```

---

# 154. Domain Event Cannot Grant New Goal

Event：

```text
resource high usage
```

可以喚醒 Agent。

但不能自動授予：

```text
delete workload
```

authority。

---

# 155. Event-to-Goal

可以：

```text
event
→ GoalProposal
```

但不是 Goal authority。

---

# 156. Rate Control

Temporal rate action本身可能影響未來事件密度。

Agent scheduler不能誤用 wall-clock估算 domain event時間。

---

# 157. Temporal Debt

PHOSPHOR IR有：

```text
temporal_debt
```

可作 planning evidence。

但不必成為 MACR generic budget。

---

# 158. Drift

drift超過 policy threshold：

可以觸發：

```text
reobserve
adjust
pause
human review
```

---

# 159. Max Skew

如果 domain定義：

```text
max_skew
```

verification可以直接使用。

---

# 160. Approximation Allowed

如果：

```text
approximation_allowed = false
```

而 provider只有 HEURISTIC capability：

不得 dispatch。

---

# 161. Speculative Domain

如果：

```text
time_class = SPECULATIVE
```

Observation必須標 world mode。

不能當 production current reality。

---

# 162. Replay Domain

REPLAY 亦同。

---

# 163. Frozen Domain

對 FROZEN domain：

某些 mutation可能非法。

需要 lifecycle check。

---

# 164. Degraded Domain

Agent可以觀察、診斷。

是否 mutate 由 policy。

---

# 165. Failed Domain

不能假定 resume可修復。

可能需要：

```text
restore
recreate
external intervention
```

---

# 166. Domain Hierarchy

PHOSPHOR domain可有：

```text
parent_domain_id
```

---

# 167. Parent / Child Domain Authority

父 domain authority不必自動包含 child。

需要 scope rules。

---

# 168. Cross-Domain Action

若 action同時影響多 domains：

應 explicit：

```text
multi_domain_effect
```

不能只綁一個 target_domain_id 假裝局部。

---

# 169. v0.1 Scope

current PHOSPHOR CommandIntent單 target domain。

所以 multi-domain action：

```text
UNSUPPORTED
```

或拆成受治理 sequence。

---

# 170. Decomposition

如果拆：

```text
A
→ A1(domain X)
→ A2(domain Y)
```

每一步重新 verification。

---

# 171. Cross-Domain Atomicity

不宣稱 external atomicity。

---

# 172. MACR Action Bundle

可以用 MACR bundle管理 logical plan。

PHOSPHOR仍執行 individual commands。

---

# 173. Bridge Errors

建議：

```text
INVALID_MAPPING
UNSUPPORTED_OPERATION
NO_DOMAIN_BINDING
CAPABILITY_UNSUPPORTED
CAPABILITY_OUT_OF_BOUNDS
PROVIDER_UNHEALTHY
PROVIDER_EPOCH_STALE
AUTHORITY_MISMATCH
EFFECT_WIDENING
EXPIRY_WIDENING
TEMPORAL_CONFLICT
CAUSAL_CONFLICT
COMMAND_REJECTED
UNKNOWN_AFTER_DISPATCH
```

---

# 174. Retry

`PROVIDER_UNHEALTHY`：

通常 DEFER。

`UNKNOWN_AFTER_DISPATCH`：

永不 automatic retry。

---

# 175. Bridge State Machine

```text
MACR_ADMITTED
↓
MAPPING
↓
PHOSPHOR_DRAFT
↓
PHOSPHOR_VALIDATED
↓
PHOSPHOR_AUTHORIZED
↓
DISPATCHING
↓
DISPATCHED
↓
RECEIPT_CAPTURED
↓
REOBSERVING
↓
VERIFIED
```

Failure branches：

```text
UNSUPPORTED
REJECTED
EXPIRED
FAILED_NO_EFFECT
RECONCILIATION_REQUIRED
DIVERGED
COMPENSATION_REQUIRED
```

---

# 176. MACR Direct Provider Route

若 route不是 PHOSPHOR：

```text
MACR_ADMITTED
↓
MACR provider adapter
```

仍需遵守相同 Action / Verification semantics。

因此 PHOSPHOR bridge是 canonical specialization，不是所有 v0.7 action 的硬依賴。

---

# 177. Future Convergence

當 PHOSPHOR provider ABI擴大後：

更多：

```text
filesystem
repository
browser
service
```

action可逐步遷入。

---

# 178. No Forced Migration

不因「架構漂亮」就立刻把所有成熟 MACR provider重寫成 PHOSPHOR provider。

先證明 compatibility。

---

# 179. Adoption Rule

每個 provider遷入 PHOSPHOR前需：

```text
semantic parity
effect parity
authority parity
failure parity
receipt parity
verification parity
performance acceptable
```

---

# 180. Provider Differential Test

同一 bounded action：

```text
MACR direct adapter
vs
PHOSPHOR adapter
```

比較：

```text
native request semantics
effects
receipt
observed world result
```

---

# 181. Migration Gate

只有 differential conformance通過才切 default route。

---

# 182. Backward Compatibility

MACR v0.6 provider profiles可繼續存在。

v0.7 bridge不要求一次性移除。

---

# 183. Event Mapping

MACR：

```text
action.command_compiled
```

PHOSPHOR：

```text
CommandIntent DRAFT/VALIDATED/...
```

兩者用 correlation refs連接。

---

# 184. Receipt Mapping

PHOSPHOR receipt：

```text
→ ASE receipt node
→ MACR action receipt record
```

不覆寫原始 receipt。

---

# 185. Observation Mapping

PHOSPHOR `observed_after`：

可以保留為 evidence。

PNCW fresh observation：

成為 final planning basis。

---

# 186. Verification Mapping

MACR：

```text
ActionVerification
```

可以引用：

```text
PHOSPHOR receipt
PNCW observation
PHOSPHOR measurement
provider evidence
tests
```

---

# 187. Benchmark

Bridge metrics：

```text
command_compile_latency
governance_latency
authority_gate_latency
provider_dispatch_latency
actuation_latency
receipt_latency
reobservation_latency
verification_latency
total_action_closure_latency
```

---

# 188. Semantic Accuracy Metric

最重要的不只是速度。

測：

$$
Requested
\rightarrow
Realized
\rightarrow
Observed
$$

偏差。

---

# 189. Authority Metrics

```text
unauthorized dispatch count = 0
stale authority dispatch count = 0
effect widening count = 0
```

是硬 gate。

---

# 190. Reconciliation Metrics

```text
unknown_after_dispatch count
resolution latency
blind retry count
```

其中：

```text
blind retry count
```

必須：

$$
0
$$

---

# 191. Temporal Metrics

```text
requested_rate
realized_rate
drift
temporal_debt
max_skew violations
```

---

# 192. Causal Metrics

```text
orphan receipt
missing command parent
missing after-observation
ambiguous external change
```

---

# 193. Failure Injection

至少：

```text
provider dies before dispatch
provider dies after dispatch
provider restarts epoch
authority revoked after admission
domain revision changes
capability changes
receipt persistence fails
PNCW unavailable after actuation
verification diverges
compensation fails
```

---

# 194. Required Negative Controls

```text
NC-GAB-01 MACR allow bypasses PHOSPHOR authority
NC-GAB-02 PHOSPHOR capability treated as MACR authority
NC-GAB-03 model name used as actor identity
NC-GAB-04 unsupported action hidden in arguments
NC-GAB-05 bridge widens effects
NC-GAB-06 bridge widens expiry
NC-GAB-07 PARTIAL capability treated fully supported
NC-GAB-08 out-of-bound capability dispatch
NC-GAB-09 stale provider epoch dispatch
NC-GAB-10 provider auto-substitution
NC-GAB-11 desired=requested=realized=observed collapsed
NC-GAB-12 receipt CONFIRMED treated final verification
NC-GAB-13 FAILED assumed no effect
NC-GAB-14 unknown-after-dispatch retried
NC-GAB-15 domain resource budget changes MACR Agent budget
NC-GAB-16 snapshot treated external rollback guarantee
NC-GAB-17 restore deletes historical evidence
NC-GAB-18 compensation bypasses authority
NC-GAB-19 temporal ordering treated causal proof
NC-GAB-20 provider event grants new authority
NC-GAB-21 replay domain treated live production
NC-GAB-22 speculative state treated observed truth
NC-GAB-23 domain lifecycle confused with AgentRun lifecycle
NC-GAB-24 PHOSPHOR AI policy proposal treated authority root
NC-GAB-25 current limited PHOSPHOR action enum falsely presented as generic provider support
```

---

# 195. Acceptance Matrix

## Mapping

- exact operation mapping；
- unsupported mapping fail closed；
- no hidden actions in arguments；
- stable mapping digest。

## Effects

- MACR effects preserved；
- PHOSPHOR side-effect class reconciled；
- no widening。

## Authority

- MACR authority checked；
- PHOSPHOR authority checked；
- stale revisions rejected。

## Capability

- provider support；
- bounds；
- privilege；
- reversibility；
- health；
- epoch。

## Temporal

- wall-clock/domain-time separation；
- expiry；
- scheduled dispatch revalidation；
- suspend/wake。

## Dispatch

- fencing；
- one-attempt；
- no silent provider fallback。

## Receipt

- immutable；
- desired/requested/realized/observed retained；
- provider epoch retained。

## Verification

- receipt != verification；
- fresh PNCW re-observation；
- divergence surfaced。

## Recovery

- unknown effect → reconciliation；
- provider restart handled；
- compensation governed。

---

# 196. v0.7 Integration MVP

第一版應真正完成：

```text
MACR command → PHOSPHOR domain action
```

至少選三個安全 action：

```text
domain.inspect
domain.pause
domain.resume
```

再選一個有數值 realization 的：

```text
domain.set_temporal_rate
```

---

# 197. Why These Four

它們可同時測：

- read-only；
- reversible lifecycle mutation；
- temporal semantics；
- desired/requested/realized/observed；
- provider capability；
- authority；
- PNCW re-observation。

---

# 198. MVP Scenario 1 — Inspect

```text
Agent Goal
→ inspect domain
→ MACR ALLOW
→ PHOSPHOR domain.inspect
→ receipt
→ PNCW observation
→ verify
```

無 world mutation。

---

# 199. MVP Scenario 2 — Pause

```text
observe ACTIVE
→ action pause
→ double authority gate
→ dispatch
→ receipt
→ observe PAUSED
→ verify
```

---

# 200. MVP Scenario 3 — Resume

```text
observe PAUSED
→ resume
→ receipt
→ observe ACTIVE
```

---

# 201. MVP Scenario 4 — Temporal Rate

Desired：

$$
0.5
$$

Requested：

$$
0.5
$$

Realized：

$$
r
$$

Observed：

$$
o
$$

驗：

$$
|o-0.5|\le\varepsilon
$$

---

# 202. Crash Scenario

```text
pause request dispatched
↓
process crashes
↓
receipt unavailable
```

restart：

```text
AgentRun RECONCILIATION_REQUIRED
↓
PNCW observe domain lifecycle
↓
PAUSED
↓
classify EXECUTED_AS_EXPECTED
↓
resolution receipt
↓
new epoch
```

不得再 pause 一次。

---

# 203. Provider Restart Scenario

```text
admission under provider epoch 5
↓
provider restarts → epoch 6
↓
dispatch
```

結果：

```text
PROVIDER_EPOCH_STALE
```

需要重新 capability resolution。

---

# 204. Authority Revocation Scenario

```text
MACR admission
↓
authority revoked
↓
PHOSPHOR mapping
↓
dispatch
```

dispatch-time revalidation：

```text
DENY
```

---

# 205. World Change Scenario

```text
observe ACTIVE
↓
plan pause
↓
external actor pauses first
↓
MACR attempts pause
```

pre-dispatch re-observation：

```text
already PAUSED
```

舊 action stale / redundant。

---

# 206. Redundant Action

Policy可以：

```text
mark NO_OP
```

但這也要形成 Decision。

不能假裝 action executed。

---

# 207. Idempotent Semantic No-Op

若 desired state已存在：

```text
ActionOutcome = ALREADY_SATISFIED
```

可能直接完成 verification，不 dispatch。

---

# 208. Optimization

這是未來很重要的：

$$
\boxed{
VerifiedAlreadySatisfied
\Rightarrow
NoActuationNeeded
}
$$

Agent 不應為了「做點事」而 mutate world。

---

# 209. Agent-Spacetime Principle

真正自主的 Agent 不是持續輸出 action。

它可以：

```text
observe
wait
do nothing
suspend
```

---

# 210. No-Op Is a Valid Decision

$$
\boxed{
\mathrm{Autonomy}
\neq
\mathrm{ContinuousActuation}
}
$$

---

# 211. Safe Inactivity

如果 World 已符合 Goal：

最安全行動可能：

```text
STOP
```

而不是再調整。

---

# 212. PHOSPHOR as World Control Plane

長期可讓 PHOSPHOR成為：

```text
Software Spacetime Control Plane
```

但 canonical world ownership仍分散在 native providers。

---

# 213. Provider Authority

PHOSPHOR provider不能因被掛載就取得其他 provider state ownership。

---

# 214. World Federation

未來：

```text
Linux domain
Windows domain
WASM domain
Unity domain
HDUS domain
```

都可進同一 Software Spacetime IR。

---

# 215. Agent Cross-Domain Planning

MACR Agent可在 semantic plane 規劃多 domain。

PHOSPHOR負責每 domain的 capability/temporal actuation。

---

# 216. GCM Future Integration

未來：

```text
Goal
↓
GCM
↓
compute/resource strategy
↓
MACR Action
↓
PHOSPHOR
```

但：

$$
\boxed{
GCMSelected
\neq
Authorized
}
$$

---

# 217. MRMIC Future Integration

MRMIC可以顯示 domain portals。

Agent在 visual world 中看到：

```text
domain
provider
runtime state
```

但 visual control仍需 Action Gate。

---

# 218. PNCW Future Integration

PHOSPHOR state可以成為 PNCW source。

因此：

```text
Software Spacetime IR
→ PNCW projection
→ Agent observation
```

---

# 219. SEDB Future Integration

長期可以保存：

```text
domain evolution
actuation history
verification history
causal relations
```

但 PHOSPHOR current runtime DB仍不需立刻遷移。

---

# 220. EML-U Future Integration

CommandIntent / Observation / Receipt / Causal Event都可成為 EML-U semantic/event nodes。

但不阻塞 Bridge MVP。

---

# 221. Formal Mapping Safety

令：

$$
C_M
$$

為 MACR CommandIntent。

Bridge：

$$
\Phi(C_M)=C_P
$$

安全要求：

$$
Meaning(C_P)
\subseteq
Meaning(C_M)
$$

且：

$$
Effects(C_P)
\subseteq
Effects(C_M)
$$

---

# 222. Formal Dual Authority

$$
Authorized(C)
=
Auth_{MACR}(C)
\land
Auth_{PHOSPHOR}(C)
$$

---

# 223. Formal Provider Validity

$$
ProviderValid(P,C)
=
Healthy(P)
\land
EpochCurrent(P)
\land
CapabilitySupported(P,C)
\land
BoundsValid(P,C)
$$

---

# 224. Formal Dispatch

$$
SafeDispatch(C)
=
Authorized(C)
\land
ProviderValid(P,C)
\land
FreshWorldBasis(C)
\land
BudgetValid(C)
\land
FenceValid(C)
$$

---

# 225. Formal Outcome

$$
Outcome(C)
=
(
Desired,
Requested,
Realized,
Observed
)
$$

---

# 226. Formal Success

$$
Success(C)
=
Verification(
Desired,
Observed
)
=
PASS
$$

不是：

$$
Receipt.status=CONFIRMED
$$

---

# 227. Formal Temporal Action

對 scheduled action：

$$
Dispatch_t(C)
$$

只有當：

$$
t\ge t_{notbefore}
$$

$$
t\le t_{expiry}
$$

且：

$$
SafeDispatch(C,t)=1
$$

---

# 228. Formal Unknown Outcome

若：

$$
DispatchKnown=1
$$

且：

$$
OutcomeKnown=0
$$

則：

$$
\boxed{
ReconciliationRequired
}
$$

---

# 229. Canonical Closure

本文件固定：

1. MACR Action 與 PHOSPHOR CommandIntent 分離。
2. MACR 是 Agent orchestration / delegated authority owner；PHOSPHOR 是 Software Spacetime actuation/governance runtime。
3. PHOSPHOR 不成為 Agent planner identity。
4. Foundation model 不等於 PHOSPHOR actor identity。
5. 現行 PHOSPHOR action vocabulary 仍為 bounded software-domain actions，不假裝已是 generic Agent provider runtime。
6. Bridge 必須使用 explicit native / extension / direct / unsupported routing。
7. Unsupported operation 不得藏入 generic arguments。
8. Mapping 不得擴大 effect、authority、expiry 或 target scope。
9. MACR authority 與 PHOSPHOR authority 採雙重 gate。
10. Capability、Privilege、Authority 保持分離。
11. Provider capability 的 bounds、reversibility、side-effect class、projection semantics 必須保留。
12. Provider epoch 是 actuation fencing 的一部分。
13. Provider restart 使舊 pending binding stale。
14. 不允許 silent provider substitution。
15. Desired、Requested、Realized、Observed 永不折疊。
16. Logical Time 與 Compute Rate 永不折疊。
17. Agent wall-clock 與 domain logical time 分離。
18. Scheduled action 在 dispatch-time 必須重新驗證 authority / budget / provider / world。
19. PHOSPHOR receipt 不等於 MACR final verification。
20. `observed_after` 不取代獨立 PNCW re-observation。
21. Provider failure 不等於 world unchanged。
22. Unknown-after-dispatch 必須進 reconciliation。
23. Compensation 是新的受治理 action。
24. Snapshot / Restore 不等於抹除歷史。
25. Domain resource budget 不等於 MACR Agent budget。
26. Domain lifecycle 不等於 AgentRun lifecycle。
27. Temporal ordering 不等於 causal proof。
28. Replay / Speculative domain 不得冒充 production live world。
29. PHOSPHOR AI policy proposal 不得成為 authority root。
30. MACR Direct Provider route 可在 v0.7 初期繼續存在，Bridge 不強迫一次性重寫全部 provider。
31. Provider 遷入 PHOSPHOR 前必須完成 differential semantic / effect / authority / outcome validation。
32. v0.7 第一個 Bridge MVP 應先使用 bounded native PHOSPHOR domain actions驗證閉環。

因此：

$$
\boxed{
\mathrm{GovernedActuation}
=
\mathrm{Intent}
+
\mathrm{Authority}
+
\mathrm{Capability}
+
\mathrm{TemporalState}
+
\mathrm{Provider}
+
\mathrm{Receipt}
+
\mathrm{MeasuredReality}
+
\mathrm{IndependentVerification}
}
$$

這使 MACR v0.7 所謂的「Agent 自主活動」不再只是：

```text
模型決定
→ 呼叫工具
```

而成為：

$$
\boxed{
\begin{aligned}
Agent
&\rightarrow Proposal\\
&\rightarrow Governance\\
&\rightarrow Authority\\
&\rightarrow Command\\
&\rightarrow Actuation\\
&\rightarrow Reality\\
&\rightarrow Observation\\
&\rightarrow Verification
\end{aligned}
}
$$

這構成 MACR Agent-Spacetime Runtime 的第五個 canonical engineering core。

---

# Appendix A — Existing PHOSPHOR Contracts Reused

```text
ssm-ir-v0.1
ssm-control-v0.1
ssm-provider-v0.1
ssm-actuation-receipt-v0.1
```

---

# Appendix B — New Bridge Contracts

```text
macr-phosphor-actuation-bridge/v1
macr-phosphor-domain-binding/v1
macr-spacetime-trigger/v1
macr-phosphor-provider-binding/v1
macr-phosphor-command-correlation/v1
```

---

# Appendix C — Initial Native Mapping Table

| MACR semantic operation | PHOSPHOR action | Initial status |
|---|---|---|
| `software_domain.inspect` | `domain.inspect` | NATIVE |
| `software_domain.pause` | `domain.pause` | NATIVE |
| `software_domain.resume` | `domain.resume` | NATIVE |
| `software_domain.set_temporal_rate` | `domain.set_temporal_rate` | NATIVE |
| `software_domain.set_resource_budget` | `domain.set_resource_budget` | NATIVE |
| `software_domain.set_observation_profile` | `domain.set_observation_profile` | NATIVE |
| `software_domain.snapshot` | `domain.snapshot` | NATIVE |
| `software_domain.restore` | `domain.restore` | NATIVE |
| generic repository mutation | — | MACR DIRECT / FUTURE |
| generic communication send | — | MACR DIRECT / FUTURE |
| generic browser actuation | — | FUTURE / MRMIC path |
| arbitrary provider mutation | — | UNSUPPORTED until explicit contract |

---

# Appendix D — Canonical Closed Loop

```text
MACR AgentRun
↓
ASE ActionProposal
↓
MACR Action / Authority / Effect Gate
↓
MACR CommandIntent
↓
MACR × PHOSPHOR Bridge
↓
PHOSPHOR CommandIntent
↓
PHOSPHOR Validation
↓
PHOSPHOR Authority Gate
↓
Provider ABI
↓
Native Provider
↓
PHOSPHOR Actuation Receipt
↓
ASE Receipt
↓
PNCW ReObservation
↓
ASE Observation
↓
MACR Outcome Verification
↓
AgentRun State Advance
↓
Continue / Suspend / Stop
```

---

# Appendix E — Next Canonical Specification

下一份：

**MACR v0.7 — Checkpoint / Suspend / Wake / Temporal Continuation Specification v0.1**

將正式收斂：

```text
AgentRun Checkpoint
Suspend
Wall-Clock Wake
Domain Logical-Time Wake
External Event Wake
Human Wake
Provider Completion Wake
Stale State Revalidation
Authority Revalidation
World ReObservation
Resume
```

並把：

$$
\mathrm{Agent}\in\mathrm{Time}
$$

真正從概念落到 executable runtime contract。