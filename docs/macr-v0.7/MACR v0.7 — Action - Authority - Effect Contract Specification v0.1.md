# MACR v0.7 — Action / Authority / Effect Contract Specification v0.1

## Agent 行動、權限封套、效應集合、執行准入與結果驗證契約 v0.1

**Document ID:** `MACR-V07-AAEC-2026-v0.1`  
**Parent Architecture:** `MACR-ASR-CCA-2026-v0.1`  
**Parent State Spec:** `MACR-V07-AGENTRUN-STATE-2026-v0.1`  
**Parent Semantic Spec:** `MACR-V07-ASE-2026-v0.1`  
**Project:** MACR  
**Target:** MACR v0.7.0 — Bounded Autonomous Agent Core  
**Baseline:** MACR v0.6.0a1  
**Date:** 2026-08-30  
**Status:** Canonical Action Contract / Pre-Implementation  
**Organization:** EveMissLab / 一言諾科技有限公司  
**Language:** Traditional Chinese

---

# 摘要

MACR v0.7 的 Agent 可以自主：

- 觀察；
- 推理；
- 規劃；
- 提出行動；
- 分解任務；
- 呼叫 Worker；
- 建立 checkpoint；
- suspend；
- wake；
- 重新規劃。

但「Agent 想做一件事」與「系統允許這件事發生」必須永久分離。

因此：

$$
\boxed{
\mathrm{Intent}
\neq
\mathrm{ActionProposal}
\neq
\mathrm{AuthorizedAction}
\neq
\mathrm{CommandIntent}
\neq
\mathrm{Actuation}
}
$$

MACR v0.7 將所有可能改變外部世界的行動建模為：

$$
a
=
(
subject,
target,
operation,
effects,
preconditions,
authority,
capability,
budget,
policy,
risk,
rollback,
verification
)
$$

Agent 只產生：

$$
a^{proposal}
$$

Runtime 經 deterministic / policy gates 後，才能產生：

$$
a^{admitted}
$$

再由 provider adapter 或 PHOSPHOR-compatible actuation layer 編譯成：

$$
CommandIntent
$$

最後才真正產生：

$$
Actuation
$$

本規格將 MACR v0.6 已有的 authorization revision/epoch、one-attempt provider dispatch 與 unknown-after-dispatch handling，SEDB v0.4B 的 effect-oriented autonomy、Decision/Commit separation，以及 PHOSPHOR Spacetime 的：

$$
\mathrm{PolicyProposal}
\neq
\mathrm{CommandIntent}
\neq
\mathrm{Actuation}
$$

收斂為 MACR v0.7 的正式 Action Gate。

---

# 0. Canonical Decision

MACR v0.7.0 的外部行動一律遵循：

```text
Intent
↓
ActionProposal
↓
Semantic Validation
↓
Effect Derivation
↓
Capability Resolution
↓
Authority Resolution
↓
Budget Gate
↓
Policy / Risk Gate
↓
Freshness / Preconditions
↓
Admission Decision
↓
CommandIntent
↓
Dispatch
↓
Receipt
↓
Re-observation
↓
Independent Verification
```

因此：

$$
\boxed{
\mathrm{ModelToolCall}
\neq
\mathrm{ExecutionAuthority}
}
$$

Provider-native tool call 不再是 Agent Runtime 的 canonical action abstraction。

---

# 1. ActionProposal

ActionProposal 是 Agent 對 World 提出的：

> **尚未取得執行權的 intended world transition。**

定義：

$$
A_p
=
(
id,
run,
goal,
operation,
target,
parameters,
effects,
basis,
preconditions,
expected,
rollback,
verification,
provenance
)
$$

---

# 2. ActionProposal v1

```json
{
  "schema": "macr-action-proposal/v1",
  "action_id": "action:...",
  "agent_run_id": "...",
  "agent_run_epoch": 3,
  "goal_ref": "sem:goal:...",
  "plan_ref": "sem:plan:...",
  "task_ref": "sem:task:...",

  "operation": "repository.patch",
  "target_ref": "world:github:repo:owner/name",
  "parameters_ref": "artifact:patch:...",

  "declared_effects": [
    "repository.branch.write"
  ],

  "basis_refs": [
    "sem:observation:..."
  ],

  "preconditions": [],
  "expected_result_ref": "sem:claim:...",

  "rollback_policy_ref": "rollback:...",
  "verification_policy_ref": "verification-policy:...",

  "provenance_ref": "prov:...",
  "proposal_digest": "sha256:..."
}
```

---

# 3. Proposal Has No Authority

ActionProposal 可以非常完整，但：

$$
\boxed{
A_p
\not\Rightarrow
Authorized(A_p)
}
$$

甚至 Agent 可以提出：

```text
delete repository
publish release
send email
modify database
```

而 Runtime 正確回覆：

```text
DENY
```

這不是 Agent failure。

這是 governance 正常工作。

---

# 4. Action Identity

`action_id` 表示一次 action occurrence。

而：

```text
proposal_digest
```

表示 proposal semantic subject。

因此：

$$
\boxed{
\mathrm{ActionOccurrence}
\neq
\mathrm{ActionSemanticIdentity}
}
$$

同一 action proposal 可以因不同 world revision 被重新提出，但應成為新的 action occurrence。

---

# 5. Operation

`operation` 是 provider-neutral semantic operation。

例如：

```text
filesystem.read
filesystem.write

repository.inspect
repository.patch
repository.commit
repository.merge
repository.release

browser.navigate
browser.click
browser.submit

communication.draft
communication.send

database.query
database.mutate

canvas.observe
canvas.control

process.execute
process.terminate
```

不得直接把：

```text
github.rest.PUT.contents
```

作為 canonical operation。

Provider-native wire format 屬 Adapter。

---

# 6. Effect

Effect 描述：

> **如果 action 真正發生，世界中哪些 authority-relevant properties 可能改變。**

Effect 不是 tool 名。

例如：

```text
repository.branch.write
```

是 effect。

```text
git
```

不是。

---

# 7. Effect Registry

v0.7.0 建議核心 effect families：

```text
compute.*
filesystem.*
repository.*
network.*
browser.*
database.*
communication.*
identity.*
credential.*
finance.*
world.*
process.*
package.*
deployment.*
publication.*
```

---

# 8. Core Effect Examples

## Filesystem

```text
filesystem.read
filesystem.write
filesystem.create
filesystem.delete
filesystem.rename
filesystem.execute
```

## Repository

```text
repository.read
repository.working_tree.write
repository.branch.create
repository.branch.write
repository.commit.create
repository.main.write
repository.merge
repository.tag.create
repository.release.publish
```

## Network

```text
network.read
network.write
network.download
network.upload
```

## Communication

```text
communication.read
communication.draft
communication.send
communication.delete
```

## Credential

```text
credential.detect
credential.read
credential.use
credential.export
credential.modify
```

## Identity

```text
identity.resolve
identity.private_read
identity.registry_write
identity.authority_change
```

---

# 9. Effects Are Open-World

Effect registry 可以版本化擴充。

但未知 effect：

$$
e\notin Registry
$$

不得：

```text
ignore
```

而必須：

```text
UNSUPPORTED_EFFECT
```

或：

```text
DEFER
```

因此：

$$
\boxed{
UnknownEffect
\Rightarrow
NoAutomaticExecution
}
$$

---

# 10. Declared Effects Are Not Enough

Agent 可以漏填 effect。

因此 Runtime 必須取得：

$$
E_{declared}
$$

與：

$$
E_{derived}
$$

最後：

$$
\boxed{
E_{effective}
=
E_{declared}
\cup
E_{derived}
}
$$

---

# 11. Effect Deriver

每一個 capability adapter 應提供 deterministic：

```text
derive_effects(operation, parameters)
```

例如：

```text
operation:
repository.patch

parameters:
branch = feature/x
```

導出：

```text
repository.working_tree.write
repository.branch.write
```

---

# 12. Effect Under-Declaration

若：

$$
E_{derived}
\not\subseteq
E_{declared}
$$

可依 policy：

```text
normalize proposal
```

或：

```text
reject malformed proposal
```

但不能使用較小的 declared set 進 authority evaluation。

---

# 13. Effect Over-Declaration

Agent 宣告：

```text
repository.release.publish
```

但 operation 其實只是 read。

可以：

```text
reject
```

或：

```text
normalize downward
```

但 normalization 必須 deterministic 且留下 evidence。

---

# 14. Effect Properties

每個 effect 可有 properties：

```text
reversible
externally_visible
persistent
shared
destructive
privacy_sensitive
credential_sensitive
financial
identity_affecting
authority_affecting
```

---

# 15. Action Classification

Action class 不由 operation name 決定。

定義：

$$
Class(A)
=
f(E_{effective},Target,Policy)
$$

例如：

```text
repository.branch.write
```

可能是：

```text
REVERSIBLE_LOCAL_MUTATION
```

而：

```text
repository.release.publish
```

可能是：

```text
IRREVERSIBLE_PUBLIC_MUTATION
```

---

# 16. Suggested Action Classes

```text
READ_ONLY
LOCAL_COMPUTE
REVERSIBLE_LOCAL_MUTATION
REVERSIBLE_SHARED_MUTATION
EXTERNAL_COMMUNICATION
PUBLICATION
DESTRUCTIVE_MUTATION
CREDENTIAL_SENSITIVE
IDENTITY_AFFECTING
AUTHORITY_AFFECTING
FINANCIAL
UNKNOWN
```

一個 Action 可屬多類。

---

# 17. Capability

Capability 回答：

> Runtime 是否知道如何執行這件事？

形式：

$$
C(a)\in\{0,1\}
$$

例如：

```text
GitHub connector installed
```

表示可能有：

```text
repository.branch.write capability
```

但：

$$
\boxed{
Capability
\neq
Authority
}
$$

---

# 18. CapabilityRef

```json
{
  "schema": "macr-capability-ref/v1",
  "capability_id": "cap:github.update_file",
  "provider": "github",
  "operation": "repository.patch",
  "effect_profile_ref": "effects:github-patch-v1",
  "adapter_version": "1",
  "availability_state": "AVAILABLE"
}
```

---

# 19. Capability Availability

建議：

```text
AVAILABLE
UNAVAILABLE
DEGRADED
DISABLED
UNSUPPORTED
```

Capability 不存在時：

```text
CAPABILITY_MISSING
```

而不是：

```text
AUTHORITY_DENIED
```

---

# 20. Authority

Authority 回答：

> 現在這個 actor，在這個 scope、epoch、revision 下，是否被允許產生這些 effects？

Authority：

$$
Auth
=
(
source,
subject,
scope,
effects,
constraints,
revision,
epoch,
expiry
)
$$

---

# 21. AuthorityEnvelope

```json
{
  "schema": "macr-authority-envelope/v1",
  "authority_id": "auth:...",
  "subject_ref": "agent-run:...",
  "source_kind": "host_operator",
  "source_id": "...",

  "allowed_effects": [
    "repository.read",
    "repository.branch.write"
  ],

  "denied_effects": [
    "repository.main.write",
    "repository.release.publish"
  ],

  "target_scopes": [
    "repo:owner/name"
  ],

  "constraints": [],
  "revision": 4,
  "epoch": 7,
  "valid_from": "...",
  "expires_at": "...",
  "digest": "sha256:..."
}
```

---

# 22. Authority Scope

Authority 必須同時綁：

```text
subject
effect
target
time
revision
epoch
```

因此：

$$
Authorized
=
SubjectMatch
\land
EffectMatch
\land
TargetMatch
\land
TemporalValid
\land
RevisionValid
\land
EpochValid
$$

---

# 23. No Authority from Memory

任何：

```text
conversation
retrieved memory
document
agent message
semantic graph claim
```

都不能自己形成 AuthorityEnvelope。

$$
\boxed{
Information
\neq
Authorization
}
$$

---

# 24. Authority Source

authority source 可為：

```text
human_operator
host_policy
parent_agent_delegation
system_policy
external_verified_identity_authority
```

Agent 自己不能是自己 authority 的 root source。

---

# 25. Self-Expansion Forbidden

Agent 可以提出：

```text
AuthorityExpansionProposal
```

但不能：

```text
AuthorityEnvelope revision 4
→ revision 5 with broader scope
```

自行 commit。

因此：

$$
\boxed{
AgentProposal(Auth')
\neq
Authority(Auth')
}
$$

---

# 26. Parent Delegation

Parent Agent 可給 child：

$$
Auth_C
\subseteq
Auth_P
$$

不得：

$$
Auth_C
\supset
Auth_P
$$

Runtime 必須 deterministic 驗證。

---

# 27. Delegation Intersection

實際 child authority：

$$
Auth_C
=
Requested_C
\cap
ParentAuth
\cap
HostPolicy
$$

不能只依 parent prompt。

---

# 28. Deny Overrides Allow

若：

```text
allowed_effects = repository.*
```

但：

```text
denied_effects = repository.release.publish
```

則：

$$
DENY
$$

優先。

---

# 29. Authority Revision

每個 action admission 綁：

```text
authority_digest
authority_revision
authority_epoch
```

dispatch 前必須再次 revalidate。

避免：

```text
proposal accepted
→ authority revoked
→ old action still executes
```

---

# 30. Authority Epoch

epoch 改變代表：

> 舊 execution continuity 的 authority claims 全部需要重新確認。

因此：

$$
Action.epoch
\neq
CurrentAuthority.epoch
\Rightarrow
DENY
$$

---

# 31. Expiry

如果 action 在：

$$
t_{admission}
<
t_{expiry}
$$

但 dispatch 發生於：

$$
t_{dispatch}
>
t_{expiry}
$$

不得執行。

Authority 必須在 dispatch-time 再驗證。

---

# 32. Budget

Budget 與 Authority 分離。

一件事可能：

```text
authorized but too expensive
```

所以：

$$
\boxed{
Authority
\neq
Budget
}
$$

---

# 33. Budget Envelope

```json
{
  "schema": "macr-budget-envelope/v1",
  "budget_id": "budget:...",
  "agent_run_id": "...",
  "limits": {
    "provider_calls": 20,
    "currency_cost_usd": 1.0,
    "wall_clock_seconds": 3600,
    "child_agent_count": 2
  },
  "revision": 3,
  "digest": "sha256:..."
}
```

---

# 34. Budget Admission

Action cost estimate：

$$
CostEstimate(a)
$$

加上：

$$
UsageSoFar
$$

不得超過：

$$
BudgetLimit
$$

形式：

$$
Usage_t + Estimate(a) \le Budget
$$

---

# 35. Conservative Cost

未知 cost：

```text
UNKNOWN
```

對有付費 provider 的 automatic execution 不應視為：

```text
0
```

應使用：

```text
conservative ceiling
```

或拒絕。

---

# 36. Risk

Risk 不是 Authority。

Risk 回答：

> 即使有 authority，這件事需要多強 verification / human review / isolation？

因此：

$$
\boxed{
Risk
\neq
Authority
}
$$

---

# 37. RiskProfile

可包含：

```text
LOW
MODERATE
HIGH
CRITICAL
```

或多維：

```text
irreversibility
blast_radius
privacy
financial
identity
external_visibility
recovery_cost
```

---

# 38. Risk Does Not Grant or Deny Alone

例如：

```text
HIGH risk
```

不一定 DENY。

可能：

```text
REQUIRE_APPROVAL
```

或：

```text
STRONG_VERIFY
```

---

# 39. Policy

Policy 將：

```text
effect
risk
authority
budget
target
context
```

映射成處置。

$$
P(a)
\rightarrow
Decision
$$

---

# 40. Admission Decision

正式 enum：

```text
ALLOW
ALLOW_WITH_VERIFY
REQUIRE_APPROVAL
DEFER
DENY
ESCALATE
```

---

# 41. ALLOW

允許 dispatch，按普通 verification policy。

---

# 42. ALLOW_WITH_VERIFY

允許 execution，但要求 post-condition verification。

對 autonomous write 建議預設此級。

---

# 43. REQUIRE_APPROVAL

proposal valid，但需要新的 human/host decision。

AgentRun：

```text
BLOCKED
```

或等待 approval。

---

# 44. DEFER

資料不足。

例如：

```text
effect unknown
world basis stale
capability temporarily unavailable
```

不是 DENY。

---

# 45. DENY

當前 contract 明確不允許。

例如：

```text
credential.export
```

---

# 46. ESCALATE

Action 可能超出目前自治層級，需要 higher authority domain 判斷。

例如：

```text
identity registry mutation
authority mutation
public irreversible release
```

---

# 47. Decision Node

Admission Decision 必須形成 ASE `decision` node。

保存：

```text
subject action
effective effects
capability refs
authority ref
budget ref
policy ref
risk profile
verdict
basis digest
```

---

# 48. Decision Is Not Dispatch

核心：

$$
\boxed{
Decision(ALLOW)
\neq
DispatchOccurred
}
$$

在 ALLOW 與 dispatch 之間仍可能：

```text
authority revoked
budget changed
world stale
user cancelled
```

---

# 49. Admission Receipt

可建立：

```json
{
  "schema": "macr-action-admission/v1",
  "action_id": "...",
  "decision_ref": "sem:decision:...",
  "effective_effects": [],
  "capability_refs": [],
  "authority_digest": "...",
  "authority_revision": 4,
  "authority_epoch": 7,
  "budget_digest": "...",
  "world_basis_digest": "...",
  "policy_digest": "...",
  "admission_digest": "..."
}
```

---

# 50. Preconditions

Action 可以要求：

```text
repo HEAD == abc
file digest == xyz
branch == feature/x
issue state == open
resource exists
lock acquired
```

---

# 51. Precondition Check

admission 時檢查一次。

dispatch 立即前再次檢查。

因此：

$$
Precondition_{admit}=true
$$

不代表：

$$
Precondition_{dispatch}=true
$$

---

# 52. Freshness

所有 external mutation action 應有：

```text
world_basis_refs
```

如果 basis stale：

```text
WORLD_STALE
```

不得執行舊 proposal。

---

# 53. Action Recompilation

若 world 變化但 action 邏輯仍可能成立：

```text
old ActionProposal
→ STALE
→ new ActionProposal
```

不建議修改舊 proposal in place。

---

# 54. CommandIntent

通過 admission 後，Runtime 產生 provider-neutral CommandIntent。

```json
{
  "schema": "macr-command-intent/v1",
  "command_intent_id": "cmd:...",
  "action_ref": "action:...",
  "operation": "repository.patch",
  "target_ref": "...",
  "parameter_ref": "...",
  "effective_effects": [],
  "admission_ref": "...",
  "idempotency_ref": "...",
  "verification_policy_ref": "...",
  "command_digest": "..."
}
```

---

# 55. CommandIntent Is Frozen

建立後 immutable。

若 parameters 變動：

```text
new CommandIntent
```

避免 provider adapter 在最後一刻偷偷改 semantic action。

---

# 56. Adapter

Provider Adapter：

$$
Adapter(
CommandIntent
)
\rightarrow
ProviderNativeRequest
$$

Adapter 不得：

- 擴大 effects；
- 換 target；
- 自行 fallback；
- 自行切換 provider；
- 自行提高 output / cost limit。

---

# 57. Adapter Effect Consistency

Provider-native request 導出的 effect：

$$
E_{native}
$$

必須：

$$
E_{native}
\subseteq
E_{authorized}
$$

否則 fail closed。

---

# 58. Provider Selection

Provider routing 與 authority 分離。

Agent 或 GCM 可以推薦 provider。

但：

$$
SelectedProvider
\neq
AuthorizedEffects
$$

---

# 59. No Silent Fallback

若 GitHub provider 失敗：

不得自動：

```text
try shell git
```

除非 fallback route 本身已預先 admission。

因為：

```text
GitHub API effects
```

與：

```text
local shell git effects
```

可能有不同 authority surface。

---

# 60. Dispatch

Dispatch 表示：

> provider invocation 可能即將產生 world effect。

需要：

```text
action_id
command_id
attempt_id
fencing token
authority revision
epoch
```

---

# 61. One-Attempt Default

延續 MACR v0.6：

$$
\boxed{
OneAdmittedCommand
\rightarrow
AtMostOneAutomaticProviderAttempt
}
$$

不 blind retry。

---

# 62. Attempt ID

每次 provider attempt：

```text
attempt_id
```

與：

```text
action_id
```

分離。

$$
\boxed{
Action
\neq
Attempt
}
$$

---

# 63. Dispatch States

```text
NOT_DISPATCHED
DISPATCHING
DISPATCHED
RECEIPT_KNOWN
OUTCOME_UNKNOWN
VERIFIED
```

---

# 64. Atomic Local Dispatch Record

最好：

```text
reserve attempt
→ persist dispatch intent
→ provider call
→ persist observation/receipt
```

但即使如此也無法消除：

```text
provider received request
local process crashed
```

的 ambiguity。

所以 reconciliation 仍必要。

---

# 65. Idempotency

若 provider 支援 idempotency key，CommandIntent 可提供。

但：

$$
\boxed{
ProviderIdempotencyKey
\neq
UniversalExactlyOnce
}
$$

---

# 66. Retry Rule

只有：

$$
KnownNoEffect=1
$$

才允許 automatic retry。

例如：

```text
DNS failure before request sent
local validation failure
capability missing
```

---

# 67. Unknown After Dispatch

只要不能證明：

$$
NoEffect
$$

則：

```text
OUTCOME_UNKNOWN
```

並：

```text
RECONCILIATION_REQUIRED
```

---

# 68. Reconciliation Freeze

當：

$$
OpenReconciliation>0
$$

AgentRun 禁止新的 external mutation。

允許：

```text
observation
status query
reconciliation query
human communication
checkpoint
```

---

# 69. Receipt

Provider response 先成為：

```text
RawProviderObservation
```

再建立：

```text
Receipt
```

Receipt 不等於 success truth。

---

# 70. Receipt Schema

```json
{
  "schema": "macr-actuation-receipt/v1",
  "receipt_id": "receipt:...",
  "action_ref": "...",
  "command_ref": "...",
  "attempt_id": "...",
  "provider": "github",
  "provider_operation_id": "...",
  "reported_status": "success",
  "reported_result_ref": "...",
  "observed_cost_ref": "...",
  "duration_ms": 1200,
  "receipt_digest": "..."
}
```

---

# 71. Provider Error Bodies

Operational DB 不應保存未經審查的完整 remote error body。

只保存：

```text
failure type
bounded status
safe metadata
digest/reference
```

---

# 72. Verification Policy

每個 Action 必須在 admission 前知道：

```text
如何確認世界真的變成預期結果？
```

---

# 73. Verification Classes

```text
NONE
STRUCTURAL
POST_CONDITION
DIFFERENTIAL
INDEPENDENT_OBSERVER
HUMAN_CONFIRMATION
MULTI_GATE
```

對外部 mutation，預設不建議 `NONE`。

---

# 74. Post-Condition Verification

例如 repository.patch：

```text
re-read file
verify digest
run tests
inspect diff
```

---

# 75. Independent Verification

最好：

$$
Verifier
\neq
Actor
$$

不必一定不同 model，但至少不同 execution path / evidence source。

---

# 76. Verification Result

```text
PASSED
FAILED
PARTIAL
DIVERGED
UNKNOWN
STALE
```

---

# 77. Expected vs Observed

Action：

$$
Expected(a)
$$

Re-observation：

$$
Observed(W_{t+1})
$$

Verification：

$$
V
=
Compare(
Expected,
Observed
)
$$

---

# 78. DIVERGED

Provider 可能成功做了事，但不是預期的事。

例如：

```text
expected:
change file A

observed:
file A + file B changed
```

則：

```text
DIVERGED
```

不是：

```text
PASSED
```

---

# 79. PARTIAL

例如：

```text
3 files expected
2 changed
1 failed
```

需要 policy 判斷：

```text
compensate
retry safe subset
human review
```

---

# 80. Verification Does Not Automatically Roll Back

$$
VerificationFailed
\not\Rightarrow
RollbackPossible
$$

尤其 external effects。

---

# 81. Rollback Policy

ActionProposal 可帶：

```text
NONE
TRANSACTIONAL
RESTORE_SNAPSHOT
COMPENSATING_ACTION
MANUAL
```

---

# 82. Rollback vs Compensation

$$
\boxed{
Rollback
\neq
Compensation
}
$$

Rollback：

> 原 transaction 尚可原子回退。

Compensation：

> 已發生 effect，再執行反向或修復 action。

---

# 83. Compensation Is a New Action

Compensation：

$$
A_{comp}
$$

必須重新走：

```text
effects
authority
budget
policy
dispatch
verification
```

不能因為它叫 rollback 就跳過 authority。

---

# 84. Destructive Action

具有：

```text
destructive=true
```

或：

```text
irreversible=true
```

的 action，預設應：

```text
REQUIRE_APPROVAL
```

除非 explicit delegated envelope 已允許。

---

# 85. Public Publication

例如：

```text
repository.release.publish
communication.send
publication.web
```

具有：

```text
externally_visible=true
```

需要單獨 policy。

---

# 86. Credential Actions

`credential.export`：

預設：

```text
DENY
```

`credential.use`：

可以在 bounded adapter 內允許，但 credential bytes 不應經 Agent semantic layer。

---

# 87. Secret Isolation

Agent 可以知道：

```text
credential available = true
```

但不必知道：

```text
credential plaintext
```

---

# 88. Identity-Affecting Actions

例如：

```text
identity.registry_write
identity.merge
identity.delete
```

不應由一般 AgentRun authority 自動包含。

預設：

```text
ESCALATE
```

---

# 89. Authority-Affecting Actions

任何：

```text
grant permission
increase budget
change authority source
disable guardrail
```

都是：

```text
authority_affecting
```

Agent 不能在自己 action loop 內自行完成。

---

# 90. Policy Self-Modification

Agent 可以提出：

```text
PolicyChangeProposal
```

但 active policy change 需要外部 canonical authority。

---

# 91. Self-Constraint

Agent 可以產生：

```text
VERIFY
COMPARE
COUNTEREXAMPLE
STOP
BACKTRACK
DECOMPOSE
```

等 self-constraint。

但它們不能降低既有 Host policy。

---

# 92. Policy Precedence

建議：

$$
HardSystemPolicy
>
AuthorityDeny
>
AuthorityAllow
>
AgentConstraint
>
AgentPreference
$$

---

# 93. Risk-Based Verification

例如：

$$
VerificationStrength
=
f(RiskClass)
$$

低風險：

```text
single structural check
```

高風險：

```text
re-observe
independent verifier
human approval
```

---

# 94. Action Admission Function

正式定義：

$$
Admit(a,R,t)
=
SemanticValid(a)
\land
EffectsKnown(a)
\land
CapabilityAvailable(a)
\land
AuthorityValid(a,R,t)
\land
BudgetValid(a,R,t)
\land
PolicyAllows(a,R,t)
\land
PreconditionsFresh(a,R,t)
\land
NoOpenReconciliation(R)
$$

若全部成立：

$$
ALLOW
$$

或：

$$
ALLOW\_WITH\_VERIFY
$$

---

# 95. Dispatchable

即使已 admission：

$$
Dispatchable(a,t)
$$

仍需重新確認：

$$
Authority_t
$$

$$
Budget_t
$$

$$
Preconditions_t
$$

$$
Fencing_t
$$

因此：

$$
\boxed{
Admitted_t
\not\Rightarrow
Dispatchable_{t+\Delta}
}
$$

---

# 96. Effect Authorization

定義：

$$
AuthorizedEffects(a)
=
\forall e\in E_{effective}(a),
Allowed(e,target,subject,t)
$$

任一 effect fail：

$$
Authorize(a)=0
$$

---

# 97. Partial Authority Is Not Partial Execution

假設 action effects：

```text
filesystem.write
network.write
```

authority 只允許：

```text
filesystem.write
```

不能只執行其中一半。

應整個 action：

```text
DENY
```

除非 Agent 重新提出拆分後 action。

---

# 98. Action Decomposition

Agent 可以：

```text
A
→ A1 + A2
```

讓：

```text
A1 authorized
A2 blocked
```

但 decomposition 必須保持 semantic relationship：

```text
A1 implements A
A2 implements A
```

---

# 99. Capability Is Not Whitelist of Imagination

SEDB v0.4B 已使用 open-world autonomy 思路：

> novel action 可以 authority-valid，但 capability missing。

MACR 保留這個原則。

因此：

$$
\boxed{
NovelAction
\not\Rightarrow
Unauthorized
}
$$

但：

$$
CapabilityMissing
\Rightarrow
NoExecution
$$

---

# 100. Novel Action

若 effects 都在 authority envelope 內，但 adapter 尚不存在：

```text
Decision:
ALLOW semantic authority

Execution:
CAPABILITY_MISSING
```

這兩個狀態可以同時成立。

---

# 101. Action History

Action 不刪除。

至少保存：

```text
proposal
admission
command
attempt
receipt
verification
compensation
```

---

# 102. Action Current State vs History

Current action projection：

```text
VERIFIED
```

不代表 historical attempt 被刪除。

---

# 103. Event Types

```text
action.proposed
action.effects_derived
action.capability_resolved
action.authority_checked
action.budget_checked
action.policy_evaluated
action.admitted
action.denied
action.approval_required
action.command_compiled
action.dispatch_requested
action.dispatched
action.receipt_captured
action.reobservation_bound
action.verification_completed
action.diverged
action.reconciliation_required
action.reconciliation_resolved
action.compensation_proposed
action.compensation_completed
```

---

# 104. Event Payload Privacy

Operational events 不保存：

```text
API keys
raw prompt
raw private document
credential plaintext
full provider answer
```

只保存：

```text
refs
digests
state
counts
safe bounded metadata
```

---

# 105. Cross-System Mapping

## MACR

擁有：

```text
ActionProposal
admission
authority/budget gating
dispatch orchestration
reconciliation
```

## ASE

擁有：

```text
semantic representation
relations
decision/receipt/verification nodes
```

## PHOSPHOR

提供：

```text
CommandIntent / actuation / measured reality semantics
```

## PNCW

提供：

```text
post-action verified world observation
```

## SEDB

可保存：

```text
long-term decisions
receipts
world evolution
```

---

# 106. PHOSPHOR Bridge

建議：

$$
\Phi_P:
MACR.CommandIntent
\rightarrow
PHOSPHOR.CommandIntent
$$

要求保持：

```text
operation
effects
target
authority binding
preconditions
expected outcome
```

無 semantic loss。

---

# 107. PNCW Verification Bridge

Actuation 後：

```text
World
→ PNCW ProjectionRequest
→ VERIFIED
→ VISIBLE
→ ASE Observation
→ Verification
```

因此：

$$
\boxed{
ActuationReceipt
\neq
WorldObservation
}
$$

---

# 108. MRMIC Action

例如：

```text
world.visual.control
```

MRMIC 可提供：

```text
focus portal
click
gesture
viewport
control ownership
```

但 provider resource mutation authority 仍必須獨立判斷。

---

# 109. Portal Control

MRMIC `controlOwner` 只代表 visual/control surface ownership。

不代表：

$$
\mathrm{ExternalResourceAuthority}
$$

---

# 110. Direct Chat Boundary

Direct Chat 不使用 Agent Action Gate，除非使用者明確將 conversation 升級為 AgentRun 或觸發受治理 action。

普通聊天仍可：

```text
message → provider → response
```

不強迫全走 Agent loop。

---

# 111. Worker Boundary

Worker 可以有 TaskContract capability。

但如果 Worker 需要 external mutation，仍必須取得 parent AgentRun 投影出的 bounded authority。

---

# 112. Multi-Agent Action

Child action authority：

$$
Auth_{child}
\subseteq
Auth_{parent}
$$

且：

$$
Budget_{child}
\subseteq
Budget_{parent}
$$

---

# 113. Child Decision Does Not Bind Parent

Child：

```text
Decision = ALLOW
```

不能替代 parent Runtime admission。

它最多回：

```text
ActionProposal
```

---

# 114. Human Approval

Approval 必須綁定 exact proposal/admission digest。

不能：

```text
yes
```

被套用到之後已改變 parameters 的 action。

---

# 115. Approval Digest Binding

Approval：

$$
Approve(
ProposalDigest,
EffectDigest,
TargetDigest,
BudgetCeiling
)
$$

任一改變：

$$
ApprovalInvalid
$$

---

# 116. Approval Expiry

Approval 應可 expiry。

特別是：

```text
external publish
financial
authority-affecting
```

---

# 117. Generic Approval Prohibited

例如：

```text
"You can do whatever is needed."
```

不應被解析為 unrestricted authority。

必須映射到 explicit scope/effects。

---

# 118. Action Bundles

未來可以一次 admission 一個 bounded bundle：

```text
A1
A2
A3
```

但 bundle 必須：

- bind exact ordered members；
- bind effects；
- bind aggregate budget；
- bind authority；
- specify failure policy。

這可延續 MACR T1 manifest 思路。

---

# 119. Bundle Atomicity

除非 provider 真正支援 transaction，不得宣稱：

```text
all-or-nothing external bundle
```

應明確記錄每個 member outcome。

---

# 120. Action Sequence Replanning

若：

```text
A1 completes
```

後 World 已與原計畫不同：

```text
A2
```

需要重新 freshness check。

不能因 bundle 原本 approved 就 blind continue。

---

# 121. Verification Before Next Mutation

高風險 sequential actions 可要求：

```text
A1
→ verify
→ A2
```

而不是：

```text
A1
→ A2
→ A3
→ verify at end
```

---

# 122. Failure Taxonomy

Action-level failure：

```text
INVALID_PROPOSAL
UNSUPPORTED_EFFECT
CAPABILITY_MISSING
AUTHORITY_DENIED
AUTHORITY_STALE
BUDGET_EXHAUSTED
POLICY_DENIED
APPROVAL_REQUIRED
PRECONDITION_FAILED
WORLD_STALE
DISPATCH_FAILED_NO_EFFECT
UNKNOWN_AFTER_DISPATCH
PROVIDER_REJECTED
RECEIPT_MALFORMED
VERIFICATION_FAILED
ACTION_DIVERGED
COMPENSATION_REQUIRED
```

---

# 123. Retry Matrix

| Failure | Auto retry |
|---|---|
| INVALID_PROPOSAL | No |
| CAPABILITY_MISSING | No |
| AUTHORITY_DENIED | No |
| BUDGET_EXHAUSTED | No |
| PRECONDITION_FAILED | Replan |
| DISPATCH_FAILED_NO_EFFECT | Maybe |
| UNKNOWN_AFTER_DISPATCH | Never |
| PROVIDER_REJECTED | Policy-specific |
| VERIFICATION_FAILED | No blind retry |
| ACTION_DIVERGED | Reconcile |

---

# 124. Reconciliation

`UNKNOWN_AFTER_DISPATCH`：

$$
\Rightarrow
RECONCILIATION\_REQUIRED
$$

直到：

```text
reobserve
provider status query
human evidence
external state comparison
```

可以建立 resolution。

---

# 125. Reconciliation Resolution

```text
NOT_EXECUTED
EXECUTED_AS_EXPECTED
EXECUTED_DIFFERENTLY
PARTIALLY_EXECUTED
STATE_UNKNOWN
```

---

# 126. STATE_UNKNOWN

如果最終仍：

```text
STATE_UNKNOWN
```

run 不得自動解除 mutation freeze。

可以：

```text
human override
cancel
manual recovery
```

---

# 127. Completion Dependency

AgentRun 不得 COMPLETED，如果：

```text
pending mutation verification
open reconciliation
required compensation incomplete
```

---

# 128. Canonical Action Digest

建議分：

$$
D_{proposal}
$$

$$
D_{admission}
$$

$$
D_{command}
$$

$$
D_{receipt}
$$

$$
D_{verification}
$$

避免全部混成一個 hash。

---

# 129. Why Separate Digests

可以準確回答：

> Agent 提議的是什麼？

> Runtime 批准的是什麼？

> Adapter 真正送的是什麼？

> Provider 回的是什麼？

> World 最終如何？

---

# 130. Canonicalization

所有 digest 使用 MACR canonical serializer。

不得 provider-specific serializer 決定 semantic identity。

---

# 131. Immutability

以下一旦建立不可修改：

```text
ActionProposal
AdmissionReceipt
CommandIntent
ProviderAttempt
Receipt
VerificationResult
```

若修正：

```text
new record
supersedes old
```

---

# 132. Action Store

建議 SQLite：

```text
agent_actions
action_admissions
command_intents
action_attempts
actuation_receipts
action_verifications
action_reconciliation
```

但 physical schema 不屬 ontology。

---

# 133. Agent-Facing API

Agent 可以：

```text
propose_action()
request_approval()
request_reobservation()
```

不能：

```text
authorize_self()
increase_budget()
force_dispatch()
mark_verified()
resolve_reconciliation()
```

---

# 134. Host-Facing API

Runtime/host：

```text
evaluate_action()
approve_action()
deny_action()
compile_command()
dispatch_command()
record_receipt()
verify_action()
require_reconciliation()
resolve_reconciliation()
```

---

# 135. Policy Evaluation Must Be Replayable

相同：

```text
proposal
authority
budget
policy snapshot
world basis
```

應得到相同 deterministic policy result，若 policy 本身 deterministic。

---

# 136. LLM Policy Is Advisory

若使用 model 輔助 risk analysis：

```text
LLM RiskProposal
```

仍需 deterministic boundary 判斷 final admission。

---

# 137. Dynamic Policy

policy 可以更新。

但已 admission 尚未 dispatch 的 action，若 policy revision 改變：

```text
revalidate
```

---

# 138. Policy Snapshot

Admission bind：

```text
policy_snapshot_digest
```

與 MACR v0.6 現有 `policy_snapshot_sha256` 方向一致。

---

# 139. Provider Model Token Policy

若 Action 包含 cognition/provider invocation，仍需 bind exact model-token policy。

Agent authority 不可以隱式提高 model output/context limit。

---

# 140. Example — Repository Repair

Proposal：

```text
operation:
repository.patch

effects:
repository.working_tree.write
repository.branch.write
```

Capability：

```text
AVAILABLE
```

Authority：

```text
branch write allowed
main write denied
```

Budget：

```text
OK
```

Risk：

```text
REVERSIBLE_LOCAL_MUTATION
```

Policy：

```text
ALLOW_WITH_VERIFY
```

Command：

```text
patch exact branch
```

Actuation。

Receipt：

```text
patch applied
```

Re-observe：

```text
diff matches
```

Verification：

```text
PASSED
```

---

# 141. Example — Main Branch Denial

Agent proposal：

```text
repository.main.write
```

Capability：

```text
AVAILABLE
```

Authority：

```text
DENIED
```

結果：

```text
AUTHORITY_DENIED
```

不是：

```text
CAPABILITY_MISSING
```

---

# 142. Example — Novel Capability Missing

Agent proposal：

```text
world.simulator.spawn_instance
```

effects 都在 authority 內。

但無 adapter：

```text
CAPABILITY_MISSING
```

Semantic action 可以是 authority-valid。

---

# 143. Example — Unknown Effect

Agent proposal：

```text
operation = custom.magic_action
effects = custom.unknown
```

結果：

```text
DEFER / UNSUPPORTED_EFFECT
```

不得：

```text
ALLOW because no dangerous effect recognized
```

---

# 144. Example — Provider Timeout

若確定 TCP 連線前失敗：

```text
DISPATCH_FAILED_NO_EFFECT
```

可依 policy retry。

若 request 已送出，response lost：

```text
UNKNOWN_AFTER_DISPATCH
```

禁止 auto retry。

---

# 145. Example — Receipt vs Reality

Receipt：

```text
status = success
```

PNCW re-observation：

```text
target unchanged
```

Verification：

```text
DIVERGED
```

AgentRun：

```text
BLOCKED
```

或：

```text
RECONCILIATION_REQUIRED
```

依 action type。

---

# 146. Example — Public Release

Action：

```text
repository.release.publish
```

Capability：

```text
AVAILABLE
```

Authority：

```text
not explicitly delegated
```

Policy：

```text
REQUIRE_APPROVAL
```

Agent 可以準備：

```text
release notes
artifacts
validation
```

但不能 publish。

---

# 147. Example — Credential Use

Action：

```text
use GitHub token via trusted adapter
```

Effect：

```text
credential.use
network.write
repository.branch.write
```

Agent 只看到：

```text
credential_ref
```

不看到 token plaintext。

---

# 148. Negative Controls

```text
NC-AAE-01 tool exists but no authority
NC-AAE-02 authority exists but no capability
NC-AAE-03 unknown effect treated safe
NC-AAE-04 omitted effect bypasses gate
NC-AAE-05 child authority exceeds parent
NC-AAE-06 Agent self-expands authority
NC-AAE-07 Agent self-expands budget
NC-AAE-08 stale authority admission
NC-AAE-09 expired authority dispatch
NC-AAE-10 stale world basis dispatch
NC-AAE-11 approval reused after proposal mutation
NC-AAE-12 provider adapter adds extra effect
NC-AAE-13 silent provider fallback
NC-AAE-14 unknown-after-dispatch auto retry
NC-AAE-15 receipt promoted to verification
NC-AAE-16 compensation skips authority
NC-AAE-17 mutation during reconciliation
NC-AAE-18 policy revision ignored before dispatch
NC-AAE-19 partial authority causes partial action
NC-AAE-20 provider key enters semantic graph
NC-AAE-21 main write inferred from branch write
NC-AAE-22 visual control inferred as provider ownership
NC-AAE-23 Decision ALLOW treated as dispatch evidence
NC-AAE-24 destructive action treated reversible without proof
```

---

# 149. Acceptance Matrix

## Effect

- registered effects；
- deterministic derivation；
- unknown effects fail closed；
- declared/derived union correct。

## Capability

- absent capability separate from denied authority；
- disabled capability rejected。

## Authority

- subject/scope/effect/time/revision/epoch all checked；
- deny overrides allow；
- child projection bounded。

## Budget

- exact revision binding；
- no self-expansion；
- conservative unknown cost。

## Admission

- replayable verdict；
- exact policy snapshot；
- freshness checked。

## Command

- immutable；
- adapter cannot widen effects；
- no silent fallback。

## Dispatch

- one-attempt default；
- fencing；
- unknown-after-dispatch classification。

## Receipt

- immutable；
- safe metadata only；
- not verification。

## Verification

- explicit policy；
- re-observation；
- expected/observed comparison；
- divergence surfaced。

## Reconciliation

- mutation freeze；
- explicit resolution；
- no self-resolution by Agent。

---

# 150. v0.7.0 Minimum Implementation

第一工程版至少實作：

```text
ActionProposal
EffectRegistry
EffectDeriver
CapabilityRef
AuthorityEnvelope adapter
BudgetEnvelope
AdmissionDecision
AdmissionReceipt
CommandIntent
ActionAttempt
Receipt
VerificationPolicy
VerificationResult
ReconciliationRecord
```

---

# 151. Relationship to Existing MACR v0.6

直接 reuse：

```text
AuthorizationReference
revision
epoch
scope
DispatchContext
policy_snapshot_sha256
run_id
Candidate Vault
ProviderObservation
Accounting
one-attempt execution
unknown_after_dispatch
reconciliation semantics
```

v0.7 是：

```text
Agent Action Gate
↓
existing MACR provider/runtime core
```

而不是推翻現有 execution chain。

---

# 152. Relationship to SEDB v0.4B

採用概念：

$$
\boxed{
Consensus
\neq
Authority
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
Capability
\neq
Authority
}
$$

以及：

> Novel Action 可以 authority-valid，但 capability missing。

但 MACR 不直接依賴 SEDB autonomy implementation。

---

# 153. Relationship to PHOSPHOR

採用：

$$
\boxed{
PolicyProposal
\neq
CommandIntent
\neq
Actuation
}
$$

以及：

$$
\boxed{
Desired
\neq
Requested
\neq
Realized
\neq
Observed
}
$$

這使 MACR action lifecycle 能正確表示「想做」「要求做」「實際做」「觀察到」四個不同狀態。

---

# 154. Relationship to PNCW

PNCW 提供最終：

```text
VerifiedObservation
```

因此 Action verification 不把 provider receipt 當世界真相。

---

# 155. Relationship to ASE

本文件的：

```text
ActionProposal
Decision
Receipt
Verification
Failure
```

全部同時是 ASE semantic nodes。

但真正 authority / budget resolution 仍由 Runtime subsystem 負責。

---

# 156. Formal Safety Condition

Agent action $a$ 的安全 dispatch 必要條件：

$$
\boxed{
\begin{aligned}
SafeDispatch(a,R,t)
={}&
SemanticValid(a)\\
&\land EffectsKnown(a)\\
&\land CapabilityAvailable(a)\\
&\land AuthorityValid(a,R,t)\\
&\land BudgetValid(a,R,t)\\
&\land PolicyAllows(a,R,t)\\
&\land PreconditionsFresh(a,R,t)\\
&\land FenceValid(R,t)\\
&\land OpenReconciliation(R)=0
\end{aligned}
}
$$

---

# 157. Formal Outcome Condition

Action 成功不是 receipt success。

$$
\boxed{
Success(a)
=
ActuationKnown(a)
\land
Verification(a)=PASSED
}
$$

若：

$$
Receipt=success
$$

但：

$$
Verification=DIVERGED
$$

則：

$$
Success(a)=0
$$

---

# 158. Formal Retry Condition

$$
\boxed{
AutoRetry(a)
\Rightarrow
KnownNoExternalEffect(a)
}
$$

反之：

$$
UnknownEffectState(a)
\Rightarrow
ReconciliationRequired
$$

---

# 159. Canonical Closure

本文件固定：

1. Agent 只能提出 ActionProposal，不能直接產生 execution authority。
2. Operation 與 Effect 分離。
3. Tool / Capability 與 Authority 分離。
4. Authority 與 Budget 分離。
5. Risk 與 Authority 分離。
6. Effect 必須由 declared + deterministic derived effects 組合。
7. Unknown effect fail closed。
8. Novel action 不必自動 unauthorized，但沒有 capability 就不能執行。
9. Authority 綁 subject、effect、target、time、revision、epoch。
10. Agent 不可自行擴張 authority 或 budget。
11. Child authority 必須是 parent authority 子集。
12. Admission 與 Dispatch 分離。
13. CommandIntent 與 provider-native request 分離。
14. Adapter 不得擴張 semantic effects。
15. 不允許 silent provider fallback。
16. provider attempt 預設 one-attempt。
17. unknown-after-dispatch 不得 auto retry。
18. Receipt 不等於 Verification。
19. Action outcome 必須經 re-observation / verification。
20. Rollback 與 Compensation 分離。
21. Compensation 本身是新的受治理 Action。
22. Open reconciliation 時禁止新的 external mutation。
23. Approval 綁 exact proposal/effects/target，而不是模糊自然語言。
24. credential plaintext 不進 ASE / Agent semantic state。
25. action success 必須建立在 verified outcome，而不是 provider 宣稱。

因此：

$$
\boxed{
\mathrm{AutonomousAction}
=
\mathrm{Proposal}
+
\mathrm{Effects}
+
\mathrm{Capability}
+
\mathrm{Authority}
+
\mathrm{Budget}
+
\mathrm{Policy}
+
\mathrm{Freshness}
+
\mathrm{Actuation}
+
\mathrm{Verification}
}
$$

MACR v0.7 所謂「讓 AI 自主活動」，因此不是：

```text
給 AI shell
```

也不是：

```text
給 AI 一堆 MCP tools
```

而是建立：

> **一套允許 AI 自主產生候選行動，同時把真正的世界改變權保留在可驗證、可撤銷、可限制、可追蹤的 runtime contract 中。**

這構成 MACR Agent-Spacetime Runtime 的第三個 canonical engineering core。

---

# Appendix A — Canonical Contracts

```text
macr-action-proposal/v1
macr-effect-registry/v1
macr-capability-ref/v1
macr-authority-envelope/v1
macr-budget-envelope/v1
macr-action-admission/v1
macr-command-intent/v1
macr-action-attempt/v1
macr-actuation-receipt/v1
macr-verification-policy/v1
macr-action-verification/v1
macr-action-reconciliation/v1
```

---

# Appendix B — Core Admission Outcomes

```text
ALLOW
ALLOW_WITH_VERIFY
REQUIRE_APPROVAL
DEFER
DENY
ESCALATE
```

---

# Appendix C — Core Action Lifecycle

```text
PROPOSED
↓
SEMANTIC_VALID
↓
EFFECTS_RESOLVED
↓
CAPABILITY_RESOLVED
↓
AUTHORITY_CHECKED
↓
BUDGET_CHECKED
↓
POLICY_EVALUATED
↓
ADMITTED
↓
COMMAND_COMPILED
↓
DISPATCHING
↓
DISPATCHED
↓
RECEIPT_CAPTURED
↓
REOBSERVED
↓
VERIFIED
```

Failure branches：

```text
DENIED
BLOCKED
APPROVAL_REQUIRED
STALE
FAILED_NO_EFFECT
RECONCILIATION_REQUIRED
DIVERGED
COMPENSATION_REQUIRED
```

---

# Appendix D — Next Canonical Specification

下一份：

**MACR × PNCW — Verified Observation Bridge Specification v0.1**

將正式定義：

```text
Agent ObservationIntent
→ ProjectionRequest
→ PNCW Readiness
→ ProjectionManifest
→ Verification
→ VisibilityCommit
→ VerifiedObservationRef
→ ASE Observation Node
→ Planning Basis
```

以及：

```text
stale observation
world revision
observation scope
partial residency
re-observation
post-actuation verification
```

如何成為 MACR v0.7 Agent 對世界的唯一 canonical observation path。