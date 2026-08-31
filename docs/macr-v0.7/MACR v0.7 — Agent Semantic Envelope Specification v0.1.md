# MACR v0.7 — Agent Semantic Envelope Specification v0.1

## Agent 語意封套、語意圖、事件 IR 與 EML-U 相容方向規格 v0.1

**Document ID:** `MACR-V07-ASE-2026-v0.1`  
**Parent Architecture:** `MACR-ASR-CCA-2026-v0.1`  
**Parent State Spec:** `MACR-V07-AGENTRUN-STATE-2026-v0.1`  
**Project:** MACR  
**Target:** MACR v0.7.0 — Bounded Autonomous Agent Core  
**Date:** 2026-08-30  
**Status:** Canonical Semantic Contract / Pre-Implementation  
**Organization:** EveMissLab / 一言諾科技有限公司  
**Language:** Traditional Chinese

---

# 摘要

MACR v0.7 的 Agent 不應只擁有：

```text
system prompt
+
conversation history
+
tool list
```

因為這種表示無法可靠區分：

- 目標；
- 觀察；
- 假設；
- 已知事實；
- 未驗證 claim；
- plan；
- action proposal；
- policy constraint；
- authority evidence；
- provider receipt；
- independent verification；
- checkpoint；
- failure；
- wake condition。

MACR v0.7 因此引入 **Agent Semantic Envelope，ASE**。

ASE 是 MACR 的 provisional canonical semantic layer。

其目的不是創造另一種自然語言，也不是取代 EML-U，而是先定義一個 v0.7.0 可以實作的最小語意契約，使 Agent 的工作狀態可以被：

- 持久化；
- 關聯；
- 驗證；
- 查詢；
- 投影；
- replay；
- 比較；
- supersede；
- 跨模型使用；
- 未來遷移到 EML-U。

因此：

$$
\boxed{
\mathrm{ASE}
\subseteq
\mathrm{EML\text{-}U\ Conceptual\ Semantic\ Space}
}
$$

但：

$$
\boxed{
\mathrm{ASE\ Runtime}
\neq
\mathrm{EML\text{-}U\ Runtime}
}
$$

本規格採用 EML-U 已提出的 semantic-node / relation / policy / provenance / observation 思路，以及 Tree IR、Graph IR、Event IR 三層方向，但把 v0.7.0 所需部分縮成可直接工程化的 bounded subset。EML-U 的形式模型本身已明確包含 Host、Anchor、Semantic Nodes、Relations、Policies、Projection/Adapters、Observations，而 Agent Interface Layer 也被列為原生用途之一。

---

# 0. Canonical Decision

MACR v0.7 將 Agent 的 canonical semantic state 定義為：

$$
\mathcal S_A
=
(N,R,E,P)
$$

其中：

- $N$：Semantic Nodes；
- $R$：Semantic Relations；
- $E$：Semantic Events；
- $P$：Projection / interpretation metadata。

因此 Agent 的 active context 不等於 canonical semantic state。

$$
\boxed{
\mathrm{ActiveContext}
\neq
\mathrm{CanonicalSemanticState}
}
$$

Model context 可以隨 provider、token budget、task 而改變。

ASE 則保持 model-independent。

---

# 1. Why Semantic Envelope

一般 Agent framework 常把所有中間狀態塞入：

```text
messages[]
```

這會讓下面內容在資料結構中沒有本體差異：

```text
user asks X
assistant guesses Y
tool says Z
assistant plans A
assistant claims B is verified
```

MACR 不接受這種折疊。

必須保持：

$$
\boxed{
\mathrm{Utterance}
\neq
\mathrm{Observation}
\neq
\mathrm{Claim}
\neq
\mathrm{Decision}
\neq
\mathrm{Verification}
}
$$

語意角色應由 contract 決定，不由文字風格決定。

---

# 2. ASE Core Node

每個 semantic node：

$$
n_i
=
(
id,
type,
payload,
scope,
effects,
constraints,
policy,
provenance,
temporal,
status
)
$$

v0.1 minimum schema：

```json
{
  "schema": "macr-semantic-node/v1",
  "node_id": "sem:...",
  "node_type": "observation",
  "payload": {},
  "scope": {},
  "effects": [],
  "constraints": [],
  "policy": {},
  "provenance": {},
  "temporal": {},
  "status": "ACTIVE",
  "semantic_digest": "sha256:..."
}
```

---

# 3. Node Identity

`node_id` 是 occurrence / semantic-record identity。

建議：

```text
sem:<node-type>:<uuid>
```

例如：

```text
sem:goal:...
sem:observation:...
sem:plan:...
sem:action:...
```

而 `semantic_digest`：

$$
D_n
=
H(
type,
payload,
scope,
effects,
constraints,
policy,
provenanceSemanticSubset
)
$$

不包含：

```text
created_at
updated_at
runtime-local database row id
display text
UI position
```

因此：

$$
\boxed{
\mathrm{NodeIdentity}
\neq
\mathrm{SemanticDigest}
}
$$

---

# 4. Node Type Registry

v0.7.0 核心 node type：

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

可選但不要求 v0.7.0 第一輪完成：

```text
question
alternative
counterexample
simulation
measurement
human_request
delegation
child_result
world_object
```

---

# 5. Goal Node

Goal 表示：

> AgentRun 被要求達成的 bounded target。

最低 payload：

```json
{
  "objective": "repair failing tests",
  "success_criteria": [
    "targeted tests pass",
    "no forbidden files changed"
  ],
  "scope_ref": "scope:...",
  "termination_policy_ref": "stop:..."
}
```

Goal 不應包含 authority。

$$
\boxed{
\mathrm{Goal}
\neq
\mathrm{Authority}
}
$$

例如：

```text
Deploy application
```

是 Goal。

不是：

```text
deploy is authorized
```

---

# 6. Trigger Node

Trigger 解釋：

> 為什麼 AgentRun 現在開始或重新醒來。

種類：

```text
human_request
scheduled
external_event
world_change
child_completion
manual_resume
policy_trigger
```

Trigger：

$$
\boxed{
\mathrm{Trigger}
\neq
\mathrm{Goal}
}
$$

一個 trigger 可以喚醒同一 Goal。

---

# 7. Observation Node

Observation 必須代表：

> 某一 observer 在某一時間，透過某個可識別 projection / measurement 得到的 evidence-bearing state。

最低：

```json
{
  "world_binding_ref": "world:...",
  "projection_ref": "pncw:...",
  "source_revision": "abc123",
  "verification_ref": "verify:...",
  "observation_kind": "structured_repository_state",
  "content_ref": "artifact:..."
}
```

MACR 不要求 observation payload 直接內嵌所有內容。

---

# 8. Verified Observation

PNCW integration 後：

$$
Observation
=
Projection
+
Verification
+
Visibility
$$

在 MACR canonical semantic graph 中，只有滿足 required observation policy 的 node 才可標：

```text
VERIFIED
```

因此：

$$
\boxed{
\mathrm{RawInput}
\neq
\mathrm{VerifiedObservation}
}
$$

PNCW 已經實作 readiness、verification、visibility 與 source/surface authority 分離，所以 ASE 不重複實作這一套。

---

# 9. Claim Node

Claim 是：

> 系統中某個 actor 對世界、任務或狀態提出的可真假判定命題。

例如：

```text
"test_x fails because parser rejects empty tuples"
```

payload：

```json
{
  "statement": "parser rejects empty tuples",
  "subject_ref": "artifact:parser",
  "predicate": "rejects",
  "object_ref": "case:empty_tuple",
  "confidence": 0.72
}
```

confidence 不是 verification。

$$
\boxed{
\mathrm{Confidence}
\neq
\mathrm{Truth}
}
$$

---

# 10. Hypothesis Node

Hypothesis 是尚待驗證的 explanatory / predictive claim。

例如：

```text
"If token normalization runs before anchor relocation, the stale-anchor failure disappears."
```

Hypothesis 可以驅動：

```text
test
simulation
action proposal
counterexample search
```

但不能直接轉成 canonical fact。

---

# 11. Claim Status

建議：

```text
PROPOSED
SUPPORTED
CONTESTED
VERIFIED
REFUTED
STALE
SUPERSEDED
```

狀態轉移需要 evidence relation。

不能：

```text
PROPOSED → VERIFIED
```

只因 Agent 說：

```text
I am confident.
```

---

# 12. Plan Node

Plan 表示：

> 為達成 Goal 而組織的一組 future-intended semantic steps。

Plan payload：

```json
{
  "plan_revision": 3,
  "steps": [
    "task:inspect",
    "task:test",
    "task:patch",
    "task:verify"
  ],
  "basis_observation_refs": [
    "sem:observation:..."
  ],
  "assumptions": [
    "sem:claim:..."
  ],
  "completion_ref": "constraint:..."
}
```

Plan：

$$
\boxed{
\mathrm{Plan}
\neq
\mathrm{Command}
}
$$

---

# 13. Task Node

Task 是 Plan 裡可以被 bounded executor 完成的子單位。

例如：

```text
run failing test
read one file
compare two revisions
ask verifier
```

Task 可以編譯到現行 MACR `TaskContract`。

因此：

$$
\boxed{
\mathrm{ASETask}
\rightarrow
\mathrm{TaskContract}
}
$$

但 TaskContract 不需要反過來成為完整 Semantic Graph。

---

# 14. Action Proposal Node

ActionProposal 是所有 external-effect action 的 canonical proposal。

最低：

```json
{
  "operation": "repository.patch",
  "target_ref": "world:repo:X",
  "parameters_ref": "artifact:patch:...",
  "expected_effects": [
    "filesystem.write",
    "git.working_tree.modify"
  ],
  "expected_result_ref": "claim:...",
  "rollback_policy_ref": "policy:...",
  "verification_policy_ref": "policy:..."
}
```

---

# 15. Effect Semantics

`effects` 是 ASE 最重要欄位之一。

Node effects 不描述 tool 名稱，而描述 world-impact semantics。

例如：

```text
filesystem.read
filesystem.write
filesystem.delete

network.read
network.write

repository.read
repository.branch.write
repository.main.write
repository.tag.create
repository.release.publish

communication.send

identity.read_private
identity.modify_registry

credential.read
credential.export

finance.spend

compute.cpu
compute.gpu

world.visual.control
world.terminal.control
```

---

# 16. Effect Composition

複合 action：

$$
Effects(a)
=
\bigcup_{i=1}^{n} Effects_i
$$

任何 child effect 若不被 authority envelope 覆蓋：

$$
\exists e\in Effects(a)
:
e\notin Authority
$$

則：

$$
\boxed{
Authorize(a)=0
}
$$

---

# 17. Constraint Node

Constraint 是：

> 對 Goal、Plan、Action、Verification 或 World 操作施加的明確限制。

例如：

```text
do_not_modify_main
tests_required
no_network
max_cost_1_usd
rollback_required
human_approval_before_publish
must_preserve_utf8
```

Constraint 不等於 prompt recommendation。

它可以進 deterministic validation。

---

# 18. Policy vs Constraint

Constraint：

> 具體要求。

Policy：

> 決定如何處理一類狀況的規則。

因此：

$$
\boxed{
\mathrm{Constraint}
\neq
\mathrm{Policy}
}
$$

例如：

```text
constraint:
max_cost_usd = 1
```

policy：

```text
if irreversible external publish:
  require human approval
```

---

# 19. Decision Node

Decision 表示：

> Runtime、Policy Engine、Human、Verifier 或 Agent 對候選狀態做出的正式判定。

例如：

```text
ALLOW
DENY
DEFER
ESCALATE
SELECT
REJECT
ACCEPT_PROPOSAL
REQUIRE_REOBSERVATION
```

Decision 必須記錄：

```text
decision_actor
basis_refs
policy_ref
subject_ref
decision_kind
```

---

# 20. Decision Authority

不是每個 actor 的 Decision 都具有相同效力。

例如：

```text
Agent Decision
```

可能只是：

```text
SELECT preferred plan
```

而：

```text
Authority Gate Decision
```

才可以產生 execution admission。

所以：

$$
\boxed{
\mathrm{Decision}
\neq
\mathrm{Authority}
}
$$

---

# 21. Receipt Node

Receipt 表示：

> 某 provider/runtime 宣稱某操作已經被接收、執行或完成的結果。

例如：

```json
{
  "provider": "github",
  "action_ref": "sem:action:...",
  "provider_operation_id": "...",
  "reported_status": "success",
  "reported_revision": "abc123",
  "content_ref": null
}
```

---

# 22. Receipt Is Not Verification

核心 invariant：

$$
\boxed{
\mathrm{Receipt}
\neq
\mathrm{Verification}
}
$$

Receipt 可以：

```text
support verification
```

但不能自己驗證自己。

---

# 23. Verification Node

Verification 表示：

> 依 explicit verification policy，對某 subject 進行的獨立結果判定。

最低：

```json
{
  "subject_ref": "sem:action:...",
  "verification_kind": "post_condition",
  "basis_refs": [
    "sem:observation:..."
  ],
  "verdict": "PASSED",
  "evidence_refs": [],
  "verifier_ref": "verifier:..."
}
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

# 24. Verification Graph

Verification 不必是一個 node 一次完成。

可形成：

```text
Action
  ↓
Receipt
  ↓
Observation
  ↓
Claim
  ↓
Verification
```

或：

```text
Hypothesis
  ├─ Test A
  ├─ Test B
  └─ Counterexample Search
       ↓
    Verification
```

---

# 25. Checkpoint Node

ASE Checkpoint node 不保存完整 AgentRun checkpoint bytes。

它表示：

> Semantic graph 中某個 execution-state checkpoint 的 semantic reference。

payload：

```json
{
  "agent_checkpoint_ref": "cp:...",
  "state_revision": 18,
  "semantic_state_digest": "sha256:...",
  "continuation_kind": "suspend"
}
```

真正 durability contract 由 AgentRun Checkpoint Specification 管理。

---

# 26. Failure Node

Failure 是 first-class semantic object。

不是：

```text
exception string
```

最低：

```json
{
  "failure_class": "AUTHORITY_DENIED",
  "subject_ref": "sem:action:...",
  "recoverability": "BLOCKED",
  "evidence_refs": [],
  "recommended_transition": "BLOCKED"
}
```

---

# 27. Failure Classes

ASE 共享 AgentRun failure taxonomy：

```text
MODEL_FAILURE
PROVIDER_FAILURE
CAPABILITY_MISSING
AUTHORITY_DENIED
BUDGET_EXHAUSTED
WORLD_STALE
PROJECTION_FAILED
VERIFICATION_FAILED
ACTION_DIVERGED
CHECKPOINT_INVALID
WAKE_INVALID
DEPENDENCY_FAILED
RECONCILIATION_REQUIRED
HUMAN_DECISION_REQUIRED
```

---

# 28. WakeCondition Node

WakeCondition 是 future continuation semantics。

例如：

```json
{
  "kind": "EXTERNAL_EVENT",
  "source_ref": "github:repo:X",
  "predicate_ref": "predicate:main_changed",
  "expiry": null
}
```

它可連到：

```text
checkpoint
agent_run
goal
```

---

# 29. Semantic Relations

ASE relation：

$$
r_{ij}
=
(
source,
type,
target,
qualifiers,
provenance
)
$$

最低 schema：

```json
{
  "schema": "macr-semantic-relation/v1",
  "relation_id": "rel:...",
  "source_ref": "sem:...",
  "relation_type": "supports",
  "target_ref": "sem:...",
  "qualifiers": {},
  "provenance": {},
  "semantic_digest": "sha256:..."
}
```

---

# 30. Core Relation Registry

v0.7.0 minimum：

```text
supports
contradicts
depends_on
derived_from
observes
describes
constrains
authorizes
does_not_authorize
motivates
implements
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
delegates_to
returns_to
causes
precedes
follows
waits_for
```

---

# 31. Relation Semantics Must Be Typed

不能只存：

```text
related_to
```

因為：

```text
A supports B
```

與：

```text
A contradicts B
```

對 Agent 行為完全不同。

---

# 32. Authority Relation

ASE 可以記錄：

```text
authority_ref authorizes action_ref
```

但 authority object 本身仍由 canonical authority subsystem 擁有。

因此 ASE relation：

```text
authorizes
```

是：

> reference to a verified authority verdict

不是：

> Semantic graph 可以創造 authority。

$$
\boxed{
\mathrm{SemanticRelation(authorizes)}
\neq
\mathrm{AuthoritySource}
}
$$

---

# 33. Semantic Graph

Agent Semantic Graph：

$$
G_A=(N,R)
$$

其中：

$$
N=\{n_1,\dots,n_k\}
$$

$$
R\subseteq N\times Type\times N
$$

Graph 必須支援：

- append；
- supersede；
- branch；
- query；
- projection；
- pruning from active context；
- persistent historical reference。

---

# 34. Graph Is Not a Tree

一個 observation 可以：

```text
support claim A
contradict claim B
motivate plan C
verify action D
```

因此純 AST 不足。

---

# 35. Tree IR

Tree IR 用於：

- Goal decomposition；
- Plan structure；
- Task hierarchy；
- Constraint nesting。

例如：

```text
Goal
├─ Plan
│  ├─ Task
│  ├─ Task
│  └─ Task
└─ SuccessCriteria
```

---

# 36. Graph IR

Graph IR 用於：

- evidence relations；
- dependency；
- causal relation；
- contradiction；
- provenance；
- semantic linking。

---

# 37. Event IR

Event IR 用於：

> 實際在時間中發生什麼。

例如：

```text
GoalBound
ObservationCreated
PlanActivated
ActionProposed
ActionAuthorized
ActionDispatched
ReceiptCaptured
VerificationPassed
CheckpointPromoted
```

因此：

$$
\boxed{
\mathrm{TreeIR}
\neq
\mathrm{GraphIR}
\neq
\mathrm{EventIR}
}
$$

---

# 38. Semantic Event

Semantic Event 最小：

```json
{
  "schema": "macr-semantic-event/v1",
  "event_id": "evt:...",
  "event_type": "verification.passed",
  "agent_run_id": "...",
  "subject_refs": [],
  "produced_refs": [],
  "timestamp": "...",
  "causal_parent_refs": [],
  "semantic_digest": "sha256:..."
}
```

---

# 39. Event Identity

時間可能屬於 event identity。

因為兩個相同 action：

```text
run test
```

在 $t_1$ 與 $t_2$ 是兩個 execution events。

但 semantic subject：

```text
test operation
```

可以相同。

---

# 40. Event Order vs Causal Order

不能假設：

$$
SerializationOrder
=
CausalOrder
$$

因此 event 支援：

```text
causal_parent_refs
```

PHOSPHOR Spacetime 已明確把 temporal / causal semantics 與普通 execution order 分開，因此 ASE 保留這個邊界。

---

# 41. Temporal Semantics

每個 node 可以有：

```json
{
  "created_at": "...",
  "valid_from": "...",
  "valid_until": null,
  "observed_at": "...",
  "superseded_at": null
}
```

但不同 type 可以有不同 temporal meaning。

Observation：

```text
observed_at
```

Goal：

```text
valid_from / valid_until
```

WakeCondition：

```text
not_before
expiry
```

---

# 42. Node Status

最低：

```text
ACTIVE
STALE
SUPERSEDED
INVALID
ARCHIVED
```

某些 node-specific status 可另有 subtype。

例如 Claim：

```text
SUPPORTED
REFUTED
```

但 canonical top-level lifecycle 保持簡單。

---

# 43. Supersession

不能 overwrite 舊 node。

例如：

```text
Claim v1
→ Claim v2
```

建立：

```text
v2 supersedes v1
```

舊 node 保持存在。

---

# 44. Mutation Model

ASE semantic graph 只接受：

```text
append node
append relation
append event
mark node superseded
mark node stale
```

不鼓勵 destructive rewrite。

這與 SEDB append-oriented history、Decision/Commit 分離方向相容。SEDB v0.4B 已採取不可抹除 Decision/Commit history 與 compensating rollback。

---

# 45. Semantic Proposal vs Commit

Model 生成語意內容時先形成：

```text
SemanticMutationProposal
```

例如：

```json
{
  "add_nodes": [],
  "add_relations": [],
  "supersede": []
}
```

然後：

```text
schema validation
→ policy validation
→ provenance validation
→ semantic consistency checks
→ commit
```

因此：

$$
\boxed{
\mathrm{ModelGeneratedSemanticPatch}
\neq
\mathrm{CommittedSemanticState}
}
$$

---

# 46. Semantic Patch

建議：

```json
{
  "schema": "macr-semantic-patch/v1",
  "patch_id": "...",
  "base_graph_digest": "sha256:...",
  "add_nodes": [],
  "add_relations": [],
  "status_updates": [],
  "producer_ref": "invocation:...",
  "patch_digest": "sha256:..."
}
```

---

# 47. Stale Semantic Patch

如果：

$$
BaseGraphDigest
\neq
CurrentGraphDigest
$$

不得 blind apply。

可以：

```text
rebase
recompute
reject
```

但 rebase 必須有 explicit deterministic or verified semantic procedure。

---

# 48. Provenance

每個 node / relation 必須有 provenance。

最低：

```json
{
  "origin_kind": "model",
  "origin_ref": "invocation:...",
  "agent_run_id": "...",
  "created_by_ref": "agent:...",
  "source_refs": []
}
```

---

# 49. Provenance Classes

```text
human
model
worker
provider
deterministic_runtime
external_world
import
migration
verifier
policy_engine
```

---

# 50. Provenance Is Not Truth

$$
\boxed{
\mathrm{TrustedOrigin}
\neq
\mathrm{VerifiedTruth}
}
$$

即使 node 由 human 建立，也可能錯。

即使 node 由 untrusted model 建立，也可能經 verification 後成為可靠 claim。

---

# 51. Scope

Node scope 可指：

```text
agent_run
goal
plan
task
world_binding
resource
project
global_reference
```

scope 決定：

> 這個 semantic node 在哪個語境有效。

---

# 52. Scope Leakage

Task-local claim 不得自動升格為 global truth。

例如：

```text
"In this branch, file X is stale."
```

不能變成：

```text
"file X is universally stale."
```

---

# 53. Semantic Namespaces

建議：

```text
macr.goal.*
macr.observation.*
macr.plan.*
macr.action.*
macr.verification.*

pncw.*
mrmic.*
phosphor.*
sedb.*
eml.*
```

但 namespace 只表示 semantic ownership / vocabulary，不授權 execution。

---

# 54. Host References

ASE 不保存所有 external resource bytes。

用：

```text
resource_ref
artifact_ref
world_binding_ref
content_ref
```

連結外部 canonical systems。

---

# 55. Anchor Semantics

若 EML-U integration 需要對 host artifact 局部附加語意，可加入：

```json
{
  "anchor_ref": {
    "host_ref": "repo:file:...",
    "selector": "function:foo/statement:3",
    "revision": "abc123"
  }
}
```

這直接與 EML-U Anchor Layer 方向相容。EML-U 已將 anchor 定義為可指向 token、AST node、文件段落、JSON path、工作流節點、音訊時間區間、圖像區域等多種宿主位置。

---

# 56. Observation Projection

同一 semantic state 可投影為：

```text
Agent JSON
Human Summary
Graph View
Timeline
Debug View
MRMIC Canvas
EML-U View
```

因此：

$$
\boxed{
\mathrm{SemanticState}
\neq
\mathrm{RenderedView}
}
$$

---

# 57. Human Projection

Human-readable summary 可以變化。

例如：

```text
Tests now pass.
```

與：

```text
3 targeted tests passed after the patch.
```

可以投影自同一 verification state。

---

# 58. Model Projection

不同 model 也可以得到不同 context projection。

例如 Qwythos：

```text
compressed local subset
```

Grok：

```text
larger semantic context
```

但 semantic graph 不因此變成兩套 canonical state。

---

# 59. Context Builder

Model context：

$$
C_m
=
\Pi_m(
G_A,
Goal,
Budget,
World,
Policy
)
$$

其中：

$$
\Pi_m
$$

可依：

- model context window；
- task；
- privacy；
- provider；
- latency；
- token budget；

產生 projection。

---

# 60. Context Selection Is Not Truth Mutation

如果某 node 沒被放入當前 context：

$$
n_i\notin C_m
$$

不表示：

$$
n_i\notin G_A
$$

---

# 61. Semantic Compression

允許壓縮：

```text
20 observations
→ summary claim node
```

但 summary 必須保留：

```text
derived_from
```

relations。

因此：

$$
\boxed{
\mathrm{Compression}
\neq
\mathrm{EvidenceDeletion}
}
$$

---

# 62. Lossless Expandability Direction

未來可接 ANLA / archive system：

```text
summary / projection
→ exact source refs
```

ASE 不要求所有 source 都長期直接存在 graph DB。

---

# 63. Contradiction

ASE 必須允許：

```text
Claim A
contradicts
Claim B
```

而不是強迫立刻覆蓋其中一個。

這對 multi-worker / multi-model 很重要。

---

# 64. Conflict Resolution

Conflict：

```text
claim A
claim B
```

可產生：

```text
comparison task
counterexample task
verification task
human decision
```

最後建立：

```text
Verification V
```

或：

```text
Decision D
```

再標：

```text
A superseded
B verified
```

---

# 65. Multi-Agent Semantic Merge

未來 child Agent 返回：

```text
SemanticPatch
```

Parent 不直接 append 全部。

需：

```text
validate
deduplicate
detect contradiction
check provenance
join
```

---

# 66. Deduplication

兩個 node 可能：

```text
node_id differs
semantic_digest equal
```

這表示：

> 兩個 occurrence 表達同一 semantic content。

是否合併由 policy 決定。

不能直接因 digest 相同刪除 provenance。

---

# 67. Semantic Digest and Provenance

若 provenance 被納入 semantic digest，兩個相同 claim 不同來源會不同 digest。

如果不納入，則 semantic subject 可相同。

v0.1 建議分兩個 digest：

$$
D_{content}
=
H(type,payload,scope,effects,constraints,policy)
$$

$$
D_{record}
=
H(D_{content},provenance)
$$

因此：

```text
content_digest
record_digest
```

---

# 68. Why Two Digests

可以回答：

> 這兩個 Agent 是否提出同一命題？

看：

```text
content_digest
```

以及：

> 這是不是同一筆 evidence record？

看：

```text
record_digest
```

---

# 69. Canonical Serialization

所有 ASE digest 必須使用 MACR 統一 canonical serializer。

不能：

```text
Python json.dumps
```

與：

```text
JavaScript JSON.stringify
```

各自算 identity。

PNCW 實際 E2E 已遇到跨 Python/JavaScript 浮點 canonicalization 差異，所以這不是理論性問題。

---

# 70. Number Policy

ASE v1 建議 canonical semantic payload 禁止 unrestricted binary float 直接參與 identity。

可採：

```text
integer
decimal-as-string
bounded rational
canonical decimal profile
```

若必須 float：

```text
normalized IEEE representation
```

必須在 serializer spec 明定。

---

# 71. Hidden Chain-of-Thought

ASE 禁止把 hidden CoT 當 mandatory semantic source。

Agent 可以產生：

```text
plan summary
reason code
evidence relation
decision basis
```

而不是：

```text
private full reasoning transcript
```

因此：

$$
\boxed{
\mathrm{SemanticAuditability}
\neq
\mathrm{CoTStorage}
}
$$

---

# 72. Explanation Node

若需要 explainability，可額外有：

```text
explanation
```

但 explanation 是 human/model-facing artifact，不是 authority。

---

# 73. Confidence

confidence 可用：

$$
c\in[0,1]
$$

但必須標來源：

```text
self_reported
model_calibrated
empirical
policy_assigned
```

不能混用。

---

# 74. Verification Overrides Confidence

例如：

```text
claim confidence = 0.99
verification = FAILED
```

則 canonical state：

```text
REFUTED
```

不能因 confidence 高保留 verified status。

---

# 75. Decision Receipt Separation

SEDB v0.4B 的：

$$
Decision\neq Commit
$$

在 ASE 保留。

所以：

```text
Decision Node
```

與：

```text
Receipt Node
```

不同。

Decision：

> 應做什麼。

Receipt：

> provider 報告做了什麼。

Verification：

> 世界實際變成什麼。

---

# 76. Action Semantic Sequence

完整：

```text
Goal
  ↓ motivates
Plan
  ↓ contains
Task
  ↓ motivates
ActionProposal
  ↓ subject_of
Decision
  ↓ authorizes/reference
Actuation Event
  ↓ produced
Receipt
  ↓ motivates
Observation
  ↓ basis_of
Verification
```

---

# 77. Failure Semantic Sequence

```text
Action
  ↓
Provider failure
  ↓
Failure Node
  ↓
Decision:
retry / reconcile / block / fail
```

若 unknown effect：

```text
Failure
  ↓
ReconciliationRequired
```

---

# 78. Reconciliation Semantics

ASE relation：

```text
failure blocks agent_run
reconciliation resolves failure
observation supports reconciliation
```

Agent 自己不能建立：

```text
reconciliation resolved
```

除非 runtime authority contract 明確授權。

---

# 79. Completion Semantics

Goal completion：

```text
Verification
  ↓ verifies
SuccessCriteria
```

最後 Runtime 建立：

```text
Decision: COMPLETE
```

Agent 文字：

```text
done
```

只是一個 proposal。

---

# 80. Semantic Graph Version

每次 commit：

```text
graph_revision
```

嚴格增加。

Graph digest：

$$
D_G
=
H(
ordered\ active\ node\ records,
ordered\ relations,
registry\ version
)
$$

Event history 不必全部納入 active graph digest。

---

# 81. Active Graph vs Historical Graph

Active Graph：

```text
current relevant semantic truth/state
```

Historical Graph：

```text
all superseded/refuted/stale records
```

因此：

$$
\boxed{
\mathrm{ActiveGraph}
\subseteq
\mathrm{HistoricalGraph}
}
$$

---

# 82. Graph Projection

可依 Goal 建：

$$
G_Q
\subseteq
G_A
$$

例如只取：

```text
current goal
relevant observations
active plan
constraints
pending action
verification
```

作 model context。

---

# 83. SEDB Compatibility

SEDB vNext 很適合保存：

```text
semantic nodes
relations
claims
provenance
lifecycle
```

但 ASE 不能直接綁 SEDB field schema。

第一版可以 SQLite，未來做：

```text
ASEStore adapter
→ SEDB
```

---

# 84. EML-U Compatibility

EML-U conceptual node：

$$
s_i
=
(
id,
type,
payload,
scope,
effects,
constraints,
policy,
provenance
)
$$

ASE：

$$
n_i
=
(
id,
type,
payload,
scope,
effects,
constraints,
policy,
provenance,
temporal,
status
)
$$

所以：

$$
\boxed{
ASE
=
EML\text{-}U_{conceptual}
+
RuntimeTemporalStatusSubset
}
$$

並不衝突。

---

# 85. Future EML-U Migration

未來若 EML-U MVP 完成：

$$
\Phi:
ASE
\rightarrow
EML\text{-}U\ IR
$$

要求：

```text
no semantic loss
explicit unsupported
provenance preserved
relation preserved
authority references preserved
temporal metadata preserved
```

---

# 86. No Silent Degradation

若 EML-U future schema 無法表示 ASE 欄位：

```text
UNSUPPORTED
```

不得：

```text
drop field silently
```

這與 EML-U 現有降級原則一致：無法安全表達的結構必須明確 unsupported，而不是靜默遺失。

---

# 87. Semantic Registry

v0.7 建議：

```text
schemas/semantic/
registry-v1.json
```

包含：

```text
node_types
relation_types
effect_types
status_types
verdict_types
failure_types
```

---

# 88. Registry Version

每個 SemanticGraph 記：

```text
registry_version
```

Registry 改變不等於舊 graph 自動升級。

需要 explicit migration。

---

# 89. Unknown Type

未知：

```text
node_type
relation_type
effect_type
```

fail closed。

不能：

```text
treat unknown as generic
```

尤其 effect unknown 必須拒絕 authorization。

---

# 90. Extension Namespace

外部 subsystem 可以擴充：

```text
pncw.observation.visible
mrmic.portal.focus
phosphor.actuation.intent
sedb.claim.field
```

但 extension schema 必須 versioned。

---

# 91. Storage Boundary

建議 physical：

```text
runtime/agent-semantics.sqlite3
```

表：

```text
semantic_nodes
semantic_relations
semantic_events
semantic_patches
semantic_graph_heads
semantic_registry_versions
```

但 storage 不是 canonical ontology。

---

# 92. Large Payload

大內容不進 semantic DB。

例如：

```text
model answer
image
repository diff
document
video
```

存：

```text
content_ref
digest
media_type
byte_count
```

---

# 93. Privacy

Semantic DB 不應保存：

```text
API key
authorization header
private plaintext by default
hidden reasoning
```

Private semantic node 可引用 Residence / encrypted/private store。

---

# 94. Public Metadata

可公開：

```text
node type
digest
status
bounded provenance
effect class
verification verdict
```

但 private content reference 仍需 access gate。

---

# 95. Agent-Facing Read API

Agent 可以：

```text
semantic.query
semantic.get_node
semantic.get_relations
semantic.get_active_goal
semantic.get_active_plan
semantic.get_constraints
semantic.get_pending_actions
```

---

# 96. Agent-Facing Write API

Agent 只可：

```text
semantic.propose_patch
```

不直接：

```text
semantic.force_commit
semantic.mark_verified
semantic.authorize
semantic.resolve_reconciliation
```

---

# 97. Runtime Commit API

Runtime：

```text
validate_patch
commit_patch
supersede_node
mark_stale
record_verification
record_decision
```

依 authority 執行。

---

# 98. Example — Repository Repair

Goal：

```text
sem:goal:g1
```

Observation：

```text
sem:observation:o1
"3 tests fail"
```

Claim：

```text
sem:claim:c1
"parser bug causes failures"
```

Relation：

```text
o1 supports c1
```

Plan：

```text
sem:plan:p1
```

Action：

```text
sem:action:a1
"patch parser"
```

Relation：

```text
c1 motivates a1
```

Decision：

```text
sem:decision:d1
ALLOW branch-local write
```

Receipt：

```text
sem:receipt:r1
patch applied
```

Observation：

```text
sem:observation:o2
tests pass
```

Verification：

```text
sem:verification:v1
PASSED
```

Relation：

```text
o2 verifies a1
v1 verifies goal success criterion
```

---

# 99. Example — Receipt Lies

Provider receipt：

```text
r1:
reported_status = success
```

Re-observation：

```text
o2:
target revision unchanged
```

Verification：

```text
v1:
DIVERGED
```

因此：

```text
r1 supports "provider reported success"
```

但：

```text
v1 refutes "world changed as expected"
```

這兩者可以同時存在。

---

# 100. Example — Multi-Model Disagreement

Worker A：

```text
claim c1:
bug in parser
```

Worker B：

```text
claim c2:
bug in tokenizer
```

Graph：

```text
c1 contradicts c2
```

Plan：

```text
run minimal tokenizer/parser isolation tests
```

Observation：

```text
o3
```

Verification：

```text
c1 VERIFIED
c2 REFUTED
```

沒有必要讓兩個 Agent 在聊天裡辯論 20 輪。

---

# 101. Minimal Validation Rules

Node：

- known schema；
- known type；
- valid ID；
- canonical payload；
- valid scope；
- effects registered；
- constraints registered or versioned；
- provenance present；
- digest correct。

Relation：

- source exists；
- target exists；
- relation registered；
- relation direction legal；
- digest correct。

---

# 102. Semantic Type Constraints

例如：

```text
verifies
```

source 必須是：

```text
verification
observation
test_result
```

target 可以是：

```text
claim
action
goal criterion
```

不能：

```text
goal verifies provider
```

除非 registry 明確允許。

---

# 103. Relation Cardinality

例如 active AgentRun：

```text
one active goal revision
one active canonical plan revision
many observations
many claims
many actions
```

這些 constraint 可由 Runtime validator 執行。

---

# 104. Effect Validation

ActionProposal 沒有 effects：

```text
effects = []
```

但 operation 明顯是 mutation：

```text
repository.delete_branch
```

應拒絕。

不能讓 Agent 透過漏填 effects 降低權限要求。

---

# 105. Effect Derivation

最好由 deterministic adapter 提供：

$$
DeclaredEffects
\cup
DerivedEffects
$$

最後 authorization 使用：

$$
EffectiveEffects
=
Union(
Declared,
Derived
)
$$

---

# 106. Semantic Verification Levels

可分：

```text
SCHEMA_VALID
SEMANTIC_VALID
EVIDENCE_SUPPORTED
INDEPENDENTLY_VERIFIED
```

不能把 schema valid 當 truth valid。

---

# 107. Maturity Labels

ASE vocabulary 可以標：

```text
IMPLEMENTED
VALIDATED
CONCEPT_ADOPTED
PLANNED
OPEN
```

尤其對跨 subsystem contract 很重要。

---

# 108. v0.7.0 Minimum Implementation

第一輪不需要完整 EML-U。

只需真正實作：

```text
Goal
Observation
Plan
Task
ActionProposal
Constraint
Decision
Receipt
Verification
Failure
Checkpoint
WakeCondition

semantic relation
semantic patch
graph head
registry
```

Claim / Hypothesis 可一起完成，但不是 agent loop 最硬 blocker。

---

# 109. Acceptance Matrix

## Node

- deterministic content digest；
- deterministic record digest；
- invalid type rejected；
- unknown effect rejected；
- missing provenance rejected。

## Relation

- dangling relation rejected；
- illegal relation type rejected；
- relation direction validated。

## Patch

- wrong base graph rejected；
- invalid patch atomic failure；
- no partial commit；
- supersession preserves old node。

## Graph

- active head deterministic；
- history remains queryable；
- model context projection does not mutate graph。

## Authority

- semantic `authorizes` text cannot create authority；
- authority reference must resolve externally。

## Verification

- receipt cannot become verification automatically；
- confidence cannot override failed verification。

## EML-U compatibility

- all ASE fields map to explicit conceptual EML-U category；
- unsupported migration fails loudly。

---

# 110. Required Negative Controls

```text
NC-ASE-01 unknown node_type
NC-ASE-02 unknown relation_type
NC-ASE-03 unknown effect
NC-ASE-04 semantic digest mismatch
NC-ASE-05 record digest mismatch
NC-ASE-06 dangling source relation
NC-ASE-07 dangling target relation
NC-ASE-08 illegal relation direction
NC-ASE-09 stale base graph patch
NC-ASE-10 partial patch commit
NC-ASE-11 silent node overwrite
NC-ASE-12 semantic text grants authority
NC-ASE-13 receipt promoted to verification
NC-ASE-14 confidence promoted to truth
NC-ASE-15 model patch directly commits
NC-ASE-16 omitted effects bypass authority
NC-ASE-17 unsupported EML-U migration silently drops field
NC-ASE-18 active-context omission deletes canonical node
NC-ASE-19 scope-local claim promoted global
NC-ASE-20 provenance removed during dedup
```

---

# 111. Relationship to AgentRun

AgentRun 保存：

```text
semantic_state_ref
semantic_state_digest
semantic_state_revision
```

ASE 保存：

```text
what the Agent knows / proposes / plans / observes
```

因此：

$$
\boxed{
\mathrm{AgentRunState}
\neq
\mathrm{SemanticGraph}
}
$$

AgentRun 是 execution lifecycle。

ASE 是 semantic working state。

---

# 112. Relationship to PNCW

PNCW：

```text
creates verified projection state
```

ASE：

```text
represents that projection as Observation semantic nodes
```

因此：

$$
\boxed{
\mathrm{PNCW}
\rightarrow
\mathrm{ASEObservation}
}
$$

而不是 ASE 自己實作 projection verification。

---

# 113. Relationship to MRMIC/NVCL

MRMIC resource portal：

```text
portal
```

可在 ASE 成為：

```text
world_object
observation target
action target
```

但 portal canonical geometry 仍由 MRMIC owning runtime 管理。MRMIC 現行架構也已明確把 portal 視為 provider resource 的投影，而非 provider resource 本身。

---

# 114. Relationship to PHOSPHOR

ASE ActionProposal：

```text
semantic intended effect
```

PHOSPHOR：

```text
CommandIntent
Actuation
MeasuredReality
```

因此：

$$
\boxed{
ASE.ActionProposal
\rightarrow
PHOSPHOR.CommandIntent
}
$$

需要 validation bridge。

---

# 115. Relationship to SEDB

SEDB 未來可以成為：

```text
ASE historical semantic backend
```

尤其：

```text
claim lifecycle
relation evolution
decision receipts
provenance
schema expansion
```

但 MACR v0.7.0 不等 SEDB vNext 才能開始。

---

# 116. Relationship to EML-U

本文件正式將 EML-U 定位為：

> **Future canonical generalized semantic host**

ASE 是：

> **MACR v0.7 bounded agent semantic profile**

可表達：

$$
\boxed{
ASE
=
\mathrm{EML\text{-}U\ Agent\ Profile}_{provisional}
}
$$

但在 EML-U 正式工程 contract 完成前，這只是一個 compatibility direction，不宣稱 EML-U 已實作。EML-U 目前公開文件本身也明確區分現有 EML-P 工程與 EML-U theory-preservation / future engineering。

---

# 117. Formal Agent Semantic Transition

Agent semantic graph：

$$
G_t
$$

Model / worker 產生 proposal：

$$
\Delta G_t^{proposal}
$$

Runtime validation：

$$
V(
G_t,
\Delta G_t^{proposal},
Policy_t
)
$$

若：

$$
V=PASS
$$

才：

$$
G_{t+1}
=
Commit(
G_t,
\Delta G_t
)
$$

因此：

$$
\boxed{
G_{t+1}
\neq
G_t
+
\mathrm{RawModelOutput}
}
$$

---

# 118. Formal Evidence Rule

Claim $c$ 成為 verified：

$$
Verified(c)
=
\exists v
:
v.type=Verification
\land
v.subject=c
\land
v.verdict=PASSED
$$

confidence 不參與此定義。

---

# 119. Formal Action Rule

Action proposal $a$ 可轉為 execution：

$$
Executable(a)
=
SemanticValid(a)
\land
EffectsKnown(a)
\land
Capability(a)
\land
Authority(a)
\land
Budget(a)
\land
Policy(a)
\land
FreshBasis(a)
$$

---

# 120. Formal Completion Relation

Goal $g$ 完成：

$$
Complete(g)
=
\bigwedge_{i=1}^{n}
Verified(
criterion_i
)
$$

其中 required criteria 由 Goal 定義。

---

# 121. Canonical Closure

本文件固定：

1. MACR v0.7 Agent canonical semantic state 不使用 `messages[]` 作為唯一表示。
2. ASE 採 Node + Relation + Event 三層模型。
3. Goal、Observation、Claim、Plan、Action、Decision、Receipt、Verification 永不折疊。
4. Receipt 不等於 Verification。
5. Confidence 不等於 Truth。
6. Plan 不等於 Command。
7. ActionProposal 不等於 authorized execution。
8. Semantic graph 不能產生 authority，只能引用 authority。
9. Model output 必須形成 SemanticPatch proposal，再經 validation commit。
10. Semantic state 使用 append / supersede，而非 destructive overwrite。
11. Tree IR、Graph IR、Event IR 保持不同 responsibility。
12. Context projection 不改變 canonical semantic state。
13. 大型 content 使用 reference，不直接塞入 semantic DB。
14. Provenance 必須保留，但 provenance 不等於 truth。
15. Effect 是 authority evaluation 的核心語意，不可只看 tool name。
16. ASE 採雙 digest：content identity 與 record/provenance identity。
17. 所有 digest 使用統一 canonical serialization。
18. ASE 與 EML-U 保持結構相容，但 v0.7.0 不依賴 EML-U runtime。
19. 未來遷移 EML-U 必須無 silent semantic loss。
20. ASE 可以先以 MACR-native SQLite/reference implementation 完成。

因此：

$$
\boxed{
\mathrm{ASE}
=
\mathrm{Typed\ Semantic\ Working\ State}
+
\mathrm{Evidence\ Graph}
+
\mathrm{Temporal\ Event\ IR}
}
$$

它使 MACR Agent 從：

```text
模型記得自己剛剛說了什麼
```

提升為：

```text
Runtime 知道
什麼是目標、
什麼是觀察、
什麼只是猜測、
什麼已被驗證、
什麼被授權、
什麼真的執行、
什麼只是 provider 宣稱成功、
以及世界最後究竟變成什麼。
```

這構成 MACR v0.7 Agent-Spacetime Runtime 的第二個 canonical engineering core。

---

# Appendix A — v0.7 ASE Core Schemas

```text
macr-semantic-node/v1
macr-semantic-relation/v1
macr-semantic-event/v1
macr-semantic-patch/v1
macr-semantic-graph-head/v1
macr-semantic-registry/v1
```

---

# Appendix B — Core Node Types

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

---

# Appendix C — Core Relations

```text
supports
contradicts
depends_on
derived_from
observes
describes
constrains
authorizes
does_not_authorize
motivates
implements
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
delegates_to
returns_to
causes
precedes
follows
waits_for
```

---

# Appendix D — Next Canonical Specification

下一份：

**MACR v0.7 — Action / Authority / Effect Contract Specification v0.1**

將正式定義：

```text
ActionProposal
EffectSet
Capability
AuthorityEnvelope
Budget
Risk
Policy
Admission
CommandIntent
Dispatch
Receipt
Verification
Reconciliation
```

之間的不可折疊關係，並把 MACR v0.6 authority、SEDB v0.4B effect-oriented autonomy、PHOSPHOR actuation semantics 收斂成 v0.7 的正式 action gate。