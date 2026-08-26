# Google GenAI live conformance — 2026-08-26

## Evidence boundary

- Evidence status: candidate-only research evidence; it grants no runtime, publication, deployment, or identity authority.
- Provider schema: v2.
- Release candidate: MACR v0.3.0.
- Calls were explicitly operator-authorized and were not automatic retries.
- Automatic retry used: false.
- Provider fallback used: false.
- Tool use enabled: false.
- Grounding enabled: false.
- Prompt bodies, answer bodies, response identifiers, account identifiers, credential data, local paths, artifact paths, artifact bytes, and artifact digests are intentionally absent.

## Credential staging

- Credential shape valid: true.
- Source and staged target byte lengths equal: true.
- Source and staged target SHA-256 equal: true.
- Idempotent second staging run copied data: false.
- Credential values printed or persisted in Git evidence: false.

## Bounded-response diagnosis

- Completion event timestamp: `2026-08-26T22:48:34.855830+08:00`.
- Provider: `google_gemini`.
- Candidate status: `candidate_failure`.
- Configured output-token bound: 64.
- Manually authorized diagnostic candidate count: 1.
- Diagnostic finish reason: `MAX_TOKENS`.
- Diagnostic part count: 1.
- Diagnostic input tokens: 77.
- Diagnostic output tokens: 3.
- Diagnostic thought tokens: 57.
- Diagnostic total tokens: 137.
- Root-cause classification: the 64-token bound was insufficient for medium thinking plus a visible answer.
- Corrective bound for text and multimodal examples: 256.
- Corrective bound for the image example: 2048.
- Automatic retry after failure: false.
- Fallback after failure: false.

## Exact-text conformance

- Completion event timestamp: `2026-08-26T22:52:24.498557+08:00`.
- Provider: `google_gemini`.
- Returned model: `gemini-3.7-flash`.
- Candidate status: `candidate_success`.
- Exact expected-text match: true.
- Input media count: 0.
- Output artifact count: 0.
- Input tokens: 77.
- Output tokens: 9.
- Thought tokens: 79.
- Total tokens: 165.
- Cost kind: `estimated`.
- Estimated cost USD: 0.00038775.

## Multimodal-understanding conformance

- Completion event timestamp: `2026-08-26T22:52:53.019596+08:00`.
- Provider: `google_gemini`.
- Returned model: `gemini-3.7-flash`.
- Candidate status: `candidate_success`.
- Exact expected-text match: true.
- Input media count: 1.
- Input media bytes: 181.
- Output artifact count: 0.
- Input tokens: 1161.
- Output tokens: 4.
- Thought tokens: 50.
- Total tokens: 1215.
- Cost kind: `estimated`.
- Estimated cost USD: 0.00107325.

## Image-generation conformance

- Completion event timestamp: `2026-08-26T22:53:26.509313+08:00`.
- Provider: `google_image`.
- Returned model: `gemini-3.1-flash-image`.
- Candidate status: `candidate_success`.
- Output artifact count: 1.
- Artifact MIME: `image/jpeg`.
- Artifact dimensions: 1024 × 1024.
- Artifact byte length: 29760.
- Independent artifact existence check: true.
- Independent MIME check: true.
- Independent dimension check: true.
- Independent byte-length match: true.
- Independent SHA-256 match: true.
- Independent image decode: true.
- Independent visual acceptance: true.
- Input tokens: 53.
- Output tokens: 1120.
- Thought tokens: 0.
- Total tokens: 1173.
- Cost kind: `estimated`.
- Estimated cost USD: 0.0670265.

## Ledger privacy and metric checks

- Inspected event count: 14.
- Forbidden-content match count: 0.
- Required-metric missing count: 0.
- Prompt and answer content absent: true.
- Credential names and fields absent: true.
- Local media and artifact paths absent: true.
- Artifact digest absent: true.
- Exact provider model identifiers present: true.
- Media and artifact metrics present: true.
- Cost kind and pricing-basis version present: true.
- Ledger privacy acceptance: true.
- Ledger metric acceptance: true.

## Cost interpretation

- Sum of estimates for the three successful acceptance calls: USD 0.0684875.
- The initial failed call and the manually authorized diagnostic are not included in that sum and may still be billable.
- This document is not an invoice or billing-total assertion; Cloud Billing remains authoritative.
