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
implementation_commit = 674b3bb88dc086f6d8d310194717ab46397c76c0
implementation_tree   = 487edab4de91af7ec46bbc73be06655f2c37a286
```

The initial a3 implementation/checkpoint pair `4a54acbdd405ee955346f112a1a45e3798850841` / `575b9b5555874067ba999b84f5176ce19dfa7853` was independently rejected after reproducing cross-hash duplicate imports and additional classifier underblocking. It remains historical and carries no route authority.

The second pair `dd0e36831f8b64556aa2df5ad4f6a8abdc2d3f59` / `ee8fe2815e05ab01fa4af7596fe8006353ed6a74` closed those findings but was independently rejected after generic file URIs and delimiter-starting Windows path components bypassed the classifier. It also remains historical and carries no route authority.

| Evidence | Bytes | SHA-256 |
|---|---:|---|
| `D:\Ai\work together\amral-research-trees\collatz-verification-zhuiheng\reports\RUN-033-HARD-ZETA-AU2D5-ANNULAR-RESIDUE.md` | 11,301 | `C949E205010F7AC18F3A12A86446EC434F449803C36A46899D40DC2AA3155EAD` |
| `D:\Ai\work together\amral-research-trees\collatz-verification-zhuiheng\data\external\hardzeta-corpus-manifest.json` | 45,577 | `2CF0874C82A584457B3458742EA4B54BED8092714384AEB63F17496974403589` |
| `D:\Ai\work together\MSSP_Architect_Exchange\evidence\2026-08-28-pragma-macr-route-drift-after-t6.md` | 2,284 | `6C0FE0A103601CBFA7371A68E04DB541E020930B3B23917832B27D73F78246B7` |
| `D:\Ai\work together\MSSP_Architect_Exchange\evidence\2026-08-28-pragma-post-migration-legacy-tail.md` | 3,145 | `3A91A0586253E533D213D9C1768B5778281DB17B2890550248130BE4F0CF8CF3` |

The 132-document manifest remains external evidence. Its exact member bytes were not resolvable from current searchable D-drive paths during this repair, so no local 132/132 rescan is claimed. Read-only inspection also found the legacy source had advanced from the previously migrated 64-event hash to 68 events under a new hash while SQLite retained only the old complete source record. The repaired comparison logic measured 64 exact prior identities, four new identities, and zero conflicts without writing. The a3 route therefore remains offline-only until old writers are retired, the source is sealed read-only, and an explicitly authorized idempotent 68-event reconciliation completes. No provider call, key read, approval creation, second legacy migration, shared-runtime write, merge, release, deployment, or publication occurred.
