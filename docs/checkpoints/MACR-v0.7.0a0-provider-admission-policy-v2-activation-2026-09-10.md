# MACR v0.7.0a0 Provider Admission policy-v2 activation receipt

Date: 2026-09-10

Status: active on the canonical shared runtime; no provider call performed by this activation

## Exact code and state subject

```text
repository        D:\Ai\work together\MACR
main/origin-main  493046f020672f627c1ef710395efaac0ca6b853
tree              82c6b8300adc4c46a1cf93c7c32dd99c680900ad
runtime database  D:\AI_RESIDENCE\AI_Runtime\macr-state\runtime\dispatch.sqlite3
provider          glm_flash_worker
```

The operator explicitly superseded target 2 as a standing product ceiling and
authorized more bounded capacity for concurrent projects and conversations.
The implementation uses policy revision 2: default/effective target 8, review
marker 16, finite hard maximum 32, per-project cap 8, and raw capacity unit 1.
Any later target change still requires a new exact one-use authority.

## Discovery correction

An earlier candidate checkpoint stated that the shared runtime was still schema
7. A later read-only post-merge check disproved that statement. The database had
already reached schema 8 at `2026-09-10T11:03:28.936933+00:00` and installed
built-in policy revision 1. Before the policy-v2 transition, readback showed 43
completed admission requests, no reconciliation, and one final live request
that subsequently completed. No actor is attributed from timestamps or process
timing.

The earlier schema-7 statement remains historical error evidence and is
superseded by this receipt. It is not used as an activation premise.

## Exact-head verification

Before shared-state mutation, exact clean code subject `493046f` passed:

```text
verify-v06 inherited tests       889 OK / 2 platform skips
verify-v06 focused tests         207 OK
quiet census samples               5
summary digest                   3e587875db234b88bd1edaf71206f3636317bc5c6429933e8e6792a59b789281
policy effective/review/hard     8 / 16 / 32
network/provider                 false / false

Phase-C inherited tests          889
Phase-C focused tests             98
Phase-B / Phase-A focused         76 / 91
wheel SHA-256                    6534616caf1e103ced4a74af3decb14147798daf4c390fb68274e756c6dcb3c8
network/provider/Phase-D         false / false / false
```

The governing Twin independently rejected and caused repairs for stale
activation authority and foreign-predecessor policy attacks. On the exact code
subject it returned `CONCUR`: only exact built-in v1 may transition to exact
built-in v2, active requests block the transition, and stale/revoked authority
cannot be consumed after its precheck.

## Backup and preconditions

Five consecutive zero-invoker samples passed immediately before backup and
again immediately before activation. SQLite backup API created:

```text
D:\AI_RESIDENCE\AI_Runtime\macr-state\backups\provider-admission-policy-v2-20260910T130715Z\dispatch-before.sqlite3
bytes   6295552
sha256  0785560b52e980329d76e8ccf080ea7c4ee6f9d8c2069f8fb14cebb51eee2fc6
```

Source and backup both returned `PRAGMA integrity_check=ok` and page count
1537. Immediately before activation:

```text
schema                    8
active policy revision    1
policy digest             79982616ca60f7957ee207b5fee4c01d5e9b2220de1783003022637c8d873d35
effective target          1
circuit                   closed
control revision/digest   44 / 7e31a095b5e2ec72893a26a54d6390e917a66cf00c196c7467b00507f6f7b983
completed requests        43
active requests/leases    0 / 0
```

## Authority and atomic transition

The exact policy transition binding was:

```text
a12d548bcf91833d52ffff7431027170eb0312c7f4daad1a504a7d83ea40358f
```

It bound built-in revision-1 digest/revision, built-in revision-2
digest/revision, and target 8. A separate authority bound only
`glm_flash_worker`, `provider_capacity_activation`,
`provider_admission_policy_transition`, and that transition digest:

```text
aeabf3ec2ee8207ebbe6e72e5b427e1bce89c395cc9a44e92fb761882ebd99b6
```

Inside one `BEGIN IMMEDIATE`, MACR revalidated current state and authority,
verified idle/circuit-closed state, preserved revision 1, inserted immutable
revision 2, consumed the authority, appended `policy_superseded`, and updated
the active projection. The authority has non-null `revoked_at` and cannot be
reused.

## Postconditions

```text
active policy revision    2
policy digest             b6688485aec5ea1c4845d650ab1fc162813540f2f644db509ae374f50a0bd3c6
effective/review/hard     8 / 16 / 32
per-project cap           8
circuit                   closed
control revision/digest   45 / 8e39098e5c81a6d3ca6598b49442771d51c1aa5b20e96ceb39b14b2c4cc3418f
last transition           policy_superseded
deployment digest         d1924ceec463eeedbd4c5a401fef2100220c61065fa254e3091df86d4c48a9ec
active requests/leases    0 / 0
post quiet census         5 consecutive zero samples
integrity_check           ok
```

Pre/post logical digests were identical for events, runs, admission requests,
admission project counters, T1 batches/members/target claims, dispatch leases,
candidate captures, and materializations. Only the exact authority, immutable
successor policy, control receipt, and active projection changed.

No production credential was read. No provider request, generation, retry,
fallback, accounting settlement, tag, release, or deployment was performed by
this activation. Target 8 is now effective capacity, but z.ai service stability
at eight overlapping calls remains live-observation evidence rather than an
offline guarantee.

The governing Twin independently opened both databases read-only, recomputed
the transition binding, receipt/body/state digests, authority body/scope, and
17 non-governance table digests, then obtained another five-sample zero-invoker
census. It returned `CONCUR`; no shared file or provider was touched by that
review.

Normal reduction is a new exact target authority and forward transition to any
value from 1 through 32. Restoring the database backup is emergency evidence
recovery, not ordinary rollback, because it would erase later legitimate
events.
