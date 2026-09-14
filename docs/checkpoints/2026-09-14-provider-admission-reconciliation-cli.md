# MACR provider-admission reconciliation CLI checkpoint — 2026-09-14

Status: implemented and verified on an isolated branch; one exact operator
reconciliation was applied to shared runtime state. Not merged, pushed, tagged,
released, or deployed.

## Subject

- Base commit: `14f0a6e8f9c1ea9452bdb3f3c6760bb5c23b90d7`
- Branch: `fix/provider-admission-reconciliation-cli`
- Provider: `glm_flash_worker`
- Runtime deployment mode: `canonical_runtime`
- Provider policy revision: 3
- Provider policy digest:
  `731de4f9c6592e6c35b97d5b5d69b6fe5e19a3782c22c014e0e2ee0407d5a74c`

## Implemented behavior

`admission-reconcile` is a two-step, network-free operator command. Preflight
binds the exact request, run, original authority, task/member, project, lane,
provider tier, provider policy, resolution evidence, and expired local lease
snapshot. Apply requires the immediately reviewed binding digest. An unexpired
local dispatch lease fails closed. Any exact expired lease release is opt-in.
The one-use reconciliation authority is revoked after the operation.

The command changes provider-admission capacity state only. It does not call a
provider, retry a task, or mutate accounting. Unknown provider billing remains
unsettled until separate billing evidence is imported.

`DispatcherLeaseStore` now exposes exact-run inspection and expired-run
reaping. Reaping refuses if any matching lease is still unexpired and never
touches another run.

## Client shutdown boundary

There is no truthful post-dispatch client `cancel`: the remote outcome may
already exist. A parent should stop scheduling, deliver Ctrl+C or Windows
`CTRL_BREAK_EVENT` to the live MACR child, and wait for the wrapper's `finally`
cleanup. Forceful termination bypasses that cleanup. After a forced exit, the
operator waits for lease expiry and uses `admission-reconcile`; billing remains
separate.

## Verification

- Focused admission/dispatch/CLI suite: 97 tests, all passed.
- Complete `scripts/verify.ps1`: 971 tests, all passed, 2 existing Windows
  symbolic-link skips.
- Exact provider invoker census before the shared-state action: 0.
- No network/provider generation occurred during preflight, tests, or apply.

## Shared-runtime operation

Operator evidence:

`D:\AI_RESIDENCE\AI_Runtime\macr-state\operator-evidence\2026-09-14-ai-frontier-stale-admission-resolution.json`

- bytes: 2,158
- SHA-256:
  `9a400e700cad6f61ae24967755e0e8339e45f9d1df09091d957e66fe3493eb1b`

Pre-action SQLite backup:

`D:\AI_RESIDENCE\AI_Runtime\macr-state\backups\2026-09-14-ai-frontier-reconciliation\dispatch-before.sqlite3`

- bytes: 9,457,664
- SHA-256:
  `372646bd95474f72915abc6ccd7ccd0b7cbd61a4ceb16d2c9a7c15adbf3ba6ac`

Five AI-Frontier admission rows moved from `reconciliation_required` to
`reconciled`; three exact expired dispatch leases were removed. Post-state was
`reconciliation_required=2`, `reconciled=5`, zero dispatch leases, and no
AI-Frontier project active units. The two preserved AGIRight reconciliation
rows were unchanged.

Accounting for 2026-09-14 remained five `billing_state=dispatched` invocations,
`unsettled_count=5`, and known estimated cost USD 0.5570229 across the 73
separately terminalized calls. The reconciliation did not assert that any
unknown remote call was free.

## Closure

- Behavioral: PASS for exact preflight, digest rejection, apply, capacity
  release, expired-lease cleanup, authority revocation, and accounting
  separation.
- Structural: PASS for the scoped operator path; admission state, local lease,
  authority, evidence, and accounting boundaries are explicit.
- Discriminative: PASS for wrong binding digest and unexpired-lease rejection;
  no claim is made about provider billing resolution or force-kill transport
  cancellation.
- Twin: degraded by explicit no-subagent boundary; no independent Twin review
  is claimed.
