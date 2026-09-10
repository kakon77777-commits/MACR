# MACR v0.7.0a0 Provider Admission Kernel Design

Status: approved implementation design; offline feature candidate

Date: 2026-09-10

## 1. Problem

MACR already separates T1 member count from `worker_count`, but every manifest
chooses demand independently. Ordinary CLI, T0, host-adapter and T1 paths do
not share a provider-wide capacity authority. Unrelated GLM task IDs acquire
different resource leases, so several projects can collectively exceed the
provider or local account capacity even when each project is internally valid.

The opposite failure is a fixed-small global worker count: it strands cheap
provider capacity and forces every project through one manually serialized
lane. An unbounded value is also invalid because provider limits, network
health and billing ambiguity are external and time-varying.

## 2. Version and phase boundary

This work remains a `0.7.0a0` feature candidate. `0.7.0a1` remains reserved
for the later bounded A-H Single-Agent MVP. Provider admission is a lower
operational network gate; it is not Phase D verified observation and does not
replace Phase E semantic action/authority/effect admission.

No provider call, shared-state migration, live capacity promotion, retry,
fallback, verification, acceptance, release or deployment is part of the
offline implementation candidate.

## 3. Core distinction

```text
queued work / manifest worker_count = demand
provider admission effective_target = currently admitted in-flight capacity
operator hard_max                  = absolute configurable ceiling
```

Member/backlog size may be large. Only in-flight provider attempts are hard
bounded. Spending remains independently accounted and warn-oriented according
to operator policy; money is not used as a concurrency semaphore.

## 4. Initial measured boundary

For GLM the immutable built-in policy declares:

```text
capacity_unit       1 per provider request
effective_target    1
candidate_target    2
hard_max            8
```

Only target 1 is initially effective. Target 2 is a bounded future live-probe
candidate. Capacity above 2, weighted capacity units, lane weights, refill
rate, burst size, automatic promotion and concurrency safety are
`NotMeasured`. There is no zero or unlimited sentinel.

## 5. Authority-bound admission identity

`ProjectAdmissionBinding` contains a bounded operator project ID, revision and
binding source and yields a canonical digest. `AdmissionLane` is one of
`interactive`, `routine`, or `bulk`.

Neither value may be derived from task text, workspace `repo`, cwd, semantic
scope, model output or a host-supplied display label. Dispatch authority scope
contract v3 binds the exact project-binding digest and lane. Existing v1/v2
authorities remain readable but cannot admit a governed GLM request and are
classified `legacy_pre_provider_admission`.

The ordinary CLI is an operator assertion boundary and binds its selected
project/lane into the authority it issues. Host adapters consume a pre-issued
grant containing the same binding. T1 staging creates a separate admission
binding over the existing schema-4 manifest digest; it does not rewrite the
schema-4 digest domain. Already staged bundles without the binding are legacy
and cannot dispatch.

## 6. Operational state

Runtime schema 8 adds provider-admission tables to the canonical shared
`runtime/dispatch.sqlite3`:

- immutable provider admission policy rows, one effective projection and an
  append-only control-transition receipt chain;
- bounded content-free admission requests;
- granted/dispatched/reconciliation lifecycle and fencing tokens;
- per-project active counts and last-grant order;
- circuit state and the last bounded capacity signal.

Every permit binds provider/capacity domain, project-binding digest, lane,
run ID, dispatch-authority digest/epoch, task or member digest, provider-tier
binding, policy digest and the raw capacity unit `1`.

Waiting requests may expire or be cancelled because no provider attempt
occurred. A granted/dispatched permit never disappears by TTL. Expiry or a
process crash moves it to `reconciliation_required`, continues consuming or
blocking capacity, and requires an explicitly authorized resolution.

## 7. Admission and fairness

The primitive `try_admit` is atomic and nonblocking. A local wrapper may keep
the task bytes in its own process and poll a content-free request for a bounded
time; this wait is not a provider retry.

Grant selection uses raw unit slots. Project scheduling order, capacity units
and currency accounting are orthogonal. Equal project fairness is based on the
least-recently-granted eligible project and then request order. Interactive is
next-slot priority rather than a permanently idle reservation; when effective
target is one, bulk capacity therefore never becomes zero. Continuous
interactive demand must not starve older non-interactive requests.

Per-project caps are policy values and unused capacity is borrowable. A caller
cannot evade the cap by changing an unbound project string.

## 8. Runtime and adapter enforcement

All orchestrated GLM paths converge on the admission kernel before dispatch
event, accounting dispatch, credential read or transport. Capacity saturation
is a typed nonterminal `BUSY`, not `candidate_failure`, and produces no provider
attempt evidence.

The GLM adapter independently consumes and validates the same one-use permit
immediately before key/transport access. Its public `invoke` and
`invoke_observed` methods reject calls without a valid production permit.
The adapter requires the concrete shared `ProviderAdmissionKernel`; a
duck-typed/no-op guard and a different real kernel are rejected before key
access.

Known pre-network cancellation releases a grant. A fully persisted terminal
response closes it. `network_attempted=true` plus no response, incomplete
terminal persistence or an expired dispatched permit enters reconciliation.
HTTP 429/5xx, response presence and duration may be recorded as bounded
capacity signals. Candidate quality, verification, acceptance and estimated
cost are never capacity signals.

## 9. T1 ordering

T1 must obtain an admission grant for the next exact member before changing
the member to `claimed/attempts=1`. The queue then claims that exact member and
the runtime consumes the pre-granted permit. If capacity is busy, the member
remains `queued`, `attempts=0`, with no dispatch event, accounting row, key read
or transport call. If a race invalidates the peeked member, the unused
pre-network grant closes safely and the worker returns a nonterminal deferred
result. Any runtime refusal before a dispatch event atomically returns the
claimed member to `queued/attempts=0` and cancels the unused provider grant.

`worker_count` remains valid demand even when it exceeds effective provider
capacity. It never changes the provider target.

## 10. Adaptation and circuit boundary

The first candidate implements observable state and explicit governance, not
unattended auto-scaling. A future exact authority may promote candidate target
2 after a bounded live probe. Values above 2 remain unavailable until measured
and superseded by a new policy revision.

Unknown network outcome opens reconciliation and cannot be blind-retried.
Provider circuit `open` or unresolved capacity state prevents new grants.
Half-open consumes a separately authorized one-use transition and binds the
slot to one exact request digest. A different request cannot take that slot;
a pre-network failure reopens the circuit because it proves nothing about
provider recovery. No fixed cooldown is claimed from current evidence.

## 11. Read-only surfaces

`admission-status` returns bounded content-free policy, target, active/waiting/
reconciliation counts, per-project digest counts, lane counts, circuit state
and legacy counts. It never prints task bodies, answers, paths, credentials or
raw provider messages and performs no migration when the database is absent.

## 12. Recovery

Schema migration is additive and copy-tested from an independently captured
schema-7 fixture generated by `main@f806fdb`. Normal rollback is a governed
forward policy transition, never replacement of a live runtime database.
Existing runtime event, authority, T1, candidate and accounting rows remain
byte/logically equivalent. Provider capability and model-token policy digests
are unchanged.

## 13. Acceptance

### Behavioral

- cross-process attempts never exceed effective target or per-project cap;
- BUSY is nonterminal and performs no provider/key/accounting/event work;
- T1 saturation leaves the exact member queued with attempts zero;
- ordinary CLI, T0, host adapter and T1 cannot bypass the kernel;
- GLM direct invocation without a valid permit fails before key/transport;
- known terminal outcomes close capacity, unknown outcomes reconcile;
- target/circuit projections match immutable receipts and half-open consumes
  one exact authority for one exact probe.

### Structural

- fresh schema-7 to schema-8 replay is additive and deterministic;
- all GLM transport paths backtrace to the same one-use permit verification;
- project/lane identity backtraces to exact dispatch authority;
- capability, token, approval and T1 v4 digests remain unchanged;
- in-range target/circuit tampering fails even when values satisfy SQL checks.

### Discriminative

- forged project/lane, v2 authority, replayed permit, stale fencing token,
  redirected production state, expired dispatched permit and direct adapter
  call are rejected for their own reason;
- replayed circuit authority, wrong half-open probe and pre-network probe
  failure remain distinct fail-closed cases;
- valid distinct projects share target slots without identity collision;
- interactive next-slot priority accepts bulk progress at target one;
- worker demand above capacity remains valid and drains without extra attempts.
