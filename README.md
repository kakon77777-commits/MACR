# MACR Runtime v0.1

MACR is a migration-first provider runtime for heterogeneous AI workers. Codex can act as the primary host, while provider-specific adapters return normalized **candidate** results. Candidates are not accepted work until a verifier or operator commits them.

This repository starts from two local evidence sources:

- `R:\AI_gamedesign\workspace\technical-docs\01_GPT_Local_Multi_AI_Collaboration_Runtime_v0.1.md`
- `D:\Ai\work together\cross-task-multi-ai-execution-study\paper.md`

The implementation is intentionally independent from APR v0.10, while retaining compatible ideas: bounded contracts, explicit budgets, append-only receipts, and generation/verification/acceptance separation.

## Storage contract

Persistent writes are split by purpose:

```text
MACR_ROOT        = D:\Ai\work together\MACR
MACR_STATE_ROOT  = R:\AI_Runtime\macr-state
CODEX_HOME_TARGET= R:\AI_Runtime\codex-home
```

`CODEX_HOME_TARGET` is documentation for a later controlled migration. This repository does **not** change the active `CODEX_HOME` or current Codex login state.

See [`docs/STORAGE_AND_MIGRATION.md`](docs/STORAGE_AND_MIGRATION.md).

## Provider baseline

| Provider | v0.1 state | Authentication policy |
|---|---|---|
| MiniMax | adapter implemented; live call blocked until environment configuration exists | API key environment variable |
| Grok | reserved and disabled | pending API application |
| Claude | API disabled | future approved subscription client only |

No API call occurs during import, `doctor`, configuration validation, or tests.

## Quick verification

```powershell
cd 'D:\Ai\work together\MACR'
.\scripts\verify.ps1
```

Or directly:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest discover -s tests -v
python -m macr_runtime doctor --config config\providers.json
```

The doctor reports whether environment variables are present, but never prints secret values.

Validate an example contract without network access:

```powershell
.\scripts\macr.ps1 validate-task examples\minimax-task.example.json
```

## Enabling MiniMax later

Set these environment variables only after checking the then-current MiniMax documentation:

```text
MINIMAX_API_KEY
MINIMAX_BASE_URL
MINIMAX_MODEL
```

The adapter defaults to the OpenAI-compatible `/chat/completions` path. Override it in configuration if the approved endpoint differs. Live conformance testing is a separate opt-in step.

After the activation gate in `docs/PROVIDER_STATUS.md` is satisfied, an invocation still requires an explicit network switch:

```powershell
.\scripts\macr.ps1 invoke minimax examples\minimax-task.example.json --allow-network
```

Without `--allow-network`, the command exits before reading the task or resolving credentials. The positive `max_cost_usd` field authorizes a billable dispatch, but v0.1 does not independently prove the final currency charge; confirm current pricing before any live test.

## Current limits

- No automatic router yet.
- No provider-price engine or hard provider-side USD cap yet.
- No cross-process file lock yet; the JSONL ledger is process-safe only within one runtime instance.
- No live provider has been called.
- No Claude subscription-client adapter has been selected or verified.
- No active Codex state has been migrated from C.
