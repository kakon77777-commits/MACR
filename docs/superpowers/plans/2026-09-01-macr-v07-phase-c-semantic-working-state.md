# MACR v0.7 Phase C Semantic Working State Implementation Plan

Status: MSSP × TDD × APR implementation plan

Date: 2026-09-01

## Exact project world

```text
repository              D:\Ai\work together\MACR
branch                  workbench/v0.7-semantic-working-state
base Phase B commit     60a477cfac179f399a6c50126523c8a55cea4575
base Phase B tree       f4d31c31b4c7759f78d72061985ac641136f4ab2
Phase C design commit   6e88853c192ed579d903764f6fee06c424e968dc
Phase C design tree     5076ad437029f5a702735097f421da33479decc0
graph-attach amendment  600a7eeeeecc1d5db10994222d5e6b896d809561
amendment tree          30dd97feb515fa2bb2089c17e48b8e0c033db80e
authority split commit  04ad276761b9c8bb3481b6ad001d14bd39bb2064
authority split tree    c0ff3471911d828c0d53fdf9927cd61a00bb7197
revision contract commit 59d827d18588bf11fcb14c6ddcbd361c27c81d00
revision contract tree   0c8557ee7324cdfcf7b2aa4b78165c0f053d35c5
package version         0.6.0a1 (unchanged)
physical database       runtime/agent.sqlite3 on D: only
```

Canonical design:

```text
docs/superpowers/specs/2026-09-01-macr-v07-phase-c-semantic-working-state-design.md
```

Private `docs/macr-v0.7/future` and ISQL Origin are excluded. NOVA, EML-U,
SEDB, MNEME, PNCW, providers, and Direct Chat are not runtime dependencies.

## MSSP governance

One event-local Lead owns source mutations. One task-local Governing Twin remains
read-only and receives compact canonical projections only. No fan-out is
authorized.

Twin reevaluation events:

1. implementation-plan closure candidate;
2. Agent runtime v2 migration plus semantic schema/store green;
3. atomic cross-component commit and fault matrix green;
4. fresh-package Goal-to-Plan reconstruction green;
5. final Phase C checkpoint candidate.

Valid Twin outcomes remain `IDLE`, `CONCUR`, `CHALLENGE`, or a targeted evidence
request. Twin agreement is not merge, release, deployment, or live authority.

### Retained design challenge

The Twin challenged the initial statement “same SQLite, independent semantic
schema” because storage locality did not identify the graph CAS target or the
single transaction owner. The accepted resolution adds:

- independent host-generated `graph_id`;
- exact `(graph_id, base_revision, base_digest, registry_version/digest)` CAS;
- per-AgentRun pinned bindings for shared graphs;
- one `SemanticCommitService` owning one `BEGIN IMMEDIATE`;
- Agent runtime v2 binding columns and `agent.semantic_state_advanced` event;
- exact ownership, Agent revision/epoch, and external AuthorizationReference;
- faults between semantic and Agent halves;
- semantic authority-looking data explicitly unable to grant commit authority.

Targeted reevaluation returned `CONCUR` at design scope only.

The implementation-plan review then challenged the fresh reconstruction
sequence after graph revisions were changed to start at one. Task 9 is corrected
to the exact sequence `create empty r1 -> attach AgentRun to r1 -> commit
Goal/Plan as r2 -> project/rebuild r2`. The smoke and manifest must bind both
Agent semantic-binding advances and the resulting exact Agent revision/event
counts. The earlier inconsistent “commit revision 1” wording is retained here as
a corrected plan defect, not silently forgotten.

The C1 storage review challenged graph-head topology: immutable revision/history
rows referenced a `semantic_graphs` row that also acted as the removable head.
The schema is corrected to immutable `semantic_graphs` catalog plus removable
`semantic_graph_heads` projection. A manifest-bound control deletes only the head
with foreign keys enabled, proves revision/history bytes unchanged, and rebuilds
the exact head.

The atomic-core review challenged attach idempotency: the first test changed
expected Agent revision on retry, so it did not replay the exact request.
`semantic_attach_receipts` now resolves operation ID plus full request digest
before stale CAS. Tests must repeat the byte-equivalent original request and
reject conflicting operation-ID reuse with no graph/Agent/event drift.

## Authorized scope

Allowed:

- Phase C source, schemas, tests, verification scripts, plan, checkpoint, and
  local commits on this branch;
- disposable D-drive Agent/semantic databases, wheels, and install targets;
- Agent runtime schema v1-to-v2 migration tests;
- semantic schema component v1;
- C1 registry/graph/store, C2 patch/commit, C3 structured context projection.

Not authorized:

- provider/model generation, credential reads, Direct DB dependency, shared
  Agent DB creation/migration, Phase D observation bridge, action execution,
  Agent loop, merge, push, tag, release, deployment, or publication.

## Closure vector

### Behavioral

Registry, graph/revision store, proposal-only patches, governed atomic commits,
AgentRun semantic binding, shared-graph pinning, bounded query, and deterministic
context projection work through named APIs. Goal-to-Plan works without a Direct
Conversation database.

### Structural

A fresh wheel installed without dependencies into a new D-drive target outside
the repository can create an AgentRun and graph, attach/commit Goal and Plan,
reopen, remove rebuildable projections, reconstruct Agent lifecycle/semantic
binding/graph head, and reproduce exact context projection bytes and digest.

### Discriminative

Every named invalid axis retains a nearby authorized-equivalent control and a
unique manifest binding: registry, graph identity/head, patch, overwrite,
relation, scope, supersession, ambiguity/obligation, authority, permit, stale
Agent state, cross-component fault, shared graph, projection omission, privacy,
and package architecture.

## TDD command prelude

Before direct Python commands:

```powershell
$env:PYTHONPATH = (Resolve-Path '.\src').Path
$env:PYTHONDONTWRITEBYTECODE = '1'
```

Each executable slice follows valid RED → minimum GREEN → nearest inherited
controls → `git diff --check` → green commit. Collection, quoting, import-path, or
fixture failures are harness evidence, not product RED.

No test calls a provider or opens the shared default Agent database.

---

## Task 1 — Registry, graph identity, and Phase C error contracts

**Create/modify:**

```text
src/macr_runtime/semantic/errors.py
src/macr_runtime/semantic/registry.py
src/macr_runtime/semantic/graph.py
src/macr_runtime/semantic/schemas/registry-v1.json
src/macr_runtime/semantic/__init__.py
tests/test_semantic_registry.py
tests/test_semantic_graph.py
```

### RED

Tests first require:

- registry canonical bytes/version/digest and packaged readback;
- exact Phase A node/relation/status enums represented in registry v1;
- unknown node/relation/effect/status and wrong registry digest rejection;
- explicit relation direction validation, including a Goal-to-Plan green control;
- immutable UUIDv4 graph identity separate from graph digest;
- deterministic registry-bound empty graph digest at revision 1, compatible
  with the existing positive-revision `SemanticStateBinding`;
- immutable `SemanticGraphHead`, `SemanticGraphRevision`, and
  `SemanticStateBinding` conversion;
- equal content under one registry gives equal digest across different graph IDs;
- stable sanitized Phase C error codes.

Run:

```powershell
python -m unittest tests.test_semantic_registry tests.test_semantic_graph -v
```

Expected valid RED: Phase C registry/graph modules are absent.

### GREEN

Implement pure contracts and registry validation only. No SQLite or Agent mutation.
Registry data is not authority.

Run:

```powershell
python -m unittest tests.test_semantic_registry tests.test_semantic_graph tests.test_semantic_contracts tests.test_agent_contract_boundaries -v
git diff --check
```

Commit:

```powershell
git add src/macr_runtime/semantic/errors.py src/macr_runtime/semantic/registry.py src/macr_runtime/semantic/graph.py src/macr_runtime/semantic/schemas/registry-v1.json src/macr_runtime/semantic/__init__.py tests/test_semantic_registry.py tests/test_semantic_graph.py
git commit -m "feat(semantic): add Phase C registry and graph contracts"
```

---

## Task 2 — Agent runtime schema v2 and semantic binding event

**Create/modify:**

```text
tests/fixtures/agent-runtime-v1.sql
src/macr_runtime/agent/database.py
src/macr_runtime/agent/events.py
src/macr_runtime/agent/store.py
src/macr_runtime/agent/semantic_binding.py
src/macr_runtime/agent/__init__.py
tests/test_agent_database.py
tests/test_agent_events.py
tests/test_agent_rebuild.py
tests/test_agent_semantic_binding.py
```

### RED

Tests require:

- exact v1 fixture migrates to `agent_runtime=2`;
- existing AgentRun/event rows retain IDs, payload JSON, payload digest, state
  digest, timestamp, sequence, and lifecycle projection;
- fresh v2 schema adds nullable semantic digest/revision columns and all-or-none
  binding validation;
- event table accepts `agent.semantic_state_advanced` while retaining every Phase
  B constraint;
- semantic binding event leaves lifecycle state/epoch unchanged and increments
  Agent state revision exactly once;
- event payload binds previous/new graph ref/digest/revision, commit/patch,
  registry, and external authorization digest;
- AgentStore reads exact current `SemanticStateBinding` separately from lifecycle
  projection;
- lifecycle replay plus semantic-binding replay detects mismatches;
- Agent projection rebuild restores semantic columns from binding events;
- no historical event is rehashed or rewritten.

Run:

```powershell
python -m unittest tests.test_agent_semantic_binding tests.test_agent_database tests.test_agent_events tests.test_agent_rebuild -v
```

Expected RED: schema v2/event/binding behavior is absent.

### GREEN

Implement the additive runtime migration and `AgentSemanticBindingPort` package
primitive. The port may prepare/commit against a caller-owned connection but does
not start cross-component transactions itself.

Run:

```powershell
python -m unittest tests.test_agent_semantic_binding tests.test_agent_database tests.test_agent_events tests.test_agent_rebuild tests.test_agent_store tests.test_agent_ownership -v
git diff --check
```

Commit:

```powershell
git add tests/fixtures/agent-runtime-v1.sql src/macr_runtime/agent/database.py src/macr_runtime/agent/events.py src/macr_runtime/agent/store.py src/macr_runtime/agent/semantic_binding.py src/macr_runtime/agent/__init__.py tests/test_agent_database.py tests/test_agent_events.py tests/test_agent_rebuild.py tests/test_agent_semantic_binding.py
git commit -m "feat(agent): add semantic binding revision events"
```

---

## Task 3 — Semantic schema v1 and immutable graph store

**Create:**

```text
src/macr_runtime/semantic/database.py
src/macr_runtime/semantic/store.py
tests/test_semantic_database.py
tests/test_semantic_store.py
```

### RED

Tests require:

- `agent_semantics=1` shares the exact AgentDatabase path and connection policy;
- semantic initialization does not change `agent_runtime=2` or other databases;
- exact semantic tables, indexes, foreign keys, CHECK constraints, WAL, and
  create-once registry bytes;
- synchronized initialization remains safe under the already-observed 32-process
  bootstrap subject;
- graph create writes revision 1, registry binding, empty membership, and current
  head atomically;
- graph identity/catalog remains immutable while the separate current-head row
  can be deleted and rebuilt from latest revision with all history byte-identical;
- duplicate graph ID and conflicting registry bytes fail closed;
- graph ID/digest separation and immutable revision reads;
- bounded graph/head/revision queries;
- no raw prompt/answer/key/path/body in database or public output.

Run:

```powershell
python -m unittest tests.test_semantic_database tests.test_semantic_store -v
```

### GREEN

Implement `SemanticSchema` over an existing `AgentDatabase` and `SemanticStore`
read/create primitives. No patch commit yet.

Run:

```powershell
python -m unittest tests.test_semantic_database tests.test_semantic_store tests.test_agent_database tests.test_storage -v
git diff --check
```

Commit:

```powershell
git add src/macr_runtime/semantic/database.py src/macr_runtime/semantic/store.py tests/test_semantic_database.py tests/test_semantic_store.py
git commit -m "feat(semantic): add versioned graph store"
```

Twin event: project exact migration/store commit/tree, schema rows, bootstrap
evidence, and any declared/effective architecture delta.

---

## Task 4 — Pure patch envelope, validator, and compiler

**Create:**

```text
src/macr_runtime/semantic/patch.py
src/macr_runtime/semantic/validation.py
tests/test_semantic_patch_validation.py
tests/test_semantic_patch_compiler.py
```

### RED

Tests define:

- immutable authority-free `SemanticPatchProposalRequest` binds proposal ID,
  graph/Agent identity, exact graph revision/digest/registry, and Phase A patch;
- immutable host-only `SemanticCommitRequest` binds the stored proposal plus
  graph ID, AgentRun ID, exact graph
  revision/digest/registry, expected Agent revision/epoch, permit digest,
  AuthorizationReference, Phase A patch, and request digest;
- patch base digest must equal request base digest;
- pure compiler performs no SQL;
- unknown types/effects/statuses, bad relation direction, dangling endpoints,
  duplicate records/IDs, scope escalation, silent overwrite, stale base, wrong
  registry, unconsumed/duplicate/cross-graph supersession, and malformed status
  update fail for distinct reasons;
- authorized Goal-to-Plan node/relation patch compiles deterministically;
- status update exact shape materializes a new record and preserves old record;
- ambiguity/obligation/correction/resolution evidence and provenance are retained;
- model-supplied resolution shortcut or authority-looking semantics cannot create
  external authority;
- equal inputs produce byte-identical compiled writes and next graph digest.

Run:

```powershell
python -m unittest tests.test_semantic_patch_validation tests.test_semantic_patch_compiler -v
```

### GREEN

Implement pure validation/compiler objects only. `CompiledSemanticPatch` contains
exact inserts and next membership; it has no connection or commit method.

Run:

```powershell
python -m unittest tests.test_semantic_patch_validation tests.test_semantic_patch_compiler tests.test_semantic_contracts tests.test_agent_contract_boundaries -v
git diff --check
```

Commit:

```powershell
git add src/macr_runtime/semantic/patch.py src/macr_runtime/semantic/validation.py tests/test_semantic_patch_validation.py tests/test_semantic_patch_compiler.py
git commit -m "feat(semantic): compile governed semantic patches"
```

---

## Task 5 — Proposal persistence without head mutation

**Modify/create:**

```text
src/macr_runtime/semantic/store.py
src/macr_runtime/semantic/service.py
tests/test_semantic_proposals.py
```

### RED

Tests require:

- agent/model-facing `propose_patch` accepts an already parsed
  `SemanticPatchProposalRequest` containing no permit, AuthorizationReference,
  Agent revision/epoch, or commit authority;
- proposal insert is create-once and content-free;
- exact duplicate proposal is idempotent; conflicting patch/commit ID rejects;
- proposal validation failure records bounded failure without partial records;
- proposal never changes graph head/revision, Agent event/revision/binding, or
  ownership;
- no raw model response enters the semantic database;
- model has no `force_commit`, authority, verification, or resolution API.

Run:

```powershell
python -m unittest tests.test_semantic_proposals -v
```

### GREEN

Implement proposal inspection/persistence only. Commit remains unavailable.

Run:

```powershell
python -m unittest tests.test_semantic_proposals tests.test_semantic_store tests.test_agent_service -v
git diff --check
```

Commit:

```powershell
git add src/macr_runtime/semantic/store.py src/macr_runtime/semantic/service.py tests/test_semantic_proposals.py
git commit -m "feat(semantic): persist proposal-only patches"
```

---

## Task 6 — Atomic attach and governed semantic commit

**Create/modify:**

```text
src/macr_runtime/semantic/commit.py
src/macr_runtime/semantic/service.py
src/macr_runtime/semantic/store.py
src/macr_runtime/agent/semantic_binding.py
tests/test_semantic_commit.py
tests/test_semantic_atomicity.py
```

### RED

Tests require:

- `attach_graph` binds an unbound owned AgentRun to the exact current head,
  appends one Agent semantic-binding event, increments Agent state revision once,
  leaves graph revision unchanged, and returns a create-once receipt;
- the byte-equivalent original attach request returns the same receipt even though
  its expected Agent revision is now historical; conflicting operation-ID reuse
  fails before stale CAS and leaves all state unchanged;
- attach rejects stale/noncurrent head, existing different binding, stale Agent
  revision/epoch/permit/token, and authority mismatch;
- commit validates exact graph and Agent CAS plus current ownership and external
  AuthorizationReference;
- semantic Decision/policy/authorizes-looking content cannot satisfy authority;
- one commit transaction inserts semantic records/event/patch/revision/membership,
  advances graph head, appends Agent binding event, updates Agent binding/revision,
  and inserts receipt;
- repeated exact committed commit ID returns the same receipt without another
  graph or Agent revision; conflicting reuse fails;
- faults after semantic records, graph head, Agent event, Agent binding, and before
  receipt/commit roll back every table and both heads;
- post-reopen graph head, Agent semantic binding, event tails, and receipt agree;
- no automatic retry.

Run:

```powershell
python -m unittest tests.test_semantic_commit tests.test_semantic_atomicity -v
```

### GREEN

Implement `SemanticCommitService` as the sole transaction owner. Connection-bound
store/port helpers may not commit independently.

Run:

```powershell
python -m unittest tests.test_semantic_commit tests.test_semantic_atomicity tests.test_agent_semantic_binding tests.test_agent_ownership tests.test_semantic_store -v
git diff --check
```

Commit:

```powershell
git add src/macr_runtime/semantic/commit.py src/macr_runtime/semantic/service.py src/macr_runtime/semantic/store.py src/macr_runtime/agent/semantic_binding.py tests/test_semantic_commit.py tests/test_semantic_atomicity.py
git commit -m "feat(semantic): atomically commit graph and Agent binding"
```

---

## Task 7 — Shared graph pinning, concurrency, replay, and authority attacks

**Create/modify:**

```text
tests/helpers/semantic_commit_worker.py
tests/test_semantic_shared_graph.py
tests/test_semantic_multiprocess.py
tests/test_semantic_rebuild.py
src/macr_runtime/semantic/store.py
src/macr_runtime/agent/store.py
```

### Subjects

- attach two AgentRuns to the same revision; one commit advances global head and
  only the committing Run binding;
- second pinned Run remains queryable at old immutable revision and cannot commit
  stale without explicit new request;
- eight synchronized exact-base commits produce one winner, one graph revision,
  one Agent advance, one receipt, and seven no-drift stale failures;
- stale permit/epoch/Agent revision and semantically forged authority fail before
  semantic writes;
- delete graph current-head projection and Agent lifecycle projection, then
  reconstruct exact head/history/binding from immutable revisions/events;
- missing/tampered semantic revision membership, commit receipt, Agent semantic
  event, graph head, or binding produces visible conflict;
- child lineage and all Phase B rebuild controls remain green.

The eight-contender subject reuses the already observed Phase B capacity; it is
not a throughput or production concurrency claim.

Run:

```powershell
python -m unittest tests.test_semantic_shared_graph tests.test_semantic_multiprocess tests.test_semantic_rebuild tests.test_agent_rebuild -v
```

Commit:

```powershell
git add tests/helpers/semantic_commit_worker.py tests/test_semantic_shared_graph.py tests/test_semantic_multiprocess.py tests/test_semantic_rebuild.py src/macr_runtime/semantic/store.py src/macr_runtime/agent/store.py
git commit -m "test(semantic): attack shared graph atomicity"
```

Twin event: send exact commit/tree, fault and multiprocess counts, shared-pin
evidence, reconstruction digest, and retained failures.

---

## Task 8 — Ephemeral context projection and Goal-to-Plan gate

**Create:**

```text
src/macr_runtime/semantic/projection.py
tests/test_semantic_projection.py
tests/integration/test_semantic_goal_to_plan.py
```

### RED

Tests require:

- exact graph revision/profile/request produces deterministic structured context
  bytes and digest;
- caller supplies positive node/relation maxima; booleans, zero, negative, or
  exceeded hard request bounds fail;
- projection includes required active Goal and Plan plus connecting relation;
- omitted record digests are explicit;
- required Goal, Plan, ambiguity, or obligation overflow produces
  `SEMANTIC_PROJECTION_INCOMPLETE`, not silent omission;
- projection performs no semantic/Agent/database write;
- omission does not stale, supersede, or delete canonical records;
- private/large payloads remain external refs;
- end-to-end Goal-to-Plan works with no Direct DB file, provider, network, or
  conversation history;
- equal fresh installed state reproduces exact projection.

Run:

```powershell
python -m unittest tests.test_semantic_projection tests.integration.test_semantic_goal_to_plan -v
```

### GREEN

Implement structured projection only. “Provider-ready” does not mean provider
rendering or invocation.

Run:

```powershell
python -m unittest tests.test_semantic_projection tests.integration.test_semantic_goal_to_plan tests.test_direct_store tests.test_direct_runtime -v
git diff --check
```

Commit:

```powershell
git add src/macr_runtime/semantic/projection.py tests/test_semantic_projection.py tests/integration/test_semantic_goal_to_plan.py
git commit -m "feat(semantic): project Goal-to-Plan context"
```

---

## Task 9 — Phase C manifests and fresh structural reconstruction

**Create/modify:**

```text
tests/gates/v07_phase_c_contract_manifest.json
tests/gates/v07_phase_c_architecture_manifest.json
tests/test_v07_phase_c_manifest.py
scripts/semantic-working-state-replay-smoke.py
src/macr_runtime/semantic/__init__.py
```

### Manifest controls

- unique S0/S1 IDs and unique non-skipped test bindings;
- exact Phase C module/support import graph;
- no provider, Direct, observation bridge, action, scheduler, external semantic
  runtime, or future/private source dependency;
- registry JSON packaged;
- Phase A/B public APIs remain present;
- all three Twin challenge axes have manifest-bound positive/falsifying controls;
- Phase D source absent.

### Fresh reconstruction

Build wheel/cache/install/run under one disposable D-drive subject, install with
`--no-deps`, and run from outside source under `python -S`:

```text
create AgentRun
admit/acquire/activate
create graph revision 1
attach AgentRun to graph revision 1
propose Goal/Plan patch
commit patch as graph revision 2 and advance Agent binding again
build context projection
close and reopen
remove rebuildable Agent/graph head projections
reconstruct from events/revisions
rebuild same projection
```

The manifest and smoke assert two distinct
`agent.semantic_state_advanced` events: one for attach at graph revision 1 and
one for commit at graph revision 2. Final AgentRun revision and total event count
are derived from this exact sequence rather than copied from an earlier phase.

Predeclare equivalence exactly as the design. Emit content-free JSON with schema,
counts, graph/Agent revisions, graph/state/binding/projection/replay digests, event
IDs, receipt ID, and offline flags.

Run:

```powershell
python -m unittest tests.test_v07_phase_c_manifest -v
```

Commit:

```powershell
git add tests/gates/v07_phase_c_contract_manifest.json tests/gates/v07_phase_c_architecture_manifest.json tests/test_v07_phase_c_manifest.py scripts/semantic-working-state-replay-smoke.py src/macr_runtime/semantic/__init__.py
git commit -m "test(semantic): prove Phase C structural closure"
```

Twin event: provide exact fresh replay command/result and closure vector.

---

## Task 10 — Verification wrapper and Phase C checkpoint

**Create/modify:**

```text
scripts/verify-v07-phase-c.ps1
scripts/verify-v07-phase-b.ps1
tests/test_v07_phase_c_manifest.py
docs/checkpoints/v07/PHASE_C_SEMANTIC_WORKING_STATE.md
```

### Wrapper RED/GREEN

Manifest-only tests first require the exact focused modules, Phase B compatibility
gate, compileall, fresh wheel replay, multiprocess/fault subjects, doctor,
diff/clean checks, and one `PHASE_C_SUMMARY` line.

Phase B summary must derive `phase_c_started=true` from the actual Phase C
manifest rather than retain hard-coded false. Phase C summary dynamically rejects
Phase D source.

The wrapper does not call `verify-v06.ps1`; the final checkpoint runs it
independently.

Commit gate infrastructure:

```powershell
git add scripts/verify-v07-phase-c.ps1 scripts/verify-v07-phase-b.ps1 tests/test_v07_phase_c_manifest.py
git commit -m "test(semantic): add Phase C verification gate"
```

### Source-frozen gates

```powershell
.\scripts\verify-v07-phase-c.ps1
.\scripts\verify-v07-phase-b.ps1
.\scripts\verify-v07-phase-a.ps1
.\scripts\verify-v06.ps1
git diff --check
git status --short
```

Record exact discovered counts, schema versions, commit/tree, registry/graph/
binding/projection/replay digests, fresh reconstruction, multiprocess/fault
subjects, network/provider flags, and Phase D absence.

### Checkpoint

The checkpoint reports behavioral, structural, and discriminative closure
separately; retains every challenge, harness correction, RED, repair, and
NotMeasured boundary; distinguishes source-frozen implementation from the later
documentation commit; and records Twin outcome without granting authority.

Commit:

```powershell
git add docs/checkpoints/v07/PHASE_C_SEMANTIC_WORKING_STATE.md
git commit -m "docs(semantic): seal Phase C working state checkpoint"
```

Run the four gates again on the clean checkpoint commit.

## Final stop

```text
Phase A                 IMPLEMENTED / OFFLINE VALIDATED
Phase B                 IMPLEMENTED / OFFLINE VALIDATED
Phase C behavioral      PASS | PARTIAL | FAIL | INCONCLUSIVE
Phase C structural      PASS | PARTIAL | FAIL | INCONCLUSIVE
Phase C discriminative  PASS | PARTIAL | FAIL | INCONCLUSIVE
Phase D                 NOT STARTED
Agent loop              NOT IMPLEMENTED
Live use                NOT MEASURED
```

Do not merge, push, tag, release, deploy, create/migrate shared state, call a
provider, or start Phase D without a separate operator decision.
