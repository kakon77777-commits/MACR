# MACR v0.7 Phase B Agent State Kernel Implementation Plan

Status: implementation plan under MSSP × TDD × APR Twin governance

Date: 2026-08-31

## Exact project world

```text
repository             D:\Ai\work together\MACR
branch                 workbench/v0.7-agent-state-kernel
operator-approved design commit 175da21a7612eecf48cb0dcc5e97472d7e7b0b32
operator-approved design tree   c43089c0837a9f5613c0ac71dfe893ccaa9c3d41
creation-guard design commit     382fa56e4cd075c0c88bba46c1f82f64b8cd7a08
creation-guard design tree       10cae90d2129f9dc0ba39f016f45ad83f5535145
base Phase A commit    05345d7a474f2cf05023ab4e50e18bae42293ee3
package version        0.6.0a1 (unchanged)
runtime state default  D:\AI_RESIDENCE\AI_Runtime\macr-state
```

Canonical design:

```text
docs/superpowers/specs/2026-08-31-macr-v07-phase-b-agent-state-kernel-design.md
```

Canonical upstream requirements:

```text
docs/macr-v0.7/MACR v0.7 — AgentRun Canonical State Specification v0.1.md
docs/macr-v0.7/MACR v0.7 — Single-Agent MVP Implementation Plan & Verification Matrix v0.1.md
docs/macr-v0.7/MACR v0.7 — Verification & Negative-Control Matrix v0.1.md
docs/checkpoints/v07/PHASE_A_AGENT_CONTRACT_KERNEL.md
```

The private `docs/macr-v0.7/future` area is excluded and must not be inspected.
ISQL Origin is excluded. No provider credential, provider transport, Direct Chat
state, or shared Agent database is required.

## MSSP governance

This plan uses one event-local Lead and one task-local Governing Twin. The Twin is
read-only unless the operator separately changes authority. It may return `IDLE`,
`CONCUR`, `CHALLENGE`, or a targeted evidence request. It is not a duplicate
implementer, final authority, resident identity, or permission source. No fan-out
or third context is authorized.

Canonical state shared with the Twin is limited to target, exact commit/tree,
approved scope, relevant artifacts, evidence, unresolved claims, closure vector,
and next decision. Full conversation history and private data are not shared.

Twin reevaluation events:

1. implementation plan closure candidate;
2. event/projection atomic core becomes green;
3. ownership, replay, and fresh-package reconstruction become green;
4. final Phase B checkpoint candidate.

The Twin may remain `IDLE` when another observation has no positive expected
value. A challenge must identify the claim, evidence gap, affected scope, minimal
requested action, and authority basis. The Lead owns source edits and integration.

### Retained plan-stage Twin challenge

The first Twin review challenged creation-time closure: Phase A deliberately
allows `AgentRunHeader` to represent a general snapshot, while Phase B creation is
restricted to CREATED/revision 1/epoch 0. The plan resolves this without changing
Phase A by requiring a pre-SQL Phase B creation guard, three independent mismatch
controls with zero writes across all Phase B tables, and one exact
`before_revision=0 -> after_revision=1` positive witness. The challenge remains in
the record as resolved design input; it is not rewritten as initial agreement.

## Target and authority

Authorized target:

```text
Implement and offline-validate the pure Phase B AgentRun State Kernel.
```

Authorized effects:

- source, tests, scripts, plan, and checkpoint changes on the Phase B branch;
- disposable D-drive test databases and wheel/install targets;
- local commits needed to preserve TDD slices and evidence.

Not authorized by this plan:

- provider calls, credential reads, network generation, shared Agent DB creation,
  migration, merge, push, tag, release, deployment, publication, or Phase C work;
- Direct Chat, dispatch, accounting, observatory, Candidate Vault, or provider
  behavior changes;
- package version promotion to `0.7.0a1`.

## Closure vector

### Behavioral closure

The named API creates, admits, owns, activates, blocks, reactivates, terminates,
reads, lists, inspects, and rebuilds a Phase B AgentRun according to the approved
state and ownership semantics. All focused and inherited executable tests pass.

### Structural closure

The target behavior is reconstructible from the declared support set without
dirty worktree residue, source-tree imports, shared state, credentials, or hidden
provider support. A wheel installed into a fresh D-drive target must execute a
complete state/rebuild replay from outside the repository source path.

Structural equivalence is predeclared as:

```text
same canonical public AgentRun projection bytes
same state_digest
same terminal state/revision/epoch
same validated event chain length and event identities
no live ownership after terminal completion
```

### Discriminative closure

The validator rejects the relevant bad state for its intended reason while
accepting the authorized equivalent. Every S0/S1 negative family has a nearby
green control, including stale/current revision, stale/current epoch, stale/current
fencing token, forbidden/safe metadata, illegal/legal transition, broken/intact
event chain, terminal reopen/new occurrence, and competing/same-owner acquisition.

## Minimal sufficient support backtrace

```text
AgentStateRecoverable
  <- typed event chain
  <- deterministic replay reducer
  <- immutable creation header and binding indexes
  <- explicit projection inspection and repair
  <- fresh installed-wheel replay

RevisionFenced
  <- state_revision in projection
  <- before/after revision in every event
  <- SQL expected-revision compare-and-swap
  <- unique run/revision event constraint

OwnershipFenced
  <- one lease row per AgentRun
  <- never-reused fencing counter
  <- epoch advance on each new acquisition
  <- exact permit validation in every owned mutation
  <- synchronized multiprocess contention control

ContentFree
  <- exact event payload schemas
  <- recursive forbidden-key/path/bytes checks
  <- bounded public read models
  <- raw database and wrapper-output scans
```

Implementation may depend on Python standard library and these existing MACR
primitives only:

```text
macr_runtime._v07_contracts
macr_runtime.canonical
macr_runtime.execution
macr_runtime.storage
macr_runtime.errors
macr_runtime.agent.contracts
```

Direct/provider/planner/scheduler/runtime invocation imports are forbidden in the
new Agent kernel. Existing v0.6 SQLite and lease modules are reference patterns,
not runtime dependencies of the new database.

## TDD rule

For every executable slice:

1. add the smallest focused positive and falsifying witness;
2. run the exact focused command and observe RED for the intended missing behavior;
3. implement only the named slice;
4. rerun focused tests to GREEN;
5. run the nearest inherited boundary tests;
6. run `git diff --check`;
7. commit the green slice with its tests.

A test that is red because of an import, fixture, or harness defect is not product
evidence. Fix the harness, rerun RED for the intended claim, then implement.

No test may call a provider or use the shared Agent database. Fault injection is
local, deterministic, and transaction-bound. No automatic retry is added merely
to make a test green.

---

## Task 1 — Projection, lifecycle, and typed errors

**Create:**

```text
src/macr_runtime/agent/errors.py
src/macr_runtime/agent/state.py
src/macr_runtime/agent/lifecycle.py
tests/test_agent_state.py
tests/test_agent_lifecycle.py
```

### RED

Tests first define:

- immutable `AgentRunProjection` constructed from a Phase A `AgentRunHeader`;
- exact initial CREATED/revision 1/epoch 0 projection;
- a distinct `from_creation_header` guard rejects a Phase-A-valid non-CREATED
  state, revision other than 1, or epoch other than 0;
- canonical `state_digest` excluding `updated_at`;
- timestamp-only differences preserve state digest;
- public round trip is closed and content-free;
- exact Phase B transition table;
- legal and illegal transition controls;
- terminal states never reopen;
- stable typed public error codes.

Run:

```powershell
python -m unittest tests.test_agent_state tests.test_agent_lifecycle -v
```

Expected RED: the Phase B state/lifecycle modules do not exist.

### GREEN

Implement:

- `AgentRunProjection` with strict validation and public serialization;
- state digest namespace `macr.agent.projection.v1`;
- one immutable lifecycle transition mapping;
- `require_transition(before, after)` with no generic mutation side effect;
- typed errors rooted in `MacrError`, with stable codes from the approved spec.

Do not add persistence or service behavior yet.

Run:

```powershell
python -m unittest tests.test_agent_state tests.test_agent_lifecycle tests.test_agent_contracts -v
git diff --check
```

Commit:

```powershell
git add src/macr_runtime/agent/errors.py src/macr_runtime/agent/state.py src/macr_runtime/agent/lifecycle.py tests/test_agent_state.py tests/test_agent_lifecycle.py
git commit -m "feat(agent): add Phase B state and lifecycle kernel"
```

---

## Task 2 — Dedicated AgentDatabase schema and D-drive boundary

**Create/modify:**

```text
src/macr_runtime/agent/database.py
src/macr_runtime/storage.py
tests/test_agent_database.py
tests/test_storage.py
```

### RED

Tests require:

- relative and non-D paths fail before directory/file creation;
- `StorageLayout.agent_db_path` resolves to `runtime/agent.sqlite3`;
- fresh schema version 1 has the exact nine Phase B tables and constraints;
- WAL, `foreign_keys=ON`, `synchronous=FULL`, and busy timeout are effective;
- a newer/invalid schema version fails closed;
- synchronized fresh bootstrap follows the already-proven 32-process v0.6 control;
- Direct, dispatch, accounting, observatory, and settings databases are untouched.

Run:

```powershell
python -m unittest tests.test_agent_database tests.test_storage -v
```

Expected RED: AgentDatabase and `agent_db_path` are absent.

### GREEN

Implement a separate `AgentDatabase` with:

- D-drive validation before mutation;
- bounded retry only around transient WAL bootstrap locks;
- schema version 1 and exact tables from the design;
- `BEGIN IMMEDIATE` mutation connections;
- no automatic opening of the shared default database during import or doctor.

Run:

```powershell
python -m unittest tests.test_agent_database tests.test_storage tests.test_multiprocess_runtime -v
git diff --check
```

Commit:

```powershell
git add src/macr_runtime/agent/database.py src/macr_runtime/storage.py tests/test_agent_database.py tests/test_storage.py
git commit -m "feat(agent): add dedicated Agent database"
```

---

## Task 3 — Typed, content-free Agent events

**Create:**

```text
src/macr_runtime/agent/events.py
tests/test_agent_events.py
```

### RED

Tests define:

- the exact eight Phase B event types;
- canonical event ID, run ID, epoch, revision, timestamp, payload digest, and
  state-digest-after fields;
- `after_revision == before_revision + 1`;
- exact payload allowlists per event type;
- creation payload carries the bounded Phase A public header only;
- prompt, answer, credential, bytes, raw content, local path, unknown key,
  non-finite number, boolean-as-integer, and oversized text rejection;
- HTTPS/model/reference and other authorized metadata controls remain accepted;
- public round trip preserves canonical bytes and digest.

Run:

```powershell
python -m unittest tests.test_agent_events -v
```

Expected RED: no Agent event module exists.

### GREEN

Implement typed event builders and a pure replay-facing `apply_event` reducer.
Do not import the v0.6 provider event store or extend its provider payload schema.

Run:

```powershell
python -m unittest tests.test_agent_events tests.test_event_store tests.test_agent_state -v
git diff --check
```

Commit:

```powershell
git add src/macr_runtime/agent/events.py tests/test_agent_events.py
git commit -m "feat(agent): add typed Agent state events"
```

---

## Task 4 — Atomic create/read/list AgentStore

**Create:**

```text
src/macr_runtime/agent/store.py
tests/test_agent_store.py
```

### RED

Tests require:

- `create_agent_run()` writes one creation event, one projection, and exact
  immutable binding indexes in one transaction;
- each otherwise valid header mismatch (state, revision, or epoch) fails before
  SQL and leaves every Phase B table at zero rows;
- the valid CREATED/revision 1/epoch 0 control writes exactly one creation event
  with `before_revision=0` and `after_revision=1`;
- duplicate AgentRun ID rejects even when the second body is identical;
- no event without projection and no projection without event at injected
  transaction boundaries;
- `get_agent_run`, bounded `list_agent_runs`, and bounded `list_agent_events`
  are deterministic and content-free;
- current projection/event tail disagreement is visible and never auto-repaired;
- creation of a second occurrence with the same subject digest is allowed.

Run:

```powershell
python -m unittest tests.test_agent_store -v
```

Expected RED: AgentStore is absent.

### GREEN

Implement:

- one internal transaction helper owned by AgentStore;
- atomic creation and binding-index insertion;
- exact projection/event read models;
- cursor-based bounded list operations;
- deterministic test-only fault markers before event insert, after event insert,
  after projection update, and before commit. Fault markers raise and rollback;
  they never exist as CLI or provider inputs.

Run:

```powershell
python -m unittest tests.test_agent_store tests.test_agent_database tests.test_agent_events -v
git diff --check
```

Commit:

```powershell
git add src/macr_runtime/agent/store.py tests/test_agent_store.py
git commit -m "feat(agent): add atomic Agent store"
```

---

## Task 5 — Named lifecycle service and revision/epoch CAS

**Create:**

```text
src/macr_runtime/agent/service.py
tests/test_agent_service.py
```

### RED

Tests cover:

- create then admit via host-only named methods;
- exact expected revision and epoch on admission;
- stale revision, skipped revision, rollback, and old epoch reject before write;
- CREATED to ACTIVE and unsupported Phase F states reject;
- no generic `set_state` or caller-selected target state API;
- CREATED host cancellation is CAS-bound without an owner;
- owned mutations are not yet available before Task 6;
- public failures expose stable codes without paths or private bodies.

Run:

```powershell
python -m unittest tests.test_agent_service -v
```

Expected RED: AgentStateService is absent.

### GREEN

Implement creation, admission, reads, lists, and pre-ownership cancellation.
All SQL updates use both expected revision and expected epoch predicates and
require exactly one updated row. Do not implement a model-facing API.

Run:

```powershell
python -m unittest tests.test_agent_service tests.test_agent_lifecycle tests.test_agent_store -v
git diff --check
```

Commit:

```powershell
git add src/macr_runtime/agent/service.py tests/test_agent_service.py
git commit -m "feat(agent): add revision-fenced Agent service"
```

---

## Task 6 — Cross-process ownership, epoch, and fencing

**Create/modify:**

```text
src/macr_runtime/agent/ownership.py
src/macr_runtime/agent/store.py
src/macr_runtime/agent/service.py
tests/test_agent_ownership.py
tests/test_agent_service.py
```

### RED

Tests define:

- acquisition only for ADMITTED, ACTIVE, or BLOCKED;
- exact expected revision and epoch are required;
- one new acquisition atomically allocates a never-reused token, increments epoch
  and revision, appends `agent.owner_acquired`, updates projection, and inserts
  the lease;
- exact same-owner unexpired acquire is idempotent;
- competing owner refuses without event, epoch, revision, or token drift;
- renew preserves token/epoch/revision and expired renew refuses;
- release requires exact owner, lease ID, epoch, and token;
- reacquire after release or expiry creates a new epoch and larger token;
- stale permit, stale epoch, stale token, and wrong lease reject before write;
- owned activate/block/reactivate/complete/fail/cancel follow the approved table;
- terminal mutation removes ownership in the same transaction.

Run:

```powershell
python -m unittest tests.test_agent_ownership tests.test_agent_service -v
```

Expected RED: ownership and owned service methods are absent.

### GREEN

Implement `AgentOwnershipPermit` and an ownership façade whose canonical
acquisition transaction remains inside AgentStore. Do not reuse provider dispatch
leases or share their database. Use an injectable timezone-aware clock for tests.

Run:

```powershell
python -m unittest tests.test_agent_ownership tests.test_agent_service tests.test_dispatch tests.test_scheduler -v
git diff --check
```

Commit:

```powershell
git add src/macr_runtime/agent/ownership.py src/macr_runtime/agent/store.py src/macr_runtime/agent/service.py tests/test_agent_ownership.py tests/test_agent_service.py
git commit -m "feat(agent): fence Agent ownership and epochs"
```

Twin event: send the exact green commit/tree, focused outputs, and any architecture
delta. A Twin `CHALLENGE` reopens only the affected slice.

---

## Task 7 — Replay, inspection, and explicit projection rebuild

**Create/modify:**

```text
src/macr_runtime/agent/store.py
tests/test_agent_rebuild.py
```

### RED

Tests require:

- pure replay from creation through terminal state;
- exact revision chain, epoch policy, event/payload/state digests, transition,
  immutable identity, and terminal closure checks;
- `inspect_projection()` is read-only for match, missing, and conflict states;
- event gap, duplicate revision, digest tampering, illegal transition, changed
  immutable header, and terminal continuation fail for distinct reasons;
- `rebuild_projection()` refuses an active lease;
- rebuild replays in memory before mutation and never edits events;
- deleting only the disposable projection and binding indexes rebuilds
  byte-equivalent canonical public state and state digest;
- a bad chain leaves the existing projection untouched.

Run:

```powershell
python -m unittest tests.test_agent_rebuild -v
```

Expected RED: replay inspection and rebuild APIs are absent.

### GREEN

Implement explicit inspection/rebuild. No read path silently repairs state. Event
rows intentionally remain independent of the rebuildable projection foreign-key
graph.

Run:

```powershell
python -m unittest tests.test_agent_rebuild tests.test_agent_store tests.test_agent_events -v
git diff --check
```

Commit:

```powershell
git add src/macr_runtime/agent/store.py tests/test_agent_rebuild.py
git commit -m "feat(agent): rebuild Agent projections from events"
```

---

## Task 8 — Multiprocess and transaction-failure attacks

**Create:**

```text
tests/helpers/agent_state_worker.py
tests/test_agent_multiprocess.py
```

### RED

Use Windows `spawn` and D-drive disposable state. Tests require:

- the inherited 32-process synchronized fresh-bootstrap subject remains exact;
- eight synchronized distinct owners contest one admitted run: exactly one permit,
  one owner-acquired event, one epoch increment, one revision increment, and one
  fencing token are observed;
- same-owner repeated acquisition is an idempotent green control;
- clean release followed by synchronized reacquisition yields one new winner,
  larger token, new epoch, and no parallel owner;
- stale winner processes cannot mutate after ownership changes;
- process exit after event insert but before commit leaves neither event nor
  projection mutation;
- fresh reopen after every attack reports no event/projection disagreement.

The worker count eight is inherited from the already exercised v0.6 queue matrix;
it is a test subject, not a concurrency claim or quota.

Run:

```powershell
python -m unittest tests.test_agent_multiprocess -v
```

Expected RED until cross-process behavior is complete.

### GREEN

Make only the smallest store/database changes required by observed failures. Do
not add sleep-based correctness, process-name allowlists, fixed retry counts, or
automatic state recovery.

Run:

```powershell
python -m unittest tests.test_agent_multiprocess tests.test_multiprocess_runtime -v
git diff --check
```

Commit:

```powershell
git add tests/helpers/agent_state_worker.py tests/test_agent_multiprocess.py src/macr_runtime/agent/database.py src/macr_runtime/agent/store.py src/macr_runtime/agent/ownership.py
git commit -m "test(agent): attack Phase B multiprocess fencing"
```

---

## Task 9 — Manifest, privacy, and structural reconstruction

**Create/modify:**

```text
tests/gates/v07_phase_b_contract_manifest.json
tests/gates/v07_phase_b_architecture_manifest.json
tests/test_v07_phase_b_manifest.py
scripts/agent-kernel-replay-smoke.py
pyproject.toml
```

### RED

Manifest tests require:

- unique required test IDs bound to real, non-skipped methods;
- explicit S0/S1 positive and falsifying witnesses;
- manifest-bound initial-state mismatch controls for state, revision, and epoch,
  plus the exact CREATED/1/0 and `0 -> 1` authorized control;
- exact new module allowlist and forbidden Phase C/provider/runtime imports;
- no source path outside the declared support set is needed by the smoke subject;
- all public database/event/result shapes are recursively content-free;
- the package contains every Agent kernel module;
- a local wheel installed with `--no-deps` into a new D-drive target can run the
  smoke from a D-drive working directory outside the repository.

Run:

```powershell
python -m unittest tests.test_v07_phase_b_manifest -v
```

Expected RED because manifests and smoke do not exist.

### GREEN

The smoke performs, using only the installed wheel:

```text
create -> admit -> acquire -> activate -> block -> activate -> complete
inspect exact projection
remove disposable projection/index rows
rebuild from events
compare predeclared structural equivalence
```

It emits one content-free JSON result with schema, counts, final
state/revision/epoch, state digest, replay digest, and offline flags. It never
opens the default shared state root.

Run package smoke with TEMP, TMP, pip cache, wheel output, install target, working
directory, and Agent database all under the current D-drive test directory.

Commit:

```powershell
git add tests/gates/v07_phase_b_contract_manifest.json tests/gates/v07_phase_b_architecture_manifest.json tests/test_v07_phase_b_manifest.py scripts/agent-kernel-replay-smoke.py pyproject.toml
git commit -m "test(agent): prove Phase B structural closure"
```

Twin event: provide the exact reconstruction command/output and manifest claims.
The Twin may request only an observation capable of changing closure.

---

## Task 10 — Offline wrapper and exact Phase B checkpoint

**Create:**

```text
scripts/verify-v07-phase-b.ps1
docs/checkpoints/v07/PHASE_B_AGENT_STATE_KERNEL.md
```

**Modify:**

```text
tests/test_v07_phase_b_manifest.py
```

### RED

Wrapper-presence tests require the exact focused modules, manifests, Phase A gate,
compileall, wheel reconstruction, multiprocess subject, doctor, diff check,
cleanliness check, and one `PHASE_B_SUMMARY` line. The wrapper must not invoke
providers or `verify-v06.ps1` internally.

Run:

```powershell
python -m unittest tests.test_v07_phase_b_manifest -v
```

Expected RED because the wrapper does not exist.

### GREEN

Implement the wrapper with no credential requirement. It uses only D-drive
temporary state and reports:

```text
candidate commit/tree
Agent schema version
focused test count
required manifest count
Phase A inherited test count
multiprocess subject/count
state/rebuild digest
fresh package replay true
network activity false
provider generation false
git clean true
Phase C started false
```

Commit verification infrastructure first:

```powershell
git add scripts/verify-v07-phase-b.ps1 tests/test_v07_phase_b_manifest.py
git commit -m "test(agent): add Phase B verification gate"
```

### Source-frozen gates

On the exact clean implementation/gate commit:

```powershell
.\scripts\verify-v07-phase-b.ps1
.\scripts\verify-v07-phase-a.ps1
.\scripts\verify-v06.ps1
git diff --check
git status --short
```

Any red required gate keeps Phase B incomplete. Record exact discovered counts;
never copy Phase A or v0.6 historical counts into the new checkpoint.

### Checkpoint

Write `docs/checkpoints/v07/PHASE_B_AGENT_STATE_KERNEL.md` with:

- baseline, source-frozen commit/tree, branch, schema, files, and API;
- exact focused, manifest, Phase A, v0.6, compile, multiprocess, wheel, fresh
  reconstruction, privacy, and diff evidence;
- retained red/green TDD sequence and fault subjects;
- behavioral, structural, and discriminative closure reported separately;
- Twin outcomes and any retained challenge without identity inflation;
- network/provider flags;
- NotMeasured and deferred items;
- explicit Phase C stop.

Commit:

```powershell
git add docs/checkpoints/v07/PHASE_B_AGENT_STATE_KERNEL.md
git commit -m "docs(agent): seal Phase B state kernel checkpoint"
```

Run the three gates again on the final checkpoint commit. The document records the
source-frozen implementation subject; the final documentation commit/tree is
reported separately to avoid a self-referential hash claim.

Twin event: send the exact checkpoint subject and closure evidence. `CONCUR` is
scoped review, not merge/release authority. `IDLE` is valid when no further probe
can change the decision. A challenge blocks only its affected closure claim.

---

## Final stop condition

Report only the closure supported by evidence:

```text
Phase A                 IMPLEMENTED / OFFLINE VALIDATED
Phase B behavioral      PASS | PARTIAL | FAIL | INCONCLUSIVE
Phase B structural      PASS | PARTIAL | FAIL | INCONCLUSIVE
Phase B discriminative  PASS | PARTIAL | FAIL | INCONCLUSIVE
Phase C                 NOT STARTED
Agent loop              NOT IMPLEMENTED
Live use                NOT MEASURED
```

Do not merge, push, tag, release, deploy, create shared Agent state, call a
provider, or begin Phase C without a separate operator decision.
