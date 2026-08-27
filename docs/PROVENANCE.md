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
