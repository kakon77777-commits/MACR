# MACR v0.7.0a0 Provider Admission Kernel — offline checkpoint

Date: 2026-09-10

Status: offline implementation candidate; not merged, released, deployed, migrated, or live-activated

## Exact implementation subject

```text
branch  feature/v070a1-provider-admission-kernel
commit  7a395e0654e1d0381ac47da7b34f6ca5e60fef9d
tree    ccafa43033eed24c6b645f9a84141c0ba1b60784
state   clean
```

The package version remains `0.7.0a0`. The reserved `0.7.0a1` Agent MVP was
not consumed and Agent Phase D was not started.

## Implemented boundary

- Runtime schema 8 adds one provider-wide, cross-process admission kernel.
- GLM policy revision 1 starts at effective target 1, records candidate target
  2, retains hard ceiling 8, raw capacity unit 1, and per-project cap 2.
- Member count and T1 `worker_count` remain operator-selected demand; neither
  silently changes provider capacity.
- Project binding, lane, provider policy, model-token policy, capability tier,
  task/member identity, run, and dispatch authority are exact-bound.
- Provider target/circuit control uses an append-only receipt chain matched to
  the active projection. In-range target and circuit tampering fail closed.
- Half-open consumes one exact authority and names one exact interactive probe
  request. A different request, authority replay, cancellation, or known local
  failure cannot close the circuit.
- The final transport edge rechecks expiry, control receipt, unresolved state,
  circuit state, exact probe, and dispatch authority under one SQLite
  `BEGIN IMMEDIATE` lock.
- A pre-dispatch runtime refusal cancels its unused provider grant. A T1 member
  is atomically returned to `queued/attempts=0` rather than being burned.
- Production/default GLM transport is bound to the operator-selected canonical
  runtime path and its persisted deployment digest. Alternate temp databases
  are explicit `offline_test` capabilities and cannot be reopened as canonical.
- A main-derived schema-7 fixture is replayed additively. Legacy nonterminal
  runs or active dispatch leases block admission genesis until external
  quiescence is established.

## Primary verification

All commands ran from the exact clean implementation subject with D-drive test
state and no provider/network generation.

```text
full unittest discovery       880 passed, 2 platform skips, 0 failures
verify-v06 inherited          880 passed, 2 platform skips, 0 failures
verify-v06 focused            198 passed, 0 failures
verify-v06 summary SHA-256     7cb3f1ed3af759d14e7b5e54354441bdd4db09912b8c356b760712c8ee3ce003
runtime schema                8
T1 complete-path processes    5
SQLite bootstrap processes    32
quiet census samples          5
network_activity              false
provider_generation           false

Phase-C inherited             880
Phase-C focused               98
Phase-B / Phase-A focused     76 / 91
required test IDs             50
fresh package replay          true
installed import isolated     true
wheel SHA-256                 1b011b4e87998b109f4b8da1b5ae334f2d048ecdff57afb1d3f96653955f0743
network_activity              false
provider_generation           false
phase_d_started               false
```

The shared canonical database remained runtime schema 7 after both gates.

## Governing Twin result

The same read-only Twin first rejected earlier green subjects for four
structural gaps and then for two additional transport-edge gaps. On the exact
subject above, the Twin reran 105 focused tests with one existing Windows
symlink capability skip and independently replayed the decisive attacks:

```text
expired grant                 rejected; reconciliation_required; circuit open
429 supersedes sibling grant rejected; unused sibling cancelled; circuit open
alternate concrete kernel     rejected; key reads 0; fake transport posts 0
primary + cleanup failure      primary preserved; cleanup retained as cause/note
```

Closure vector: Behavioral `PASS`, Structural `PASS`, Discriminative `PASS`
for the offline Provider Admission Kernel slice only.

## Retained limits and trust boundary

- Target 2 is a bounded candidate, not live-accepted capacity. Values 3–8,
  automatic promotion, refill algorithms, and provider-safe concurrency remain
  `NotMeasured`.
- No automatic retry, fallback, acceptance, materialization, merge, release,
  deployment, or provider call is authorized by this checkpoint.
- Canonical uniqueness trusts that the operator selects and protects
  `MACR_STATE_ROOT` and the canonical factory. It is not OS/service-level
  attestation. If untrusted project processes can rewrite that environment or
  construct an alternate claimed deployment, a separate hardening project is
  required.
- Shared runtime schema migration and live target activation require separate
  operator decisions after exact preflight and quiescence checks.
