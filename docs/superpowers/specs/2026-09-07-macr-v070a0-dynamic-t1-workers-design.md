# MACR v0.7.0a0 dynamic T1 workers design

Date: 2026-09-07

## Decision

T1 no longer treats the three-worker pressure-test shape as a product limit.
Each private execution manifest declares two independent quantities:

- the ordered member list is the exact work set;
- `worker_count` is the number of authorized dispatcher slots available to
  consume that work set.

`worker_count` is explicit, canonical, and covered by the manifest digest. It
must be an integer from one through the member count. The authorized dispatcher
list must contain exactly that many unique identifiers. Member count may exceed
worker count; an authorized dispatcher may be invoked again after completing a
member to claim later queued work.

There is no product-wide maximum of three, four, eight, or another arbitrary
worker count. The strict 4 MiB private-manifest input limit remains the bounded
resource envelope. Provider capacity, operating-system process capacity, and
operator-selected concurrency remain operational concerns rather than silently
encoded protocol constants.

## Cost semantics

The former USD 0.010 member, USD 0.030 aggregate, and USD 0.040 campaign
constants are removed from the T1 manifest contract.

Every member must carry a positive exact cost ceiling equal to its
`TaskContract` ceiling. The manifest aggregate must equal the mathematical sum
of all member ceilings. The operator-selected campaign ceiling must be greater
than or equal to that aggregate. All values and relations are digest-bound and
validated before staging, authority issue, queue mutation, credential access,
or transport.

This change makes the envelope configurable; it does not remove per-member
provider admission, accounting records, aggregate reconciliation, or the
warn-only shared budget policy selected elsewhere by the operator.

## Compatibility

The current contract is T1 manifest schema 4 with
`t1_execution_member_v4` and `t1_execution_manifest_v4` digest domains.

Schemas 1, 2, and 3 remain readable only through the content-free inspection
surface. Their statuses are respectively `legacy_pre_tier`,
`legacy_pre_quality_floor`, and `legacy_fixed_three_workers`. They cannot stage
or dispatch and are never rewritten or silently interpreted as schema 4.

The topology identity remains `T1_FANOUT_VERIFIED`; the schema version, not a
new unrelated topology label, carries the dynamic-worker contract change.

## Retained safety boundaries

- one queue member permits at most one provider attempt;
- no automatic retry or provider fallback;
- ambiguous dispatch blocks later claims through global reconciliation;
- task, route, policy, tier, approval, role, privacy, target, cost, expiry, and
  dispatcher evidence remain exact and digest-bound;
- provider completion remains a candidate, not verification, materialization,
  acceptance, merge, release, or deployment;
- staging performs no provider call, and this implementation change performs no
  paid provider call.

## Operator surface

`t1-stage` reports both `member_count` and `worker_count` and verifies that the
repeated `--dispatcher-id` arguments exactly match the manifest. `t1-worker`
reports the same counts and claims at most one member per invocation. Operators
may launch the number of concurrent worker invocations declared by
`worker_count`, and may invoke an authorized dispatcher again while work remains
queued.

Automatic process-pool sizing, provider rate adaptation, and autonomous cost
throttling are deliberately outside this change. They can be added later using
observed accounting and provider-capacity evidence without changing the exact
schema-4 meaning.
