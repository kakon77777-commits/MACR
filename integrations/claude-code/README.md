# Claude Code → MACR

Claude Code can use MACR today through the same local CLI used by an operator or
Codex. This route reaches the shared provider registry, approval store, budgets,
Candidate Vault, event store and accounting ledger. It does not use an Anthropic
API key and does not convert the Claude subscription into API authority.

## Current usable route

From a Claude Code shell in the MACR repository:

```powershell
Set-Location 'D:\Ai\work together\MACR'

# Read-only/offline policy and approval digest preparation.
.\scripts\macr.ps1 glm-preflight `
    .\examples\glm-worker-task.example.json `
    --show-required-digest

# After the operator places that exact digest in the reviewed task contract:
.\scripts\macr.ps1 glm-approve `
    .\examples\glm-worker-task.example.json `
    --expires-in-days 30

# Paid network invocation; no retry or fallback.
.\scripts\invoke-glm.ps1 `
    -TaskPath .\examples\glm-worker-task.example.json
```

Other configured providers use the generic route, for example:

```powershell
.\scripts\macr.ps1 invoke grok `
    .\examples\grok-task.example.json `
    --allow-network

.\scripts\macr.ps1 invoke ollama_qwythos `
    .\examples\ollama-task.example.json `
    --allow-local
```

These commands are deliberately attributed as `cli` / `process_id`. Claude Code
hook JSON and `CLAUDE_CODE_SESSION_ID` are useful discovery evidence, but a shell
can fabricate both; they are not accepted as `task_local_host_observed` or as
authority. A future host-owned verifier can use `MacrHostAdapter`, but that live
binding remains `NotMeasured`.

Provider output remains an unverified candidate. GLM still rejects sensitive,
`frontier_restricted` and `private_resident` tasks, patch output, write scope and
tools. The active provider capability tier and exact approval digest determine
the maximum latency and accepted task types.
