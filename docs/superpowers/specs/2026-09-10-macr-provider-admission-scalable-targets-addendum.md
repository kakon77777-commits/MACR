# MACR Provider Admission — scalable target addendum

Date: 2026-09-10

Status: implementation input; live provider behavior remains unmeasured

Supersedes only the revision-1 capacity constants in the original Provider
Admission Kernel design. Permit identity, project fairness, exact authority,
append-only receipts, final-lock revalidation, circuit handling, accounting,
and candidate-only output semantics remain unchanged.

## Operator direction

The operator runs many projects and conversations concurrently. Cost is
operator-owned and already recorded separately; MACR must not use a two-request
product ceiling as a substitute for accounting. Capacity remains finite, but
the operator must be able to choose it without a source-code rewrite.

Z.ai's public documentation says concurrency quotas vary by account or plan and
that overages may return HTTP 429 or business code 1302. It does not publish one
universal safe number for this account:

- https://docs.z.ai/guides/overview/concept-param
- https://docs.z.ai/api-reference/api-code

## Revision-2 policy

```text
capacity_unit       1
effective_target    8
candidate_target    16  # compatibility field; next review marker only
hard_max            32
per_project_cap     8
```

`ProviderAdmissionTargetBinding` accepts every exact integer from 1 through the
active policy's `hard_max`. A separately issued authority still binds one exact
target digest and is consumed once. There is no zero, negative, null, infinity,
or unlimited sentinel. There is no automatic increase or retry.

The built-in maximum 32 is a local finite software guard, not a claim that z.ai
will accept 32 simultaneous calls. The provider circuit remains responsible for
known 429/5xx and ambiguous outcomes. A later live campaign may retain, lower,
or raise the effective target through a new forward authority transition.

## Compatibility

Policy revision 2 has a new digest. A runtime already initialized under the
revision-1 `1/2/8/2` policy cannot silently gain capacity: initialization with
revision 2 fails closed with no state or receipt rewrite. Canonical runtime
discovery continues operating the exact active revision-1 policy until an idle
forward transition is explicitly authorized. That transition binds both policy
digests/revisions and the selected successor target, revalidates authority under
the write lock, preserves the old policy/receipt rows, appends
`policy_superseded`, and then exposes revision 2.

## Required evidence

- policy contract accepts `8/16/32/8` and rejects values outside 1–32;
- exact target transitions succeed at representative values 1, 7, 16, 24, 32;
- sixteen synchronized distinct projects receive exactly eight default grants
  and eight BUSY results;
- an exact downgrade to target 2 still permits only two grants;
- per-project cap, fairness, BUSY, receipt, circuit, expiry, and transport-edge
  attacks remain green;
- legacy revision-1 state cannot be silently upgraded;
- target and half-open activation revalidate authority inside the same write
  lock that consumes it, closing epoch/revocation races;
- full repository, v0.6 compatibility, and Phase-C gates remain offline.

This addendum authorizes no shared-runtime migration, provider call, target
activation, merge, publication, release, or deployment by itself.
