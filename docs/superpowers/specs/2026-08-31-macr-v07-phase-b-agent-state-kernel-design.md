# MACR v0.7 Phase B Agent State Kernel Design

Status: approved design; not yet implemented

Date: 2026-08-31

## 1. Exact baseline

```text
repository             D:\Ai\work together\MACR
base branch            main
base commit            05345d7a474f2cf05023ab4e50e18bae42293ee3
base tree              e03b180ab2eac7737fb2af5adb80257b2b387a22
design branch          workbench/v0.7-agent-state-kernel
package version        0.6.0a1 (unchanged during Phase B)
Phase A                IMPLEMENTED / OFFLINE VALIDATED
Phase B implementation NOT STARTED at design approval
```

This design is subordinate to the canonical v0.7 documents under
`docs/macr-v0.7` and narrows only Phase B, the AgentRun State Kernel. It does
not revise the Phase A contract identities or authorize later phases.

## 2. Decision

Phase B will implement a dedicated single-machine, cross-process AgentRun state
kernel backed by a separate SQLite database. Each canonical mutation will append
one typed event and update the current projection in the same SQLite transaction.

The Phase B gate is:

```text
AgentStateRecoverable
and RevisionFenced
and OwnershipFenced
and InheritedTestsGreen
```

Phase B is not an autonomous agent loop. It contains no provider dispatch,
planner, runner, scheduler, checkpoint engine, wake evaluator, semantic store,
Direct Chat change, or external-system dependency.

## 3. Alternatives considered

### 3.1 Dedicated Agent SQLite with atomic event and projection writes — selected

This keeps AgentRun state separate from v0.6 dispatch and Direct Chat data while
making compare-and-swap, cross-process ownership, and deterministic replay
directly testable. Event and projection writes share one transaction, so a normal
mutation cannot commit only one half.

### 3.2 Extend `runtime/dispatch.sqlite3` — rejected

This would reuse some tables and migration machinery, but it couples the new
AgentRun lifecycle to historical dispatch state, increases shared-runtime
migration risk, and violates the specified AgentRun database boundary.

### 3.3 Event log without a current projection — rejected for Phase B

This makes replay conceptually simple, but every compare-and-swap, ownership
decision, list, and status read would require replay or a second index that is a
projection in practice. It does not fit the Phase B `agent_runs` requirement.

## 4. Scope

### 4.1 In scope

- one durable AgentRun occurrence with the Phase A `AgentRunHeader`;
- a deterministic Phase B lifecycle subset;
- strict state revision compare-and-swap;
- runtime epoch fencing;
- one active cross-process owner per AgentRun;
- expiring leases and persistent monotonically increasing fencing tokens;
- append-only, content-free, typed AgentRun events;
- a rebuildable operational projection;
- host/runtime-only state mutation service methods;
- D-drive-only persistence and D-drive test state;
- unit, negative-control, multiprocess, fault-injection, replay, and inherited
  offline verification.

### 4.2 Explicitly out of scope

- command-line or UI Agent controls;
- model or provider invocation, including loopback Ollama;
- planning, semantic graph mutation, observation, action, or verification work;
- WAITING execution, reconciliation workflow, checkpoint creation, suspension,
  wake, resume, temporal scheduling, or durable timers;
- child Agent creation or joining;
- distributed consensus, cross-machine fencing, leader election, or Byzantine
  tolerance;
- encrypted persistence or multi-tenant security;
- migration of v0.6 provider invocations or Direct conversations into AgentRuns;
- package version promotion to `0.7.0a1`;
- release, deployment, shared-runtime migration, or live acceptance.

The Phase A states and binding types remain available as contracts. Phase B does
not expose host methods that enter WAITING, SUSPENDED, WAKING, or
RECONCILIATION_REQUIRED.

## 5. Component boundary

```text
AgentStateService
  |-- LifecyclePolicy
  |-- AgentOwnershipStore
  `-- AgentStore
        `-- AgentDatabase
```

Planned source responsibilities:

```text
src/macr_runtime/agent/database.py
  D-drive validation, SQLite connection policy, schema v1, WAL bootstrap

src/macr_runtime/agent/state.py
  immutable current projection, canonical state digest, safe public shape

src/macr_runtime/agent/events.py
  typed Phase B event records, exact payload schemas, replay validation

src/macr_runtime/agent/lifecycle.py
  the only legal transition table and transition validation

src/macr_runtime/agent/store.py
  atomic event/projection persistence, CAS, reads, replay, rebuild inspection

src/macr_runtime/agent/ownership.py
  lease acquire/renew/release, epoch advance, fencing-token verification

src/macr_runtime/agent/service.py
  named host/runtime operations; no generic state setter

src/macr_runtime/agent/errors.py
  typed fail-closed errors for state, revision, epoch, ownership, and integrity
```

`contracts.py` remains the canonical Phase A contract module. Phase B must not
duplicate or silently reinterpret its identifiers, bindings, or state enum.

## 6. Storage boundary

The default database is:

```text
D:\AI_RESIDENCE\AI_Runtime\macr-state\runtime\agent.sqlite3
```

`StorageLayout.agent_db_path` will derive this path. `AgentDatabase` rejects a
relative path or a persistent path outside D: before creating a directory or
file. Tests use a unique child under `MACR_TEST_TMP` on D: and never open the
shared Agent database.

The database uses:

```text
SQLite WAL
PRAGMA foreign_keys = ON
PRAGMA synchronous = FULL
PRAGMA busy_timeout = 30000
BEGIN IMMEDIATE for every mutation
bounded retry only for transient bootstrap locks
```

The Agent schema has its own `schema_meta` component and version `1`. It does not
bump the v0.6 runtime, accounting, observatory, Direct, or settings schemas.

## 7. Physical schema v1

The minimum schema contains:

```text
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

### 7.1 `agent_runs`

This is the rebuildable current operational projection. It stores only bounded
public references and metadata:

```text
agent_run_id             primary key, canonical UUIDv4
subject_digest           lowercase SHA-256
agent_ref                bounded reference
initial_header_json      canonical Phase A public header at CREATED/revision 1
state                    closed AgentRunState value
state_revision           positive integer
epoch                    non-negative integer
goal_ref                 bounded reference
authority_ref            bounded reference
budget_ref               bounded reference
semantic_state_ref       nullable bounded reference
active_plan_ref          nullable bounded reference
latest_checkpoint_ref    nullable; always null in Phase B
parent_agent_run_id      nullable canonical UUIDv4
delegation_ref           nullable bounded reference
state_digest             lowercase SHA-256
created_at               normalized UTC timestamp
updated_at               normalized UTC timestamp, excluded from state digest
```

The initial header is immutable. Phase B changes only the lifecycle state,
revision, epoch, and operational timestamps. Later phases may add binding events
without rewriting the original header.

### 7.2 Binding and lineage tables

`agent_goals`, `agent_world_bindings`, `agent_memory_bindings`, and
`agent_plan_bindings` contain only the Phase A public binding fields and digests.
They preserve complete initial-header reconstruction without storing goal text,
memory text, world payloads, plans, prompts, answers, or local file paths.

`agent_children` stores parent/child occurrence references and a bounded
delegation reference. Phase B can persist a supplied parent relationship but does
not create or join child runs.

### 7.3 `agent_events`

```text
sequence                 integer primary key autoincrement
event_id                 unique canonical UUIDv4
agent_run_id             canonical UUIDv4; intentionally independent of projection
epoch                    non-negative integer
before_revision          non-negative integer
after_revision           positive integer
event_type               closed Phase B event type
payload_json             canonical, event-specific, content-free JSON
payload_digest           lowercase SHA-256
state_digest_after       lowercase SHA-256
created_at               normalized UTC timestamp
```

The event log is historical evidence and is not deleted with the projection.
Every Phase B event is state-changing and satisfies:

```text
after_revision = before_revision + 1
```

A unique `(agent_run_id, after_revision)` constraint prevents skipped or duplicate
canonical revisions. Event type and payload are validated before SQL execution.

### 7.4 Ownership tables

`agent_ownership` contains at most one current lease per AgentRun:

```text
agent_run_id
owner_id
lease_id
fencing_token
epoch
acquired_at
expires_at
```

`agent_fencing_counter` stores a monotonically increasing database-wide token.
Tokens are never reused, including after lease release or expiry.

## 8. State identity

Phase B preserves the Phase A distinction:

```text
agent_run_id   = occurrence identity
subject_digest = immutable initial execution subject
```

The current `state_digest` covers all canonical projection fields except
`updated_at` and other non-semantic telemetry. It uses the Phase A canonical JSON
profile and a dedicated namespace. A timestamp cannot change state identity by
itself.

The initial state is exactly:

```text
state          CREATED
state_revision 1
epoch          0
```

The creation event is `before_revision=0`, `after_revision=1`.

## 9. Phase B lifecycle

The single transition table allows only:

```text
CREATED  -> ADMITTED
CREATED  -> CANCELLED

ADMITTED -> ACTIVE
ADMITTED -> FAILED
ADMITTED -> CANCELLED

ACTIVE   -> BLOCKED
ACTIVE   -> COMPLETED
ACTIVE   -> FAILED
ACTIVE   -> CANCELLED

BLOCKED  -> ACTIVE
BLOCKED  -> FAILED
BLOCKED  -> CANCELLED
```

COMPLETED, FAILED, and CANCELLED are terminal. No terminal state can reopen.
CREATED to ACTIVE is illegal. The store exposes no generic transition method to
callers; every change uses a named service method whose expected source and target
states are fixed.

`complete_agent_run()` is host/runtime-facing and exists only so Phase B can test
terminal integrity. Nothing in Phase B lets an Agent or model declare its own
completion.

## 10. Event set

The closed Phase B event set is:

```text
agent.run_created
agent.run_admitted
agent.owner_acquired
agent.run_activated
agent.blocked
agent.completed
agent.failed
agent.cancelled
```

Each type has an exact payload allowlist. Payloads may include IDs, digests,
bounded reason codes, safe references, and the creation header. They reject
unknown keys, credential-like fields, prompt/answer/content bodies, absolute
local paths, non-finite numbers, booleans where integers are required, and
unbounded free text.

Lease renewals and clean releases are operational ownership changes, not
canonical AgentRun state changes, and do not append AgentRun state events.

## 11. Ownership and epoch policy

### 11.1 Admission before ownership

`create_agent_run()` and `admit_agent_run()` are host-only operations. Creation
uses the supplied Phase A header; admission requires exact expected revision and
epoch but does not require an active owner because execution ownership does not
exist yet.

### 11.2 Acquisition

Ownership may be acquired only for ADMITTED, ACTIVE, or BLOCKED runs. A successful
new acquisition:

1. locks the database with `BEGIN IMMEDIATE`;
2. refuses an unexpired lease owned by another process;
3. allocates a never-reused fencing token;
4. increments the AgentRun epoch by one;
5. increments the state revision by one;
6. appends `agent.owner_acquired` while leaving the lifecycle state unchanged;
7. updates the projection and inserts the lease in the same transaction;
8. returns an immutable ownership permit containing run ID, owner ID, lease ID,
   fencing token, epoch, revision, and expiry.

An exact repeated acquire by the same owner while its lease remains current is
idempotent: it returns the existing permit without allocating a token or changing
epoch/revision.

The first acquisition therefore moves an admitted run from epoch 0 to epoch 1.
Any acquisition after clean release, expiry, or process loss creates a new epoch,
so an old worker fails both the epoch and fencing-token checks.

### 11.3 Mutation and renewal

Every mutation after admission requires:

```text
expected_revision
expected_epoch
owner_id
lease_id
fencing_token
```

The lease must be unexpired and exactly match the ownership row. Renewal preserves
epoch, revision, and fencing token and may only extend the expiry. An expired lease
cannot be renewed.

Release deletes only an exact current lease. Releasing the wrong owner, lease ID,
or token fails closed. A terminal transition removes the current lease in the same
transaction as its event/projection mutation.

## 12. Atomic mutation protocol

Every named mutation follows this order inside one transaction:

1. load the current projection;
2. validate AgentRun existence and non-terminal status;
3. compare exact expected revision;
4. compare exact expected epoch;
5. validate current ownership permit when the operation requires one;
6. validate the named lifecycle transition;
7. construct and validate the exact typed event;
8. calculate the next projection and state digest;
9. insert the event;
10. update the projection with a SQL revision/epoch compare-and-swap predicate;
11. require exactly one updated projection row;
12. commit.

Any failure rolls back both event and projection. The database never commits a
state event whose projection update failed, or a projection mutation without its
event.

## 13. Service API

The Phase B internal service surface is:

```text
create_agent_run(header)
admit_agent_run(run_id, expected_revision, expected_epoch, reason_code, reason_digest)

acquire_agent_run(run_id, owner_id, expected_revision, expected_epoch, ttl_seconds)
renew_agent_run(permit, ttl_seconds)
release_agent_run(permit)

activate_agent_run(permit, expected_revision, expected_epoch, reason_code, reason_digest)
block_agent_run(permit, expected_revision, expected_epoch, reason_code, reason_digest)
complete_agent_run(permit, expected_revision, expected_epoch, evidence_ref, evidence_digest)
fail_agent_run(permit, expected_revision, expected_epoch, reason_code, reason_digest)
cancel_agent_run(...)

get_agent_run(run_id)
list_agent_runs(state=None, limit=..., after_run_id=None)
list_agent_events(run_id, limit=..., after_sequence=None)

inspect_projection(run_id)
rebuild_projection(run_id)
```

`cancel_agent_run()` has two explicit paths: CREATED may be cancelled by a host
CAS without ownership because no execution owner can exist; ADMITTED, ACTIVE, and
BLOCKED cancellation requires a current permit. No method accepts arbitrary model
output as a state mutation command.

List APIs are bounded, deterministic, content-free, and cursor based. They never
return prompt, answer, key, memory body, goal body, world payload, or local path.

## 14. Projection replay and repair

Replay reads events for one run in sequence order and validates:

- one creation event at revision 1;
- canonical event and payload digests;
- exact revision continuity with no duplicate or gap;
- monotonic epoch, changed only by `agent.owner_acquired` in Phase B;
- legal lifecycle transitions;
- state digest after every event;
- immutable identity and initial header;
- terminal closure.

`inspect_projection()` is read-only and reports exact match, missing projection, or
conflict without rewriting anything.

`rebuild_projection()` is an explicit host operation. It refuses while an
unexpired lease exists, replays into memory first, then recreates the projection
and binding indexes in one transaction. It never edits or replaces historical
events. A malformed, incomplete, or conflicting event chain fails closed and
leaves the existing database state unchanged.

The required crash-rebuild control deletes only the disposable test projection,
replays the retained events, and requires byte-equivalent canonical state and
state digest.

## 15. Failure taxonomy

Phase B uses typed errors with stable public codes:

```text
AGENT_RUN_ALREADY_EXISTS
AGENT_RUN_NOT_FOUND
ILLEGAL_AGENT_RUN_TRANSITION
STALE_AGENT_RUN_REVISION
STALE_AGENT_RUN_EPOCH
AGENT_OWNERSHIP_CONFLICT
AGENT_LEASE_EXPIRED
STALE_AGENT_FENCING_TOKEN
AGENT_EVENT_INTEGRITY_ERROR
AGENT_PROJECTION_CONFLICT
AGENT_REBUILD_BLOCKED
```

Messages are sanitized and never embed database paths, event bodies, credentials,
or private content. A caller may inspect current content-free state after a stale
revision or epoch error; the service does not retry automatically.

## 16. Test design

Planned focused modules:

```text
tests/test_agent_state.py
tests/test_agent_lifecycle.py
tests/test_agent_database.py
tests/test_agent_events.py
tests/test_agent_store.py
tests/test_agent_ownership.py
tests/test_agent_service.py
tests/test_agent_rebuild.py
tests/test_agent_multiprocess.py
tests/test_v07_phase_b_manifest.py
```

The Phase B manifest will assign unique stable IDs to required positive and
negative controls. At minimum it proves:

- duplicate AgentRun ID rejection;
- CREATED to ACTIVE rejection;
- terminal reopen rejection;
- exact revision increment, skipped revision rejection, and rollback rejection;
- stale revision and stale epoch rejection before write;
- one winner across synchronized competing processes;
- never-reused fencing tokens;
- stale owner, lease, and fencing token rejection;
- same-owner acquire idempotence;
- lease expiry followed by new epoch acquisition;
- event/projection atomic rollback at injected pre-commit boundaries;
- event gap, duplicate revision, digest tampering, and illegal replay rejection;
- projection deletion and byte-equivalent event rebuild;
- active lease blocks rebuild;
- public reads and database scans contain no prompt, answer, key, memory body,
  local path, or raw goal/world content;
- no Direct, dispatch, accounting, observatory, or shared Agent database mutation;
- no provider adapter, HTTP transport, Ollama transport, or network path invoked.

## 17. Verification gate

`scripts/verify-v07-phase-b.ps1` will:

1. set D-drive state and temporary roots;
2. run the exact focused Phase B modules;
3. validate the Phase B test manifest;
4. run compileall;
5. run `scripts/verify-v07-phase-a.ps1`, which includes inherited
   `scripts/verify.ps1` discovery;
6. run deterministic multiprocess and rebuild controls;
7. check doctor reports `network_activity=false`;
8. record `provider_generation=false` because no provider path is invoked;
9. run `git diff --check` and require a clean tracked/untracked worktree;
10. emit one compact `PHASE_B_SUMMARY` containing exact commit/tree, schema
    version, focused and inherited counts, manifest count, multiprocess count,
    rebuild digest, and offline flags.

The Phase B wrapper does not call `scripts/verify-v06.ps1`. The final checkpoint
must run that complete gate separately on the same exact clean candidate. This
avoids hiding the v0.6 result inside another wrapper while retaining one Phase A
gate and one complete v0.6 gate as independent evidence.

## 18. Version, migration, and release boundary

Phase B adds `AgentDatabase` schema version 1 but does not change the package
version from `0.6.0a1`. The `0.7.0a1` claim remains reserved for the bounded
single-Agent MVP after its later phases and final acceptance gates.

There is no automatic shared-state migration. Instantiating `AgentDatabase` on a
new explicitly selected D-drive path creates schema v1. Historical v0.6 events,
provider runs, and Direct conversations remain unchanged and are never imported.

Phase B completion does not authorize merge, tag, release, deployment, GitHub
publication, shared D-drive activation, or live provider use. Those remain
separate operator decisions.

## 19. Acceptance and stop boundary

Phase B may be reported complete only when an exact clean commit/tree proves:

```text
AgentStateRecoverable = true
RevisionFenced        = true
OwnershipFenced       = true
InheritedTestsGreen   = true
network_activity      = false
provider_generation   = false
Phase C started       = false
```

The checkpoint must state:

```text
Phase A        IMPLEMENTED / OFFLINE VALIDATED
Phase B        IMPLEMENTED / OFFLINE VALIDATED
Phase C        NOT STARTED
Agent loop     NOT IMPLEMENTED
Live use       NOT MEASURED
```

Implementation stops at this boundary until a separate Phase C direction and
approved design are present.
