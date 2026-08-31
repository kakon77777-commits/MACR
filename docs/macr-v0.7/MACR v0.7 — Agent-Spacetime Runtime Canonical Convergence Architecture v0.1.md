# MACR v0.7 — Agent-Spacetime Runtime Canonical Convergence Architecture v0.1

## Agent-Spacetime 執行期規範收斂架構 v0.1

**Document ID:** `MACR-ASR-CCA-2026-v0.1`  
**Project:** MACR  
**Target line:** MACR v0.7.x  
**Baseline:** MACR v0.6.0a1  
**Date:** 2026-08-30  
**Status:** Canonical Architecture Draft / Pre-Implementation Convergence  
**Organization:** EveMissLab / 一言諾科技有限公司  
**Language:** Traditional Chinese  
**Primary convergence sources:** MACR, PNCW, MRMIC/NVCL, PHOSPHOR Spacetime, EML / EML-U, SEDB, LIMEN

---

# 摘要

MACR v0.6 已建立異質模型與 Worker 執行的核心基礎，包括 provider/model profile、token policy、TaskContract、dispatch authority、lease、candidate capture、accounting、reconciliation、Direct Chat、T1 coordination，以及生成、驗證、接受與 canonical mutation 之間的狀態分離。

MACR v0.7 的目標不再只是擴充更多模型、更多工具或更長的對話。

v0.7 的核心變化是：

> **MACR 從 Model/Worker Runtime 進入 Agent-Spacetime Runtime。**

這代表系統中的 AI 不再只接受一次 request 並回傳一次 response，而可以在明確治理範圍內：

- 持續存在於一個 AgentRun；
- 接收 Goal 或 Trigger；
- 觀察外部世界；
- 建立與更新工作狀態；
- 形成計畫；
- 提出 Action Proposal；
- 經過 capability、authority、budget、policy 與 readiness gate；
- 執行一個或多個外部行動；
- 取得 receipt；
- 重新觀察世界；
- 獨立驗證結果；
- checkpoint；
- suspend；
- wake；
- continue；
- stop。

因此：

$$
\boxed{
\mathrm{MACR}_{0.7}
\neq
\mathrm{ChatRuntime}
+
\mathrm{Tools}
}
$$

而應被定義為：

$$
\boxed{
\mathrm{MACR}_{0.7}
=
\mathrm{Governed\ Agent\ Runtime}
+
\mathrm{Software\ Spacetime}
+
\mathrm{Verified\ World\ Projection}
+
\mathrm{Semantic\ Working\ State}
+
\mathrm{Persistent\ Evolution}
}
$$

本文件不要求 EML-U Runtime 已完成，也不要求所有 EveMissLab 既有子系統先被合併為 monorepo。

相反地，本架構採取：

$$
\boxed{
\mathrm{Semantic\ Convergence}
\neq
\mathrm{Implementation\ Monolith}
}
$$

各系統保留自己的 canonical responsibility，透過 versioned contract、adapter 與 authority boundary 進行整合。

---

# 0. Canonical Decision

MACR v0.7 的正式架構決策如下。

## 0.1 v0.7 是 Agent Runtime 版本線

MACR v0.6 的主要抽象單位是：

```text
Model
Provider
TaskContract
Worker
Dispatch
Candidate
Verification
Acceptance
Accounting
Queue
```

MACR v0.7 新增的主要抽象單位是：

```text
Agent
AgentRun
Goal
Trigger
Observation
World Projection
Semantic Working State
Plan
Action Proposal
Authority Envelope
Checkpoint
Suspend
Wake
Verification
Continuation
Termination
```

因此：

$$
\boxed{
\mathrm{Worker}
\neq
\mathrm{Agent}
}
$$

Worker 可以只是完成一個 bounded task 的執行器。

Agent 則具有跨 step、跨時間與跨 observation 的持續 runtime state。

---

## 0.2 Direct Chat 保留，不被 Agent Mode 取代

MACR v0.7 不應把所有模型互動強迫轉成 Agent。

仍然保留：

```text
Direct Chat
```

以及：

```text
Delegated Task / Worker
```

並新增：

```text
Agent Run
```

三者應被視為不同 contract：

$$
\boxed{
\mathrm{DirectChat}
\neq
\mathrm{DelegatedTask}
\neq
\mathrm{AgentRun}
}
$$

例如 Grok 可以同時存在：

```text
Grok Direct Chat
Grok Worker
Grok-backed Agent
```

但三者的 authority、persistent state、tool access、context policy 與 execution semantics 不必相同。

---

## 0.3 Model 不等於 Agent

Foundation model 或 local model 只是一個 cognitive provider。

因此：

$$
\boxed{
\mathrm{Model}
\neq
\mathrm{Agent}
}
$$

一個 Agent 可以在不同 step 使用：

```text
Grok
GLM
Gemini
Qwythos
future local model
specialized verifier
non-LLM deterministic component
```

反之，同一模型也可以服務多個 AgentRun。

Agent identity、Agent state 與 Agent authority 不得由 provider model name 決定。

---

## 0.4 Agent 不等於 Resident

MACR v0.7 必須繼續保留 LIMEN / Residence 系統所強調的 identity boundary：

$$
\boxed{
\mathrm{Agent}
\neq
\mathrm{Resident}
}
$$

Agent 可以是：

- ephemeral；
- task-local；
- session-local；
- project-local；
- persistent but non-resident；
- resident-bound。

只有在需要私人 Residence、長期 identity、private memory 或跨 runtime identity continuity 時，才進入 LIMEN / Residence identity flow。

因此：

$$
\boxed{
\mathrm{PersistentAgent}
\not\Rightarrow
\mathrm{ResidentIdentity}
}
$$

---

# 1. 為什麼不是直接採用現有 Agent Framework

MACR v0.7 可以參考外部開源 Agent framework，但不得讓外部框架成為 ontology owner。

正式原則：

$$
\boxed{
\mathrm{Reference\ External\ Primitives}
\neq
\mathrm{Delegate\ Canonical\ Semantics}
}
$$

允許借鑑：

- durable execution；
- sandbox；
- scheduler；
- checkpoint；
- tracing；
- browser automation；
- tool adapters；
- handoff UX；
- multi-Agent coordination pattern；
- process supervision；
- queue implementation；
- workflow persistence。

但不直接讓外部框架定義：

- Agent 是什麼；
- World 是什麼；
- Observation 是什麼；
- Authority 是什麼；
- Memory 是什麼；
- Action 如何成為 canonical mutation；
- Agent identity；
- Agent temporal semantics；
- Agent-to-world relation。

MACR 應保持：

$$
\boxed{
\mathrm{MACR\ Canonical\ Core}
+
\mathrm{EveMissLab\ Internal\ Architecture}
+
\mathrm{Selected\ External\ Primitives}
}
$$

而不是：

$$
\boxed{
\mathrm{External\ Agent\ Framework}
+
\mathrm{MACR\ Plugins}
}
$$

---

# 2. Canonical Engineering Baselines

本架構以目前已存在的工程為基礎，不把所有內容重新發明一次。

## 2.1 MACR

MACR v0.6.0a1 已提供：

- provider/model separation；
- Direct plane；
- delegated TaskContract；
- model-local token policies；
- dispatch authority；
- leases；
- provider accounting；
- candidate capture；
- verification boundary；
- acceptance boundary；
- reconciliation；
- T1 manifest；
- T1 staging；
- one-attempt worker；
- multiprocess evidence；
- offline gates。

因此 MACR v0.7 應在既有 runtime 上新增 Agent Plane，而不是重寫 provider/runtime core。

---

## 2.2 PNCW

PNCW 已建立：

```text
REQUESTED
→ RESOLVED
→ READY
→ PROJECTED
→ VERIFIED
→ VISIBLE
```

以及：

$$
\boxed{
\mathrm{ResultExistence}
\neq
\mathrm{ResultVisibility}
\neq
\mathrm{FullResidency}
}
$$

PNCW 同時分離：

$$
\boxed{
\mathrm{SourceAuthority}
\neq
\mathrm{SurfaceAuthority}
\neq
\mathrm{VisibilityAuthority}
}
$$

因此 PNCW 應作為 MACR Agent 的 **Verified World Projection substrate**。

Agent 所「看到」的世界不應被建模為：

```text
dump everything into context
```

而應是：

```text
World
→ Projection Request
→ Readiness
→ Materialization
→ Verification
→ Visibility Commit
→ Agent Observation
```

---

## 2.3 MRMIC/NVCL

MRMIC/NVCL 已經不是單純畫布 UI。

它目前提供：

- Canvas authoritative state；
- transaction；
- event ledger；
- MCP control plane；
- NVCL Agent Runtime；
- recursive subcanvas；
- snapshot/recovery；
- pixel-native multimodal loop；
- Observation Governor；
- Passive Scene Timeline；
- resource portal；
- authenticated principal；
- semantic-agent presence；
- runtime presence；
- mounted / visible / focused / controlOwner lifecycle。

因此它應被定義為：

> **Visual / Interactive World Provider**

而不是 MACR 的 UI library。

---

## 2.4 PHOSPHOR Spacetime

PHOSPHOR Spacetime 已建立：

```text
Observe
→ Project
→ Govern
→ Authorize
→ Actuate
→ Verify
→ Benchmark
→ Gate
```

並保留核心不變量：

$$
\boxed{
\mathrm{Time}\neq\mathrm{Compute}
}
$$

$$
\boxed{
\mathrm{Observation}\neq\mathrm{Authority}
}
$$

$$
\boxed{
\mathrm{Capability}\neq\mathrm{Authority}
}
$$

$$
\boxed{
\mathrm{PolicyProposal}
\neq
\mathrm{CommandIntent}
\neq
\mathrm{Actuation}
}
$$

$$
\boxed{
\mathrm{Desired}
\neq
\mathrm{Requested}
\neq
\mathrm{Realized}
\neq
\mathrm{Observed}
}
$$

因此 PHOSPHOR Spacetime 應作為 v0.7 的 temporal / causal / actuation semantics reference。

---

## 2.5 EML / EML-U

EML-P 已有 executable programming profile。

EML 1.5 已存在：

$$
\mathcal P_t
=
(V_t,C_t,G_t,Q_t,O_t)
$$

其中：

- $V_t$：value state；
- $C_t$：control state；
- $G_t$：dependency graph；
- $Q_t$：temporal decision queue；
- $O_t$：observation stream。

而 EML-U 的 conceptual architecture 已定義：

$$
\mathcal E
=
(H,A,S,R,P,X,O)
$$

其中：

- $H$：Host Artifacts；
- $A$：Anchors；
- $S$：Semantic Nodes；
- $R$：Relations；
- $P$：Policies；
- $X$：Projection / Adapters；
- $O$：Observations。

並提出：

```text
Semantic Tree IR
Semantic Graph IR
Semantic Event IR
```

MACR v0.7 採用 EML-U 的 **conceptual semantic direction**，但：

$$
\boxed{
\mathrm{Use\ EML\text{-}U\ Semantics}
\neq
\mathrm{Depend\ on\ EML\text{-}U\ Runtime}
}
$$

---

## 2.6 SEDB

SEDB v0.4B 已有：

- dynamic semantic fields；
- provenance；
- lifecycle；
- multi-Agent evidence；
- autonomy envelope；
- Decision Receipt；
- Commit Receipt；
- effect classification；
- bounded canonical mutation；
- rollback；
- capability/authority separation。

尤其：

$$
\boxed{
\mathrm{Consensus}\neq\mathrm{Authority}
}
$$

$$
\boxed{
\mathrm{Decision}\neq\mathrm{Commit}
}
$$

SEDB 因此可作為 v0.7 的 dynamic/evolving state substrate 候選，但需要從 field-centric ontology 進一步抽象成通用 evolving-object substrate。

---

## 2.7 LIMEN

LIMEN 應只處理：

```text
Host observation
→ identity resolution
→ immutable envelope
→ minimum private projection
→ bootstrap
→ output guard
```

並保留：

$$
\boxed{
\mathrm{MODEL}\neq\mathrm{RESIDENT}
}
$$

$$
\boxed{
\mathrm{MEMORY}\neq\mathrm{IDENTITY\ AUTHORITY}
}
$$

$$
\boxed{
\mathrm{READ}\neq\mathrm{WRITE\ AUTHORITY}
}
$$

LIMEN 不負責 Agent planning、Agent scheduling 或 Agent runtime loop。

---

# 3. MACR v0.7 Core Invariants

以下 invariants 應被視為 v0.7 canonical architecture 的硬邊界。

## 3.1 Model / Agent / Resident 分離

$$
\boxed{
\mathrm{Model}
\neq
\mathrm{Agent}
\neq
\mathrm{Resident}
}
$$

---

## 3.2 Capability / Authority 分離

$$
\boxed{
\mathrm{Capability}
\neq
\mathrm{Authority}
}
$$

一個 Agent 即使知道某 tool 存在，也不代表它可以使用。

一個 provider 即使實作 mutation API，也不代表 Agent 擁有 mutation authority。

---

## 3.3 Observation / World 分離

$$
\boxed{
\mathrm{Observation}
\neq
\mathrm{World}
}
$$

Agent 所持有的 context 永遠只是 World 的 projection。

---

## 3.4 Projection / Mutation 分離

$$
\boxed{
\mathrm{ProjectionAuthority}
\neq
\mathrm{MutationAuthority}
}
$$

可以看見，不代表可以改變。

---

## 3.5 Planning / Authorization 分離

$$
\boxed{
\mathrm{PlannerDecision}
\neq
\mathrm{ExecutionAuthority}
}
$$

Agent 可以提出一個非常合理的計畫，但 authority gate 仍可以拒絕。

---

## 3.6 Decision / Commit 分離

$$
\boxed{
\mathrm{Decision}
\neq
\mathrm{Commit}
}
$$

決定「應該做」與 canonical state 已被修改，是兩個不同事件。

---

## 3.7 Receipt / Verification 分離

$$
\boxed{
\mathrm{Receipt}
\neq
\mathrm{IndependentVerification}
}
$$

provider 回覆 `success=true` 不代表世界真的達到預期狀態。

---

## 3.8 Time / Compute 分離

$$
\boxed{
\mathrm{Time}
\neq
\mathrm{Compute}
}
$$

Agent 可以 suspend，而不是 busy loop。

外部世界也可能在 Agent 不計算時發生變化。

---

## 3.9 Reasoning / Canonical State 分離

MACR 不要求保存 hidden chain-of-thought。

Canonical Agent state 應保存：

```text
goal
observation
plan summary
action proposal
constraints
authority evidence
decision
receipt
verification
checkpoint
failure
continuation state
```

而不是依賴私人 reasoning trace。

因此：

$$
\boxed{
\mathrm{CanonicalAgentState}
\neq
\mathrm{PrivateChainOfThought}
}
$$

---

# 4. Agent 的正式定義

MACR v0.7 不將 Agent 定義為一段 system prompt。

Agent 是一個被 runtime 治理的持續執行主體。

定義：

$$
\mathcal A_t
=
(
I,
G_t,
W_t,
C_t,
M_t,
\Gamma_t,
P_t,
X_t,
V_t,
\Sigma_t
)
$$

其中：

- $I$：Agent identity / runtime identity；
- $G_t$：Goal / Agenda；
- $W_t$：目前可觀察 World Projection；
- $C_t$：active context；
- $M_t$：memory references；
- $\Gamma_t$：capability + authority envelope；
- $P_t$：plan / policy state；
- $X_t$：execution state；
- $V_t$：verification state；
- $\Sigma_t$：persistent checkpoint state。

其中任何一個 component 都不能單獨被視為 Agent。

---

# 5. Agent、Worker 與 Cognitive Sub-Agent

## 5.1 Worker

Worker：

- bounded；
- one task；
- 無 persistent agenda；
- 無自主 wake；
- 完成後可消失。

$$
\boxed{
\mathrm{Worker}
=
\mathrm{BoundedExecutor}
}
$$

---

## 5.2 Agent

Agent：

- 有 AgentRun；
- 有 Goal；
- 有跨 step state；
- 可觀察；
- 可重新規劃；
- 可 checkpoint；
- 可 suspend / wake；
- 可在 authority envelope 內持續行動。

---

## 5.3 Cognitive Sub-Agent

未來 v0.7.x 可引入 Cognitive Sub-Agent：

```text
Planner
Researcher
Coder
Critic
Verifier
Searcher
Simulator
Memory Retriever
Tool Specialist
```

它們可以是：

```text
Spawn
→ Delegate
→ Execute
→ Return Evidence
→ Join
→ Retire
```

不要求每個 cognitive worker 都成為 persistent resident。

---

## 5.4 Authority 不自動繼承

若 parent Agent 的 authority 為：

$$
\Gamma_P
$$

child 最多只能取得：

$$
\Gamma_C
\subseteq
\Gamma_P
$$

且：

$$
\boxed{
\mathrm{Spawn}
\not\Rightarrow
\mathrm{AuthorityInheritance}
}
$$

authority 必須被顯式 projection。

---

# 6. AgentRun：v0.7 的 Canonical Runtime Unit

AgentRun 是 v0.7 最重要的新 object。

建議最小結構：

```json
{
  "schema": "macr-agent-run/v1",
  "agent_run_id": "ar:...",
  "agent_ref": "agent:...",
  "goal_ref": "goal:...",
  "state": "ACTIVE",
  "created_at": "...",
  "checkpoint_ref": null,
  "authority_envelope_ref": "auth:...",
  "budget_ref": "budget:...",
  "world_bindings": [],
  "semantic_state_ref": null,
  "parent_run_id": null,
  "termination_policy_ref": "stop:..."
}
```

AgentRun lifecycle：

```text
CREATED
→ ADMITTED
→ ACTIVE
→ WAITING
→ SUSPENDED
→ WAKING
→ ACTIVE
→ COMPLETED

or

ACTIVE
→ BLOCKED

ACTIVE
→ RECONCILIATION_REQUIRED

ACTIVE
→ FAILED

ACTIVE
→ CANCELLED
```

不能只用：

```text
running = true / false
```

描述。

---

# 7. Goal 與 Trigger

Agent 不應該從任意 observation 自動生成無限制 goal。

Goal 必須有來源。

建議：

```text
HumanAssigned
SystemAssigned
ParentDelegated
PolicyGenerated
Scheduled
EventTriggered
AgentProposed
```

其中 `AgentProposed` 不等於直接生效。

$$
\boxed{
\mathrm{GoalProposal}
\neq
\mathrm{GoalAuthority}
}
$$

新的 long-running goal 若擴張 scope，必須重新 admission。

---

# 8. Agent-Spacetime Canonical Loop

MACR v0.7 的主要 loop 不採簡化：

```text
Think
→ Tool
→ Think
→ Tool
```

Canonical loop：

```text
Goal / Trigger
    ↓
AgentRun Admission
    ↓
Wake / Resume
    ↓
World Observation Request
    ↓
PNCW Readiness
    ↓
Projection
    ↓
Verification
    ↓
Visible Observation
    ↓
Semantic Working-State Update
    ↓
Plan
    ↓
Action Proposal
    ↓
Effect Classification
    ↓
Capability Gate
    ↓
Authority Gate
    ↓
Budget / Risk / Policy Gate
    ↓
Command Intent
    ↓
Actuation
    ↓
Receipt
    ↓
World Re-observation
    ↓
Independent Verification
    ↓
State Evolution
    ↓
Checkpoint
    ↓
Continue / Suspend / Stop
```

形式上：

$$
\boxed{
G
\rightarrow
O_t
\rightarrow
S_t
\rightarrow
P_t
\rightarrow
A_t^{proposal}
\rightarrow
A_t^{authorized}
\rightarrow
R_t
\rightarrow
O_{t+1}
\rightarrow
V_{t+1}
\rightarrow
\Sigma_{t+1}
}
$$

其中：

$$
A_t^{proposal}
\neq
A_t^{authorized}
$$

---

# 9. World Observation Plane — PNCW

Agent 不能假設：

```text
context == world
```

而應透過 World Projection Contract。

Agent 發出：

```text
ObservationIntent
```

再編譯成：

```text
ProjectionRequest
```

PNCW 負責：

```text
resolve source
check source authority
check surface authority
prepare materialization
prepare surface
verify freshness
verify integrity
build manifest
verify
visibility commit
```

最後 MACR 只接收：

```text
VerifiedObservationRef
```

因此：

$$
\boxed{
\mathrm{AgentObservation}
=
\mathrm{VerifiedProjection}
}
$$

而不是：

$$
\mathrm{AgentObservation}
=
\mathrm{RawWorldDump}
$$

---

# 10. Interactive World Plane — MRMIC/NVCL

MRMIC/NVCL 可以成為第一個正式 Agent World Provider。

Agent 可以在其內：

- 看見 Canvas；
- 建立 resource portal；
- 操作 browser；
- 操作 terminal；
- 讀取 thread projection；
- 建立 recursive workspace；
- 使用 visual observation；
- 取得 runtime presence；
- 使用 guarded control。

但：

$$
\boxed{
\mathrm{Portal}
\neq
\mathrm{ProviderResource}
}
$$

Canvas 只擁有 portal geometry 與 projection state。

例如：

```text
GitHub portal
```

不代表 MRMIC 取得 GitHub canonical repository authority。

---

# 11. Semantic Working Plane — EML-U-Compatible Agent Semantic Envelope

EML-U 尚未完成完整 runtime。

因此 v0.7.0 不依賴 EML-U executable implementation。

但 MACR 應建立一個薄型 provisional semantic contract，使其未來可以低成本遷移到 EML-U Canonical Semantic IR。

建議：

$$
N
=
(
id,
type,
payload,
relations,
effects,
constraints,
policy,
provenance,
temporal
)
$$

最小 node families：

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

例如：

```json
{
  "schema": "macr-semantic-node/v1",
  "id": "sem:action:...",
  "type": "action_proposal",
  "payload": {
    "operation": "repo.patch"
  },
  "relations": [
    {
      "type": "supports_goal",
      "target": "sem:goal:..."
    }
  ],
  "effects": [
    "filesystem.write",
    "git.working_tree.modify"
  ],
  "constraints": [
    "tests_required",
    "no_secret_export"
  ],
  "policy": {
    "review": "conditional",
    "rollback": "required"
  },
  "provenance": {
    "origin": "agent_run"
  },
  "temporal": {
    "created_step": 12
  }
}
```

這不是完整 EML-U。

它只是：

$$
\boxed{
\mathrm{MACRSemanticEnvelope}
\subseteq
\mathrm{EML\text{-}UConceptualSpace}
}
$$

---

# 12. Semantic Graph 不等於 Execution Graph

MACR 必須避免把 Agent workflow graph 與 semantic graph 混為一談。

Execution Graph 描述：

```text
step A
→ step B
→ step C
```

Semantic Graph 描述：

```text
observation supports hypothesis
hypothesis motivates action
action affects resource
receipt contradicts expected result
verification supersedes earlier claim
```

因此：

$$
\boxed{
\mathrm{ExecutionGraph}
\neq
\mathrm{SemanticGraph}
}
$$

未來 LangGraph 類技術即使被採用，也最多負責 execution orchestration，不擁有 semantic truth。

---

# 13. Spacetime Plane — PHOSPHOR Integration

Agent 不只是 step machine。

它存在於時間中。

因此需要：

```text
wall-clock
logical time
event time
deadline
wake condition
causal predecessor
causal consequence
scheduled trigger
external trigger
suspension
resumption
```

Agent temporal state 可表示：

$$
\mathcal S^{agent}_{temporal}
=
(
\Sigma,
T,
D,
E
)
$$

其中：

- $\Sigma$：checkpoint state；
- $T$：time state；
- $D$：delayed decisions / wake queue；
- $E$：external event references。

Agent 可以：

$$
\operatorname{Suspend}
(
\Sigma_t,
t_{wake},
condition
)
$$

而不需要持續消耗模型 inference。

---

# 14. Wake Semantics

Wake source 可包含：

```text
timer
cron-like schedule
new message
file change
GitHub event
provider event
world-state change
human instruction
child-agent completion
verification result
budget replenishment
resource becoming available
```

Wake 不代表直接執行。

流程仍是：

```text
Wake Event
→ Validate
→ Rehydrate
→ Recheck Authority
→ Reobserve World
→ Continue
```

因此：

$$
\boxed{
\mathrm{Wake}
\neq
\mathrm{Authorization}
}
$$

---

# 15. Action Proposal Plane

所有 Agent action 先是 proposal。

建議：

```json
{
  "schema": "macr-action-proposal/v1",
  "proposal_id": "ap:...",
  "agent_run_id": "ar:...",
  "goal_ref": "goal:...",
  "operation": "github.update_file",
  "target_ref": "resource:...",
  "effects": [],
  "expected_result": {},
  "preconditions": [],
  "rollback_policy": {},
  "verification_policy": {},
  "cost_estimate": {},
  "provenance": {}
}
```

Agent 不直接呼叫 mutation API。

而是：

$$
\boxed{
\mathrm{Agent}
\rightarrow
\mathrm{ActionProposal}
\rightarrow
\mathrm{RuntimeGate}
\rightarrow
\mathrm{CommandIntent}
}
$$

---

# 16. Effect Classification

SEDB v0.4B 的 effect-oriented autonomy model 應被提升到 MACR Agent Runtime。

Action 不應只由 tool name 判斷危險性。

例如：

```text
tool = shell
```

本身資訊不足。

應看：

```text
read filesystem
write filesystem
network access
credential access
repository mutation
external publication
financial cost
delete
irreversible external side effect
identity-affecting action
authority-affecting action
```

因此：

$$
\boxed{
\mathrm{ActionClassification}
=
f(\mathrm{Effects})
}
$$

而不是：

$$
f(\mathrm{ToolName})
$$

---

# 17. Capability、Authority、Budget 三重分離

一個 action 要執行，至少需要：

$$
C(a)=1
$$

$$
A(a)=1
$$

$$
B(a)=1
$$

其中：

- $C$：capability exists；
- $A$：authority permits；
- $B$：budget permits。

最小 execution gate：

$$
\boxed{
Execute(a)
=
C(a)
\land
A(a)
\land
B(a)
\land
P(a)
}
$$

其中 $P$ 為 policy / safety / readiness gates。

---

# 18. CommandIntent 與 Provider Actuation

Action Proposal 通過 MACR gate 後，不直接等於 provider-native request。

應編譯為：

```text
CommandIntent
```

再由 PHOSPHOR / provider adapter 負責：

```text
CommandIntent
→ Provider ABI
→ native provider operation
→ Actuation Receipt
```

因此：

$$
\boxed{
\mathrm{ActionProposal}
\neq
\mathrm{CommandIntent}
\neq
\mathrm{ProviderCall}
}
$$

---

# 19. Receipt 與 Outcome Verification

任何有外部 effect 的 action 完成後，Agent 不得只相信 provider receipt。

必須區分：

```text
provider says done
```

與：

```text
world is now in expected state
```

因此：

```text
Actuation
→ Receipt
→ Reobserve
→ Compare Expected / Observed
→ Verify
```

定義：

$$
V
=
Compare(
Expected,
Observed
)
$$

可能輸出：

```text
VERIFIED
PARTIAL
DIVERGED
UNKNOWN
STALE
CONFLICT
```

---

# 20. SEDB vNext — Evolving Agent State

SEDB 不應直接變成 MACR internal SQLite replacement。

它的角色應是：

> **Evolving semantic/world state substrate**

現行 field-oriented schema 未來可抽象：

```text
Object
Relation
State
Event
Claim
Observation
Decision
Receipt
Provenance
Lifecycle
```

AgentRun 的 transient scheduler state 可以仍存在 MACR。

SEDB 保存適合長期演化與查詢的狀態：

```text
observed objects
semantic fields
claims
world distinctions
decisions
reasons
receipts
verification evidence
history
schema evolution
```

因此：

$$
\boxed{
\mathrm{MACRRuntimeState}
\neq
\mathrm{SEDBKnowledgeState}
}
$$

---

# 21. Checkpoint

Agent 每一輪不需要完整 snapshot 整個世界。

Checkpoint 只需要保存足以恢復 AgentRun 的 canonical state。

建議：

```json
{
  "schema": "macr-agent-checkpoint/v1",
  "checkpoint_id": "cp:...",
  "agent_run_id": "ar:...",
  "step": 42,
  "goal_ref": "goal:...",
  "semantic_state_ref": "graph:...",
  "world_projection_refs": [],
  "pending_action_refs": [],
  "authority_revision": "...",
  "budget_state_ref": "...",
  "wake_condition": null,
  "verification_state_ref": "...",
  "created_at": "..."
}
```

checkpoint 不應保存：

- raw API key；
- hidden CoT；
- stale provider session secret；
- unverifiable ephemeral authority。

---

# 22. Resume

Resume 流程：

```text
load checkpoint
→ verify checkpoint integrity
→ resolve current AgentRun
→ recheck authority revision
→ recheck budget
→ resolve world bindings
→ reobserve world
→ detect stale assumptions
→ continue
```

不能：

```text
load old state
→ blindly replay action
```

因此：

$$
\boxed{
\mathrm{Resume}
\neq
\mathrm{Replay}
}
$$

---

# 23. Failure Classes

Agent Runtime 的 failure 不應全部被壓成 exception。

建議：

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

其中：

```text
provider timeout
```

與：

```text
unknown whether provider already executed
```

必須是不同 failure。

後者應：

```text
RECONCILIATION_REQUIRED
```

不得自動 retry。

---

# 24. Retry Semantics

Retry 只允許在明確知道前一次 action 沒有造成 side effect 時。

因此：

$$
\boxed{
\mathrm{Retryable}
\Rightarrow
\mathrm{KnownNoEffect}
}
$$

若 effect state 未知：

$$
\boxed{
\mathrm{UnknownAfterDispatch}
\Rightarrow
\mathrm{ReconciliationRequired}
}
$$

這延續 MACR v0.6 T1 的 one-attempt philosophy。

---

# 25. Rollback 與 Compensation

Agent Runtime 必須區分：

$$
\boxed{
\mathrm{Rollback}
\neq
\mathrm{Compensation}
}
$$

內部 transaction 可 rollback。

外部已經發生的 action 多數只能 compensation。

例如：

```text
published comment
created issue
sent message
remote API mutation
financial operation
```

不能假裝歷史從未發生。

---

# 26. Memory

MACR v0.7 不建立一個巨大的「Agent Memory」抽象包辦所有資訊。

應分為：

```text
Working State
Conversation History
Evidence
World Projection
Checkpoint
Semantic Knowledge
Private Residence Memory
Archive
External Resource
```

因此：

$$
\boxed{
\mathrm{Memory}
\neq
\mathrm{OneDatabase}
}
$$

未來可由：

- MACR；
- SEDB；
- ANLA/context archive；
- Residence；
- project repository；
- external databases；

共同提供不同 memory plane。

---

# 27. Private Residence Integration

只有當 AgentRun 綁定 resident 時：

```text
Host
→ LIMEN observe
→ resolve
→ envelope
→ minimum private projection
→ AgentRun
```

並保持：

$$
\boxed{
\mathrm{AgentRunID}
\neq
\mathrm{ResidentID}
}
$$

MACR 不得根據：

```text
model
name
persona label
project
writing style
```

自行推測 resident identity。

---

# 28. Multi-Agent 不作為 v0.7.0 的必要條件

v0.7.0 首要目標是：

> **一個 Agent 可以安全地持續工作。**

而不是：

> **很多 Agent 可以互相聊天。**

因此 v0.7.0 acceptance 不要求：

```text
Group Chat
Swarm
Society
Voting
Debate
```

Multi-Agent 應建立在 single-Agent semantics 完成後。

---

# 29. Multi-Agent 的正式方向

未來多 Agent 應形成：

```text
Parent Agent
   ├─ Cognitive Agent A
   ├─ Cognitive Agent B
   ├─ Verifier
   └─ Specialist
```

或者真正獨立：

```text
Agent A
Agent B
Agent C
```

但要分清：

$$
\boxed{
\mathrm{MultiModel}
\neq
\mathrm{MultiAgent}
}
$$

以及：

$$
\boxed{
\mathrm{ManyResponses}
\neq
\mathrm{AgentSociety}
}
$$

---

# 30. Delegation Contract

建議：

```json
{
  "schema": "macr-agent-delegation/v1",
  "parent_run_id": "ar:parent",
  "child_run_id": "ar:child",
  "goal_projection": {},
  "context_projection": {},
  "capability_projection": [],
  "authority_projection": [],
  "budget_projection": {},
  "return_contract": {},
  "expiry": "..."
}
```

child 不得：

- 自行提升 authority；
- 自行提高 budget；
- 修改 parent goal；
- 假裝 parent approval；
- 將自己的 result 當成 parent canonical decision。

---

# 31. MRMIC Recursive Workspace 與 Cognitive Delegation

MRMIC/NVCL 已有 recursive subcanvas。

未來可自然對應：

```text
Parent AgentRun
→ parent workspace
→ spawn child AgentRun
→ open child subcanvas
→ child work
→ verify
→ fold result
```

失敗時：

```text
child failure
→ retain evidence
→ discard or restore workspace projection
→ parent continues
```

這是一個比 shared-chat 更具體的 cognitive delegation topology。

---

# 32. Agent World Binding

AgentRun 應顯式記錄它綁定哪些世界。

例如：

```text
repository
filesystem
browser
MRMIC canvas
terminal
SEDB dataset
AI Board
Gmail
Google Drive
simulation
remote API
```

WorldBinding：

```json
{
  "provider": "github",
  "resource": "repo:owner/name",
  "observation_mode": "structured",
  "mutation_mode": "proposal_only",
  "authority_ref": "auth:...",
  "projection_provider": "pncw"
}
```

---

# 33. World 不要求單一資料格式

不同世界可以是：

```text
graph
table
file tree
visual canvas
text
event stream
database
spacetime domain
API state
```

PNCW 與 EML-U conceptual IR 的目的，就是避免：

```text
everything must become chat messages
```

---

# 34. Context Construction

Agent context 不應等於「所有歷史都塞給模型」。

Context Builder 可根據：

```text
current goal
world projection
semantic graph
recent actions
open failures
constraints
authority
budget
verification
relevant memory
```

建構 task-local cognitive context。

因此：

$$
C_t
\subseteq
M_t^{available}
$$

而：

$$
\boxed{
\mathrm{AvailableMemory}
\neq
\mathrm{ActiveContext}
}
$$

---

# 35. Context 不得授予 Authority

即使某 private memory 中寫：

```text
always allow deployment
```

也不能成為 authority。

$$
\boxed{
\mathrm{RetrievedText}
\neq
\mathrm{AuthorityEvidence}
}
$$

---

# 36. Planner

Planner 可以是：

```text
LLM
deterministic rule
hybrid
multi-worker synthesis
search
simulation
GCM-selected computation strategy
```

MACR 不應把 planner 綁定單一 foundation model。

Planner 產生：

```text
PlanCandidate
```

而不是 command。

---

# 37. Plan Revision

每次重大 observation 改變時，舊 plan 可以變成 stale。

因此需要：

```text
plan_id
plan_revision
basis_projection_refs
goal_revision
assumptions
```

若 basis 已改變：

$$
\boxed{
\mathrm{PlanValidity}_{t}
\not\Rightarrow
\mathrm{PlanValidity}_{t+1}
}
$$

---

# 38. GCM Future Integration

GCM 可以負責：

- computational form selection；
- resource allocation；
- worker topology；
- projection planning；
- model routing candidate；
- cost / latency optimization。

但：

$$
\boxed{
\mathrm{GCMSelection}
\neq
\mathrm{MACRAuthority}
}
$$

GCM 選出「最好怎麼算」不等於「允許做」。

---

# 39. Agent Budget Model

至少分：

```text
token
USD
wall-clock
provider calls
CPU
GPU
memory
storage
network
external side effects
child-agent count
```

預算應能：

```text
hard limit
warning limit
per-step
per-run
per-world
per-provider
```

Agent 不得自行提高自己的 budget ceiling。

---

# 40. Autonomy Envelope

Agent autonomy 不是 boolean：

```text
autonomous = true
```

而應是一個 envelope。

例如：

```json
{
  "allowed_effects": [
    "repository.read",
    "repository.branch.write",
    "test.execute"
  ],
  "forbidden_effects": [
    "release.publish",
    "main.force_push",
    "credential.export"
  ],
  "max_cost_usd": 1.0,
  "max_child_agents": 4,
  "requires_human_for": [
    "irreversible_external_publish"
  ]
}
```

因此：

$$
\boxed{
\mathrm{Autonomy}
=
\mathrm{BoundedDelegatedAuthority}
}
$$

---

# 41. Self-Constraint

沿用 SEDB v0.4B 精神，self-constraint 不應等於要求模型永久自我懷疑。

應施加在 canonical decision boundary。

公共 constraint vocabulary 可包含：

```text
VERIFY
COMPARE
COUNTEREXAMPLE
BACKTRACK
DECOMPOSE
STOP
HUMAN_REVIEW
REOBSERVE
```

這些是 runtime state，不需要 hidden reasoning。

---

# 42. Agent Stop

Stop condition 可以是：

```text
goal satisfied
verification passed
budget exhausted
deadline reached
authority expired
human cancelled
irrecoverable failure
conflict
no progress
reconciliation required
```

Agent 不得因 model 自己輸出：

```text
I am done
```

就直接把 run 標記為成功。

成功需要 runtime-defined completion gate。

---

# 43. Completion

形式上：

$$
Complete(G)
=
GoalSatisfied
\land
RequiredVerification
\land
NoBlockingFailure
\land
RequiredReceiptsPresent
$$

必要時再加入：

$$
HumanApproval
$$

---

# 44. EML-U Completion Independence

EML-U 現階段不構成 MACR v0.7 blocker。

正式關係：

```text
EML-U Conceptual Semantics
        ↓
MACR provisional semantic envelope
        ↓
MACR v0.7 runtime
```

未來：

```text
EML-U MVP
        ↓
compatibility mapping
        ↓
canonical semantic IR migration
```

因此：

$$
\boxed{
\mathrm{EML\text{-}U\ NotImplemented}
\not\Rightarrow
\mathrm{MACR\ v0.7\ Blocked}
}
$$

---

# 45. No Duplicate Reimplementation Principle

MACR v0.7 不應重新實作所有子系統。

禁止形成：

```text
MACR own PNCW
MACR own Canvas
MACR own SEDB
MACR own identity registry
MACR own software spacetime
MACR own semantic language
```

正確方式：

```text
MACR
  ↔ versioned contract
  ↔ adapter
  ↔ independently governed subsystem
```

---

# 46. Canonical Ownership Matrix

| System | Canonical Responsibility |
|---|---|
| MACR | AgentRun、orchestration、provider dispatch、authority/budget、checkpoint、delegation、reconciliation |
| PNCW | World projection、readiness、verification、visibility |
| MRMIC/NVCL | Interactive/visual world、resource portal、workspace、presence、control surface |
| PHOSPHOR Spacetime | temporal/causal semantics、governance、CommandIntent、actuation、measured outcome |
| EML / EML-U | semantic ontology、IR direction、effects、constraints、policies、provenance |
| SEDB | evolving semantic/world state、claims、events、receipts、provenance、dynamic schema |
| LIMEN | host-to-residence identity mediation、private projection envelope |
| GCM | computation strategy / routing / resource selection |
| Provider systems | native resource authority and external side effects |

---

# 47. Cross-System Authority Rule

沒有任何單一系統應因為參與一個流程就自動取得其他系統 authority。

例如：

$$
\boxed{
\mathrm{MACRAgentAuthority}
\not\Rightarrow
\mathrm{GitHubAuthority}
}
$$

$$
\boxed{
\mathrm{MRMICControlOwner}
\not\Rightarrow
\mathrm{ProviderResourceOwner}
}
$$

$$
\boxed{
\mathrm{PNCWVisibilityAuthority}
\not\Rightarrow
\mathrm{MutationAuthority}
}
$$

---

# 48. Security Model

v0.7 security 不建立在：

```text
prompt says don't
```

而是：

```text
identity
authority envelope
capability registry
provider adapter
effect classification
budget
sandbox
checkpoint
receipt
verification
audit
```

共同構成。

---

# 49. Sandbox

Sandbox 是 v0.7 的重要 external primitive，但 sandbox 不等於全部 security。

$$
\boxed{
\mathrm{Sandbox}
\neq
\mathrm{AuthorityModel}
}
$$

即使 action 在 sandbox 裡：

```text
credential exfiltration
network abuse
external API side effect
```

仍可能發生。

因此 sandbox 必須與 authority/effect model 並用。

---

# 50. Human-in-the-Loop

Human approval 不應成為所有 step 的預設。

否則 Agent 退化為 expensive autocomplete。

應依 effect 決定：

```text
AUTO
AUTO_WITH_VERIFY
PROPOSE_ONLY
REQUIRE_APPROVAL
FORBIDDEN
```

例如：

```text
read source                 AUTO
run local tests             AUTO
write reversible branch     AUTO_WITH_VERIFY
merge main                  REQUIRE_APPROVAL
publish public release      REQUIRE_APPROVAL
export credentials          FORBIDDEN
```

實際 policy 由 deployment 決定。

---

# 51. Event Model

Agent Runtime 應採 append-oriented observable event model。

例如：

```text
AGENT_RUN_CREATED
GOAL_BOUND
WAKE_RECEIVED
OBSERVATION_REQUESTED
OBSERVATION_VISIBLE
PLAN_CREATED
ACTION_PROPOSED
ACTION_AUTHORIZED
ACTION_DENIED
ACTUATION_DISPATCHED
RECEIPT_CAPTURED
OUTCOME_VERIFIED
CHECKPOINT_CREATED
AGENT_SUSPENDED
AGENT_RESUMED
AGENT_COMPLETED
RECONCILIATION_REQUIRED
```

event metadata 應 content-aware 但 privacy bounded。

---

# 52. Event 與 State 分離

$$
\boxed{
\mathrm{EventHistory}
\neq
\mathrm{CurrentState}
}
$$

Current state 可以重建。

歷史 evidence 不應因 current state 改變而消失。

---

# 53. Deterministic Boundary

MACR v0.7 不要求 LLM decision deterministic。

但 deterministic components 必須 deterministic：

```text
schema validation
identity derivation
authority resolution
budget arithmetic
checkpoint digest
event ordering constraints
canonical serialization
policy evaluation where rules are deterministic
```

---

# 54. Model Nondeterminism Is Not Runtime Nondeterminism

即使模型每次可能提出不同 plan：

$$
P_1 \neq P_2
$$

runtime 對同一 proposal 的 authority verdict 應該穩定：

$$
Gate(P_1)
$$

與 deterministic policy 一致。

---

# 55. Agent Observability

需要觀察：

```text
current goal
current state
active plan
last verified observation
pending actions
authority
budget
children
failures
wake conditions
checkpoint
```

但不要求顯示 private CoT。

---

# 56. Agent UI

未來 Agent UI 可以存在於：

- MACR Direct/Agent UI；
- MRMIC Canvas；
- terminal；
- browser；
- AI Space；
- project-specific surface。

但 UI 不得成為 Agent canonical state owner。

---

# 57. Agent as World Participant

Agent 不只「使用工具」。

它應被視為 software world 中的一個 actor。

因此：

```text
Agent
↔ World
```

關係包含：

```text
observe
project
interpret
propose
act
verify
remember
wait
resume
```

這就是 Agent-Spacetime 名稱的來源。

---

# 58. Software-Spacetime Agent Definition

Agent 在時間 $t$ 的 runtime state：

$$
A(t)
$$

World state：

$$
W(t)
$$

Agent 實際可見的不是 $W(t)$，而是 projection：

$$
O_A(t)
=
\Pi_A(W(t))
$$

Agent 提出 action：

$$
a_t
=
f(
G,
O_A(t),
\Sigma_t
)
$$

通過 gate 後：

$$
a_t^{*}
=
Gate(a_t)
$$

World transition：

$$
W(t+1)
=
T(
W(t),
a_t^{*},
E_t
)
$$

其中 $E_t$ 為外部事件。

Agent 必須重新觀察：

$$
O_A(t+1)
=
\Pi_A(W(t+1))
$$

不能假設：

$$
Expected(W(t+1))
=
Observed(W(t+1))
$$

---

# 59. Agent-Spacetime Closed Loop

最終 canonical closed loop：

$$
\boxed{
\begin{aligned}
Goal/Trigger
&\rightarrow AgentRun\\
&\rightarrow VerifiedObservation\\
&\rightarrow SemanticWorkingState\\
&\rightarrow Plan\\
&\rightarrow ActionProposal\\
&\rightarrow Authority/Capability/Budget\\
&\rightarrow CommandIntent\\
&\rightarrow Actuation\\
&\rightarrow Receipt\\
&\rightarrow ReObservation\\
&\rightarrow IndependentVerification\\
&\rightarrow EvolutionCommit\\
&\rightarrow Checkpoint\\
&\rightarrow Continue/Suspend/Stop
\end{aligned}
}
$$

---

# 60. Proposed v0.7 Implementation Line

本文件只固定 architecture，不強迫工程精確照以下 minor version，但推薦：

## v0.7.0 — Bounded Autonomous Agent Core

最低完成：

```text
AgentRun
Goal
single Agent
bounded autonomous loop
action proposal
authority/budget gate
tool/provider capability
checkpoint
resume
stop
failure/reconciliation
```

不要求 Multi-Agent。

---

## v0.7.1 — Verified World Projection

正式接：

```text
PNCW Observation Contract
VerifiedObservationRef
world binding
stale observation handling
```

---

## v0.7.2 — Semantic Working Graph

加入：

```text
MACR Semantic Envelope
Goal/Observation/Plan/Action/Receipt nodes
relations
effects
constraints
provenance
```

保持 EML-U compatible direction。

---

## v0.7.3 — Agent Spacetime

加入：

```text
suspend
wake
timer
external event
deadline
causal references
PHOSPHOR integration
```

---

## v0.7.4 — Dynamic Evolution State

接 SEDB vNext：

```text
claims
world distinctions
semantic state
evolution
decision/commit history
```

---

## v0.7.5 — Cognitive Sub-Agent Runtime

加入：

```text
spawn
delegate
join
verify
retire
authority projection
budget projection
```

---

# 61. v0.7.0 Minimum Acceptance Scenario

一個最小 AgentRun：

> 檢查一個本機 repository，找出失敗測試原因，提出並實作可回復修復，在 sandbox/branch 中跑測試，驗證修復後回報。

流程必須真正包含：

```text
Goal
→ inspect
→ observe repo
→ plan
→ read
→ test
→ identify failure
→ propose patch
→ authority gate
→ apply candidate patch
→ rerun tests
→ independent result verification
→ checkpoint
→ completion
```

並證明：

- model failure 不等於 host failure；
- failed patch 不會直接污染 canonical branch；
- retry 不會造成未知重複 effect；
- authority 可以拒絕；
- budget 可以停止；
- checkpoint 可 resume；
- success 必須通過 verification。

---

# 62. v0.7.0 Negative Controls

至少測試：

```text
tool exists but authority absent
authority exists but capability absent
budget exhausted
stale observation
action after authority expiry
provider returns malformed result
provider timeout before effect
unknown outcome after dispatch
checkpoint tampering
blind resume of stale action
Agent self-proposes authority expansion
child Agent requests parent-only capability
receipt claims success but world unchanged
world changed differently than expected
verification failure after apparent success
```

---

# 63. External Framework Adoption Matrix

所有外部 framework primitive 應被分類：

```text
ADOPT
ADAPT
REIMPLEMENT
REJECT
DEFER
```

例如：

| Primitive | Direction |
|---|---|
| durable scheduler | ADOPT / ADAPT |
| checkpoint store | ADAPT |
| sandbox | ADOPT / ADAPT |
| browser automation | ADOPT |
| provider-specific tool calling | ADAPTER ONLY |
| external Agent ontology | REJECT |
| shared-chat-as-multi-agent | REJECT AS CORE |
| tracing UI | ADOPT / ADAPT |
| workflow persistence | ADAPT |
| semantic graph ontology | INTERNAL CANONICAL |
| authority semantics | INTERNAL CANONICAL |

---

# 64. Anti-Patterns

MACR v0.7 應明確拒絕：

## 64.1 Prompt-Only Authority

```text
You are allowed to...
```

不能取代 runtime authority。

---

## 64.2 Tool List Equals Permission List

看得到 tool 不代表可以呼叫。

---

## 64.3 Conversation Equals Memory

conversation history 不是完整 memory architecture。

---

## 64.4 Agent Equals Model

換 model 不應讓 Agent identity/state 被摧毀。

---

## 64.5 Shared Chat Equals Multi-Agent

多個 prompt role 不等於真正多 Agent runtime。

---

## 64.6 Retry Everything

任何 unknown-after-dispatch 都不能 blind retry。

---

## 64.7 Receipt Equals Truth

provider receipt 不是 world verification。

---

## 64.8 UI Equals World

visual projection 不是 canonical provider resource。

---

## 64.9 EML-U Theory Equals Implemented Runtime

Conceptual semantics 不得被宣稱為 executable implementation。

---

## 64.10 Central Monolith

MACR 不應吞併所有 EveMissLab 子系統。

---

# 65. Formal Maturity Vocabulary

v0.7 文件統一使用：

### IMPLEMENTED

已有 executable source。

### VALIDATED

已有執行 evidence。

### INTEGRATION-READY

已有足夠 contract 可開始 adapter integration。

### CONCEPT-ADOPTED

概念成為 canonical architecture，但 runtime 尚未完成。

### PLANNED

已知方向，尚未成為正式 contract。

### OPEN

仍需研究或設計。

---

# 66. Current Maturity Mapping

| Component | Status for MACR v0.7 |
|---|---|
| MACR v0.6 runtime core | IMPLEMENTED / VALIDATED |
| MACR Agent Plane | PLANNED |
| PNCW projection lifecycle | IMPLEMENTED / VALIDATED |
| PNCW full perception-actuation loop | OPEN |
| MRMIC/NVCL Visual World | IMPLEMENTED / VALIDATED in bounded scope |
| PHOSPHOR Spacetime | IMPLEMENTED / VALIDATED in reference scope |
| EML-P | IMPLEMENTED |
| EML-U ontology | CONCEPT-ADOPTED |
| EML-U complete runtime | OPEN |
| SEDB v0.4B autonomy kernel | IMPLEMENTED / VALIDATED |
| SEDB general Agent/world state abstraction | PLANNED |
| LIMEN identity mediation | IMPLEMENTED in bounded phases |
| persistent Resident Agent integration | PLANNED |
| MACR Multi-Agent | PLANNED |
| unrestricted autonomous system | NOT CLAIMED |

---

# 67. Final Architecture

MACR v0.7 的最終收斂圖：

```text
                  Human / System / Event
                           │
                           ▼
                    Goal / Trigger
                           │
                           ▼
                 ┌──────────────────┐
                 │   MACR AgentRun  │
                 │ orchestration    │
                 │ budget/authority │
                 │ checkpoint       │
                 └────────┬─────────┘
                          │
             observation  │
                          ▼
                 ┌──────────────────┐
                 │       PNCW       │
                 │ verified world   │
                 │ projection       │
                 └────────┬─────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │ Semantic Working State │
              │ EML-U-compatible IR    │
              └──────────┬─────────────┘
                         │
                         ▼
                    Plan / Proposal
                         │
                         ▼
                MACR Effect / Authority
                  Capability / Budget
                         │
                         ▼
              ┌────────────────────────┐
              │ PHOSPHOR Spacetime     │
              │ CommandIntent          │
              │ Actuation / Causality  │
              └──────────┬─────────────┘
                         │
                         ▼
               Native World Providers
        ┌────────────┬────────────┬───────────┐
        │ GitHub     │ Browser    │ Filesystem │
        │ Terminal   │ APIs       │ Services   │
        └────────────┴────────────┴───────────┘
                         │
                         ▼
                       Receipt
                         │
                         ▼
                 PNCW Re-observation
                         │
                         ▼
               Independent Verification
                         │
                         ▼
             SEDB / Evolving State Plane
                         │
                         ▼
                      Checkpoint
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
         Continue      Suspend        Stop
                          │
                          ▼
                        Wake
```

MRMIC/NVCL 可以同時跨越：

```text
World Provider
Observation Surface
Interactive Workspace
Resource Portal
Agent Presence Surface
```

但不取得 external provider canonical authority。

LIMEN 則在需要 persistent private Residence identity 時從 MACR AgentRun 側接，不進入所有普通 AgentRun 的 mandatory path。

---

# 68. Core Thesis

MACR v0.7 的核心不是：

> 給模型更多工具。

而是：

> **建立一個可讓 AI 在軟體時空中持續存在、觀察、規劃、行動、等待、重新觀察、驗證與恢復，同時保持世界狀態、權限、身份、認知與計算彼此不被錯誤折疊的 Runtime。**

可以形式化為：

$$
\boxed{
\mathrm{Agent}
=
\mathrm{Persistent\ Governed\ Process}
\;\mathrm{within}\;
\mathrm{Software\ Spacetime}
}
$$

其基本循環不是：

$$
Prompt
\rightarrow
Answer
$$

而是：

$$
\boxed{
Observe
\rightarrow
Interpret
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
Continue
}
$$

而當世界暫時不需要它工作時：

$$
\boxed{
Continue
\rightarrow
Suspend
\rightarrow
Wake
\rightarrow
Reobserve
}
$$

這才是 MACR 從 v0.6 的 heterogeneous AI worker runtime，跨入 v0.7 Agent-Spacetime Runtime 的真正版本邊界。

---

# 69. Canonical Closure Statement

本 v0.1 文件固定以下決策：

1. MACR v0.7 正式進入 Agent Runtime。
2. Direct Chat、Worker、AgentRun 保持分離。
3. Model、Agent、Resident 保持分離。
4. PNCW 作為 Verified World Projection substrate。
5. MRMIC/NVCL 作為首個 Visual / Interactive World Provider。
6. PHOSPHOR Spacetime 提供 temporal / causal / actuation reference semantics。
7. EML-U 概念被採用為 semantic ontology / IR direction，但不是 v0.7 runtime dependency。
8. SEDB 作為 evolving semantic/world state substrate 候選，後續需要 general-object abstraction。
9. LIMEN 只在需要 Residence identity/private projection 時介入。
10. Capability、Authority、Budget、Planning、Actuation、Receipt、Verification 永不折疊。
11. v0.7.0 優先完成 single bounded autonomous Agent，而不是先做 Multi-Agent。
12. 外部開源框架只能提供 primitives，不得成為 MACR canonical ontology。
13. Agent canonical state 不要求保存 hidden chain-of-thought。
14. Agent autonomy 被定義為 bounded delegated authority，而不是 unrestricted freedom。
15. Agent 必須存在於時間中，因此 suspend / wake / stale-world re-observation 是核心語義，而非附加功能。

因此：

$$
\boxed{
\mathrm{MACR\ v0.7}
=
\mathrm{Agent\text{-}Spacetime\ Runtime}
}
$$

並以此作為後續 specification、implementation plan、schema design、test matrix 與 v0.7 engineering work 的 canonical architecture anchor。

---

## Appendix A — Primary Engineering Source Map

```text
MACR
  README.md
  docs/ARCHITECTURE.md
  docs/V060A1_OFFLINE_CHECKPOINT.md

PNCW
  README.md
  docs/whitepaper/PNCW_Runtime_Technical_Whitepaper_v0.1.md
  contracts/*

MRMIC_NVCL
  README.md
  VERSION
  docs/ARCHITECTURE.md
  docs/PHASE13_CANVAS_FIRST_PMW.md

PHOSPHOR Spacetime
  README.md
  docs/architecture/README.md
  schemas/*

Efficient New Language / EML
  docs/EML-AI-SEMANTIC-SPEC-v1.5.md
  docs/EML-U-PROFILE.md
  docs/EML_Universal_Semantic_Overlay_2026_v2.0.md

SEDB
  README.md
  current/docs/RELEASE_NOTES_v0.4B.md

LIMEN
  README.md
```

---

## Appendix B — First Engineering Follow-Up Documents

本架構完成後，後續工程文件應依序收斂：

```text
01. MACR v0.7 AgentRun Canonical State Specification
02. MACR v0.7 Agent Semantic Envelope Specification
03. MACR v0.7 Action / Authority / Effect Contract
04. MACR × PNCW Observation Bridge Specification
05. MACR × PHOSPHOR Spacetime Actuation Bridge Specification
06. MACR v0.7 Checkpoint / Suspend / Wake Specification
07. MACR v0.7 Single-Agent MVP Implementation Plan
08. MACR v0.7 Verification & Negative-Control Matrix
09. External Agent Framework Primitive Adoption Matrix
10. SEDB vNext Agent/World State Adaptation Proposal
```

這十份文件完成後，才進入 MACR v0.7.0 的正式工程實作。