# Provider status

Updated: 2026-09-07 for MACR v0.7.0a0 Phase-C Alpha feature candidate

| Provider ID | Required model/route | Credential | Billing | Runtime state |
|---|---|---|---:|---|
| `minimax` | exact `MiniMax-M2.7` or `MiniMax-M2.7-highspeed` | `MINIMAX_API_KEY` | allowed | adapter implemented; 180,000 hard context / 2,048 output policy |
| `grok` | `grok-4.6`, reasoning high | `XAI_API_KEY` | allowed | delegated + Direct adapters implemented; Direct live acceptance pending |
| `grok_standard` | `grok-4.3` | `XAI_API_KEY` | allowed | adapter implemented; manual profile only |
| `ollama_qwythos` | installed Qwythos-9B-v2 Q4_K_M | none | zero | delegated + Direct adapters implemented; Direct live acceptance pending |
| `google_gemini` | `gemini-3.7-flash` | D: service-account file + project environment | allowed | adapter implemented; live v0.3 candidate evidence recorded |
| `google_image` | `gemini-3.1-flash-image`, one 1K output | D: service-account file + project environment | allowed | adapter implemented; live v0.3 candidate evidence recorded |
| `glm_flash_worker` | `glm-5.3-flash`, reasoning max | provider-late fixed `D:\KEY\GLM.txt` | allowed | native pre-validation observation adapter; prior v0.4 live candidate evidence retained |
| `google_veo_fast` | `veo-3.1-fast-generate-001` | not loaded | unavailable | disabled; no long-running-operation adapter |
| `google_tts` | `gemini-3.1-flash-tts-preview` | not loaded | unavailable | disabled; no audio adapter |
| `google_lyria` | `lyria-3-clip-preview` | not loaded | unavailable | disabled; no music adapter |
| `claude_subscription` | approved subscription client not selected | subscription login | API forbidden | disabled |

## Shared execution and Direct alpha status

Delegated callable profiles enter the v0.7.0a0 CLI through current-epoch authority, fenced lease, SQLite dispatch/accounting records, private candidate capture, and return-contract validation. Direct Grok/Qwythos turns keep the separate `DirectRuntime` contract. Phase C adds semantic proposals and host-governed commits but does not invoke providers. T1 has explicit `t1-stage` and one-member-per-invocation `t1-worker` product paths backed by the real GLM adapter. No standing T1 authority follows from installation or release: live use still requires one current schema-4 manifest, its exact member approvals, explicit connectivity opt-in, and operator invocation.

Provider reachability, billing entitlement, account configuration, and live T1 acceptance are not implied by an offline checkpoint. The dynamic five-process T1 gate uses an injected fake transport; no real provider generation occurred in that gate. Direct Chat is locally executable. A shared Codex/Claude host-adapter core is implemented offline; live host-owned binding and autonomous routing remain unavailable/NotMeasured.

Accounting's `soft_warning` state remains distinct from each delegated provider adapter's hard task-budget gate. The Direct local `operator_managed` profile is now active for newly created Direct conversations and is warn-only; exact settings are pinned per conversation.

## Exact model-token policy status

The active token controls use policy contract v2 with an explicit digest-bound floor and append-only store schema 1 at `settings\model-token-policies.sqlite3`: Grok 4.6/4.3 hard context 400,000, floor/default 32,768 and max output 65,536; ordinary GLM 5.3 Flash hard context 512,000, minimum 32,768 and default/max 65,536; Gemini 3.7 Flash hard context 512,000, floor/default 16,384 and max output 65,536; MiniMax M2.7 variants hard context 180,000 and provider-limited 2,048 floor/max; Qwythos-9B-v2 hard context 8,192 and max output 4,096 with no cloud floor. The separate T1 GLM preset is 128,000 context, 32,768 minimum and 65,536 default/max. An override never changes provider/model identity or immutable provider ceilings/floors, and cannot reduce GLM's task-specific 65,536 real-work requirement. `capability-status` reports content-free current/legacy/invalid/active override counts; a policy-v1-base override is immutable `legacy_pre_quality_floor` evidence and fails typed activation/use.

## Grok policy

The operator approved Grok API activation on 2026-08-25. A direct transport smoke test authenticated successfully and a minimal Grok 4.3 response cost USD 0.0002734. This established API access only; the default MACR profile is Grok 4.6.

Every MACR Grok call requires:

- process-only `XAI_API_KEY` injection;
- `--allow-network`;
- a public or explicitly approved internal task;
- positive `max_cost_usd` and bounded `max_output_tokens`;
- `store=false`, no tools, exact returned-model equality, and actual-cost capture.

Grok 4.6 failure never invokes Grok 4.3 automatically.

## Ollama/Qwythos policy

Observed installation:

```text
model  = hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M
digest = 5008e78bba127262f3f7ad86425bb49a5e0f47bb1959a4d30bfe17832ec45856
size   = 6,657,768,737 bytes
```

The direct local smoke test used an 8,192-token context, observed 86% GPU / 14% CPU allocation, completed at 34.36 generated tokens per second, and unloaded successfully with `keep_alive=0`.

MACR still treats Qwythos output as unverified. Low refusal does not imply accuracy, and this release grants it no filesystem, network, tool, or private-resident access.

## Google policy

The active v0.3 profiles are exact `gemini-3.7-flash` for text/multimodal understanding and exact `gemini-3.1-flash-image` for one 1K image. Every invocation requires explicit `--allow-network`, a public or approved internal task, positive task-level budget, named Google environment values, and a structurally valid service-account file on D:.

MACR uses `google-genai>=2.17,<3`, passes credentials explicitly, fixes total SDK attempts to one, and enables no grounding or tools. Generated image bytes are decoded, MIME-checked, hashed, and atomically persisted without overwrite or recompression.

Currency cost is estimated from a dated public pricing basis when the API does not return invoice-grade cost. Cloud Billing is authoritative; current credits and expiration dates do not change provider behavior or guarantee free use.

Veo, TTS, and Lyria remain disabled until separate artifact, duration, long-running-operation, pricing, and live-verification designs are approved.

## GLM delegated-worker policy

`glm_flash_worker` is a low-cost external contractor for explicitly non-sensitive routine text work. It uses only the direct Z.ai general API endpoint and exact `glm-5.3-flash`; the Coding Plan endpoint, OpenRouter, substitute models, tools, retries, and provider fallback are not enabled.

Provider capabilities are operator-owned and provider/model scoped. `standard`
permits routine/conformance work up to 300 seconds.
`extended_text_candidate` permits non-sensitive routine, analysis, review and
code-text candidates up to 900 seconds. Both deny patches, write scope and
tools. A task cannot select a tier; activation consumes a pre-issued authority
witness bound to the full provider/model/tier/revision/policy/limit digest.

`task_type` is the provider execution/authority class. Project-local stages such
as Discovery, Classification, Identity, Extraction, Verification and Review do
not become new standard-tier values merely because a workflow uses those
labels. Routine, non-sensitive, no-tool/no-write instances may use
`delegated_routine`; genuinely privileged analysis/review/code tasks require the
matching extended-tier type. Preflight type rejection exposes the safe requested
identifier and exact active-tier allowlist without task content.

Dispatch requires all of:

- `delegable=true` on the task contract;
- exact `non_sensitive_routine` classification plus a current SHA-256 approval manifest over the full request, route/model, privacy, limits, and budget;
- a separate unexpired HMAC-authenticated host record with fixed author role, nonce, creation time, and expiry;
- `public` or explicitly `internal_approved` privacy;
- `internet=true`, positive latency and cost budgets, and `text_generation` capability only;
- empty `workspace.write_scope`, no requested patch authority, and independent verification;
- empty inputs or bounded text-only inputs with non-path labels.

The outbound request excludes local task/workspace identity and currency budget. Credential-free preflight validates structure without reading a key; provider invocation repeats validation, reads fixed `D:\KEY\GLM.txt`, verifies the approval HMAC, and only then permits network transport. Health reads metadata only. Candidate output is never verification or acceptance. Budget admission and recorded currency cost use conservative list pricing; the lower dated promotional estimate is informational only. GLM max reasoning uses a task-specific profile: short exact conformance requires 32,768, while every real workload requires 65,536. MACR never silently enlarges an approved envelope, and neither value guarantees visible content. An observed no-answer `length` response whose output is effectively all reasoning becomes `ProviderReasoningBudgetExhaustedError`, retains usage/cost evidence, records typed response-validation failure in accounting/events, and is never retried automatically. New HTTP/connection failures retain elapsed time and bounded response-boundary telemetry without remote prose; historical failures remain null and `unknown_after_dispatch` remains unreconciled rather than zero-cost.

Accounting schema 4 and terminal event contract 3 expose provider/date-filtered failure groups with `network_attempted`, `response_received`, `provider_http_status`, `provider_error_code`, and `transport_stage`. The fields are observations, not retry permission. A received HTTP error can still have unknown billing, and a later successful manual dispatch does not settle the earlier run.

For T1, `queue-status` exposes only bounded content-free state. Schema 4 binds ordered v4 member digests, an explicit worker count, and a v4 manifest digest to exact routes, role/privacy/context classes, targets, GLM approvals, the T1 token-policy-v2 digest, the exact profile-valid output value, per-member cost ceilings, their exact aggregate, an operator-selected campaign ceiling, expiry, and the dispatcher set. Current delegated real-work members require 65,536 output tokens. Member count may exceed worker count; worker count must be between one and member count and equal the number of authorized dispatcher IDs. Schemas 1, 2 and 3 remain inspectable respectively as `legacy_pre_tier`, `legacy_pre_quality_floor`, and `legacy_fixed_three_workers`, but cannot stage or dispatch. Stale schema-4 manifests carrying the prior T1 policy digest also fail before staging and are not rewritten. `reconciliation_required` blocks every later claim. There is no automatic retry, fallback, verification, materialization, or acceptance.

Provider Admission Kernel policy v1 governs GLM capacity across projects and
all delegated entry points. Effective target is 1, candidate target 2, hard
ceiling 8 and raw request weight 1. Only an exact pre-issued capacity authority
may activate target 2; 3–8 and auto-scaling remain NotMeasured. Project and
lane bindings live in authority scope v3 rather than task text. A saturated
request is BUSY before dispatch/accounting/key access. A no-response or
incomplete terminal consumes a reconciliation slot and opens the provider
circuit until exact evidence-bound resolution. `admission-status` is read-only
and content-free.

## Claude boundary

Do not read or use `ANTHROPIC_API_KEY`. A future Claude integration must be an explicitly approved subscription-client route and must not fall back to API billing.

### Claude Code CLI and deferred host-owned binding

Claude Code can invoke the existing MACR CLI today under `cli` attribution and therefore call the same configured provider registry—such as Grok, GLM, Google, MiniMax, or local Ollama/Qwythos—without converting Claude subscription access into Anthropic API billing. The offline `MacrHostAdapter` core uses the same model-local token policy, provider capability, authority/lease gates, candidate separation, and shared accounting as the Codex-facing route.

Trusted `task_local_host_observed` attribution still requires a host-owned verifier unavailable to generic/model shells and a pre-issued operator authority/connectivity grant. Environment variables and hook JSON alone remain forgeable discovery evidence. No cross-provider context transfer, Direct-conversation read permission, fallback, credential bridge, self-issued authority, or live host binding exists in this candidate. The current `claude_subscription` configuration remains disabled with `api_usage_allowed=false`.

Grok Direct enforces its 32,768 floor inside the adapter before reading the
credential. A legacy Grok conversation with a null or policy-v1 snapshot fails
as `legacy_direct_token_policy_incompatible` before message append, authority,
dispatch or network. Its preserved history can still be archived/deleted;
start a new conversation to obtain a current policy-v2 snapshot.
Verified legacy Qwythos v1 snapshots remain usable only on the loopback route
with their original local settings and do not inherit cloud authority or limits.
