# MACR v0.7.0a0 Provider Admission Kernel Implementation Plan

Status: active implementation plan

Design: `docs/superpowers/specs/2026-09-10-macr-v070a0-provider-admission-kernel-design.md`

## Slice 1 — contracts and schema

- Add pure admission policy, project binding, lane, request, permit, decision
  and status contracts.
- Extend dispatch authority scope to v3 project/lane binding while preserving
  v1/v2 parsing and explicit legacy refusal.
- Add runtime schema 8 tables and additive migration tests.
- RED/GREEN: validation, no-unlimited sentinels, exact digests, schema-7 replay,
  corrupt/partial state rejection.

## Slice 2 — atomic provider kernel

- Implement atomic content-free request/grant lifecycle at raw unit 1.
- Enforce global target, hard ceiling, per-project cap and bounded fairness.
- Implement cancel-before-dispatch, one-use transport transition, known
  terminal close and reconciliation-required outcomes.
- RED/GREEN: synchronized multi-process target/cap, replay/stale-token attacks,
  expired waiting versus expired dispatched behavior, circuit blocking.

## Slice 3 — runtime and GLM transport boundary

- Add admission identity to `DispatchContext` and dispatch/terminal evidence.
- Add kernel to `RuntimeServices` and every registry constructed for runtime.
- Make `MacrRuntime` return/raise typed nonterminal BUSY before provider work.
- Require GLM adapter permit validation immediately before key/transport.
- RED/GREEN: ordinary invoke and direct-adapter bypass, key/transport sentinels,
  terminal/reconciliation lifecycle, non-GLM compatibility.

## Slice 4 — T1 and host/T0 integration

- Bind project/lane as a separate admission envelope over schema-4 T1.
- Add non-mutating next-member selection followed by provider grant and exact
  claim; saturation remains queued/attempts zero.
- Bind host grant and T0 execution to the same admission identity.
- RED/GREEN: worker_count greater than target, simultaneous dispatchers,
  peek/claim race, legacy staged bundle, forged host/project/lane.

## Slice 5 — operator surfaces and recovery

- Add read-only `admission-status` and bounded nonterminal CLI output.
- Add explicit governed reconciliation/target-transition APIs; do not add a
  self-authorizing capacity CLI.
- Update PowerShell wrappers with project/lane and bounded wait options while
  keeping provider calls opt-in.
- RED/GREEN: privacy sentinels, absent-store read, exact resolution authority,
  target 2 candidate only, values above measured boundary rejected.

## Slice 6 — gates and documentation

- Update schema fingerprints, multiprocess gate and package exports.
- Run focused tests, full repository tests, v0.6 compatibility gate and v0.7
  Phase-C gate without introducing Phase D paths.
- Record exact commit/tree, counts, digests, known limitations and closure
  vector. No shared runtime migration, provider call, merge, release or
  deployment without a separate operator decision.

