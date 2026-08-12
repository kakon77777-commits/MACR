# Storage and migration contract

Status: active from MACR v0.1
Policy tags: `C_DRIVE_PERSISTENCE_FORBIDDEN`, `MIGRATION_REQUIRED`, `SECRETS_EXTERNAL`

## Canonical roots

| Purpose | Current root | Persistence class |
|---|---|---|
| Source, docs, tests, non-secret configuration | `D:\Ai\work together\MACR` | canonical and backed up |
| Runtime ledger, cache, artifacts, test temporary data | `R:\AI_Runtime\macr-state` | canonical runtime state |
| Future Codex state target | `R:\AI_Runtime\codex-home` | pending controlled migration |
| Existing Codex installation and state on C | unchanged | reinstallable or pending migration review |

Application binaries may currently execute from C. That does not authorize persistent MACR output on C.

## Environment-root indirection

Runtime code resolves roots from environment variables and uses D/R defaults only when they are absent:

```text
MACR_ROOT
MACR_STATE_ROOT
CODEX_HOME_TARGET
```

`CODEX_HOME_TARGET` is not the official active variable. It records the intended destination without changing the running Codex instance. During an approved migration it will become the value of official `CODEX_HOME` only after copy and validation.

Official OpenAI documentation states that `CODEX_HOME` controls Codex config, auth, logs, sessions, skills, and standalone package metadata for the CLI, IDE extension, app-server, and installers. The destination must already exist:

- https://learn.chatgpt.com/docs/config-file/environment-variables
- https://learn.chatgpt.com/docs/config-file/config-advanced

## Later SSD migration procedure

Do not delete or overwrite the source disk during these steps.

1. Freeze writes and record the current source/state paths and volume labels.
2. Create the new destination directories.
3. Copy source and state while preserving timestamps.
4. Produce and compare SHA-256 manifests at source and destination.
5. Point `MACR_ROOT` and `MACR_STATE_ROOT` to the new SSD.
6. Run the complete offline suite and a ledger append/readback smoke test.
7. Separately copy `CODEX_HOME`, set the official variable, restart Codex, and verify login, config, skills, sessions, and provider profiles.
8. Retain the old data as a rollback copy until the operator explicitly accepts the migration.

Changing drive letters must require environment changes only. A source scan must show no operational hard-coded C path.

## Secrets

- Commit environment-variable names only.
- Do not commit `.env`, API keys, bearer tokens, copied credential files, or provider response dumps that may contain secrets.
- Claude API use is forbidden under the current policy.
- A subscription-client credential is still a credential and must remain outside the repository.
