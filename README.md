# MACR Runtime v0.5.0a2 — Shared Core Checkpoint A Repair

MACR is a migration-aware runtime for heterogeneous AI workers. Checkpoint A adds a host-neutral, cross-process-safe shared core around the existing provider adapters. Provider generation, return-contract validity, materialization, verification, and acceptance remain separate states; a provider completion never becomes accepted work automatically.

This alpha repair supersedes the unaccepted v0.5.0a1 candidate after independent replay found a fresh-SQLite bootstrap race, incomplete event-payload privacy enforcement, a plain-source wrapper gap, and a non-self-contained replay command. It does **not** implement Direct Chat, a browser UI, Codex/Claude Code host adapters, bounded fan-out, or Context Capsules.

## Canonical D: placement

```text
MACR_ROOT         = D:\Ai\work together\MACR
MACR_STATE_ROOT   = D:\AI_RESIDENCE\AI_Runtime\macr-state
CODEX_HOME_TARGET = D:\AI_RESIDENCE\AI_Runtime\codex-home
OLLAMA_MODELS     = D:\Ai\work together\LocalModels\models
```

`CODEX_HOME_TARGET` is inactive metadata for a separately governed future migration. This runtime does not move the active Codex installation, login, sessions, or credentials.

## Provider profiles

| Provider ID | Model/route | Scope | Selection rule |
|---|---|---|---|
| `minimax` | configured MiniMax OpenAI-compatible chat model | external HTTPS | explicit |
| `grok` | `grok-4.6`, reasoning high | external HTTPS | default Grok/frontier profile |
| `grok_standard` | `grok-4.3` | external HTTPS | explicit manual selection only |
| `ollama_qwythos` | Qwythos-9B-v2 Q4_K_M | loopback HTTP | explicit private local selection |
| `google_gemini` | `gemini-3.7-flash` | external HTTPS | explicit text/multimodal candidate |
| `google_image` | `gemini-3.1-flash-image`, one 1K output | external HTTPS | explicit image candidate |
| `glm_flash_worker` | `glm-5.3-flash`, reasoning max | external HTTPS | explicit non-sensitive delegated text candidate only |
| `google_veo_fast` | `veo-3.1-fast-generate-001` | disabled | implementation and live verification deferred |
| `google_tts` | `gemini-3.1-flash-tts-preview` | disabled | implementation and live verification deferred |
| `google_lyria` | `lyria-3-clip-preview` | disabled | implementation and live verification deferred |
| `claude_subscription` | no adapter selected | disabled | Anthropic API use forbidden |

There is no automatic provider routing or fallback. A failed provider never invokes GLM or another model, Google media profile, Grok profile, or Ollama.

## Shared-core execution boundary

Every v0.5 CLI invocation uses this order:

```text
deterministic task preflight
  -> current-epoch dispatch authority
  -> fenced cross-process lease
  -> transactional SQLite dispatch event
  -> one provider attempt and typed observation
  -> private immutable candidate capture
  -> provider accounting observation
  -> return-contract validation
  -> one terminal event and accounting outbox record
```

Origin identity, authorization provenance, and lease ownership are three independent claims. Timing, a task name, or possession of a lease cannot substitute for current authority. The CLI creates a ten-minute one-shot authority only after the matching `--allow-network` or `--allow-local` opt-in and task preflight; GLM's exact-envelope host approval remains an additional provider-specific gate.

Operational events now live in `runtime\dispatch.sqlite3`. The former `ledger\events.jsonl` is immutable source evidence and receives no new runtime writes.

## Offline verification

```powershell
cd 'D:\Ai\work together\MACR'
.\scripts\verify.ps1
```

The default suite is offline. It compiles source/tests, attacks SQLite with 1/2/3/4/8 concurrent writers, verifies lease contention and process-census controls, scans credential-shaped material and operational C/R paths, validates configuration, and runs `doctor` without contacting a provider or loading a model.

For the dedicated multiprocess replay from a source checkout:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -m unittest tests.test_multiprocess_runtime -v
```

The synchronized fresh-database test starts 32 processes behind one barrier. WAL bootstrap retries only transient SQLite `BUSY/LOCKED` conditions within a bounded deadline; provider calls are never retried by this mechanism.

## Legacy-ledger migration gate

If the preserved JSONL ledger is nonempty, inspect it before the first v0.5 invocation:

```powershell
.\scripts\macr.ps1 migrate-ledger --dry-run
.\scripts\macr.ps1 migrate-ledger
```

Use `--expected-count N` when an external exact count is available. Import is copy-only and idempotent. Invalid UTF-8, malformed JSON, duplicate keys, forbidden content fields, duplicate original IDs, or an expected-count mismatch make migration incomplete. Corrupt bytes are retained under `quarantine`; provider invocation remains blocked until the current source hash has a complete import record.

## Invocation

Grok 4.6 frontier profile:

```powershell
$env:XAI_API_KEY = '<set outside the repository>'
.\scripts\macr.ps1 invoke grok .\examples\grok-task.example.json --allow-network
```

Manual Grok 4.3 profile:

```powershell
.\scripts\macr.ps1 invoke grok_standard .\examples\grok-task.example.json --allow-network
```

Private local Qwythos profile:

```powershell
$env:MACR_OLLAMA_KEEP_ALIVE = '5m'
.\scripts\macr.ps1 invoke ollama_qwythos .\examples\ollama-task.example.json --allow-local
```

Google Gemini 3.7 Flash:

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = 'D:\KEY\GOOGLE_VERTEX.json'
$env:GOOGLE_CLOUD_PROJECT = '<set outside the repository>'
.\scripts\macr.ps1 invoke google_gemini .\examples\google-gemini-task.example.json --allow-network
```

Google Gemini 3.1 Flash Image:

```powershell
.\scripts\macr.ps1 invoke google_image .\examples\google-image-task.example.json --allow-network
```

Restricted GLM Flash worker, loading its key from D: for this process only:

```powershell
# Review the exact task, then obtain the digest that binds its outbound bytes,
# fixed route/model, privacy class, output limit, and USD ceiling.
.\scripts\macr.ps1 glm-preflight .\examples\glm-worker-task.example.json --show-required-digest

# A trusted operator/host places that digest in delegation_approval_sha256.
.\scripts\macr.ps1 glm-approve .\examples\glm-worker-task.example.json --expires-in-days 30
.\scripts\invoke-glm.ps1 -TaskPath .\examples\glm-worker-task.example.json
```

`glm_flash_worker` requires `delegable=true`, `delegation_class=non_sensitive_routine`, an exact `delegation_approval_sha256`, and a separate unexpired host-approval record under D: runtime state. That record binds the digest to `host_operator`, a UUID nonce, creation time, and expiration time, and is authenticated with HMAC-SHA256 using the separately controlled fixed GLM credential; editing the JSON or extending its expiry invalidates the MAC. A task cannot authorize itself merely by carrying its own checksum. The approval manifest covers the complete credential-free request payload, fixed provider/endpoint/model, task type, privacy, maximum output, pricing basis, and USD ceiling. Changing any covered byte invalidates approval before network use. Public or explicitly approved internal privacy, an empty `write_scope`, independent verification, no patch authority, and a positive conservative-list-price budget are also mandatory. It accepts only bounded text inputs with non-path labels, rejects obvious local-path/credential markers, and omits local task/workspace identity and currency budget from the outbound request. Semantic classification still belongs to the trusted operator.

Generated images are preserved at:

```text
D:\AI_RESIDENCE\AI_Runtime\macr-state\artifacts\google\<task_id>\
```

Only validated JPEG/PNG bytes become artifacts. Paths, prompts, answers, source filenames, credentials, and image bytes are excluded from operational event and accounting databases.

`--allow-network` cannot authorize loopback work, and `--allow-local` cannot authorize an external request. Missing opt-in is rejected before task-file access or runtime-state creation. An incomplete legacy migration is rejected before task-file access, authority creation, lease acquisition, dispatch, or network use.

## Privacy and identity

- Grok requests send `store: false`, no tools, and no previous response ID. This is not proof of account-level Zero Data Retention.
- Ollama is restricted to `http://127.0.0.1:11434`; Ollama Cloud URLs and API keys are rejected.
- Google credentials are loaded from a named D: file through `GOOGLE_APPLICATION_CREDENTIALS`; the project is read from `GOOGLE_CLOUD_PROJECT`. Google SDK retries are fixed to one total attempt, and tools/grounding are disabled.
- GLM is fixed to the direct Z.ai API and exact `glm-5.3-flash`. The wrapper performs content-free structural preflight and never reads or exports the key. Health checks path metadata only. During approval creation or invocation, the provider resolves fixed `D:\KEY\GLM.txt`; invocation verifies the approval HMAC before contacting Z.ai. Rotating that credential intentionally invalidates every existing approval MAC, so each still-needed digest must be explicitly reapproved with `glm-approve --replace-existing`. No key-root override, tools, retries, fallback, filesystem authority, patch authority, verification authority, or acceptance authority are granted.
- SQLite events and accounting record bounded origin, authority, model, usage, cost, duration, finish, media-count, capture-hash, and contract-state metadata. They never store task prompts, candidate bytes, thinking, authorization headers, source paths, artifact content, or remote error bodies.
- GLM captures safe model, finish reason, token usage, estimated cost, duration, and exact answer bytes before protocol validation. A non-`stop` or malformed response remains a failed candidate without losing those safe observations and is never retried automatically.
- Candidate answer bytes are create-once files beneath `candidates`; public event rows contain only byte count and SHA-256 metadata. Verbatim materialization and transformed materialization have distinct provenance.
- Operational dispatch and terminal events enforce required fields, reviewed value types, and exact candidate-capture shape in addition to top-level field names. All event APIs recursively reject snake/kebab/camel/acronym path/body/content keys plus drive-absolute, drive-relative, backslash-UNC, and forward-UNC values; HTTPS URLs and provider model IDs remain valid metadata.
- Google currency values are estimates derived from a dated pricing basis. Cloud Billing is authoritative. Promotional credits do not guarantee free model use and are not embedded into provider policy.
- `MODEL != RESIDENT`. Provider profile names are service identifiers, not speaker names or resident identities. Without a task-local HOST-OBSERVED binding, speaker identity remains `unresolved`.

## Current limits

- No Direct Chat runtime/UI, host adapter, automatic router, fan-out scheduler, Context Capsule, verifier decision, or acceptance transition.
- Checkpoint A keeps the accounting `soft_warning` state distinct from existing task/provider hard budget gates. Provider adapters retain v0.4 task-budget behavior; the operator-managed warn-only profile is reserved for the Direct/settings checkpoint.
- No provider-side hard USD cap; actual Grok cost is checked after completion and an overrun becomes `candidate_failure`.
- No Grok search, code execution, files, images, or server-side tools.
- No Ollama tools, vision, embeddings, model pulling, or service startup.
- No implicit GLM substitution or quota router. GLM must be named explicitly and every task must be marked `delegable=true`; semantic sensitivity classification remains the operator's responsibility.
- Google accepts only bounded workspace-relative local media; URLs, `gs://`, automatic uploads, multi-image output, Veo, TTS, and Lyria invocation are unavailable.
- SQLite event and accounting writes are cross-process transactional. The legacy JSONL writer remains intentionally unsafe historical code used only by migration and mutation tests; it is not an operational writer.
- `PLAIN_SOURCE` rejects fences and common prose wrappers but is not a language parser; compilation remains independent verification. `JSON_OBJECT` is semantic-object validation, so whitespace and key order are not byte contracts. Use `EXACT_TEXT` for byte-exact JSON.
