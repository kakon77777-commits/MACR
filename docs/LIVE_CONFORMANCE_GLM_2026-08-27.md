# GLM delegated-worker live conformance — 2026-08-27

## Evidence boundary

- Evidence status: candidate-only research evidence; it grants no verification, acceptance, deployment, identity, or private-residence authority.
- Runtime release candidate: MACR v0.4.0.
- Provider ID: `glm_flash_worker`.
- Direct returned model: `glm-5.3-flash`.
- Completion observed at: `2026-08-27T06:19:40.1426760+00:00`.
- Prompt bodies, answer bodies, response identifiers, account identifiers, credential values, credential digests, local paths, and workspace names are intentionally absent.

## Dispatch controls

- Explicit `delegable` authorization: true.
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

## Candidate result

- Candidate status: `candidate_success`.
- Exact returned-model match: true.
- Exact expected-text match: true.
- Prompt tokens: 175.
- Completion tokens: 38.
- Reasoning tokens: 31.
- Total tokens: 213.
- Output artifact count: 0.
- Tool-event count: 0.
- Cost kind: `estimated`.
- Pricing basis version: `zai-2026-08-27`.
- Conservative list-price estimate USD: 0.00004525.
- Current promotional-price estimate USD: 0.000022625.
- Credential environment present after wrapper exit: false.

## Ledger checks

- Matching dispatch/completion event count: 2.
- Dispatch records `delegable=true`: true.
- Completion records exact model and bounded usage metrics: true.
- Forbidden prompt, answer, credential, key-name, and local-path match count: 0.
- Ledger privacy acceptance: true.

## Cost interpretation

- Currency values are estimates derived from public token pricing, not invoice-grade provider billing.
- The conservative list-price estimate controls MACR budget admission; promotional pricing is informational only.
- Provider billing remains authoritative.
