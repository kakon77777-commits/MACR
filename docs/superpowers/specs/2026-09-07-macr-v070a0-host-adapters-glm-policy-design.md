# MACR v0.7.0a0 Host Adapters, Provider Tiers, and Field Repairs — Design

Status: implementation candidate under MSSP × TDD × APR

Date: 2026-09-07

## Exact project world

```text
repository       D:\Ai\work together\MACR
base main/tag    20a2d5e02e34c0faf74fcaa5c40721df9aa37763
base tree        a16a181a96e7ede415648872b68263db43a02d13
base version     0.7.0a0
feature branch   feature/v070a0-host-adapters-glm-policy
Bridge installed true
Bridge verified  true
Bridge live      false
Bridge degraded  herdr_not_running
```

The package version remains `0.7.0a0` during this feature line. Merge, version
advance, tag, push, shared-state migration, and live provider use remain separate
operator decisions.

## User objective

1. Repair the measured Windows locale harness, GLM latency contract, hidden
   failure type, and incomplete accounting visibility.
2. Give Codex and Claude Code one equal MACR host-adapter path to the existing
   provider registry, budgets, approvals, candidate capture, and accounting.
3. Replace GLM's single hard-coded routine profile with an operator-selected,
   provider/model-scoped capability tier. Initially enable a larger but still
   candidate-only tier for non-sensitive work.
4. Leave room for other cheap providers to opt into higher tiers later without
   silently granting those tiers today.

## Retained boundaries

- A provider/model is not a resident or speaker identity.
- Host origin attribution is not dispatch authority.
- A task or model cannot grant its own capability tier.
- Provider completion remains a candidate, never verification or acceptance.
- No automatic retry, provider fallback, materialization, merge, or deployment.
- No Direct Conversation history is exposed to either host adapter.
- Claude subscription remains a host runtime only; `ANTHROPIC_API_KEY` and an
  Anthropic API fallback remain forbidden.
- `frontier_restricted` and `private_resident` are never eligible for GLM.
- Credential resolution remains provider-late, after task, tier, budget,
  approval, authority, and connectivity gates.

## Field evidence to repair

### Locale harness

`tests/test_direct_launcher_scripts.py` decodes Windows PowerShell stderr as
strict `utf-8-sig`. A cp950 byte can kill `subprocess`'s reader thread and leave
`CompletedProcess.stderr=None`, so the secret non-disclosure assertion never
runs. The repair captures bytes, scans raw stdout/stderr for the exact secret
and UUID canaries, then separately produces replacement-decoded diagnostic text.
It adds a forced non-UTF8 negative plus a UTF-8 control and never weakens the
non-disclosure assertion.

The Phase C wrapper is also exercised explicitly through Windows PowerShell 5.1
so native stderr wrapping cannot be confused with a product failure.

### GLM 300-second clamp

Five real GLM tasks independently terminated at approximately 300 seconds even
when one task declared 900 seconds. Three later disambiguation tasks—12 rows,
then 6 and 6—also terminated at the same boundary. The source silently computes
`min(task.max_latency_s, 300)`.

The repair introduces an explicit provider transport ceiling. A task at or below
the selected tier ceiling receives its exact requested timeout. A request above
the ceiling fails before key/transport. No silent clamp remains.

### Approval reuse

The prior approval digest intentionally covered provider request content but not
task ID or latency. The observed consequence was cross-task reuse. Approval
schema 3 now binds:

```text
task_id
provider_tier_binding_digest
max_latency_s
existing provider/model/privacy/budget/token/request payload fields
```

This intentionally invalidates old GLM approvals for future dispatch. There is
no automatic migration or signature reuse; the normal operator approval command
creates a new record after inspection.

### Failure visibility

Post-dispatch failure keeps a sanitized `failure_type` in memory and the runtime
event but emits only a generic warning. Add a stable, typed top-level failure
code and failure stage to the host-facing invocation outcome. Human warnings may
also include the exception class, but never its message or a remote body.

### Accounting visibility

Invocation rows and their outboxes are durable, but operators lack one bounded
content-free status command. Add a fixed-query, read-only accounting summary
exposing counts and sums by provider/billing state, including explicit
unknown-after-dispatch, unsettled dispatches and every pending outbox. Its query
count is invariant with the number of runs/providers. It must not infer invoice
payment, coerce unknown to zero, or ingest browser content.

Daily provider bill observations may use `run_id=None`; exact per-run
reconciliation remains impossible when a provider only publishes an N-1 daily
aggregate. External bill recording is not automated in this slice.

## Provider capability tiers

### Operator-owned contract

`TaskContract` remains provider-neutral. It declares task requirements through
its existing task type, constraints and `required_capabilities`; it cannot name,
select or activate a provider tier.

Static provider support and operator authorization are separate. A provider
adapter publishes the policy shapes it actually implements. An append-only,
provider/model-scoped capability-policy store records versioned policies and a
separate active operator selection. A policy definition is create-once and has
a canonical digest over every rule, including task types, privacy classes,
delegation class, required verification, patch/write/tool eligibility and all
limits.

The runtime resolves an immutable `ProviderTierBinding`:

```text
provider_id
model
tier_id
revision
complete_policy_digest
effective_limits
```

Its sole cross-component identity is:

```text
binding_digest = SHA256(canonical_json({
  provider_id, model, tier_id, revision,
  complete_policy_digest, effective_limits
}))
```

Every reference below binds this `binding_digest`, never only the tier name or
the inner policy digest. When no operator activation exists for GLM, resolution
deterministically returns the immutable built-in `standard` revision-1 binding.
A present but corrupt, stale or unresolvable activation fails closed rather than
falling back. `extended_text_candidate` becomes effective only after an explicit
operator activation record names its exact binding digest.

Effective capability is the intersection of:

```text
adapter implementation
active operator tier binding
task requirements
current dispatch authority
```

No task, provider response, model text, host label or CLI flag can create or
activate a stronger binding. Unknown, inactive, unsupported or stale bindings
fail before key resolution or transport. The exact binding digest is recorded
in the host request, `AuthorityScope`, approval manifest, dispatch policy/event,
accounting observation and T1 member evidence.

Tier activation consumes a pre-existing operator authorization witness whose
scope names the exact binding digest. The capability store cannot issue that
witness, and this slice exposes no shell command that both creates authorization
and activates a tier. A failed or missing witness leaves the active pointer and
all other state unchanged.

Existing schema-2 approvals remain immutable historical records but are
explicitly incompatible with new GLM dispatch. Pending old approval/T1 state is
enumerated before any future shared-state activation; it is not rewritten.

### Contract and migration matrix

All migrations are additive or copy-preserving. Old rows/documents are readable
for audit as `legacy_pre_tier` but can never authorize or satisfy a new GLM
dispatch.

| Surface | New contract | Historical disposition | New dispatch rule |
| --- | --- | --- | --- |
| Capability policy | Store schema 2 binds activation authority | Schema-1 definitions/active rows are preserved; active rows become legacy until reauthorized | Built-in standard or exact authorized active binding only |
| Provider config | Remains schema 2 | Byte/semantic behavior unchanged | Contains no tier authority |
| `AuthorityScope` | Contract 2 adds exact binding-digest set | Empty field reads as `legacy_pre_tier` | GLM requires exact binding digest |
| `DispatchContext` / event | Contract 2 adds exact binding digest and payload schema marker | Old events stay byte-preserved/readable | GLM context must carry exact digest |
| Runtime T1 queue | Runtime schema 7 adds nullable binding digest | Schema-6 rows migrate as null/`legacy_pre_tier` | New T1 enqueue requires exact digest |
| GLM approval | Approval schema 3 | Schema-2 records stay immutable/incompatible | Exact task, latency and binding digest required |
| Accounting DB | Schema 3 adds nullable binding digest and typed failure code/stage | Existing rows remain null and report `legacy_pre_tier` | New GLM rows require exact digest |
| Accounting outbox | New payload schema 2 | Schema-1 payload bytes remain unchanged | New GLM emission uses schema 2 |
| T1 manifest/member | Manifest schema 2 adds exact member binding digest | Schema-1 remains parseable for audit only | Dispatch rejects schema 1 distinctly |

Pending schema-2 GLM approvals and schema-1 T1 members are enumerated with a
content-free incompatibility status. Attempts to use them fail before key,
transport, lease or new event write with the distinct code
`legacy_pre_tier_incompatible`; neither record is modified.

### GLM standard

Retains current behavior:

```text
delegation_class       non_sensitive_routine
task types             delegated_routine / provider_conformance
timeout ceiling        300 seconds
patch candidate        false
write_scope            empty
verification           required
tools                   none
privacy                 public / internal_approved
```

### GLM extended text candidate

The initial operator-selected increase is:

```text
delegation_class       non_sensitive_routine only
task types             delegated_routine / delegated_analysis /
                       delegated_review / delegated_code /
                       provider_conformance
timeout ceiling        900 seconds
patch candidate        false
write_scope            still empty
verification           required
tools                   none
privacy                 public / internal_approved
```

This first elevation increases duration and broadens non-sensitive text/code
candidate task types only. Patch output, filesystem writes, target leases,
tools, materialization, acceptance and merge remain unavailable. More powerful
tiers are deliberately deferred until separately designed and activated.

## Shared Codex/Claude host adapter

### Contract

Add a provider-neutral host module with:

```text
HostKind              codex | claude_code
HostSessionBinding    host, identifier_kind, native_id, binding_source, digest
HostDispatchRequest   host binding, provider, task digest, connectivity opt-ins,
                      resolved tier binding digest, request digest
MacrHostAdapter       preflight and invoke
```

Allowed identifier kinds are exact:

```text
codex        -> codex_thread_id
claude_code  -> claude_code_session_id
```

No display name, resident name, memory, hidden context, or conversation text is
part of the binding. Separate trusted Codex and Claude binding-verifier
interfaces may emit `binding_source=task_local_host_observed` only after the
embedding host supplies and verifies its native identifier. Manually entered
CLI metadata is `operator_asserted` or `unresolved`; it can never be relabelled
host-observed. Attribution is not dispatch authority.

### Equal rights

For equal provider/task/opt-in inputs, Codex and Claude preparations must produce
the same provider, model-token policy, resolved tier binding, task digest, budget, approval and
connectivity decision. Only host origin fields and the resulting request digest
differ.

The adapter uses the same `ProviderRegistry`, `RuntimeServices`, authority store,
lease, `MacrRuntime`, Candidate Vault, return-contract validator, and accounting
store. It does not duplicate provider adapters or create a Claude-specific
provider route.

### Authority

A host-adapter invocation consumes a pre-issued operator dispatch authority and
a pre-issued connectivity grant; it never calls `issue()` from host metadata,
model-controlled flags or task content. Authority source records the host kind
and exact task/run occurrence; its scope binds the exact
`ProviderTierBinding.binding_digest`. Host kind alone never grants a provider,
tier, task type, member digest, connection scope or plane outside those grants.

### Integration surface

This slice delivers a reusable in-process host adapter and separate verifier
protocols, tested with synthetic Codex and Claude bindings. It does not add a
CLI that accepts arbitrary native identifiers or caller-constructed trusted
metadata.

Claude Code's official `SessionStart` hook JSON and the locally observed
`CLAUDE_CODE_SESSION_ID` are useful discovery evidence, but a model-controlled
shell can fabricate both hook JSON and its environment. They therefore remain
`operator_asserted`, not `task_local_host_observed`, until a pre-existing
host-owned enrollment/verifier unavailable to generic shells exists. Likewise,
the locally observed `CODEX_THREAD_ID` and `CODEX_SESSION_ID` are distinct and
never treated as aliases; only an injected Codex host-owned verifier may bind
`codex_thread_id` from `CODEX_THREAD_ID`.

The immediately usable Claude path is the existing MACR CLI under honest
`cli`/`operator_asserted` origin. It already reaches the same provider registry,
budgets, approvals, vault and accounting as Codex. The new host adapter accepts
only a freshly verified binding handle plus pre-issued authority/connectivity
grants. Preflight performs no state write, key read or provider call. Native IDs
remain bounded origin metadata and are never echoed in public accounting
summaries. Live host-observed Codex and Claude bindings remain `NotMeasured`.

Because the verified Bridge is currently `live=false` with
`herdr_not_running`, live Claude availability and an end-to-end Claude-origin
provider call remain `NotMeasured`.

## TDD and discriminating controls

Required positives and negatives include:

- raw non-UTF8 stderr bytes are scanned for secret/UUID canaries before lossy
  rendering; rendered stderr uses replacement and UTF-8 output remains exact;
- a UTF-8 machine-readable test summary replaces locale-dependent parsing of
  native PowerShell stderr or English `Ran ... tests` output;
- GLM standard 300 and extended-text 900 reach transport unchanged;
- 301 standard and 901 extended-text fail before key/transport;
- approval digest changes independently with task ID, latency, tier binding, request
  content, model-token policy, or complete provider tier policy digest;
- holding `complete_policy_digest` constant while changing provider, model,
  tier ID, revision or effective limits changes `binding_digest`; authority,
  approval, context, accounting and T1 each reject the mismatched binding;
- extended-text accepts reviewed analysis/code text candidates but rejects
  patch, write scope, tools, disabled verification, frontier/private delegation,
  and unapproved privacy;
- task or model cannot select/activate a tier, and another provider cannot
  inherit GLM's active tier;
- Codex and Claude adapters are equal except origin and request identity;
- unsupported host, wrong identifier kind, `claude_subscription` target,
  unverified/manual-as-trusted binding, missing connectivity opt-in, stale
  authority, and tier-policy mismatch fail before provider/key/state write;
- a plain shell can fabricate matching environment variables, `SessionStart`
  JSON and an attacker-controlled environment file but still cannot obtain
  `task_local_host_observed`, mint host-bound authority or activate a tier;
- direct trusted-DTO construction, host invocation without pre-issued authority
  and shell-triggered tier activation fail before authority/state/key/provider
  access;
- host invoke records exact host origin, tier and failure type through runtime,
  accounting and terminal event;
- a typed top-level invocation outcome exposes stable failure code/stage without
  remote message/body data;
- a bounded, fixed-query accounting snapshot counts pending/known/unknown,
  unsettled dispatches and every pending outbox without content or zero-fill;
- Direct store/history is never imported by the host adapter;
- all v0.7 Phase A-C and v0.6 gates remain green.

## Stop boundary

This feature may end with offline implementation and fake-transport conformance.
It does not authorize:

- a real Claude-originated provider call;
- a real GLM elevated/long-timeout call;
- activation of any provider tier in shared runtime state;
- a live `task_local_host_observed` Codex or Claude integration;
- shared-state migration or re-signing all historical approvals;
- filesystem/tool authority for GLM or other workers;
- Phase D, Agent loop, merge, tag, push, release, or deployment.
