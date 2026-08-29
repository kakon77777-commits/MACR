# MACR v0.6.0a1 T1 Operability + Shared Core + Direct Chat architecture

```text
Loopback browser (127.0.0.1, authenticated cookie)
        |
        v
Direct Web API + Direct Conversation Store
        |
        v
DirectRuntime -- current authority -- fenced provider lease
        |                                   |
        +--> GrokDirectAdapter              +--> SQLite events/accounting
        +--> QwythosDirectAdapter           +--> private Candidate Vault
        |
        v
complete non-streaming response -> atomic assistant message -> safe text projection

Delegated host / CLI
        |
        v
TaskContract -> MacrRuntime -> candidate-only worker path
```

The Direct and delegation planes share configuration, credential custody, transport, observation, authority, lease, candidate, event, and accounting primitives. They do not share their public request contract. `DirectRuntime` never creates a `TaskContract`, never calls `MacrRuntime.invoke()`, and never imports the worker-instruction compiler. Direct history therefore contains only the operator-visible system prompt, user messages, and prior assistant messages.

```text
Codex or another primary host
        |
        v
TaskContract + explicit connection opt-in
        |
        v
structured contradiction preflight
        |
        v
current-epoch authority --> fenced cross-process lease
        |
        v
transactional SQLite dispatch event + accounting dispatch
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
        +--> Z.ai adapter: glm-5.3-flash restricted delegated text worker
        +--> Google Veo/TTS/Lyria discovery profiles: disabled
        +--> Claude subscription route: disabled
        |
        v
RawProviderObservation + ProviderResult(status=candidate_*)
        |
        v
private Candidate Vault + accounting observation
        |
        v
structured return-contract validation
        |
        v
one SQLite terminal event + accounting outbox
        |
        v
materialization / verification / acceptance (orthogonal; acceptance host-only)
```

The a3 Checkpoint A shared core remains an immutable ancestor and a4 supplies Direct runtime/UI. v0.6 adds Context Capsules, model/route identities, append-only Observatory evidence, deterministic planning, exact T0 execution, durable T1 queue/batch authority, constrained T2 proposals, T3 target ownership/cross-file verification, and blinded differential manifests. v0.6.0a1 adds the production T1 consumer and model-local token policy plane without activating a live route. Codex or Claude Code host adapters, transport-level Direct cancellation, late-result recovery, autonomous acceptance, and an activated live route remain absent.

## Dynamic coordination boundary

```text
untrusted external observation -> immutable snapshot/evidence
                              -> rebuildable Model Passport
                              -> route-role qualification
                              -> deterministic shadow plan
                              -> exact host authority
                              -> fenced T0/T1 execution candidate
                              -> typed verification
                              -> host-only acceptance
```

T1 queue members are exact ordered digests bound to provider, route, role, privacy, context class, per-member ceiling, aggregate ceiling, expiry, and an authorized dispatcher set. One member permits one provider attempt. `queue-status` provides bounded global state/reconciliation enumeration. `t1-stage` creates exact batch plus dispatch authority only after manifest, token-policy and GLM approval validation. `t1-worker` claims one plan-scoped member and traverses `MacrRuntime`, Candidate Vault, events and accounting once. Expired or ambiguous dispatches enter `reconciliation_required`, block every later T1 claim, and never auto-requeue. Explicit reconciliation revokes the old batch, so continuation requires a new manifest and new authority. Verification and acceptance remain outside the worker. T2 coordinator output is an untrusted, content-free plan-revision proposal; it cannot issue authority, accept, merge, deploy, or name a resident. T3 target paths remain digest-only.

Differential manifests apply one exact probe pack and verifier graph to at least three qualified route candidates. Public comparison rows contain blinded candidate IDs, verifier counts, evidence digests, and costs—never model labels. `probe-plan` and `probe-replay` are manifest/replay commands and perform no provider execution.

## Direct conversation boundary

- Direct provider IDs are closed to exact `grok`/`grok-4.6` and exact `ollama_qwythos`/Qwythos-9B-v2 Q4_K_M.
- Provider/model, system-prompt hash, settings profile/version, policy hash, plaintext-encryption marker, dataset role, and training eligibility are immutable conversation metadata.
- Grok Direct records are `archive_only`; Qwythos Direct records are `eval_only`; both are `training_eligible=false`. The Qwythos installed model digest is pinned at conversation creation and its canonical weights are never modified.
- Complete history is sent without automatic summary, compaction, truncation, routing, fallback, or retry. A local context estimate warns or refuses before provider use without dropping earlier turns.
- Raw answer bytes enter the private Candidate Vault before a successful assistant message is committed. Rejected protocol observations retain safe usage/cost/finish/model evidence without entering conversation history.
- Archive is reversible. Operator-confirmed permanent deletion is serialized against sends for the same conversation, refuses an active run, purges unmaterialized Candidate answer files, deletes Direct plaintext under SQLite `secure_delete`, truncates the Direct WAL, and appends only a content-free deletion event. Existing provider accounting and operational hashes remain immutable.

## Loopback Web boundary

The server is Python standard library plus packaged vanilla HTML/CSS/JavaScript. It binds exactly to `127.0.0.1:0`, rejects non-loopback Host/Origin values, has exact bounded JSON routes, emits no CORS allowance, and loads no CDN, remote font, analytics, or third-party asset. A random bootstrap token travels in the URL fragment, is exchanged once for an HttpOnly SameSite=Strict cookie, and is invalidated. Model text is assigned through DOM `textContent`; it is never interpreted as provider-supplied HTML.

The on-demand Windows launcher holds a cross-process file lock, writes a content-free D-drive instance descriptor, and opens or reuses one server. Default idle shutdown is 30 minutes. Active requests and unsettled accounting prevent shutdown. The Desktop link contains only the D-drive launcher path; xAI credentials remain child-process environment only.

## Execution-state separation

The observable lifecycle is deliberately non-collapsing:

```text
provider completion
!= raw-answer capture
!= return-contract validity
!= materialization
!= verification
!= acceptance
```

Likewise, dispatch origin, authorization provenance, and lease ownership are independent records. An authority is exact, expiring, scoped, revisioned, and bound to the current stop epoch. A lease is an exclusive holder record with a monotonic fencing token. Admission verifies authority before and after lease acquisition; neither timing nor a process census grants authority.

## Connection scopes

`external_https` requires both `--allow-network` and `TaskContract.constraints.internet=true`. Hostname allowlisting, HTTPS, credential presence, privacy, positive budget, latency, capability, request size, redirect, response size, and response shape all fail closed.

`loopback_http` requires both `--allow-local` and `internet=false`. The v0.2 Ollama adapter accepts exactly `http://127.0.0.1:11434`, `local_only`, zero cost, and an installed exact model. It does not treat loopback authorization as external-network authorization.

The CLI resolves provider scope without creating state or reading a task file. State creation and task parsing happen only after the matching opt-in passes. It then rejects an incomplete legacy migration before reading the task, performs deterministic preflight, and issues a ten-minute one-shot delegation authority bound to provider, task type, optional exact member digest, origin process, and a policy snapshot hash.

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

## GLM delegated-worker boundary

- `glm_flash_worker` is fixed to direct `https://api.z.ai/api/paas/v4`, exact `glm-5.3-flash`, max reasoning, non-streaming output, and one transport attempt.
- The task must explicitly set `delegable=true` and `delegation_class=non_sensitive_routine`. Existing tasks default to closed values and therefore cannot reach GLM accidentally. Frontier-restricted and private-resident classes are never eligible.
- A SHA-256 approval manifest binds the complete credential-free request payload to exact provider ID, endpoint, model, task type, privacy class, maximum output, conservative USD ceiling, and pricing basis. Any instruction, sampling, content, or policy mutation invalidates approval before credential resolution.
- The checksum carried by the task is integrity evidence, not authority. Authority is a separate D: host-approval record with fixed `host_operator`, UUID nonce, creation time, and expiry, authenticated with HMAC-SHA256 using fixed-key custody unavailable to the task payload. `glm-approve` is an explicit host action; absent, malformed, expired, future-dated, MAC-invalid, or tampered records fail closed.
- Only `public` or explicitly `internal_approved` tasks qualify. Local-only data, local-or-approved-cloud data, write scopes, patch authority, missing verification, non-text inputs, and insufficient conservative budget fail before credential resolution or transport.
- The adapter sends a reduced envelope containing the goal, delegation decision, verification/return contract, exact text capability, and validated text inputs. It omits local task/workspace identity and the task currency budget. Obvious path/credential markers are denied as defense in depth, not treated as semantic proof of safety.
- `glm-preflight` performs credential-free structural validation of policy, exact request digest, and the external record, emitting only content-free metadata. It does not claim cryptographic approval. The wrapper never reads the key. Provider invocation reparses the current task, repeats structural checks, reads only fixed `D:\KEY\GLM.txt`, verifies the record MAC, and only then permits transport; this closes the preflight/invoke TOCTOU window before any network use. Health inspects key path metadata without reading contents.
- No tools, web search, file reads, filesystem writes, retries, provider fallback, verifier decision, acceptance event, resident identity, or private-residence access is available.
- List pricing is the enforcement basis. Current promotional pricing is recorded separately as non-authoritative estimated metadata.

GLM is the first provider with a native pre-validation observation adapter. Once one transport response exists, safe model, response ID, finish reason, token fields, estimated cost, duration, and exact UTF-8 answer bytes are observed before protocol checks. Non-stop, malformed, tool-bearing, web-search-bearing, model-mismatched, or over-bound responses do not retry. Public failure output omits candidate text while private capture remains available for audit. Other existing providers use the compatibility wrapper around their normalized result until migrated individually.

## Event, candidate, and accounting boundary

`runtime\dispatch.sqlite3` is the operational event, authority, lease, legacy-import, and candidate-provenance database. `accounting\accounting.sqlite3` stores invocation accounting and a local outbox. Each admitted run has exactly one dispatch event and at most one terminal event. A provider or adapter crash after admission is terminal `candidate_failure` with billing `unknown_after_dispatch`; cost never defaults to zero.

Fresh runtime-database construction negotiates WAL through a bounded bootstrap-only retry for transient SQLite `BUSY/LOCKED` results. Ordinary connections verify the persisted WAL mode instead of trying to change journal mode on every connection. This database retry is unrelated to provider transport, which remains single-attempt.

Dispatch events contain origin, task/provider identity, policy hash, authority digest/revision/epoch, and fencing token. Terminal events contain an allowlist of:

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
finish_reason
billing_state
provider_state
capture_state
return_contract_state
```

Missing metrics remain null. Task inputs, prompts, candidate bytes, warnings, thinking, credentials, local source paths, artifact paths/content, and error bodies are excluded. Candidate bytes are immutable files beneath `candidates`; event rows expose only content-free hashes and counts. Return-contract rejection never rewrites the raw capture.

Dispatch and terminal payloads enforce required keys, reviewed field types, and exact candidate-capture shape as well as top-level names. Every event API also applies a recursive privacy guard that normalizes snake/kebab/camel/acronym forms and rejects path/body/content keys plus drive-absolute, drive-relative, backslash-UNC, and forward-UNC values before transaction start. Generic diagnostics may still use reviewed metadata keys and HTTPS/model identifiers.

The legacy `ledger\events.jsonl` is immutable input evidence. Import is copy-only and idempotent. Corrupt or forbidden lines are retained byte-for-byte in quarantine and make the source incomplete; the CLI refuses provider invocation until the current nonempty source hash has a complete import record.

Accounting separates estimated/provider-reported/zero-local/unknown billing state from candidate status. Its `soft_warning` state is distinct from delegated task/provider hard budget gates. Direct `operator_managed` settings activate warn-only accounting without weakening credential, privacy, route, legacy, authority, or lease gates.

## Speaker identity boundary

```text
MODEL != RESIDENT
provider profile != speaker label
runtime role != authorship identity
```

`grok`, `grok_standard`, `ollama_qwythos`, `google_gemini`, `google_image`, and `glm_flash_worker` are service profiles only. A provider account identity and model-emitted self-label are claims or service provenance, not speaker identity evidence. Until a task-local identity envelope binds the current HOST-OBSERVED native task/session identifier and declares `identifier_kind`, the readable speaker identity is `unresolved`. This runtime does not authorize access to any named resident's private data.

## Commit boundary

```text
generation != verification != acceptance
```

Every delegated provider completion remains a candidate. MACR v0.6.0a1 preserves provider, capture, return-contract, materialization, verification, and acceptance states independently; Direct projection into its private conversation store does not create a coordinated verification or accepted-result transition.

## Model-local token-policy plane

`ModelTokenPolicy` is keyed by exact provider and exact model. Seven built-ins establish immutable provider ceilings; append-only revisions in `settings\model-token-policies.sqlite3` may change warning, hard-context, default-output, and max-output values only inside those ceilings. There is no global active token profile. Direct schema 2 pins canonical policy JSON/digest when a conversation is created. Delegated runtime resolves the current exact policy before authority admission, records its digest in the dispatch event, and never clamps an oversized task. GLM approval schema 2 binds the same digest, explicit context envelope, and output envelope.

Ordinary external policies are larger than the local Qwythos policy: Grok hard context 400,000; GLM and Gemini 512,000; MiniMax 180,000 with a 2,048 OpenAI-compatible output ceiling; Qwythos remains 8,192 context and 4,096 output. The T1 GLM preset is separate at 128,000 context and 8,192 output.

## Quiet verification admission

The invoker predicate is unchanged and fail-closed. `verify-v06.ps1` owns the named `MACR_V06_QUIET_CENSUS` mutex for its complete run and requires five zero samples before and after all tests. The sampler reports only counts and PIDs. The mutex coordinates updated verifiers; it does not control arbitrary processes or turn a census into authority.

`PLAIN_SOURCE` is a conservative wrapper-format guard: it rejects Markdown fences, evidence/warning sections, common leading prose wrappers, and headings derived from the task's declared language. A generic `Code:`/`Source:` heading is rejected only when the colon ends the line, avoiding false rejection of source such as Python `code: str = 'ok'`. It does not prove that arbitrary source compiles. `JSON_OBJECT` validates one semantic object with unique keys; whitespace, final newline, and member order are not significant. Byte-exact JSON belongs under `EXACT_TEXT`.
