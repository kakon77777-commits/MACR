# MACR v0.6.0a1 Future Live Gate Runbook

Status: not authorized; do not execute from this document alone

This runbook records the only proposed live sequence. It is not authority, not a provider approval, and not evidence that any live call occurred.

## Fixed campaign limits

```text
T0                     USD 0.005 hard ceiling
T1 member              USD 0.005 hard ceiling each
T1 three-member total  USD 0.015 hard aggregate
campaign total         USD 0.020 hard cap
GLM context            128,000
GLM output             8,192
attempts               serialized, one per member
retry                   no retry
fallback                no fallback or model substitution
```

## Preconditions

1. Neo authorizes one exact live manifest digest, exact commit/tree, exact dispatcher set, expiry, task bodies, GLM approval digests and campaign subject.
2. The repository is clean at the published a1 checkpoint and two complete quiet gates have byte-identical non-identity evidence.
3. `queue-status --state reconciliation_required` returns zero globally.
4. The current legacy JSONL remains read-only and its current bytes/count/SHA-256 have a complete SQLite source row; no legacy invoker exists.
5. Accounting has zero unsettled invocations and the T0/T1 campaign ledger contains no earlier charge for this subject.
6. Every member uses exact `glm_flash_worker/glm-5.3-flash`, T1 policy digest, `non_sensitive_routine`, no write scope, no patch authority, independent host verification, and one unexpired HMAC-authenticated GLM host approval.
7. Provider credential custody remains fixed at `D:\KEY\GLM.txt`; keys never enter the manifest, command line, event database, accounting database, or report.

## Proposed sequence

1. Execute one T0 bounded candidate at USD 0.005 maximum.
2. Stop. Reconcile its dispatch, terminal event, Candidate capture, accounting terminal, actual/unknown billing state and verification result. Any ambiguity ends the campaign.
3. Re-run quiet census and global reconciliation checks.
4. Stage the exact live manifest:

```powershell
.\scripts\macr.ps1 t1-stage <exact-private-manifest.json> `
  --dispatcher-id <worker-1> `
  --dispatcher-id <worker-2> `
  --dispatcher-id <worker-3> `
  --expires-in-minutes 30
```

5. Run one worker at a time; inspect accounting and queue state after each:

```powershell
.\scripts\macr.ps1 t1-worker <exact-private-manifest.json> `
  --dispatcher-id <worker-1> --allow-network
.\scripts\macr.ps1 queue-status --state reconciliation_required
```

6. A nonzero reconciliation count, unknown billing state, missing terminal/capture/accounting evidence, cost above a member ceiling, changed policy/approval digest, expired authority, or census marker stops all remaining work. Do not retry. Resolve explicitly, revoke the old batch, and obtain authority for a new exact live manifest before any continuation.
7. Provider output remains an unverified candidate. A trusted host performs separate verification and acceptance. No worker accepts, materializes, merges, deploys, publishes, or opens a private resident context.

## Explicit non-authority

As of the v0.6.0a1 offline checkpoint, the exact live manifest is absent and the campaign is not authorized. The three-process repository gate uses a fake transport only. This runbook grants no live provider call, no expenditure, no retry, no fallback, no merge/release/deploy, and no resident identity.
