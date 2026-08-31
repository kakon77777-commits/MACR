# MACR v0.7 Phase C Semantic Working State Design

Status: implementation design under MSSP × TDD × APR Twin governance

Date: 2026-09-01

## 1. Exact baseline

```text
repository              D:\Ai\work together\MACR
base branch             main
base commit             60a477cfac179f399a6c50126523c8a55cea4575
base tree               f4d31c31b4c7759f78d72061985ac641136f4ab2
design branch           workbench/v0.7-semantic-working-state
package version         0.6.0a1 (unchanged during Phase C)
Agent runtime schema    1 at baseline
Phase A                 IMPLEMENTED / OFFLINE VALIDATED
Phase B                 IMPLEMENTED / OFFLINE VALIDATED
Phase C implementation  NOT STARTED at design opening
```

Canonical sources:

```text
docs/macr-v0.7/MACR v0.7 — Agent Semantic Envelope Specification v0.1.md
docs/macr-v0.7/MACR v0.7 — AgentRun Canonical State Specification v0.1.md
docs/macr-v0.7/MACR v0.7 — Single-Agent MVP Implementation Plan & Verification Matrix v0.1.md
docs/macr-v0.7/MACR_v0.7_FIELD_INTEGRATION_BASELINE_2026-08-31.md
docs/checkpoints/v07/PHASE_B_AGENT_STATE_KERNEL.md
```

The private `docs/macr-v0.7/future` area is excluded. ISQL Origin is excluded.
NOVA contributes ambiguity, obligation, correction, resolution, proposal/commit,
and back-projection discipline only; its runtime and wire formats are not
dependencies. EML-U, SEDB, MNEME, PNCW, and provider systems remain external
ports or future adapters.

## 2. Phase C goal

Phase C establishes a durable semantic working state so an AgentRun does not use
conversation history as canonical cognition state.

The acceptance target is:

```text
Goal -> Plan
```

through a typed semantic graph, validated patch, durable graph head, exact
AgentRun binding, and ephemeral context projection while the Direct Conversation
database is absent.

Phase C has three bounded closures:

```text
C1  Registry + graph/store + immutable revision history
C2  Proposal-only patches + atomic governed commit + AgentRun binding
C3  Ephemeral context projection + Goal-to-Plan source-free replay
```

## 3. Decisions

### 3.1 Same physical SQLite, independent schema ownership

Phase C uses the existing physical future path:

```text
D:\AI_RESIDENCE\AI_Runtime\macr-state\runtime\agent.sqlite3
```

but keeps two schema components:

```text
agent_runtime   version 2
agent_semantics version 1
```

`AgentDatabase` continues to own connection policy, WAL bootstrap, and
`agent_runtime`. `SemanticSchema` owns only semantic tables and registers its own
component in `schema_meta`. Sharing a file does not merge responsibilities.

### 3.2 One transaction owner

`SemanticCommitService` is the only host/runtime component that may atomically
advance a semantic graph and the corresponding AgentRun binding. It owns one
`BEGIN IMMEDIATE` connection from validation through commit.

Neither `SemanticStore` nor `AgentStore` starts a nested transaction when called
from this service. They expose package-internal connection-bound primitives and
retain their normal standalone read APIs.

### 3.3 Two revision domains

```text
AgentRun state_revision  execution mutation order
Semantic graph_revision semantic graph head order
```

They are not interchangeable. A semantic commit increments both the committing
AgentRun state revision and the target graph revision exactly once, but their
values need not be equal.

### 3.4 Two digest domains

```text
Agent lifecycle state_digest      lifecycle projection integrity
SemanticStateBinding.binding_digest graph ref/digest/revision integrity
```

Phase C does not rewrite Phase B lifecycle digests to embed a graph. Full
AgentRun integrity is the explicit pair of lifecycle projection integrity and
semantic binding integrity. The domains are stored, replayed, and verified
separately.

## 4. Explicit non-goals

- no provider call, model planner, action execution, Direct Chat integration, or
  provider-ready text generation;
- no Phase D real observation bridge;
- no complete Claim/Hypothesis inference engine;
- no obligation-driven Agent completion gate yet;
- no automatic graph branch, merge, rebase, deduplication, or conflict
  resolution;
- no external EML-U/NOVA/ISQL/SEDB/MNEME runtime dependency or migration;
- no large document, prompt, answer, image, diff, hidden reasoning, credential,
  or private plaintext body in semantic SQLite;
- no shared runtime creation/migration during tests;
- no package version promotion, merge, push, release, deployment, or live use.

## 5. Identity model

### 5.1 Graph identity

Each graph has a host-generated canonical UUIDv4 `graph_id`. It is independent
of AgentRun identity and graph content.

```text
graph_id    which durable semantic graph?
graph_digest what is the active graph content?
```

Two graphs may have the same digest. The graph ID disambiguates compare-and-swap
targets and sharing relationships.

### 5.2 Graph revision

A new graph begins at revision 1 with an empty active membership set and a
registry-bound empty digest. Each successful patch produces exactly one new
revision:

```text
revision n -> revision n + 1
```

All revisions remain queryable. The current head is a projection over immutable
revision history.

### 5.3 Graph digest

The graph digest covers:

```text
registry version and digest
ordered active node record digests
ordered active relation digests
```

It excludes graph ID, graph revision number, commit timestamp, event history,
and projection telemetry. Equal active semantic content under the same registry
therefore has equal graph digest even across distinct graphs.

### 5.4 Shared graphs and pinned AgentRuns

A semantic graph may be used by multiple AgentRuns. Each AgentRun is pinned to
one exact graph `(graph_id, revision, digest)`.

When one AgentRun commits a patch to a shared graph:

- the global graph head advances;
- only the committing AgentRun binding advances;
- other AgentRuns remain pinned to their prior immutable revision;
- no silent propagation occurs;
- a later commit from a stale pinned revision is rejected until an explicit
  verified rebase/attach operation is introduced.

Automatic branching, merging, or rebasing is deferred. A caller that needs a
branch must create a new graph through a future explicit operation.

## 6. Phase C proposal and commit requests

The Phase A `SemanticPatch` remains proposal-only and intentionally lacks graph
identity or commit authority. Phase C first wraps it in an immutable
`SemanticPatchProposalRequest` containing:

```text
schema_version
proposal_id                 UUIDv4 create-once identity
graph_id                    UUIDv4 intended graph
agent_run_id                UUIDv4 proposing run
base_graph_revision         positive integer
base_graph_digest           SHA-256
registry_version            bounded version
registry_digest             SHA-256
patch                       existing SemanticPatch
proposal_digest             SHA-256
```

This proposal object contains no Agent revision/epoch, ownership permit,
AuthorizationReference, commit ID, or authority-like boolean. It may be created
from model output only after parsing into the Phase A patch contract.

The host/runtime later creates a distinct immutable `SemanticCommitRequest`
referencing the stored proposal and containing:

```text
schema_version
commit_id                   UUIDv4 idempotency key
graph_id                    UUIDv4 CAS target
agent_run_id                UUIDv4 committing run
base_graph_revision         non-negative integer
base_graph_digest           SHA-256
registry_version            bounded version
registry_digest             SHA-256
expected_agent_revision     positive integer
expected_agent_epoch        non-negative integer
ownership_permit_digest     SHA-256
authorization_reference     existing AuthorizationReference
proposal_id / proposal_digest exact stored proposal binding
patch                       existing SemanticPatch
request_digest              SHA-256
```

Hard invariants:

- `patch.base_graph_digest == request.base_graph_digest`;
- proposal ID/digest and patch digest match the exact stored proposal;
- graph ID, base revision, base digest, registry version, and registry digest all
  match the current head;
- AgentRun ID, expected revision/epoch, permit, and authorization reference all
  match current operational state;
- authorization reference equals the AgentRun's externally established current
  authority binding for this Phase C scope;
- semantic nodes, relations, decisions, text, or relations that appear to
  authorize do not satisfy this authority requirement;
- request digest binds every field and the patch digest.

`commit_id` is create-once. Repeating the exact committed request returns its
stored content-free receipt without another revision. Reusing the ID with a
different request fails closed.

## 7. Agent runtime schema v2

Phase C migrates only `agent_runtime` from version 1 to 2.

### 7.1 AgentRun semantic binding columns

`agent_runs` gains:

```text
semantic_state_digest   nullable SHA-256
semantic_state_revision nullable positive integer
```

Together with the existing `semantic_state_ref`, all three fields must be either
present or absent. The ref is the graph identity reference; digest and revision
pin the exact graph head.

### 7.2 Agent event extension

The closed Agent event set adds:

```text
agent.semantic_state_advanced
```

This event:

- leaves the lifecycle state and epoch unchanged;
- increments AgentRun state revision by exactly one;
- produces a new lifecycle state digest because revision changed;
- carries the previous and new semantic bindings, semantic commit ID, patch
  digest, registry digest, and external authorization digest;
- never derives authority from semantic content.

The SQLite migration rebuilds the event table constraint additively, copies old
rows byte-for-byte, preserves event IDs, payload JSON, payload digests, state
digests, timestamps, and sequence order, then recreates indexes. No historical
event is rehashed or rewritten.

### 7.3 Replay

Phase B lifecycle replay accepts `agent.semantic_state_advanced` as a same-state,
same-epoch, revision-plus-one event. Agent projection rebuild separately derives
the latest semantic binding from these events and restores the three binding
columns. A mismatch between lifecycle tail, semantic event payload, AgentRun
binding columns, and graph revision is visible and never auto-repaired on read.

## 8. Semantic schema v1

`agent_semantics` version 1 owns:

```text
semantic_registry_versions
semantic_graphs
semantic_graph_revisions
semantic_graph_revision_nodes
semantic_graph_revision_relations
semantic_nodes
semantic_relations
semantic_events
semantic_patches
semantic_commit_receipts
```

### 8.1 Registry versions

Registry records are create-once and bind exact canonical bytes, version, digest,
node types, relation types/directions, status types, effect types, verdict types,
and failure types. A registry change does not migrate an existing graph.

The built-in v1 registry is packaged under:

```text
src/macr_runtime/semantic/schemas/registry-v1.json
```

It recognizes the Phase A closed enums. Unknown or extension types fail closed
unless an independently versioned registry is explicitly supplied later.

### 8.2 Graphs and revisions

`semantic_graphs` stores graph identity, scope, current head revision/digest,
registry binding, creator AgentRun, and bounded metadata. It is the current-head
projection.

`semantic_graph_revisions` stores every immutable revision and its parent,
commit/patch references, registry binding, graph digest, and timestamp.

Membership tables bind each revision to exact active node record digests and
relation digests. Historical records remain in `semantic_nodes` and
`semantic_relations` even when no longer active.

### 8.3 Nodes and relations

Phase C persists the existing Phase A `SemanticNode` and `SemanticRelation`
public canonical forms. Content digest and record digest remain separate.

Node record identity is create-once. The same node ID may receive a later record
only through an explicit consumed supersession or typed status update. Silent
overwrite is forbidden.

Active relations reference logical node IDs. Every active relation must have an
active source and target record at the new head and satisfy the registry's exact
direction rule.

### 8.4 Patches, semantic events, and receipts

`semantic_patches` stores proposal and terminal validation/commit status,
request/patch digests, graph/base identity, producer reference, and bounded
failure code. It does not store raw model output.

`semantic_events` stores append-only proposal, commit, correction, resolution,
and status-change evidence with causal parent references.

`semantic_commit_receipts` stores content-free local commit evidence including
commit ID, graph revision/digest, AgentRun revision, semantic event ID, Agent event
ID, patch digest, and commit timestamp.

## 9. Registry and semantic validation

`SemanticRegistry` validates:

- exact known node and relation types;
- status family appropriate to node type;
- relation source/target direction;
- known effect, verdict, and failure classes;
- exact registry version/digest;
- graph scope and extension namespace policy.

The built-in registry is data, not authority. Registering a semantic relation
called `authorizes`, a Decision node, or a policy-looking payload never creates
an `AuthorizationReference`.

## 10. Patch compiler

`SemanticPatchCompiler` performs a pure, no-write compilation from an existing
head and `SemanticPatch` into a `CompiledSemanticPatch`:

1. validate patch and commit-request digests;
2. validate exact base graph identity/revision/digest/registry;
3. validate every proposed node and relation against the registry;
4. resolve existing active node IDs and record digests;
5. reject duplicate IDs or records;
6. validate every relation endpoint and direction against the proposed new
   active node set;
7. compile typed status updates;
8. consume supersession references exactly once;
9. retain ambiguity, obligations, correction, resolution, provenance, and old
   records;
10. calculate the deterministic next active membership and graph digest;
11. emit exact write records without performing SQL.

### 10.1 Status update shape

Each Phase A generic status-update object is interpreted only if it has exactly:

```text
node_id
from_record_digest
to_status
reason_digest
evidence_refs
```

The compiler verifies the old active record, status family, evidence refs, and
allowed transition, then materializes a new node record. Unknown fields or
model-supplied `resolved=true` shortcuts fail closed.

### 10.2 Supersession

Each `supersession_ref` is interpreted as an old active record digest. It must be
consumed by exactly one replacement node or status update. The old record remains
queryable. An unconsumed, duplicate, missing, or cross-graph reference fails.

### 10.3 Ambiguity and obligation

- ambiguity is retained until an explicit resolution event and relation exist;
- selecting one candidate does not delete alternatives;
- unresolved obligations remain active/queryable;
- model text cannot mark an obligation resolved;
- a resolution must carry evidence refs, parent event lineage, and provenance;
- Phase C records blocking obligations but does not yet enforce Agent completion.

## 11. Proposal and commit separation

Agent/model-facing API:

```text
propose_patch(proposal_request)
```

It may validate and persist a proposal but cannot advance a graph.

Host/runtime-facing API:

```text
attach_graph(agent_run_id, graph_id, revision, digest, ownership, authority)
validate_patch(commit_request)
commit_patch(commit_request, ownership_permit, authorization_reference)
```

`attach_graph` is the only Phase C operation that binds an AgentRun to an
existing current graph head without advancing that graph. It requires the same
AgentRun revision/epoch, ownership, and external authority checks as commit,
appends `agent.semantic_state_advanced`, increments AgentRun state revision, and
updates the semantic binding in one transaction. Exact repetition is idempotent;
a different existing binding or stale/noncurrent graph head fails. This explicit
operation enables multiple AgentRuns to pin the same revision without silent
follow behavior.

Revision 1 is deliberate: the existing Phase A `SemanticStateBinding` requires a
positive revision, so an empty graph head must already be bindable without a
special zero-revision exception. The first committed patch advances revision 1
to revision 2.

There is no conversion that copies model-supplied fields into commit authority.
Host/runtime constructs the commit request from the stored proposal plus current
Agent/graph observations, ownership permit, and independently supplied external
authorization.

There is no `model_output_to_db`, `force_commit`, semantic self-authorization, or
implicit conversion from a model response to committed state.

## 12. Atomic commit protocol

`SemanticCommitService.commit_patch()` owns this exact order inside one
`BEGIN IMMEDIATE` transaction:

1. load and verify the AgentRun projection and event tail;
2. compare expected AgentRun revision and epoch;
3. validate the exact unexpired ownership permit/fencing token;
4. validate the external `AuthorizationReference` against AgentRun authority;
5. load the graph and compare graph ID, base revision/digest, and registry;
6. verify the AgentRun's pinned semantic binding, if present, equals the request
   base; a first binding may target only the current graph head;
7. resolve exact-duplicate commit ID idempotently or reject conflicting reuse;
8. compile the patch in memory without writes;
9. insert immutable nodes, relations, semantic event, patch result, graph revision,
   and revision membership;
10. compare-and-swap the graph current head;
11. build and insert `agent.semantic_state_advanced`;
12. compare-and-swap AgentRun state revision/epoch and update semantic ref,
    digest, and revision;
13. insert the content-free commit receipt;
14. commit once.

Fault injection between every write group must roll back all semantic and Agent
halves. There is no automatic retry. A response-loss caller queries commit ID and
receipt before deciding another action.

## 13. Stale and shared-graph behavior

The following all fail before writes:

- wrong graph ID;
- stale base graph revision;
- correct revision with wrong digest;
- wrong registry version or digest;
- stale AgentRun revision or epoch;
- stale, expired, wrong-owner, or wrong-token permit;
- authority mismatch;
- AgentRun pinned to a different graph/head;
- another AgentRun advanced the shared global head;
- patch digest mismatch.

Phase C does not silently rebase. The caller must obtain a fresh head and produce
a new patch or later use an explicitly designed branch/rebase operation.

## 14. Context projection

`SemanticContextProjector` builds an immutable, ephemeral projection from an
exact graph revision. It accepts:

```text
agent_run_id
graph_id / revision / digest
projection profile ID/version/digest
required root node IDs
allowed node types
caller-supplied maximum nodes and relations
```

The output contains deterministic selected node/relation public forms, omitted
record digests, source graph binding, profile binding, and projection digest.

Properties:

- no provider or tokenizer dependency;
- no graph, AgentRun, or database write;
- omission does not stale, supersede, or delete a canonical node;
- a required Goal, Plan, blocking ambiguity, or obligation that cannot fit is
  reported explicitly as incomplete rather than silently omitted;
- hidden reasoning and large/private bodies remain external references;
- equal request and graph revision produce equal projection bytes/digest.

Phase C calls the structured result “provider-ready” only in the sense that a
future provider adapter can consume it. No provider rendering or generation is
measured here.

## 15. Query surface

Read-only APIs are bounded and revision-aware:

```text
get_registry(version)
get_graph_head(graph_id)
get_graph_revision(graph_id, revision)
get_node(graph_id, node_id, revision=None)
get_relations(graph_id, node_id, revision=None)
get_active_goal(agent_run_id)
get_active_plan(agent_run_id)
get_constraints(agent_run_id)
get_ambiguities(agent_run_id)
get_obligations(agent_run_id)
get_patch(patch_id)
get_commit_receipt(commit_id)
build_agent_context(request)
```

All list operations use deterministic cursor pagination and content-free public
metadata where the underlying node payload is not authorized for projection.

## 16. Privacy and content boundary

Semantic SQLite may store bounded structured node payloads already accepted by
the Phase A public contract. It rejects:

- credential-like keys or values;
- authorization headers or private keys;
- local absolute paths;
- raw prompt/answer/model-response bodies;
- hidden reasoning;
- bytes, non-finite numbers, duplicate JSON keys, or unbounded text;
- large document/media/diff bodies.

Large or private content is represented by an external ref, SHA-256 digest,
media type, byte count, and access-policy ref. Such a reference is not permission
to read the external body.

## 17. Failure taxonomy

Stable Phase C codes include:

```text
SEMANTIC_SCHEMA_UNSUPPORTED
SEMANTIC_REGISTRY_UNKNOWN
SEMANTIC_REGISTRY_MISMATCH
SEMANTIC_GRAPH_NOT_FOUND
SEMANTIC_GRAPH_ALREADY_EXISTS
SEMANTIC_GRAPH_HEAD_STALE
SEMANTIC_GRAPH_DIGEST_MISMATCH
SEMANTIC_PATCH_ALREADY_EXISTS
SEMANTIC_PATCH_CONFLICT
SEMANTIC_PATCH_INVALID
SEMANTIC_NODE_CONFLICT
SEMANTIC_RELATION_DANGLING
SEMANTIC_RELATION_DIRECTION_INVALID
SEMANTIC_STATUS_TRANSITION_INVALID
SEMANTIC_SUPERSESSION_INVALID
SEMANTIC_SCOPE_ESCALATION
SEMANTIC_COMMIT_AUTHORITY_INVALID
SEMANTIC_COMMIT_PERMIT_INVALID
SEMANTIC_AGENT_BINDING_CONFLICT
SEMANTIC_PROJECTION_INCOMPLETE
SEMANTIC_PROJECTION_CONFLICT
```

Errors are sanitized and contain no raw payload, local path, credential, prompt,
or answer. Unknown is not converted to false or generic.

## 18. TDD and fault subjects

At minimum, Phase C must bind positive and falsifying witnesses for:

### Registry and graph

- exact registry bytes/version/digest;
- unknown node/relation/effect/status rejection;
- deterministic empty and non-empty graph digests;
- graph identity separate from graph digest;
- immutable revision history and active head;
- relation direction and dangling endpoint rejection.

### Patch and commit

- proposal does not advance graph or AgentRun;
- exact base `(graph_id, revision, digest, registry)` CAS;
- stale shared head rejection;
- duplicate exact commit ID idempotence and conflicting reuse rejection;
- node overwrite, partial patch, scope escalation, bad supersession, and bad
  status update rejection;
- model-created authority-looking semantics cannot commit;
- receipt cannot become verification automatically;
- confidence cannot override failed verification;
- ambiguity/obligation/correction/resolution history is retained.

### Cross-component atomicity

- fault after semantic records but before graph head;
- fault after graph head but before Agent event;
- fault after Agent event but before AgentRun binding update;
- fault after Agent binding but before receipt;
- every fault leaves graph head, revision membership, Agent event tail, AgentRun
  revision/binding, and receipt unchanged;
- committed semantic state and AgentRun binding always agree after reopen;
- Agent projection rebuild restores semantic binding from Agent events.

### Projection

- Goal-to-Plan projection without Direct Conversation DB;
- deterministic projection digest;
- omitted context does not delete canonical records;
- required-item overflow is explicit incomplete;
- private/large content remains reference-only;
- no provider, network, or shared state.

## 19. Three closure claims

Behavioral closure requires the scoped C1-C3 API and Goal-to-Plan scenario to
work offline.

Structural closure requires a fresh installed-wheel subject outside the source
tree to create an AgentRun, initialize a graph, propose and commit Goal/Plan,
reopen, verify graph/Agent binding, remove rebuildable projections, reconstruct,
and reproduce the same structured context projection.

Predeclared structural equivalence:

```text
same graph ID and revision history
same active node/relation record digests
same graph digest
same AgentRun lifecycle revision/epoch and semantic binding
same semantic and Agent event identities/counts
same commit receipt
same context projection bytes/digest
no Direct DB, provider, network, or live ownership after terminal test cleanup
```

Discriminative closure requires every named negative axis to retain a nearby
authorized-equivalent green control and manifest-bound unique test identity.

## 20. Version, migration, and rollback boundary

- `agent_runtime` migration v1 to v2 is additive except for the controlled event
  table constraint rebuild; old rows remain byte-identical.
- `agent_semantics` begins at v1 and never imports v0.6 history as semantic truth.
- historical provider, Direct, Candidate Vault, Observatory, accounting, and
  Phase B data remain unchanged.
- migration tests begin from an exact v1 fixture and prove row/event preservation.
- newer or inconsistent component versions fail closed.
- no automatic downgrade mutates either component.
- tests use disposable D-drive databases only.

## 21. Acceptance and stop boundary

Phase C may be reported complete only when an exact clean commit/tree proves:

```text
SemanticRegistryBound       true
SemanticGraphVersioned      true
SemanticPatchAtomic         true
AgentBindingAtomic          true
SemanticAuthoritySeparated  true
GoalToPlanWithoutDirectDB   true
ContextProjectionEphemeral  true
BehavioralClosure           PASS
StructuralClosure           PASS
DiscriminativeClosure       PASS
network_activity            false
provider_generation         false
Phase D started             false
```

Checkpoint verdict:

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

Implementation stops at Phase C. No Phase D observation bridge, Phase E action,
provider loop, merge, push, release, deployment, or shared-runtime activation is
authorized by this design.
