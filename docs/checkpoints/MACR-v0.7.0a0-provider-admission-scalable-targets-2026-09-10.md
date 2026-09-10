# MACR v0.7.0a0 Provider Admission scalable targets — offline checkpoint

Date: 2026-09-10

Status: offline implementation candidate; shared runtime and live provider unchanged

## Exact subject

```text
branch  feature/provider-admission-scalable-targets
commit  e55f1a4ccc8fe8be0020da6b807d62a59a4a778b
tree    4e67225937c1a7ac55c6052a61e1296d350808f0
state   clean
```

## Superseding operator direction

The operator explicitly rejected target 2 as a standing product ceiling: many
projects and conversations use GLM concurrently, spending is operator-owned,
and MACR's job is to bound, schedule, account, observe, and stop unsafe states
rather than enforce an unnecessarily small concurrency number.

Z.ai documents concurrency as account/plan-specific and identifies HTTP 429 or
business code 1302 when concurrency is exceeded. No universal account value is
published:

- https://docs.z.ai/guides/overview/concept-param
- https://docs.z.ai/api-reference/api-code

## Policy revision 2

```text
capacity_unit       1
effective_target    8
candidate_target    16  (review marker only)
hard_max            32
per_project_cap     8
```

An exact one-use authority may select any integer target from 1 through 32.
Backlog and T1 `worker_count` may be larger. There is no unlimited sentinel,
automatic increase, provider retry, or cost-based refusal. The finite 32 is a
local software guard, not a z.ai service-capacity claim.

Target and half-open activation now revalidate their exact authority inside the
same `BEGIN IMMEDIATE` transaction that consumes it and appends the receipt.
This closes an independently reproduced precheck-to-consume epoch/revocation
race.

Policy revision 1 state is not silently rewritten or promoted. Reopening an
initialized `1/2/8/2` database with revision 2 fails closed with unchanged
state, policy rows, and receipts. The canonical shared runtime was still schema
7, so no revision-1 Provider Admission state existed there.

## Verification

The complete test discovery first encountered five red results. One was a real
stale single-slot test assumption and was repaired by explicitly selecting a
one-slot test policy. The other four were global census controls correctly
observing unrelated concurrent MACR/GLM activity; they were not reclassified as
green or attributed from timing.

Exact-subject evidence after repair:

```text
all modules except global-census module     874 OK / 2 platform skips
non-census multiprocess module tests          6 OK
admission/runtime/T1 focused                 58 OK
16-process scalable admission          8 granted / 8 BUSY
global invoker observation                    1 matching process
network/provider calls by this work           0
production credential reads                   0
```

The governing Twin independently reproduced the stale-epoch target-32 attack
against the earlier candidate, causing the lock-local authority repair. On the
exact subject above the Twin returned `CONCUR`: stale target activation raised
`DispatchAuthorizationError`, effective target remained 8, receipt count
remained 1, circuit-authority revocation also failed without projection drift,
and the 16-process result was exactly 8 grants / 8 BUSY.

The four full-machine census tests and the composite v0.6/Phase-C gates remain
pending a naturally quiet window. This checkpoint does not claim those gates
passed. It does claim behavioral, structural, and discriminative closure for
the scalable capacity slice under isolated D-drive state and fake transports.

## Authority boundary

No shared-runtime migration, production credential read, real provider call,
target activation, retry, fallback, tag, release, or deployment occurred. A
merge or publication decision does not activate policy revision 2. Live use
still requires a separately authorized, quiescent schema-7-to-8 initialization
and subsequent observed operation.
