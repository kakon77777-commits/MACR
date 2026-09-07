# Storage and migration contract

Status: active at MACR v0.7.0a0 Phase-C Alpha with retained Direct UI 0.1

Policy tags: `C_DRIVE_PERSISTENCE_FORBIDDEN`, `D_RESIDENCE_CANONICAL`, `SECRETS_EXTERNAL`

## Canonical roots

| Purpose | Current root | Boundary |
|---|---|---|
| Source, docs, tests, non-secret configuration | `D:\Ai\work together\MACR` | active Git project |
| Runtime databases, legacy ledger, candidates, cache, artifacts, test state | `D:\AI_RESIDENCE\AI_Runtime\macr-state` | shared service state |
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

## v0.6 runtime-state layout

```text
D:\AI_RESIDENCE\AI_Runtime\macr-state\
  runtime\agent.sqlite3        future Agent/semantic state; not created by release
  runtime\dispatch.sqlite3       operational events, runs, exact authority,
                                 T1 queue, target leases, legacy/candidate provenance
  accounting\accounting.sqlite3 invocation accounting and local outbox
  candidates\                   immutable private candidate bytes
  ledger\events.jsonl           preserved legacy source; no new writes
  quarantine\                   byte-exact corrupt legacy lines
  artifacts\                    validated provider artifacts
  cache\                        rebuildable cache
  test-tmp\                     bounded disposable verification state
  direct\conversations.sqlite3 exact plaintext Direct conversation history
  direct\instance.json          content-free running-instance descriptor
  direct\instance.lock          cross-process launcher lock
  settings\settings.sqlite3     append-only versioned Direct settings profiles
  settings\model-token-policies.sqlite3
                                 append-only exact provider/model token overrides
  settings\provider-capability-policies.sqlite3
                                 versioned provider/model capability tiers
```

SQLite event and accounting databases contain bounded operational metadata, not prompts, candidate bytes, credentials, local input paths, or remote response bodies. Candidate files are create-once and referenced publicly by byte count and SHA-256 only. A transformed materialization cannot claim verbatim provenance.

Current schema versions are:

```text
runtime operational SQLite 7
observatory SQLite          2
accounting SQLite           3
Direct conversation schema  2
model-token policy schema   1
provider-capability schema  1
T1 manifest schema          2
Agent runtime schema        2
semantic schema             1
```

Runtime schema 7 adds a nullable provider-tier binding to queue members. Schema-6 rows migrate without rewrite and remain globally countable as `legacy_pre_tier`; schema-2 T1 members carry an exact binding digest. Existing batch-authority bodies, digest-only target claims and fenced target-path leases remain intact. v0.7.0a0 retains those tables for global `queue-status`, exact T1 staging, one-attempt workers, and explicit `reconciliation_required` resolution. The separate future `runtime\agent.sqlite3` hosts Agent lifecycle and semantic components only when an operator explicitly creates it; this feature did not create or migrate shared Agent state. Resolving an ambiguous member revokes the old batch; it never requeues or grants a replacement writer. Raw task bodies, answers and target paths remain absent from runtime/accounting databases.

Direct archive is reversible and changes no content bytes. Permanent Direct deletion is a separate operator-confirmed path requiring exact `DELETE`. It refuses conversations with an active run, overwrites and removes unmaterialized Candidate answer files, deletes Direct conversation/message/run rows with SQLite `secure_delete=ON`, and requires a successful WAL `TRUNCATE` checkpoint. Content-free invocation accounting, operational hashes, Candidate metadata, and a deletion tombstone remain for cost/audit continuity. MACR does not claim forensic erasure from SSD wear-leveling, filesystem snapshots, external backups, provider retention, or already materialized external artifacts.

Operational event payloads use required keys, reviewed field types, exact candidate-capture shape, and recursive key/value privacy guards. Acronym-bearing aliases and drive-relative/absolute or backslash/forward-UNC paths fail before persistence. WAL is configured during bounded bootstrap and verified on ordinary connections, avoiding concurrent journal-mode mutation during steady-state use.

## Legacy JSONL migration

The legacy JSONL file is immutable evidence. The current runtime does not append to it, truncate it, repair it in place, or delete it.

Inspect without writing:

```powershell
.\scripts\macr.ps1 migrate-ledger --dry-run
.\scripts\macr.ps1 migrate-ledger --dry-run --expected-count <N>
```

Copy-import after reviewing the counts and source hash:

```powershell
.\scripts\macr.ps1 migrate-ledger
.\scripts\macr.ps1 migrate-ledger --expected-count <N>
```

Every nonblank line is parsed with strict UTF-8, unique JSON keys, a timezone-aware timestamp, and a content-free event payload. Invalid UTF-8, malformed JSON, invalid shape, duplicate keys, forbidden content fields, duplicate original event IDs, or expected-count mismatch makes the source incomplete. Corrupt line bytes are stored in SQLite and copied byte-for-byte to `quarantine`; valid lines remain imported as provenance but cannot make the batch complete. Repeating an identical complete import changes zero rows.

When an append-only source grows and therefore receives a new file hash, the importer reconciles each valid line against prior imports using the original legacy event ID, event type, timestamp, and canonical original payload. Exact matches count as already imported and only new logical events are inserted. Reusing an existing legacy event ID with changed content fails the transaction. Reused event rows retain their first-import source provenance; each reviewed source snapshot has its own exact `legacy_sources` hash and count record.

When `ledger\events.jsonl` is nonempty and its current SHA-256 lacks a complete matching import record, `macr invoke` returns `legacy_migration_required` before reading the task, creating one-shot authority, acquiring a lease, dispatching, or contacting a provider. A corrupt import returns `legacy_migration_incomplete`; it never silently starts from empty history.

Before any live route, retire all legacy invocation entry points, confirm the GLM invoker census is zero, and set the preserved JSONL source to Windows read-only. Verify the attribute before taking the hash/count snapshot used for dry-run and copy-import:

```powershell
$legacyLedger = 'D:\AI_RESIDENCE\AI_Runtime\macr-state\ledger\events.jsonl'
$legacyItem = Get-Item -LiteralPath $legacyLedger
$legacyItem.IsReadOnly = $true
if (-not (Get-Item -LiteralPath $legacyLedger).IsReadOnly) {
    throw 'Legacy ledger seal was not applied.'
}
```

The read-only attribute prevents ordinary old append writers; it is not an ACL or cryptographic guarantee. Removing or bypassing it invalidates the route. Independently, any byte drift changes the source hash and causes the v0.5 migration gate to fail closed until the exact new source is reviewed and imported.

## Future volume migration procedure

1. Freeze writes and record source/destination volume identity.
2. Copy without deleting the source.
3. Produce SHA-256 manifests for both sides.
4. Compare manifests and run the complete offline suite.
5. Perform bounded live provider checks.
6. Retain the old root as rollback until explicit operator acceptance.

Never infer a destination from free space, drive order, model identity, or a familiar resident name.
