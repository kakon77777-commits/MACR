# Provenance baseline

Observed on 2026-08-12 before MACR v0.1 implementation.

| Source | Identity |
|---|---|
| `R:\AI_gamedesign\workspace\technical-docs\01_GPT_Local_Multi_AI_Collaboration_Runtime_v0.1.md` | SHA-256 `E089C1730943D4F23E979B0B5287A6FA2CAA92964A4E33A60E538B050BE874A5`, 17,297 bytes |
| `D:\Ai\work together\cross-task-multi-ai-execution-study\paper.md` | SHA-256 `CDDAF1B99BB13C78FAC83FADF658A5152B8701B0DC18BFB7BD70869028B1F39C`, 27,878 bytes |
| `D:\Ai\work together\APR` | Git commit `d1722eca845353acd3ce1f7241283bfa16263e93`, clean worktree at inspection |

The source documents were not modified or copied into this repository. MACR is a new implementation with explicit provenance references.

The R: path above is historical evidence. Current Residence authority records that the former R: device became system C: on 2026-08-16 and current runtime entry points moved to D:.

## v0.2 design and observed provider baseline

| Evidence | Identity |
|---|---|
| Grok/Ollama design | Git commit `2b0e589`, 2026-08-25 |
| D Residence and speaker-boundary review | Git commit `6b6da53`, 2026-08-25 |
| Implementation plan | Git commit `76b5911`, 2026-08-25 |
| Qwythos Ollama installation | model `hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M`, manifest digest `5008e78bba127262f3f7ad86425bb49a5e0f47bb1959a4d30bfe17832ec45856`, 6,657,768,737 bytes |
| xAI access smoke test | authenticated model listing plus one fixed-string `grok-4.3` response; actual cost USD 0.0002734; no key value retained |

These observations do not establish v0.2 live acceptance. Grok 4.6 and MACR-routed Qwythos conformance are recorded separately only after Task 8 succeeds.

## v0.3 Google GenAI design baseline

| Evidence | Identity |
|---|---|
| Google balanced-provider design | Git commit `9a33b28`, 2026-08-26 |
| Google implementation plan | Git commit `48774d0`, 2026-08-26 |
| Google research directory | preserved external prototype; not imported into MACR runtime |
| Vertex model discovery | 2026-08-25 cached catalog evidence; visibility is not inference entitlement |

The approved credential operation is copy-only to `D:\KEY\GOOGLE_VERTEX.json` with byte-length and SHA-256 equality checks. Neither credential bytes nor account/project identifiers belong in Git or this provenance file. Live text, multimodal, and image conformance is recorded separately only after the complete offline v0.3 gate succeeds.

## v0.4 GLM delegated-worker baseline

| Evidence | Identity |
|---|---|
| Official model profile | direct Z.ai general API, exact `glm-5.3-flash`, max reasoning |
| Credential custody | external D: key file; shape and presence checked without retaining value or digest |
| Pre-integration smoke test | exact returned model and fixed-string match; 20 prompt, 195 completion, 215 total tokens; one request, no tools or retry |
| Pricing basis | 2026-08-27 official Z.ai page; list price is enforcement basis and promotional price is informational |

The pre-integration smoke test established account access only. It did not grant runtime authority or acceptance. No prompt body, response body, credential value, account identifier, or credential digest belongs in Git. MACR-routed live acceptance is recorded separately only after the complete offline v0.4 gate succeeds.

The final delegated-worker gate requires `non_sensitive_routine` plus a SHA-256 approval manifest over the complete credential-free request payload, exact provider/endpoint/model, task type, privacy, maximum output, conservative USD ceiling, and pricing basis. Integrity alone is not authority: a separate content-free D: host record binds the digest to a fixed author role, nonce, creation time, and expiry and carries an HMAC-SHA256 verified with fixed-key custody. The wrapper never reads the credential; provider invocation repeats structural approval against the current task, then reads fixed `D:\KEY\GLM.txt` to authenticate the record before network use. Semantic classification remains a trusted operator decision and is not inferred from model content.

## v0.5.0a1 Shared Core Checkpoint A baseline

The implementation boundary immediately before documentation was:

```text
implementation_commit = 89becf2cce5fcb3ff18f379bbb7bae8de9dbe6f2
implementation_tree   = e6ed4ed624a18bea000cf140148c9bce903c4767
```

The checkpoint design and execution plan are repository artifacts under `docs/superpowers`. The implementation also incorporated version-bound field observations from the MSSP architect exchange without treating those reports as implementation authority:

| Field evidence | Bytes | SHA-256 |
|---|---:|---|
| `2026-08-27-pragma-glm-author-island-vectors-result.md` | 3,363 | `3CB9C3B14E4E8AF3188767480409335639BF56E3EB7275ADA428AAA623F23DFD` |
| `2026-08-27-pragma-glm-author-vectors-process-census-correction.md` | 1,338 | `9F5FE9C49710A35C95F55D7FDCEF93E487DAD52CFC94F7ED402A7630188D2DE2` |
| `2026-08-27-macr-owner-feedback-from-glm-pilot.md` | 6,013 | `9799D35321940FCB7179E059027F58A580555290D4E2AF4F1BA3E531EBBDA915` |
| `2026-08-27-macr-owner-feedback-t1-return-contract-addendum.md` | 3,580 | `0AB4B1D25DD4B4B0110A652AFFDED4F606C849B6FDFCB5258606A8D0AC8EB844` |
| `2026-08-27-post-pilot-glm-dispatch-observation.md` | 2,544 | `5BBC530852111EE366A25B066383E2E21D4883130954EAFB813A8D649D2CC47A` |
| `2026-08-27-pragma-ledger-concurrency-replay.md` | 2,419 | `4A2DE92CEE8B55B4F478BE0C91FD59DFA3C970072C39AB4E360718002ADB977D` |
| `2026-08-27-metron-ledger-concurrency-replay.md` | 2,341 | `9B4FB0738DBBA0CF6F43C46F08989E7BFBEF98F7FF880D6E70F68933BCB18457` |

The withdrawn observation that one codec CLI remained active is excluded; the correction's self-excluding control is authoritative for that field report. Checkpoint A made no provider request and generated no new live conformance claim. The field evidence remains external and unchanged.

## v0.5.0a2 replay-repair baseline

Independent a1 replay produced one green sample and one blocking red sample. The blocking report was independently reproduced before repair: synchronized fresh SQLite construction failed at `PRAGMA journal_mode=WAL`; `PLAIN_SOURCE` accepted a leading prose wrapper; EventStore accepted `path`, `source_path`, and `remote_body`; and the documented bare multiprocess command failed without `PYTHONPATH=src`.

The implementation-only repair boundary before version and documentation edits is:

```text
implementation_commit = b6cbab09bc792d83f706e82caf34b19313ffc1b7
implementation_tree   = d6b599505b9d47da3a291528a42c159f7a93bf43
```

The a1 checkpoint document and external reviewer evidence remain historical artifacts and are not rewritten. The single authorized twin rejected the first a2 repair candidate `d0aff2858b263492d2d75e9a22b2a20e41b08ecf` after reproducing acronym/path aliases, missing field-type enforcement, incomplete dynamic language headings, and a Python annotation false positive. Those findings were closed in the implementation boundary above with new RED/GREEN controls. No provider was called during diagnosis or repair.

## v0.5.0a3 sensitive-marker repair baseline

Field observation showed that the GLM obvious-sensitive heuristic confused HTTPS and LaTeX control sequences with Windows drive paths. Subsequent route evidence also exposed append-only legacy growth after a completed migration. The repair is bounded to the classifier, logical cross-hash legacy reconciliation, their behavioral tests, active alpha version labels, and checkpoint documentation. It does not adopt v0.6 work.

```text
implementation_commit = c64d9b8ae8593319bd4c5b6b9aa33a999ea489f1
implementation_tree   = c0d8f33ea2a1d6ec87fdbe20b1b882da5f371745
```

The initial a3 implementation/checkpoint pair `4a54acbdd405ee955346f112a1a45e3798850841` / `575b9b5555874067ba999b84f5176ce19dfa7853` was independently rejected after reproducing cross-hash duplicate imports and additional classifier underblocking. It remains historical and carries no route authority.

The second pair `dd0e36831f8b64556aa2df5ad4f6a8abdc2d3f59` / `ee8fe2815e05ab01fa4af7596fe8006353ed6a74` closed those findings but was independently rejected after generic file URIs and delimiter-starting Windows path components bypassed the classifier. It also remains historical and carries no route authority.

The third pair `674b3bb88dc086f6d8d310194717ab46397c76c0` / `ca6547d271fb97c73946358dc3a4fbea1373ba53` closed those cases but was independently rejected after valid single-slash and relative `file:` URI forms bypassed its slash-count rule. It also remains historical and carries no route authority.

| Evidence | Bytes | SHA-256 |
|---|---:|---|
| `D:\Ai\work together\amral-research-trees\collatz-verification-zhuiheng\reports\RUN-033-HARD-ZETA-AU2D5-ANNULAR-RESIDUE.md` | 11,301 | `C949E205010F7AC18F3A12A86446EC434F449803C36A46899D40DC2AA3155EAD` |
| `D:\Ai\work together\amral-research-trees\collatz-verification-zhuiheng\data\external\hardzeta-corpus-manifest.json` | 45,577 | `2CF0874C82A584457B3458742EA4B54BED8092714384AEB63F17496974403589` |
| `D:\Ai\work together\MSSP_Architect_Exchange\evidence\2026-08-28-pragma-macr-route-drift-after-t6.md` | 2,284 | `6C0FE0A103601CBFA7371A68E04DB541E020930B3B23917832B27D73F78246B7` |
| `D:\Ai\work together\MSSP_Architect_Exchange\evidence\2026-08-28-pragma-post-migration-legacy-tail.md` | 3,145 | `3A91A0586253E533D213D9C1768B5778281DB17B2890550248130BE4F0CF8CF3` |

The 132-document manifest remains external evidence. Its exact member bytes were not resolvable from current searchable D-drive paths during this repair, so no local 132/132 rescan is claimed. At the initial a3 checkpoint, read-only inspection found the legacy source had advanced from the previously migrated 64-event hash to 68 events under a new hash while SQLite retained only the old complete source record. The repaired comparison logic measured 64 exact prior identities, four new identities, and zero conflicts without writing. The checkpoint was therefore correctly published as offline-only at that time. No provider call, key read, approval creation, second legacy migration, shared-runtime write, merge, release, deployment, or publication occurred during that repair checkpoint.

## v0.5.0a3 bounded live-route activation

Neo later clarified that MACR/v0.6 development was paused so the three MSSP architects could use the stable a3 runtime; this was not a cancellation of bounded MACR/GLM use. The MACR owner froze the clean a3 subject and published an exact live route. The legacy source had advanced to 74 events before sealing, so the earlier 68-event runbook remained historical and was not reused.

| Route evidence | Bytes | SHA-256 |
|---|---:|---|
| `decisions/2026-08-28-neo-macr-update-pause-clarification.md` | 1,495 | `69839675762BEA309B8FE0759379FBBAE76B26D170E9647613992958BEDB11ED` |
| `decisions/2026-08-28-macr-a3-live-route-legacy74.md` | 7,289 | `8A43F7F6FEFF86D05120C66A0720FF03C058570270A7CF9EC839687A55647B13` |
| `evidence/2026-08-28-metron-macr-a3-legacy74-reconciliation.md` | 2,579 | `AB8144F777AAF779E666D5D39962B5BFDCFB80D30A404833C25ACE3A8313D098` |
| `decisions/2026-08-28-neo-mssp-p1-p3-standing-authorization.md` | 4,777 | `FA2C0044274D8362105315E3414B4E99855C18134EDB54E57B8E2A8E68267CF0` |

The authorized one-operator reconciliation sealed the 41,490-byte legacy JSONL read-only at SHA-256 `80AF74FB9FB20FF805E168F13A40E4DC585DA20AEA3778347FDDE6CC29128299`. Dry-run observed 74 valid/distinct events with zero corrupt or duplicate records. The first copy-import reported 10 new and 64 already imported; the identical repeat reported zero new and 74 already imported. Readback showed 76 runtime events, 74 legacy-backed events, one complete current-source row, and zero active leases.

The current route is active for bounded sequential `glm_flash_worker` use after each exact P1/P2/P3 v2 member exists and passes one peer static audit. Standing Neo authorization permits a trusted operator to finalize the exact digest, create/replace the 30-day host approval, preflight, and invoke once without returning for a new conversational authorization on every member. All v1 tasks remain blocked. No automatic retry, provider/model fallback, concurrent fan-out, merge, release, deployment, adoption, or named resident authority follows.

## v0.6 design and implementation-plan intake

The original v0.6 design pack remains preserved outside Git under `D:\Ai\work together\MACR_Research_Handoffs\2026-08-28-macr-v0.6-design-pack`. Its ZIP is 12,791 bytes with SHA-256 `1922C33D300CA882C6DA40641A82A07E5C430B09BA3A37D08D29BECAB4DD8290`; the original Markdown is 31,023 bytes with SHA-256 `7B4C6639C6508B5309BB4419751F875C27B371E7FB7FDDEC1C16EDF6B52F0B8C`.

The reviewed canonical candidate and master implementation plan were copied byte-for-byte into `docs/superpowers` without changing the active package version or granting implementation authority:

| Repository artifact | Bytes | SHA-256 |
|---|---:|---|
| `docs/superpowers/specs/2026-08-28-macr-v0.6-dynamic-coordination-design.md` | 22,219 | `96F80327174335997AADDEFC8214E4116765604D9DD3F2C7F71742287AD3B67C` |
| `docs/superpowers/plans/2026-08-28-macr-v0.6-dynamic-coordination.md` | 50,717 | `44267DB22C74124A41F1797FCE6B1E6C86B82285E18E8F324BE0E7D1B02FD172` |

This intake was documentation-only. At intake time MACR remained version `0.5.0a3`; the original a3 checkpoint commit/tree remains an immutable ancestor. The later a4 Direct Chat supplement below does not revise, rename, or implement the v0.6 plan. The intake itself did not create provider, discovery, automation, migration, merge, release, or deployment authority. The bounded live route described above was activated separately under Neo's direct clarification and completed 74-event reconciliation.

## v0.5.0a4 Direct Chat UI 0.1 alpha candidate

Neo explicitly authorized completing the previously approved Direct Chat design before v0.6. The version boundary is two-level:

```text
MACR package/runtime = 0.5.0a4
Direct browser/API   = 0.1 alpha
future coordination = v0.6 (unchanged and not implemented here)
```

The a4 work was isolated from the frozen MSSP a3 route:

```text
base_commit          = 42ea69479b4cc02c41fda9f0f6746c764cf9d2fa
base_tree            = 605084f538c36435e3e23a04f91c2cefd8ef8260
branch               = feature/macr-v0.5-direct-chat-ui
worktree             = D:\Ai\work together\MACR\.worktrees\macr-v0.5-direct-chat-ui
implementation_commit = 0827fc5e0c9d11cd62674648e0fdd8e90a7bb663
implementation_tree   = 507f58b47ba58edc9457b7b443ee92caf8598f64
```

| Repository artifact | Bytes | SHA-256 |
|---|---:|---|
| `docs/superpowers/specs/2026-08-27-macr-v0.5-direct-chat-design.md` | 32,493 | `EED4BDF417EDE5A989A40DE4597FD92BC6B536A00EF5ACA9FA8A4C69795A66AF` |
| `docs/superpowers/plans/2026-08-29-macr-v0.5-direct-chat-ui-v0.1.md` | 28,657 | `0956CD74FC67AA4B5E99E146714A577160482A8AE8FAEB134D5D869DC9E1D561` |

The implementation adds immutable Direct contracts, versioned settings, complete plaintext conversation persistence, exact Grok/Qwythos native adapters, standing current-epoch operator authority, fenced sequential admission, private answer capture, accounting, an authenticated loopback API, packaged offline UI assets, a cross-process single-instance launcher, and a Windows shortcut installer. `DirectRuntime` does not accept a `TaskContract`, call `MacrRuntime.invoke()`, or compile a worker prompt.

The first complete repository gate after implementation ran 298 tests with zero failures and two pre-existing Windows symbolic-link capability skips. It also completed the parameterized multi-process SQLite gates, content/credential scan, zero-invoker census, and offline doctor at version `0.5.0a4`. No Grok or Qwythos generation occurred in that gate. A separate local smoke started the server on `127.0.0.1`, fetched the packaged UI, exchanged the one-time bootstrap, and stopped without provider generation.

The first real shortcut launch exposed two Windows credential-loader integration faults that the offline dry-run did not exercise: the previously shared helper rejected an observed UUID-shaped value, and direct console output bypassed the PowerShell success pipeline used by the launcher. A later content-free live authentication probe proved that UUID was not a valid API secret: `/models` returned HTTP 400 with an invalid-key signal, no quota/model signal, and no credential echo. After the operator updated the D-drive file, the same bounded probe returned HTTP 200 and confirmed `grok-4.6` visibility without generation. The final repository loader accepts only a bounded `xai-...` secret from an ordinary D-drive file, while missing/invalid Grok custody degrades to Qwythos-only startup. The actual Desktop `.lnk` was read back with a D-drive launcher, hidden PowerShell arguments, and no key marker; launching twice retained one identical Python Direct process, served `MACRDirect/0.1` with HTTP 200, and kept the instance descriptor free of key/bootstrap data. No provider generation occurred during these launcher/authentication probes.

The credential/UI correction gate ran 302 tests with zero failures and the same two symbolic-link capability skips. It adds fail-closed Direct secret-shape validation, Qwythos-only degradation, disabled unavailable provider cards, and visible failed-turn projection that preserves composer text. The gate remained offline apart from the separately bounded `/models` authentication probe.

Neo then authorized an operator-confirmed privacy deletion path for disposable or sensitive Direct tests. The implementation never deletes an existing conversation automatically. Exact uppercase `DELETE` is required; active runs refuse deletion. Under disposable D-drive tests, Candidate answer files were overwritten best-effort and removed, Direct system/user/assistant sentinels were absent from both the main SQLite file and WAL after `secure_delete=ON` plus a successful `wal_checkpoint(TRUNCATE)`, and content-free accounting remained readable. A `direct.conversation_deleted` event retains only conversation/run/message/Candidate counts, origin metadata, deletion mode, and secure-delete/WAL results. The complete gate increased to 308 tests with zero failures and the same two symbolic-link capability skips. This is application-layer privacy deletion, not a claim of forensic NAND erasure, provider-side deletion, snapshot removal, backup deletion, or removal of already materialized external copies.

The operator subsequently authorized deletion of the exact current archived set: four of four total Direct conversations, 27 messages, and 16 terminal runs, with zero active runs, leases, or unsettled invocations. The first live batch exposed a Windows-only post-purge defect: one Candidate file had already been overwritten/removed when an empty-directory `rmdir` received `WinError 5`; the Direct database transaction had not begun, so all four conversation records remained. A RED/GREEN control now proves transient empty-directory locks are cosmetic after Candidate bytes are gone. Replaying the same exact archived set was idempotent for the already-absent file and completed all four deletions. Readback showed zero conversations/messages/Direct runs, zero Grok/Qwythos Candidate `answer.bin` files, a zero-byte Direct WAL, four content-free deletion tombstones, and 14 retained content-free Direct accounting rows. No non-archived or active conversation was in scope.

This checkpoint remains an alpha candidate until the operator performs one bounded complete multi-turn Grok Direct conversation and one complete multi-turn Qwythos Direct conversation, including D-drive reload and accounting inspection. Transport-level cancellation and explicit late-result recovery are openly absent and remain beta gates. No merge, release, deployment, publication, v0.6 implementation, host-adapter authority, named resident identity, or delegated acceptance follows from this candidate.

## v0.6.0a0 integration baseline decision

Neo explicitly directed MACR development to continue from the completed a4 Direct Chat checkpoint rather than return to the earlier a3-only subject. A new isolated branch/worktree was created without merging or modifying the a4 branch:

```text
branch               = feature/macr-v0.6-dynamic-coordination
worktree             = D:\Ai\work together\MACR\.worktrees\macr-v0.6-dynamic-coordination
base_commit          = 8b897eadb0f2f82ff02676ff5ead017067d6bb85
base_tree            = 7b938ca69652c876b9be1c5cbebc80a7971e2921
a4 implementation    = 0827fc5e0c9d11cd62674648e0fdd8e90a7bb663
a4 implementation tree = 507f58b47ba58edc9457b7b443ee92caf8598f64
```

The fresh v0.6 worktree baseline ran 309 tests with zero failures and the same two Windows symbolic-link capability skips. A read-only shared-state observation found the legacy JSONL unchanged at 41,490 bytes / 74 parsed events / SHA-256 `80AF74FB9FB20FF805E168F13A40E4DC585DA20AEA3778347FDDE6CC29128299`, with the read-only attribute set, 74 legacy-backed runtime events, a current complete 74-event source row, 114 total runtime events, and zero leases. Runtime-event totals may grow under the separately running a4 Direct service and are not an immutable v0.6 baseline input. The sealed legacy bytes/hash and complete source record are the gate; no migration, provider call, credential read, discovery request, deployment, automation, or shared-state write occurred during v0.6 baseline inspection.

## v0.6 dynamic-coordination implementation train

The isolated v0.6 branch implemented the offline control plane in focused, verified commits. The final pre-release-gate code subject is:

```text
branch = feature/macr-v0.6-dynamic-coordination
commit = 13c975e90ee5283cb73142e9ab72612bba619146
tree   = b6af1a038bfe1b733264e29aa02a44dd1cee6c9d
```

| Boundary | Commit |
|---|---|
| T1 durable ordered queue, exact batch authority, aggregate admission | `1a164e5dfda9977bee6c91388428c992caafbd72` |
| T2 constrained coordinator revision proposals | `ebec124c74b068f2a9026b20e353fb2693f6bddd` |
| T3 digest-only target ownership and cross-file verification | `f2096c99598be8a82791b7a1e3fd86eb16fda8c9` |
| blinded differential manifest/replay harness | `13c975e90ee5283cb73142e9ab72612bba619146` |

These commits add no standing provider authority and perform no discovery request, paid/local generation, real migration, seal change, merge, release, deployment, adoption, automation, or resident binding. T2 output cannot issue authority; T3 verification cannot materialize; differential public rows cannot reveal model labels. The separate final offline checkpoint records the later clean verifier/docs subject rather than rewriting these historical code commits.

## v0.6 first offline gate candidate (later rejected)

The first verifier/docs/runbook subject `ca374ec1be30d675dc10d62354c7f5b44d7dfb9e` / tree `61a1988a59096823640c942687ae81904b72e13b` was clean and ran `scripts\verify-v06.ps1` twice. Both runs returned exit 0 and the byte-identical summary digest `843c1b9a4f0761c23fa03619ae9b2d8fed2499fa6c645f73a52cc9194902761f`: 440 tests with two existing platform skips, 103 named v0.6 controls, schemas 6/2/2, census zero, network false, provider generation false. A later twin review found three Important gaps despite these green automated results, so this subject is historical rejected evidence and carries no current checkpoint status.

## v0.6 repaired final offline gate evidence

Commit `6c66eff1ce200c4d07506310794ea9ac89a42895` / tree `5172fb7b0d72d3a733ec06bf7aa1d7f598b68e2f` closes cross-plan target alternatives, pre-digest T1 path aliases, and actual probe-pack replay binding. The primary seat ran the clean gate twice with byte-identical summary digest `38b6087445be0e0232bf4f415d87ccd7fe2adbb4dc5ddc18af80ff5b0a680832`: 443 tests, two existing platform skips, 106 named controls, schemas 6/2/2, census zero, network false, provider generation false. The same authorized twin independently reproduced all three closures, ran 3 exact regressions, 24 adjacent tests, and the complete gate; Critical 0, Important 0. The live runbook remains unexecuted.

## v0.6.0a0 local release decision

On 2026-08-30 Neo explicitly authorized updating, merging, and publishing the verified v0.6 work. The release remains version `0.6.0a0` and is tagged `v0.6.0a0` only after merged-result verification. It is an offline candidate, not a claim that the live runbook passed. At the time of authorization this repository had no configured remote, so local merge/tag and external push are distinct states; no external publication is inferred.

## v0.6.0a1 T1 operability and model-local token repair

Post-release MSSP pressure testing retained the clean `v0.6.0a0` positives but found two product gaps and one conservative operational interaction: `PlanQueue` had no global `reconciliation_required` enumeration, no production consumer traversed `MacrRuntime`/Vault/events/accounting, and concurrent reviewer PowerShell command lines containing the synthetic invoker marker could make the unchanged census fail safely. Neo authorized a bounded offline repair and separately requested model-local context/output settings with larger external defaults. No implementation subagent, real provider call, shared-runtime migration, merge, tag, deployment, or live-route activation was authorized for the repair branch.

The implementation train is exact and append-only:

| Boundary | Commit |
|---|---|
| model-token policy contracts/store | `a9c72346ed4273e3848ddb553b2d0408b1d80b88` |
| Direct per-model pinned policy | `e5052583a25baf9cba3928035c381141dbffa869` |
| delegated limits and GLM approval schema 2 | `dbcd8368b609d0fb9f12e60508c25dad408abff4` |
| global queue reconciliation/status | `cd8286843d957e27c34845e4611e69f2d8a259cd` |
| strict private T1 manifests | `f5ff4ccbf0cd8dad9221b8dc10dded5d31c38361` |
| dual-authority staging | `df92aae165025f1cbd6022d4661f90d6242e1ba6` |
| one-attempt production worker | `531b4745e664c35995fb42bf7e537bf61fc304f6` |
| three-process complete-path mock | `8c5c4da8172cc976d6f58b37e9bf76066f691b10` |
| quiet census admission | `4404fd2012b9789ed6f732c320e188659ec93e6d` |

Token-policy state is append-only in store schema 1 at `settings\model-token-policies.sqlite3`. Policy contract v2 serializes its minimum task output into the digest. Policy-v1-base override rows remain immutable and are counted as `legacy_pre_quality_floor`; activation/effective use fails typed until a new revision targets the v2 base. New Direct conversations pin one exact provider/model policy; old conversations are not rewritten, legacy Grok snapshots cannot dispatch, and verified loopback Qwythos v1 snapshots retain their original local limits in memory. Delegated runtime records the exact policy digest, and GLM approval schema 3 binds the same digest plus context/output envelope. The ordinary presets deliberately differ: Grok hard context 400,000 and output floor/default 32,768; GLM/Gemini 512,000 with floor/default 16,384; MiniMax 180,000 with immutable provider-limited output 2,048; Qwythos-9B-v2 8,192 / 4,096 without a cloud floor. The T1 GLM preset is a separate 128,000 / 16,384.

T1 schema-3 staging uses v3 member and manifest digest domains and requires a strict three-member manifest, three existing GLM host approvals, exact T1 token-policy-v2 digest, batch authority, dispatch authority, 16,384 output tokens, USD 0.010 per member, USD 0.030 aggregate and USD 0.040 campaign. Schema 2 is immutable audit evidence reported as `legacy_pre_quality_floor` and cannot satisfy the new route. One worker claims at most one plan-scoped member. Provider completion does not verify, materialize, accept, merge, or deploy. Dispatch ambiguity enters global `reconciliation_required`, blocks later claims, and explicit resolution revokes the old batch so only a separately authorized new manifest can continue.

The original concurrent census RED remains evidence; it is not erased by later quiet-window GREEN controls. The predicate was not weakened. Updated verifiers coordinate through the named `MACR_V06_QUIET_CENSUS` mutex and require five zero samples before and after the full gate. Arbitrary external processes remain outside mutex control.

The `v0.6.0a0` tag and release decision remain immutable historical evidence. v0.6.0a1 is offline-only until a later exact clean checkpoint and explicit Neo live authorization. No live provider call occurred during this repair.

The first exact clean a1 checkpoint subject was commit `74e81ae5133dd9e9e34fdfc11dae341a10310b2a` / tree `26a232ae138be7dd7f7f21bd4fb62c9d4951711c`. Two complete `verify-v06.ps1` runs each ran 482 tests (480 passed, two existing platform capability skips, zero failures) plus 127 passing targeted tests, five pre/post quiet samples, network false, provider generation false, and byte-identical summary digest `6f93542eac54462bebb03fab8e504c411298d5e01a8c0d0103d28a39e3bd9c24`. This is offline verification, not live acceptance or route activation.

## v0.7.0a0 Phase-C Alpha release

Neo authorized the completed Phase C checkpoint to enter the v0.7 version line.
The accepted offline implementation base is commit
`84a562fe58de8a279d427f6dd33ddc05410d1b1c` / tree
`b0bbbc2210e50d47d6447d1e7bdf32c4aaa2e05f`. It establishes Agent contract and
state kernels plus semantic working state only. Phase D, governed action,
temporal continuation, closed loop, shared Agent-state activation, and live use
remain absent or NotMeasured.

The release version is `0.7.0a0`; `0.7.0a1 remains reserved` for the later A-H
bounded single-Agent MVP. Claude Code direct provider access is a deferred
subscription-client host-adapter requirement. No `ANTHROPIC_API_KEY`, provider
generation, credential read, shared runtime migration, or live route is involved
in this version transition.

## v0.7.0a0 host-adapter and GLM capability-policy candidate

Neo authorized repairing the measured locale/timeout/failure/accounting issues,
letting Claude Code use MACR's other providers, and preparing an initial bounded
GLM capability increase. Work was isolated at
`D:\Ai\work together\MACR\.worktrees\v070a0-host-adapters-glm-policy` on
`feature/v070a0-host-adapters-glm-policy`, based on release commit
`20a2d5e02e34c0faf74fcaa5c40721df9aa37763` / tree
`a16a181a96e7ede415648872b68263db43a02d13`.

The implementation train is append-only:

| Boundary | Commit |
|---|---|
| reviewed design | `0af3c1bb30fac4b039497198d93ffda01cd837a5` |
| locale-safe raw-byte and JSON test harness | `d92ec10ada88642abcf04980082a0eb85b049e7d` |
| operator-owned provider capability policies | `31660b6` |
| tier-bound authority, typed failure and accounting schema 3 | `cc4fd99` |
| GLM approval schema 3 and T1 manifest schema 2 | `be95675` |
| governed shared host adapter and read-only status surfaces | `0a0ba159` |
| pre-issued-authority tier activation verifier | `f838bf87eb4b002a08dd2fc6dcf6c124027f857f` |
| deterministic wheel verification | `6547c3af6b8cbc46e08a73ba1fd4137bc7e4ca24` |
| close injected verifier, rogue policy and cached-head escalation | `c938136cecd2836f0182ad57ef431dd28251b939` |
| canonical state-root governance and schema-2 migration | `36b73bebd6e07a81332c5b8d18ecff01ff46af15` |

The final code/gate subject is `36b73bebd6e07a81332c5b8d18ecff01ff46af15` /
tree `ad6182a50afc1c15ba8b97e3ab2ed5cc707bbca9`. Package version remains
`0.7.0a0`.

The former GLM transport `min(max_latency_s, 300)` was replaced by exact tier
validation: standard permits at most 300 seconds and the inactive
`extended_text_candidate` policy permits at most 900 seconds. Both remain
non-sensitive, candidate-only, no-patch, no-write and no-tools. Tasks/models
cannot select or activate a tier. Activation consumes a pre-issued authority
whose scope binds the full provider/model/tier/revision/policy/limit digest.

Approval schema 3 binds task ID, exact latency and tier digest. New typed
approval records and T1 schema-2 members carry that evidence; prior records and
schema-1 manifests remain immutable `legacy_pre_tier` evidence and cannot
satisfy new dispatch. Runtime schema 7 and accounting schema 3 add nullable
tier/failure fields without rewriting historical payloads. Read-only status
commands enumerate legacy/current state and cost/outbox totals without prompts,
answers, keys, paths or provider calls.

Claude Code and Codex can use the existing MACR CLI under honest CLI origin.
The offline `MacrHostAdapter` consumes an injected host-owned verifier and
pre-issued operator authority/connectivity grant; it cannot mint either.
Environment variables and hook JSON alone remain insufficient for
`task_local_host_observed`, so live host binding is `NotMeasured`. Claude
subscription still grants no `ANTHROPIC_API_KEY` authority.

A clean Phase C run on code commit `0a0ba159` executed 777 inherited tests plus
the Phase A/B/C focused gates with two existing platform capability skips, zero
failures, network false, provider generation false, Phase D false and clean Git
state. The subsequent activation-verifier commit passed all six focused store
tests.

Two green gates on the first documentation subject revealed differing wheel
hashes despite identical state/replay evidence. A minimal two-build probe traced
the difference to five generated `.dist-info` ZIP timestamps. Phase B/C now pin
`SOURCE_DATE_EPOCH` to the candidate commit timestamp. Two consecutive clean
gates on `6547c3a` each ran 778 inherited tests and produced identical wheel SHA
`220e4f9907a81347d620dc9d93de3a5c89a47ebb0c996f466553ac87ad60f283`,
epoch `1788771048`, and identical state/replay digests. No key read, real
provider call, shared-state migration/activation, merge, tag, push, release,
deployment or adoption occurred in this candidate.

The governing twin rejected the earlier green candidate after reproducing an
allow-all activation-verifier attack, a rogue 3,600-second patch/write policy,
cached active-head drift, foreign-state-root authority reuse, and a missing
schema migration for activation authority provenance. The repaired governance
surface has no public raw activation method, accepts only adapter-published
policies, rereads active head before runtime/T1 admission, requires canonical
sibling settings/runtime databases, and migrates schema-1 policy state to
schema 2 without trusting its old active pointer.

On exact `36b73be`, the twin independently verified foreign-root zero drift and
literal schema-1 preservation/fail-closed/reauthorization, then returned
`CONCUR` after 114 passing focused tests and one existing platform skip. Two
primary clean Phase C runs each executed 787 inherited tests and produced
identical wheel SHA
`b67e13954b4c85e12749169590d23953e72fc977aafa0f3bed757fdd4e613ccd`,
epoch `1788773322`, identical state/replay digests, network false, provider
generation false, Phase D false, and clean Git state.

## v0.7.0a0 dynamic T1 worker topology candidate

Neo rejected the earlier pressure-test count of three as a standing product
limit and directed T1 concurrency and cost envelopes to become operator
configurable. The implementation commit is
`bf993074881d9884f0e704b9bc7851ca5fb07a4f` / tree
`c583e7dd303ac348a064d85bc9648b07735801fa`.

T1 manifest schema 4 binds an explicit `worker_count`, an arbitrary nonempty
ordered member set within the existing strict 4 MiB manifest boundary, the
exact dispatcher set, positive per-member ceilings, their exact aggregate, and
an operator-selected campaign ceiling that covers the aggregate. Member and
manifest authority use v4 digest domains. Worker count may be lower than member
count, and an authorized dispatcher may be invoked again to drain later queued
work. No arbitrary three-worker or fixed USD 0.010/0.030/0.040 protocol ceiling
remains.

Schema 3 remains immutable audit evidence under
`legacy_fixed_three_workers`; schemas 1 and 2 retain their prior audit labels.
All three fail before staging or dispatch and are never silently upgraded. The
topology identity remains `T1_FANOUT_VERIFIED`; schema 4 carries the changed
contract.

The implementation RED/GREEN evidence includes a four-worker/five-member
dispatcher path, a five-process complete-path runtime/Vault/event/accounting
mock, dynamic cost relations, CLI count projection, and typed schema-3
rejection. The first post-implementation complete unit replay ran 814 tests
with zero failures and two existing platform capability skips. This replay was
offline: no provider call, key read, shared-state mutation, migration, or live
authority activation occurred. The final clean Phase-C gate is recorded in the
separate exact checkpoint after documentation is committed.

## v0.7.0a0 GLM fixed-key Claude/Codex handoff

Claude Code field feedback inferred that a missing `ZAI_API_KEY` entry in
`.env.example` meant the GLM credential had not been persisted. Read-only
source and runtime diagnosis disproved that hypothesis: the exact provider
profile uses `auth_mode=api_key_file`, accepts only `D:\KEY\GLM.txt`, and the
wrapper removes any inherited environment override. The current D-drive file
was an ordinary non-reparse-point file and passed the bounded loader without
printing its value or digest. Offline doctor reported `glm_flash_worker` ready
as `configured_offline`.

The actual obstruction was the committed conformance example's stale approval
digest after later policy-envelope changes. A RED integration test reproduced
the mismatch. Commit `7377f27fb3385c903ae4db538f14fcedce3260df` /
tree `07d0ed6ce5788363741a22ce046971bc79211a52` updates the exact example,
adds a Claude/Codex operator quickstart and failure map, and makes the example
digest an executable offline contract rather than untested prose.

Under Neo's explicit approval, one 30-day host approval was created for the
exact public `glm-flash-conformance-001` envelope. This was a deliberate shared
runtime approval-state mutation: the provider read the fixed credential only
to authenticate that local record. A second preflight with `ZAI_API_KEY`
absent returned exit 0. No provider transport, generation, retry, fallback, or
currency cost occurred. The approval does not authorize translation tasks or
other content; every different task still requires its own exact digest and
host record.

## v0.7.0a0 provider transport telemetry repair

On 2026-09-08 a bounded Claude Code GLM batch stopped after four rapid
`ProviderProtocolError` results. Read-only accounting showed that the reported
29 unknown runs were the all-provider lifetime total: GLM owned 26 and Grok
owned three. Of the GLM rows, nine historical rows had no typed failure, 13
were `ProviderUnavailableError` runs lasting roughly 280–291 seconds, and only
the four new runs were rapid protocol failures. Their dispatch-to-terminal
times were 0.419–0.582 seconds. Same-task retries retained exact member,
model-token-policy and provider-tier digests. No other MACR provider invocation
overlapped any of the four failures.

The upstream cause was not recoverable because the shared HTTP transport knew
the HTTP status but the runtime reduced every exception to its Python class and
an empty observation. Z.ai documents an outer HTTP status plus an inner
business error code; rate/concurrency/high-traffic and server errors therefore
could not be distinguished. The batch remained stopped. No historical status
or cost was inferred, and successful later dispatches did not reconcile prior
unknown runs.

Neo authorized a P0 observation repair without retry, pacing, worker-count, or
provider-policy changes. Implementation commit
`ddcdb67048039bbaee6a23c2011e0b17443db109` / tree
`d57ac3dd548b5875c88c036b6b29e3b3c714f17` preserves only elapsed time,
three-state network-attempt/response-received evidence, HTTP status, bounded
provider error code, and transport stage. Remote HTTP message/body and
connection reason are omitted. Accounting schema 4, accounting-outbox schema
3, and terminal-event contract 3 carry the fields; old values remain null.
Provider/date filters and failure grouping were added to the read-only
`accounting-status` surface.

Before integration, the repository root gained `CURRENT_VERSION_USAGE.md` as
the short operational index for Direct Chat, Claude/Codex GLM use, filtered
accounting, dynamic T1, and the Phase-C/future boundary. It contains no
credential value or standing provider authority.

The implementation suite ran 822 tests with zero failures and two existing
platform capability skips while treating `ResourceWarning` as an error. A
copy-only replay of the live 137-row accounting database migrated schema 3 to
4 with identical row count and historical-field digest, exactly five additive
columns, and zero fabricated historical telemetry. The source database hash
remained unchanged and the replay copy was removed. No provider call, retry,
fallback, source-accounting migration, billing reconciliation, or expenditure
occurred during repair verification.

Neo then authorized merge, local activation, and GitHub publication. The live
database was sealed at zero invokers, zero unsettled rows and zero WAL bytes; a
byte-identical 360,448-byte pre-schema4 backup was retained under the D-drive
MACR state backup directory. The additive live migration preserved all 137
historical rows and their predeclared field digest, created exactly five nullable
transport columns, and left all historical transport values null. Filtered
readback preserved the 17-success/four-unknown 2026-09-08 GLM view. Activation
performed no provider call or billing reconciliation; future accounting writes
will naturally supersede the post-migration database hash without invalidating
the backup or migration receipt.
