# Google GenAI Balanced Provider Integration Design

Status: approved in chat on 2026-08-26; written specification awaiting final operator review

## Purpose

Extend MACR from v0.2.0 to v0.3.0 with a balanced, governed Google Vertex AI integration:

- `google_gemini`: exact `gemini-3.7-flash` for text generation and multimodal understanding;
- `google_image`: exact `gemini-3.1-flash-image` for image generation and one-reference-image editing;
- disabled discovery profiles for Veo, TTS, and Lyria, without callable implementations.

The existing `D:\Ai\work together\google-genai` directory remains preservation-first research evidence. MACR does not import it as runtime code, does not rewrite its experiments, and does not delete its existing service-account credential source.

All Google output remains a candidate. Model generation does not imply verification, acceptance, identity, or authority.

## Approved operator decisions

- Google is integrated into MACR rather than directly into native Codex provider selection.
- The architecture uses two provider adapters with one shared Google core, not a universal mode-switching adapter or a separate gateway process.
- The first release activates Gemini 3.7 Flash understanding and Gemini 3.1 Flash Image generation.
- Veo, TTS, and Lyria are discoverable but disabled until their own implementation and live-verification cycles.
- The existing service-account JSON is copied, byte-for-byte, to `D:\KEY\GOOGLE_VERTEX.json`; its source remains untouched until a later explicit deletion decision.
- Persistent artifacts remain on D: under the existing MACR state root.
- Live conformance is explicitly authorized after offline implementation gates pass. It has no separate campaign-wide USD ceiling and no credit-expiry shutdown.
- Promotional-credit names, balances, restrictions, and expiration dates are not embedded in runtime policy. They may change without requiring a code change.
- No automatic retry, fallback, search grounding, server-side tool, or substitute model is permitted in v0.3.
- Existing task-level cost metadata and budget behavior remain part of ordinary MACR task governance. Waiving a separate live-test campaign ceiling does not authorize hidden or unattended spend.

## Observed baseline

### MACR

MACR `main` is clean at `fa6a221` with v0.2.0 provider support for Grok 4.6, Grok 4.3, MiniMax, local Qwythos/Ollama, and a disabled Claude subscription route. The exact-tree offline gate passed 69/69 tests. Runtime state is:

```text
D:\AI_RESIDENCE\AI_Runtime\macr-state
```

The current provider result already supports `artifacts`, but there is no enforced media-input schema, artifact persistence protocol, or provider-neutral media validation layer.

### Google prototype

The existing Google prototype is not a Git repository. It contains experiments using Google Gen AI, older Vertex SDK paths, direct REST requests, a Model Garden catalog generator, cached discovery output, and a service-account JSON with a private key. The credential contents were not printed or copied during design.

Observed local dependencies and discovery evidence on 2026-08-26:

- `google-genai` 2.17.0 is installed;
- `google-auth` 2.56.3 and `httpx` 0.28.1 are installed;
- the older `google-cloud-aiplatform` package is not installed;
- the 2026-08-25 project catalog lists `gemini-3.7-flash` as GA;
- the catalog also lists Gemini 3.1 image models, Veo 3.1, TTS, and Lyria models.

Catalog visibility is discovery evidence only. It does not prove inference entitlement, successful billing, response shape, or acceptance.

### Current official model facts

Gemini 3.7 Flash uses exact model ID `gemini-3.7-flash`. It accepts text, image, video, audio, and PDF input and returns text. Image and audio generation are not capabilities of this model:

- https://ai.google.dev/gemini-api/docs/models/gemini-3.7-flash
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/document-understanding

The approved image model is exact `gemini-3.1-flash-image`. Google recommends the Gemini image line over deprecated Imagen endpoints:

- https://ai.google.dev/gemini-api/docs/image-generation
- https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing

Veo 3.1 Generate and Fast Generate use exact GA model IDs `veo-3.1-generate-001` and `veo-3.1-fast-generate-001`:

- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/veo/3-1-generate

Cloud promotional credits are scoped to eligible services or SKUs. Runtime correctness must not depend on a current promotion:

- https://docs.cloud.google.com/billing/docs/how-to/resolve-issues

## Provider architecture

### Active profiles

| Provider ID | Adapter kind | Exact model | Capabilities | Scope | Output |
|---|---|---|---|---|---|
| `google_gemini` | `google_vertex_gemini` | `gemini-3.7-flash` | `text_generation`, `multimodal_understanding` | external HTTPS | text candidate |
| `google_image` | `google_vertex_image` | `gemini-3.1-flash-image` | `image_generation` | external HTTPS | one image artifact plus optional text |

Both require:

- `--allow-network`;
- `TaskContract.constraints.internet = true`;
- an approved non-local privacy level;
- required capability declaration;
- Google project and credential configuration;
- exact-model equality in the normalized result where the API exposes returned model identity.

There is no default Google route and no automatic provider selection. The caller names the provider ID.

### Shared Google core

The adapters share a small Google core responsible for:

- lazy service-account authentication;
- Google Gen AI client construction;
- project and location resolution;
- SDK exception normalization and secret redaction;
- input-file validation and conversion to SDK parts;
- usage normalization and cost-estimate provenance;
- media-byte validation and atomic artifact persistence.

Provider-specific request and response handling remains in separate adapter classes. Text response normalization cannot accidentally accept image output, and image persistence cannot run for a Gemini text candidate.

The implementation uses the current `google-genai` SDK. It does not add the deprecated `vertexai.generative_models` interface or import prototype scripts.

### Configuration

The additive provider kinds fit the existing provider schema v2. The schema version remains 2 unless implementation discovers an unavoidable incompatible configuration change.

Non-secret Google configuration uses environment indirection:

```text
GOOGLE_APPLICATION_CREDENTIALS
GOOGLE_CLOUD_PROJECT
```

Committed provider policy fixes:

```text
location = global
allowed_hosts = aiplatform.googleapis.com, oauth2.googleapis.com
model = exact profile model
```

The first release does not use regional inference hosts. Any later regional endpoint requires an explicit allowlist change and regression tests rather than wildcard host matching.

No project ID, service-account email, private key, OAuth token, billing-account identifier, promotion ID, or literal credential path is committed to provider configuration. The runtime process points `GOOGLE_APPLICATION_CREDENTIALS` at `D:\KEY\GOOGLE_VERTEX.json`.

`doctor` remains offline. It validates provider policy, environment-variable presence, credential-file existence and JSON shape without printing values or minting an OAuth token. It reports `configured_offline`, never `live`.

## Credential custody

Credential migration is copy-only and preservation-first:

1. Resolve the exact source and target paths.
2. Refuse a non-D: target.
3. Refuse to overwrite an existing non-identical target.
4. Copy source bytes to `D:\KEY\GOOGLE_VERTEX.json`.
5. Compare byte length and SHA-256.
6. Parse only enough JSON structure to confirm service-account fields; never print field values.
7. Re-read both hashes after the copy.
8. Leave the source unchanged.

The credential is never committed, copied into MACR state, included in a fixture, added to a design artifact, or exposed in error text. Source deletion, key rotation, ADC, Workload Identity, and moving native Google login state are separate future decisions.

## Task input contract

`TaskContract.goal` remains the primary text instruction. Google providers additionally accept bounded file entries in `TaskContract.inputs`:

```json
{
  "type": "file",
  "path": "relative/path/to/input.png",
  "mime_type": "image/png",
  "sha256": "lowercase-hex-digest"
}
```

Rules:

- `path` is workspace-relative and cannot contain `..`;
- the resolved file must remain under the task workspace;
- the file must be a regular file, not a directory, symlink, junction, device, or named pipe;
- the declared SHA-256 must equal the bytes read for dispatch;
- declared MIME, extension where present, and detected magic must agree;
- each file is at most 20 MiB and all input files total at most 32 MiB;
- the first-release input MIME allowlist is exactly `image/png`, `image/jpeg`, `image/webp`, `video/mp4`, `audio/mpeg`, `audio/mp3`, `audio/wav`, and `application/pdf`;
- no external URL, `gs://` URI, remote fetch, inline base64, or absolute path is accepted;
- validation completes before authentication or network access.

`google_image` accepts text-to-image plus at most one validated local reference image. It returns exactly one image and defaults to 1K output. Multiple reference images, multi-image output, 2K/4K output, and conversational editing are non-goals for v0.3.

## Request policy

### `google_gemini`

The adapter uses `genai.Client(vertexai=True, project=..., location="global")` and exact `gemini-3.7-flash`.

The request includes:

- one bounded MACR worker instruction;
- the task goal;
- validated local media parts when present;
- `max_output_tokens` from the task contract;
- provider-policy thinking level `medium` for normal use.

The v0.3 profile does not enable Google Search grounding, Maps grounding, code execution, computer use, File Search, URL Context, cached-content creation, or function tools. A future tool-enabled profile requires a separate design.

### `google_image`

The adapter uses exact `gemini-3.1-flash-image` with:

- task goal as the image instruction;
- zero or one validated reference image;
- one requested output image;
- 1K output resolution;
- no search grounding or server-side tool.

The provider must not silently select Flash Lite Image, Gemini Pro Image, Imagen, or another resolution.

## Artifact persistence

Google artifacts are stored under:

```text
D:\AI_RESIDENCE\AI_Runtime\macr-state\artifacts\google\<task_id>\
```

Persistence is fail-closed:

1. Create a task-scoped temporary file inside the target artifact filesystem.
2. Enforce response and decoded-byte limits before finalization.
3. Detect actual media type from magic bytes; never trust a requested extension.
4. Accept final image output only as `image/jpeg` or `image/png` and require full image decoding.
5. Record width, height, byte length, and SHA-256.
6. Atomically rename to a non-existing final name.
7. Never overwrite an existing artifact.

The exact provider bytes are preserved without recompression or metadata rewriting. Invalid or partial bytes never become an artifact. Temporary failure files are removed before returning the failed candidate.

`ProviderResult.artifacts` returns only bounded metadata:

```text
relative_path
mime_type
width
height
byte_length
sha256
model
created_at
```

## Cost and ledger policy

Live conformance has no additional campaign-wide USD ceiling and no date-based shutdown. The adapter is billing-source agnostic: Free Trial, promotional credit, and paid billing do not change model selection or runtime behavior.

Ordinary MACR tasks retain the existing `max_cost_usd` contract. For image generation, the adapter performs a deterministic preflight estimate from exact model and requested resolution. If an ordinary task budget is below that estimate, it fails before authentication and network access. Text costs are normalized from provider usage metadata when available.

When Google does not return invoice-grade currency cost, MACR records:

- token and media usage;
- model and endpoint location;
- output image count and resolution;
- `currency_cost_usd` as a clearly labeled estimate;
- pricing source, effective date, and formula version.

An estimate is never presented as an observed Cloud Billing charge. Billing reports remain the authority for promotion application and invoice cost.

The append-only ledger may add allowlisted non-content metrics:

```text
input_media_count
input_media_bytes
output_artifact_count
output_artifact_bytes
cost_kind = actual | estimated | unavailable
pricing_basis_version
```

It never stores task goals, serialized input entries, workspace paths, artifact bytes, source filenames, image prompts, OAuth tokens, credential fields, remote response bodies, or generated text/image content.

## Error handling

The following fail before network access:

- missing or malformed configuration;
- missing, non-file, oversized, or structurally invalid credential;
- wrong network opt-in, privacy, internet, or capability policy;
- path escape, link/reparse-point input, hash mismatch, MIME mismatch, or input-size overrun;
- occupied artifact destination;
- ordinary-task image estimate above `max_cost_usd`.

The following normalize to `candidate_failure` without retry or fallback:

- authentication or entitlement denial;
- HTTP error, redirect, timeout, quota, or rate limit;
- model mismatch, empty candidate, safety block, or malformed response;
- unexpected response modality;
- oversized, invalid, undecodable, or unsupported image bytes;
- final atomic-write failure;
- post-response task-budget overrun where cost could not be known before dispatch.

Google SDK retry behavior must be explicitly disabled or bounded to one transport attempt. If the SDK cannot guarantee that, the implementation must use a transport path that can. Exception messages and remote bodies are not reflected. Only sanitized failure category and exception type may be recorded.

## Disabled future providers

The provider document includes non-callable profiles:

| Provider ID | Exact model | Intended capability | Initial status |
|---|---|---|---|
| `google_veo_fast` | `veo-3.1-fast-generate-001` | `video_generation` | disabled |
| `google_tts` | `gemini-3.1-flash-tts-preview` | `audio_generation` | disabled |
| `google_lyria` | `lyria-3-clip-preview` | `music_generation` | disabled |

Each has an explicit `disabled_reason` stating that v0.3 does not implement or live-verify it. The registry creates no callable adapter. Active provider failure never routes to a disabled profile.

Veo requires long-running-operation polling, cancellation, output download, and video-specific cost handling. TTS and Lyria require their own MIME, duration, and preview/terms boundaries. Those are separate follow-up designs.

## Speaker identity boundary

Google provider and model selection do not establish resident or speaker identity:

```text
MODEL != RESIDENT
provider profile != speaker label
cloud service account != authorship identity
```

Until a task-local identity envelope binds the current HOST-OBSERVED native task/session identifier and declares `identifier_kind`, readable speaker identity remains `unresolved`. Provider results preserve service provenance but do not claim a resident identity.

## Testing and acceptance

Implementation follows test-driven development. Each behavior is observed failing before minimal implementation.

Offline tests cover:

- additive Google provider configuration and exact model IDs;
- disabled Veo/TTS/Lyria registration;
- lazy auth and strictly offline doctor behavior;
- missing/malformed credential handling without value disclosure;
- network, privacy, internet, capability, and cost-policy gates;
- path traversal, absolute path, link/reparse point, MIME, magic, hash, per-file, and aggregate-size rejection;
- Gemini request construction with no tools or grounding;
- image request construction, one-reference limit, one-output/1K enforcement, and no fallback;
- token usage and estimated-cost provenance;
- response modality and malformed response rejection;
- atomic no-overwrite artifact persistence;
- PNG/JPEG magic, decode, dimension, byte-count, and hash checks;
- ledger content exclusion and bounded metric allowlist;
- regression coverage for Grok, MiniMax, Ollama, Claude policy, storage, and CLI gates;
- secret-pattern and operational C:/R: path scans.

After the offline gate passes, the operator has authorized direct live conformance without an additional campaign cap:

1. Copy the credential to `D:\KEY\GOOGLE_VERTEX.json`, prove byte length and SHA-256 equality, and prove the source remains unchanged.
2. Invoke `google_gemini` with a public fixed-string goal and exact-output acceptance.
3. Invoke `google_gemini` with a deterministic, non-sensitive local test image and require an exact observable answer.
4. Invoke `google_image` once with a neutral public prompt and require exactly one valid 1K image artifact.
5. Re-read artifact bytes, MIME, dimensions, and SHA-256 independently.
6. Confirm no key, token, prompt, answer, source path, or artifact content appears in Git or the ledger.
7. Confirm no retry, fallback, grounding, or disabled-provider call occurred.

Live checks are not part of the default offline suite. A failed check stops the acceptance sequence unless the failure is independently diagnosed and the operator explicitly continues.

## Versioning and delivery

- Package version advances to `0.3.0`.
- Provider configuration remains schema version 2 unless an implementation-proven incompatibility requires a separately reviewed bump.
- This design receives one local commit before implementation planning.
- Implementation uses a reviewable feature branch/worktree and separate commits.
- No remote push, pull request, release, deployment, billing configuration change, or source-credential deletion is authorized by this design.

## Non-goals

- native Codex Google model profiles;
- importing prototype scripts as production runtime code;
- changing or deleting the prototype directory;
- deleting or rotating the original service-account credential;
- ADC, Workload Identity, or user-login migration;
- external URLs, `gs://` inputs, remote fetches, or automatic uploads;
- multiple reference images or multiple generated images;
- 2K/4K output in v0.3;
- Google Search/Maps grounding, code execution, computer use, File Search, URL Context, or tools;
- Veo, TTS, or Lyria invocation;
- automatic provider routing, retries, or fallback;
- campaign-wide spending caps, promotion coupling, or credit-expiration shutdown;
- automated verification or acceptance of provider output.
