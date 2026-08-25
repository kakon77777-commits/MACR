# Grok and Ollama Provider Integration Design

Status: approved in chat on 2026-08-25; D: storage review change applied; written specification awaiting final operator review

## Purpose

Extend MACR from its MiniMax-first v0.1 baseline to a migration-safe v0.2 runtime with three additional selectable provider profiles:

- `grok`: the default frontier cloud worker using `grok-4.6`;
- `grok_standard`: an explicitly selected ordinary/special-purpose cloud worker using `grok-4.3`;
- `ollama_qwythos`: a private local worker using the installed Qwythos-9B-v2 Q4_K_M model.

All provider output remains a candidate. Generation does not imply verification or acceptance.

## Approved operator decisions

- Grok 4.6 is the normal/default Grok model.
- Grok 4.3 is available only through an explicit provider selection.
- MACR must never silently downgrade or fall back from Grok 4.6 to Grok 4.3.
- Qwythos runs through the local Ollama service and is reserved for private local work.
- Persistent source, runtime state, and model data stay on D:. No new operational state is written to C:.
- Grok credentials remain external to the repository. The existing plaintext source is not a supported runtime dependency and its path must not appear in committed configuration.
- Claude API billing remains forbidden. The existing Claude subscription-client route stays disabled.

## Observed baseline

### Grok

On 2026-08-25, the operator-provided xAI key passed `GET https://api.x.ai/v1/models`. A minimal `grok-4.3` Responses API smoke test returned HTTP 200 and an exact fixed response. This was a transport test, not a model-default decision.

The current official xAI documentation identifies `grok-4.6` as the frontier model and supports it through `POST /v1/responses`. The documented standard price below the long-context threshold is USD 2.00 per million input tokens, USD 0.50 per million cached input tokens, and USD 6.00 per million output tokens:

- https://docs.x.ai/developers/grok-4-6
- https://docs.x.ai/developers/models/grok-4.6

The Responses API stores state by default. MACR must set `store: false` on every Grok request:

- https://docs.x.ai/developers/model-capabilities/text/generate-text

`store: false` disables response-state storage for continuation. It is not a claim that the xAI account has contractual Zero Data Retention.

### Ollama and Qwythos

The local service is Ollama 0.32.15 at `http://127.0.0.1:11434`. Its user-level `OLLAMA_MODELS` value is:

```text
D:\Ai\work together\LocalModels\models
```

The installed model is:

```text
hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M
```

Observed installation identity and behavior:

- manifest digest: `5008e78bba127262f3f7ad86425bb49a5e0f47bb1959a4d30bfe17832ec45856`;
- reported installed size: 6,657,768,737 bytes, including the vision projector;
- model family: `qwen35`, approximately 8.95B parameters;
- advertised Ollama capabilities: completion, thinking, tools, and vision;
- 8,192-token smoke-test context;
- observed processor allocation: 86% GPU and 14% CPU;
- observed cold request: 126.895 seconds wall time, including 67.55 seconds load time;
- observed generation rate: 34.36 tokens per second;
- exact fixed response succeeded and `keep_alive: 0` unloaded the model afterward.

Official Ollama documentation confirms the loopback API, local no-auth behavior, configurable model location, and `keep_alive` semantics:

- https://docs.ollama.com/api/introduction
- https://docs.ollama.com/api/chat
- https://docs.ollama.com/api/authentication
- https://docs.ollama.com/windows
- https://docs.ollama.com/faq

## Architecture

### Provider profiles

| Provider ID | Adapter kind | Model | Connection scope | Required CLI opt-in | Allowed privacy | Cost policy |
|---|---|---|---|---|---|---|
| `grok` | `grok_responses` | `grok-4.6` | external HTTPS | `--allow-network` | `public`, `internal_approved` | positive budget required; actual cost recorded |
| `grok_standard` | `grok_responses` | `grok-4.3` | external HTTPS | `--allow-network` | `public`, `internal_approved` | positive budget required; actual cost recorded |
| `ollama_qwythos` | `ollama_local_chat` | installed Qwythos model | loopback HTTP | `--allow-local` | `local_only` | budget must be zero |

`grok` is the default Grok profile by naming and documentation. MACR v0.2 does not add automatic provider routing; callers still select a provider ID explicitly.

### Configuration schema v2

`config/providers.json` advances from schema version 1 to 2. `ProviderConfig` gains explicit non-secret values and transport scope:

```text
connection_scope = external_https | loopback_http | disabled
base_url          = optional static non-secret URL
model             = optional static non-secret model ID
reasoning_effort  = optional low | medium | high | xhigh
```

Existing environment indirection remains supported:

```text
api_key_env
base_url_env
model_env
```

Resolution rules are fail-closed:

1. A provider may define either `base_url` or `base_url_env`, never both.
2. A provider may define either `model` or `model_env`, never both.
3. API-key providers must define `api_key_env` and must never define a literal key.
4. External HTTPS providers require an exact hostname allowlist.
5. Loopback HTTP providers require an exact loopback URL and cannot define an API key.
6. Enabled provider kinds must have a registered adapter.

MiniMax remains on its existing environment-selected model and base URL. Claude remains disabled. Grok model IDs are committed because model choice is policy, not a credential.

Schema version 1 provider documents are rejected with a migration error. The repository's canonical provider document and tests advance atomically to version 2; MACR does not guess defaults for an older external file.

### TaskContract output bound

`TaskConstraints` gains:

```text
max_output_tokens: integer, default 1024, allowed range 1..16384
```

This per-task value supplies Grok `max_output_tokens` and Ollama `options.num_predict`. Boolean values and numeric strings are rejected rather than coerced.

### Connection-scope gates

The current CLI treats all invocation as external networking. v0.2 separates authorization without weakening the existing cloud gate:

```text
external_https:
  CLI requires --allow-network
  TaskContract.constraints.internet must be true

loopback_http:
  CLI requires --allow-local
  TaskContract.constraints.internet must be false
  endpoint must be exactly 127.0.0.1 on the configured port
```

`--allow-network` cannot substitute for `--allow-local`, and `--allow-local` cannot authorize an external request. Supplying both is permitted, but only the selected provider's required gate is relevant.

The local gate is explicit because loading Qwythos consumes substantial GPU/RAM and can take more than a minute on a cold start.

### Offline doctor semantics

`macr doctor` remains strictly offline and continues to report `network_activity: false`. It validates schema, connection scope, allowlists, model selection, and the presence (not value) of required environment variables. It does not contact xAI or loopback Ollama and therefore reports providers as `configured_offline`, never `live`.

`doctor --strict` succeeds when every enabled provider is validly configured offline. Actual reachability, model entitlement, model presence, and inference behavior are established only by an explicitly authorized invocation. This prevents an innocent diagnostic command from loading Qwythos or making a billable Grok request.

## Grok Responses adapter

### Request

The adapter posts to `https://api.x.ai/v1/responses` with:

```json
{
  "model": "<profile model>",
  "input": [
    {"role": "system", "content": "<bounded MACR worker instruction>"},
    {"role": "user", "content": "<serialized TaskContract>"}
  ],
  "store": false,
  "reasoning": {"effort": "high"},
  "max_output_tokens": 1024
}
```

The `grok` profile explicitly sets `reasoning_effort = high`. The `grok_standard` profile omits the reasoning field because its purpose is a manually selected, lower-cost ordinary profile rather than an implicit substitute for frontier behavior.

No server-side tools, web search, X search, code execution, files, images, or previous response IDs are enabled in this release.

The adapter sends `Authorization: Bearer <XAI_API_KEY>` from process environment only. It rejects redirects and never reflects remote error bodies into normalized results.

### Response normalization

The adapter extracts only `output_text` content from message output items. It returns:

- candidate answer;
- exact model returned by xAI;
- response ID;
- token usage, including cached and reasoning token details when present;
- server-side tool count, which must be zero for this release;
- `cost_in_usd_ticks` and `currency_cost_usd = ticks / 10,000,000,000`;
- a warning that `store: false` is not proof of account-level Zero Data Retention.

The task's positive `max_cost_usd` authorizes dispatch but is not a provider-side hard cap. After completion, if actual cost exceeds the contract budget, the result becomes `candidate_failure` with a sanitized budget warning. The ledger records the overrun, although the charge cannot be undone. This limitation is explicit until a separately designed preflight price/token estimator exists.

No automatic call to `grok_standard` occurs after a frontier failure, timeout, rate limit, policy denial, or model error.

## Ollama local adapter

### Endpoint and policy

The only allowed base URL in this release is:

```text
http://127.0.0.1:11434
```

`localhost`, non-loopback addresses, alternate hosts, URL credentials, query strings, fragments, redirects, and Ollama Cloud URLs are rejected. The endpoint is `POST /api/chat`.

Before generation, the adapter performs a loopback-only model check through `/api/tags`. A missing service or missing exact model fails before the generation request.

### Request

The adapter sends:

```json
{
  "model": "hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M",
  "messages": [
    {"role": "system", "content": "<bounded MACR worker instruction>"},
    {"role": "user", "content": "<serialized TaskContract>"}
  ],
  "stream": false,
  "think": false,
  "keep_alive": "5m",
  "options": {
    "num_ctx": 8192,
    "num_predict": 1024,
    "temperature": 0.6,
    "top_p": 0.95,
    "top_k": 20
  }
}
```

`MACR_OLLAMA_KEEP_ALIVE` may override the committed `5m` default. Accepted values are exactly `0` or an integer duration from `1m` through `60m`; `0` requests immediate unload. Other units, negative values, indefinite residency, and durations above 60 minutes are rejected. The adapter does not start Ollama, pull models, sign into Ollama Cloud, or invoke tools.

### Response normalization

The adapter returns:

- candidate answer from `message.content`;
- model name and completion reason;
- prompt and generated token counts;
- load, prompt-evaluation, generation, and total durations;
- zero currency cost;
- a warning that low refusal does not imply correctness.

The adapter discards any thinking field and does not write prompt, answer, or thinking content to the ledger.

## Ledger and privacy

Existing append-only dispatch and completion events remain. Candidate completion adds bounded, non-content metrics:

```text
model
input_tokens
output_tokens
reasoning_tokens
cached_tokens
currency_cost_usd
duration_ms
```

Absent metrics remain null rather than invented. The ledger never stores:

- API keys or authorization headers;
- serialized TaskContracts or prompts;
- candidate answer text;
- Grok reasoning/encrypted content;
- Ollama thinking content;
- remote error bodies.

Runtime state uses `D:\AI_RESIDENCE\AI_Runtime\macr-state`. Model files remain under the already configured D: Ollama store.

### Storage placement and migration boundary

The current Residence authority documents that the former R: 500GB NVMe was cloned into the system role and became C: on 2026-08-16. Former Residence content was moved to `D:\AI_RESIDENCE` before that conversion, and old R: paths are historical evidence rather than valid current entry points.

Current MACR placement is:

```text
source:             D:\Ai\work together\MACR
runtime state:      D:\AI_RESIDENCE\AI_Runtime\macr-state
future Codex target: D:\AI_RESIDENCE\AI_Runtime\codex-home
Ollama models:      D:\Ai\work together\LocalModels\models
```

The runtime-state root already exists with empty `artifacts`, `cache`, `ledger`, and `test-tmp` directories. It is a shared MACR service location, not a private `00_RESIDENCE/agents/<resident>` namespace. MACR must not load or write any named resident's private residence unless a future task-local HOST-OBSERVED identity binding authorizes that resident.

`CODEX_HOME_TARGET` records only a future D: destination. It does not change the official active `CODEX_HOME`, move credentials, copy sessions, or alter the running Codex application. Current Codex native state remains in its native C: location under the Residence governance policy; any later migration requires a separate design, consistent snapshot, manifest, hashes, restart validation, and rollback copy.

The active workspace, Residence, runtime state, and local model store currently share physical D: storage. Their separation is logical, not a second-medium backup. Future internal AI-management changes may migrate these roots only through explicit manifests, hash verification, rollback copies, and operator approval.

The unchanged v0.1 suite passed 32/32 with an isolated D: test root, proving the code baseline after the storage decision. Current manifests, defaults, examples, and scripts must stop using operational R: paths during v0.2 implementation; historical evidence remains unchanged.

## Speaker identity boundary

Provider and model selection do not establish resident or speaker identity:

```text
MODEL != RESIDENT
provider profile != speaker label
runtime role != authorship identity
```

`grok`, `grok_standard`, and `ollama_qwythos` are service profiles only. They do not name the current Codex speaker, Grok, Qwythos, or a future resident. Until a task-local identity envelope binds the current HOST-OBSERVED native task/session identifier and declares its `identifier_kind`, the readable speaker identity remains `unresolved`.

Model-emitted self-labels are claims, not identity evidence. Future naming and private-residence access require an independently approved identity design and explicit rebinding; neither this provider integration nor familiar conversational continuity grants access to `00_RESIDENCE/agents/<resident>` private data.

## Error handling

Expected failures normalize to `candidate_failure` and append a terminal completion event:

- missing Grok key;
- wrong opt-in flag;
- privacy or internet mismatch;
- non-positive Grok budget or non-zero Ollama budget;
- unavailable or disallowed model;
- external host or loopback mismatch;
- timeout, HTTP error, redirect, malformed JSON, or oversized response;
- unexpected nonzero Ollama server-side tool request;
- actual Grok cost exceeding the authorized budget.

Unexpected exceptions remain sanitized exactly as in v0.1: exception type may be recorded, but exception text is omitted from user-visible results and the ledger.

## CLI examples

```powershell
# Default frontier Grok profile: always grok-4.6 in this version.
.\scripts\macr.ps1 invoke grok .\examples\grok-task.example.json --allow-network

# Manual ordinary/special-purpose profile: never selected implicitly.
.\scripts\macr.ps1 invoke grok_standard .\examples\grok-task.example.json --allow-network

# Private local worker.
.\scripts\macr.ps1 invoke ollama_qwythos .\examples\ollama-task.example.json --allow-local
```

No command silently selects another provider or model.

## Testing and acceptance

Implementation follows test-driven development. Every new behavior is first observed failing, then minimally implemented.

Offline tests cover:

- schema v2 static/environment resolution and invalid combinations;
- exact Grok 4.6 and Grok 4.3 profile selection;
- mandatory `store: false`;
- no automatic Grok fallback;
- cost tick conversion and post-dispatch budget overrun;
- output-text normalization and malformed response rejection;
- external HTTPS host and redirect rejection;
- independent `--allow-network` and `--allow-local` gates;
- exact loopback host enforcement;
- Ollama model-presence check;
- local-only, internet-disabled, zero-cost policy;
- Ollama request options, keep-alive override, metrics normalization, and thinking exclusion;
- ledger content exclusion and bounded metrics;
- MiniMax regression behavior and Claude API prohibition;
- secret-pattern and operational C-path scans.

After the offline suite passes, acceptance requires two explicit live conformance checks:

1. Grok 4.6 receives a public fixed-string prompt with `store: false`, `reasoning.effort: high`, no tools, `max_output_tokens: 64`, actual-cost capture, and exact-output comparison.
2. Qwythos receives a local-only fixed-string prompt through MACR with `max_output_tokens: 64`, reports local metrics, and is then unloaded with `keep_alive: 0` for the acceptance run.

Live checks are not part of the default offline test suite. Grok key material is loaded only into the test process and is never printed, persisted, committed, or copied into the runtime ledger.

## Versioning and delivery

- Package version advances to `0.2.0`.
- Provider configuration advances to schema version 2.
- The design receives its own local commit before implementation planning.
- Implementation receives separate reviewable commits.
- No remote, push, pull request, or deployment is authorized by this specification.

## Non-goals

- automatic model/provider routing;
- automatic frontier-to-standard fallback;
- multi-provider fan-out in one invocation;
- server-side Grok tools or web/X search;
- Ollama tool calling, vision, embeddings, or model pulling from MACR;
- hard pre-dispatch USD enforcement based on live pricing;
- verifier or acceptance automation;
- Claude API integration;
- Codex user-level provider configuration changes;
- moving or deleting the operator's existing plaintext Grok credential source.
