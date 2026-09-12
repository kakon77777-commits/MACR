# MACR v0.7.0a0 Grok admission and large-context checkpoint

Date: 2026-09-12

Implementation subject:

```text
commit 597b49a652d1855d5dd6da1a44e097299268ff6b
tree   c8c148ab13a32c86371b03831046d44133fd99b6
branch feature/grok-admission-context-v1
```

The subsequent read-only status repair is commit
`c68ababfc19310d539ae3e51d15f02d9c100722f` / tree
`c1490d903328182beb62ff15a097083dfa7c1b97`. It makes a schema-8 database with
only the existing GLM domain report Grok as `initialized=false` rather than a
generic failure, without creating a policy/state row. The focused control and
the complete 45-test provider-admission module passed, and readback against the
shared database returned the expected content-free uninitialized status.
Twin review then challenged the missing-state boundary: a benign uninitialized
answer must not conceal orphan Grok policy or request evidence. Follow-up
commit `c61c8443d689cdb96814860c8f97cbb881d3bae0` / tree
`da3c78707ba8f59b4d04d2708ac27e7b6ff249cc` returns uninitialized only when
all Grok policy, transition, request, and project tables are empty; otherwise
it fails closed. The positive control also proves the GLM-only database bytes
are unchanged by readback, and an orphan-policy negative is rejected.

This checkpoint extends the existing provider-neutral admission substrate to
the exact `grok/grok-4.6` route without consuming the reserved `0.7.0a1` Agent
MVP version. It does not change `grok_standard/grok-4.3` or Qwythos transport
authority.

## Closed implementation scope

- A provider-keyed directory exposes independent GLM and Grok kernels in the
  same canonical runtime database.
- Grok policy revision 1 uses effective/review/hard targets `8/16/32`, unit
  weight 1, and per-project cap 8.
- Ordinary delegated invocation, T0 Plan, the Codex/Claude host adapter, and
  Direct Grok resolve the same `grok` capacity domain. GLM state cannot consume
  or open Grok capacity, and Grok state cannot consume or open GLM capacity.
- Direct Grok uses a conversation-scoped dispatch lease plus the provider-wide
  slot. The same conversation is serial; different conversations can overlap
  within the provider target. Qwythos retains its previous global Direct lease.
- Grok transport requires a one-use v3 authority-bound admission permit. The
  permit is consumed immediately before the one provider transport attempt,
  after deterministic local request construction.
- A response-received protocol failure releases capacity with preserved safe
  telemetry. A no-response outcome becomes `reconciliation_required`; a known
  pre-network failure is `zero_local` and cancels the unused grant.
- New Grok conversations pin warning/hard/default/max values
  `400000/500000/65536/131072`. `TaskConstraints` can represent 131072, while
  every smaller exact provider policy still rejects it before transport.
- Existing complete Direct policy snapshots remain immutable. A Grok row with
  no snapshot remains fail-closed, and a token-policy mutation that does not
  match the combined conversation snapshot is rejected before message append.
- Candidate Vault directory creation tolerates a valid concurrent mkdir winner
  and then repeats the reparse-point/directory checks.

No retry, provider fallback, automatic target promotion, server-side Grok
tools, acceptance authority, Agent loop, or provider call is added.

## Offline evidence before documentation

The implementation subject passed 162 focused tests, with one existing
platform symlink skip, covering provider admission, delegated/Direct Grok,
Claude host adapter, T0 Plan, token policies, contracts, examples, registry,
Candidate Vault, and GLM regression boundaries. A ten-run concurrency loop
also passed the concurrent first-capture and eight-slot Direct controls.

The decisive controls include:

- eight different Direct conversations enter transport and the ninth is BUSY
  before transport;
- two sends on one conversation have maximum active transport 1;
- with Grok target 1, one blocked Direct turn prevents delegated Grok transport
  in the same database;
- opening the circuit after grant but before transport cancels that grant and
  records `zero_local` without leaving a `created` Direct run;
- a GLM reconciliation/open circuit does not poison Grok;
- raw delegated and Direct Grok transports reject a missing permit;
- Host and Plan paths carry exact project, lane, and Grok policy digests into
  dispatch evidence;
- 131072 is accepted by Grok 4.6 and rejected by GLM, Grok 4.3, Gemini,
  MiniMax, and Qwythos exact policies.

All test transports were injected and bound to isolated D-drive offline-test
databases. No key was read and no provider/local-model request was made.

## Activation and restart boundary

Merge is not live enforcement. Before the first shared-runtime use:

1. stop the existing Direct Chat process and require a quiet provider/Direct
   window with no active run or dispatch lease;
2. preserve a WAL-consistent backup of the canonical runtime database;
3. initialize and read back the exact Grok policy/control row in the canonical
   database;
4. restart Direct Chat from the merged source so it issues the split local
   Qwythos authority and v3 Grok admission authority;
5. read `admission-status --provider grok` and retain the content-free receipt.

Historical `direct-chat-operator-managed-v1` authority revisions remain
auditable and are not proof that an old process stopped. The operational
restart/quiet-window condition is therefore mandatory. Initialization grants
no provider call, no target change, and no authority to backfill the two known
shared Grok conversations whose token snapshots are absent.

## Remaining live boundary

Provider-safe throughput at 8, 16, or 32 remains `NotMeasured`. A bounded live
probe, billing reconciliation, and any target change require separate operator
action. Candidate completion remains distinct from verification, acceptance,
merge, release, deployment, and Agent adoption.
