# MACR v0.7 Hosted Agent Cell precursor for reserved v0.7.0a1

Date: 2026-09-12

Status: offline implementation precursor under package `0.7.0a0`; canonical
`0.7.0a1` remains unissued; no shared Agent adoption or live provider call

## Precursor target

Add one bounded host-owned execution cell above the existing Phase A-C Agent
and semantic kernels. A model endpoint remains replaceable cognition; durable
continuity belongs to one exact `AgentRun`, not to a provider/model name.

This slice is evidence toward the reserved `0.7.0a1`; it is not the canonical
Phase A-H closure and does not change the package, CLI, Direct UI, or release
version from `0.7.0a0`.

The MVP must execute this offline vertical slice:

```text
active AgentRun + pinned semantic projection
  -> provider-ready hosted context envelope
  -> one closed model decision
  -> host-validates one read-only tool request
  -> private tool result becomes next-turn context
  -> final candidate enters Candidate Vault
  -> exact cell checkpoint can be rehydrated under a new fencing epoch
```

## Existing canonical owners

- `AgentStore` owns AgentRun identity, state, revision, epoch, and ownership.
- `SemanticContextProjection` owns deterministic Phase-C graph projection.
- Action contracts own proposal/admission vocabulary.
- `AgentCheckpoint` owns canonical checkpoint identity.
- `CandidateVault` owns final candidate bytes.
- Provider runtime/admission/accounting continue to own real provider calls.

The cell wraps these objects. It does not redefine Context Capsule, semantic
projection, authority, verified observation, checkpoint, provider admission,
or acceptance.

## Persistence boundary

`runtime/agent.sqlite3` gains a separate `hosted_agent_cell` schema component.
Its tables are content-free: IDs, refs, digests, counters, bounded states, and
timestamps only. Provider-ready context, initial briefing text, model decision
bytes, tool arguments, and tool-result bytes are immutable blobs under:

```text
<MACR_STATE_ROOT>/agent-cells/<agent-run-id>/<closed-role>/<sha256>.bin
```

Context cache is derived, deletable, and byte-rebuildable. It never proves
freshness, authority, or completion.

## Runtime boundary

- Policy is bound to AgentRun, exact provider/model/token policy, a
  credential-free provider execution-profile digest (endpoint/model/reasoning/
  privacy/capabilities/tier/admission/transport mode), prompt
  compiler, delegation/privacy class, capability tier, project admission lane,
  exact tool catalog, and finite step/provider/tool/wall/currency/latency/
  context/output limits. Limits are per cell; there is no universal worker
  count. `project_ref` is an opaque identifier and cannot serialize a local
  path into `agent.sqlite3`.
- The provider bridge accepts one exact task template. Task ID is derived from
  AgentRun epoch/step/invocation ID; goal, task type, workspace, verification,
  capabilities, return contract, policy clauses, and the sole UTF-8 context
  input are host-compiled and checked before MACR dispatch. The TaskContract
  digest is recomputed, while `DispatchContext` binds the same preallocated
  provider invocation, token policy, tier, project, lane, admission policy,
  and cell-policy snapshot.
- The model grammar has exactly `tool_request` and `final_candidate`.
- Model output is a proposal. Unknown tools, malformed arguments, path escape,
  stale ownership, and exhausted budget execute nothing.
- The initial registry contains only bounded read-only workspace list/read/
  search tools. No process, write, network, credential, browser, or MCP tool is
  in this slice. The tool-catalog digest binds a hash of the resolved workspace
  root, approved relative prefixes, file/scan/result limits, and a finite
  examined-entry ceiling. List/search results expose `truncated=true` for entry,
  byte, result-size, match, inaccessible, oversized, or non-UTF-8 omissions.
- Every model attempt and admitted tool action is preallocated before external
  execution. A dispatch without a terminal record blocks rehydration and is
  never silently retried.
- The last permitted model call may consume its already-paid final/tool
  decision before the next-dispatch budget gate runs. A known response cost
  above either the per-call ceiling or remaining total is instead preserved as
  a typed terminal failure and cannot execute a tool or complete the AgentRun.
- Final candidate uses a separate preallocated candidate run UUID linked to the
  AgentRun/step; `DispatchContext.run_id` and `agent_run_id` never collapse.
- Provider-visible context cannot change while a model/tool operation is
  pending, and context append rechecks cell authority under the write lock.
  Final evidence references must occur in the exact verified context-envelope
  blob used by the final model dispatch; later current-state existence is not
  sufficient.
- Cell checkpointing releases ownership while AgentRun stays ACTIVE. Rehydrate
  requires a fresh ownership epoch and an exact checkpoint/snapshot match.
  This is not Phase-F suspend/wake/resume and emits no `ResumeRecord`.
- A durably observed no-response provider call remains
  `reconciliation_required` and consumes one global and one project capacity
  unit. It does not consume every remaining provider slot. Missing terminal
  evidence and explicit provider pressure (HTTP 429/5xx) still open the global
  circuit. There is no automatic retry or cost-zero inference.
- The changed uncertainty semantics use new policy digests (GLM revision 3,
  Grok revision 2). Historical GLM r1/r2 and Grok r1 reopen by exact stored
  digest. An old OPEN unknown episode can move forward without resolving its
  charge only through a reviewed transition binding that includes an exact
  reconciliation-isolation evidence digest plus a database-derived digest of
  the current control head and ordered unresolved request set. Apply recomputes
  the database snapshot inside the policy-transition write transaction. The
  old request/accounting rows remain unchanged and continue consuming capacity.
  Any pressure signal in the same OPEN episode or any snapshot drift refuses
  that isolation transition.

## Closure witnesses

1. deterministic model requests read, receives exact result, then completes;
2. every causal digest changes cache identity, while cache deletion rebuilds
   byte-identical context;
3. unknown tool, malformed arguments, and path escape dispatch no tool;
4. provider/tool/step/wall/currency bounds stop before the next operation and
   survive fresh-store rehydration;
5. checkpoint rehydrates in a fresh process/store under a newer fencing epoch
   without duplicating completed model/tool operations;
6. a concurrent second owner loses;
7. pending model/tool dispatch or a tampered checkpoint fails closed;
8. malformed or multiple model decisions cannot mutate AgentRun or execute a
   tool;
9. Agent DB contains no briefing, candidate, tool-result, path, or credential
   canary; private blobs contain the expected bytes;
10. the real Grok and GLM adapters each complete exactly one fake-transport
    invocation through v3 authority and the shared admission kernel; stale
    GLM approval or authority performs zero transport;
11. one durably recorded unknown provider call reserves exactly one capacity
    unit while another project may use remaining capacity; missing terminal
    evidence still opens the global circuit;
12. Direct Chat and ordinary `invoke` compatibility gates remain green.

## Explicit non-closure

This slice does not close canonical Phase D, E, F, or G. It has no
`VerifiedObservationRef` promotion, write/process tools, semantic mutation,
automatic provider authorization, GLM approval bypass, Grok/GLM live model
network exercise, production HostedTurnPreparer/CLI, wake scheduler, autonomous
acceptance, retry, fallback, or shared Agent database activation. The tested
provider bridge uses the real adapters and admission path with injected offline
transports; that is not a live-route claim. Those remain separately gated
follow-up work.
