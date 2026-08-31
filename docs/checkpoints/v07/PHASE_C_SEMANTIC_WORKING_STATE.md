# MACR v0.7 Phase C Checkpoint — Semantic Working State

Status: implemented and offline-validated; Phase D not started

Date: 2026-09-01

## Exact subject

```text
base Phase B commit         60a477cfac179f399a6c50126523c8a55cea4575
branch                      workbench/v0.7-semantic-working-state
source-frozen commit        2949d4c0f399f4ef4326e799356678fdc4d30783
source-frozen tree          0ae93b25ae3015630d5fa5aa4e8b449d6f576651
package version             0.6.0a1 (intentionally unchanged)
Agent schema                2
semantic schema             1
shared Agent DB created     false
network activity            false
provider generation         false
Phase D started             false
```

The source-frozen subject is the implementation and verification-gate commit
before this document. The documentation commit is verified separately below;
the two identities are not collapsed.

## Delivered scope

Phase C adds a governed semantic working state to the Phase B AgentRun kernel:

- packaged, versioned semantic registry and closed node/relation vocabulary;
- independent UUIDv4 graph identity, immutable revisions, and deterministic
  registry-bound content digests;
- immutable graph catalog plus removable/rebuildable current-head projection;
- Agent runtime schema v1-to-v2 migration with exact historical row retention;
- per-AgentRun pinned `SemanticStateBinding` and
  `agent.semantic_state_advanced` events;
- authority-free patch proposals separated from host-authorized commits;
- pure validation/compiler for Goal, Plan, ambiguity, obligation, status,
  supersession, direction, scope, provenance, and relation membership;
- one `SemanticCommitService` transaction for semantic records, graph CAS,
  Agent binding CAS, events, and receipts;
- create-once attach and commit receipts with exact replay/conflict behavior;
- shared-graph pinning without silent follower advancement;
- exact revision/read/rebuild validation over scalar rows, membership, and
  referenced records;
- bounded, deterministic, ephemeral context projection from one coherent SQLite
  snapshot;
- Goal-to-Plan replay without Direct Conversation state or provider rendering.

Phase C does not implement an Agent loop, action execution, observation bridge,
provider adapter, scheduler, wake/resume engine, or Phase D behavior.

## Storage and authority boundary

The future default physical database remains:

```text
D:\AI_RESIDENCE\AI_Runtime\macr-state\runtime\agent.sqlite3
```

No shared database was created, opened, or migrated. All subjects were unique
children of D-drive test state. `agent_runtime=2` and `agent_semantics=1` share
one SQLite file so graph and Agent binding can commit under one
`BEGIN IMMEDIATE`, while their schema components and digests remain distinct.

Semantic tables are:

```text
semantic_registry_versions
semantic_graphs
semantic_graph_heads
semantic_graph_revisions
semantic_graph_revision_nodes
semantic_graph_revision_relations
semantic_nodes
semantic_relations
semantic_events
semantic_patches
semantic_attach_receipts
semantic_commit_receipts
```

Semantic vocabulary, Decision-like nodes, model output, and profile metadata
never create authority. Commit requires the current Agent revision/epoch, exact
ownership permit/fencing token, current graph revision/digest/registry, pinned
Agent binding, and external `AuthorizationReference` already bound to the
AgentRun.

## Atomicity, concurrency, and replay evidence

- Attach exact replay resolves its receipt before stale Agent CAS; any reuse of
  the operation ID with different input fails without drift.
- Attach failure injection at two write boundaries rolls back Agent event,
  binding, and receipt.
- Commit failure injection at six write boundaries rolls back semantic records,
  graph head, Agent event/binding, patch state, and receipt.
- Eight synchronized exact-base commit processes produced one winner, seven
  typed refusals, graph revision 2 only, one semantic event, one commit receipt,
  and one Agent semantic advance.
- Two AgentRuns may pin graph revision 1; one committing revision 2 advances only
  its own binding. The other remains queryable at revision 1 and cannot silently
  commit against the stale global head.
- Deleting graph and Agent projections reconstructs the exact graph head,
  Agent lifecycle state, semantic binding, and events from retained evidence.
- Missing or altered node/relation membership is rejected by both ordinary
  revision readback and head rebuild; failed rebuild creates no head.
- Tampered commit receipts are rejected on idempotent readback.
- A controlled WAL interleave commits membership corruption after the projector
  pins its read snapshot. Projection returns the coherent pre-fault source set;
  later ordinary readback detects the corruption. Mixed-time output is not
  produced.

The eight-contender subject demonstrates the tested safety invariant, not
production throughput or a general concurrency proof.

## Context projection contract

`SemanticContextProjector` binds:

```text
AgentRun ID
graph ID / revision / digest
projection profile ID / version / digest
required root node IDs
allowed node types
caller maxima (hard ceiling 128 nodes / 128 relations)
```

Required Goal/Plan roots, their direct connection, active unresolved obligations,
and blocking unresolved ambiguities cannot be silently omitted. If required
content or required relations do not fit, projection fails with
`SEMANTIC_PROJECTION_INCOMPLETE`. Optional omission is explicit through canonical
record/relation digests and never changes the graph.

Projection has no provider/tokenizer dependency and performs no database write.
“Provider-ready” means only that a future adapter can consume the structured
result; no provider rendering or generation is measured.

## Fresh installed reconstruction

The Phase C gate built a wheel on D:, installed it with `--no-deps --no-index`
into a new D-drive target, changed to a separate run directory, and executed
under `python -S` with `PYTHONPATH` pointing only at the install target. A probe
confirmed both `macr_runtime` and `macr_runtime.semantic` resolved beneath that
target. The packaged registry was therefore exercised from the wheel, not the
working source tree.

Two fresh installed runs produced byte-identical content-free JSON for:

```text
create AgentRun
admit / acquire / activate
create empty graph r1
attach AgentRun to r1
propose and commit Goal/Plan as r2
project Goal-to-Plan context
release ownership and reopen
delete Agent and graph-head projections
rebuild Agent and graph head
replay exact attach/commit receipt requests from persisted rows
reproduce projection bytes and digest
```

Observed replay identity:

```text
Agent revision / epoch       6 / 1
Agent events                 6
semantic binding events      2
graph revision / count       2 / 2
semantic events              1
Agent state digest           1149b3cf31bb5250128a4abda3d93d6e326981d310d0cbe5722fe0c313bc8bf9
semantic binding digest      de88e9adb4291d1e255478cc697aebf03844af1085a95e290bee9b488929029a
graph digest                 0e7be3a37de0542d5a0a639aa3a78c71e8f849820f7689fc66979bbdcde1875e
projection digest            db5f74496073e7a98dda0aab5132e276e6cee492c6a9885a4a046f3451f16aaf
attach receipt digest        683b534542699f2a3912eb7634f02ee18d06f07c458d296527b93df469a2c14b
commit receipt digest        046a0ec197a314fbf2b9117766fd12b835b370f50ef935b48443203b33f04362
replay digest                96ef3421b994b57324491c11bec75e3307b5444f4b0dbaa1aae31f031ebd004e
wheel SHA-256                5bb131fcb28f846ef1df260193f43897033a9fe9c1e3b4b66d558cd2bed4b2e1
```

## Source-frozen verification

All commands below exited 0 on `2949d4c` / tree `0ae93b2` with a clean worktree.

```text
.\scripts\verify-v07-phase-c.ps1
  focused tests              95
  required Phase C IDs       47 unique IDs / unique bindings
  installed import isolated true
  fresh package replay       true

.\scripts\verify-v07-phase-b.ps1
  focused tests              76
  required Phase B IDs       69
  phase_c_started            true

.\scripts\verify-v07-phase-a.ps1
  focused tests              91
  required Phase A IDs       68
  phase_b_started            true

.\scripts\verify-v06.ps1
  complete tests             724; OK; 2 existing Windows symlink skips
  targeted tests             127; OK
  summary digest             b107df70512bce35f0472575f724904653fb49c246127eb64b23cfd603841c7a
  schema fingerprint         43ca1e5e8cc0f75b4ac5de1821ce2f8b2d7d5632e7ad0a151910543dc396c0b5
```

Every gate reported `network_activity=false`, `provider_generation=false`, and
`git_clean=true`.

## MSSP Twin record

One task-local read-only Governing Twin was used; no fan-out occurred. Twin
agreement is scoped review evidence, not merge, release, deployment, or live-use
authority.

Retained challenges and resolutions:

1. Graph identity, global head CAS, per-Agent pinning, and transaction ownership
   were initially under-specified. The design now names every boundary.
2. Fresh replay initially skipped attach and confused r1/r2. The exact sequence
   is now empty r1 -> attach -> Goal/Plan r2, with two Agent binding events.
3. A public Agent binding mutator would bypass commit authority. It is private
   and package exports prove no public mutation surface.
4. Graph catalog and removable head were initially one FK parent. They are split
   so history survives head deletion and rebuild.
5. Attach “idempotency” originally changed expected revision on retry. A
   create-once request-digest receipt now resolves exact historical replay and
   rejects operation-ID conflicts.
6. Revision JSON readback originally ignored membership rows. One exact validator
   now checks scalar columns, membership, and referenced records.
7. Rebuild initially bypassed that validator. Read and rebuild now share the same
   connection-bound evidence path.
8. Projection initially used four connections. It now reads Agent binding and all
   graph evidence in one SQLite snapshot, with a deterministic interleave control.
9. The first “fresh” smoke test used repo `src`. The full gate now proves isolated
   installed-wheel imports and byte-identical external replays.
10. The first reopened replay reused in-memory receipts. It now rereads and fully
    compares both persisted receipts after rebuild.

Every targeted reevaluation returned `CONCUR` for its repaired scope. Final Twin
closure is recorded only after the checkpoint commit gates below complete.

## Retained RED and harness corrections

- Task 7 first used SQLite DML `LIMIT`, unsupported by the tested Windows SQLite
  build. That run was discarded; a rowid-subquery probe exposed the intended
  membership product RED.
- Task 9 first named nonexistent `tests.test_semantic_contract_boundaries`, then
  a following diff-check overwrote the Python exit code. The run was discarded;
  the corrected module is `tests.test_agent_contract_boundaries`, with the test
  exit captured before diff-check.
- Earlier focused REDs for missing modules/contracts were retained only after
  collection and fixture correctness were established.

## Closure vector

### Behavioral — PASS

The scoped registry, graph, proposal, governed commit, Agent binding, shared
pinning, revision query/rebuild, and structured projection behaviors execute
through named APIs and pass focused plus inherited offline gates.

### Structural — PASS

The declared architecture reconstructs Agent state, semantic head, persisted
receipts, and projection from a freshly installed wheel without source imports,
Direct DB, provider modules, credentials, or shared runtime state.

### Discriminative — PASS

Forty-seven unique Phase C witnesses plus inherited controls reject registry,
graph, membership, patch, authority, permit, CAS, receipt, atomicity, shared-head,
projection-overflow, snapshot-interleave, privacy, packaging, and Phase D faults
while retaining named authorized equivalents.

These PASS claims are Phase C offline claims, not a global proof of MACR v0.7.

## NotMeasured and deferred

- shared/default Agent database creation, migration, backup, restore, encryption,
  operator adoption, or live route activation;
- provider rendering or calls; Grok, Qwythos/Ollama, GLM, Google, MiniMax,
  Codex, Claude Code, latency, quality, retention, token use, cost, or billing;
- Agent planner/runner/loop, action execution, observation bridge, checkpoint,
  suspend/wake/resume, Phase D, or autonomous semantic evolution;
- cross-machine consensus, distributed fencing, storage-device loss, Byzantine
  behavior, production multi-tenancy, performance, or long-duration operation;
- merge to main, push, tag, release, deployment, publication, or GitHub update.

No credential was read, no provider was called, and no shared runtime state was
mutated while producing this checkpoint.

## Verdict and stop boundary

```text
Phase A                 IMPLEMENTED / OFFLINE VALIDATED
Phase B                 IMPLEMENTED / OFFLINE VALIDATED
Phase C behavioral      PASS
Phase C structural      PASS
Phase C discriminative  PASS
Phase D                 NOT STARTED
Agent loop              NOT IMPLEMENTED
Live use                NOT MEASURED
```

Phase C stops here. Merge, push, release, shared-runtime adoption, and Phase D
require separate operator direction.
