# SEDB vNext — Agent / World State Adaptation Proposal v0.1

## Generalized Evolving Object Layer、MACR/ASE 映射與既有 Dynamic Field Kernel 相容升級提案 v0.1

**Document ID:** `SEDB-VNEXT-AWSA-2026-v0.1`  
**Related Architecture:** `MACR-ASR-CCA-2026-v0.1`  
**Related Semantic Contract:** `MACR-V07-ASE-2026-v0.1`  
**Related Agent Runtime:** MACR v0.7.x  
**Baseline:** SEDB v0.4B — Reflexive Autonomous Canonical Commit Kernel  
**Date:** 2026-08-30  
**Status:** Canonical Adaptation Proposal / Pre-Implementation  
**Organization:** EveMissLab / 一言諾科技有限公司  
**Language:** Traditional Chinese

---

# 摘要

SEDB 目前最成熟的工程核心仍是：

> **AI-Native Unbounded Dynamic Field System**

其基本資料模型為：

$$
V:E\times F\rightarrow D_f\cup\{\varnothing\}
$$

並以 sparse cells 保存：

$$
C=
\{
(e,f,v)
\mid
V(e,f)\neq\varnothing
\}
$$

這套架構本身不應被推翻。

因為它解決的是一個非常實際、且圖資料模型不能自然取代的問題：

> 一個 AI-native database 如何允許數千、數萬甚至更多 logical fields 存在，同時不要求每個 entity 都 materialize 所有欄位。

但隨 MACR v0.7 Agent-Spacetime Runtime 開始形成，SEDB 所需要保存的東西已經不只：

```text
Entity
Field
Cell
Field Proposal
Field Evaluation
Field Lifecycle
```

還可能包括：

```text
World Object
Relation
State
Event
Claim
Observation
Decision
Receipt
Verification
Provenance
Lifecycle
```

因此 vNext 的正確方向不是：

```text
SEDB Field Database
→ Rewrite as Graph Database
```

而是：

$$
\boxed{
\mathrm{SEDB}_{vNext}
=
\mathrm{ExistingDynamicFieldKernel}
+
\mathrm{GeneralizedEvolvingObjectLayer}
}
$$

本文件將新增邏輯層稱為：

> **GEOL — Generalized Evolving Object Layer**

GEOL 不是新的獨立產品，也不是另一個 database。

它是 SEDB 內部的一個 general semantic/evolution abstraction，使 Field 從「SEDB 唯一演化主體」提升為「其中一種 first-class evolving object」。

因此：

$$
\boxed{
Field
\in
EvolvingObject
}
$$

而不是：

$$
\boxed{
EvolvingObject
=
Field
}
$$

---

# 0. Canonical Decision

SEDB vNext 採：

```text
Existing Sparse Field Layer
            +
Generalized Evolving Object Layer
            +
Existing Governance / Autonomy Kernel
            +
MACR / ASE Adapter
```

而不是重新開始一套資料庫。

---

# 1. Why vNext Is an Extension, Not a Pivot

SEDB 原來已經隱含三個方向：

### 1.1 Data Evolves

Value 不是唯一重要內容。

還要知道：

```text
where it came from
why it changed
who changed it
what evidence supported it
```

---

### 1.2 Schema Evolves

Field 本身有：

```text
proposal
creation
evaluation
merge
split
convergence
reactivation
deprecation
```

---

### 1.3 Governance Evolves

v0.4B 已經進一步讓：

```text
Decision
Commit
Authority
Effect
Rollback
Receipt
```

成為 first-class governance state。

因此自然的下一步就是：

> **把「演化」從 Field 專用模型抽成所有重要 semantic objects 都能共用的 substrate。**

---

# 2. vNext Non-Goals

vNext 不做：

```text
rewrite SEDB as Neo4j
replace SQLite immediately
delete current fields/cells schema
move MACR scheduler state into SEDB
store every Agent thought
store hidden chain-of-thought
become a generic vector database
become the authority root for all systems
replace PNCW
replace PHOSPHOR
replace LIMEN
```

---

# 3. Core Boundary

SEDB vNext 的 canonical responsibility：

> **保存可持續演化、可查詢、可追溯、具 provenance 與 lifecycle 的 semantic/world state。**

不是：

> 管理 Agent process 本身。

所以：

$$
\boxed{
\mathrm{SEDBState}
\neq
\mathrm{MACRAgentRunState}
}
$$

---

# 4. Runtime State vs Evolving State

MACR 保存：

```text
ACTIVE / SUSPENDED / WAKING
runtime lease
fencing token
active owner
scheduler state
pending process
current invocation
```

SEDB 適合保存：

```text
observed object
world distinction
claim
verified knowledge
decision
receipt
state evolution
relation
provenance
lifecycle
```

---

# 5. Target Logical Model

定義：

$$
\mathcal S_{\mathrm{SEDB}}
=
(
\Omega,
\mathcal R,
\mathcal S,
\mathcal E,
\mathcal C,
\mathcal O,
\mathcal D,
\mathcal Q,
\mathcal P,
\mathcal L,
\mathcal F
)
$$

其中：

- $\Omega$：Objects；
- $\mathcal R$：Relations；
- $\mathcal S$：Versioned States；
- $\mathcal E$：Events；
- $\mathcal C$：Claims；
- $\mathcal O$：Observations；
- $\mathcal D$：Decisions；
- $\mathcal Q$：Receipts；
- $\mathcal P$：Provenance；
- $\mathcal L$：Lifecycle；
- $\mathcal F$：Existing Dynamic Field Layer。

---

# 6. Generalized Evolving Object

一個 object：

$$
o_i
=
(
id,
type,
scope,
identity,
lifecycle,
currentState,
provenance
)
$$

最低 schema：

```json
{
  "schema": "sedb-object/v1",
  "object_id": "obj:...",
  "object_type": "world_object",
  "scope_ref": "scope:...",
  "identity_ref": "identity:...",
  "lifecycle_state": "ACTIVE",
  "current_state_ref": "state:...",
  "provenance_ref": "prov:...",
  "created_at": "...",
  "object_digest": "sha256:..."
}
```

---

# 7. Object Type Registry

vNext 最低核心：

```text
entity
field
world_object
semantic_artifact
claim
observation
decision
receipt
verification
policy_object
external_resource
```

可後續擴：

```text
goal
project
agent_reference
dataset
workspace
software_domain
document
event_source
```

---

# 8. Field Remains a Native Object Type

現行：

```text
field_registry
```

不刪除。

而是建立：

```text
field
→ GEOL object identity
```

因此：

$$
\boxed{
\mathrm{FieldRegistry}
\neq
\mathrm{Deprecated}
}
$$

---

# 9. Why Not Put All Fields into Generic JSON Objects

因為目前 Field Layer 有專門的：

```text
sparse values
field utility
field lifecycle
families
proposal deduplication
task-local views
large field-space operations
```

把這些全部改成 generic object payload：

反而失去現有工程優勢。

---

# 10. Dual Representation Principle

因此：

```text
Generic Object Identity
          ↓
Domain-Specialized Storage
```

例如：

```text
object_type = field
→ field_registry

object_type = entity
→ entities

object_type = claim
→ claims

object_type = observation
→ observations
```

---

# 11. Object Registry

新增：

```text
object_registry
```

主要負責：

```text
global semantic identity
object type
scope
lifecycle
current version
specialized storage binding
```

---

# 12. Specialized Storage Binding

例如：

```json
{
  "object_id": "obj:field:123",
  "object_type": "field",
  "storage_kind": "field_registry",
  "storage_ref": "field:123"
}
```

---

# 13. Relation

Relation：

$$
r=
(
id,
source,
type,
target,
qualifiers,
provenance
)
$$

---

# 14. Core Relation Types

```text
describes
depends_on
derived_from
observes
supports
contradicts
constrains
supersedes
revises
causes
precedes
belongs_to
projects
verifies
refutes
produced
targets
affected_by
merged_into
split_from
```

---

# 15. Relation Is Not Authority

SEDB 可以保存：

```text
decision authorizes action
```

作 historical relation。

但：

$$
\boxed{
StoredRelation(authorizes)
\neq
LiveAuthority
}
$$

真正 authority仍由 authority subsystem resolve。

---

# 16. Versioned State

任何 evolving object可以有：

```text
state v1
state v2
state v3
```

不直接 overwrite。

---

# 17. Object State

```json
{
  "schema": "sedb-object-state/v1",
  "state_id": "state:...",
  "object_id": "obj:...",
  "revision": 4,
  "payload_ref": "artifact:...",
  "basis_refs": [],
  "status": "CURRENT",
  "created_at": "...",
  "state_digest": "sha256:..."
}
```

---

# 18. State Append Rule

$$
S_{n+1}
\neq
overwrite(S_n)
$$

而是：

$$
S_n
\rightarrow
S_{n+1}
$$

---

# 19. Event

Event 表示：

> Object / relation / semantic state 的某個 transition 曾發生。

---

# 20. Event Schema

```json
{
  "schema": "sedb-event/v1",
  "event_id": "evt:...",
  "event_type": "object.state_changed",
  "subject_refs": [],
  "before_refs": [],
  "after_refs": [],
  "causal_refs": [],
  "provenance_ref": "prov:...",
  "occurred_at": "...",
  "event_digest": "sha256:..."
}
```

---

# 21. Current State vs History

$$
\boxed{
CurrentState
\neq
EventHistory
}
$$

Current projection可重建。

History不可因 current state更新而消失。

---

# 22. Claim

Claim 是：

> 可被支持、反駁、驗證、失效或 supersede 的 semantic proposition。

---

# 23. Claim Schema

```json
{
  "schema": "sedb-claim/v1",
  "claim_id": "claim:...",
  "subject_ref": "obj:...",
  "predicate": "...",
  "object_ref": "...",
  "statement_ref": "...",
  "epistemic_status": "PROPOSED",
  "confidence": null,
  "scope_ref": "...",
  "provenance_ref": "...",
  "claim_digest": "sha256:..."
}
```

---

# 24. Claim Status

```text
PROPOSED
SUPPORTED
CONTESTED
VERIFIED
REFUTED
STALE
SUPERSEDED
```

---

# 25. Confidence != Truth

$$
\boxed{
Confidence
\neq
Verification
}
$$

---

# 26. Observation

Observation 保存：

> Observer 在特定 scope / time / projection 下取得的 evidence-bearing world state。

---

# 27. Observation Schema

```json
{
  "schema": "sedb-observation/v1",
  "observation_id": "obs:...",
  "subject_ref": "obj:...",
  "observer_ref": "...",
  "source_ref": "...",
  "projection_ref": "...",
  "source_revision": "...",
  "scope_ref": "...",
  "observed_at": "...",
  "verification_ref": "...",
  "content_ref": "...",
  "provenance_ref": "...",
  "observation_digest": "sha256:..."
}
```

---

# 28. Observation != Claim

例如：

```text
Observation:
test output = FAIL

Claim:
parser implementation causes the failure
```

兩者不能折疊。

---

# 29. Observation != Current World

$$
\boxed{
Observation_t
\neq
World_{now}
}
$$

SEDB 要能將 Observation 標為：

```text
CURRENT
STALE
HISTORICAL
```

但不刪除。

---

# 30. Decision

v0.4B 已經有 Decision Receipt。

vNext 不重新發明。

而是把 Decision Receipt提升為通用 object/evolution layer可引用的 first-class record。

---

# 31. Decision Semantics

$$
\boxed{
Decision
\neq
Commit
}
$$

永久保留。

---

# 32. Decision Can Target More Than Fields

現行 action較集中：

```text
accept proposal
transition field
update definition
set guardrail
```

vNext未來可以 target：

```text
claim lifecycle
object lifecycle
relation lifecycle
observation classification
world-state update
semantic merge
```

---

# 33. Open-World Authority Remains

v0.4B的重要 invariant：

$$
\boxed{
NovelAction
\not\Rightarrow
Unauthorized
}
$$

仍保留。

---

# 34. Capability Still Separate

$$
\boxed{
Capability
\neq
Authority
}
$$

一個 generic object action可以 authority-valid，但 adapter尚未實作。

結果：

```text
CAPABILITY_MISSING
```

---

# 35. Receipt

Receipt 泛化成：

> 某 execution / provider / commit subsystem 報告的已發生操作記錄。

---

# 36. Receipt Types

```text
decision_receipt
commit_receipt
provider_receipt
rollback_receipt
compensation_receipt
verification_receipt
external_receipt
```

---

# 37. Receipt != Verification

$$
\boxed{
Receipt
\neq
Truth
}
$$

---

# 38. Verification

Verification 可以 target：

```text
claim
observation
commit
world state
action result
object state
```

---

# 39. Verification Record

```json
{
  "schema": "sedb-verification/v1",
  "verification_id": "verify:...",
  "subject_ref": "...",
  "verdict": "PASSED",
  "basis_refs": [],
  "verifier_ref": "...",
  "policy_ref": "...",
  "created_at": "...",
  "verification_digest": "sha256:..."
}
```

---

# 40. Provenance

SEDB原本就非常強調：

```text
where
why
how
who
```

vNext將 provenance變成所有 GEOL record的共同 contract。

---

# 41. Provenance Minimum

```text
origin kind
origin ref
source refs
derivation refs
actor ref
time
scope
```

---

# 42. Provenance Does Not Equal Trust

$$
\boxed{
KnownOrigin
\neq
VerifiedTruth
}
$$

---

# 43. Lifecycle

Generic object lifecycle最低：

```text
PROPOSED
ACTIVE
STALE
SUPERSEDED
CONVERGED
MERGED
SPLIT
DEPRECATED
ARCHIVED
```

---

# 44. Domain-Specific Lifecycle

不是所有 object都必須使用全部 states。

例如 Field：

```text
Proposed
Active
Converged
Reactivated
Merged
Split
Deprecated
```

繼續用現有 specialization。

---

# 45. Claim Lifecycle

```text
PROPOSED
SUPPORTED
CONTESTED
VERIFIED
REFUTED
STALE
SUPERSEDED
```

---

# 46. Observation Lifecycle

```text
CURRENT
STALE
SUPERSEDED
ARCHIVED
```

---

# 47. Lifecycle Registry

允許：

```text
object_type
→ allowed lifecycle transitions
```

---

# 48. Illegal Transition

例如：

```text
ARCHIVED → ACTIVE
```

若該 object type不允許：

fail closed。

---

# 49. Fields as Specialized Objects

SEDB vNext的關鍵不是：

```text
Fields disappear.
```

而是：

```text
Field becomes one member of a larger ontology.
```

---

# 50. Existing Field Equation Remains

$$
V:E\times F
\rightarrow
D_f\cup\{\varnothing\}
$$

完全保留。

---

# 51. Existing Cells Remain Sparse

$$
C=
\{
(e,f,v)
|
V(e,f)\neq\varnothing
\}
$$

亦保留。

---

# 52. Do Not Convert Every Cell to a Graph Edge

這一點應成為 hard engineering rule。

因為：

```text
10,000 fields
×
many entities
```

若全部變成 generic relation rows：

可能造成不必要的 storage/query成本。

---

# 53. Sparse Field Kernel Owns Cell Storage

GEOL負責：

```text
identity
relation
history
semantic lifecycle
```

Field Kernel負責：

```text
high-density sparse values
```

---

# 54. Entity

現有 `entities`同樣映射為：

```text
object_type = entity
```

但不要求搬資料。

---

# 55. Backward Compatibility

vNext第一階段：

```text
existing entities
existing fields
existing cells
```

全部保持可用。

---

# 56. Existing APIs

現行 Field API不應因 GEOL加入而立即 breaking change。

---

# 57. New Object API

新增：

```text
GET  /api/objects/{id}
GET  /api/objects/{id}/states
GET  /api/objects/{id}/events
GET  /api/objects/{id}/relations

POST /api/objects
POST /api/relations
POST /api/claims
POST /api/observations
```

---

# 58. Governed Mutation API

canonical mutation仍應走：

```text
proposal
→ decision
→ commit
```

而不是 generic：

```text
PUT /object
```

直接改 canonical state。

---

# 59. Proposed Generic Governance Flow

```text
Observe
↓
Proposal
↓
Effect Classification
↓
Authority
↓
Self-Constraint
↓
Decision Receipt
↓
Basis Revalidation
↓
Commit
↓
Commit Receipt
↓
Verification / Observation
```

---

# 60. This Reuses v0.4B

不新增第二套 autonomy kernel。

---

# 61. Existing Autonomy Kernel Becomes Generic

目前 effect classifier主要服務 SEDB field/governance actions。

vNext將 target abstract成：

```text
ObjectMutationProposal
```

---

# 62. ObjectMutationProposal

```json
{
  "schema": "sedb-object-mutation-proposal/v1",
  "proposal_id": "...",
  "subject_ref": "obj:...",
  "operation": "claim.supersede",
  "declared_effects": [],
  "basis_refs": [],
  "expected_state_ref": "...",
  "provenance_ref": "...",
  "proposal_digest": "..."
}
```

---

# 63. Effect-Oriented Authority Remains

Authority判斷基於：

```text
effect properties
target scope
authority envelope
```

而不是：

```text
adapter function name
```

---

# 64. Commit-Time Basis Revalidation Remains

如果：

$$
Basis_{decision}
\neq
Basis_{commit}
$$

必須：

```text
STALE_BASIS
```

拒絕 canonical mutation。

---

# 65. Decision Receipt Remains Immutable

後續 rollback不修改 Decision Receipt。

---

# 66. Commit Receipt Remains Immutable

同理。

---

# 67. Rollback

現有 SEDB採 compensating rollback。

vNext維持：

$$
\boxed{
Rollback
\neq
DeleteHistory
}
$$

---

# 68. Generic Compensation

例如 claim錯誤提交：

```text
claim VERIFIED
```

後續發現錯：

不刪除歷史。

新增：

```text
verification refuted
claim REFUTED / SUPERSEDED
```

---

# 69. Relation Compensation

錯誤 relation：

不一定直接 delete。

可以：

```text
relation state = superseded
```

保留 historical evidence。

---

# 70. Object Merge

若兩 object 後來認定為同一 semantic object：

```text
A
B
↓
Merge Decision
↓
canonical successor C
```

---

# 71. Merge Does Not Erase A/B

建立：

```text
A merged_into C
B merged_into C
```

---

# 72. Split

同樣：

```text
A
↓
B + C
```

A仍為歷史 identity。

---

# 73. MACR Integration Principle

MACR 不把全部 Agent semantic graph都自動 dump進 SEDB。

需要：

```text
PersistencePolicy
```

---

# 74. Why

MACR semantic graph內可能有大量：

```text
temporary plan
temporary hypothesis
rejected action
short-lived task
```

不一定值得成為 long-term evolving knowledge。

---

# 75. Persistence Classes

建議：

```text
ALWAYS
CONDITIONAL
REFERENCE_ONLY
EPHEMERAL
FORBIDDEN
```

---

# 76. ALWAYS

適合：

```text
verified world observation reference
important decision receipt
canonical commit receipt
verification result
provenance
stable world object lifecycle event
```

---

# 77. CONDITIONAL

例如：

```text
claim
hypothesis
goal
failure
plan
```

依 project / policy決定。

---

# 78. REFERENCE_ONLY

例如：

```text
MACR checkpoint
AgentRun
external artifact
PNCW manifest
PHOSPHOR receipt
```

SEDB存 identity/ref。

不複製 canonical owning system資料。

---

# 79. EPHEMERAL

例如：

```text
temporary planner candidate
discarded context projection
token-local scratch data
```

預設不進 SEDB。

---

# 80. FORBIDDEN

```text
hidden chain-of-thought
API key
OAuth secret
provider plaintext credential
private memory without access policy
```

---

# 81. ASE → SEDB Mapping

MACR ASE：

```text
Goal
Observation
Claim
Hypothesis
Plan
ActionProposal
Decision
Receipt
Verification
Failure
Checkpoint
```

不全等價映射。

---

# 82. Recommended Mapping

| ASE | SEDB vNext |
|---|---|
| Goal | Conditional semantic object |
| Observation | Observation |
| Claim | Claim |
| Hypothesis | Claim subtype / Conditional |
| Plan | Conditional semantic artifact |
| ActionProposal | Usually reference/history |
| Constraint | Policy/semantic object |
| Decision | Decision Receipt |
| Receipt | Receipt |
| Verification | Verification |
| Failure | Event / conditional object |
| Checkpoint | External reference only |
| WakeCondition | Normally MACR-only |

---

# 83. MACR AgentRun

SEDB可存：

```text
AgentRunRef
```

用於 provenance。

但：

$$
\boxed{
SEDB
\neq
AgentRunStore
}
$$

---

# 84. Agent Identity

同理。

SEDB可以引用：

```text
agent_ref
resident_ref
```

但不負責 resolve persistent identity。

---

# 85. LIMEN Boundary

如果涉及 Resident：

```text
LIMEN / Registry
→ identity envelope
→ MACR
→ SEDB provenance ref
```

SEDB不能根據名字自己推測 Resident identity。

---

# 86. PNCW Integration

PNCW VerifiedObservationRef可映射：

```text
SEDB Observation
```

---

# 87. But PNCW Remains Owner

SEDB保存：

```text
PNCW result ID
manifest digest
verification digest
source identity
```

不把 PNCW canonical manifest重新定義一次。

---

# 88. PHOSPHOR Integration

PHOSPHOR Actuation Receipt：

可保存：

```text
external receipt ref
world transition event
```

---

# 89. Desired / Requested / Realized / Observed

SEDB非常適合長期保存這四者之間的 evolution history。

---

# 90. World Evolution

例如：

```text
Domain rate:
desired 0.5
requested 0.5
realized 0.47
observed 0.46
```

可以成為：

```text
object state
receipt
observation
verification
```

而不是一個扁平 value。

---

# 91. SEDB as World Evolution Ledger

長期定位可以是：

> **semantic world evolution ledger / evolving state substrate**

而不是：

> Agent runtime database。

---

# 92. Double Authority Gate

MACR Agent要 mutate SEDB canonical state：

至少：

$$
Auth_{MACR}
\land
Auth_{SEDB}
$$

---

# 93. Why

MACR回答：

> Agent被授權做什麼？

SEDB回答：

> SEDB canonical domain允許什麼 mutation？

---

# 94. Consensus Still Not Authority

即使多 Agent都同意：

```text
claim should be verified
```

也不能跳過：

```text
SEDB authority / governance
```

---

# 95. Semantic Consensus

可以作：

```text
evidence
recommendation
decision basis
```

不是 authority。

---

# 96. Agent Cannot Expand SEDB Envelope

現有 v0.4B沒有此 endpoint。

vNext必須保留。

---

# 97. Authority-Affecting Object Mutation

如果未來 object本身描述：

```text
policy
authority
guardrail
```

其 mutation應屬特殊 effect class。

不能因 generic object API而降低 protection。

---

# 98. Generic APIs Must Not Create Governance Bypass

禁止：

```text
POST /api/objects
```

直接建立：

```text
authority envelope
guardrail canonical state
```

繞過 governance。

---

# 99. Physical Schema Proposal

新增 tables：

```text
object_registry
object_states
object_relations
object_events
claims
observations
verification_records
object_bindings
```

---

# 100. Reuse Existing Tables

保留：

```text
entities
field_registry
cells
field_events
field_evaluations
field_proposals
views
provenance
search_index
```

---

# 101. Existing Governance Tables

Decision / Commit / autonomy相關 tables亦保留並擴 generic target references。

---

# 102. Object Registry

建議欄位：

```text
object_id
object_type
scope_ref
lifecycle_state
current_state_id
storage_kind
storage_ref
created_at
object_digest
```

---

# 103. Object States

```text
state_id
object_id
revision
payload_ref
basis_digest
status
created_at
state_digest
```

---

# 104. Relations

```text
relation_id
source_object_id
relation_type
target_object_id
qualifier_json
provenance_ref
lifecycle_state
relation_digest
```

---

# 105. Claims

```text
claim_id
object_id
predicate
value/reference
epistemic_status
confidence
scope
provenance
content_digest
record_digest
```

---

# 106. Observations

```text
observation_id
subject_object_id
observer_ref
source_ref
source_revision
projection_ref
scope_ref
observed_at
verification_ref
content_ref
observation_digest
```

---

# 107. Search

Search index擴充：

```text
fields
objects
relations
claims
observations
```

但不要求一次全部重建。

---

# 108. Query Plane

vNext query可以是：

```text
field-centric
entity-centric
object-centric
claim-centric
evolution-centric
```

---

# 109. Existing Task View

保留。

另外可加：

```text
Object View
Evolution View
Evidence View
```

---

# 110. Object View

顯示：

```text
current state
relations
claims
observations
provenance
lifecycle
```

---

# 111. Evolution View

顯示：

```text
state revisions
events
decisions
commits
verification
rollback/compensation
```

---

# 112. Evidence View

顯示：

```text
claims
supporting observations
contradictions
verification
source lineage
```

---

# 113. Task-Local Object Projection

類似現有：

$$
F_Q\subseteq F
$$

vNext新增：

$$
\Omega_Q
\subseteq
\Omega
$$

---

# 114. Active Semantic Support

對 Agent task $Q$：

$$
G_Q
=
(
\Omega_Q,
R_Q,
C_Q,
O_Q
)
$$

只取 relevant subset。

---

# 115. Available != Active

同 Field 理念延續：

$$
\boxed{
AvailableKnowledge
\neq
ActiveTaskContext
}
$$

---

# 116. SEDB Is Not Model Context

SEDB可以存很多。

MACR Context Builder只投影少量。

---

# 117. State Projection

因此：

```text
SEDB
→ task-local semantic projection
→ MACR ASE
→ model context
```

---

# 118. Reverse Flow

Agent產生新 verified evolution：

```text
MACR ASE
→ Persistence Policy
→ SEDB Proposal
→ SEDB Governance
→ Commit
```

---

# 119. No Direct Graph Mirroring

不是：

```text
every ASE node
→ SEDB row
```

---

# 120. Canonical Ownership

同一 artifact只能有明確 canonical owner。

例如：

```text
PNCW manifest → PNCW
AgentRun checkpoint → MACR
Residence identity → Registry/LIMEN
SEDB observation record → SEDB
```

---

# 121. Cross-System References

使用：

```text
external_system
external_schema
external_id
external_digest
```

---

# 122. Object Binding

```json
{
  "schema": "sedb-external-binding/v1",
  "object_id": "obj:...",
  "external_system": "pncw",
  "external_type": "verified_observation",
  "external_id": "...",
  "external_digest": "sha256:..."
}
```

---

# 123. No Silent Copy Ownership

若 import external artifact內容：

必須標：

```text
COPY
PROJECTION
REFERENCE
DERIVED
```

---

# 124. Temporal Semantics

SEDB保存：

```text
occurred_at
observed_at
recorded_at
valid_from
valid_until
```

時需分清。

---

# 125. Observed Time != Recorded Time

$$
\boxed{
ObservedAt
\neq
RecordedAt
}
$$

---

# 126. Historical State

vNext應能回答：

> 在時間 $t$，系統當時認為這個 object 是什麼狀態？

---

# 127. Current Truth vs Historical Belief

這兩者都重要。

---

# 128. Epistemic Evolution

例如：

```text
t1 claim proposed
t2 supported
t3 verified
t4 contradicted
t5 refuted
```

這就是 SEDB 原本「Why did knowledge become what it is now?」的自然泛化。

---

# 129. Event Causality

relation可記：

```text
event B caused_by event A
```

但：

$$
TemporalOrder
\neq
CausalProof
$$

---

# 130. MACR Causal Trace

Agent action closure：

```text
Observation
→ Decision
→ Commit/Action
→ Receipt
→ ReObservation
→ Verification
```

可投影為 SEDB evolution chain。

---

# 131. Provenance Compression

SEDB可以保存 digest/ref而非 raw large artifact。

---

# 132. Large Payload Rule

以下不直接塞 generic SQLite JSON：

```text
large model output
image
video
huge manifest
repository archive
```

使用 content refs。

---

# 133. Private Data

GEOL新增 object abstraction不能成為 private-data bypass。

---

# 134. Private Object

需要：

```text
access_class
scope
authority domain
```

或外部 private store reference。

---

# 135. Residence Memory

仍不直接搬進 SEDB public/general store。

---

# 136. Self-Constraint

v0.4B：

```text
VERIFY
COUNTEREXAMPLE
BACKTRACK
COMPARE
STOP
DECOMPOSE
```

繼續可套用 generic object mutations。

---

# 137. Example — Claim Verification

Agent proposes：

```text
claim C → VERIFIED
```

Governance：

```text
effect = epistemic_state_mutation
```

Self-constraint：

```text
VERIFY + COUNTEREXAMPLE
```

Decision。

Commit-time重新驗 evidence basis。

最後才變成 VERIFIED。

---

# 138. Example — Observation Stale

PNCW source revision更新。

SEDB：

```text
Observation O1
CURRENT → STALE
```

不刪除 O1。

---

# 139. Example — Field Evolution

原本完全不變：

```text
Proposed
→ Active
→ Converged
→ Reactivated
```

只是現在可以和更多 objects建立 relation。

---

# 140. Example — World Object

```text
object:
GitHub repository X
```

Relations：

```text
contains field...
observed_by...
affected_by action...
```

---

# 141. Example — Software Domain

PHOSPHOR domain：

```text
object_type = external_resource / software_domain
```

State versions：

```text
ACTIVE
PAUSED
ACTIVE
```

receipts與observations形成 evolution history。

---

# 142. Example — Contradictory Claims

Claim A：

```text
parser caused failure
```

Claim B：

```text
tokenizer caused failure
```

relation：

```text
A contradicts B
```

驗證後：

```text
A VERIFIED
B REFUTED
```

歷史保留。

---

# 143. SEDB Is Not ASE Replacement

ASE是：

> Agent active semantic working state。

SEDB是：

> Long-term evolving semantic/world substrate。

---

# 144. Formal Relationship

$$
ASE_t
\subseteq
Projection(
SEDB,
World,
AgentRun
)
$$

並：

$$
Selected(ASE_{t+1})
\rightarrow
SEDBProposal
$$

---

# 145. Not Every Agent Thought Persists

這是必要 boundary。

---

# 146. Implementation Strategy

不要一次大改 v0.4B。

建議：

```text
Phase O0 — Object Registry
Phase O1 — Versioned Object State
Phase O2 — Relations / Events
Phase O3 — Claims / Observations
Phase O4 — Generic Governance Target
Phase O5 — ASE Adapter
Phase O6 — MACR Integration
Phase O7 — Migration / Validation
```

---

# 147. O0 — Object Registry

只加：

```text
object_registry
object_bindings
```

並讓 existing Entity / Field取得 object identities。

---

# 148. O0 Hard Rule

不搬 existing entity/field data。

---

# 149. O1 — Versioned State

加入：

```text
object_states
```

先對一種 generic object驗證 append-only versioning。

---

# 150. O2 — Relation / Event

加入：

```text
object_relations
object_events
```

---

# 151. O3 — Claim / Observation

建立 first-class：

```text
claims
observations
verification_records
```

---

# 152. O4 — Governance Generalization

現有 autonomy kernel target從：

```text
field-centric action
```

泛化：

```text
governed canonical mutation
```

---

# 153. O4 Must Preserve Existing Tests

189 v0.4B tests與後續新增 inherited regression全部要通過。

---

# 154. O5 — ASE Adapter

建立：

```text
ASEPersistencePort
```

---

# 155. Adapter Operations

```text
persist_observation()
persist_claim()
persist_decision_ref()
persist_receipt_ref()
persist_verification()
project_task_context()
```

---

# 156. O6 — MACR Integration

先使用 fixture AgentRun。

不需要 real model。

---

# 157. O6 Scenario

```text
MACR observes fixture world
→ PNCW-like verified observation
→ ASE node
→ SEDB persist observation
→ claim
→ verification
→ SEDB evolution query
```

---

# 158. O7 — Migration

現有 v0.4B database：

```text
no destructive migration
```

---

# 159. Migration Principle

新增：

```text
object identities
```

給 existing entities / fields。

不更改它們原 primary identity。

---

# 160. Deterministic Legacy Binding

例如：

$$
ObjectID_{field}
=
H(
"sedb-field",
fieldId
)
$$

或明確 versioned UUID mapping。

需固定 migration contract。

---

# 161. Migration Idempotency

同一 DB migration跑兩次：

不得產兩個 object identity。

---

# 162. Backward Query Compatibility

舊：

```text
get field
get entity
get cells
```

仍需正確。

---

# 163. New Query Compatibility

新：

```text
get object
→ resolves specialized field/entity
```

---

# 164. No Dual-Truth

不能出現：

```text
field lifecycle = active
object lifecycle = deprecated
```

卻沒有 reconciliation rule。

---

# 165. Specialized Object Projection

對 field：

canonical lifecycle仍由 Field subsystem擁有。

GEOL object lifecycle是 projection/reference。

---

# 166. Authority of Specialized State

$$
\boxed{
SpecializedDomainCanonicalState
>
GenericProjection
}
$$

Generic layer不能偷偷 overwrite field canonical semantics。

---

# 167. Generic Object Owns Generic Objects

對沒有 specialized store的：

```text
claim
observation
world_object
```

GEOL可以直接 canonical own。

---

# 168. Search Migration

先 incremental indexing。

不要求第一版全庫重算昂貴 semantic index。

---

# 169. Performance

新增 object layer不得讓：

```text
sparse cell read/write
10k-field operations
```

大幅退化。

---

# 170. Performance Gate

至少比較：

```text
v0.4B baseline
vs
vNext object layer enabled
```

對 existing workload。

---

# 171. Object Overhead

需要測：

```text
object registry size
relation count
event growth
claim history growth
```

---

# 172. Compaction

History可以 archive。

但 immutable Decision/Commit receipts不可因 compaction消失。

---

# 173. Archive

後續可：

```text
hot current state
warm history
cold evidence artifacts
```

---

# 174. SEDB / SEDB-RAL Boundary

SEDB vNext仍不是 Resident Authority Ledger。

若 SEDB-RAL是 specialized identity/registry ledger：

不要合併。

---

# 175. Generic Object != Registry Identity

Object可以 reference：

```text
resident_id
```

但不發行 resident identity。

---

# 176. SEDB / LIMEN Boundary

LIMEN負責：

```text
host → identity resolution → access envelope
```

SEDB只接 validated refs。

---

# 177. SEDB / PNCW Boundary

PNCW負責：

```text
verified projection / visibility
```

SEDB負責：

```text
historical semantic persistence
```

---

# 178. SEDB / PHOSPHOR Boundary

PHOSPHOR負責：

```text
temporal/causal actuation runtime
```

SEDB保存：

```text
selected durable world evolution records
```

---

# 179. SEDB / MACR Boundary

MACR：

```text
Agent execution
```

SEDB：

```text
selected evolving knowledge/world state
```

---

# 180. SEDB / EML-U Direction

EML-U未來可定義 generalized semantic IR。

SEDB可以成為其中一個 persistence backend。

但：

$$
\boxed{
SEDB
\neq
EML\text{-}U
}
$$

---

# 181. EML-U Adapter

未來：

```text
EML-U Semantic Node
↔ SEDB Object / Claim / Relation
```

需要 explicit mapping。

---

# 182. No Premature Dependency

vNext不等 EML-U MVP完成。

---

# 183. Canonical Invariants

## S-01

$$
Field\subset EvolvingObject
$$

但 Sparse Field Kernel保持 specialized。

## S-02

$$
AgentRunState\neq SEDBKnowledgeState
$$

## S-03

$$
Observation\neq Claim
$$

## S-04

$$
Decision\neq Commit
$$

## S-05

$$
Capability\neq Authority
$$

## S-06

$$
Consensus\neq Authority
$$

## S-07

$$
Receipt\neq Verification
$$

## S-08

$$
CurrentState\neq History
$$

## S-09

$$
Rollback\neq HistoryDeletion
$$

## S-10

$$
StoredAuthorityRelation\neq LiveAuthority
$$

---

# 184. Further Invariants

## S-11

$$
ExternalReference\neq CanonicalOwnership
$$

## S-12

$$
GenericObjectLayer\neq GraphDatabaseRewrite
$$

## S-13

$$
AvailableKnowledge\neq ActiveContext
$$

## S-14

$$
Confidence\neq Truth
$$

## S-15

$$
ObservedAt\neq RecordedAt
$$

---

# 185. Negative Controls

```text
NC-SDB-01 generic object API bypasses autonomy
NC-SDB-02 relation grants live authority
NC-SDB-03 consensus overrides envelope
NC-SDB-04 Decision Receipt treated Commit Receipt
NC-SDB-05 stale basis commits
NC-SDB-06 rollback deletes immutable history
NC-SDB-07 Field data rewritten into generic JSON
NC-SDB-08 existing cell query regresses
NC-SDB-09 same legacy field gets two object IDs
NC-SDB-10 specialized lifecycle conflicts with generic projection
NC-SDB-11 raw Agent plan automatically persisted as canonical knowledge
NC-SDB-12 hidden CoT persisted
NC-SDB-13 credential persisted
NC-SDB-14 PNCW manifest copied and re-owned silently
NC-SDB-15 AgentRun runtime lease persisted as semantic world state
NC-SDB-16 observation promoted to current after source stale
NC-SDB-17 confidence promoted to VERIFIED
NC-SDB-18 provider receipt promoted to truth
NC-SDB-19 external object ref mutates owner system
NC-SDB-20 claim history destroyed by merge/split
```

---

# 186. Verification Matrix

## Legacy Compatibility

```text
all inherited v0.4B tests
field lifecycle
sparse cells
task-local fields
field proposal
governance
autonomy
rollback
```

全部 PASS。

---

# 187. Object Layer

```text
object identity deterministic/unique
object state append-only
relation integrity
event integrity
lifecycle validation
```

---

# 188. Governance

```text
generic action effect classification
authority envelope
Decision Receipt
basis revalidation
Commit Receipt
capability missing
escalation
```

---

# 189. MACR Adapter

```text
ASE observation persistence
claim persistence
verification persistence
receipt refs
task projection
forbidden transient state rejection
```

---

# 190. Migration

```text
existing DB migrates
migration idempotent
no data loss
old queries work
new object queries work
```

---

# 191. Security

```text
no hidden CoT
no secret
no generic authority bypass
no self-envelope expansion
```

---

# 192. Performance

existing field workload需保持合理範圍。

vNext第一版不要求 graph workload極端優化。

---

# 193. vNext MVP Boundary

第一個真正 implementation不需要一次完成全部。

最低：

```text
Object Registry
Object State
Relation
Event
Claim
Observation
Verification
Legacy Field Binding
Generic Governance Target
ASE Persistence Adapter
```

---

# 194. Deferred

```text
distributed object graph
Postgres migration
vector-native indexing
large-scale graph traversal optimizer
full EML-U backend
Resident private memory backend
multi-region replication
global semantic federation
```

---

# 195. Proposed Source Additions

以現有 package結構，建議 additive：

```text
current/src/sedb/
├─ objects.py
├─ relations.py
├─ observations.py
├─ claims.py
├─ evolution.py
├─ object_governance.py
└─ macr_adapter.py
```

---

# 196. Existing Modules Retained

```text
agent.py
autonomy.py
campaign.py
db.py
entities.py
family.py
fields.py
governance.py
semantic.py
server.py
```

不因 vNext全部重寫。

---

# 197. Likely Integration Points

```text
db.py
→ schema/migration

autonomy.py
→ generic effect/authority path

governance.py
→ lifecycle/governance extension

semantic.py
→ claim/object semantic bridge

entities.py
fields.py
→ legacy object binding

server.py
→ API exposure
```

---

# 198. Engineering Rule

先：

```text
source inspection
```

再決定 exact module split。

本文件的 filenames只是 responsibility map，不是 mandatory implementation layout。

---

# 199. Version Naming

本文件暫不強制：

```text
v0.5A
v0.5
v1.0
```

等 release number。

版本應在 implementation scope真正固定後決定。

---

# 200. Why

這次是 ontology/generalization的重要擴展。

不應只因下一號自然是：

```text
v0.5
```

就先綁死 release meaning。

---

# 201. Recommended Engineering Sequence

```text
1. Legacy schema/source inspection
2. Object registry spike
3. Entity/Field object binding
4. Versioned object state
5. Relations/events
6. Claims/observations
7. Generic autonomy path
8. ASE adapter
9. MACR fixture integration
10. full inherited regression
11. migration validation
12. performance regression
13. checkpoint/release decision
```

---

# 202. First Demonstration

建立：

```text
Entity E
Field F
```

保持 existing sparse cell：

```text
V(E,F)=X
```

同時：

```text
E → object
F → object
```

新增：

```text
Observation O
Claim C
Verification V
```

Relations：

```text
O supports C
C describes E
V verifies C
F describes_dimension_of E
```

並能查：

> 為什麼目前系統認為 C 是成立的？

---

# 203. Second Demonstration

MACR Agent：

```text
VerifiedObservation
→ ASE Claim
→ SEDB Proposal
→ Governance
→ Persist
```

之後第二次 observation推翻：

```text
Claim
VERIFIED → REFUTED
```

歷史完整保存。

---

# 204. Third Demonstration

Novel semantic object action：

authority-valid。

adapter不存在。

應得到：

```text
Decision = EXECUTE
Commit = CAPABILITY_MISSING
```

證明：

$$
Capability\neq Authority
$$

仍成立。

---

# 205. Fourth Demonstration

Agent consensus要求高風險 canonical mutation。

SEDB envelope不允許。

結果：

```text
ESCALATE
```

證明：

$$
Consensus\neq Authority
$$

---

# 206. Fifth Demonstration

Commit後執行 compensating rollback。

必須：

```text
current state restored/compensated
```

同時：

```text
original Decision Receipt remains
original Commit Receipt remains
rollback receipt added
```

---

# 207. Strategic Result

完成後 SEDB 不再只是：

> Dynamic Field Database。

更準確地成為：

> **Semantic Evolution Database with a specialized unbounded dynamic-field kernel and a generalized evolving-object substrate.**

---

# 208. Formal Future Position

$$
\boxed{
\mathrm{SEDB}
=
\mathrm{SparseFieldSystem}
+
\mathrm{SemanticEvolutionLedger}
+
\mathrm{EvolvingObjectSubstrate}
+
\mathrm{GovernedCanonicalMutation}
}
$$

---

# 209. MACR Role

這會使 MACR v0.7 / v0.8 得到一個很自然的 durable semantic/world backend：

```text
AgentRun
↓
ASE
↓
Selected Durable State
↓
SEDB
```

---

# 210. But Dependency Remains Optional

MACR Agent Core第一版不必硬依賴 SEDB。

應透過：

```text
EvolutionStatePort
```

或：

```text
SemanticPersistencePort
```

接入。

---

# 211. Why

避免：

```text
SEDB unavailable
→ Agent cannot exist
```

這種錯誤耦合。

---

# 212. Correct Dependency

$$
\boxed{
MACRAgentRuntime
\not\subset
SEDBRuntime
}
$$

而：

$$
\boxed{
MACR
\xleftrightarrow{Adapter}
SEDB
}
$$

---

# 213. Canonical Closure

本文件固定：

1. SEDB vNext 是 v0.4B 的泛化，不是重寫。
2. Sparse Dynamic Field Kernel保持 canonical。
3. `V:E×F→D_f∪{∅}` 模型保持有效。
4. 不將所有 cells轉成 generic graph edges。
5. 新增 Generalized Evolving Object Layer。
6. Field 成為 evolving object的一種 specialized type。
7. Entity同樣取得 generic object binding。
8. Object、Relation、State、Event、Claim、Observation、Decision、Receipt、Verification、Provenance、Lifecycle成為 general semantic primitives。
9. Generic layer與 specialized field storage採雙層 representation。
10. Specialized domain canonical state優先於 generic projection。
11. Decision != Commit 保留。
12. Capability != Authority 保留。
13. Consensus != Authority 保留。
14. NovelAction不自動等於 Unauthorized。
15. Commit-time basis revalidation保留。
16. Decision Receipt / Commit Receipt保持 immutable。
17. Rollback仍採 compensation，不刪歷史。
18. Observation與Claim分離。
19. Receipt與Verification分離。
20. Confidence與Truth分離。
21. Current State與Historical Event分離。
22. SEDB保存 selected durable Agent/world state，不保存 MACR scheduler internals。
23. MACR AgentRun不搬入 SEDB作 canonical runtime state。
24. ASE不做全量 automatic mirroring。
25. 所有 ASE → SEDB persistence受 Persistence Policy控制。
26. hidden CoT與 credential禁止進 general semantic persistence。
27. PNCW、PHOSPHOR、LIMEN artifacts以 reference/binding方式整合，不奪取其 canonical ownership。
28. MACR mutation SEDB時採 MACR + SEDB雙 authority boundary。
29. Generic Object API不得繞過 existing autonomy kernel。
30. vNext採 additive migration。
31. existing Field/Entity identity與API盡量 backward compatible。
32. legacy object binding必須 deterministic/idempotent。
33. full v0.4B inherited regression必須保持。
34. vNext implementation首先驗 Object Registry，而不是先重寫 UI或 storage engine。
35. EML-U完成度不構成此升級 blocker。
36. SEDB未來可以成為 EML-U-compatible persistence backend，但兩者不是同一系統。
37. MACR對 SEDB保持 adapter-mediated optional dependency。
38. release version號在 engineering scope固定後再決定。

因此：

$$
\boxed{
\mathrm{SEDB}_{vNext}
=
\mathrm{FieldEvolution}
\rightarrow
\mathrm{GeneralSemanticEvolution}
}
$$

但這個箭頭不是取代，而是包含：

$$
\boxed{
\mathrm{GeneralSemanticEvolution}
\supset
\mathrm{FieldEvolution}
}
$$

這使 SEDB 可以從目前非常成功的 Dynamic Field / Governance Kernel，平滑成為 MACR Agent-Spacetime Runtime 未來所需要的 **Evolving Agent / World Semantic-State Substrate**，同時不犧牲它原本已經驗證的 sparse-field engineering。

---

# Appendix A — Logical Stack

```text
┌────────────────────────────────────────────┐
│ MACR / ASE / External Systems              │
└───────────────────┬────────────────────────┘
                    │ Adapter
                    ▼
┌────────────────────────────────────────────┐
│ Generalized Evolving Object Layer          │
│ Object / Relation / State / Event          │
│ Claim / Observation / Verification         │
│ Provenance / Lifecycle                     │
└───────────────────┬────────────────────────┘
                    │
┌────────────────────────────────────────────┐
│ Governance / Autonomy Kernel               │
│ Effect / Authority / Decision / Commit     │
│ Self-Constraint / Rollback / Receipts      │
└───────────────────┬────────────────────────┘
                    │
┌────────────────────────────────────────────┐
│ Specialized Domain Kernels                 │
│ Dynamic Fields / Entities / Families       │
│ Sparse Cells / Views                       │
└───────────────────┬────────────────────────┘
                    │
┌────────────────────────────────────────────┐
│ SQLite / Future Storage Adapters           │
└────────────────────────────────────────────┘
```

---

# Appendix B — Minimum New Tables

```text
object_registry
object_states
object_relations
object_events
claims
observations
verification_records
object_bindings
```

Existing：

```text
entities
field_registry
cells
field_events
field_evaluations
field_proposals
views
provenance
search_index
```

保持。

---

# Appendix C — First MACR Adapter Surface

```text
project_task_state()
persist_observation()
persist_claim()
persist_verification()
persist_decision_reference()
persist_receipt_reference()
query_object_history()
query_evidence_graph()
```

---

# Appendix D — Initial Maturity Claim

在真正工程完成前只能稱：

> **CONCEPT-ADOPTED / INTEGRATION-DIRECTION**

不得宣稱：

> SEDB already implements generalized Agent/world state.

現行 validated claim仍是：

> SEDB v0.4B — Reflexive Autonomous Canonical Commit Kernel over the existing dynamic-field architecture.

---

# Appendix E — Series Closure

至此，MACR v0.7 Canonical Convergence 前置文件鏈已形成：

```text
00 Agent-Spacetime Canonical Convergence Architecture
01 AgentRun Canonical State
02 Agent Semantic Envelope
03 Action / Authority / Effect
04 PNCW Verified Observation Bridge
05 PHOSPHOR Governed Actuation Bridge
06 Checkpoint / Suspend / Wake / Temporal Continuation
07 Single-Agent MVP Implementation Plan
08 Verification & Negative-Control Matrix
09 External Agent Framework Primitive Adoption Matrix
10 SEDB vNext Agent / World State Adaptation Proposal
```

下一階段不應再增加大量平行架構論文。

正式路徑應轉為：

```text
MACR v0.7 Phase A
→ Contract Kernel
→ AgentRun Kernel
→ Semantic State
→ Observation
→ Action
→ Temporal Continuation
→ Closed Loop
→ Failure Injection
→ v0.7.0a1
```

SEDB vNext則可另開獨立 engineering line，不阻塞 MACR v0.7.0a1。