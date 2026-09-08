# MACR Runtime v0.7.0a0 — Phase-C Semantic Working State Alpha

MACR is a migration-aware runtime for heterogeneous AI workers. The v0.7.0a0 Phase-C Alpha preserves the v0.6 Direct and delegated planes, adds the Agent contract/state kernels, and introduces a governed semantic working state: immutable graph revisions, per-Agent pinned bindings, authority-free proposals, atomic host-authorized commits, reconstructible receipts, and deterministic Goal-to-Plan context projection. Provider completion, private capture, semantic commit, projection, verification, acceptance, merge, release, and live-route activation remain separate states.

This alpha line is the completed offline A-C foundation, not the full bounded single-Agent MVP. Phase D verified observation, governed action, temporal continuation, the closed Agent loop, and live provider use remain absent. Direct Chat remains a separate public contract from delegated `TaskContract` work: it sends provider-native message history without a MACR worker instruction or hidden prompt, pins one provider/model and model-token policy per conversation, projects only complete non-streaming responses, and persists exact plaintext history under D:. A provider-neutral Codex/Claude host-adapter core now exists offline, but live host-owned bindings and a live T1 provider route are not activated by this release.

`0.7.0a1` remains reserved for the later A-H bounded single-Agent MVP. Claude Code can use the existing MACR CLI today under honest `cli` attribution; the trusted host-observed adapter embedding remains deferred/NotMeasured. Neither route authorizes Anthropic API use.

## Canonical D: placement

```text
MACR_ROOT         = D:\Ai\work together\MACR
MACR_STATE_ROOT   = D:\AI_RESIDENCE\AI_Runtime\macr-state
CODEX_HOME_TARGET = D:\AI_RESIDENCE\AI_Runtime\codex-home
OLLAMA_MODELS     = D:\Ai\work together\LocalModels\models
```

`CODEX_HOME_TARGET` is inactive metadata for a separately governed future migration. This runtime does not move the active Codex installation, login, sessions, or credentials.

## Direct Chat quick start

Install or refresh the Windows Desktop shortcut:

```powershell
Set-Location 'D:\Ai\work together\MACR'
.\scripts\install-direct-chat-shortcut.ps1
```

Then open **MACR Direct Chat (Alpha)** from the Desktop. The shortcut contains no provider key or bootstrap token. It launches a hidden D-drive PowerShell entry point, uses the repository's bounded loader to read `D:\KEY\GROK.txt` only into the child process, starts one `127.0.0.1` server on an OS-assigned port, and opens the default browser. The loader accepts only a bounded `xai-...` API secret and prints no diagnostics. A missing, malformed, or key-ID-shaped Grok value leaves the Grok card unavailable without preventing local Qwythos use. A second launch opens the existing instance instead of starting another server.

Local startup smoke without model generation:

```powershell
.\scripts\macr.ps1 direct-chat --smoke
```

The UI exposes only `grok` (`grok-4.6`) and `ollama_qwythos`. A blank system-prompt field produces no system message; nonblank content stays visible and is sent exactly once. Responses appear only after the provider completes. Conversation history, search, archive/restore, settings snapshots, cost metadata, and candidate captures remain on D:. Permanent privacy deletion requires exact `DELETE`, refuses active runs, removes Direct plaintext and Candidate files, enables SQLite `secure_delete`, and truncates the Direct WAL while retaining content-free accounting/audit metadata. See `docs/DIRECT_CHAT.md` for limits and the manual two-provider acceptance run.

## Provider profiles

| Provider ID | Model/route | Scope | Selection rule |
|---|---|---|---|
| `minimax` | `MiniMax-M2.7` or `MiniMax-M2.7-highspeed` | external HTTPS | explicit exact model |
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

## Model-local token policies

Token limits are no longer one global setting. Built-ins and append-only operator overrides are keyed by exact provider/model and stored at `settings\model-token-policies.sqlite3`. A new Direct conversation pins the exact canonical policy JSON and digest; changing an active override affects only later conversations. Delegated dispatch records the same digest and refuses an under-floor or over-limit task before authority admission or transport; GLM approval schema 3 binds it together with task ID, exact latency and provider-tier binding.

| Exact provider/model | Warning context | Hard context | Minimum task output | Default output | MACR max output |
|---|---:|---:|---:|---:|---:|
| `grok/grok-4.6` | 180,000 | 400,000 | 32,768 | 32,768 | 65,536 |
| `grok_standard/grok-4.3` | 180,000 | 400,000 | 32,768 | 32,768 | 65,536 |
| `glm_flash_worker/glm-5.3-flash` | 400,000 | 512,000 | 16,384 | 16,384 | 65,536 |
| `google_gemini/gemini-3.7-flash` | 400,000 | 512,000 | 16,384 | 16,384 | 65,536 |
| `minimax/MiniMax-M2.7` | 160,000 | 180,000 | 2,048 | 2,048 | 2,048 |
| `minimax/MiniMax-M2.7-highspeed` | 160,000 | 180,000 | 2,048 | 2,048 | 2,048 |
| `ollama_qwythos/Qwythos-9B-v2` | 7,000 | 8,192 | 1 | 4,096 | 4,096 |

`TaskConstraints.max_output_tokens` now defaults to 16,384. For external text
models, the exact model-local default is also a hard quality floor: Grok uses
32,768; ordinary GLM and Gemini use 16,384. MiniMax remains an explicit
2,048-token capability exception because that is its configured provider
ceiling. Loopback Qwythos does not inherit the cloud floor. An external
operator override cannot lower its default below 16,384 unless the provider's
own output ceiling is lower.

The quality floor is an explicit field in model-token policy contract v2 and
therefore changes the policy digest. Grok, Gemini, MiniMax and GLM adapters
repeat the check before credential access; runtime admission is not the sole
enforcement point. Existing GLM approvals bind policy-v1 digests and must be
regenerated. A legacy Grok Direct conversation without a current v2 policy
snapshot fails before message append, authority admission or network; create a
new conversation rather than silently rebinding its history. A legacy local
Qwythos v1 snapshot is verified under its original digest and retains the same
local limits in memory; it does not acquire the cloud floor.

The T1 GLM preset is separate: exact `glm-5.3-flash`, 128,000 context and
16,384 output. T1 manifest schema 4 no longer fixes the batch at three members
or three workers. `worker_count` is explicit and digest-bound, may range from
one through the exact member count, and must match the authorized dispatcher
set. Each member carries its own positive exact cost ceiling; the aggregate
must equal the sum of all member ceilings, while the operator-selected campaign
ceiling must cover that aggregate. Older schema-1/2/3 manifests remain
audit-visible and are never silently upgraded. Current member and manifest
authority digests use v4 domains.

## Shared-core execution boundary

Every delegated CLI or T1 invocation uses this order:

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

Origin identity, authorization provenance, and lease ownership are three independent claims. Timing, a task name, or possession of a lease cannot substitute for current authority. The ordinary CLI creates a ten-minute one-shot authority only after the matching `--allow-network` or `--allow-local` opt-in and task preflight; the host-adapter core cannot issue authority and consumes a pre-issued operator authority/connectivity grant. GLM's exact-envelope host approval remains an additional provider-specific gate.

Operational events now live in `runtime\dispatch.sqlite3`. The former `ledger\events.jsonl` is immutable source evidence and receives no new runtime writes.

## Offline verification

```powershell
cd 'D:\Ai\work together\MACR'
.\scripts\verify.ps1
.\scripts\verify-v06.ps1
```

Both suites are offline. `verify.ps1` runs the complete repository baseline. `verify-v06.ps1` holds the named `MACR_V06_QUIET_CENSUS` mutex, requires five zero-invoker samples before and after the suite, and adds exact schema fingerprints, the 1/2/3/4/8 queue matrix, a five-process dynamic T1 complete-path mock, synchronized 32-process bootstrap, planner replay, identity, qualification, target-collision, accounting-privacy, cross-file and differential gates. It emits one deterministic `V06_SUMMARY` line and contacts no real provider or local model.

Phase B/C package replay pins `SOURCE_DATE_EPOCH` to the exact candidate commit
timestamp. Repeated clean gates therefore require the generated wheel hash—not
only the semantic replay digests—to remain byte-identical.

Current schema versions are `runtime operational SQLite 7`, `observatory SQLite 2`, `accounting SQLite 3`, Direct conversation schema 2, model-token-policy store schema 1 / policy contract v2, provider-capability-policy schema 2, and T1 manifest schema 4.

For the dedicated multiprocess replay from a source checkout:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -m unittest tests.test_multiprocess_runtime -v
```

The synchronized fresh-database test starts 32 processes behind one barrier. WAL bootstrap retries only transient SQLite `BUSY/LOCKED` conditions within a bounded deadline; provider calls are never retried by this mechanism.

## Legacy-ledger migration gate

If the preserved JSONL ledger is nonempty, inspect it before any current invocation:

```powershell
.\scripts\macr.ps1 migrate-ledger --dry-run
.\scripts\macr.ps1 migrate-ledger
```

Use `--expected-count N` when an external exact count is available. Import is copy-only and idempotent. Invalid UTF-8, malformed JSON, duplicate keys, forbidden content fields, duplicate original IDs, or an expected-count mismatch make migration incomplete. Corrupt bytes are retained under `quarantine`; provider invocation remains blocked until the current source hash has a complete import record.

If an append-only source grows after an earlier import, unchanged logical events are matched by original event ID, type, timestamp, and canonical payload. Only the new tail is inserted; conflicting reuse of an existing ID fails closed.

A live route also requires every legacy invoker to be retired and the preserved JSONL source to be sealed with the Windows read-only attribute before the authoritative hash/count snapshot and migration. See `docs/STORAGE_AND_MIGRATION.md`. The SQLite current-hash gate detects later drift, but it does not grant authority to unseal or rerun an old writer.

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

`ZAI_API_KEY` is intentionally not a supported MACR setting. The committed GLM
profile and bounded provider loader use only the ordinary, non-reparse-point
file `D:\KEY\GLM.txt`; `invoke-glm.ps1` clears any process-level variable of
that name before entering MACR. Claude Code and Codex therefore do not need the
credential value in their shell, prompt, `.env`, or task file. See
[`docs/GLM_CLAUDE_CODE_QUICKSTART.md`](docs/GLM_CLAUDE_CODE_QUICKSTART.md) for
the content-free readiness check, exact approval sequence, and failure map.

`glm_flash_worker` requires `delegable=true`, `delegation_class=non_sensitive_routine`, an exact `delegation_approval_sha256`, and a separate unexpired host-approval record under D: runtime state. New typed approval records bind approval-contract schema 3 and the exact provider-tier binding; pre-existing records remain immutable `legacy_pre_tier` evidence and cannot satisfy new dispatch. The approval is authenticated with HMAC-SHA256 using the separately controlled fixed GLM credential; editing the JSON or extending its expiry invalidates the MAC. A task cannot authorize itself merely by carrying its own checksum. The approval manifest covers task ID, exact latency, complete credential-free request payload, fixed provider/endpoint/model, provider-tier binding, task type, privacy, maximum output, pricing basis, and USD ceiling. Changing any covered byte invalidates approval before network use. Public or explicitly approved internal privacy, an empty `write_scope`, independent verification, no patch authority, and a positive conservative-list-price budget are also mandatory. It accepts only bounded text inputs with non-path labels, rejects obvious local-path/credential markers, and omits local task/workspace identity and currency budget from the outbound request. HTTPS schemes are not drive paths; observed `X:\\<LaTeX-command>` ambiguities are exempted only through a closed command set and cease to be exempt when path-like continuation follows. Semantic classification still belongs to the trusted operator.

The immutable built-in `standard` GLM tier permits the two existing routine task
types and a maximum 300-second transport timeout. The optional
`extended_text_candidate` tier permits non-sensitive routine, analysis, review
and code-text candidates up to 900 seconds. It still grants no patch, write
scope or tools. Activation consumes a separately pre-issued authority bound to
the exact provider/model/tier/revision/policy/limit digest; no task field or CLI
flag can activate it.

Here `task_type` is an authority-bearing MACR execution class, not a project's
business-stage label. A non-sensitive Discovery, Classification, Identity,
Extraction, Verification or Review job may accurately use
`delegated_routine`; its business role belongs in the task ID and task/return
contract. Work that actually requires analysis, review or code authority must
use the matching type under an explicitly activated extended tier and must not
be relabelled as routine. When a type is rejected, `glm-preflight` returns a
content-free structured diagnostic containing the requested safe identifier,
active tier/revision/digest and exact allowed types.

GLM 5.3 Flash keeps max reasoning. A delegated request below the model-local
16,384-token floor is rejected before credential access or transport, rather
than silently enlarged. Reaching the floor reduces the observed exhaustion
risk but does not guarantee visible content: a `length` response whose output
is entirely reasoning becomes the distinct
`ProviderReasoningBudgetExhaustedError`, preserves safe usage/cost evidence,
records typed `failure_code` / `provider_response_validation` in terminal and
accounting state, performs no automatic retry, and requires a newly approved
larger envelope for any later attempt.

Read the current tier, legacy approval/queue counts and accounting state without
creating or migrating state:

```powershell
.\scripts\macr.ps1 capability-status --provider glm_flash_worker
.\scripts\macr.ps1 accounting-status
```

`capability-status` also reports content-free current, legacy, invalid and
active counts for model-token overrides. An old override remains immutable
`legacy_pre_quality_floor` evidence, but cannot be activated or used until it
is reissued against the policy-v2 base. Only the exact reconstructed v1 base
digest receives that label; arbitrary mismatches are counted as invalid.

## T1 staging and worker commands

`queue-status` globally enumerates bounded content-free queue rows, including `reconciliation_required`, without task bodies, answers, credentials, or paths. `t1-stage` loads one strict private schema-4 manifest, verifies every member's existing GLM host approval and the exact T1 token policy, checks that its digest-bound `worker_count` matches the dispatcher set, signs batch plus dispatch authority, and enqueues without a provider call. Member count, worker count, per-member ceilings and the campaign ceiling are operator-selected manifest data rather than fixed constants. `t1-worker` claims at most one exact member per invocation and performs no retry or fallback; an authorized dispatcher may be invoked again to drain a later queued member.

```powershell
.\scripts\macr.ps1 queue-status --state reconciliation_required
.\scripts\macr.ps1 t1-stage .\private\t1-manifest.json `
  --dispatcher-id worker-1 --dispatcher-id worker-2 `
  --dispatcher-id worker-3 --dispatcher-id worker-4 `
  --expires-in-minutes 30
.\scripts\macr.ps1 t1-worker .\private\t1-manifest.json `
  --dispatcher-id worker-1 --allow-network
```

These commands are implemented but the current route is offline-only. The repository includes only fake-transport complete-path evidence. No exact live manifest has been authorized and no live provider call was made for v0.7.0a0.

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

- Direct Chat is an alpha candidate. Offline and local service gates pass, but one real multi-turn Grok conversation and one real multi-turn Qwythos conversation remain operator acceptance gates.
- Transport-level cancellation and explicit late-result recovery are not exposed in Direct UI 0.1. There is no fake cancel control; these are required before a beta label.
- The host-adapter core is implemented and synthetically verified, but no live host-owned Codex/Claude binding, autonomous router, autonomous acceptance, or activated live tier follows. The explicit T1 worker remains operator-controlled and offline-only.
- Direct `operator_managed` calls are warn-only and require accounting. Privacy, credential, legacy-migration, current authority, route, and lease failures remain hard pre-network gates.
- No provider-side hard USD cap; actual Grok cost is checked after completion and an overrun becomes `candidate_failure`.
- No Grok search, code execution, files, images, or server-side tools.
- No Ollama tools, vision, embeddings, model pulling, or service startup.
- No implicit GLM substitution or quota router. GLM must be named explicitly and every task must be marked `delegable=true`; semantic sensitivity classification remains the operator's responsibility.
- Google accepts only bounded workspace-relative local media; URLs, `gs://`, automatic uploads, multi-image output, Veo, TTS, and Lyria invocation are unavailable.
- SQLite event and accounting writes are cross-process transactional. The legacy JSONL writer remains intentionally unsafe historical code used only by migration and mutation tests; it is not an operational writer.
- `PLAIN_SOURCE` rejects fences and common prose wrappers but is not a language parser; compilation remains independent verification. `JSON_OBJECT` is semantic-object validation, so whitespace and key order are not byte contracts. Use `EXACT_TEXT` for byte-exact JSON.
