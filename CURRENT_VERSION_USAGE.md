# MACR current-version usage

Current package line: `0.7.0a0`

Canonical source: `D:\Ai\work together\MACR`

Canonical state: `D:\AI_RESIDENCE\AI_Runtime\macr-state`

GitHub: <https://github.com/kakon77777-commits/MACR>

This file is the short operator index. `README.md`, `docs/ARCHITECTURE.md`, and
the named checkpoints remain the detailed contracts.

## What is usable now

- Direct Chat Alpha provides explicit native Grok 4.6 and local
  Ollama/Qwythos conversations.
- Claude Code and Codex can invoke configured MACR providers through the
  ordinary CLI under honest `cli` attribution.
- `glm_flash_worker` can perform separately approved, non-sensitive candidate
  work through the direct Z.ai API.
- GLM accounting schema 4 records safe transport-boundary telemetry for new
  calls and supports provider/time-filtered failure summaries.
- T1 manifest schema 4 supports an operator-selected dynamic `worker_count`;
  each worker invocation still claims at most one member.
- Runtime schema 8 adds a provider-wide Provider Admission Kernel. GLM starts
  with effective target 8, review marker 16 and hard ceiling 32; an exact
  operator authority may select any target from 1 through 32. Queued demand
  never directly changes provider capacity. Production transport accepts only
  the canonical operator runtime; alternate D-drive databases are explicit
  offline-test capabilities.
- The v0.7 Agent contract, state, and semantic kernels through Phase C are
  available offline.

Provider completion is still only a candidate. Verification, acceptance,
materialization, merge, release, deployment, and resident identity remain
separate decisions.

## Direct Chat

Install or refresh the Desktop shortcut:

```powershell
Set-Location 'D:\Ai\work together\MACR'
.\scripts\install-direct-chat-shortcut.ps1
```

Then open **MACR Direct Chat (Alpha)**. A local startup smoke without model
generation is:

```powershell
.\scripts\macr.ps1 direct-chat --smoke
```

Full behavior and privacy-deletion boundaries are in `docs\DIRECT_CHAT.md`.

## Claude Code or Codex calling GLM

Do not request, paste, export, or set `ZAI_API_KEY`. MACR uses only the fixed
bounded file loader for `D:\KEY\GLM.txt`.

Check the provider without contacting it:

```powershell
Set-Location 'D:\Ai\work together\MACR'
$report = .\scripts\macr.ps1 doctor | ConvertFrom-Json
$report.providers |
  Where-Object provider_id -eq 'glm_flash_worker'
```

For every distinct task:

```powershell
.\scripts\macr.ps1 glm-preflight .\path\to\task.json --show-required-digest
# A trusted operator writes the returned digest into the exact task.
.\scripts\macr.ps1 glm-approve .\path\to\task.json --expires-in-days 30
.\scripts\macr.ps1 glm-preflight .\path\to\task.json
.\scripts\invoke-glm.ps1 -TaskPath .\path\to\task.json
```

Output selection is automatic but never silent:

- a `provider_conformance` task with `exact_text` of at most 256 UTF-8 bytes
  requires/recommends 32,768;
- every translation, classification, analysis, review, or code-text task
  requires/recommends 65,536;
- preflight returns the profile and recommendation; the AI host writes the
  exact integer before obtaining a new digest and approval;
- an operator override cannot lower the 65,536 real-work requirement.

The PowerShell entry point temporarily forces its Python child to UTF-8 and
restores the outer `PYTHONUTF8` and `PYTHONIOENCODING` values. Claude/Codex do
not need to configure console encoding before multilingual output.

Only the last command contacts Z.ai. There is one attempt and no automatic
retry or provider fallback. See `docs\GLM_CLAUDE_CODE_QUICKSTART.md` for task
constraints and the failure map.

## Read accounting without mixing providers or dates

```powershell
.\scripts\macr.ps1 accounting-status `
  --provider glm_flash_worker `
  --since 2026-09-08T00:00:00+00:00
```

Interpretation:

- `known_cost_usd` sums only known amounts.
- `unknown_after_dispatch` is not zero cost and requires later billing
  reconciliation.
- `unsettled_count=0` means runtime terminal rows exist; it is not provider
  invoice settlement.
- `by_failure` can show HTTP status, bounded provider business code,
  network-attempt, response-received, and transport-stage evidence for calls
  made after accounting schema 4 became active.
- Historical failures remain null; MACR never invents missing telemetry.

Remote HTTP error messages, response bodies, connection reasons, credentials,
prompts, and answers are not written into public event/accounting telemetry.

## Dynamic T1 use

T1 is configured per private schema-4 manifest:

- member count is the exact ordered work set;
- `worker_count` is between one and member count;
- the authorized dispatcher list exactly matches `worker_count`;
- cost ceilings are per member, with exact aggregate and campaign envelopes;
- one member permits one provider attempt;
- ambiguous dispatch blocks later claims and never auto-requeues.
- `t1-stage --project-id ... --admission-lane ...` binds admission identity
  outside the unchanged schema-4 manifest digest;
- provider BUSY leaves a member queued with `attempts=0` rather than creating a
  failed candidate or provider accounting row.
- an authority, TTL, or circuit change between grant and transport is rechecked
  under the final write lock; an unused blocked grant cannot reach the provider.

Staging is offline:

```powershell
.\scripts\macr.ps1 t1-stage .\private\t1-manifest.json `
  --project-id my-project --admission-lane bulk `
  --dispatcher-id worker-1 --dispatcher-id worker-2 `
  --expires-in-minutes 30
```

Execution is explicit and may contact the provider:

```powershell
.\scripts\macr.ps1 t1-worker .\private\t1-manifest.json `
  --dispatcher-id worker-1 --allow-network
```

The T1 product path is implemented, but repository state alone supplies no
live manifest, approvals, or live acceptance.

## Not active yet

- Phase D observation/action/temporal continuation and the closed Agent loop;
- autonomous provider routing or acceptance;
- live host-owned Claude/Codex identity binding;
- Anthropic API access through a Claude subscription;
- automatic provider retry, fallback, unattended target promotion, or
  provider-specific rate adaptation beyond the explicit admission circuit;
- live-accepted T1 campaign authority;
- Google Veo, TTS, and Lyria execution adapters.

Use `docs\PROVIDER_STATUS.md` for the exact current provider matrix and
`docs\checkpoints` for version-bound evidence.
