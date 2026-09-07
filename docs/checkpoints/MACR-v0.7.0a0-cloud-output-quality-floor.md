# MACR v0.7.0a0 Cloud Output Quality Floor Checkpoint

Status: isolated implementation candidate; not merged, released, deployed or
activated

Date: 2026-09-07

## Exact base and scope

The isolated worktree started clean from commit
`2e5d4ed88139a711a13f97dba15a6b098c558444` / tree
`618f68b1c24431a846c8bd0ca152fd7e6474791f`.

This candidate changes delegated cloud text output admission, GLM preflight
diagnostics, GLM reasoning-exhaustion classification, the TaskContract output
default, and the still-unactivated T1 preset/cost envelope. It does not change
provider identity, reasoning effort, privacy, tools, write scope, automatic
retry, acceptance, credentials, shared runtime state or provider-side billing.

## Field observations that triggered the change

Read-only accounting/event inspection found this exact GLM 5.3 Flash pair for
`discovery-ai-crawler-001`:

- a 4,096-token request ended `finish_reason=length` with
  `output_tokens=4096`, `reasoning_tokens=4096`, no accepted answer,
  `candidate_failure`, and estimated cost USD 0.00211805;
- the separately re-preflighted/reapproved 16,384-token request ended
  `finish_reason=stop` with `output_tokens=5745`,
  `reasoning_tokens=5217`, `candidate_success`, and estimated cost
  USD 0.0029424.

This is evidence that 4,096 was exhausted in that task and that 16,384 worked
for its retry. It does not prove that 16,384 guarantees visible output for every
task. The adapter therefore retains a distinct postflight exhaustion failure
even after adding the preflight quality floor.

The `universal-directory/agents` draft set contained 14 JSON manifests. All 14
were structurally read as `task_type=delegated_routine` with
`max_output_tokens=16384`; all nine concrete Discovery manifests passed
credential-free `glm-preflight --show-required-digest` under the active
`standard` tier. Five template files still contain documented placeholders and
were not treated as dispatchable tasks.

## Effective design

- `TaskConstraints.max_output_tokens` defaults to 16,384.
- Model-token policy contract v2 serializes `minimum_task_output_tokens` into
  its digest. An external text task must request at least that exact floor.
- Grok's floor is 32,768. GLM/Gemini use 16,384. MiniMax remains a visible
  2,048 exception because its configured provider output ceiling is 2,048.
  Loopback Qwythos does not inherit the cloud rule.
- External operator overrides cannot change the immutable floor or provider
  ceilings. MiniMax's 2,048 exception is rooted in its adapter definition;
  caller-supplied ceilings cannot manufacture another exception.
- GLM preflight rejects a below-floor request before key/transport and returns a
  content-free `output_budget_below_quality_floor` diagnostic.
- GLM task-type rejection returns requested safe type plus exact active
  provider/model/tier/revision/binding and allowed values. Unsafe arbitrary type
  text is rendered as `unavailable` rather than echoed.
- `task_type` remains an authority class. Domain stages may use a task ID prefix
  and their full task/return contract; privileged analysis/review/code semantics
  still require the extended tier.
- A no-content `length` response with all but at most one generated token
  reported as reasoning becomes
  `ProviderReasoningBudgetExhaustedError`. Safe response and cost observations
  remain available; terminal/accounting rows receive the same typed failure at
  `provider_response_validation`, and no retry occurs.
- Grok, Gemini, MiniMax and GLM adapters repeat the floor check before reading a
  credential or contacting a provider. Grok Direct does the same. Legacy Grok
  Direct rows without a v2 snapshot fail before message append or dispatch and
  must continue in a newly created conversation.
- T1 schema 3 binds the new 128,000 / 16,384 token-policy-v2 digest and exact
  USD 0.010 / 0.030 / 0.040 ceilings. Schema 2 is inspectable as
  `legacy_pre_quality_floor` but cannot stage/dispatch and must be regenerated.
  Current member and enclosing manifest digests both use v3 domains.
- Policy-v1-base override rows remain immutable and are exposed through
  content-free current/legacy/invalid/active counts. Legacy activation or
  effective use raises `LegacyOutputPolicyIncompatibleError`; a new revision
  must bind the v2 base. Only the exact reconstructed v1 digest is historical;
  arbitrary mismatches are invalid, including a separate active-invalid count.
  The shared store was observed to contain no overrides.
- A verified legacy Qwythos policy-v1 Direct snapshot retains its original
  loopback-only settings in memory; this exception cannot authorize cloud use.

## Governing-twin challenge and successor work

The first committed candidate `596b1b2` / tree `1e5ff16e` passed its offline
gate but was not accepted. The governing Twin independently demonstrated four
closure gaps: raw Grok/Gemini and Grok Direct adapter bypass, unchanged v1
policy digests plus a forgeable GLM ceiling exception, T1 schema/domain drift,
and null top-level reasoning-exhaustion failure fields. The subsequent changes
in this checkpoint are a successor candidate, not a reinterpretation of that
earlier green result.

The governing Twin then challenged successor `fa3ce97` / tree `f1c1912a` for
an untyped active-v1-override failure and a residual v2 member digest domain.
Those findings caused another scoped reopening; neither earlier green gate is
the final closure subject.

The governing Twin then challenged `e96cdf0` / tree `33b4f351` because an
arbitrary known-provider base digest was incorrectly labelled as genuine v1
history. The final successor distinguishes exact reconstructed v1 history from
invalid mismatches and proves that a failed activation leaves the active table
unchanged.

## Authority and live-state boundary

No provider call, credential read, approval creation, tier activation, shared
database migration, merge, tag, release or deployment was performed by this
repair. Other host activity was actively dispatching GLM from the canonical
checkout, so implementation stayed in an isolated worktree. The shared T1 queue
was observed empty before this work; that observation is not a future live-use
authorization.

## Verification

Verification results will be sealed here only after the final clean candidate
and full offline gates exist.
