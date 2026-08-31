# MACR v0.7 — External Agent Framework Primitive Adoption Matrix v0.1

## 外部 Agent Framework、Durable Runtime、Browser、Sandbox、MCP 與 Observability Primitive 採用矩陣 v0.1

**Document ID:** `MACR-V07-EAFPAM-2026-v0.1`  
**Parent Architecture:** `MACR-ASR-CCA-2026-v0.1`  
**Implementation Plan:** `MACR-V07-SINGLE-AGENT-MVP-PLAN-2026-v0.1`  
**Verification Baseline:** `MACR-V07-VNCM-2026-v0.1`  
**Project:** MACR  
**Target:** MACR v0.7.x Agent-Spacetime Runtime  
**Date:** 2026-08-30  
**Status:** Canonical External Primitive Adoption Policy v0.1  
**Organization:** EveMissLab / 一言諾科技有限公司  
**Language:** Traditional Chinese

---

# 摘要

MACR v0.7 不需要從零重新實作所有 Agent 工程基礎。

2026 年現有開源與公開 Agent ecosystem 已經具備大量成熟 primitive，包括：

- durable execution；
- checkpoint；
- graph/workflow orchestration；
- human-in-the-loop；
- tracing；
- tool guardrail；
- agent handoff；
- sandbox；
- browser automation；
- MCP；
- process isolation；
- long-running workflow；
- event-driven flow；
- provider-neutral telemetry。

例如 LangGraph 已將 durable execution、checkpoint persistence、pending writes、human-in-the-loop 與 fault-tolerance 作為核心 runtime 能力；其 checkpointer abstraction 亦已有 SQLite、Postgres 等實作。

Microsoft Agent Framework 現行 Workflow 亦已支援 checkpoint、resume、rehydration，以及 in-memory、file、Cosmos DB 等 checkpoint storage；pending human requests 也能被 checkpoint 並在 resume 後重新送出。

OpenAI Agents SDK 則提供 handoff、tool/agent guardrails 與 tracing，其中 tracing 可以記錄 agent run、model generation、tool、handoff、guardrail 等 span。

Temporal 提供跨 crash、network failure、長時間等待後的 durable workflow continuation。

Playwright 已明確支援 browser scripting、testing 與 AI-agent browser automation，並同時提供 CLI 與 MCP 介面。

因此問題不是：

> **MACR 能不能使用外部技術？**

而是：

> **哪些東西可以拿，拿到哪一層，以及哪些語義永遠不能外包？**

本文件正式採用：

$$
\boxed{
\mathrm{Reuse\ Engineering}
\neq
\mathrm{Outsource\ Architecture}
}
$$

外部 ecosystem 可以提供：

```text
mechanism
library
transport
driver
scheduler
sandbox
telemetry
```

但不得成為 MACR 以下領域的 canonical owner：

```text
Agent ontology
AgentRun identity
Authority semantics
Effect semantics
Verified Observation
Semantic IR
World model
Checkpoint meaning
Reconciliation
Completion truth
Resident identity
```

---

# 0. Canonical Adoption Vocabulary

所有 external primitive 一律分類為：

```text
ADOPT
ADAPT
REIMPLEMENT
REFERENCE_ONLY
REJECT
DEFER
```

---

# 1. ADOPT

含義：

> 可直接使用其 library / protocol / implementation 作為 MACR 的 bounded infrastructure dependency。

但仍需：

```text
version pinning
license audit
security audit
adapter boundary
conformance tests
```

---

# 2. ADAPT

含義：

> 採用外部 mechanism，但必須包在 MACR interface 內，不能直接暴露外部 ontology。

例如：

```text
Playwright
→ MacrBrowserProvider
```

而不是：

```text
Agent
→ Playwright directly
```

---

# 3. REIMPLEMENT

含義：

> 外部已有類似能力，但 MACR canonical semantics與它差異太大，核心必須自己實作。

可以借鑑 design。

---

# 4. REFERENCE_ONLY

含義：

> 用來研究實作模式、failure modes、API ergonomics、test ideas。

不加入 runtime dependency。

---

# 5. REJECT

含義：

> 該 primitive / abstraction若成為 core，會破壞 MACR 已固定的 canonical invariants。

不是說外部專案不好。

而是：

> 不適合作為 MACR canonical layer。

---

# 6. DEFER

含義：

> 可能有價值，但 v0.7.0a1 不需要現在決定或導入。

---

# 7. Fundamental Adoption Rule

任何外部 component $X$：

$$
Adoptable(X)
=
MechanismUseful(X)
\land
SemanticBoundaryPreserved(X)
\land
AuthorityBoundaryPreserved(X)
\land
RecoveryCompatible(X)
\land
VerificationCompatible(X)
$$

只要任何一項為 false：

不直接 ADOPT。

---

# 8. Non-Outsource Zone

以下正式列為：

## MACR Canonical Non-Outsource Zone

```text
AgentRun
Goal authority
Agent lifecycle
Agent epoch / revision
Semantic Working State
ActionProposal
EffectSet
Authority Envelope
Budget
Admission
VerifiedObservationRef
Completion gate
Reconciliation
Checkpoint semantics
Wake semantics
Resume semantics
Delegation authority projection
```

---

# 9. Why

因為這些 object共同決定：

> **Agent 是誰、知道什麼、能做什麼、現在是否安全、世界究竟發生了什麼。**

若它們由第三方 framework 定義，MACR 只剩一層 wrapper。

---

# 10. Master Primitive Matrix

| Primitive | Candidate ecosystem | Decision | MACR Strategy |
|---|---|---|---|
| Agent ontology | LangChain / OpenAI / Microsoft / CrewAI | **REJECT** | MACR own |
| AgentRun lifecycle | Agent frameworks | **REIMPLEMENT** | MACR own |
| Semantic Working Graph | LangGraph state / external memory | **REIMPLEMENT** | ASE / EML-U direction |
| Durable checkpoint mechanism | LangGraph / Microsoft AF / Temporal | **REFERENCE_ONLY → ADAPT later** | MACR v0.7 own first |
| Local scheduler | Temporal / framework schedulers | **REIMPLEMENT v0.7** | bounded local scheduler |
| Future distributed durable runtime | Temporal | **DEFER / ADAPT candidate** | optional backend |
| Handoff | OpenAI Agents / MAF / LangGraph | **REFERENCE_ONLY** | MACR DelegationContract |
| Multi-Agent topology | CrewAI / Auto patterns / OpenAI | **REFERENCE_ONLY** | future MACR child AgentRun |
| Tool discovery | MCP | **ADOPT protocol** | strict MACR capability adapter |
| Tool authority | MCP annotations / framework tools | **REJECT** | MACR authority only |
| Browser driver | Playwright | **ADAPT / strong ADOPT candidate** | BrowserProvider |
| Browser agent ontology | Browser Use / agent wrappers | **REFERENCE_ONLY / DEFER** | specialized worker only |
| Sandbox interface | Docker/E2B/Daytona | **ADAPT** | SandboxProvider ABI |
| Specific sandbox vendor | Docker/E2B/Daytona | **DEFER** | provider choice after audit |
| Observability transport | OpenTelemetry | **ADOPT** | telemetry projection |
| Vendor agent tracing | OpenAI/LangSmith/etc. | **DEFER / optional adapter** | not canonical evidence |
| Guardrail hook pattern | OpenAI Agents etc. | **REFERENCE_ONLY / ADAPT pattern** | Action Gate owns decision |
| Human approval UX | MAF/OpenAI/etc. | **REFERENCE_ONLY** | MACR approval contract |
| Flow DAG engine | LangGraph / CrewAI / MAF | **REFERENCE_ONLY** | execution graph ≠ semantic graph |
| Long-running workflow backend | Temporal | **DEFER** | post-v0.7 evaluation |
| Memory store abstraction | agent frameworks | **REJECT as canonical memory** | multiple MACR memory planes |
| External Agent-as-Tool | OpenAI / LangGraph | **ADAPT later** | child AgentRun adapter |
| MCP Resources | MCP | **ADOPT transport semantics** | observation candidate only |
| MCP Tools | MCP | **ADOPT transport semantics** | ActionProposal required |
| MCP Sampling | MCP | **DEFER** | no authority delegation |
| Sandboxed code execution | Docker/E2B/Daytona | **ADAPT** | bounded compute provider |
| Process supervision | OS/runtime libraries | **ADOPT/ADAPT** | implementation primitive |
| Event telemetry | OpenTelemetry | **ADOPT** | projection of canonical events |
| Canonical event ledger | OpenTelemetry/vendor tracing | **REJECT as source of truth** | MACR event store |

---

# 11. Framework-Level Position

外部 framework 不應以：

```text
Which framework wins?
```

的方式選擇。

應拆成：

```text
Which primitive is useful?
```

---

# 12. LangGraph

## Current Relevant Capabilities

LangGraph 現行定位是 low-level agent orchestration runtime，其主要能力包括：

```text
durable execution
checkpoint persistence
human-in-the-loop
streaming
fault tolerance
state inspection
```

Checkpoint 按 execution super-step 保存，並支援 thread state、pending writes、SQLite/Postgres 等 checkpointer implementations。

---

# 13. LangGraph Strong Points for MACR Research

```text
checkpoint abstraction
pending-write recovery
thread/checkpoint separation
interrupt/resume UX
subgraph persistence modes
state history
```

其 subgraph persistence亦明確區分 per-invocation、per-thread 與 stateless modes。

---

# 14. LangGraph Decision

### Durable Execution

```text
REFERENCE_ONLY for v0.7.0a1
```

### Checkpointer Interface

```text
REFERENCE_ONLY
possible ADAPT after v0.7
```

### Graph Engine

```text
REFERENCE_ONLY
```

### Agent Ontology

```text
REJECT
```

---

# 15. Why Not Directly Build MACR on LangGraph

MACR 已要求：

```text
AgentRun != Conversation Thread
Checkpoint != Replay
UnknownAfterDispatch != ordinary node failure
Receipt != Verification
Observation != State Dictionary
Authority != graph routing condition
```

如果 AgentRun直接成為 LangGraph thread：

許多語義會被錯誤折疊。

---

# 16. Important LangGraph Difference

LangGraph 的 durable execution會保存 task results以避免 resume時重做已完成 task，並強調 side-effect task應具 idempotency。

這是良好的 workflow工程模式。

但 MACR 必須額外保留：

$$
\boxed{
UnknownAfterDispatch
\neq
RetryableTaskFailure
}
$$

所以不能直接把 external mutation安全問題交給 workflow replay語義。

---

# 17. Microsoft Agent Framework

Microsoft Agent Framework 現行 workflow系統已支援：

```text
typed executors
graph workflows
fan-out/fan-in
events
checkpoints
human input
resume / rehydration
```

並提供 in-memory、file 與 Cosmos checkpoint storage。

---

# 18. MAF Useful Patterns

```text
CheckpointStorage protocol
workflow/executor separation
pending request persistence
human request port
rehydration
superstep checkpoint
```

---

# 19. MAF Human-in-the-Loop

MAF 的 pending request可以隨 checkpoint持久化，resume後重新 emit，這對 MACR：

```text
REQUIRE_APPROVAL
→ SUSPENDED
→ Human response
→ WAKING
```

是一個值得參考的實作模式。

---

# 20. MAF Decision

### Checkpoint Storage Pattern

```text
REFERENCE_ONLY
```

### Request / HITL Pattern

```text
REFERENCE_ONLY / ADAPT UX
```

### Workflow Runtime Dependency

```text
DEFER
```

### Agent Ontology

```text
REJECT
```

---

# 21. OpenAI Agents SDK

OpenAI Agents SDK 現行核心 abstraction包含：

```text
Agent
tools
agents-as-tools
handoffs
guardrails
tracing
```

Agent 本身被定義為帶 instructions、tools與 runtime behavior的 LLM-based abstraction。

---

# 22. OpenAI Agents Useful Primitives

```text
handoff ergonomics
agent-as-tool UX
tool guardrail hook
trace/span hierarchy
custom tracing processor
```

---

# 23. Guardrail Lesson

OpenAI Agents SDK特別區分：

```text
input guardrail
output guardrail
tool guardrail
```

且 tool guardrail可以包在每次 custom tool invocation 前後。

這對 MACR 的啟示是：

> safety / policy hook必須存在於 action boundary，而不能只存在整個 AgentRun的 input/output。

---

# 24. OpenAI Agents Decision

### Handoff

```text
REFERENCE_ONLY
```

### Tool Guardrail Hook Pattern

```text
ADAPT concept
```

### Tracing Export

```text
OPTIONAL ADAPTER
```

### Agent Ontology

```text
REJECT
```

### Agent-as-Tool

```text
ADAPT after child AgentRun exists
```

---

# 25. Why Not Adopt Agent-as-Tool Directly

MACR child Agent必須有：

```text
child AgentRun
goal projection
authority projection
budget projection
return contract
```

而不是只：

```text
call another agent
```

---

# 26. CrewAI

CrewAI Flows 現行提供：

```text
event-driven flow
shared state
conditional execution
loops
structured/unstructured state
Crews + tasks
```

每個 Flow state具有自己的 ID，也提供 state management、event listeners與 workflow routing。

---

# 27. CrewAI Useful Patterns

```text
simple event-driven DSL
developer ergonomics
workflow visualization
flow-level usage accounting
```

---

# 28. CrewAI Decision

### Flow DSL

```text
REFERENCE_ONLY
```

### Multi-Agent Crew Ontology

```text
REJECT as MACR core
```

### Flow State

```text
REFERENCE_ONLY
```

### Usage Aggregation

```text
REFERENCE_ONLY
```

---

# 29. Why

MACR 已經明確要求：

$$
\mathrm{MultiModel}
\neq
\mathrm{MultiAgent}
$$

以及：

$$
\mathrm{AgentRun}
\neq
\mathrm{FlowState}
$$

所以 Crew/Crew Manager不能成為 MACR ontology。

---

# 30. Temporal

Temporal 是一般-purpose durable execution platform，而不是 Agent ontology。

它將 durable workflow continuation作為核心能力，目標包括在 crash、network failure或 infrastructure outage後繼續 long-running process。

---

# 31. Why Temporal Is Different

Temporal不是：

```text
AI Agent Framework
```

而更接近：

```text
Durable Execution Substrate
```

所以長期對 MACR更有價值。

---

# 32. Temporal Candidate Uses

```text
long-duration AgentRun scheduling
durable timers
event wake
workflow persistence
cross-process continuation
distributed workers
```

---

# 33. Temporal Decision

### v0.7.0a1

```text
DEFER
```

### v0.8+ Evaluation

```text
ADAPT candidate
```

---

# 34. Why Defer

v0.7.0a1首先要證明：

> MACR 自己的 AgentRun語義是正確的。

若現在直接放進 Temporal：

```text
Temporal Workflow
```

與：

```text
MACR AgentRun
```

的 responsibility boundary還沒有經 executable proof。

---

# 35. Future Temporal Rule

如果採用：

$$
\boxed{
TemporalWorkflow
\neq
AgentRun
}
$$

Temporal只管理：

```text
durability
timer
worker scheduling
event delivery
```

MACR仍管理：

```text
Agent state
authority
semantic state
reconciliation
completion
```

---

# 36. Temporal Replay Warning

MACR external action不能簡單套入：

```text
workflow replay
```

因為：

$$
WorldSideEffect
\neq
ReplayablePureComputation
$$

所有 external mutation仍要經 MACR Action Gate / reconciliation。

---

# 37. MCP

MCP 是本文件中最適合直接採用的 interoperability primitive之一。

MCP將：

```text
Resources
Prompts
Tools
```

作為不同 server primitives；Resources由 application控制 context inclusion，Tools則可以被 model discovery/invocation。

---

# 38. MCP Decision

### Protocol / Transport

```text
ADOPT
```

### Resource Discovery

```text
ADOPT
```

### Tool Discovery

```text
ADOPT
```

### MCP Tool = Authorized Action

```text
REJECT
```

---

# 39. MCP Capability Rule

MCP server暴露：

```text
tool X
```

只表示：

$$
CapabilityCandidate(X)
$$

不能表示：

$$
Authority(X)
$$

---

# 40. Canonical Rule

$$
\boxed{
MCPTool
\neq
MACRAuthority
}
$$

---

# 41. MCP Security Alignment

MCP specification 本身也要求 implementer把 tool input validation、access controls、rate limits與安全 UI納入設計，且 tool annotations不能在不可信 server上被直接信任。

這與 MACR：

$$
Capability\neq Authority
$$

高度相容。

---

# 42. MCP Tool Adapter

正確流程：

```text
MCP tools/list
↓
Capability Candidate
↓
MACR Effect Derivation
↓
Capability Registry
↓
Agent ActionProposal
↓
MACR Authority Gate
↓
MCP tools/call
```

不是：

```text
tools/list
↓
LLM calls anything
```

---

# 43. MCP Tool Annotation

任何 MCP annotation：

```text
readOnly
destructive
idempotent
etc.
```

最多是：

```text
Effect Hint
```

而不是 authoritative EffectSet。

---

# 44. MCP Resources

MCP Resource可以作：

```text
Observation Candidate
```

但：

$$
\boxed{
MCPResource
\neq
VerifiedObservation
}
$$

若成為 Agent canonical world basis：

仍應經 observation/provenance policy。

---

# 45. MCP Resource Subscription

Resources可有 change notification能力。

這未來可以成為：

```text
Wake Candidate
```

但仍：

$$
ResourceChangedNotification
\neq
VerifiedWorldState
$$

---

# 46. MCP Sampling

Server-initiated sampling / recursive model interaction：

```text
DEFER
```

因為容易造成：

```text
hidden Agent recursion
authority ambiguity
budget ambiguity
```

---

# 47. MCP 2026 Direction

2026-07 的 MCP specification更新仍持續強化 authorization相關協議細節，例如 issuer validation等。

MACR應追蹤 MCP evolution，但：

> MCP authentication / authorization protocol仍不取代 MACR application-level Agent authority semantics。

---

# 48. Browser Automation — Playwright

Playwright是：

```text
browser driver / automation engine
```

而不是 Agent ontology。

它目前支援 Chromium、Firefox、WebKit，也提供 scripting、testing、CLI與 MCP browser控制。

---

# 49. Playwright Decision

### Browser Driver

```text
ADAPT
```

### Underlying Library

```text
Strong ADOPT candidate
```

### Playwright MCP

```text
ADOPT through MCP adapter if appropriate
```

---

# 50. MACR BrowserProvider

建議：

```text
MacrBrowserProvider
```

底下：

```text
Playwright
```

---

# 51. Why Adapter

MACR Action：

```text
browser.click
```

需經：

```text
effect
authority
fresh observation
```

不能讓 planner拿到 raw `page` object直接控制。

---

# 52. Browser State

Playwright accessibility snapshot / DOM / screenshot：

都只是：

```text
Observation Source
```

不是 Agent semantic truth。

---

# 53. Browser Use

Browser Use提供 natural-language browser agent，能執行 extraction、form fill、multi-step workflows與 research等 browser task。

---

# 54. Browser Use Decision

### Browser implementation ideas

```text
REFERENCE_ONLY
```

### Specialized external Worker

```text
DEFER / possible ADAPT
```

### MACR primary browser ontology

```text
REJECT
```

---

# 55. Why

如果未來使用 Browser Use：

應該像：

```text
MACR Agent
↓
bounded browser task
↓
BrowserUseWorker
↓
result/evidence
```

而不是：

```text
BrowserUse Agent
owns MACR AgentRun
```

---

# 56. Sandbox Principle

Sandbox是 MACR v0.7 後續最值得採用的外部 primitive之一。

但：

$$
\boxed{
Sandbox
\neq
Authority
}
$$

---

# 57. SandboxProvider ABI

MACR 應先定義：

```text
SandboxProvider
```

而不是先選 vendor。

---

# 58. SandboxProvider Minimum Interface

```text
create()
destroy()
pause()
resume()

mount_workspace()
run_process()
kill_process()

read_file()
write_file()

network_policy()
resource_limits()

snapshot()
restore()

inspect()
```

---

# 59. Sandbox Identity

每 sandbox：

```text
sandbox_id
provider
instance_id
epoch
workspace binding
network policy
credential policy
resource limits
```

---

# 60. Docker Sandboxes

目前 Docker AI Sandboxes使用 microVM 作 agent isolation，其 default security posture可阻擋未授權 outbound TCP，並隔離 host filesystem/process；credential也可以透過 host-side proxy而不是直接交給 sandbox。

---

# 61. Docker Sandbox Decision

```text
PILOT / ADAPT candidate
```

尤其適合：

```text
coding agent
repository fixture
local development
```

但不直接成為 MACR authority subsystem。

---

# 62. Important Docker Caveat

Sandbox內 Agent可能有很高 sandbox-local權限。

因此：

$$
RootInsideSandbox
\neq
AuthorityOutsideSandbox
$$

---

# 63. Workspace Mount

若 workspace direct read/write mount：

Agent仍可能修改 host working tree。

所以：

```text
sandboxed
```

不自動等於：

```text
safe reversible workspace
```

MACR應偏好：

```text
private clone
temporary worktree
snapshot
```

等隔離方式。

---

# 64. E2B

E2B提供 isolated cloud sandbox、Linux OS、filesystem、commands、PTY與 internet access，並支援 pause/connect等 lifecycle operations。

---

# 65. E2B Decision

```text
DEFER / optional SandboxProvider
```

適合：

```text
cloud isolated compute
remote coding
ephemeral execution
```

不成為 MACR mandatory dependency。

---

# 66. Daytona

Daytona現行 Sandbox亦提供 isolated runtime，以及 Linux container、Linux VM、Windows VM、GPU等環境。

---

# 67. Daytona Decision

```text
DEFER / optional SandboxProvider
```

---

# 68. No Canonical Sandbox Vendor

正式：

$$
\boxed{
MACR.SandboxProvider
\neq
Docker
\neq
E2B
\neq
Daytona
}
$$

---

# 69. Sandbox Security Contract

Sandbox provider必須 machine-readable回報：

```text
network isolation
workspace mode
credential mode
filesystem boundary
resource limit
privilege level
persistence
snapshot support
```

---

# 70. Sandbox Effect Integration

例如：

```text
sandbox.process.execute
```

與：

```text
host.process.execute
```

必須是不同 effect。

---

# 71. Sandbox Escape Assumption

MACR不能宣稱：

> sandbox = impossible escape。

安全模型應該是 layered defense。

---

# 72. Credential Isolation

最理想：

```text
Agent sees credential_ref
provider proxy injects credential
```

而不是：

```text
Agent receives token plaintext
```

Docker現行 sandbox credential proxy模式正是一個值得參考的工程pattern。

---

# 73. Observability

MACR 已經有：

```text
canonical event store
evidence artifacts
AgentRun timeline
```

但需要對外 telemetry。

---

# 74. OpenTelemetry

OpenTelemetry提供跨系統的 traces、metrics、logs與 semantic conventions；2026 年 GenAI observability也已能表達 model call、token usage與 tool execution等 telemetry。

---

# 75. OpenTelemetry Decision

### Export Protocol / SDK

```text
ADOPT
```

### Canonical Agent Evidence Store

```text
REJECT
```

---

# 76. Correct Direction

```text
MACR Agent Events
↓
Telemetry Projection
↓
OpenTelemetry
↓
Collector / Dashboard
```

不是：

```text
OpenTelemetry spans
↓
reconstruct canonical Agent truth
```

---

# 77. Why

Telemetry可能：

```text
sampled
dropped
redacted
exported asynchronously
```

所以不能成為 canonical event ledger。

---

# 78. Trace Correlation

建議映射：

```text
AgentRun → trace
Agent activation → span
Model invocation → span
Observation → span
Action → span
Provider attempt → span
Verification → span
```

---

# 79. Semantic Convention

若 OpenTelemetry GenAI conventions仍 evolving：

MACR自己的：

```text
agent_run_id
action_id
observation_ref
```

作 stable canonical IDs。

OTel attributes只是 projection。

---

# 80. Sensitive Telemetry

prompt / completion content：

預設：

```text
not exported
```

除非 explicit policy。

OpenTelemetry GenAI telemetry本身也把完整 prompt/completion視為可選資料，而不是必要 measurement。

---

# 81. Vendor Tracing

OpenAI Agents tracing、LangSmith、CrewAI tracing等可作 optional export target。

分類：

```text
DEFER / OPTIONAL ADAPTER
```

---

# 82. Why Not Canonical

避免：

```text
provider or framework lock-in
```

也避免 sensitive data semantics由 vendor決定。

---

# 83. Guardrails

External framework常有：

```text
input guardrail
output guardrail
tool guardrail
```

MACR不直接採這個名稱作 authority。

---

# 84. MACR Mapping

```text
Input Guardrail
→ admission/preflight validator

Tool Guardrail
→ Action Gate hook

Output Guardrail
→ return-contract / semantic patch validator
```

---

# 85. Guardrail Decision

```text
ADAPT pattern
REIMPLEMENT semantics
```

---

# 86. Why

MACR的：

```text
Authority
Effect
Budget
Verification
```

比普通 guardrail有更強 canonical meaning。

---

# 87. Human-in-the-Loop

外部 frameworks已證明：

```text
pause
request
human response
resume
```

是實用 primitive。

---

# 88. Decision

### UI / request pattern

```text
REFERENCE_ONLY
```

### Approval semantics

```text
REIMPLEMENT
```

---

# 89. MACR Approval Must Bind Exact Object

```text
proposal_digest
effect_digest
target
expiry
```

不能只是：

```text
human said yes
```

---

# 90. Handoff

OpenAI/Microsoft/LangGraph等皆支援不同形式的 agent delegation。

MACR只採：

```text
ergonomic / execution patterns
```

不採 ontology。

---

# 91. MACR Delegation

正式：

```text
Parent AgentRun
↓
DelegationContract
↓
Child AgentRun
↓
ReturnContract
↓
Join
```

---

# 92. External Handoff Mapping

未來可以：

```text
MACR child AgentRun
→ external agent runtime worker
```

但 external agent只拿到：

```text
bounded task
bounded authority projection
bounded context
```

---

# 93. External Agent as Worker

這是重要 interoperability方向。

例如未來：

```text
OpenAI Agent
LangGraph Agent
CrewAI Crew
BrowserUse
custom MCP agent
```

都可以被包成：

```text
MacrExternalAgentWorker
```

---

# 94. External Agent Worker Is Not Resident

$$
\boxed{
ExternalAgentWorker
\neq
MACRAgentIdentity
}
$$

---

# 95. External Agent Result

回來的只是一個：

```text
candidate
evidence
semantic patch proposal
```

而不是 canonical truth。

---

# 96. Workflow Graph Engines

LangGraph、MAF、CrewAI皆提供 graph/flow orchestration。

MACR可以借：

```text
visualization
execution DAG
fan-out/fan-in
```

pattern。

---

# 97. But

$$
\boxed{
ExecutionGraph
\neq
SemanticGraph
}
$$

這個 invariant不變。

---

# 98. Execution Graph Decision

```text
REFERENCE_ONLY for v0.7
```

後續如果 Agent plan需要 dynamic DAG runtime再重新評估。

---

# 99. Why Not Now

MACR v0.6本來已有：

```text
CoordinationPlan
Topology
T0/T1/T2 direction
```

不應再塞第二套 graph runtime。

---

# 100. Memory Frameworks

LangGraph、CrewAI、Microsoft、OpenAI ecosystem都有 memory/session persistence。

MACR不採：

```text
one framework memory
```

作 canonical。

---

# 101. Memory Decision

```text
REJECT as canonical abstraction
ADAPT external stores as providers
```

---

# 102. Why

MACR已區分：

```text
Working State
Conversation
Evidence
World Projection
Checkpoint
Semantic Knowledge
Residence Memory
Archive
```

將它們重新折疊為：

```text
memory
```

反而倒退。

---

# 103. Process Supervision

這屬真正工程 primitive。

候選：

```text
Python subprocess
Windows Job Objects
Linux process groups/cgroups
supervisor/service manager
sandbox process API
```

---

# 104. Decision

```text
ADOPT / ADAPT
```

依 platform implementation。

不需要 MACR發明 operating system。

---

# 105. Process State

但 process lifecycle仍需映射成：

```text
ProviderAttempt
PendingDependency
Receipt
Failure
```

---

# 106. Retry Libraries

例如 generic retry/backoff libraries：

```text
ADOPT for known-no-effect operations
```

但不允許套在所有 provider calls外層。

---

# 107. Retry Canonical Rule

任何 generic retry utility必須被：

```text
RetryPolicy
```

包住。

---

# 108. Forbidden Generic Decorator

禁止：

```python
@retry
def mutate_external_world():
    ...
```

如果函數可能 unknown-after-dispatch。

---

# 109. Rate Limiting

成熟 external library：

```text
ADOPT
```

但 rate limit不等於 budget。

---

# 110. Queue

一般 local queue / database：

```text
ADOPT
```

但 queue message不等於 authority。

---

# 111. Serialization Library

可以：

```text
ADOPT implementation
```

但 canonical serialization profile由 MACR own。

---

# 112. Database

SQLite：

繼續：

```text
ADOPT
```

作 v0.7 local runtime。

不需要為了 Agent改掉。

---

# 113. Postgres

未來 distributed runtime：

```text
DEFER
```

---

# 114. Redis

如果未來只作：

```text
ephemeral coordination/cache
```

可評估。

不得作 canonical truth唯一來源。

---

# 115. Event Bus

Kafka/NATS等：

```text
DEFER
```

v0.7 single-machine沒有需要。

---

# 116. Overall Framework Decision Matrix

| Ecosystem | Best useful primitive | v0.7 Decision | Canonical role |
|---|---|---|---|
| LangGraph | checkpoint / durable graph patterns | REFERENCE_ONLY | none |
| Microsoft Agent Framework | checkpoint / HITL / executor patterns | REFERENCE_ONLY | none |
| OpenAI Agents SDK | handoff / tool guardrail / tracing ergonomics | REFERENCE_ONLY / optional adapter | none |
| CrewAI | event-driven Flow ergonomics | REFERENCE_ONLY | none |
| Temporal | durable workflow substrate | DEFER | possible future scheduler backend |
| MCP | tools/resources protocol | ADOPT | interoperability transport |
| Playwright | browser driver | ADAPT | browser provider |
| Browser Use | browser-agent worker | DEFER | optional specialized worker |
| Docker Sandboxes | local agent isolation | ADAPT candidate | sandbox provider |
| E2B | remote sandbox | DEFER | optional sandbox provider |
| Daytona | remote/local sandbox | DEFER | optional sandbox provider |
| OpenTelemetry | telemetry standard | ADOPT | observability projection |

---

# 117. v0.7.0a1 Dependency Freeze

最重要決策：

> **MACR v0.7.0a1 Agent Core 在完成前，不新增大型 Agent-framework mandatory dependency。**

---

# 118. Allowed New Dependencies Before Alpha

只有：

```text
small utility
testing
schema
process/sandbox adapter if absolutely needed
```

且有明確理由。

---

# 119. Specifically Not Required for v0.7.0a1

```text
langgraph
langchain
agent-framework
openai-agents
crewai
temporal
browser-use
e2b
daytona
```

都不是完成 Agent Core的 blocker。

---

# 120. Why Dependency Freeze

因為 v0.7目前最重要的是證明：

$$
\boxed{
MACR.AgentSemantics
}
$$

而不是驗證外部 framework能不能工作。

---

# 121. Post-Alpha Adoption Phase

`v0.7.0a1` offline accepted後，再進：

```text
Primitive Integration Phase
```

---

# 122. Integration Order Recommendation

建議順序：

```text
1. OpenTelemetry
2. MCP adapter strengthening
3. Playwright BrowserProvider
4. SandboxProvider ABI
5. one sandbox implementation
6. real PNCW bridge
7. real PHOSPHOR bridge
8. external AgentWorker adapter
9. Temporal feasibility spike
```

---

# 123. Why OpenTelemetry First

Observability：

```text
low semantic risk
high engineering value
```

而且不改 Agent authority。

---

# 124. Why MCP Early

MACR已有 MCP方向與 ecosystem。

而 MCP適合作：

```text
interoperability transport
```

不需要讓它接管 Agent ontology。

---

# 125. Why Browser Next

真 Agent實際價值大量來自：

```text
web world interaction
```

Playwright是低 ontology侵入的成熟 browser primitive。

---

# 126. Why Sandbox Before Broad Computer Use

先建立：

```text
isolated world
```

再給：

```text
terminal
browser
code
```

比直接開 host authority安全。

---

# 127. Why Temporal Later

Temporal真正有價值時：

> MACR開始需要多機、長期、durable Agent orchestration。

v0.7 local single-Agent還不到非用不可。

---

# 128. Adoption Contract

任何外部 dependency加入前必須新增：

```text
ExternalPrimitiveAdoptionRecord
```

---

# 129. Adoption Record

```json
{
  "schema": "macr-external-primitive-adoption/v1",
  "name": "playwright",
  "primitive": "browser_driver",
  "decision": "ADAPT",
  "version": "...",
  "license_review_ref": "...",
  "security_review_ref": "...",
  "adapter_ref": "MacrBrowserProvider",
  "canonical_owner": "MACR",
  "forbidden_semantic_roles": [
    "authority_source",
    "agent_identity_owner"
  ],
  "conformance_ref": "...",
  "digest": "sha256:..."
}
```

---

# 130. License Boundary

本文件不是 License Audit。

任何 `ADOPT / ADAPT` code dependency 在 merge前必須單獨確認：

```text
license
redistribution
NOTICE
copyleft boundary
transitive dependencies
commercial use
```

---

# 131. Security Boundary

同樣：

```text
package reputation
supply chain
network behavior
credential handling
filesystem authority
update policy
```

必須獨立 audit。

---

# 132. Version Pinning

Agent runtime critical dependency不得：

```text
latest
*
floating major
```

無 pin。

---

# 133. Upgrade Policy

外部 major/minor更新：

```text
run conformance
run negative controls
```

不能因 dependency lock更新就自動信任。

---

# 134. Tool Adapter Conformance

任何 external tool adapter至少測：

```text
input schema
effect derivation
authority
timeout
receipt
unknown-after-dispatch
secret handling
```

---

# 135. Browser Adapter Conformance

至少：

```text
navigation
read-only DOM/snapshot
click
form fill
download
upload
authentication boundary
unexpected navigation
popup/new tab
timeout
browser crash
```

---

# 136. Sandbox Adapter Conformance

至少：

```text
host filesystem isolation
workspace bounds
network deny
network allow
credential proxy
resource bounds
process kill
snapshot
restart
cleanup
```

---

# 137. Telemetry Adapter Conformance

至少：

```text
correct AgentRun correlation
no canonical state dependency
sensitive content off by default
export failure does not kill AgentRun
```

---

# 138. External Workflow Backend Conformance

若未來 Temporal/LangGraph等作 backend：

必須證：

```text
AgentRun identity preserved
authority preserved
unknown effect preserved
reconciliation preserved
checkpoint meaning preserved
completion gate preserved
```

---

# 139. Semantic Equivalence Gate

令 native MACR behavior：

$$
M
$$

External-backed behavior：

$$
E
$$

必須：

$$
SemanticProjection(M)
=
SemanticProjection(E)
$$

在 bounded conformance scenarios成立。

---

# 140. Differential Testing

同一 scenario：

```text
MACR native backend
vs
external primitive backend
```

比較：

```text
state transitions
effects
authority verdict
attempt count
receipt
verification
completion
```

---

# 141. No Performance-Only Adoption

外部系統即使：

```text
10x faster
```

只要破壞：

```text
authority
reconciliation
verification
```

不能採。

---

# 142. No Popularity-Based Adoption

GitHub stars、社群熱度、公司規模：

不是 architecture criterion。

---

# 143. No Framework FOMO

MACR 不需要：

```text
support every agent framework
```

---

# 144. External Interop Philosophy

更合理：

```text
MACR
→ ExternalAgentWorkerAdapter
→ many frameworks
```

而不是：

```text
MACR core
= union of every framework
```

---

# 145. Future ExternalAgentWorker ABI

建議：

```text
submit_task()
stream_events()
cancel()
status()
collect_result()
```

---

# 146. Worker Input

只給：

```text
TaskContract
ContextProjection
CapabilityProjection
AuthorityProjection
BudgetProjection
ReturnContract
```

---

# 147. Worker Output

只收：

```text
Candidate
Evidence
Usage
ProviderReceipt
SemanticPatchProposal
```

---

# 148. External Framework Cannot Complete Parent

Child external agent回：

```text
done
```

不能讓 MACR parent AgentRun直接 COMPLETED。

---

# 149. Multi-Agent Future

當 MACR v0.7 Single-Agent完成後，外部 frameworks最值得研究的是：

```text
parallel execution
fan-out/fan-in
agent handoff ergonomics
subagent persistence
```

而不是「角色聊天」。

---

# 150. Research Priority

由高至低：

```text
1. Durable execution
2. Sandbox
3. Browser
4. MCP interoperability
5. Observability
6. Handoff
7. Parallel subagents
8. Agent society / group chat
```

---

# 151. Why Agent Society Last

因為：

$$
\boxed{
OneUnsafeAgent
\times
N
=
N\ UnsafeAgents
}
$$

Multi-Agent不會自動修復單 Agent runtime semantics。

---

# 152. Architecture Ownership Matrix

| Domain | Canonical Owner |
|---|---|
| Agent identity/run | MACR |
| Goal | MACR / host authority |
| Semantic state | ASE / EML-U direction |
| World projection | PNCW |
| Interactive visual world | MRMIC/NVCL |
| Actuation/time | PHOSPHOR |
| Dynamic long-term state | SEDB direction |
| Residence identity | LIMEN / Residence stack |
| Tool/resource protocol | MCP |
| Browser mechanics | Playwright/provider |
| Sandbox mechanics | SandboxProvider implementation |
| Telemetry export | OpenTelemetry |
| Durable distributed scheduling | future backend candidate |

---

# 153. Non-Collapse Matrix

正式保留：

$$
\boxed{
MCPTool
\neq
Authority
}
$$

$$
\boxed{
Sandbox
\neq
Authority
}
$$

$$
\boxed{
BrowserDriver
\neq
Agent
}
$$

$$
\boxed{
Workflow
\neq
AgentRun
}
$$

$$
\boxed{
Trace
\neq
CanonicalEventHistory
}
$$

$$
\boxed{
FrameworkMemory
\neq
MACRMemoryArchitecture
}
$$

$$
\boxed{
Handoff
\neq
AuthorityDelegation
}
$$

$$
\boxed{
CheckpointBackend
\neq
CheckpointSemantics
}
$$

---

# 154. v0.7 Primitive Adoption Decision

正式 v0.1 結論：

## Adopt Now / Early

```text
MCP protocol semantics
OpenTelemetry export
existing SQLite/runtime primitives
OS process supervision primitives
```

---

# 155. Adapt Early After Core

```text
Playwright
SandboxProvider
MCP tool/resource adapters
tool guardrail hook pattern
```

---

# 156. Reference Now

```text
LangGraph
Microsoft Agent Framework
OpenAI Agents SDK
CrewAI
Browser Use
```

---

# 157. Defer

```text
Temporal backend
E2B
Daytona
distributed workflow backend
external AgentWorker frameworks
```

不是因為不好，而是 v0.7.0a1不需要。

---

# 158. Reject as Canonical

```text
external Agent ontology
messages[] as canonical Agent state
tool list as authority
workflow thread as AgentRun identity
framework memory as total memory architecture
receipt as truth
handoff as implicit authority delegation
generic retry around mutation
agent-group-chat as Multi-Agent canonical model
```

---

# 159. Formal Adoption Test

對每個 external primitive $x$：

$$
A(x)
=
Utility(x)
-
SemanticCoupling(x)
-
AuthorityRisk(x)
-
RecoveryRisk(x)
-
LockIn(x)
$$

只有：

$$
A(x)>Threshold
$$

才進 integration spike。

這不是數值實作要求，只是 architecture decision function。

---

# 160. Core Principle

如果一個外部 framework提供：

```text
90% engineering convenience
```

但要求 MACR放棄：

```text
AgentRun
Authority
Reconciliation
VerifiedObservation
```

則：

```text
REJECT
```

---

# 161. Conversely

如果某個 library只做：

```text
browser driving
telemetry
sandbox
process isolation
```

而不碰 Agent ontology：

更容易：

```text
ADOPT / ADAPT
```

---

# 162. Canonical Closure

本文件固定：

1. MACR 不採「選一個 Agent framework當底座」策略。
2. 外部 ecosystem以 primitive extraction方式使用。
3. Agent ontology屬 MACR canonical non-outsource zone。
4. AgentRun lifecycle屬 MACR。
5. ASE / EML-U semantic direction不交給 workflow framework state。
6. PNCW observation semantics不交給 tool return value。
7. Authority不交給 MCP、tool annotations或 guardrail。
8. Reconciliation不交給 generic retry engine。
9. Completion不交給 external Agent `done` output。
10. LangGraph作 durable execution/checkpoint research reference，不作 v0.7 core dependency。
11. Microsoft Agent Framework作 checkpoint/HITL/workflow reference，不作 Agent ontology。
12. OpenAI Agents SDK的 handoff、tool guardrail與 tracing ergonomics值得參考，但不接管 Agent identity。
13. CrewAI Flows作 event-driven UX / workflow pattern reference。
14. Temporal是未來 distributed durable backend的重要候選，但 v0.7.0a1 defer。
15. MCP作 tools/resources interoperability protocol正式 ADOPT。
16. MCP tool existence只代表 capability candidate。
17. MCP Resource只代表 observation candidate。
18. MCP notification可作 wake candidate，但不是 world truth。
19. Playwright是 BrowserProvider的強 ADAPT/ADOPT候選。
20. Browser Use只能作未來 specialized external worker候選。
21. MACR定義 SandboxProvider ABI，不綁單一 sandbox vendor。
22. Docker Sandboxes、E2B、Daytona皆可成 provider候選。
23. Sandbox不等於 authority。
24. sandbox-local root不等於 host/world authority。
25. credential proxy模式優於把 secret plaintext交給 Agent。
26. OpenTelemetry可 ADOPT作 observability projection。
27. OpenTelemetry / vendor trace不能取代 canonical Agent event history。
28. Human approval semantics仍由 MACR own。
29. Handoff semantics仍由 MACR DelegationContract own。
30. workflow graph與 semantic graph保持分離。
31. external framework memory不能取代 MACR多 memory-plane architecture。
32. v0.7.0a1完成前維持大型 Agent framework dependency freeze。
33. v0.7.0a1完成後再按低語義耦合 → 高語義耦合順序導入 external primitives。
34. 每個 external dependency必須有 Adoption Record、version pin、license/security review與 conformance tests。
35. external-backed implementation必須與 native MACR作 differential semantic validation。
36. performance優勢不能覆蓋 authority / reconciliation / verification缺陷。
37. popularity不能作 architecture decision。
38. MACR應支援外部 Agent framework成為 bounded worker，而不是讓它們成為 MACR core。
39. Single-Agent安全 closure優先於 Multi-Agent ecosystem integration。
40. 「會用外部技術」與「被外部技術定義」必須永久分離。

因此：

$$
\boxed{
MACR
=
CanonicalAgentSemantics
+
BestAvailableExternalPrimitives
}
$$

而不是：

$$
\boxed{
MACR
=
ExternalAgentFramework
+
CustomPlugins
}
$$

這完成 MACR v0.7 Agent-Spacetime Runtime 的第九份 canonical engineering document。

---

# Appendix A — Immediate Adoption Queue

```text
P0 — v0.7.0a1 Core
  no major external Agent framework dependency

P1 — Observability / Interop
  OpenTelemetry
  MCP strengthening

P2 — World Interaction
  Playwright BrowserProvider
  SandboxProvider ABI

P3 — Sandbox Implementations
  Docker Sandbox evaluation
  E2B evaluation
  Daytona evaluation

P4 — External Agent Workers
  OpenAI Agent worker
  LangGraph worker
  BrowserUse worker
  other framework workers

P5 — Durable Runtime
  Temporal feasibility / differential spike
```

---

# Appendix B — Adoption Status Summary

```text
ADOPT
  MCP protocol
  OpenTelemetry telemetry
  standard OS/process/database primitives

ADAPT
  Playwright
  SandboxProvider implementations
  tool guardrail patterns
  external AgentWorker APIs

REFERENCE_ONLY
  LangGraph core runtime
  Microsoft Agent Framework
  OpenAI Agents SDK orchestration
  CrewAI Flows
  Browser Use architecture

DEFER
  Temporal backend
  E2B provider
  Daytona provider
  distributed event bus
  distributed scheduler

REIMPLEMENT
  AgentRun
  checkpoint semantics
  semantic working state
  authority/effect/budget
  reconciliation
  completion
  delegation authority

REJECT AS CANONICAL
  external Agent ontology
  framework thread = AgentRun
  tool = authority
  memory = one store
  receipt = verification
  generic retry of world mutation
```

---

# Appendix C — External Primitive Review Checklist

```text
[ ] What exact primitive are we adopting?
[ ] Does it define Agent identity?
[ ] Does it mutate world state?
[ ] Does it have hidden retry behavior?
[ ] Does it have hidden provider fallback?
[ ] How are effects derived?
[ ] How are credentials handled?
[ ] Can it operate behind a MACR adapter?
[ ] Can it preserve AgentRun IDs?
[ ] Can it preserve authority revision/epoch?
[ ] Can it preserve unknown-after-dispatch?
[ ] Can it preserve reconciliation freeze?
[ ] Can its result be independently verified?
[ ] Is persistent state canonical or merely cache?
[ ] Can it be version-pinned?
[ ] License reviewed?
[ ] Security reviewed?
[ ] Negative controls written?
[ ] Differential tests written?
```

---

# Appendix D — Next Canonical Document

下一份：

**10 — SEDB vNext Agent / World State Adaptation Proposal v0.1**

目標是把目前 SEDB 的：

```text
Field
Proposal
Evaluation
Decision
Commit
Provenance
Autonomy Envelope
```

進一步抽象成：

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

使 SEDB 可以成為 MACR v0.7 / v0.8 的 evolving Agent / World semantic-state backend，而不把現有 field-based SEDB 打掉重寫。