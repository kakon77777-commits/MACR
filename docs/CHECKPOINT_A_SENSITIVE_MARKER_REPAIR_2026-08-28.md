# MACR v0.5.0a3 — sensitive-marker repair checkpoint

Status: local offline candidate; not merged, released, deployed, live-accepted, or authorized for provider invocation.

## Exact implementation boundary

```text
implementation_commit = 4a54acbdd405ee955346f112a1a45e3798850841
implementation_tree   = 22d4549090fbfcfbdbaba036391a928f5cf8b785
parent_candidate      = 8697e25fa8541a89aa2f39b294a733cf15c79bcd
```

The earlier live route bound to the clean parent candidate closed as soon as this repair worktree changed. No approval, migration, provider call, or shared-runtime write was performed by this repair.

## Defect and repair boundary

The former case-insensitive pattern treated every `letter + colon + slash` sequence as an obvious Windows path. It therefore matched the final `s:/` inside HTTPS schemes and mathematical variable/control-sequence pairs such as `s:\delta`, `B:\neg`, `D:\quad`, and `D:\text`.

v0.5.0a3 keeps this as an intentionally conservative obvious-marker heuristic rather than claiming general semantic classification:

- credential and private-key markers are checked independently;
- UNC candidates require an evident server and share component;
- drive candidates require a left boundary that excludes URI-scheme letters;
- a closed set of observed LaTeX control words is treated as ambiguous rather than obviously path-shaped;
- a recognized LaTeX word followed by path-like continuation, for example `D:\text\secret.txt`, is still rejected;
- unrecognized `X:\word`, forward-slash drive paths, file URLs, UNC paths, and escaped UNC representations remain rejected.

The closed set is not a LaTeX parser and must not be generalized into stripping formulas before scanning.

## TDD evidence

The clean parent baseline ran 250 tests with zero failures and two existing Windows symlink skips.

RED observations reproduced before production changes:

1. HTTPS and six single-backslash LaTeX controls all raised `obvious sensitive marker`.
2. Double-backslash mathematical source remained rejected through the UNC branch.
3. The first ambiguity rule incorrectly allowed real continuations `D:\text\secret.txt` and `D:\delta_u\secret.txt` to reach the approval-digest gate.
4. The version test expected `0.5.0a3` while both package sources still reported `0.5.0a2`.

Each RED was followed by one bounded production change and a targeted GREEN run. Credential-shaped inputs, actual drive paths, lowercase drive paths, forward-slash drive paths, file URLs, UNC, escaped UNC, LaTeX in goals, and LaTeX in text inputs have direct behavioral controls.

## Offline gate

The full gate immediately before the implementation commit reported:

```text
scripts/verify.ps1       exit 0
unittest                 252 run / 250 pass / 2 skip
doctor                   version 0.5.0a3 / network_activity false
invoker census           0
secret scan              clean
git diff --check         exit 0
```

An earlier full-gate run had the same 252 unit tests green but correctly failed the repository secret scan because the test source contained literal PEM header controls. The test now constructs those exact runtime values from non-secret fragments; the behavior remains exercised without committing credential-shaped material.

## Evidence inputs and blind spots

| Evidence | Bytes | SHA-256 |
|---|---:|---|
| `RUN-033-HARD-ZETA-AU2D5-ANNULAR-RESIDUE.md` | 11,301 | `C949E205010F7AC18F3A12A86446EC434F449803C36A46899D40DC2AA3155EAD` |
| `hardzeta-corpus-manifest.json` | 45,577 | `2CF0874C82A584457B3458742EA4B54BED8092714384AEB63F17496974403589` |
| `2026-08-28-pragma-macr-route-drift-after-t6.md` | 2,284 | `6C0FE0A103601CBFA7371A68E04DB541E020930B3B23917832B27D73F78246B7` |
| `2026-08-28-pragma-post-migration-legacy-tail.md` | 3,145 | `3A91A0586253E533D213D9C1768B5778281DB17B2890550248130BE4F0CF8CF3` |

The manifest declares 132 distinct documents, but none of its exact document hashes could be resolved from currently searchable D-drive files. This checkpoint therefore does **not** claim a fresh 132/132 corpus replay. That replay remains an independent external acceptance subject.

Ambiguity is deliberate: a bare real directory whose complete text is exactly a listed LaTeX word may not count as an *obvious* path until further path-like continuation appears. Semantic sensitivity classification and exact task approval remain operator responsibilities.

## Post-migration legacy tail

Read-only inspection after the implementation commit found that four legacy v0.4 events had been appended after the earlier 64-event migration:

```text
current legacy source
  bytes                 37975
  sha256                E2AE623F983B34575F6D73DE153A47B37841DE1346A8531EAF9C115252E81BEE
  parsed/distinct       68 / 68

runtime SQLite
  event rows            66
  complete legacy row   old SHA 28BF... / 64 only
  current-hash row      absent
```

No actor is attributed from timing. The correct current behavior is fail-closed: the new legacy hash has no complete migration record, so a v0.5 invocation must stop before task access, authority, lease, or provider contact.

The future operator reconciliation sequence is exact and is **not** performed by this checkpoint:

1. Retire every v0.4 invocation route and confirm the exact GLM invoker census is zero.
2. Set `ledger\events.jsonl` to Windows read-only and verify the attribute before taking the authoritative hash/count snapshot. This prevents ordinary legacy append writers during reconciliation and later v0.5 route use.
3. Run `migrate-ledger --dry-run --expected-count 68`; require the exact current SHA, 68 valid, zero corrupt, zero duplicate, complete, and no writes.
4. Run `migrate-ledger --expected-count 68`; the idempotent expectation is 64 already-imported legacy IDs and four newly imported IDs. Existing native v0.5 events remain separate.
5. Repeat the identical import; require zero newly imported IDs, 68 already imported, unchanged event count, and a complete current-hash source record.
6. Use only scripts from a newly authorized exact clean v0.5 checkpoint. Keep the legacy file read-only. Any later byte drift changes the source hash and re-closes the invocation gate.

Read-only file metadata is a reversible operational seal, not an ACL or cryptographic immutability proof. Removing the attribute or using an administrative bypass violates the route; the current-hash migration gate remains the independent detection control.

## Route statement

`offline-only` until a fresh independent replay binds a clean checkpoint commit/tree, the 68-event legacy source is sealed and reconciled as above under explicit operator authority, and the MACR owner issues a new live route. No authority carries forward from v0.5.0a2 or its parent route.
