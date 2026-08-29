# MACR v0.6.0a1 Offline Checkpoint — T1 Operability Repair

Status: offline-only candidate; live provider route stopped

Date: 2026-08-30

## Exact implementation boundary

```text
base tag              v0.6.0a0 (immutable)
base commit           683101636edd5e840c9a2809fc85a575add18bf7
base tree             070519796d4bbbd8e73e7f63eeb0402b86eaaab1
repair branch         fix/macr-v0.6.0a1-t1-operability
implementation commit 4404fd2012b9789ed6f732c320e188659ec93e6d
implementation tree   f71550e11c760c76a991ac393a3d425b2620cd03
version               0.6.0a1
```

The exact clean documentation/gate subject is:

```text
candidate commit        74e81ae5133dd9e9e34fdfc11dae341a10310b2a
candidate tree          26a232ae138be7dd7f7f21bd4fb62c9d4951711c
worktree before/after   clean
complete gate runs      2
complete tests/run      482 passed, 2 platform capability skips
targeted tests/run      127 passed
summary digest/run      6f93542eac54462bebb03fab8e504c411298d5e01a8c0d0103d28a39e3bd9c24
network activity        false
provider generation     false
quiet census            5 zero samples before + 5 after each run
```

Both complete `verify-v06.ps1` runs exited 0 and emitted byte-identical `V06_SUMMARY` JSON. Identity fields remained the same because both runs used the same clean commit/tree. The implementation commit above remains the last product-code commit before version/documentation work.

Additional deterministic evidence from the summary:

```text
runtime/observatory/accounting schemas  6 / 2 / 2
Direct conversation schema              2
model-token policy schema/count         1 / 7
model-token policy set digest           8046258902d867e70e7015fed2b68dc92334796ad4d0319b5d1a21da3f6f4247
T1 live-policy digest                   1164ee2bb62fffbd42fa5ffbfa3b7344fd825cae4c506dabff4afa30c59b48d6
three-process complete path             3
SQLite bootstrap processes              32
queue-only historical matrix            1 / 2 / 3 / 4 / 8
```

## Retained evidence, not rewritten

- initial concurrent census RED: conservative marker-bearing review/search command lines caused safe false positives during the first MSSP pressure run;
- quiet-window GREEN on the immutable a0 release: two complete reviewer replays were byte-identical at summary digest `9f34cf229c0c673e773ebfbc490750fd55dfe6671c57824ee93f59b13ac9da57`;
- the later green does not erase or reinterpret the initial red;
- the invoker predicate remains unchanged and no reviewer/process-name allowlist was added.

Exact external review records retained outside this repository include:

```text
D:\Ai\work together\MSSP_Architect_Exchange\opinions\2026-08-30-metron-macr-v06-pressure-convergence.md
SHA-256 C026BF94DE70F42E7D99F32B0E7AF53896EB9C88EB3DD928508ADACAEFB1631C

D:\Ai\work together\MSSP_Architect_Exchange\evidence\2026-08-30-pragma-macr-v060a0-pressure-replay.md
SHA-256 B79B7BFFC9EB016BF939EA2AE102D3638491C7CCF3A37EC61F0517D5EF42B65B
```

## Repairs

1. `PlanQueue.list_by_state`, `state_counts`, `require_reconciliation`, and explicit reconciliation resolution provide bounded global visibility. Pagination is deterministic and content-free.
2. `T1ExecutionManifest` binds the exact ordered task/route/token-policy/role/privacy/context/cost/target subject. Duplicate JSON keys, raw absolute paths, stale approval digests, wrong models, policy mismatch, and non-T1 limits fail before authority or queue write.
3. `t1-stage` creates exact batch plus dispatch authority only after all three existing GLM host approvals validate. Staging performs no provider call.
4. `t1-worker` claims at most one plan-scoped member and traverses the existing authority, lease, `MacrRuntime`, event, Candidate Vault and accounting paths exactly once. It performs no retry, fallback, verification, materialization, or acceptance.
5. Unknown-after-dispatch or persistence ambiguity enters global `reconciliation_required` and blocks every later T1 claim. Explicit resolution revokes the old batch; continuation requires a new manifest and new authority.
6. A synchronized three-process complete-path mock produced three distinct claims, exactly three fake transport attempts, three dispatch/terminal pairs, three captures, three terminal accounting rows, three plan-cost rows, zero unsettled invocations and zero reconciliation rows. No task, answer, key, or manifest path entered public databases.
7. `verify-v06.ps1` holds `MACR_V06_QUIET_CENSUS`, samples five zero-invoker observations before and after the gate, and reports only count/PID on failure.

## Exact model-local token policies

| Provider/model | Warning | Hard context | Default output | Max output |
|---|---:|---:|---:|---:|
| `grok/grok-4.6` | 180,000 | 400,000 | 32,768 | 65,536 |
| `grok_standard/grok-4.3` | 180,000 | 400,000 | 32,768 | 65,536 |
| `glm_flash_worker/glm-5.3-flash` | 400,000 | 512,000 | 16,384 | 65,536 |
| `google_gemini/gemini-3.7-flash` | 400,000 | 512,000 | 16,384 | 65,536 |
| `minimax/MiniMax-M2.7` | 160,000 | 180,000 | 2,048 | 2,048 |
| `minimax/MiniMax-M2.7-highspeed` | 160,000 | 180,000 | 2,048 | 2,048 |
| `ollama_qwythos/Qwythos-9B-v2` | 7,000 | 8,192 | 4,096 | 4,096 |

The separate T1 GLM policy is 128,000 context / 8,192 output. Persistent overrides live at `settings\model-token-policies.sqlite3`; there is no global active token profile.

## Schema boundary

```text
runtime operational SQLite 6
observatory SQLite          2
accounting SQLite           2
Direct conversation schema 2
model-token policy schema   1
```

## NotMeasured

- NotMeasured: real Z.ai transport, latency, billing, provider retention, or account entitlement under the a1 subject;
- NotMeasured: shared production D-drive migration or current legacy seal/hash recheck;
- NotMeasured: Codex/Claude Code host integration, autonomous routing, provider fallback, verification, acceptance, merge, release, deployment, adoption, or external publication;
- NotMeasured: cross-machine coordination, crash recovery after operating-system or storage-device failure, or encrypted Candidate/Direct storage;
- NotMeasured: a real T0 followed by three live T1 members under the USD 0.020 campaign cap.

There was no live provider call, credential export, shared-runtime migration, merge, tag, release, deployment, or publication while producing this checkpoint.
