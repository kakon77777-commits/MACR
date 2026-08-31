# MACR × PNCW — Verified Observation Bridge Specification v0.1

## MACR Agent 與 PNCW 驗證世界投影橋接規格 v0.1

**Document ID:** `MACR-PNCW-VOBS-BRIDGE-2026-v0.1`  
**Parent Architecture:** `MACR-ASR-CCA-2026-v0.1`  
**Parent State Spec:** `MACR-V07-AGENTRUN-STATE-2026-v0.1`  
**Parent Semantic Spec:** `MACR-V07-ASE-2026-v0.1`  
**Parent Action Spec:** `MACR-V07-AAEC-2026-v0.1`  
**Projects:** MACR / PNCW  
**Target:** MACR v0.7.x / PNCW integration line  
**Date:** 2026-08-30  
**Status:** Canonical Integration Contract / Pre-Implementation  
**Organization:** EveMissLab / 一言諾科技有限公司  
**Language:** Traditional Chinese

---

# 摘要

MACR v0.7 的 Agent 必須能觀察世界。

但「讓 Agent 讀到資料」與「讓 Agent 擁有一個可作為 planning basis 的 verified observation」不是同一件事。

因此：

$$
\boxed{
\mathrm{RawInput}
\neq
\mathrm{WorldObservation}
\neq
\mathrm{VerifiedObservation}
}
$$

MACR 不將模型 context、tool response、API response 或畫面內容直接視為 canonical world truth。

PNCW 已經建立：

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

MACR v0.7 因此將 PNCW 定位為 Agent 的 **Verified Observation Substrate**。

Agent 的觀察流程正式定義為：

```text
ObservationIntent
↓
Observation Planning
↓
PNCW ProjectionRequest
↓
Readiness
↓
Materialization / Surface Preparation
↓
ProjectionManifest
↓
Independent Verification
↓
Visibility Commit
↓
VerifiedObservationRef
↓
ASE Observation Node
↓
Planning Basis
```

此 bridge 不重新實作 PNCW。

MACR 負責：

- Agent 為什麼需要觀察；
- 需要觀察什麼；
- observation 的 task/goal context；
- observation 是否仍適合作為目前 plan basis；
- stale 後如何重新觀察；
- observation 如何進入 ASE；
- action 後何時要求 re-observation；
- observation 如何影響 AgentRun。

PNCW 負責：

- projection request contract；
- source / surface readiness；
- source identity；
- materialization；
- surface binding；
- freshness；
- integrity；
- verification；
- visibility；
- residency semantics。

因此：

$$
\boxed{
\mathrm{MACR\ Observation\ Semantics}
+
\mathrm{PNCW\ Projection\ Semantics}
}
$$

形成 Agent 對世界的 canonical observation path。

---

# 0. Canonical Decision

MACR v0.7 正式採用：

$$
\boxed{
\mathrm{AgentObservation}
=
\mathrm{VerifiedWorldProjection}
}
$$

對需要 canonical planning / action basis 的 mutable world state，不接受：

```text
raw tool response
raw provider text
unverified cache
old screenshot
old serialized VERIFIED object
```

直接成為 authoritative observation。

---

# 1. Observation Is a Projection

令真實外部世界為：

$$
W_t
$$

Agent $A$ 在時間 $t$ 得到的 observation：

$$
O_A(t)
=
\Pi_{A,S,R}(W_t)
$$

其中：

- $A$：observer；
- $S$：scope；
- $R$：representation。

因此：

$$
\boxed{
O_A(t)
\neq
W_t
}
$$

Agent 永遠只看到世界的一個 projection。

---

# 2. Observation Is Observer-Relative

同一 World：

$$
W_t
$$

不同 observer profile：

$$
\Pi_{human}(W_t)
$$

$$
\Pi_{agent}(W_t)
$$

$$
\Pi_{service}(W_t)
$$

可以產生不同 observation。

這不是 contradiction。

---

# 3. Observation Is Scope-Relative

同一 repository：

```text
whole repository
one branch
one file
one AST node
one test failure
```

都是不同 scope。

因此：

$$
\boxed{
\mathrm{ObservedSubset}
\neq
\mathrm{WholeWorldKnowledge}
}
$$

---

# 4. Observation Intent

MACR 新增：

```text
ObservationIntent
```

它描述：

> Agent 為了目前 Goal / Plan，需要知道世界中的什麼。

而不是直接指定 PNCW internal materialization。

---

# 5. ObservationIntent v1

```json
{
  "schema": "macr-observation-intent/v1",
  "observation_intent_id": "obs-intent:...",
  "agent_run_id": "...",
  "agent_run_epoch": 3,

  "goal_ref": "sem:goal:...",
  "plan_ref": "sem:plan:...",
  "task_ref": "sem:task:...",

  "world_binding_ref": "world:...",
  "observation_purpose": "verify_repository_state",

  "requested_scope": {
    "scope_kind": "resource_region",
    "region_refs": [
      "repo:file:src/parser.py"
    ]
  },

  "preferred_representation": "structured",
  "freshness_policy_ref": "freshness:...",
  "verification_requirement": "VERIFIED",

  "intent_digest": "sha256:..."
}
```

---

# 6. ObservationIntent Has No Source Authority

Agent 可以要求：

```text
observe private dataset
```

但：

$$
\boxed{
ObservationIntent
\neq
SourceReadAuthority
}
$$

是否允許讀取仍由 source authority 判斷。

---

# 7. Observation Planning

ObservationIntent 不需要直接對應 exact PNCW representation。

中間可以存在：

```text
ObservationPlan
```

由：

- deterministic rules；
- GCM；
- provider capability；
- PNCW adapter；
- task policy；

共同決定：

```text
representation
scope
carrier
observation mode
materialization budget
```

---

# 8. Planning Does Not Grant Authority

$$
\boxed{
\mathrm{ObservationPlan}
\neq
\mathrm{ProjectionAuthority}
}
$$

即使 planner 認為最佳 representation 是 HMBT1，也不能繞過 source/surface authority。

---

# 9. MACR → PNCW ProjectionRequest

Bridge 將 ObservationIntent 編譯成 PNCW：

```text
pncw-projection-request/v1
```

其核心欄位保持：

```text
requestId
sourceRef
observer
representation
scope
requestedMode
authorityContext
```

MACR 不修改這些語義。

---

# 10. Observer Mapping

MACR Agent：

```text
agent_run_id
agent_ref
```

不直接等於 PNCW observer ID。

建議：

```text
observerId = stable bridge observer reference
observerType = ai
profile = machine-structured / task-specific profile
```

---

# 11. Observer Identity vs Resident Identity

PNCW observer identity：

> 誰在取得 projection。

不等於：

> LIMEN / Residence 中的 persistent Resident identity。

因此：

$$
\boxed{
\mathrm{ProjectionObserver}
\neq
\mathrm{ResidentIdentity}
}
$$

---

# 12. SourceRef

`sourceRef` 指向外部 source adapter 所理解的 canonical source。

例如：

```text
repo:owner/name@branch
sedb:dataset:X
canvas:workspace:X
software-spacetime:domain:X
hdsrc:state:X
```

PNCW 不取得 source ownership。

---

# 13. Representation

MACR 的：

```text
preferred_representation
```

經 bridge 解析為 PNCW：

```text
representation.profile
representation.protocolVersion
```

---

# 14. Requested Mode

PNCW 目前 observation modes：

```text
human_preview
machine_carrier
structured_manifest
```

MACR Agent 預設不應假設：

```text
human_preview
```

就是 machine-optimal observation。

---

# 15. Scope

MACR requested scope 編譯為：

```text
scopeId
regionRefs[]
```

Scope 必須 bounded。

空 scope 或模糊：

```text
everything
```

不能在沒有 explicit policy 下自動展成 unbounded world read。

---

# 16. Authority Context

PNCW ProjectionRequest 要求：

```text
principalId
sourceRead
surfaceProject
```

MACR bridge 不可自行將：

```text
sourceRead = true
surfaceProject = true
```

當作授權本身。

這些是 request-side authority claims/context。

---

# 17. Independent Authority

實際成立條件至少包括：

$$
A_{MACR}
$$

$$
A_{Source}
$$

$$
A_{Surface}
$$

因此：

$$
\boxed{
MACRObservationAllowed
\not\Rightarrow
PNCWSourceAuthorized
}
$$

以及：

$$
\boxed{
SourceReadAuthorized
\not\Rightarrow
SurfaceProjectionAuthorized
}
$$

---

# 18. Readiness

PNCW Readiness 回答：

> 是否具備開始安全建立 projection 的必要條件？

不是：

> 這個 projection 已被驗證。

---

# 19. Readiness Result

Bridge 必須保存：

```text
request id
ready
checks
source snapshot
capability snapshot
blocking error
```

但不需把全部內容塞進 Agent context。

---

# 20. Source Snapshot

Readiness 的 source identity：

$$
S_t
=
(
authority,
sourceId,
revision,
digest
)
$$

是 observation 的重要 lineage basis。

---

# 21. Source Revision

MACR 必須保存：

```text
source_revision
source_digest
```

以判斷 observation 是否可能 stale。

---

# 22. Capability Snapshot

Readiness 同時記錄：

```text
source capabilities
surface capabilities
```

因此：

$$
\boxed{
ObservationCapability
\neq
ObservationAuthority
}
$$

---

# 23. Unexpected Mutation Capability

若 MACR 正在要求 read-only observation，但 source adapter 回報不符合當前 integration profile 的 mutation capability：

應依 PNCW contract fail closed。

Bridge 不得：

```text
great, now Agent can write too
```

---

# 24. Readiness Failure

PNCW error taxonomy 包括：

```text
INVALID_REQUEST
UNAUTHORIZED
UNSUPPORTED
SOURCE_UNAVAILABLE
STALE_SOURCE
INTEGRITY_FAILURE
MATERIALIZATION_FAILED
SURFACE_UNAVAILABLE
VERSION_CONFLICT
VERIFICATION_FAILED
INVALID_TRANSITION
ALREADY_VISIBLE
ABORTED
```

MACR 不壓成：

```text
OBSERVATION_FAILED
```

單一錯誤。

---

# 25. Failure Mapping

建議 MACR mapping：

```text
PNCW UNAUTHORIZED
→ AUTHORITY_DENIED

PNCW UNSUPPORTED
→ CAPABILITY_MISSING / UNSUPPORTED_OBSERVATION

PNCW STALE_SOURCE
→ WORLD_STALE

PNCW INTEGRITY_FAILURE
→ OBSERVATION_INTEGRITY_FAILURE

PNCW VERSION_CONFLICT
→ WORLD_VERSION_CONFLICT

PNCW SOURCE_UNAVAILABLE
→ WORLD_UNAVAILABLE
```

---

# 26. Retryability

PNCW error envelope 有：

```text
retryable
```

MACR 可以參考，但：

$$
\boxed{
PNCWRetryable
\neq
MACRAutoRetryRequired
}
$$

MACR 仍依 Agent budget / policy / world semantics 決定。

---

# 27. Materialization

Materialization 是：

> 可供 projection / partial read / machine processing 的 carrier。

它不是 source。

因此：

$$
\boxed{
\mathrm{Materialization}
\neq
\mathrm{CanonicalSource}
}
$$

---

# 28. Materialization Identity

Bridge 可以記錄：

```text
materializationId
sourceRevision
sourceDigest
carrierProfile
materializationDigest
partialRead
```

作 observation provenance。

---

# 29. Surface

Surface 是 observation presentation / interaction binding。

例如：

```text
MRMIC portal
Canvas surface
machine surface
```

Surface 不是 source。

---

# 30. Prepared Surface Is Not Visible

PNCW 的 prepared surface 可以：

```text
visible = false
```

因此：

$$
\boxed{
\mathrm{SurfacePrepared}
\neq
\mathrm{ObservationVisible}
}
$$

MACR 不得在 projection 組裝中途就把內容送進 canonical Agent context。

---

# 31. ProjectionManifest

PNCW ProjectionManifest 組合：

```text
resultId
sourceIdentity
projectionProfile
materializationRefs
surfaceRefs
integrityRefs
authorityRefs
residencyMap
version
manifestDigest
```

它是跨 provider projection lineage 的核心。

---

# 32. Manifest Is Not Verification

$$
\boxed{
\mathrm{ManifestSelfConsistency}
\neq
\mathrm{VerifiedProjection}
}
$$

Manifest 完成後仍要 Verification。

---

# 33. Integrity References

Bridge 不自行解讀所有 provider structural semantics。

只保存：

```text
integrity refs
structuralVerified
digest
provider
kind
```

---

# 34. Structural Integrity vs Digest

$$
\boxed{
\mathrm{DigestMatch}
\neq
\mathrm{StructuralSemanticValidity}
}
$$

MACR 不可只驗 hash 就跳過 PNCW verifier。

---

# 35. Residency

PNCW residency：

```text
DECLARED
AVAILABLE
RESIDENT
UNAVAILABLE
INVALID
```

---

# 36. Available vs Resident

$$
\boxed{
\mathrm{Available}
\neq
\mathrm{Resident}
}
$$

Agent 不需要要求整個世界全部 resident 才能使用 projection。

---

# 37. Visible vs Resident

$$
\boxed{
\mathrm{Visible}
\neq
\mathrm{FullyResident}
}
$$

這是 MACR Agent observation 的重要能力。

---

# 38. Partial Residency

Agent 可以擁有：

$$
LogicalVisible=1
$$

同時：

$$
0<\rho_{resident}<1
$$

只要所需 semantic root 與 addressability 已滿足。

---

# 39. Partial Residency Is Not Partial Truth

如果 root manifest 已 verified：

```text
detail region not resident
```

不等於：

```text
root observation is semantically incomplete
```

必須區分：

$$
\boxed{
\mathrm{LogicalCompleteness}
\neq
\mathrm{PhysicalCompleteness}
}
$$

---

# 40. Region Demand

Agent 後續需要更多細節時：

```text
ObservationIntent
→ selected region expansion
```

而不是：

```text
重新載入整個 world
```

---

# 41. Progressive Observation

因此一個 Agent observation 可以形成：

```text
root verified observation
↓
region expansion 1
↓
region expansion 2
```

各 expansion 都有 lineage。

---

# 42. Region Expansion Must Bind Parent

新增 region 必須保存：

```text
parent result
source revision
manifest identity
```

避免不同 source revision 的 region 混進同一 observation basis。

---

# 43. Mixed Version Forbidden

例如：

```text
root from revision 10
region A from revision 10
region B from revision 11
```

如果 contract 不允許 mixed lineage：

```text
VERSION_CONFLICT
```

不能自動拼接。

---

# 44. Verification

PNCW VerificationResult 至少包含：

```text
resultId
verified
manifestDigest
checks
verificationDigest
failure
```

---

# 45. Verification Is Current-State Sensitive

一個曾經 valid 的 manifest：

```text
t0 verified
```

在：

```text
t1 source changed
```

之後不能因 serialized verification record 還存在就重新 promotion。

---

# 46. Live Verification

MACR bridge 必須遵守：

$$
\boxed{
\mathrm{PersistedVerifiedRecord}
\neq
\mathrm{CurrentLiveVerification}
}
$$

resume 後若需要 current observation，應重新走必要 validation。

---

# 47. Verification Failure

若：

```text
verified = false
```

Bridge 不建立：

```text
VerifiedObservationRef
```

最多建立：

```text
FailedObservationAttempt
```

供 Agent diagnostics。

---

# 48. Visibility

PNCW lifecycle：

```text
VERIFIED
→ VISIBLE
```

不是單純 UI transition。

它表示：

> 這個已驗證 projection 現在成為 observer-authoritative result。

---

# 49. VisibilityCommit

MACR 只有在：

```text
state = VISIBLE
```

之後，才能建立 canonical：

```text
VerifiedObservationRef
```

---

# 50. VERIFIED Is Not Enough

因此：

$$
\boxed{
PNCW.VERIFIED
\neq
MACR.ObservationBound
}
$$

仍需 visibility promotion。

---

# 51. Visibility State

Bridge 支援：

```text
REQUESTED
RESOLVED
READY
PROJECTED
VERIFIED
VISIBLE
STALE
INTEGRITY_FAILURE
UNAUTHORIZED
UNSUPPORTED
UNAVAILABLE
CONFLICT
ABORTED
SUPERSEDED
```

---

# 52. VISIBLE → STALE

已 visible observation 可以之後被標：

```text
STALE
```

但歷史 observation 不刪除。

---

# 53. Stale Does Not Mean Corrupt

$$
\boxed{
\mathrm{STALE}
\neq
\mathrm{INTEGRITY\_FAILURE}
}
$$

Stale：

> 曾經有效，但世界變了。

Integrity failure：

> projection / carrier / structure 本身不能可信。

---

# 54. MACR VerifiedObservationRef

Bridge 建議新增：

```json
{
  "schema": "macr-verified-observation-ref/v1",
  "observation_ref_id": "vobs:...",

  "agent_run_id": "...",
  "observation_intent_ref": "obs-intent:...",

  "pncw_request_id": "...",
  "pncw_result_id": "...",
  "pncw_manifest_digest": "sha256:...",
  "pncw_verification_digest": "sha256:...",
  "pncw_visibility_commit_id": "...",

  "source_identity": {
    "authority": "...",
    "source_id": "...",
    "revision": 10,
    "digest": "sha256:..."
  },

  "projection_profile_digest": "sha256:...",
  "scope_digest": "sha256:...",
  "residency_summary_ref": "...",

  "visible_at": "...",
  "observation_digest": "sha256:..."
}
```

---

# 55. ObservationRef Is a Reference

不包含：

```text
full carrier bytes
full world state
full screenshot
large document body
```

只保存 identity / lineage / refs。

---

# 56. Observation Digest

$$
D_O
=
H(
PNCWResultID,
ManifestDigest,
VerificationDigest,
VisibilityCommitID,
SourceIdentity,
ProjectionProfile,
Scope
)
$$

不應把：

```text
visibleAt
```

當 semantic identity 的必要成分，除非 future contract 特別需要。

---

# 57. ASE Observation Node

VerifiedObservationRef 再映射到：

```text
macr-semantic-node/v1
node_type = observation
```

---

# 58. ASE Observation Payload

```json
{
  "world_binding_ref": "world:...",
  "verified_observation_ref": "vobs:...",
  "observation_kind": "repository_state",
  "source_revision": 10,
  "scope_ref": "scope:...",
  "content_ref": "artifact:...",
  "freshness_class": "CURRENT"
}
```

---

# 59. Observation Provenance

至少：

```text
PNCW request
manifest
verification
visibility commit
source identity
```

都應可追溯。

---

# 60. Observation Node Cannot Grant Authority

Agent 看見：

```text
repository supports delete
```

不代表：

```text
repository.delete authorized
```

因此：

$$
\boxed{
\mathrm{ObservedCapability}
\neq
\mathrm{Authority}
}
$$

---

# 61. Planning Basis

Plan 必須顯式綁：

```text
basis_observation_refs[]
```

不能只依模型 hidden context。

---

# 62. Basis Digest

Plan 可有：

$$
D_B
=
H(
ordered\ VerifiedObservationRefs
)
$$

用來快速判斷 planning basis 是否改變。

---

# 63. Observation Freshness Policy

不同 world 有不同 stale 邏輯。

例如：

```text
immutable artifact
```

可能永久 valid。

```text
GitHub branch head
```

可能瞬間 stale。

---

# 64. FreshnessPolicy v1

```json
{
  "schema": "macr-observation-freshness-policy/v1",
  "policy_id": "freshness:...",
  "mode": "SOURCE_REVISION",
  "max_age_seconds": null,
  "require_pre_action_recheck": true,
  "require_post_action_reobservation": true,
  "digest": "sha256:..."
}
```

---

# 65. Freshness Modes

```text
IMMUTABLE
SOURCE_REVISION
MAX_AGE
EVENT_INVALIDATED
ALWAYS_RECHECK_BEFORE_MUTATION
```

---

# 66. Time Freshness vs Revision Freshness

Observation 五分鐘前不一定 stale。

Observation 一秒前也可能 stale。

因此：

$$
\boxed{
\mathrm{Age}
\neq
\mathrm{Freshness}
}
$$

---

# 67. Source Revision Preferred

若 source 有 canonical revision：

```text
git commit
database revision
canvas revision
SEDB revision
```

優先用 revision lineage，而不是單純 timestamp。

---

# 68. Stale Detection

若：

$$
SourceIdentity_{current}
\neq
SourceIdentity_{observation}
$$

則 observation 至少：

```text
STALE_CANDIDATE
```

是否仍 usable 由 scope/policy 判斷。

---

# 69. Scope-Aware Staleness

Whole repository revision 改了，不一定代表 agent 正在看的 immutable artifact 變了。

所以 stale 判斷可以用：

```text
source revision
+
region digest
+
scope
```

---

# 70. Planning after Stale

若 active plan 的 required basis stale：

```text
plan → STALE
```

AgentRun 不必 FAILED。

可以：

```text
reobserve
→ revise plan
→ continue
```

---

# 71. Action Admission Requires Fresh Basis

對 external mutation：

$$
FreshBasis(a)=1
$$

是 Action Gate 的必要條件。

---

# 72. Pre-Action Re-observation

高風險 action：

```text
main branch write
delete
publish
send
shared database mutation
```

可強制：

```text
fresh observation immediately before admission/dispatch
```

---

# 73. TOCTOU

Bridge 必須處理：

> Time of Check vs Time of Use。

流程：

```text
observe
→ plan
→ approve
→ world changes
→ dispatch
```

不能只因 approve 過就執行。

---

# 74. Pre-Dispatch Freshness Token

CommandIntent 可以 bind：

```text
source_revision
observation_digest
```

Adapter dispatch 前驗證。

---

# 75. Post-Actuation Re-observation

任何有 external effect 的 action，預設：

```text
Actuation
→ Receipt
→ ReObservationIntent
```

---

# 76. ReObservationIntent

其 purpose：

```text
verify_action_outcome
```

並綁：

```text
action_ref
command_ref
receipt_ref
expected_result_ref
```

---

# 77. Same Observer Not Required

Post-action verification 可以使用不同 observer profile。

例如：

```text
action through browser
verification through structured API
```

這反而可能更獨立。

---

# 78. Independent Observation Path

最好：

$$
ObservationPath_{verify}
\neq
ActuationPath
$$

例如：

```text
write via GitHub API
verify via fresh repository read
```

---

# 79. Provider Receipt vs ReObservation

$$
\boxed{
\mathrm{ProviderReceipt}
\neq
\mathrm{ReObservedWorld}
}
$$

這是 bridge 的主要存在理由之一。

---

# 80. Expected Result

ActionProposal 指向：

```text
expected_result_ref
```

Re-observation 建立：

```text
observed_result
```

Verification 比較：

$$
Expected
\leftrightarrow
Observed
$$

---

# 81. Observation Difference

Bridge 可以提供：

```text
observation_diff_ref
```

例如：

```text
before revision
after revision
changed regions
```

---

# 82. Difference Is Not Verification Alone

Diff 表示：

> 變了什麼。

Verification 表示：

> 這是否符合 action contract。

兩者不同。

---

# 83. Before / After Pair

對 mutation：

$$
(O_{before},O_{after})
$$

形成最重要的 outcome evidence pair。

---

# 84. Causal Binding

After observation 必須可關聯：

```text
follows action
```

但：

$$
\boxed{
\mathrm{TemporalFollowing}
\neq
\mathrm{CausalProof}
}
$$

如果外部 actor 同時改變 world，需要額外 evidence。

---

# 85. Concurrent World Change

若 action 執行期間另有 actor 修改 source：

```text
VERSION_CONFLICT
```

或：

```text
DIVERGED
```

不能把所有差異都歸因於 Agent。

---

# 86. Observation Conflict

兩個 valid observer 可以產生不同 view。

Bridge 不直接宣稱其中之一錯。

可以建立：

```text
CONFLICT
```

並要求：

```text
additional observation
```

---

# 87. Multi-Observation Synthesis

ASE 可以讓：

```text
Observation A
Observation B
```

共同：

```text
support Claim C
```

PNCW 不需要合併 semantic claims。

---

# 88. Observation Confidence

PNCW verification 是 structural/projection verification。

不一定證明：

> 觀察內容對世界所有高層語義的解讀都正確。

例如：

```text
pixel screenshot verified
```

不等於：

```text
OCR interpretation verified
```

---

# 89. Representation Interpretation Boundary

因此：

$$
\boxed{
\mathrm{ProjectionVerified}
\neq
\mathrm{InterpretationVerified}
}
$$

ASE 的 claim/hypothesis 層處理後續 cognition。

---

# 90. Pixel Observation

MRMIC pixel frame 可以透過 PNCW 成為 verified visual projection。

但 model 對畫面的描述：

```text
button is disabled
```

仍是 Claim，不是 Observation 本體。

---

# 91. Structured Observation

例如：

```text
GitHub branch HEAD = abc123
```

如果直接來自 validated structured source，可能更接近 machine-semantic observation。

---

# 92. Observation Topology

未來支援：

```text
ATOMIC_ARTIFACT
SEMANTIC_BATCH
STREAM
HYBRID
```

但 v0.7 bridge 不能因 PNCW enum 存在就宣稱所有 transport engine 已完成。

---

# 93. Stream Observation

Stream 不表示每個 token/event 自動成為 canonical observation。

應有：

```text
stream segment
→ bounded projection unit
→ verification / promotion
```

---

# 94. Semantic Batch

Batch 可以一次 promotion：

```text
related observation set
```

但 batch identity 必須 deterministic。

---

# 95. Atomic Artifact

適合：

```text
test report
manifest
repository snapshot
rendered frame
```

一次成為 observer-authoritative result。

---

# 96. Hybrid

可以：

```text
root atomic
+
regions progressively materialized
```

這與 partial residency 最自然。

---

# 97. Observation Caching

MACR 可以 cache observation refs。

但 cache reuse 必須通過 freshness policy。

---

# 98. Cache Hit Is Not Freshness Proof

$$
\boxed{
CacheHit
\neq
CurrentWorldValidation
}
$$

---

# 99. Immutable Observation

如果 source 本身 content-addressed：

```text
SHA-256 artifact
immutable commit
sealed release
```

可以長期 reuse。

---

# 100. Mutable Observation

如：

```text
working tree
browser page
database row
Canvas live state
queue
```

通常要求較強 freshness check。

---

# 101. Agent Suspend

Agent suspend 時 checkpoint 保存：

```text
latest_verified_observation_refs
```

但醒來後不直接相信 mutable observation 仍 current。

---

# 102. Wake Re-observation

Resume：

```text
checkpoint
→ inspect observation freshness
→ reobserve mutable basis
→ invalidate stale plan
→ ACTIVE
```

---

# 103. Observation and Reconciliation

如果 action outcome unknown：

Agent 可使用 observation bridge：

```text
reconciliation observation
```

判斷：

```text
NOT_EXECUTED
EXECUTED_AS_EXPECTED
EXECUTED_DIFFERENTLY
PARTIALLY_EXECUTED
STATE_UNKNOWN
```

---

# 104. Reconciliation Observation Has Special Purpose

```text
observation_purpose = reconcile_action
```

並綁：

```text
action_ref
attempt_ref
```

---

# 105. Reconciliation Must Not Mutate

Reconciliation observation path：

```text
read-only
```

不能因檢查狀態順便「修好」。

---

# 106. Repair Is New Action

如果 reconciliation 發現：

```text
PARTIALLY_EXECUTED
```

後續 repair：

```text
new ActionProposal
```

重新走 authority。

---

# 107. Observation Budget

Observation 也消耗：

```text
tokens
bandwidth
materialization bytes
provider calls
latency
storage
```

因此可以有 observation budget。

---

# 108. Observation Budget Is Not Mutation Budget

read budget 與 write budget 可以分開。

---

# 109. Materialization Budget

Bridge 可限制：

```text
bytes
regions
latency class
resolution
```

未來可由 GCM 計算。

---

# 110. Budget Exhaustion

若完整 world 太大：

```text
budget exhausted
```

可以：

```text
reduce scope
change representation
defer
```

不能假裝已完整觀察。

---

# 111. Insufficient Observation

如果 Goal 所需 evidence 不足：

ASE 建立：

```text
Claim: evidence insufficient
```

或：

```text
Decision: require more observation
```

不是 hallucinate missing world state。

---

# 112. Observation Expansion

Agent 可以提出：

```text
ExpandObservation
```

其實是一個新的 ObservationIntent。

---

# 113. Observation Compression

Agent context 可以只拿：

```text
semantic summary
```

但 VerifiedObservationRef 仍指回原 projection lineage。

---

# 114. Exact Expandability

未來與 ANLA/Archive 整合時：

```text
summary
→ source region
```

可以保持 exact retrievability。

---

# 115. World Binding Contract

MACR WorldBinding 應增加：

```json
{
  "observation_provider": "pncw",
  "source_adapter": "...",
  "surface_adapter": "...",
  "default_observer_profile": "...",
  "freshness_policy_ref": "...",
  "projection_policy_ref": "..."
}
```

---

# 116. PNCW Is Optional for Non-Canonical Ephemeral Input

並不是所有文字都一定要走 PNCW。

例如：

```text
user says hello
```

可以直接作 conversation input。

但若該資料被提升為：

```text
world-state basis
```

則應有適合的 provenance/verification contract。

---

# 117. Human Statement

Human statement：

```text
"The server is down."
```

在 ASE 中可以是：

```text
Claim
```

不是 verified world observation。

---

# 118. Tool Output

普通 tool 回：

```text
HTTP 200
```

可以先是：

```text
RawEvidence
```

是否成為 Observation 要經 bridge policy。

---

# 119. Direct Chat Boundary

Direct Chat 不要求 PNCW。

AgentRun 的 canonical world basis 才使用 Verified Observation Bridge。

---

# 120. Worker Boundary

Worker 可以接收 projection content。

但 worker output 不得改寫 source observation identity。

---

# 121. Child Agent Observation

Child 可以取得 parent observation 的 projection subset。

但：

$$
\boxed{
ChildContextProjection
\neq
NewWorldObservation
}
$$

除非 child 自己重新觀察 world。

---

# 122. Observation Delegation

Parent 可傳：

```text
VerifiedObservationRef
```

給 child。

Child 必須知道：

```text
source revision
scope
freshness
```

不能只傳 summary text 丟失 lineage。

---

# 123. Child Re-observation

若 child action 需要 current world：

child 應自行走 observation bridge。

---

# 124. MRMIC Integration

MRMIC 可作：

```text
surface provider
interactive world provider
visual observation source
```

PNCW 維持：

```text
projection readiness
verification
visibility
```

---

# 125. MRMIC Portal

Portal：

$$
\pi_C(r)
$$

仍：

$$
\pi_C(r)\neq r
$$

Agent 看到 portal 不代表它看到了 provider resource 的完整 canonical state。

---

# 126. Portal Snapshot vs Live

Bridge 必須區分：

```text
snapshot
live projection
```

尤其 freshness policy不同。

---

# 127. Passive Observation

MRMIC Passive Scene Timeline 可以產生 event-driven observation candidate。

但是否提升為 MACR planning basis，仍需 bridge policy。

---

# 128. Observation Governor

Observation Governor 決定：

```text
skip
ROI
full
keyframe
```

這是 observation delivery strategy。

不是 truth authority。

---

# 129. PHOSPHOR Integration

PHOSPHOR Software Spacetime observation：

```text
Software Spacetime IR
```

可以作 PNCW source。

PNCW 再提供 observer-specific verified projection。

---

# 130. Temporal Observation

Agent 可以要求：

```text
current state
state at t
window [t1,t2]
causal predecessor
event sequence
```

未來 ProjectionRequest scope 可以擴展 temporal/causal scope。

---

# 131. Historical Observation

對 immutable historical event：

```text
freshness
```

不同於 live world。

---

# 132. Replay Observation

Replay：

```text
reconstructed historical state
```

必須標：

```text
replay
```

不能冒充 live current state。

---

# 133. Simulation Observation

模擬世界結果：

```text
simulation
```

也不能冒充 production world observation。

---

# 134. World Classes

建議 bridge 支援：

```text
LIVE
HISTORICAL
REPLAY
SIMULATION
SNAPSHOT
```

---

# 135. Observation Class in ASE

Observation node 記：

```text
world_mode
```

避免模型誤把 simulation 當 current reality。

---

# 136. Verification Level

Bridge 可以標：

```text
PROJECTION_VERIFIED
INTERPRETATION_UNVERIFIED
OUTCOME_VERIFIED
```

不同層級。

---

# 137. Planning Requirement

Plan policy 可以要求：

```text
minimum observation verification level
```

---

# 138. High-Risk Action Requirement

高風險 action：

```text
require CURRENT + PROJECTION_VERIFIED
```

不能用 stale summary。

---

# 139. Observation Conflict Handling

若：

```text
two current projections conflict
```

AgentRun：

```text
BLOCKED / require additional evidence
```

依 policy。

---

# 140. Observation Failure Does Not Mean Agent Failure

Source temporarily unavailable：

```text
AgentRun → BLOCKED
```

或：

```text
WAITING
```

不必 FAILED。

---

# 141. Observation Retry

Read-only projection retry 可比 mutation retry寬鬆。

因為：

$$
ReadRetry
$$

通常沒有 external mutation effect。

但仍受：

```text
budget
rate limits
privacy
```

限制。

---

# 142. Privacy

PNCW manifest / MACR observation metadata 不應無限制複製 private source content。

保存：

```text
refs
digests
bounded metadata
```

---

# 143. Private Source

若 source 為 Residence：

```text
LIMEN envelope
→ source read authority
→ PNCW projection
```

PNCW 不負責 resident identity resolution。

---

# 144. Privacy Scope

Observation scope 必須尊重：

```text
minimum necessary projection
```

而不是「既然已登入就全部讀」。

---

# 145. Projection Authority Is Read-Side

PNCW v0.1 observation path 明確不提供 canonical mutation。

因此：

$$
\boxed{
\mathrm{VerifiedObservationBridge}
\neq
\mathrm{WritebackBridge}
}
$$

---

# 146. Writeback Separate

未來 World mutation：

```text
MACR Action Gate
→ PHOSPHOR / provider
```

不是：

```text
PNCW observation adapter.write()
```

---

# 147. Closed Loop

完整：

```text
World
↓
PNCW Observation
↓
MACR Agent
↓
ActionProposal
↓
MACR Authority Gate
↓
PHOSPHOR / Provider Actuation
↓
World
↓
PNCW ReObservation
↓
Verification
```

---

# 148. Bridge State Machine

MACR bridge-level：

```text
INTENT_CREATED
↓
REQUEST_COMPILED
↓
READINESS_PENDING
↓
READY
↓
PROJECTING
↓
VERIFYING
↓
VISIBLE
↓
BOUND
```

Failure：

```text
UNAUTHORIZED
UNSUPPORTED
STALE
INTEGRITY_FAILED
UNAVAILABLE
CONFLICT
ABORTED
```

---

# 149. BOUND

`BOUND` 表示：

> PNCW visible result 已被正式加入 AgentRun / ASE planning basis。

PNCW 本身不需要知道 MACR BOUND state。

---

# 150. Binding Event

```text
agent.observation_bound
```

保存：

```text
VerifiedObservationRef
ASE observation node
graph revision
AgentRun revision
```

---

# 151. Binding Atomicity

理想：

```text
create ASE observation node
→ update semantic graph head
→ update AgentRun observation binding
```

在 MACR local state 中原子提交。

---

# 152. PNCW State Not Rolled Back

如果 MACR binding persistence fail：

不能修改 PNCW 的 historical visibility event。

應重新 bind existing valid observation 或建立 recovery evidence。

---

# 153. Visibility Is Observer-Authoritative, Not MACR Commit

PNCW `VISIBLE` 表示 projection visibility authority。

MACR `BOUND` 表示：

> 此 observation 被 AgentRun 接受作為 semantic basis。

兩者分離。

---

# 154. Supersession

新 observation：

```text
O2
```

可：

```text
supersedes O1
```

但 O1 歷史仍存在。

---

# 155. Stale Observation Preservation

O1 stale 後：

```text
status = STALE
```

仍可以解釋：

> Agent 當時為什麼做出某 plan。

---

# 156. Historical Explainability

因此能重建：

```text
At plan revision 3,
Agent had observation O1,
source revision was 10,
later world moved to 11.
```

---

# 157. Falsification

Bridge 必須能證偽：

```text
Agent acted on current world state
```

如果實際 basis stale。

這比事後只看 action log 更重要。

---

# 158. Benchmark Metrics

建議：

```text
time_to_verified_observation
time_to_visible_root
time_to_first_addressable_region
reobservation_latency
verification_latency
bytes_materialized
bytes_resident
stale_detection_latency
world_conflict_rate
observation_reuse_rate
```

---

# 159. Efficiency Metrics

不能只看：

```text
tokens/sec
```

還應看：

$$
\frac{UsefulVerifiedInformation}
{MaterializedBytes}
$$

與：

$$
\frac{UsefulVerifiedInformation}
{ObservationCost}
$$

---

# 160. Partial Residency Benchmark

測：

```text
logical root visible
while resident fraction << 1
```

是否仍支援正確 planning。

---

# 161. Stale Benchmark

故意：

```text
observe
→ mutate source externally
→ attempt action
```

必須阻止 blind dispatch。

---

# 162. Integrity Benchmark

carrier tamper + recomputed metadata：

仍須 structural verification reject。

---

# 163. Version Conflict Benchmark

混合：

```text
source rev A
materialization rev A
surface rev B
```

必須 fail closed。

---

# 164. Blind Recommit Benchmark

serialize old VERIFIED result：

```text
restart
→ attempt visibility
```

必須拒絕沒有 fresh live verification 的 blind recommit。

---

# 165. Scope Leakage Benchmark

只觀察：

```text
file A
```

Agent 不得把 observation semantic scope提升：

```text
entire repository verified
```

---

# 166. Planning-Basis Benchmark

Plan 必須可列出：

```text
exact observation refs
```

不能只回：

```text
based on context
```

---

# 167. Post-Action Verification Benchmark

Receipt success + unchanged world：

必須：

```text
DIVERGED
```

---

# 168. Required Negative Controls

```text
NC-VOBS-01 raw tool output bound as verified observation
NC-VOBS-02 readiness treated as verification
NC-VOBS-03 VERIFIED treated as VISIBLE
NC-VOBS-04 VISIBLE result bound without MACR observation record
NC-VOBS-05 source authority implies surface authority
NC-VOBS-06 capability implies authority
NC-VOBS-07 stale source used for mutation basis
NC-VOBS-08 integrity failure retried as ordinary stale
NC-VOBS-09 mixed revision regions combined
NC-VOBS-10 old serialized verification blindly recommitted
NC-VOBS-11 partial residency treated as semantic incompleteness
NC-VOBS-12 unavailable region treated as resident
NC-VOBS-13 human preview treated machine-complete
NC-VOBS-14 pixel interpretation treated as projection fact
NC-VOBS-15 portal treated as provider resource
NC-VOBS-16 cached observation treated fresh without policy
NC-VOBS-17 wake resumes old mutable observation blindly
NC-VOBS-18 provider receipt substitutes post-action observation
NC-VOBS-19 temporal following treated as causal proof
NC-VOBS-20 simulation observation treated as live world
NC-VOBS-21 child summary loses source lineage
NC-VOBS-22 reconciliation observation mutates source
NC-VOBS-23 scope-local observation promoted global
NC-VOBS-24 bridge silently changes PNCW manifest identity
```

---

# 169. Acceptance Matrix

## Intent

- valid AgentRun；
- bounded scope；
- valid world binding；
- observation purpose known。

## Compilation

- deterministic intent → request under fixed policy；
- observer mapping stable；
- no authority escalation。

## Readiness

- source identity captured；
- capability snapshot retained；
- typed failure preserved。

## Manifest

- identity retained；
- no bridge rewriting；
- residency retained；
- authority refs retained。

## Verification

- verified false never creates VerifiedObservationRef；
- live verification requirement retained。

## Visibility

- only VISIBLE promotes canonical observation；
- idempotent visibility preserved。

## ASE

- observation node retains source/projection lineage；
- semantic scope correct；
- provenance complete。

## Freshness

- mutable source rechecked；
- stale basis invalidates action；
- immutable source reusable。

## Re-observation

- post-action observation linked to action；
- expected / observed comparison possible。

## Recovery

- checkpoint resume revalidates mutable observations；
- old visible record cannot bypass source freshness.

---

# 170. v0.7.0 / Integration MVP Boundary

第一版 bridge 不需要完成所有 PNCW future architecture。

最低：

```text
ObservationIntent
ObservationRequestCompiler
PNCW client/adapter
Readiness mapping
Projection result binding
Verification result binding
Visibility binding
VerifiedObservationRef
ASE Observation mapper
Freshness policy
Stale invalidation
Post-action re-observation
```

---

# 171. Not Required in First Bridge

第一版不要求：

```text
GCM dynamic projection optimization
all RevealMode transport engines
distributed PNCW
multi-tenant security certification
canonical source writeback
full multimodal interpretation verification
arbitrary cross-world semantic federation
```

---

# 172. Proposed MACR Modules

```text
src/macr_runtime/observation/
├─ intent.py
├─ contracts.py
├─ compiler.py
├─ pncw_bridge.py
├─ freshness.py
├─ binding.py
├─ reobserve.py
└─ errors.py
```

只是建議 physical layout。

---

# 173. Proposed Schemas

```text
macr-observation-intent/v1
macr-observation-freshness-policy/v1
macr-verified-observation-ref/v1
macr-observation-binding/v1
macr-reobservation-request/v1
macr-observation-diff/v1
```

---

# 174. API

Agent-facing：

```text
request_observation()
expand_observation()
request_reobservation()
```

Runtime-facing：

```text
compile_projection_request()
run_readiness()
bind_visible_projection()
check_freshness()
invalidate_observation()
bind_post_action_observation()
```

---

# 175. Observation Cannot Self-Verify

Agent 不能：

```text
mark_observation_verified()
```

Verification 必須由 PNCW / trusted verifier contract 建立。

---

# 176. Observation Cannot Self-Promote

Agent 不能：

```text
make_visible()
```

Visibility 由 PNCW lifecycle 決定。

---

# 177. Observation Cannot Self-Globalize

Agent 不能改：

```text
scope=file
```

成：

```text
scope=repository
```

而不重新觀察。

---

# 178. Observation Cannot Grant Write Authority

即使 observation 顯示：

```text
current user is repo admin
```

仍不是 MACR authority envelope。

---

# 179. Formal Observation Validity

對 AgentRun $R$ 與 observation $O$：

$$
ValidObservation(O,R,t)
=
Visible(O)
\land
Verified(O)
\land
ScopeValid(O,R)
\land
AuthorityLineageValid(O)
\land
FreshEnough(O,t)
$$

---

# 180. Formal Planning Basis

Plan $P$ 可使用 observation $O$：

$$
BasisValid(P,O,t)
=
ValidObservation(O,R,t)
\land
O.scope
\supseteq
RequiredScope(P)
$$

---

# 181. Formal Action Basis

Action $A$：

$$
ActionBasisValid(A,t)
=
\bigwedge_{O\in Basis(A)}
ValidObservation(O,R,t)
$$

若任一 required observation stale：

$$
ActionBasisValid=0
$$

---

# 182. Formal Re-observation

Action 後：

$$
O_{t+1}
=
\Pi(
W_{t+1}
)
$$

Verification：

$$
V(A)
=
Compare(
Expected(A),
O_{t+1}
)
$$

---

# 183. Formal Partial Residency

令：

$$
\rho
=
\frac{bytesResident}{bytesTotal}
$$

只要 required semantic root / regions 满足：

$$
RequiredRegions\subseteq AvailableOrResident
$$

則：

$$
\rho<1
$$

不阻止 observation 成為 usable basis。

---

# 184. Formal Staleness

$$
Stale(O,t)
=
SourceIdentity(O)
\neq
CurrentSourceIdentity(t)
$$

更細緻版本可以 scope-aware：

$$
Stale_{scope}(O,t)
=
Digest_{scope}(O)
\neq
Digest_{scope}(Current)
$$

---

# 185. Formal Visibility Separation

$$
\boxed{
Ready
\not\Rightarrow
Projected
\not\Rightarrow
Verified
\not\Rightarrow
Visible
\not\Rightarrow
MACRBound
}
$$

每一步都是獨立 boundary。

---

# 186. Canonical Closure

本文件固定：

1. MACR Agent canonical observation 以 Verified World Projection 為核心。
2. ObservationIntent 與 PNCW ProjectionRequest 分離。
3. Observation planning 不授予 source/surface authority。
4. MACR 不重新實作 PNCW readiness、manifest、verification 或 visibility。
5. Source、Materialization、Surface、Verified Artifact、Visible Artifact 永不折疊。
6. Readiness 不等於 Verification。
7. VERIFIED 不等於 VISIBLE。
8. PNCW VISIBLE 不等於 MACR BOUND。
9. Observation 不等於 World。
10. Observation 永遠有 observer、scope、representation 與 temporal lineage。
11. Capability 不等於 Authority。
12. Source authority 不等於 Surface authority。
13. Partial residency 不等於 semantic incompleteness。
14. Available 不等於 Resident。
15. Mixed-version observation fail closed。
16. Persisted verification 不等於 current live verification。
17. Stale 與 Integrity Failure 分離。
18. Observation cache 不等於 freshness proof。
19. Plan 必須綁 exact observation basis。
20. External mutation dispatch 必須驗 freshness。
21. Agent suspend/resume 必須重新檢查 mutable observation。
22. Action receipt 不等於 post-action observation。
23. External effect 後應經 re-observation / independent verification。
24. Projection verification 不等於 higher-level interpretation truth。
25. Pixel interpretation應以 Claim 表示，而非直接改寫 Observation。
26. MRMIC portal 不等於 provider native resource。
27. Replay / Simulation / Historical observation 不得冒充 live world。
28. Reconciliation observation 必須 read-only。
29. Large world 應支援 bounded scope / partial residency，而非強制全量 context。
30. PNCW bridge 是 observation path，不是 canonical mutation path。

因此：

$$
\boxed{
\mathrm{MACR\ Agent\ Knowledge}
\text{ begins from }
\mathrm{VerifiedObservation},
\text{ not raw access.}
}
$$

更完整地：

$$
\boxed{
World
\rightarrow
Projection
\rightarrow
Verification
\rightarrow
Visibility
\rightarrow
SemanticObservation
\rightarrow
Plan
}
$$

而世界被改變後：

$$
\boxed{
Actuation
\rightarrow
ReObservation
\rightarrow
Verification
\rightarrow
StateEvolution
}
$$

這形成 MACR Agent-Spacetime Runtime 的第四個 canonical engineering core。

---

# Appendix A — Existing PNCW Contracts Reused Without Redefinition

```text
pncw-projection-request/v1
pncw-readiness-result/v1
pncw-projection-manifest/v1
pncw-verification-result/v1
pncw-visibility-state/v1
pncw-error/v1
```

---

# Appendix B — New MACR Bridge Contracts

```text
macr-observation-intent/v1
macr-observation-freshness-policy/v1
macr-verified-observation-ref/v1
macr-observation-binding/v1
macr-reobservation-request/v1
macr-observation-diff/v1
```

---

# Appendix C — Canonical Observation Flow

```text
AgentRun
↓
ObservationIntent
↓
ObservationRequestCompiler
↓
PNCW ProjectionRequest
↓
Readiness
↓
Materialization
↓
Surface Preparation
↓
ProjectionManifest
↓
Projection Verification
↓
VisibilityCommit
↓
VerifiedObservationRef
↓
ASE Observation Node
↓
AgentRun Observation Binding
↓
Plan Basis
```

Post-action：

```text
Action
↓
CommandIntent
↓
Actuation
↓
Receipt
↓
ReObservationIntent
↓
PNCW
↓
VerifiedObservationRef
↓
ASE Observation
↓
Outcome Verification
↓
AgentRun State Advance
```

---

# Appendix D — Next Canonical Specification

下一份：

**MACR × PHOSPHOR Spacetime — Governed Actuation Bridge Specification v0.1**

將正式定義：

```text
ASE ActionProposal
→ MACR Admission
→ CommandIntent
→ PHOSPHOR Governance
→ Authority Gate
→ Provider ABI
→ Actuation
→ Measured Reality
→ Actuation Receipt
→ PNCW ReObservation
```

並處理：

```text
logical time
wall-clock time
causal binding
scheduled action
suspend / wake
desired / requested / realized / observed
provider failure
host failure
compensation
```

使 MACR v0.7 的「自主活動」真正進入受治理的 Software Spacetime。