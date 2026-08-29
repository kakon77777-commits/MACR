# MACR v0.6 Final Offline Checkpoint — 2026-08-29

## Exact verified subject

```text
branch  feature/macr-v0.6-dynamic-coordination
commit  ca374ec1be30d675dc10d62354c7f5b44d7dfb9e
tree    61a1988a59096823640c942687ae81904b72e13b
version 0.6.0a0
```

This is the exact clean implementation/docs/runbook subject tested twice. The later commit that adds this evidence document is not substituted for the subject above.

## Reproducible gate result

`scripts\verify-v06.ps1` ran twice on the same clean commit/tree. Both executions returned exit 0 and emitted byte-identical `V06_SUMMARY` records:

```text
full repository tests          440 passed / 2 platform skips
named v0.6 attack/control set  103 passed
provider invoker census        0
doctor network_activity        false
provider generation            false
runtime schema                 6
observatory schema             2
accounting schema              2
1/2/3/4/8 queue controls       passed
32-process SQLite bootstrap    passed
schema fingerprint             43ca1e5e8cc0f75b4ac5de1821ce2f8b2d7d5632e7ad0a151910543dc396c0b5
planner replay digest          ff6b6070a1201773f4ff52fe0199680f3e6c511cfb7d9372f3081e30e5086fef
canonical probe-pack digest    e5fef10ef254b2a134c3b2a1d2a52a73c713c756df6a4768f7460d5d51e67d96
V06 summary digest             843c1b9a4f0761c23fa03619ae9b2d8fed2499fa6c645f73a52cc9194902761f
```

The two skips are the retained Windows symbolic-link/reparse tests on a host where unprivileged test symlink creation is unavailable. No new skip was introduced. `git diff --check`, source/test compilation, operational D-drive scan, ignored-file credential scan, census self-exclusion/positive control, and offline doctor passed.

## Implemented v0.6 boundary

- canonical model/route/role/qualification identities, host-session/resident separation, Context Capsules, and configurable owner policy;
- capture-first Observatory evidence, offline OpenRouter parsing, rebuildable Model Passports, route-role qualification and invalidation;
- deterministic shadow planning, explicit fallback revisions, route proposals, exact T0 authority/execution, private capture, typed verification, pending host acceptance;
- separate coordination cost classes and content-free future billing/reconciliation port;
- durable T1 ordered queue with exact batch scope, dispatcher set, per-member/aggregate ceilings, fencing, one provider attempt per member, and reconciliation instead of auto-retry;
- digest-only target claims and target-path leases, named competing alternatives, at most one automatic materializer flag, and no automatic materialization by verification;
- constrained T2 coordinator proposals that cannot choose provider/model, expand context, issue authority, accept, merge, deploy, or acquire resident identity;
- T3 individual-versus-integration verification with required compile-together, vector and exact-diff definitions;
- blinded, deterministic cross-route differential manifest/replay for at least three qualified candidate routes; public rows contain no model labels;
- offline `model-observe`, `model-passport`, `plan-shadow`, `plan-show`, `plan-diff`, `probe-plan`, and `probe-replay` control commands.

## Authority and side-effect boundary

- No OpenRouter discovery network request ran through MACR.
- No Grok, GLM, Google, MiniMax, Ollama, Claude, or other provider generation occurred.
- No provider credential content was loaded by the gate; health reporting remained offline metadata inspection.
- No shared legacy migration, seal change, batch authority, plan promotion, live T0/T1 run, differential provider run, merge, release, deployment, publication, automation, acceptance, or resident binding occurred.
- Disposable writes were restricted to D-drive `test-tmp`; the ordinary state initializer only verified the configured D directory tree.
- The live runbook is intentionally unexecuted and grants no authority.

## NotMeasured and remaining live gates

- The final gate did not re-read the real 41,490-byte/74-event legacy source, read-only attribute, current complete row, or shared lease/accounting totals. Those are live-route preconditions, not inferred from historical evidence.
- T1 concurrency is proven with synthetic SQLite workers and mock terminal evidence. No paid/local bounded three-worker batch has been run on this checkpoint.
- No real T0 canary or three-route differential provider run has been performed.
- Raw Observatory and Candidate files are not encrypted at rest in v0.6.
- Cross-database runtime/accounting/observatory atomicity is not claimed; visible reconciliation is the contract.
- Context semantic sensitivity still requires trusted operator classification.
- Provider retention, training, region, cache, ZDR, account-credit and invoice truth remain external observations unless separately snapshotted.
- The future billing port reserves identifiers and reconciliation records; it does not ingest invoices.
- Direct UI transport cancellation and late-result recovery remain future gates.
- Host-native agent backends and broader Grok/Qwythos agent mode are deferred to v0.7.

## Verdict

The planned v0.6 implementation is complete as a clean, reproducible **offline candidate**. The result is not a live-route acceptance, merge, release or deployment decision. Any provider-bearing gate follows `docs/V06_LIVE_GATE_RUNBOOK.md` under fresh operator authority.
