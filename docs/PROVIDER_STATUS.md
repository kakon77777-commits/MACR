# Provider status

Updated: 2026-08-26

| Provider ID | Required model/route | Credential | Billing | Runtime state |
|---|---|---|---:|---|
| `minimax` | operator-selected compatible model | `MINIMAX_API_KEY` | allowed | adapter implemented; account configuration may be absent |
| `grok` | `grok-4.6`, reasoning high | `XAI_API_KEY` | allowed | adapter implemented; live v0.2 acceptance pending |
| `grok_standard` | `grok-4.3` | `XAI_API_KEY` | allowed | adapter implemented; manual profile only |
| `ollama_qwythos` | installed Qwythos-9B-v2 Q4_K_M | none | zero | adapter implemented; live MACR acceptance pending |
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

## Claude boundary

Do not read or use `ANTHROPIC_API_KEY`. A future Claude integration must be an explicitly approved subscription-client route and must not fall back to API billing.
