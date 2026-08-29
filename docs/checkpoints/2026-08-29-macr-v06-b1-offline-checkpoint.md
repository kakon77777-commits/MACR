# MACR v0.6 b1 Offline Checkpoint — 2026-08-29

## Exact subject

```text
branch   feature/macr-v0.6-dynamic-coordination
worktree D:\Ai\work together\MACR\.worktrees\macr-v0.6-dynamic-coordination
commit   a0dbd10ee9697a6bb5b71c1444be21ab41495656
tree     fd9086cad27585db162d92b15f9974864653d2a8
version  0.6.0a0
```

The implementation subject was clean after commit. It descends from the retained
v0.5.0a4 Direct Chat checkpoint and does not replace or relocate the separately
usable a4 Direct Chat worktree/shortcut.

## Implemented through this checkpoint

- canonical JSON, namespaced SHA-256 identifiers, and timezone-normalized timestamps;
- model subject, execution route, role, qualification-key, resident-separation, and host-session-separation invariants;
- configurable owner policy, manual Direct-context import, and scoped Context Capsules;
- append-only Observatory SQLite with create-once private raw snapshots and exact 32-process bootstrap/write control;
- capture-first discovery contracts and a read-only OpenRouter discovery source that cannot enter `ProviderRegistry` as an execution provider;
- immutable Model Passport projection with price history, route privacy history, evidence, decisions, invalidations, and explicit blind spots;
- versioned probe definitions, Wilson lower-bound qualification, route/role isolation, staleness, revocation, and negative controls;
- inspect-first reviewed GLM evidence import for three bounded worker roles without architecture-reviewer promotion;
- typed acyclic verifier graphs, canonical Coordination Plans, deterministic shadow planning, explicit exclusions, and revisioned fallback;
- proposal-only execution route resolution with exact provider model and endpoint matching;
- offline `model-observe`, `model-passport`, `plan-shadow`, `plan-show`, and `plan-diff` commands;
- T0 exact-plan-digest authority, one-attempt provider execution, private candidate capture, separate return/verification/acceptance states, and visible persistence failure;
- separate discovery/probe/production/verification/integration/human-correction cost classes plus a content-free future bill observation port.

## Verification evidence

```text
.\scripts\verify.ps1
Ran 403 tests
OK (skipped=2)
provider invoker census: 0
doctor version: 0.6.0a0
doctor network_activity: false
```

The two skips are the pre-existing Windows symbolic-link/reparse controls on a
host where test symlink creation is unavailable. `git diff --check` passed.

Additional exact synthetic controls include:

- Observatory fresh database: 32 synchronized processes, 32 successful unique evidence appends;
- runtime SQLite multiprocess controls retained for 1/2/3/4/8 writers;
- same model on a later catalog snapshot preserves the original first-seen lineage and appends history;
- identical planning snapshots produce byte-identical canonical plan JSON/digest independent of candidate input order and plan UUID;
- stale/incorrect plan authority refuses before provider invocation;
- provider-side persistence failure returns `unknown_after_dispatch` and never retries;
- warn-only accounting records warnings without changing candidate or acceptance state;
- bill metadata rejects prompt, answer, path, credential, invoice body, and remote body before write.

## State and authority boundary

- No MACR discovery adapter network call was made.
- No live Grok, GLM, Google, MiniMax, Ollama, or other provider call was made.
- Public OpenRouter documentation and its public models endpoint were consulted externally to review the adapter schema; this is research provenance, not a MACR runtime discovery execution.
- No real MSSP evidence package was imported; tests use synthetic reviewed fixtures under `tests/fixtures`.
- No shared D runtime migration, provider authority, plan promotion, or live T0 execution occurred.
- No merge, release, deployment, publication, automation, or acceptance occurred.
- All implementation writes and concurrency tests used the isolated worktree and D-drive test state.

Current schema versions:

```text
runtime operational SQLite 4 (unchanged)
observatory SQLite          2
accounting SQLite           2
```

## NotMeasured and remaining gates

- The OpenRouter API adapter captures canonical bytes reconstructed from decoded JSON, not exact HTTP wire bytes.
- The reviewed OpenRouter fixture is a three-record public subset, not a full live-catalog acceptance replay.
- Endpoint-specific training, retention, ZDR, region, and caching policies remain unknown-conservative unless separately snapshotted.
- Raw Observatory snapshots are create-once but not encrypted.
- Passport cache invalidation remains explicit; authoritative evidence stays append-only.
- Reviewed GLM import is synthetic at this checkpoint and cannot promote `architecture_reviewer`.
- T0 verifier tests use an injected deterministic verifier; no general OS/tool executor is accepted.
- Cross-database runtime/accounting/observatory atomicity is not claimed; failures are made visible and retry is not inferred.
- No real plan has been promoted to `execution_eligible` or exercised against a paid/local provider.
- T1 durable queue, exact ordered batch authority, aggregate admission, target collision controls, and bounded live fan-out are not implemented.
- T2/T3 coordinator and cross-file integration paths, plus rc1 cross-model differential qualification, remain pending.

The next implementation subject begins at Task 16: durable T1 queue and exact
batch authority. It requires fresh synthetic multiprocess replay before any
bounded live fan-out can be proposed.
