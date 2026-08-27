# GLM delegated-worker live conformance — 2026-08-27

## Evidence boundary

- Evidence status: candidate-only research evidence; it grants no verification, acceptance, deployment, identity, or private-residence authority.
- Runtime release candidate: MACR v0.4.0.
- Exact tested implementation commit: `01a8329dbfb61f9b6370926d1b67dd4c6293e7fe`.
- This evidence-only documentation commit follows the tested implementation commit.
- Provider ID: `glm_flash_worker`.
- Direct returned model: `glm-5.3-flash`.
- Final completion observed at: `2026-08-27T15:31:16.375458+08:00`.
- Prompt bodies, answer bodies, response identifiers, account identifiers, credential values, credential digests, local paths, and workspace names are intentionally absent.

## Dispatch controls

- Explicit `delegable` authorization: true.
- Delegation class: `non_sensitive_routine`.
- Complete credential-free request approval SHA-256: `240cca0ff34342fe73d5e170a48dbada669866195a46e4be38372b1d892dbc7e`.
- Separate external host-approval record structurally accepted: true.
- Host-approval HMAC verified inside provider invocation before transport: true.
- Privacy classification: `public`.
- Input item count: 0.
- Write-scope item count: 0.
- Patch authority requested: false.
- Independent verification required: true.
- Explicit network opt-in: true.
- Direct provider route: true.
- Automatic retry used: false.
- Provider fallback used: false.
- Tool use enabled or observed: false.
- Filesystem authority granted: false.
- Wrapper credential read or export: false.

## Exact-head candidate result

- Candidate status: `candidate_success`.
- Exact returned-model match: true.
- Exact expected-text match: true.
- Prompt tokens: 139.
- Completion tokens: 63.
- Reasoning tokens: 56.
- Cached tokens: 0.
- Total tokens: 202.
- Output artifact count: 0.
- Tool-event count: 0.
- Cost kind: `estimated`.
- Pricing basis version: `zai-2026-08-27`.
- Conservative list-price estimate USD: 0.00005235.
- Dated promotional-price estimate USD: 0.000026175.
- Promotional price observation date: `2026-08-27`.
- Credential environment present after wrapper exit: false.

## Ledger checks

- Matching dispatch/completion event count across both bounded live observations: 4 (2 dispatch and 2 completion).
- Dispatch records `delegable=true`: true.
- Latest dispatch records exact delegation class and approval digest: true.
- Completion records exact model and bounded usage metrics: true.
- Forbidden prompt, answer, credential, key-name, and local-path match count: 0.
- Ledger privacy acceptance: true.

## Earlier pre-hardening observation

- Tested implementation commit: `128f067`.
- Completion observed at: `2026-08-27T06:19:40.1426760+00:00`.
- Candidate status and exact expected-text match: successful.
- Prompt/completion/reasoning/total tokens: 175 / 38 / 31 / 213.
- Conservative list-price estimate USD: 0.00004525.
- Dated promotional-price estimate USD: 0.000022625.
- This observation predates authenticated external host approval and is retained only as historical evidence; the exact-head result above supersedes it for implementation conformance.

## Cost interpretation

- Currency values are estimates derived from public token pricing, not invoice-grade provider billing.
- The conservative list-price estimate controls MACR budget admission; promotional pricing is informational only.
- Provider billing remains authoritative.
