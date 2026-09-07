# MACR v0.7.0a0 dynamic T1 workers checkpoint

Date: 2026-09-07

Status: offline verified candidate. This document is not a provider approval,
live-run acceptance, deployment record, or standing dispatch authority.

## Exact subject

```text
implementation_commit = bf993074881d9884f0e704b9bc7851ca5fb07a4f
implementation_tree   = c583e7dd303ac348a064d85bc9648b07735801fa
code_and_docs_commit  = 38dcad7224d03cbbd6ea3626868a70b8b1989b1c
code_and_docs_tree    = 60f0ae3a7718de97b44b0b3b66eaa78585f11cf7
branch                = feature/t1-dynamic-workers
```

## Closed boundary

- T1 manifest schema 4 binds explicit `worker_count` and v4 member/manifest
  digest domains.
- Nonempty member sets are not capped at three. `worker_count` is between one
  and member count and exactly matches the unique authorized dispatcher set.
- Member count may exceed worker count. Each worker invocation still claims at
  most one member; an authorized dispatcher may be invoked again to drain later
  queued work.
- Per-member cost ceilings are positive exact task values. Aggregate cost is
  the exact sum; campaign cost is operator-selected and must cover it. The
  former fixed USD 0.010/0.030/0.040 values are no longer protocol limits.
- Schemas 1, 2, and 3 remain audit-only and fail before staging or dispatch;
  schema 3 is reported as `legacy_fixed_three_workers`.
- Staging and worker JSON project both member and worker counts.

One-attempt semantics, no automatic retry/fallback, global reconciliation,
exact route/policy/tier/approval binding, private candidate capture, accounting,
and host-only verification/acceptance boundaries remain unchanged.

## Verification evidence

The focused dynamic-T1 replay ran 64 tests with zero failures. The first full
repository replay ran 814 tests with zero failures and two existing Windows
platform capability skips.

The clean Phase-C gate on `code_and_docs_commit` returned exit 0 with:

```text
inherited_tests             = 814
phase_c_focused_tests        = 98
phase_b_focused_tests        = 76
phase_a_focused_tests        = 91
required_test_ids            = 50
bootstrap_processes          = 32
semantic_commit_contenders   = 8
wheel_sha256                 = b201e2628181a642cc7a52cf733b8a0a918d4095b1393370173634cc9d01e99f
network_activity             = false
provider_generation          = false
phase_d_started              = false
git_clean                    = true
```

The behavioral subjects include four workers draining five members, five
parallel T1 complete-path processes with exact queue/Vault/event/accounting
counts, dynamic cost-envelope rejection controls, schema-3 audit-only
preservation, and CLI count projection. No provider call, credential read,
shared-runtime mutation, migration, or live authority activation occurred.
