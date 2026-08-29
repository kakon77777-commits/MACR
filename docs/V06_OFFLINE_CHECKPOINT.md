# MACR v0.6 Offline Checkpoint History and Final Repair — 2026-08-29/30

Current verdict: the repaired subject `6c66eff1ce200c4d07506310794ea9ac89a42895` is the final green offline candidate. The earlier `ca374ec...` section is retained below as a **historical rejected candidate**; its green automated gate did not erase the later twin-review blockers.

## Historical candidate subject (later rejected)

```text
branch  feature/macr-v0.6-dynamic-coordination
commit  ca374ec1be30d675dc10d62354c7f5b44d7dfb9e
tree    61a1988a59096823640c942687ae81904b72e13b
version 0.6.0a0
```

This is the exact clean implementation/docs/runbook subject tested twice. The later commit that adds this evidence document is not substituted for the subject above.

## Historical candidate self-gate result

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

## Historical self-verdict (superseded)

The initial self-verdict called the planned v0.6 implementation a clean, reproducible offline candidate. A later read-only twin review rejected that checkpoint after finding three Important gaps. Therefore this paragraph is historical evidence, not the current verdict.

## Twin rejection of the historical candidate

The single authorized twin reviewed final documentation commit `ed59182938b5dc47dfc8f5eadd8d8ba8a53d8c0d` / tree `4b8880b0a02251ba3d9d54d2946d9205021224a5`. That commit inherited the same executable code as the `ca374ec...` checkpoint subject. Two independent offline summaries on the twin subject matched and all automated gates were green, but code review found three Important blockers:

1. same-target named alternatives could cross `plan_digest` boundaries;
2. T1 `TargetClaim.for_path()` created digests before rejecting dotdot, absolute, drive, UNC, ADS, or Windows-reserved aliases;
3. differential replay trusted a self-consistent manifest without loading and comparing the actual probe pack.

The earlier checkpoint was therefore rejected despite its green tests. No Critical finding was reported.

## Final repaired subject

```text
branch  feature/macr-v0.6-dynamic-coordination
commit  6c66eff1ce200c4d07506310794ea9ac89a42895
tree    5172fb7b0d72d3a733ec06bf7aa1d7f598b68e2f
version 0.6.0a0
```

The repair adds one regression attack for each blocker and changes the runtime boundary as follows:

- target alternatives require the same exact plan as every active owner;
- T1 queue and T3 target leases share one repository-relative Windows-safe normalizer before any digest is created;
- `probe-replay` requires the actual probe-pack file and verifies the complete case/task/context/verifier/cost matrix against its canonical digest.

## Final repair verification

The primary seat ran `scripts\verify-v06.ps1` twice on the clean repaired subject. Both runs returned exit 0 and byte-identical summaries. The same authorized twin then independently replayed the three attacks, adjacent suites, and the complete gate.

```text
full repository tests          443 passed / 2 platform skips
named v0.6 attack/control set  106 passed
twin exact regressions         3 passed
twin adjacent repair suite     24 passed
provider invoker census        0
doctor network_activity        false
provider generation            false
runtime/observatory/accounting 6 / 2 / 2
schema fingerprint             43ca1e5e8cc0f75b4ac5de1821ce2f8b2d7d5632e7ad0a151910543dc396c0b5
planner replay digest          ff6b6070a1201773f4ff52fe0199680f3e6c511cfb7d9372f3081e30e5086fef
canonical probe-pack digest    e5fef10ef254b2a134c3b2a1d2a52a73c713c756df6a4768f7460d5d51e67d96
V06 summary digest             38b6087445be0e0232bf4f415d87ccd7fe2adbb4dc5ddc18af80ff5b0a680832
twin Critical                  0
twin Important                 0
```

The two skips remain the existing Windows symbolic-link/reparse controls on this host. The repair and re-review performed no live provider/discovery call, credential read, shared migration/seal, paid T1 batch, materialization, merge, release, deployment, adoption, automation, acceptance, or resident binding.

## Final current verdict

The planned v0.6 implementation is complete as a clean, reproducible **offline candidate** at `6c66eff...`. This is not live-route acceptance, merge, release or deployment authority. Provider-bearing validation remains governed by the still-unexecuted `docs/V06_LIVE_GATE_RUNBOOK.md`.
