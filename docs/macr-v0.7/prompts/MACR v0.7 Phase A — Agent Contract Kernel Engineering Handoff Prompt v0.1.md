# MACR v0.7 Phase A — Agent Contract Kernel Engineering Handoff Prompt v0.1

## 工作台正式實作交接提示詞

你現在正在接手 **MACR v0.7 — Agent-Spacetime Runtime** 的第一個正式工程階段。

本輪不是重新研究 Agent 架構，不是重新比較 Agent Framework，也不是開始 Multi-Agent。

本輪只完成：

# **Phase A — Agent Contract Kernel**

---

# 0. Repository

GitHub：

`kakon77777-commits/MACR`

Canonical engineering baseline：

`main`

規劃時已確認的 baseline HEAD：

`d3ecaf16de66fb7df326253fbd09df3aa353b5f4`

version：

`0.6.0a1`

開始時必須自行重新確認 GitHub / local repository 當前 `main` HEAD。

如果 `main` 已比上述 commit 更新：

> **以實際最新 `main` 為 engineering baseline。**

不得強行 reset 回舊 commit。

---

# 1. Canonical Architecture Context

MACR v0.7 已完成以下 canonical architecture / specification convergence：

```text
00 Agent-Spacetime Canonical Convergence Architecture
01 AgentRun Canonical State Specification
02 Agent Semantic Envelope Specification
03 Action / Authority / Effect Contract
04 MACR × PNCW Verified Observation Bridge
05 MACR × PHOSPHOR Governed Actuation Bridge
06 Checkpoint / Suspend / Wake / Temporal Continuation
07 Single-Agent MVP Implementation Plan
08 Verification & Negative-Control Matrix
09 External Agent Framework Primitive Adoption Matrix
10 SEDB vNext Agent / World State Adaptation Proposal
```

本輪禁止重新設計這套 architecture。

若完整文件沒有直接存在於 repository：

> **本提示詞所列 Phase A contract requirements 即為本輪實作的 authoritative condensed specification。**

不要因找不到 00–10 文件就重新做 architecture research。

---

# 2. MACR v0.7 Core Direction

MACR v0.6 是：

```text
heterogeneous model / worker runtime
```

MACR v0.7 開始進入：

```text
Agent-Spacetime Runtime
```

核心概念：

```text
Goal
→ AgentRun
→ Verified Observation
→ Semantic Working State
→ Plan
→ Action Proposal
→ Authority / Capability / Budget
→ CommandIntent
→ Actuation
→ ReObservation
→ Verification
→ Checkpoint
→ Continue / Suspend / Stop
```

但本輪 **Phase A 不實作完整 loop**。

Phase A 只建立後續所有工程依賴的 canonical contract kernel。

---

# 3. Hard Architecture Invariants

以下 invariants 不得被修改：

$$
\boxed{\mathrm{Model}\neq\mathrm{Agent}}
$$

$$
\boxed{\mathrm{Agent}\neq\mathrm{Resident}}
$$

$$
\boxed{\mathrm{AgentRun}\neq\mathrm{InvocationRun}}
$$

$$
\boxed{\mathrm{Conversation}\neq\mathrm{AgentRun}}
$$

$$
\boxed{\mathrm{Observation}\neq\mathrm{World}}
$$

$$
\boxed{\mathrm{Capability}\neq\mathrm{Authority}}
$$

$$
\boxed{\mathrm{Goal}\neq\mathrm{Authority}}
$$

$$
\boxed{\mathrm{Plan}\neq\mathrm{Command}}
$$

$$
\boxed{\mathrm{Decision}\neq\mathrm{Commit}}
$$

$$
\boxed{\mathrm{Receipt}\neq\mathrm{Verification}}
$$

$$
\boxed{\mathrm{Wake}\neq\mathrm{Authorization}}
$$

$$
\boxed{\mathrm{Resume}\neq\mathrm{Replay}}
$$

$$
\boxed{\mathrm{Checkpoint}\neq\mathrm{AuthorityRollback}}
$$

$$
\boxed{\mathrm{Time}\neq\mathrm{Compute}}
$$

以及：

$$
\boxed{
\mathrm{UnknownAfterDispatch}
\Rightarrow
\mathrm{ReconciliationRequired}
}
$$

本輪雖然還不實作 runtime behavior，但 contract 不得讓未來無法維持這些 invariant。

---

# 4. Existing MACR Core Must Be Preserved

開始前必須 source-inspect：

```text
src/macr_runtime/canonical.py
src/macr_runtime/contracts.py
src/macr_runtime/execution.py
src/macr_runtime/authority.py
src/macr_runtime/batch_authority.py
src/macr_runtime/accounting.py
src/macr_runtime/candidate_vault.py
src/macr_runtime/coordination.py
src/macr_runtime/coordinator_contract.py
src/macr_runtime/plan_runtime.py
src/macr_runtime/runtime.py
src/macr_runtime/config.py
src/macr_runtime/cli.py
```

以及相關 tests：

```text
tests/test_canonical.py
tests/test_contracts.py
tests/test_authority.py
tests/test_batch_authority.py
tests/test_accounting.py
tests/test_candidate_vault.py
tests/test_coordination.py
tests/test_coordinator_contract.py
tests/test_cli.py
```

並檢查：

```text
scripts/verify.ps1
scripts/verify-v06.ps1
```

目的不是重構它們。

目的是：

> **確保新 Agent contracts 能沿用現有 MACR canonical identity / authority / execution semantics，而不是建立平行宇宙。**

---

# 5. Important Existing Facts

現行 `canonical.py` 已提供：

```python
canonical_json_bytes(...)
sha256_id(...)
aware_iso8601(...)
```

現有 canonical profile：

- JSON；
- sorted keys；
- UTF-8；
- compact separators；
- finite JSON values only；
- rejects NaN / Infinity；
- deterministic namespace-separated SHA-256 identity。

Phase A 應優先重用此機制。

---

# 6. Canonicalization Rule

本輪禁止為 Agent contracts 自建：

```python
json.dumps(...)
hashlib.sha256(...)
```

的平行 identity implementation。

所有新 identity digest 應透過：

```text
macr_runtime.canonical
```

或經過 source-audited 的 additive extension。

---

# 7. Do Not Casually Change Existing Canonical Profile

現行 MACR 已有大量 object / tests 使用既有 canonical serializer。

因此 Phase A：

> **不得為了 Agent 理論上的漂亮設計，直接修改整個 MACR canonical representation。**

如果新 Agent contract 可以避免 identity-critical floating values：

優先避免。

若真的需要修改 canonical profile：

必須：

1. 證明現有 profile無法滿足 contract；
2. 加 backward regression；
3. 證明所有 historical MACR identity不被破壞；
4. 明確記錄 migration implication。

否則不要改。

---

# 8. Existing Authorization Semantics Must Be Reused

現有 `AuthorizationReference` 已具有：

```text
source_kind
source_id
digest
revision
epoch
scope
```

Phase A 不建立：

```text
AgentAuthorizationV2
```

作第二套 authority。

Phase A contract最多建立：

```text
AuthorityBinding
AuthorityEnvelopeRef
```

引用現有 authority semantics。

真正 effect-aware Agent authority adaptation屬 **Phase E**。

---

# 9. Existing Invocation run_id Must Remain

現有：

```text
DispatchContext.run_id
```

表示 bounded provider/runtime invocation。

Agent 新增：

```text
agent_run_id
```

表示 long-lived Agent execution lineage。

兩者禁止共用 identity。

---

# 10. Interaction Plane

現有：

```text
DIRECT
DELEGATION
```

本輪不要因為 v0.7 叫 Agent Runtime 就立即新增：

```text
AGENT
```

除非 source inspection證明：

- enum extension影響非常小；
-所有 consumers都有完整 tests；
-不會擴大 Phase A scope。

預設：

> **Phase A 不修改 InteractionPlane。**

Agent invocation integration留給後續 Phase。

---

# 11. No External Agent Framework

本輪禁止新增 mandatory dependency：

```text
LangGraph
LangChain
Microsoft Agent Framework
OpenAI Agents SDK
CrewAI
Temporal
Browser Use
```

Phase A contract kernel應為 pure MACR-native implementation。

---

# 12. Working Branch

建議建立：

`workbench/v0.7-agent-contract-kernel`

或：

`integration/v0.7.0a1-single-agent`

若 repository已有使用中的 v0.7 branch：

先確認狀態並沿用合理 branch。

不要同時建立很多 branch。

---

# 13. Phase A Scope

本輪只實作五組 contract families：

```text
A1 — AgentRun Contracts
A2 — Semantic Contracts
A3 — Observation Contracts
A4 — Action Contracts
A5 — Temporal Contracts
```

加：

```text
A6 — Canonical Validation / Cross-Contract Tests
A7 — Phase A Verification / Evidence
```

---

# 14. Recommended New Package Layout

建立：

```text
src/macr_runtime/agent/
src/macr_runtime/semantic/
src/macr_runtime/observation/
src/macr_runtime/action/
src/macr_runtime/temporal/
```

每個 package至少：

```text
__init__.py
contracts.py
```

不要現在提前建立：

```text
runner.py
loop.py
scheduler.py
pncw_bridge.py
dispatch.py
store.py
```

除非 contract tests不可避免需要薄 helper。

Phase A 的目標是 contract kernel，不是提前偷做 Phase B–F。

---

# 15. A1 — AgentRun Contracts

最低需要：

```text
AgentRunState
AgentRunIdentity / AgentRunRef
GoalBinding
AuthorityBinding
BudgetBinding
SemanticStateBinding
PlanBinding
WorldBindingRef
AgentRunHeader
```

---

# 16. AgentRunState

必須至少：

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

本輪不實作 lifecycle transition engine。

只固定 contract vocabulary。

---

# 17. AgentRun Identity

要求：

```text
agent_run_id
```

使用 occurrence identity。

推薦 UUIDv4，延續 MACR invocation identity風格。

不得以 Goal digest直接作 AgentRun identity。

---

# 18. AgentRun Subject Digest

同時需要 deterministic semantic subject identity。

概念：

```text
subject_digest
```

可基於：

```text
agent_ref
initial goal
origin
authority binding
budget binding
world binding set
```

但 **Phase A 不要過度把未來 mutable object塞進 subject digest**。

實作前先寫測試固定哪些欄位參與 identity。

---

# 19. AgentRun Header

至少要能表達：

```text
schema/version
agent_run_id
agent_ref
subject_digest
origin
state
state_revision
epoch
goal binding
authority binding
budget binding
parent_agent_run_id
delegation_ref
created_at
```

---

# 20. Revision

contract要求：

```text
state_revision >= 1
```

是否初始採 `1` 或 `0`：

以現有 MACR revision convention source inspection後統一。

不要讓 Agent contracts自己使用與 existing plan/authority完全不同的 revision philosophy。

---

# 21. Epoch

要求：

```text
epoch >= 0
```

不得與 revision合併。

---

# 22. Terminal State Helper

可以提供 pure helper：

```python
is_terminal_agent_run_state(...)
```

不實作 transition engine。

---

# 23. A2 — Semantic Contracts

Phase A 不實作 EML-U。

建立 MACR provisional：

# **Agent Semantic Envelope — ASE**

---

# 24. SemanticNode

最低欄位：

```text
node_id
node_type
payload
scope
effects
constraints
policy
provenance
temporal
status
content_digest
record_digest
```

---

# 25. Core Node Types

至少：

```text
goal
trigger
observation
claim
hypothesis
plan
task
action_proposal
constraint
decision
receipt
verification
checkpoint
failure
wake_condition
```

可以 enum或 validated registry。

Phase A 建議使用 explicit enum / bounded registry。

---

# 26. SemanticRelation

至少：

```text
relation_id
source_ref
relation_type
target_ref
qualifiers
provenance
relation_digest
```

---

# 27. Core Relation Types

至少：

```text
supports
contradicts
depends_on
derived_from
observes
describes
constrains
motivates
targets
affects
expects
produced
verifies
refutes
supersedes
revises
blocks
resolves
causes
precedes
follows
waits_for
```

不要現在加入幾百個 relation type。

---

# 28. Authority Relation Warning

若保留：

```text
authorizes
```

relation vocabulary：

測試必須明確保證：

> semantic relation 本身不構成 `AuthorizationReference`。

若容易造成誤用，Phase A 可以先不提供 `authorizes` relation，而等 Phase E用 authority decision reference明確接入。

---

# 29. SemanticPatch

至少：

```text
patch_id
base_graph_digest
add_nodes
add_relations
status_updates / supersession refs
producer_ref
patch_digest
```

Phase A 只做 contract。

不實作 graph persistence/commit。

---

# 30. Content Digest vs Record Digest

需要固定：

$$
D_{content}
$$

與：

$$
D_{record}
$$

分離。

目的：

```text
same semantic statement
different provenance
```

應：

```text
content_digest equal
record_digest different
```

---

# 31. Provenance

最低：

```text
origin_kind
origin_ref
source_refs
agent_run_id optional
created_by_ref
```

避免大 payload。

---

# 32. Forbidden Semantic Payload

contract validation至少不得接受：

```text
raw bytes where JSON expected
NaN
Infinity
unsupported arbitrary Python object
```

secret detection不是 Phase A generic schema責任，但 tests不可把 credential當示例內容。

---

# 33. A3 — Observation Contracts

最低：

```text
ObservationIntent
ObservationScope
FreshnessPolicy
VerifiedObservationRef
ObservationBinding
ReObservationRequest
```

---

# 34. ObservationIntent

至少：

```text
observation_intent_id
agent_run_id
goal_ref
plan_ref optional
task_ref optional
world_binding_ref
observation_purpose
requested_scope
preferred_representation
freshness_policy_ref
verification_requirement
intent_digest
```

---

# 35. Freshness Modes

Phase A最低：

```text
IMMUTABLE
SOURCE_REVISION
MAX_AGE
EVENT_INVALIDATED
ALWAYS_RECHECK_BEFORE_MUTATION
```

即使 Phase D 首版只實作部分 mode，contract可以先固定 vocabulary。

---

# 36. VerifiedObservationRef

至少：

```text
observation_ref_id
agent_run_id
observation_intent_ref

projection request/result refs
manifest digest
verification digest
visibility commit ref

source identity
scope digest
projection profile digest
visible_at
observation_digest
```

不要把完整 PNCW manifest塞入 contract。

只引用。

---

# 37. Observation Boundary

contract命名要能清楚阻止：

```text
RawObservation
```

與：

```text
VerifiedObservationRef
```

混用。

如果需要 raw evidence type：

另命名。

不要讓同一 class用：

```text
verified: bool
```

決定它突然變成 canonical VerifiedObservation。

---

# 38. A4 — Action Contracts

最低：

```text
ActionProposal
EffectSet
CapabilityRef
BudgetEnvelope
AdmissionDecision
ActionAdmission
CommandIntent
ActionAttempt
ActuationReceipt
ActionVerification
ReconciliationRecord
```

---

# 39. ActionProposal

最低：

```text
action_id
agent_run_id
agent_run_epoch
goal_ref
plan_ref
task_ref
operation
target_ref
parameters_ref
declared_effects
basis_refs
preconditions
expected_result_ref
rollback_policy_ref
verification_policy_ref
provenance_ref
proposal_digest
```

---

# 40. Effects

Phase A 建立 vocabulary mechanism。

最少能表達：

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

不要一開始建立巨大 registry。

---

# 41. Unknown Effects

contract parser / constructor應 fail closed。

不要：

```text
effect = arbitrary string accepted forever
```

除非使用 versioned extension namespace contract。

---

# 42. CapabilityRef

最低：

```text
capability_id
provider
operation
effect_profile_ref
adapter_version
availability_state
```

availability：

```text
AVAILABLE
UNAVAILABLE
DEGRADED
DISABLED
UNSUPPORTED
```

---

# 43. BudgetEnvelope

至少：

```text
budget_id
agent_run_id
limits
revision
digest
```

limits 初始支援：

```text
provider_calls
currency_cost_usd
wall_clock_seconds
child_agent_count
```

Phase A只固定 representation。

不做 accounting logic。

---

# 44. AdmissionDecision

enum：

```text
ALLOW
ALLOW_WITH_VERIFY
REQUIRE_APPROVAL
DEFER
DENY
ESCALATE
```

---

# 45. ActionAdmission

必須能 bind exact：

```text
action_id
proposal_digest
decision
effective_effects
capability refs
authority digest/revision/epoch
budget digest/revision
world basis digest
policy snapshot digest
admission digest
```

---

# 46. CommandIntent

必須 immutable conceptual record。

至少：

```text
command_intent_id
action_ref
operation
target_ref
parameter_ref
effective_effects
admission_ref
idempotency_ref
verification_policy_ref
command_digest
```

---

# 47. Attempt != Action

`ActionAttempt`：

```text
attempt_id
action_ref
command_ref
provider_ref
state
started_at
...
```

與 Action identity分離。

---

# 48. Receipt

至少：

```text
receipt_id
action_ref
command_ref
attempt_id
provider
provider_operation_id
reported_status
reported_result_ref
observed_cost_ref
duration_ms
receipt_digest
```

---

# 49. Verification

至少：

```text
verification_id
action_ref
verification_kind
basis_refs
verdict
evidence_refs
verifier_ref
verification_digest
```

verdict：

```text
PASSED
FAILED
PARTIAL
DIVERGED
UNKNOWN
STALE
```

---

# 50. ReconciliationRecord

至少：

```text
reconciliation_id
agent_run_id
action_id
classification
evidence_refs
resolved_by
authority_ref
resolved_at
resolution_digest
```

classification：

```text
NOT_EXECUTED
EXECUTED_AS_EXPECTED
EXECUTED_DIFFERENTLY
PARTIALLY_EXECUTED
STATE_UNKNOWN
COMPENSATION_REQUIRED
```

---

# 51. Receipt and Verification Must Be Different Types

禁止設計：

```python
ExecutionResult(success=True, verified=True)
```

把兩個概念揉在同一 primitive。

---

# 52. A5 — Temporal Contracts

最低：

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

# 53. AgentCheckpoint

至少：

```text
checkpoint_id
agent_run_id
agent_run_epoch
state_revision

goal_ref / digest

authority ref/digest/revision/epoch
budget ref/digest/revision

semantic state ref/digest/revision
active plan ref/digest/revision

world basis refs
pending action refs
reconciliation refs

verification state ref
wake condition ref
parent checkpoint ref

created_at
checkpoint_digest
```

---

# 54. No Secret / Process Handle

Checkpoint contract不能設計：

```text
provider_session_blob
raw_secret
open_socket
process_handle
model_kv_cache
```

作 canonical fields。

---

# 55. WakeKind

至少：

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

# 56. WakeCondition

必須 declarative。

不要允許：

```text
callable
lambda
pickle
arbitrary code
```

---

# 57. WakeEvent

至少：

```text
wake_event_id
agent_run_id
wake_condition_ref
source
source_event_ref
received_at
source_event_time optional
deduplication_key
digest
```

---

# 58. ResumeRecord

Phase A contract至少記：

```text
agent_run_id
checkpoint_ref
wake_event_ref
previous_epoch
new_epoch
authority_binding
budget_binding
fresh_observation_refs
invalidated_plan_refs
resumed_at
resume_digest
```

不實作 resume engine。

---

# 59. TemporalLease

至少可以表達：

```text
lease_id
agent_run_id
owner_id
epoch
fencing_token
acquired_at
expires_at
```

---

# 60. A6 — Cross-Contract Rules

這是本輪非常重要的部分。

不是只讓每個 dataclass自己 parse。

要寫 tests證明 object之間不能被錯用。

---

# 61. Cross Contract — AgentRun vs Invocation

測試：

```text
agent_run_id
```

不能被當成：

```text
DispatchContext.run_id
```

的型別/constructor shortcut。

不必建立 Python nominal type system，但 API naming不得鼓勵混用。

---

# 62. Goal vs Authority

Goal contract不得有：

```text
authorized = true
```

這類隱含執行權欄位。

---

# 63. Semantic Node vs Authority

SemanticNode：

```text
node_type = decision
payload = "allow"
```

不能被 constructor/helper轉成 AuthorizationReference。

---

# 64. Observation vs Verification

ObservationIntent不能：

```text
verified=true
```

直接成 VerifiedObservationRef。

兩者必須不同 constructor/path。

---

# 65. ActionProposal vs Admission

ActionProposal不得有：

```text
authorized=true
```

欄位。

---

# 66. Admission vs Dispatch

ActionAdmission不得包含：

```text
provider_call_completed=true
```

等 execution state。

---

# 67. Receipt vs Verification

兩者 separate schemas/types/tests。

---

# 68. Wake vs Resume

WakeEvent不能同時包含：

```text
state=ACTIVE
```

這種 implicit transition。

---

# 69. Checkpoint vs Authority

Checkpoint只能保存 authority reference/history binding。

不能直接是 authority source。

---

# 70. Reconciliation STATE_UNKNOWN

contract必須能完整表示：

```text
STATE_UNKNOWN
```

不能只有：

```text
success
failure
```

二元模型。

---

# 71. Serialization

所有 contracts至少提供：

```text
to_public_dict()
```

或專案現行相容 serialization方式。

要求：

- JSON-compatible；
- bounded；
- deterministic semantic fields；
- no secret-bearing repr；
- no arbitrary Python object。

---

# 72. Dataclass / Enum Style

優先遵守 MACR 現行：

```text
frozen dataclass
Enum
__post_init__ validation
to_public_dict()
```

風格。

不要突然引入 Pydantic 作整個新 Agent contract系統，除非 repo本來已有 canonical reason。

目前不應新增此依賴。

---

# 73. Error Style

優先重用：

```text
MacrError
ValueError
```

與現有專案 error pattern。

Phase A 不需要建立 50 個 exception classes。

但至少可以新增 bounded：

```text
AgentContractError
SemanticContractError
ObservationContractError
ActionContractError
TemporalContractError
```

如果 source style適合。

---

# 74. Test Framework

目前 repository主要使用：

```text
unittest
```

Phase A 繼續沿用。

不要為 Agent引入 pytest mandatory dependency。

---

# 75. Required Test Files

至少：

```text
tests/test_agent_contracts.py
tests/test_semantic_contracts.py
tests/test_observation_contracts.py
tests/test_action_contracts.py
tests/test_temporal_contracts.py
```

若 cross-contract tests較多：

```text
tests/test_agent_contract_boundaries.py
```

---

# 76. Minimum Agent Contract Tests

至少：

```text
AR-C01 valid AgentRun header
AR-C02 invalid AgentRun UUID
AR-C03 invalid state
AR-C04 invalid revision
AR-C05 invalid epoch
AR-C06 deterministic subject digest
AR-C07 same subject / different occurrence IDs
AR-C08 terminal helper
```

---

# 77. Minimum Semantic Tests

```text
ASE-C01 valid node
ASE-C02 unknown node type
ASE-C03 valid relation
ASE-C04 unknown relation
ASE-C05 content digest stable
ASE-C06 provenance changes record digest
ASE-C07 NaN rejected
ASE-C08 arbitrary object rejected
ASE-C09 semantic patch digest
ASE-C10 stale graph represented without mutation logic
```

---

# 78. Minimum Observation Tests

```text
OBS-C01 valid intent
OBS-C02 invalid scope
OBS-C03 valid freshness policy
OBS-C04 unknown freshness mode
OBS-C05 valid VerifiedObservationRef
OBS-C06 invalid verification digest
OBS-C07 invalid source revision
OBS-C08 raw intent cannot be mistaken for verified ref
```

---

# 79. Minimum Action Tests

```text
ACT-C01 valid ActionProposal
ACT-C02 unknown effect
ACT-C03 valid CapabilityRef
ACT-C04 valid BudgetEnvelope
ACT-C05 invalid budget
ACT-C06 AdmissionDecision enum
ACT-C07 valid Admission
ACT-C08 valid CommandIntent
ACT-C09 Action != Attempt identity
ACT-C10 Receipt != Verification type
ACT-C11 reconciliation STATE_UNKNOWN
ACT-C12 invalid reconciliation classification
```

---

# 80. Minimum Temporal Tests

```text
TMP-C01 valid checkpoint
TMP-C02 invalid checkpoint digest
TMP-C03 invalid parent ref
TMP-C04 valid wake condition
TMP-C05 unknown wake kind
TMP-C06 callable predicate rejected
TMP-C07 valid wake event
TMP-C08 dedup key required
TMP-C09 valid TemporalLease
TMP-C10 invalid lease epoch
TMP-C11 valid ResumeRecord
```

---

# 81. Required Negative Controls

至少：

```text
NC-A01 ActionProposal tries authorized=true
NC-A02 Semantic decision tries to become authority
NC-A03 Receipt used where Verification required
NC-A04 WakeEvent tries to encode ACTIVE transition
NC-A05 Checkpoint contains arbitrary runtime handle
NC-A06 Unknown effect accepted
NC-A07 Unknown enum silently accepted
NC-A08 NaN/Infinity canonical payload
NC-A09 unbounded arbitrary Python object payload
NC-A10 same semantic content different key order changes digest
```

---

# 82. Existing Regression

完成 Phase A 新 tests後：

先跑 focused tests。

再跑：

```powershell
.\scripts\verify.ps1
```

若合理，再跑：

```powershell
.\scripts\verify-v06.ps1
```

或等價完整 inherited gate。

---

# 83. Offline Rule

本輪：

```text
network activity = 0
provider generation = 0
```

Phase A 沒有任何理由需要 live API。

不得呼叫：

```text
Grok
GLM
MiniMax
Google
OpenRouter
```

等 live provider。

---

# 84. Runtime State Rule

依 repository instruction：

```text
MACR_STATE_ROOT
```

預設使用 D drive。

Tests必須使用 isolated test temp。

不得把：

```text
sqlite
cache
log
checkpoint
test state
```

寫進 repo tree。

---

# 85. AGENTS.md Caveat

必須讀 `AGENTS.md`。

但目前其中 provider availability敘述可能含歷史性內容。

本輪 Phase A 不涉及 live providers，所以：

> 不要順便修 provider policy。

只遵守其仍有效的 workspace/security invariants：

```text
D-drive state
no committed credentials
offline default tests
candidate != verification != acceptance
append-only evidence
provider formats behind adapters
```

provider availability reconciliation留給後續 documentation closure。

---

# 86. Phase A Explicit Non-Goals

本輪禁止實作：

```text
AgentRunner
Agent loop
Planner
semantic DB
semantic graph persistence
PNCW live integration
PHOSPHOR live integration
action execution
provider dispatch through Agent
checkpoint database
scheduler
suspend
wake
resume
reconciliation runtime
Multi-Agent
sub-agent
browser
sandbox
SEDB adapter
EML-U runtime
```

---

# 87. Do Not Overbuild

如果 contract需要 5000 行 runtime才可測：

設計過頭了。

Phase A 應該主要是：

```text
types
validation
serialization
digest
cross-contract invariants
tests
```

---

# 88. Expected Source Size

不設 hard LOC limit。

但應保持：

> **contract-first、low-dependency、low-side-effect。**

---

# 89. Phase A Evidence

完成後新增：

```text
docs/checkpoints/v07/PHASE_A_AGENT_CONTRACT_KERNEL.md
```

若 `docs/checkpoints/v07/` 不存在：

建立。

---

# 90. Checkpoint Contents

必須包含：

```text
baseline commit
candidate commit
branch
files changed
contracts implemented
tests added
focused test result
inherited regression result
network activity
provider generation
known deferred items
Phase A verdict
```

---

# 91. Phase A Machine Evidence

如果 repo既有 evidence模式適合，可新增：

```text
artifacts/v0.7.0a1/phase-a-contract-kernel.json
```

但不要為了這個提前建立龐大 artifact framework。

---

# 92. Phase A Gate

正式 PASS：

$$
\boxed{
ContractKernelValid
\land
CanonicalDigestStable
\land
CrossContractBoundariesPass
\land
InheritedRegressionPass
\land
OfflineInvariantPass
}
$$

---

# 93. Hard Failure Conditions

任何：

```text
existing MACR identity regression
existing authority regression
live network activity
credential leakage
unknown effect accepted silently
receipt/verification collapse
ActionProposal carries execution authority
checkpoint becomes authority source
semantic text generates AuthorizationReference
repo runtime-state pollution
```

都使 Phase A：

```text
FAIL
```

---

# 94. Phase A Definition of Done

本輪完成時應具備：

### Source

```text
agent/contracts
semantic/contracts
observation/contracts
action/contracts
temporal/contracts
```

### Tests

```text
focused contract tests
cross-boundary negative controls
inherited regression
```

### Evidence

```text
Phase A checkpoint
```

### No Runtime Claim

不得宣稱：

```text
Agent Runtime implemented
Autonomous Agent implemented
v0.7.0a1 completed
```

---

# 95. Correct Maturity Claim

Phase A 完成後只能稱：

> **MACR v0.7 Phase A — Agent Contract Kernel: IMPLEMENTED / VALIDATED**

而：

```text
AgentRun Runtime
Semantic State Runtime
Observation Runtime
Action Runtime
Temporal Runtime
```

仍：

```text
PLANNED
```

---

# 96. Phase B Is Explicitly Deferred

Phase A完成後：

停止。

不要順手開始：

# **Phase B — AgentRun State Kernel**

除非收到下一輪明確指令。

---

# 97. Required Final Report

完成後回報：

```text
1. Branch
2. Baseline commit
3. Candidate commit
4. Files added
5. Files modified
6. Contracts implemented
7. Tests added
8. Focused test results
9. Full inherited regression
10. Network/provider activity
11. Known gaps
12. Phase A verdict
13. Exact next step
```

---

# 98. No Planning-Only Completion

本輪最重要規則：

> **不要只寫 implementation plan 然後把 Phase A 標成完成。**

必須真的：

```text
write source
write tests
run tests
fix failures
rerun
produce evidence
```

---

# 99. No Version Bump Before Evidence

不要一開始：

```text
0.6.0a1 → 0.7.0a1
```

然後才開始寫 contracts。

version bump只有在相應 release boundary真的達成時進行。

Phase A checkpoint本身不需要改 project version。

---

# 100. Canonical Engineering Sequence

本輪實際執行順序：

```text
1. Inspect current main / branch / worktree
2. Read repository instructions
3. Inspect canonical / contracts / authority / execution styles
4. Inspect current tests and verification wrappers
5. Write Phase A focused tests first or alongside contracts
6. Implement AgentRun contracts
7. Implement ASE contracts
8. Implement Observation contracts
9. Implement Action contracts
10. Implement Temporal contracts
11. Add cross-contract negative controls
12. Run focused tests
13. Fix
14. Run inherited verification
15. Check offline/network invariants
16. Check repo cleanliness
17. Write Phase A checkpoint
18. Stop
```

---

# 101. Final Engineering Principle

Phase A 的目的不是產生大量 dataclasses。

而是第一次把：

$$
\boxed{
Agent
}
$$

從自然語言概念變成 MACR 能夠 machine-validate 的 bounded contracts。

完成後，MACR 應第一次可以在沒有真正 Agent loop 的情況下精確表示：

```text
這是哪一個 AgentRun？
它的 Goal 是什麼？
它引用哪個 Authority？
它有哪些 Budget？
它需要什麼 Observation？
它提出了什麼 Action？
該 Action 有哪些 Effects？
Runtime 做了什麼 Decision？
Provider 回了什麼 Receipt？
Verification 判斷了什麼？
它可以等待哪個 WakeCondition？
Checkpoint 保存的是什麼？
如果 outcome 不確定，Reconciliation 該如何表示？
```

而且所有答案都不能依賴：

```text
"看聊天記錄大概知道"
```

必須由 typed canonical contract直接回答。

---

# 102. Phase A Closure

只有在以下成立時才能交付：

$$
\boxed{
\begin{aligned}
&AgentRunContracts\\
+&SemanticContracts\\
+&ObservationContracts\\
+&ActionContracts\\
+&TemporalContracts\\
+&CanonicalIdentity\\
+&NegativeControls\\
+&InheritedRegression
\end{aligned}
=
PASS
}
$$

這是 MACR v0.7 正式從 architecture 進入 executable engineering 的第一步。

**Do not redesign. Build it. Test it. Stop at Phase A.**