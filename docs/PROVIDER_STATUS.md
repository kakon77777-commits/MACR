# Provider status

Updated: 2026-08-27

| Provider ID | Required model/route | Credential | Billing | Runtime state |
|---|---|---|---:|---|
| `minimax` | operator-selected compatible model | `MINIMAX_API_KEY` | allowed | adapter implemented; account configuration may be absent |
| `grok` | `grok-4.6`, reasoning high | `XAI_API_KEY` | allowed | adapter implemented; live v0.2 acceptance pending |
| `grok_standard` | `grok-4.3` | `XAI_API_KEY` | allowed | adapter implemented; manual profile only |
| `ollama_qwythos` | installed Qwythos-9B-v2 Q4_K_M | none | zero | adapter implemented; live MACR acceptance pending |
| `google_gemini` | `gemini-3.7-flash` | D: service-account file + project environment | allowed | adapter implemented; live v0.3 candidate evidence recorded |
| `google_image` | `gemini-3.1-flash-image`, one 1K output | D: service-account file + project environment | allowed | adapter implemented; live v0.3 candidate evidence recorded |
| `glm_flash_worker` | `glm-5.3-flash`, reasoning max | process-only `ZAI_API_KEY` from D: key file | allowed | restricted adapter implemented; live v0.4 acceptance pending |
| `google_veo_fast` | `veo-3.1-fast-generate-001` | not loaded | unavailable | disabled; no long-running-operation adapter |
| `google_tts` | `gemini-3.1-flash-tts-preview` | not loaded | unavailable | disabled; no audio adapter |
| `google_lyria` | `lyria-3-clip-preview` | not loaded | unavailable | disabled; no music adapter |
| `claude_subscription` | approved subscription client not selected | subscription login | API forbidden | disabled |

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

Dispatch requires all of:

- `delegable=true` on the task contract;
- `public` or explicitly `internal_approved` privacy;
- `internet=true`, positive latency and cost budgets, and `text_generation` capability only;
- empty `workspace.write_scope`, no requested patch authority, and independent verification;
- empty inputs or bounded text-only inputs with non-path labels.

The outbound envelope excludes the local workspace path and currency budget. Candidate output is never verification or acceptance. Budget admission and recorded currency cost use conservative list pricing; the lower promotional estimate is informational only.

## Claude boundary

Do not read or use `ANTHROPIC_API_KEY`. A future Claude integration must be an explicitly approved subscription-client route and must not fall back to API billing.
