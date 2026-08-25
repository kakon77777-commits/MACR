# MACR v0.2 live provider conformance — 2026-08-26

Status: passed after one documented Grok exact-output correction

## Scope and preflight

- Branch: `feature/grok-ollama-v0.2`
- Offline gate before live calls: 69 tests passed, compile and policy scans passed, `doctor.network_activity=false`
- Provider output classification: candidate-only; no verification or acceptance transition was created
- Credentials: injected into one process, never printed, committed, or copied into the ledger

## Ollama Qwythos acceptance

Observed completion: `2026-08-26T00:37:40.598044+08:00`

| Field | Observation |
|---|---|
| Provider | `ollama_qwythos` |
| Model | `hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M` |
| Manifest digest | `5008e78bba127262f3f7ad86425bb49a5e0f47bb1959a4d30bfe17832ec45856` |
| Status | `candidate_success` |
| Exact fixed-string match | true |
| Input tokens | 234 |
| Output tokens | 7 |
| Total duration | 31,111 ms |
| Load duration | 30,512 ms |
| Prompt evaluation duration | 408 ms |
| Generation duration | 181 ms |
| Currency cost | USD 0 |
| Post-test model residency | unloaded; `ollama ps` returned no model rows |

The request used loopback-only transport, `internet=false`, `local_only`, `--allow-local`, no tools, `think=false`, and `keep_alive=0`.

## Grok 4.6 acceptance

Both requests used the `grok` profile, exact returned model `grok-4.6`, high reasoning, `store=false`, no tools, a 64-token visible-output bound, and a USD 0.01 task budget.

| Completion time | Candidate status | Exact match | Input | Cached | Output | Reasoning | Tools | Cost USD |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `2026-08-26T00:41:09.917695+08:00` | success | false | 840 | 512 | 381 | 331 | 0 | 0.003198 |
| `2026-08-26T00:44:07.722205+08:00` | success | true | 869 | 512 | 84 | 75 | 0 | 0.001474 |

Total Grok conformance cost: USD 0.004672.

The first transport/model/cost candidate succeeded but failed exact-output verification because the shared worker instruction requested evidence and warnings in addition to the task's exact-output goal. It was not promoted to acceptance. A regression test was observed failing, the shared instruction was made goal-aware, both conformance examples disabled summary/evidence output, and the complete 69-test offline gate passed before the single retry.

The second candidate matched the expected fixed string exactly. `store=false` disables Responses continuation state for this request but is not evidence of account-level contractual Zero Data Retention.

## Ledger and secret audit

The canonical ledger contained six events: three dispatch events and three candidate-completion events. Assertions after both providers completed:

- neither fixed-string answer was present;
- no `xai-` credential prefix was present;
- no private unit-test answer was present;
- provider/model/status/token/cost/duration metadata was present;
- the process environment no longer contained `XAI_API_KEY`;
- no prompt, TaskContract body, reasoning content, warning text, authorization header, or remote error body was persisted.

## Acceptance boundary

This evidence accepts provider connectivity, exact profile/model routing, request policy, result normalization, actual cost capture, local unloading, and content-free ledger behavior for MACR v0.2. It does not accept model claims as factual truth, grant tool authority, establish resident identity, or implement verifier/acceptance automation.
