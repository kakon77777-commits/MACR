# MACR v0.5.0a1 Shared Core — Checkpoint A candidate

Status: local review candidate; not merged, released, deployed, or published externally.

Date: 2026-08-27

## Revision boundary

The implementation revision captured before version and documentation edits is:

```text
implementation_commit = 89becf2cce5fcb3ff18f379bbb7bae8de9dbe6f2
implementation_tree   = e6ed4ed624a18bea000cf140148c9bce903c4767
```

Both values are literal 40-character lowercase Git object IDs returned by:

```powershell
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
```

The final documentation commit cannot self-record its own commit ID. The exact candidate commit and tree must therefore be supplied in the review handoff and recomputed by each reviewer.

The governing repository artifacts are:

| Artifact | Commit | Bytes | SHA-256 |
|---|---|---:|---|
| `docs/superpowers/specs/2026-08-27-macr-v0.5-direct-chat-design.md` | `7de92c2` | 32,493 | `EED4BDF417EDE5A989A40DE4597FD92BC6B536A00EF5ACA9FA8A4C69795A66AF` |
| `docs/superpowers/plans/2026-08-27-macr-v0.5-checkpoint-a-shared-core.md` | `58ece24` | 76,117 | `46EDBEA195D637AF2AC96583D01FCE2EDD9FF88E6A97ECEC095695E68FCDDC25` |

## Observable contract

- `runtime\dispatch.sqlite3` is the operational authority for runs, content-free events, authorization epochs and records, fenced leases, legacy-import provenance, quarantine rows, and candidate metadata.
- `accounting\accounting.sqlite3` stores dispatch/observation/terminal accounting and a local outbox. An unknown post-dispatch charge remains `unknown_after_dispatch`; it is never coerced to zero.
- `ledger\events.jsonl` is immutable legacy source evidence. The v0.5 runtime writes no new JSONL events.
- A nonempty legacy source requires a complete record for its current SHA-256 before `invoke` may read a task, create one-shot authority, acquire a lease, dispatch, or use a provider.
- Origin, authorization provenance, and lease ownership are independent. Admission verifies an exact current-epoch authority before and after acquiring a fenced lease.
- GLM constructs a safe `RawProviderObservation` before response validation. Non-stop and malformed candidates retain safe finish/model/token/cost/duration fields and private answer bytes without retry.
- Existing non-GLM adapters remain callable through a compatibility observation derived from normalized `ProviderResult`; they are not claimed to expose pre-validation raw provider responses.
- Candidate bytes are immutable private files. Event and accounting databases contain hashes/counts only, not candidate text or bytes.
- Provider completion, capture, return-contract validity, materialization, verification, and acceptance are separate states. Checkpoint A implements no verifier decision or acceptance transition.
- Structured task contradictions fail before provider/key/network/event use. Structured return contracts compile provider instructions and validate candidates independently of provider completion.
- Accounting records `soft_warning` separately from the existing task/provider hard budget gates. Existing provider task-budget behavior remains active; the operator-managed warn-only profile is deferred to the Direct/settings checkpoint.

## Schema versions

| Database | Component | Version | Durability policy |
|---|---|---:|---|
| `runtime\dispatch.sqlite3` | runtime | 4 | SQLite WAL, `synchronous=FULL`, foreign keys, 30-second busy timeout |
| `accounting\accounting.sqlite3` | accounting | 1 | SQLite WAL, `synchronous=FULL`, foreign keys, 30-second busy timeout |

## Offline verification evidence

The post-version documentation gate ran:

```powershell
.\scripts\verify.ps1
```

Observed result:

```text
Ran 244 tests in 13.878s
OK (skipped=2)
process census count = 0
doctor version = 0.5.0a1
doctor network_activity = false
```

The two skips are the Windows symbolic-link capability controls in Candidate Vault and GLM fixed-key custody. Their ordinary-path controls passed; no symlink claim is made on this host.

The dedicated concurrency gate also ran:

```powershell
python -m unittest tests.test_multiprocess_runtime -v
```

It completed five tests successfully. SQLite standalone-event writers produced exact and distinct event counts for 1, 2, 3, 4, and 8 processes at 60 events each: 60, 120, 180, 240, and 480. Two processes contending for one provider resource produced exactly one admitted mock transport marker and one typed `DispatchLeaseError` refusal. A forced two-process interleaving of the historical JSON/newline writer produced an incomplete corrupt fixture, demonstrating the old failure shape without asserting a scheduler-dependent loss percentage.

Process-census controls observed:

```text
self-only command containing invoker text = 0
one harmless exact-pattern PowerShell process = 1
same exact PID after termination = 0
```

The census excludes its own `$PID` before matching, recognizes only the documented GLM invoker command shapes, and returns PIDs without command lines.

## Synthetic migration evidence

The offline suite verified all of the following against D-drive temporary state:

- dry-run reports source hash/counts and creates neither runtime DB nor quarantine;
- exact two-event import preserves source bytes;
- the second identical import writes zero rows and reports two already-imported events;
- a corrupt one-line source is retained byte-for-byte in quarantine and reports `legacy_migration_incomplete`;
- an unmigrated nonempty source blocks invocation before task-file access and leaves authority, lease, and event row counts at zero.

No real operator ledger was migrated by this checkpoint task. Migration of the current shared D-state source remains an explicit operator action after reviewing `migrate-ledger --dry-run` output and any external expected count.

## Known blind spots

- No paid, local-model, or other live provider call was made for Checkpoint A. Offline configuration health is not reachability or billing entitlement.
- Direct Chat, its local browser service, conversation/settings databases, Codex and Claude Code host adapters, bounded fan-out, Context Capsules, and GLM Direct Chat are absent.
- Runtime and accounting use separate SQLite databases; there is no single cross-database transaction. The pipeline records accounting terminal state before the terminal event so a persistence failure leaves the runtime run visibly dispatched/unsettled rather than silently complete. Reconciliation of such a split state remains operator work.
- Leases have bounded TTL but no in-flight renewal loop in this checkpoint. Workspace-writing tasks use a conservative repository-wide collision key; no target-path parallel materializer is implemented.
- The census recognizes the supported CLI invoker forms, not every possible custom provider client.
- Candidate Vault stores raw bytes without encryption in this checkpoint, per operator choice. D-drive access control remains the local security boundary.
- Legacy valid lines may be preserved even when another line makes the source incomplete. The invocation gate still refuses that source until a complete current-hash record exists.
- Accounting outbox rows are local only; the future AI accounting system and bill-ingestion interface are reserved, not connected.
- Provider retention, training, privacy, quota, pricing, and billing policies remain provider-controlled external facts. `store=false` or local MACR policy is not proof of provider-side deletion.

## MSSP fresh replay instructions

Each architect should work from the exact candidate commit supplied in the handoff, record both `git rev-parse HEAD` and `git rev-parse 'HEAD^{tree}'`, and confirm the worktree is clean before testing.

Run only offline gates first:

```powershell
.\scripts\verify.ps1
python -m unittest tests.test_multiprocess_runtime -v
git diff --check
```

Then independently attack at least:

1. 1/2/3/4/8-process event counts and distinct IDs;
2. same-resource two-process admission and exact transport-marker count;
3. authority stop/reopen epoch invalidation before lease/network;
4. GLM synthetic `length`, malformed usage, tool, web-search, and returned-model mismatch observation preservation;
5. byte-identical candidate readback and transformed-versus-verbatim provenance;
6. exact-text/plain-source/JSON return-contract positive and negative controls;
7. legacy dry-run, exact import, idempotent replay, corrupt-line quarantine, and invocation gate;
8. self-only/real-invoker/terminated-invoker census controls;
9. prompt, answer, key, path, and remote-body absence from event/accounting databases.

Do not perform a live provider call, merge, release, deploy, publish, or begin Checkpoint B during this replay. Return version-bound evidence and distinguish observation, verification, acceptance, and implementation authority.
