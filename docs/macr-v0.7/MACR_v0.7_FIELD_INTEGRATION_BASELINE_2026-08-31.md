# MACR v0.7 現場整合基線與 Phase A 最小收斂增補

**Document ID:** MACR-V07-FIELD-INTEGRATION-2026-08-31
**Date:** 2026-08-31
**Status:** PRE-PHASE-A FIELD BASELINE / APPROVED DESIGN DIRECTION / NOT IMPLEMENTATION
**Repository:** D:\Ai\work together\MACR
**Engineering branch:** workbench/v0.7-agent-contract-kernel
**Baseline commit:** d3ecaf16de66fb7df326253fbd09df3aa353b5f4
**Baseline version:** 0.6.0a1
**Language:** Traditional Chinese

---

# 0. 這份文件的用途

這份文件是 MACR v0.7 在正式進入 Phase A 之前的現場整合記錄。

它不是新的大架構論文，也不是 Phase A 已完成的證據。

它的用途是讓未來任何一次：

- 對話壓縮；
- 任務切換；
- 模型切換；
- 本地與 GitHub 狀態不同步；
- 人類忘記當時的整合理由；
- AI 沒有取得完整先前上下文；

都可以只讀這份文件，重建下列資訊：

1. 當時 MACR 的精確工程 baseline；
2. 實際存在於 D 槽、work together 與 GitHub 的相關系統；
3. 哪些是 canonical、candidate、reference、proposal 或 blocked；
4. 為什麼 Phase A 不只參考 EML-U；
5. 為什麼仍然不把 ISQL、NOVA、MNEME、ANDO 或其他 runtime 直接塞進 MACR；
6. Phase A 真正新增的最小 contract delta；
7. 哪些工作必須延後；
8. 下一位執行者應從哪裡重新開始。

本文件優先保存：

- 精確 commit、branch、tag、封包 SHA-256；
- 成熟度與 authority boundary；
- 已採用的整合決策；
- 未採用與未量測項目；
- Phase A 的進入、驗證與停止條件。

本文件不保存：

- credential；
- provider key；
- private Residence memory；
- hidden chain-of-thought；
- 未授權的內部語義來源內容；
- 任何把 proposal 冒充 implementation 的宣稱。

---

# 1. Operator Decision

2026-08-31，operator 明確核准採用：

> MACR v0.7 Phase A 最小收斂方案。

其意思不是進行全系統融合。

其意思是：

1. 保留既有 MACR v0.7 設計主線；
2. 讓 Agent Semantic Envelope 對 EML-U、ISQL、NOVA 與未來 semantic profile 保持中立；
3. 補上現場已證明重要的 unresolved / ambiguity / obligation 語義；
4. 補上 MNEME 等 memory plane 的可選 binding reference；
5. 不新增任何外部 semantic runtime mandatory dependency；
6. 不在 Phase A 偷做 Agent loop、database、scheduler、provider integration 或 Multi-Agent。

---

# 2. Canonical Source Precedence

Phase A 使用以下 source precedence。

## 2.1 第一層：現行 MACR source 與 executable tests

第一層永遠是：

1. D:\Ai\work together\MACR 的實際 source；
2. exact commit；
3. executable tests；
4. current repository instructions；
5. verification evidence。

文件不能覆蓋 executable source fact。

## 2.2 第二層：MACR v0.7 canonical specification set

docs\macr-v0.7 內 00–10 規格是 v0.7 architecture 的 normative source。

Phase A handoff prompt 是工程入口與濃縮交接，不是第二個獨立 ontology owner。

若 prompt 與完整規格不同：

1. 先判定是否為濃縮、省略或真正衝突；
2. 真正衝突必須在實作前留下 design delta；
3. 不得自行選一份比較方便的文字。

## 2.3 第三層：本現場整合文件

本文件只處理：

- 現場成熟度訂正；
- 新發現的系統；
- 最小跨系統 contract delta；
- 實作前 source routing。

它不重寫 00–10 的完整 Agent architecture。

## 2.4 第四層：外部或平行系統

EML-U、ISQL、NOVA、MNEME、ANDO、PNCW、PHOSPHOR、SEDB、LIMEN、GCM 等，只能透過：

- reference；
- versioned contract；
- adapter；
- external binding；
- later integration gate；

影響 MACR。

它們不自動成為 MACR canonical owner。

---

# 3. Exact MACR Baseline

## 3.1 Repository identity

| Field | Value |
|---|---|
| Local root | D:\Ai\work together\MACR |
| Branch before v0.7 work | main |
| Phase A branch | workbench/v0.7-agent-contract-kernel |
| Local baseline HEAD | d3ecaf16de66fb7df326253fbd09df3aa353b5f4 |
| GitHub main HEAD at audit | d3ecaf16de66fb7df326253fbd09df3aa353b5f4 |
| Tag | v0.6.0a1 |
| Runtime version | 0.6.0a1 |
| State root | D:\AI_RESIDENCE\AI_Runtime\macr-state |

Local baseline與 GitHub main 相同。

## 3.2 Fresh offline baseline

2026-08-31 fresh execution：

| Check | Result |
|---|---|
| scripts\verify.ps1 | exit 0 |
| Tests run | 482 |
| Passed | 480 |
| Failed | 0 |
| Platform capability skips | 2 |
| Network activity | false |
| Provider generation | false |
| GLM invoker census | 0 |
| git diff --check | pass |

這次 fresh run 證明：

- v0.6.0a1 baseline仍可執行；
- Phase A 前沒有 inherited test failure；
- verification 沒有呼叫 real provider；
- 既有 v0.6 source不需要先修復才能開始 Phase A contracts。

## 3.3 Current source style relevant to Phase A

MACR current source使用：

- Python 3.11+；
- frozen dataclass；
- Enum；
- explicit __post_init__ validation；
- to_dict / to_public_dict style；
- unittest；
- finite JSON canonicalization；
- namespace-separated SHA-256 identity；
- timezone-aware ISO timestamp normalization。

Phase A不得為了新 Agent contracts改成另一套 framework。

---

# 4. MACR v0.7 Design Pack Integrity

repo 中的 12 份非延後區 v0.7 文件，與真終極來源逐檔 SHA-256 相同。

| Relative file | SHA-256 |
|---|---|
| MACR × PHOSPHOR Spacetime — Governed Actuation Bridge Specification v0.1.md | D1069B6F67E32C1E580212517F10F16D6713ECD13E59A603E797ED73030991B0 |
| MACR × PNCW — Verified Observation Bridge Specification v0.1.md | 17A7BBBFB2C461A3CF32EC9FC06CF561B012682505B864E38191FBC14E85D5E2 |
| MACR v0.7 — Action - Authority - Effect Contract Specification v0.1.md | D4630056F2463CAAE418F88A5B0FFAEFF3C92B3CDBDC13D31F07A2A90264CD50 |
| MACR v0.7 — Agent Semantic Envelope Specification v0.1.md | 2FB5E587A850114BCE40D258E6B41515D30AB63363C8B659482E01309E87EE7B |
| MACR v0.7 — Agent-Spacetime Runtime Canonical Convergence Architecture v0.1.md | 4ED241712D2675A7D65EF475D9A4C3B59B38B2F16687B2B580B10D6B06A30F07 |
| MACR v0.7 — AgentRun Canonical State Specification v0.1.md | 06BBBDDF8123A05EA504E8036C7F05D3A7A050278C959AE396C82D766B6DC9CA |
| MACR v0.7 — Checkpoint - Suspend - Wake - Temporal Continuation Specification v0.1.md | 3D0F33068542C02A4018EDCFB42C47C411517319CF0657DB2A94A0040102B1C8 |
| MACR v0.7 — External Agent Framework Primitive Adoption Matrix v0.1.md | 2A26F003F5F0ABCD3FF812795BCBAB33CCA3BCAAD5AEF1E5C0B88252F7EC091A |
| MACR v0.7 — Single-Agent MVP Implementation Plan & Verification Matrix v0.1.md | 04B3C2304F049571B332E9DEA9218B7BC61B7C02B612270A3D6C9F269889AC9F |
| MACR v0.7 — Verification & Negative-Control Matrix v0.1.md | A49BD8E5C5E1DE814ED86FCBCBADA3499A7D7296C8677920CC6597316CDCA271 |
| SEDB vNext — Agent - World State Adaptation Proposal v0.1.md | 98E9EB24EBF42D0C390152E37DFD1B31852EA508BE041C83461ED331BF4E51B7 |
| prompts\MACR v0.7 Phase A — Agent Contract Kernel Engineering Handoff Prompt v0.1.md | 97F8DFE5E252CB2563C2840C8C1AC712A23B33C620C5A981167A12C3E7FC549A |

因此：

> repo copy不是改寫版，也沒有在搬移時發生內容漂移。

上述來源文件的 metadata 行保留原始 Markdown 兩空格 hard break。不得為了通用 whitespace cleanup 批次刪除，否則會破壞這份逐檔 SHA-256 基線；新增或修改的 MACR source仍應正常通過 whitespace檢查。

---

# 5. Field System Census

本節記錄 2026-08-31 現場可驗證狀態。

## 5.1 MACR

Status：

- v0.6.0a1 implemented / validated；
- Direct Chat、delegated TaskContract、T1、authority、accounting、candidate vault、reconciliation皆存在；
- live T1仍未由 v0.6.0a1 release啟用；
- Phase A尚未實作。

Phase A decision：

- reuse canonical.py；
- reuse AuthorizationReference semantics；
- preserve DispatchContext.run_id；
- preserve Direct / Delegation planes；
- no provider call。

## 5.2 PNCW

Canonical main：

- local clean v0.1.0 at 121bc1024277e7e21a14e8e1a92eed7dba02400d；
- GitHub main at 003cce0a5f4c35b7870850af66c883b856da7ea1；
- GitHub main比 local多兩個白皮書 commit；
- runtime baseline未因此改變。

Candidate branch：

- workbench/v0.2-gcm-guided-projection-planning；
- head 0e084a1c87e4bb6dad639ba2259e009b031de1df；
- ahead of main by 44 commits；
- latest CI success；
- no open PR；
- not canonical main。

Phase A decision：

- v0.1 lifecycle與 VerifiedObservationRef 可作 reference；
- v0.2 planning contracts不得當成已採用 MACR dependency；
- real integration留給獨立 gate。

## 5.3 MRMIC / NVCL

Local：

- main 791efb9d98270d4db9c25f257aac805196ba62e8；
- clean；
- Phase 13 boundary。

GitHub：

- main 1c3ec2b137cfe801c47b02cd64cb614f0bbaa97b；
- local落後 3 commits；
- Phase 14 HDSRC runtime discovery / supervision / routing；
- CI success；
- 252 tests，251 pass，1 existing skip；
- no HDSRC canonical mutation authority。

Phase A decision：

- no direct code dependency；
- observation/world binding保持 provider-neutral；
- MRMIC real integration later。

## 5.4 PHOSPHOR EAI and PHOSPHOR Spacetime

這是兩個不同工程線。

### PHOSPHOR EAI

Path：

D:\Ai\work together\PHOSPHOR

State：

- local/GitHub main 286cfce4353d37585363e6043bf33676678557ae；
- package 0.8.0-beta.0；
- VM / WASM / CTS / EAI / trace / spreadsheet line。

### PHOSPHOR Spacetime

Field package：

D:\我的研究\學術討論\論文\真終極\真本體論12\Software_Spacetime\PHOSPHOR_Spacetime_v0.1.0a9_M10.zip

Package SHA-256：

8B371BE6CCEFD48EF9718EA644B41D12259E44F9C58136F33E42D4C3F23F3B06

GitHub：

- repository kakon77777-commits/phosphor-spacetime；
- main 23184e704c02f876602784530693da3073487f6f；
- exact package metadata matches main；
- M10；
- Ubuntu 133 pass / 1 Windows-only skip；
- Windows 133 pass / 1 Linux-only skip；
- pss gate 7/7 PASS；
- performance superiority not measured。

Phase A decision：

- ssm-ir-v0.1；
- ssm-control-v0.1；
- ssm-provider-v0.1；
- ssm-actuation-receipt-v0.1；

可作 Action / Temporal contract reference。

不新增 PHOSPHOR runtime dependency。

## 5.5 EML-P

Path：

D:\Ai\work together\EML

State：

- local/GitHub main f5b8b871ecfec8e0a0d9cf36c28e096915bab060；
- EMLP-AUDIT-005 landed；
- current implementation line is EML-P；
- EML-P是 executable language profile，不是 universal Agent semantic owner；
- repo尚有未追蹤 demo、public release plan與handoff內容；
- no current GitHub Actions gate。

Phase A decision：

- reference only；
- no dependency；
- do not confuse EML-P execution semantics with ASE ontology。

## 5.6 EML-U

GitHub main：

- efa06e9f909edea88a2f51490bce324b9d8a162f；
- repository initialization only。

PR #1：

- head 48d66c2eadccb630c09ee7c7edde74811ec6e5fb；
- open；
- 41 changed files；
- 1151 additions；
- packaged validation reports 26/26 pass；
- GitHub reports no checks；
- not merged。

Implemented candidate scope：

- composite semantic glyph；
- position-aware semantic structure；
- deterministic graph；
- round-trip；
- explicit loss report；
- manual crystallization。

Not implemented：

- complete universal ontology；
- complete Agent semantic graph runtime；
- world authority；
- MACR integration。

Phase A decision：

- EML-U concepts are valid reference input；
- EML-U is not the sole semantic source；
- no mandatory dependency；
- no maturity overclaim。

## 5.7 ISQL

Operator boundary：

- ISQL Origin is internal-use material；
- it is excluded from this integration；
- no Phase A semantics are imported from the Origin line。

Allowed reference lines：

### Public ISQL Core v1.0

- GitHub main f4bf2fb30b20f389be73da912d04e3daa7ba9abc；
- Core Runtime v1.0.0；
- machine-native memory, locality index, actual-byte rerank；
- implementation exists。

### ISQL Meta-Core v0.2

Package：

ISQL_Meta_Core_Specification_v0.2_2026-08-18.zip

SHA-256：

FD5AACDAC4EF3869406927FD54123AD11D2BDC25B6EC2A9C7EFB081B98EB3E1C

Status：

- Candidate Meta-Core Specification；
- document validation PASS；
- shared object contracts I / R / V / S / C / D；
- operational contracts F / B / O；
- extension hooks Projection / History / Transition / Execution。

Important terminology boundary：

ISQL 的 Canonical Machine Authority 描述 artifact canonicality。

它不得與 MACR execution authorization 混用。

MACR採用中性名稱 ArtifactRole / CanonicalityClass。

### ISQL Agent Knowledge Library v0.4

Package：

ISQL_Agent_Knowledge_Library_v0.4.0_2026-08-20(1).zip

SHA-256：

FF4CAA1FDABE8E97342F8628FA554E8CB3EDE0C4DB3123A4713CF2B385CD08A8

Relevant concepts：

- exact source != semantic interpretation；
- relation proposal != validated relation；
- evidence exactness != proposition truth；
- rebuildable non-authoritative epistemic projection；
- ACTIVE / SUPPORTED / CONTESTED / SUPERSEDED / REFUTED / UNRESOLVED；
- immutable relation / validation history。

Phase A decision：

- adopt selected contract ideas；
- no wire format adoption；
- no runtime dependency；
- no registry or storage migration。

## 5.8 NOVA

GitHub：

- main d204cb4c18d4a29fc433ecfcde27b2aa7f538ce1；
- public GitHub only reaches Round 00 initialization/release packaging。

Local field package：

NOVA_Core_Closure_Round_13_G7_ISQL_High_Dimensional_Semantic_Interface_2026-08-20.zip

SHA-256：

7F87EC256FB49CD58EDD3B0F50FECCE92C5A5BFBE4967F40CD7CE527B9DD14A9

Package claims through G7：

- immutable canonical typed graph；
- GraphPatch preview / validation / commit separation；
- multi-projection identity；
- AI proposal != program authority；
- high-dimensional SemanticTensor；
- multiple candidates from one intent；
- explicit ambiguity；
- explicit unresolved obligations；
- append-only correction and resolution；
- semantic back-projection；
- bridge confidence != correctness probability。

Phase A decision：

- borrow ambiguity / obligation / correction / resolution semantics；
- preserve candidate != commit；
- do not import NOVA graph/program runtime；
- do not claim local package was independently rerun during this MACR audit。

## 5.9 MNEME

Path：

D:\Ai\work together\MNEME\repo

State：

- local/GitHub main d911c7bcf9fa187b87bfc4101e020653f5b06ec6；
- package candidate 0.5.0a1；
- multiple GitHub workflows green at exact head；
- current local untracked state consists of Python __pycache__ directories only。

Implemented surfaces：

- MLF-RM/0.1 canonical record memory；
- MNEME-MD/0.1 compatibility；
- MNEME-CPS/0.1 observation-only persistence semantics；
- private Residence two-pass dry-run；
- unified profile integration。

Hard boundary：

- memory != context；
- memory != identity；
- canonical state != projection；
- proposal != commit；
- read authority != write authority。

Phase A decision：

- add optional MemoryBindingRef；
- do not read private memory；
- do not integrate MNEME runtime；
- checkpoint stores references only；
- actual MemoryNeed / reconstruction remains later work。

## 5.10 SOACR

Path：

D:\Ai\work together\SOACR

State：

- local/GitHub main bf95043ca220faa447617b690f6bfc2bfef7ea05；
- architecture and local implementation handoff complete；
- runtime not implemented。

Phase A decision：

- MemoryNeed / progressive recall / reconstruction are later port concepts；
- no SOACR contract dependency in Phase A；
- MemoryBindingRef must not pretend SOACR exists as runtime。

## 5.11 ANDO Runtime

GitHub：

- repository ANDO-Runtime；
- main 87d84e7b8072871d7b09bddb2f4c491b7f397f13；
- release v0.1.0；
- CI green。

Field package：

ANDO_Runtime_Lite_v0.1_MVP.zip

SHA-256：

F22A6CC3BD2BE3A9B7549940B693C16D05E2722F7C3E71E0831FB98CBB123B38

Validated package evidence：

- 42 tests；
- 12 acceptance tests；
- SQLite WAL；
- optimistic versioning；
- task DAG；
- bounded delegation；
- checkpoint / crash replacement / resume；
- no human continue trigger。

Phase A decision：

- reference AgentRun / delegation / lifecycle failure patterns；
- no dependency；
- no Multi-Agent implementation；
- later Phase B/F comparison only。

## 5.12 SEDB

Local：

- main 0156ef238f2aee4efc2173174232e921212c4da2；
- 23 commits ahead of GitHub main 0d95c810661ecbeb83633ea9712dd24a41ce7e7f；
- ahead commits are Wanxiang project work and supporting docs；
- one unrelated untracked brief remains。

Core：

- current v0.4B；
- effect-oriented autonomy；
- Decision != Commit；
- Capability != Authority；
- compensating rollback；
- 189 inherited tests in the sealed core evidence。

vNext：

- GEOL is proposal / integration direction；
- not implemented。

Phase A decision：

- no SEDB dependency；
- semantic persistence port later；
- no automatic ASE mirroring。

## 5.13 LIMEN

Path：

D:\Ai\work together\LIMEN

State：

- local/GitHub main eb3fe5cf3742796f02fe805652376feb536fb153；
- B0–B5 promoted；
- B6A public-resolution candidate；
- no background service；
- no real private resident activation；
- no registrar write。

Phase A decision：

- ordinary AgentRun must not require LIMEN；
- only resident-bound future AgentRun uses identity mediation；
- no private Residence access in Phase A。

## 5.14 GCM

Observed field evidence：

- no canonical D:\Ai\work together GCM checkout found；
- no matching GitHub GCM repository found；
- local delivery inspection says Phase A/B validated/sealed；
- Phase C C1 remains PARTIAL；
- blocker F-C1-CTX-01 allows nested mutable/secret-bearing dataclass objects through AIContextSnapshot boundary；
- C2 is not eligible until C1 repair/reacceptance。

Related PNCW v0.2 branch：

- contains fake and real GCM Phase-B adapter packages；
- CI green；
- branch is not canonical main；
- no PR。

Phase A decision：

- do not use GCM C1 context snapshot；
- do not use PNCW v0.2 candidate as dependency；
- GCM planning remains future adapter/integration work。

## 5.15 Context-memory empirical line

Relevant field packages include：

- Gamma0–Gamma5 context coordination prototypes；
- E0–E4 context-memory experiments；
- E5 pre-content freeze；
- LRSC interaction research。

Observed boundaries：

- Gamma5 synthetic stress PASS，learned proposal remains guard-bounded；
- E4 passes its predeclared aggregate gate but is only a weak blind generalization signal；
- E4 paired sign-test p = 1.0；
- E4 evidence recall remains low；
- E5 has only pre-content freeze / design / plan，not a completed live-provider result；
- LRSC B3b.1 supports context/state-conditioned interaction evidence but does not identify an executable operator。

Phase A decision：

- no learned context coordinator；
- no neural embedding dependency；
- no claim that memory virtualization is solved；
- only preserve room for future ContextProjection / MemoryBinding ports。

## 5.16 Expandable Intelligence / Mother AI line

The ten-paper Expandable Cognitive Core series defines：

- Cognitive Density；
- Resident Cognitive Core；
- Conditional Intelligence；
- Externalized Cognitive Experts；
- Cognitive Factorization；
- Temporary Cognition；
- Mother AI as Cognitive Command Tower；
- Capability Boundary Tomography；
- Expandable Intelligence synthesis。

Phase A decision：

- these are long-term architectural direction；
- no Mother AI runtime in Phase A；
- no model/router/capability-atlas implementation；
- Agent contract must remain compatible with later heterogeneous cognitive expansion。

---

# 6. Phase A Minimal Contract Delta

這是本文件最重要的 normative section。

Phase A仍然只做 contracts、validation、serialization、digest與negative controls。

在原 handoff prompt上增加以下最小內容。

## 6.1 Semantic substrate neutrality

ASE由 MACR canonical own。

它不能在 schema上假定：

- EML-U是唯一 future ontology；
- ISQL是 canonical wire；
- NOVA graph就是 Agent semantic graph；
- 任一外部 registry具有 MACR authorization。

新增薄型：

### SemanticProfileRef

最低應能表達：

- system_id；
- profile_id；
- profile_version；
- registry_ref optional；
- registry_revision optional；
- registry_digest optional；
- decoder_contract_ref optional；
- binding_digest。

規則：

1. profile reference是 identity/provenance binding；
2. profile reference不是 authority；
3. profile reference不是 runtime availability proof；
4. external profile缺失時，MACR-native ASE仍能運作；
5. digest使用 macr_runtime.canonical。

### ExternalSemanticBinding

最低應能表達：

- MACR semantic ref；
- external system/profile ref；
- external object ref；
- external digest；
- binding kind；
- binding digest。

Binding kind使用 bounded vocabulary：

- REFERENCE；
- PROJECTION；
- DERIVED；
- TRANSFORMATION。

任何 external binding都不得改寫 MACR node identity。

## 6.2 Artifact canonicality terminology

ISQL Meta-Core使用 Canonical Machine Authority 表示 artifact status。

MACR中 Authority已具有 execution permission語義。

因此 Phase A不得新增第二套名為 Authority的 artifact classification。

使用：

### ArtifactRole

建議 vocabulary：

- CANONICAL_SOURCE；
- CANONICAL_DERIVED；
- DERIVED_REBUILDABLE；
- PROJECTION；
- CACHE_INDEX；
- LEGACY_COMPATIBILITY。

ArtifactRole：

- 只描述 artifact canonicality / rebuildability；
- 不允許 provider call；
- 不授予 action；
- 不取代 AuthorizationReference。

## 6.3 Epistemic unresolved state

原 Claim status保留：

- PROPOSED；
- SUPPORTED；
- CONTESTED；
- VERIFIED；
- REFUTED；
- STALE；
- SUPERSEDED。

新增：

- UNRESOLVED。

UNRESOLVED表示：

- 有候選 evidence / relation；
- truth state尚不能決定；
- 或 required evidence / decoder / binding不足。

UNRESOLVED不等於：

- false；
- failed；
- verified；
- safe default。

## 6.4 Ambiguity and obligation

新增兩個 SemanticNodeType：

- AMBIGUITY；
- OBLIGATION。

### AMBIGUITY

表示：

- 多個候選都仍可能成立；
- semantic decoding不足以選唯一結果；
- scope/shape/effect/context存在未解歧義。

### OBLIGATION

表示：

- 在 commit / action / completion前必須取得的 evidence、verification、human decision或constraint resolution。

規則：

1. ambiguity不得被 silent default消失；
2. obligation不得被 model文字標記為完成；
3. obligation resolution需要 evidence relation；
4. unresolved blocking obligation阻止 runtime completion；
5. Phase A只固定 contract，不實作 obligation engine。

## 6.5 Correction and resolution lineage

Phase A不新增可覆寫歷史的 edit API。

Correction / resolution使用：

- SemanticEvent；
- supersedes / revises / resolves relations；
- parent refs；
- provenance；
- record digest。

規則：

1. correction不修改原 node；
2. resolution不刪除 ambiguity；
3. selected candidate不等於 committed action；
4. semantic resolution不等於 AuthorizationReference；
5. same content / different provenance保留不同 record digest。

## 6.6 Optional MemoryBindingRef

AgentRun contracts新增可選：

### MemoryBindingRef

最低應能表達：

- memory_system_id；
- profile_id；
- subject_ref；
- head_ref optional；
- head_digest optional；
- access_policy_ref；
- projection_policy_ref；
- binding_digest。

AgentRun可持有：

- zero；
- one；
- multiple bounded memory bindings。

規則：

1. MemoryBindingRef不是 memory content；
2. MemoryBindingRef不是 active context；
3. MemoryBindingRef不是 identity proof；
4. MemoryBindingRef不是 read/write authority；
5. checkpoint只保存 exact refs/digests；
6. no automatic profile detection；
7. no private read in Phase A；
8. absence of MNEME/SOACR不阻止普通 AgentRun contract成立。

## 6.7 No MemoryNeed contract yet

SOACR runtime尚未實作。

因此 Phase A不新增完整：

- MemoryNeed；
- progressive recall；
- reconstruction plan；
- memory strategy governor；
- autonomous writeback。

只保留 future port空間。

---

# 7. Existing Phase A Contracts That Remain Unchanged

以下不因本次整合而改變：

1. Model != Agent。
2. Agent != Resident。
3. AgentRun != InvocationRun。
4. Conversation != AgentRun。
5. Capability != Authority。
6. Goal != Authority。
7. Observation != World。
8. Plan != Command。
9. Decision != Commit。
10. Receipt != Verification。
11. Wake != Authorization。
12. Resume != Replay。
13. Checkpoint != Authority rollback。
14. Time != Compute。
15. UnknownAfterDispatch => ReconciliationRequired。
16. DispatchContext.run_id保持 bounded invocation identity。
17. agent_run_id使用獨立 occurrence identity。
18. AuthorizationReference重用現有 source_kind / source_id / digest / revision / epoch / scope。
19. Phase A不新增 InteractionPlane.AGENT。
20. Direct Chat與Agent Plane保持分離。

---

# 8. Explicit Non-Adoption / Deferred List

Phase A不採用：

- EML-U runtime dependency；
- EML-P parser/transpiler dependency；
- ISQL wire format；
- ISQL registry migration；
- NOVA Graph runtime；
- NOVA GraphPatch commit path；
- MNEME runtime integration；
- SOACR runtime；
- ANDO scheduler；
- ANDO database；
- PNCW v0.2 candidate branch；
- GCM C1 context；
- PHOSPHOR runtime；
- SEDB vNext；
- LIMEN private bootstrap；
- OpenTelemetry；
- MCP adapter expansion；
- Playwright；
- sandbox vendor；
- real provider；
- model call；
- browser action；
- Multi-Agent；
- child AgentRun runtime；
- Mother AI router；
- learned context coordinator。

這些可以：

- 作 reference；
- 留 adapter interface；
- 留 future test vector；

但不能出現在 Phase A mandatory dependency graph。

---

# 9. Version Interpretation

原 architecture roadmap與 Single-Agent MVP plan對 minor version有不同讀法。

本文件固定：

## 9.1 v0.7.0a1

v0.7.0a1 是：

> bounded single-machine single-Agent core candidate。

其 core gate可使用：

- fake PNCW port；
- fake PHOSPHOR port；
- deterministic planner；
- fixture world。

要完成 v0.7.0a1，仍需：

- AgentRun；
- semantic state；
- verified observation semantics；
- governed action semantics；
- temporal continuation；
- reconciliation；
- closed loop；
- failure injection；
- inherited regression。

## 9.2 v0.7.1–v0.7.3

這些 minor versions解讀為 real integration maturity，而不是把 core semantics延後：

- v0.7.1：real PNCW integration maturity；
- v0.7.2：external semantic profile / graph integration maturity；
- v0.7.3：real temporal / PHOSPHOR integration maturity。

這避免：

- v0.7.0a1宣稱完整 real integration；
- 或 v0.7.0a1缺少其安全核心所需的 observation / semantic / temporal contracts。

---

# 10. Phase A Entry Gate

開始 Phase A source前必須：

1. current branch = workbench/v0.7-agent-contract-kernel；
2. baseline ancestry包含 d3ecaf16de66fb7df326253fbd09df3aa353b5f4；
3. non-Phase-A user changes不被覆寫；
4. v0.7 design baseline已被 Git追蹤；
5. 本文件已被 operator review；
6. current AGENTS.md已讀；
7. canonical.py與現有 contract style已讀；
8. scripts\verify.ps1 fresh baseline PASS；
9. network activity = false；
10. provider generation = false。

若 baseline已更新：

- 不 reset回 d3ecaf1；
- 重新 source audit；
- 記錄新 baseline；
- 重跑 inherited test。

---

# 11. Phase A Implementation Boundary

Phase A只實作：

1. AgentRun contracts；
2. Semantic contracts；
3. Observation contracts；
4. Action contracts；
5. Temporal contracts；
6. SemanticProfileRef / ExternalSemanticBinding；
7. ArtifactRole；
8. UNRESOLVED / AMBIGUITY / OBLIGATION；
9. MemoryBindingRef；
10. canonical digest rules；
11. cross-contract negative controls；
12. Phase A evidence/checkpoint。

Phase A不實作：

- state store；
- event store；
- semantic DB；
- graph commit；
- Agent lifecycle engine；
- Agent runner；
- planner；
- context builder；
- observation provider；
- action dispatch；
- scheduler；
- checkpoint database；
- wake service；
- resume engine；
- reconciliation engine；
- memory retrieval；
- provider integration；
- live model。

---

# 12. Phase A Test Addendum

除了原 handoff prompt要求的 tests，增加：

## 12.1 Semantic profile boundary

- valid profile ref canonicalizes；
- profile version / registry binding enters digest；
- field order does not change digest；
- external binding cannot become authority；
- external object digest不能改寫 MACR node digest；
- unknown binding kind rejected。

## 12.2 Artifact role boundary

- canonicality class does not produce AuthorizationReference；
- CACHE_INDEX不能被當成 canonical source；
- PROJECTION不能被當成 world truth；
- unknown ArtifactRole rejected。

## 12.3 Epistemic boundary

- UNRESOLVED round-trip；
- UNRESOLVED不能被當作 VERIFIED；
- CONTESTED仍可存在但不能自動完成；
- confidence不能轉成 verification。

## 12.4 Ambiguity / obligation

- multiple candidates preserve ambiguity；
- missing obligation cannot silently disappear；
- model-supplied resolved=true不能完成 obligation；
- correction produces new record digest；
- resolution retains parent/provenance；
- resolution不產生 action authority。

## 12.5 Memory binding

- zero memory binding valid；
- multiple bounded bindings canonicalized；
- same binding order policy fixed；
- raw memory content rejected；
- callable / handle / arbitrary object rejected；
- memory text不能成 authority；
- checkpoint reference不能恢復 historical write authority。

---

# 13. Phase A Stop Gate

Phase A完成後必須停止。

正確 maturity claim：

> MACR v0.7 Phase A — Agent Contract Kernel: IMPLEMENTED / VALIDATED。

仍為 PLANNED：

- AgentRun state runtime；
- semantic persistence；
- observation runtime；
- action runtime；
- temporal runtime；
- Agent loop；
- live integration。

不得因 dataclass與tests完成就宣稱：

- autonomous Agent implemented；
- Mother AI implemented；
- Agent memory integrated；
- ISQL / NOVA / EML-U integrated；
- PNCW / PHOSPHOR integrated；
- v0.7.0a1 completed。

---

# 14. Recovery / Re-entry Checklist

未來若上下文遺失，依序做：

1. 讀本文件。
2. 讀 docs\macr-v0.7 00–10規格。
3. 讀 Phase A handoff prompt。
4. git branch --show-current。
5. git rev-parse HEAD。
6. git status --short。
7. git ls-remote origin refs/heads/main。
8. 檢查本文件列出的外部 source是否已有新 canonical release。
9. 不從熟悉名字推斷 speaker/resident identity。
10. 不從 memory或聊天文字推斷 authority。
11. 跑 scripts\verify.ps1。
12. 若 Phase A已開始，讀 Phase A checkpoint與新增 tests。
13. 若 exact source或contract已漂移，先做新的 delta audit。
14. 不盲目重做已完成且有 exact evidence的工作。

快速判斷：

| Question | Correct first answer |
|---|---|
| EML-U是否已成 MACR dependency？ | No |
| ISQL Origin是否可用？ | No，operator excluded |
| NOVA G7是否已合併GitHub main？ | No，local package is newer |
| MNEME是否存在？ | Yes，0.5.0a1 candidate |
| SOACR runtime是否存在？ | No，architecture/handoff only |
| PHOSPHOR Spacetime是否只是理論？ | No，a9/M10 reference runtime exists |
| GCM C1是否可作可信 context provider？ | No，PARTIAL blocker remains |
| PNCW v0.2是否 canonical？ | No，candidate branch |
| Phase A是否可以使用 provider？ | No |
| Phase A是否可以做 Multi-Agent？ | No |

---

# 15. Measured / Not Measured

## Measured

- MACR local/GitHub exact main identity；
- MACR fresh 482-test offline baseline；
- v0.7 design pack SHA equality；
- local Git status / branch / commits；
- selected GitHub main/branch/PR/run metadata；
- PHOSPHOR Spacetime archive metadata and embedded verification；
- selected ISQL/NOVA/MNEME/ANDO field artifacts and documented evidence；
- PNCW/MRMIC local-vs-remote drift；
- SEDB local ahead scope；
- EML-U PR state；
- GCM delivery inspection blocker。

## Not Measured

- live provider behavior；
- real AgentRun；
- real PNCW v0.2 deployment；
- real PHOSPHOR bridge from MACR；
- real MNEME recall from MACR；
- real SOACR reconstruction；
- real EML-U/NOVA/ISQL semantic adapter；
- distributed Agent ownership；
- multi-day Agent soak；
- Mother AI routing quality；
- context-memory E5 live replication；
- GCM C1 repair；
- broad security certification；
- production private Residence activation。

---

# 16. Final Integration Decision

MACR v0.7 Phase A將採：

> MACR-owned, semantic-substrate-neutral Agent contracts。

概念來源可以多元：

- EML-U提供 universal semantic overlay方向；
- ISQL Meta-Core提供 identity / registry / structured state / canonicality / interpretation / boundedness；
- ISQL Agent Knowledge Library提供 epistemic projection與 unresolved state；
- NOVA提供 candidate graph、ambiguity、obligation、correction、resolution與back-projection discipline；
- MNEME提供 memory != context與canonical memory binding boundary；
- ANDO提供 later runtime/delegation/recovery reference；
- PNCW提供 verified observation；
- PHOSPHOR Spacetime提供 governed actuation/temporal reference；
- SEDB提供 future evolving semantic/world persistence；
- LIMEN提供 future resident-bound identity mediation。

但 canonical ownership仍是：

| Domain | Owner |
|---|---|
| AgentRun / orchestration | MACR |
| Agent semantic envelope contract | MACR |
| Execution authorization | MACR existing authority subsystem |
| Verified world projection | PNCW |
| Temporal/actuation reference | PHOSPHOR Spacetime |
| Canonical memory records | MNEME when integrated |
| Long-term evolving semantic/world state | SEDB direction |
| Resident identity mediation | LIMEN / Residence stack |
| External semantic profiles | Their own systems, through bindings |

因此本次整合的正式結論是：

> 多來源收斂，不等於多 runtime耦合。
>
> 語義可借鑑，canonical authority不可外包。
> Phase A只固定未來不應再破壞的最小 contract。

---

# 17. Next Exact Step

在 operator review本文件後：

1. 建立 Phase A detailed implementation plan；
2. 以 tests-first方式實作 Agent Contract Kernel；
3. 跑 focused contract tests；
4. 跑 inherited verify.ps1；
5. 視 clean-tree條件跑 verify-v06或等價 gate；
6. 寫 Phase A checkpoint；
7. 停止，不進 Phase B。

---

# 18. Closure

這份文件是：

- 現場事實備份；
- Phase A設計增補；
- context-loss recovery anchor；
- 人類回想當時整合理由的索引。

它不是：

- 私人記憶；
- identity proof；
- provider authority；
- implementation completion；
- release acceptance；
- deployment record。

Phase A的正確起點不是：

> 重新發明 Agent。

而是：

> 在已存在的 MACR、PNCW、PHOSPHOR Spacetime、ISQL、NOVA、MNEME、ANDO、SEDB、LIMEN 與 Mother AI研究之間，選出最小、可驗證、可延伸、又不互相奪權的 contract kernel。
