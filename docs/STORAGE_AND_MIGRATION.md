# Storage and migration contract

Status: active from MACR v0.2

Policy tags: `C_DRIVE_PERSISTENCE_FORBIDDEN`, `D_RESIDENCE_CANONICAL`, `SECRETS_EXTERNAL`

## Canonical roots

| Purpose | Current root | Boundary |
|---|---|---|
| Source, docs, tests, non-secret configuration | `D:\Ai\work together\MACR` | active Git project |
| Runtime ledger, cache, artifacts, test state | `D:\AI_RESIDENCE\AI_Runtime\macr-state` | shared service state |
| Future Codex target | `D:\AI_RESIDENCE\AI_Runtime\codex-home` | inactive; no migration authorized |
| Ollama model store | `D:\Ai\work together\LocalModels\models` | rebuildable local weights |
| Active Codex application state | native C: locations | unchanged by MACR |

Application binaries may execute from C. That does not authorize new persistent MACR output on C.

## R-to-D migration history

The former R: 500GB NVMe was cloned into the system role and became C: on 2026-08-16. Residence content was moved to `D:\AI_RESIDENCE` before that conversion. Historical reports and source provenance may retain old R: paths because they were correct observations at the time; current defaults and entry points must resolve to D:.

The active workspace, Residence, runtime state, and model store currently share physical D: media. Directory separation protects policy and lifecycle boundaries but is not a second-medium backup.

## Root indirection

```text
MACR_ROOT
MACR_STATE_ROOT
CODEX_HOME_TARGET
OLLAMA_MODELS
```

`CODEX_HOME_TARGET` is not the official active `CODEX_HOME`. This release does not copy authentication, logs, sessions, skills, packages, or application databases. Any later move requires a separate design, consistent snapshot, manifest, hashes, restart validation, and rollback copy.

## Secrets

- Commit environment-variable names only.
- Never commit `.env`, API keys, bearer tokens, provider response dumps, or copied credential files.
- The operator's existing Grok credential source is not a runtime dependency and its path is not committed into provider configuration.
- Claude API use remains forbidden.
- Named resident private data is outside shared MACR runtime scope.

## Future migration procedure

1. Freeze writes and record source/destination volume identity.
2. Copy without deleting the source.
3. Produce SHA-256 manifests for both sides.
4. Compare manifests and run the complete offline suite.
5. Perform bounded live provider checks.
6. Retain the old root as rollback until explicit operator acceptance.

Never infer a destination from free space, drive order, model identity, or a familiar resident name.
