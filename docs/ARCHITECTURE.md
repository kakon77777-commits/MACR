# MACR v0.3 architecture

```text
Codex or another primary host
        |
        v
TaskContract + explicit connection opt-in
        |
        v
ProviderRegistry -- auth / privacy / budget / capability gate
        |
        +--> MiniMax OpenAI-compatible chat adapter
        +--> Grok Responses adapter: grok-4.6 frontier
        +--> Grok Responses adapter: grok-4.3 manual standard
        +--> Ollama local chat adapter: Qwythos-9B-v2
        +--> Google Gen AI adapter: gemini-3.7-flash text/multimodal
        +--> Google Gen AI adapter: gemini-3.1-flash-image one-image output
        +--> Google Veo/TTS/Lyria discovery profiles: disabled
        +--> Claude subscription route: disabled
        |
        v
ProviderResult(status=candidate_*)
        |
        v
Append-only content-free ledger on D:
        |
        v
Verifier / operator acceptance (not implemented)
```

## Connection scopes

`external_https` requires both `--allow-network` and `TaskContract.constraints.internet=true`. Hostname allowlisting, HTTPS, credential presence, privacy, positive budget, latency, capability, request size, redirect, response size, and response shape all fail closed.

`loopback_http` requires both `--allow-local` and `internet=false`. The v0.2 Ollama adapter accepts exactly `http://127.0.0.1:11434`, `local_only`, zero cost, and an installed exact model. It does not treat loopback authorization as external-network authorization.

The CLI resolves provider scope without creating state or reading a task file. State creation and task parsing happen only after the matching opt-in passes.

## Offline doctor

`doctor` always reports `network_activity: false`. It validates schema, scope, allowlists, model selection, named environment presence, and bounded Google service-account file shape without minting OAuth tokens or contacting xAI, MiniMax, Google, or Ollama. A healthy provider is `configured_offline`, not live. Actual reachability is established only by an explicitly authorized invocation.

## Grok boundary

- `grok` is fixed to `grok-4.6` with `reasoning.effort=high`.
- `grok_standard` is fixed to `grok-4.3` and must be named explicitly.
- Every request sets `store=false`, uses a per-task output bound, and enables no tools.
- Returned model identity must exactly match the requested profile.
- xAI `cost_in_usd_ticks` is normalized to USD. Cost above `max_cost_usd` is retained as a failed candidate because the completed charge cannot be undone.
- A failure never triggers another Grok profile or provider.

## Ollama boundary

The adapter performs an exact `/api/tags` model check before `/api/chat`. It sends `stream=false`, `think=false`, an 8,192-token context, bounded generation, and a validated `keep_alive` from `0` or `1m..60m`. Thinking and tool calls are not accepted into the result.

## Google boundary

- `google_gemini` is fixed to `gemini-3.7-flash`, medium thinking, text output, and bounded local image/video/audio/PDF input.
- `google_image` is fixed to `gemini-3.1-flash-image`, at most one validated reference, exactly one 1K output, and JPEG/PNG artifact validation.
- All inputs are workspace-relative D: files with declared SHA-256, closed MIME allowlists, a 20 MiB per-file limit, and a 32 MiB aggregate limit.
- Google credentials and project selection come only from named environment variables. Runtime uses an explicit service-account credential and never falls back to native ADC state.
- SDK retry attempts are exactly one. Search/Maps grounding, tools, code execution, external URLs, `gs://`, automatic uploads, and provider fallback are disabled.
- Images are atomically persisted without recompression at `D:\AI_RESIDENCE\AI_Runtime\macr-state\artifacts\google\<task_id>\`.
- `google_veo_fast`, `google_tts`, and `google_lyria` are disabled discovery profiles with no callable adapters.
- Cost metadata is dated and estimated when Google does not return invoice-grade currency values; Cloud Billing remains authoritative.

## Ledger boundary

Dispatch and completion events contain task/provider/event identity plus an allowlist of:

```text
model
input_tokens
output_tokens
reasoning_tokens
cached_tokens
currency_cost_usd
duration_ms
input_media_count
input_media_bytes
output_artifact_count
output_artifact_bytes
cost_kind
pricing_basis_version
```

Missing metrics remain null. Task inputs, prompts, answers, warnings, thinking, credentials, local source paths, artifact paths/content, and error bodies are excluded.

## Speaker identity boundary

```text
MODEL != RESIDENT
provider profile != speaker label
runtime role != authorship identity
```

`grok`, `grok_standard`, `ollama_qwythos`, `google_gemini`, and `google_image` are service profiles only. A Google service-account identity and model-emitted self-label are claims or service provenance, not speaker identity evidence. Until a task-local identity envelope binds the current HOST-OBSERVED native task/session identifier and declares `identifier_kind`, the readable speaker identity is `unresolved`. This runtime does not authorize access to any named resident's private data.

## Commit boundary

```text
generation != verification != acceptance
```

Every provider completion is a candidate. MACR v0.3 records evidence but does not add verifier decisions or accepted-result transitions.
