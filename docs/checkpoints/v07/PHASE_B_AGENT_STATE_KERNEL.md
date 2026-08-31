# MACR v0.7 Phase B Checkpoint — Agent State Kernel

Status: implemented and offline-validated; Phase C not started

Date: 2026-08-31

## Exact subject

```text
base Phase A commit        05345d7a474f2cf05023ab4e50e18bae42293ee3
branch                     workbench/v0.7-agent-state-kernel
source-frozen commit       d378cc951f107418c9f27e3b8de2d1f90e5975d4
source-frozen tree         6ccef8fb1a867d45200323d9b8da1818d73a7f95
package version            0.6.0a1 (intentionally unchanged)
Agent database schema      1
shared Agent DB created    false
network activity           false
provider generation        false
Phase C started            false
```

The source-frozen subject is the final implementation and verification-gate
commit before this checkpoint document. The checkpoint commit is verified
separately after creation so the document does not make a self-referential hash
claim.

## Scope delivered

Phase B implements a pure single-machine, cross-process AgentRun State Kernel:

- immutable AgentRun projection with occurrence identity separate from subject
  identity;
- exact initial creation guard: CREATED/revision 1/epoch 0;
- deterministic Phase B lifecycle transitions with no generic state setter;
- a dedicated D-drive-only `AgentDatabase` schema v1;
- append-only, typed, content-free Agent state events;
- atomic event, projection, binding-index, ownership, epoch, and fencing writes;
- strict revision and epoch compare-and-swap;
- one active owner per AgentRun, expiring leases, and never-reused fencing tokens;
- same-owner acquire idempotence, monotonic lease renewal, and explicit release;
- host/runtime-facing create, admit, acquire, activate, block, reactivate,
  complete, fail, cancel, inspect, list, and rebuild operations;
- read-only projection inspection and explicit event-derived reconstruction;
- event-derived parent/child lineage that survives parent projection rebuild;
- bounded cursor reads and stable sanitized error codes.

This is not an autonomous Agent loop. It contains no provider dispatch, Agent
planner, runner, scheduler, checkpoint engine, wake evaluator, semantic store,
Direct Chat change, or Phase C behavior.

## Source boundary

New Agent kernel modules:

```text
src/macr_runtime/agent/database.py
src/macr_runtime/agent/errors.py
src/macr_runtime/agent/events.py
src/macr_runtime/agent/lifecycle.py
src/macr_runtime/agent/ownership.py
src/macr_runtime/agent/service.py
src/macr_runtime/agent/state.py
src/macr_runtime/agent/store.py
```

Integration changes:

```text
src/macr_runtime/agent/__init__.py
src/macr_runtime/storage.py
src/macr_runtime/__init__.py
```

The root package now resolves its existing public exports lazily. This preserves
normal root API object identity while allowing `macr_runtime.agent` to load under
`python -S` without initializing provider runtime or optional media dependencies.

Verification and reconstruction:

```text
scripts/agent-kernel-replay-smoke.py
scripts/verify-v07-phase-b.ps1
scripts/verify-v07-phase-a.ps1
tests/gates/v07_phase_b_contract_manifest.json
tests/gates/v07_phase_b_architecture_manifest.json
```

The Phase A wrapper now derives `phase_b_started` from the actual Phase B manifest
instead of reporting a hard-coded false value.

## Database boundary

The default future path is:

```text
D:\AI_RESIDENCE\AI_Runtime\macr-state\runtime\agent.sqlite3
```

No shared database was opened or created for this checkpoint. All database tests
used unique children of D-drive `MACR_TEST_TMP`.

Schema v1 tables:

```text
schema_meta
agent_runs
agent_events
agent_goals
agent_world_bindings
agent_memory_bindings
agent_plan_bindings
agent_children
agent_ownership
agent_fencing_counter
```

The database uses WAL, `foreign_keys=ON`, `synchronous=FULL`, a 30-second SQLite
busy timeout, and `BEGIN IMMEDIATE` for canonical mutations. Thirty-two
synchronized fresh bootstrap processes produced one valid schema subject.

`agent_events` is independent of the rebuildable projection. `agent_children` is
an immutable lineage index derived from child creation events; it does not
cascade with a parent projection. Store-level creation still requires an existing
parent and exact delegation relation.

## Lifecycle and ownership evidence

The Phase B service exposes no caller-selected target-state method. Supported
transitions are the exact approved subset across CREATED, ADMITTED, ACTIVE,
BLOCKED, COMPLETED, FAILED, and CANCELLED. Terminal states never reopen.

Every canonical mutation increments revision by exactly one. Every new ownership
acquisition increments both epoch and revision, appends `agent.owner_acquired`,
updates the projection, allocates a persistent fencing token, and inserts the
lease in one transaction.

Observed controls include:

- eight synchronized distinct owners produced one permit, one owner event, one
  epoch/revision advance, and one fencing token;
- seven losing owners produced no state, event, lease, epoch, revision, or token
  drift;
- release followed by another eight-owner contest produced exactly one new
  owner, a larger token, and one new epoch;
- an old process could not mutate after ownership changed;
- process exit code 73 immediately after event insert but before commit left all
  canonical tables unchanged;
- same-owner unexpired acquisition was idempotent;
- expired renewal failed;
- a renewal proposing an earlier or equal expiry failed without any drift;
- terminal completion/failure/cancellation removed ownership atomically.

## Replay and reconstruction evidence

Replay validates event identity, exact revision continuity, epoch policy,
payload digest, state digest, legal lifecycle transition, immutable creation
header, binding indexes, parent/child lineage, and terminal closure.

Negative controls include:

```text
event gap
duplicate event
payload digest tamper
state digest tamper
projection tamper
binding tamper with unchanged row count
immutable-header tamper
terminal continuation
active-lease rebuild
missing child lineage
same-count tampered child delegation
```

Reads never auto-repair. Explicit rebuild first replays in memory, refuses active
leases or invalid evidence, then replaces projection/index state in one
transaction without editing historical events.

A parent projection deletion/rebuild preserved or reconstructed its outgoing
child relation from the child's retained creation event. Missing and tampered
lineage both produced conflict; explicit rebuild restored only the event-derived
canonical relation.

## Source-frozen Phase B gate

```text
command                  .\scripts\verify-v07-phase-b.ps1
exit                     0
focused tests            75 passed
required manifest IDs    69 unique IDs / 69 unique test bindings
Agent schema version     1
bootstrap processes      32
ownership contenders     8
hard-exit subject        73
fresh package replay     true
final state              completed
final revision / epoch   7 / 1
event count              7
state digest             558ef9cb05f10aec7d41b5cac569ea101adb2528e72be484cc1cf359861b34b4
replay digest            8cc4c56f11c0a0e9d3e4b6c166b147811f9ae67e6d6757bfc8856f2b7f6f4356
wheel SHA-256            f09f31ba4f458a3fa0d4ca6653a0ffcf0507b8b12b5060b70375573733f4a50a
network activity         false
provider generation      false
git clean                true
Phase C started          false
```

The wheel was built with temporary directories and pip cache on D:, installed
with `--no-deps` into a new D-drive target, and executed from outside the
repository under `python -S`. The deterministic seven-event sequence was:

```text
create -> admit -> acquire -> activate -> block -> activate -> complete
```

The smoke then deleted the disposable projection, rebuilt only from events, and
required canonical public projection bytes, state digest, terminal
state/revision/epoch, event identities/count, and terminal ownership absence to
remain equivalent.

## Inherited gates

Independent Phase A compatibility result on the same source-frozen subject:

```text
command                  .\scripts\verify-v07-phase-a.ps1
exit                     0
Phase A focused tests    91 passed
Phase A required IDs     68
inherited tests          648; OK; 2 existing Windows symlink skips
network activity         false
provider generation      false
git clean                true
phase_b_started          true
```

Independent complete v0.6 result:

```text
command                  .\scripts\verify-v06.ps1
exit                     0
complete tests           648; OK; 2 existing Windows symlink skips
targeted tests           127 passed
summary digest           8180290efc8acfe5275a040175fd0a6ab7b7e6817f02c79544818ae103cca345
schema fingerprint       43ca1e5e8cc0f75b4ac5de1821ce2f8b2d7d5632e7ad0a151910543dc396c0b5
network activity         false
provider generation      false
git clean                true
```

## MSSP Twin governance record

One task-local read-only Governing Twin was used; no fan-out occurred. Twin
concurrence is scoped evidence review, not acceptance or world-effect authority.

Retained challenges and resolutions:

1. **Creation-time snapshot confusion.** Phase A accepts general AgentRun
   snapshots, so Phase B added a pre-SQL exact CREATED/1/0 guard plus three
   independent zero-mutation mismatch controls and one exact `0 -> 1` creation
   witness. Targeted reevaluation: `CONCUR` for this scope.
2. **Lease shortening.** `now + ttl` could shorten a valid lease. Renewal now
   requires strictly later expiry inside the transaction; the negative control
   proves no ownership/projection/event drift. Targeted reevaluation: `CONCUR`.
3. **Outgoing child lineage loss.** Parent projection cascade could delete
   lineage the parent header could not reconstruct. Lineage is now child-event
   derived, inspected in both directions, and explicitly rebuilt. Targeted
   reevaluation: `CONCUR`.

The final Twin outcome on source-frozen `d378cc9` / tree `6ccef8f` was `CONCUR`
for Phase B behavioral, structural, and discriminative offline closure only. It
did not authorize release, deployment, shared-runtime activation, or live use.

## Retained RED and harness corrections

- The first direct unittest command omitted `PYTHONPATH=src`; that collection
  failure was discarded and rerun to the intended missing-module RED.
- An invalid test raw string prevented collection; it was corrected before the
  valid missing-store RED.
- Three ownership tests initially reached intended error branches but exposed two
  missing error imports; imports were corrected without changing semantics.
- The first fresh wheel replay failed under `python -S` because eager root package
  imports pulled provider runtime and Pillow. Installing Pillow would have hidden
  the dependency; the root export map was made lazy and all legacy exports were
  checked for compatibility.
- A direct recursive cleanup command for two manually created D-drive structural
  subjects was rejected by host safety policy. No bypass was attempted. The
  complete wrapper later created and safely cleaned its own fresh subject.

The two retained manual inspection subjects are under D-drive test state with
names beginning `phase-b-structural-ec14e0d...` and
`phase-b-structural-cf0d109...`. They contain no provider credentials or shared
runtime state and may be removed later through an authorized cleanup route.

## Three closure claims

### Behavioral closure — PASS

The scoped pure State Kernel behavior is executable through named host/runtime
operations, survives process and transaction failures in the tested boundary,
and passes focused plus inherited suites.

### Structural closure — PASS

The declared module graph and fresh installed-wheel subject reconstruct the
scoped behavior without source-tree imports, provider modules, optional media
dependencies, shared state, credentials, or dirty residue. Projection and child
lineage are reconstructible from retained events under the declared equivalence.

### Discriminative closure — PASS

Sixty-nine unique required witnesses exercise authorized equivalents and the
relevant bad states for initial creation, lifecycle, database, events, store,
service, ownership, rebuild, multiprocess, privacy, packaging, and architecture.
The validators reject named faults without rejecting the paired controls.

These PASS claims are limited to the Phase B offline scope. They are not global
proofs of the later v0.7 architecture.

## NotMeasured and deferred

- NotMeasured: shared default Agent database creation, migration, backup,
  restoration, encryption, or operator adoption;
- NotMeasured: real Agent planner, runner, scheduler, checkpoint, suspend, wake,
  resume, reconciliation workflow, observation, semantic state, or action loop;
- NotMeasured: Grok, Qwythos/Ollama, GLM, Google, MiniMax, Codex, Claude Code, or
  any other provider/model integration, latency, billing, quality, retention, or
  live authority;
- NotMeasured: cross-machine consensus/fencing, distributed leader election,
  operating-system or storage-device loss, Byzantine behavior, or multi-tenant
  production security;
- NotMeasured: CLI/UI Agent controls, Interaction Plane integration, production
  performance, long-duration lease behavior, or clock-skew tolerance;
- NotMeasured: merge, tag, release, deployment, publication, shared-runtime
  activation, or GitHub update of this branch.

No credential was read, no provider was called, no shared runtime was migrated,
and no live AgentRun was created while producing this checkpoint.

## Verdict and stop boundary

```text
Phase A                 IMPLEMENTED / OFFLINE VALIDATED
Phase B behavioral      PASS
Phase B structural      PASS
Phase B discriminative  PASS
Phase C                 NOT STARTED
Agent loop              NOT IMPLEMENTED
Live use                NOT MEASURED
```

The Phase B stop is active. Work must not continue into Phase C without a
separate operator direction and approved design.
