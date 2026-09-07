# MACR v0.7.0a0 Host Adapters and GLM Capability Policy Checkpoint

Status: offline implementation candidate; not merged, released, deployed or
activated

Date: 2026-09-07

## Exact subject

```text
repository       D:\Ai\work together\MACR
worktree         D:\Ai\work together\MACR\.worktrees\v070a0-host-adapters-glm-policy
branch           feature/v070a0-host-adapters-glm-policy
base commit      20a2d5e02e34c0faf74fcaa5c40721df9aa37763
base tree        a16a181a96e7ede415648872b68263db43a02d13
code commit      36b73bebd6e07a81332c5b8d18ecff01ff46af15
code tree        ad6182a50afc1c15ba8b97e3ab2ed5cc707bbca9
package version  0.7.0a0
```

The reviewed design is
`docs/superpowers/specs/2026-09-07-macr-v070a0-host-adapters-glm-policy-design.md`.
The executable plan is
`docs/superpowers/plans/2026-09-07-macr-v070a0-host-adapters-glm-policy.md`.

## Implemented boundaries

- Windows subprocess tests capture raw bytes, scan secret/UUID canaries before
  replacement decoding, and Phase A-C gates consume UTF-8 JSON test summaries
  instead of localized `unittest` prose or native stderr.
- `ProviderCapabilityPolicy` is separate from `TaskContract`. The task cannot
  select or activate a provider tier.
- The exact `ProviderTierBinding.binding_digest` covers provider, model, tier,
  revision, complete policy and effective latency. It is bound through
  authority, approval, dispatch/terminal events, accounting/outbox and T1.
- GLM `standard` is 300 seconds with the existing routine/conformance types.
  `extended_text_candidate` is 900 seconds with routine, analysis, review and
  code-text candidates. Both deny patch, write scope and tools.
- Requested GLM latency is passed unchanged when within the active tier and is
  rejected before key/transport when above it. The former silent 300-second
  clamp is gone.
- GLM approval schema 3 binds task ID, exact latency and provider-tier digest.
  Typed external approval records distinguish new schema-3 approvals from
  immutable `legacy_pre_tier` records.
- Provider failures expose stable top-level `failure_code` and `failure_stage`.
  Exception messages and remote bodies remain excluded.
- Accounting schema 3 and outbox schema 2 bind tier/failure fields. A fixed
  three-query snapshot reports known cost, unknown-after-dispatch, unsettled
  runs and all pending outboxes without task or candidate content.
- Runtime schema 7 adds nullable queue tier evidence. Schema-6 rows remain
  readable/countable as legacy; T1 manifest schema 2 binds one exact tier.
- `MacrHostAdapter` gives synthetic Codex and Claude host verifiers equal
  provider/policy/budget rights. It consumes pre-issued authority/connectivity
  grants and is tested not to call `DispatchAuthorityStore.issue()`.
- Tier activation consumes a separately pre-issued authority scoped to the
  exact binding digest. The capability store cannot issue that authority.
- `capability-status` and `accounting-status` are read-only and do not create an
  absent database.

## Verification evidence

The clean baseline at design commit `0af3c1b` ran the Phase C gate with 727
inherited tests, network false and provider generation false. Locale repair
commit `d92ec10` ran 735 inherited tests with the same offline flags.

The combined post-change focused gate ran 197 tests with zero failures and one
existing symbolic-link capability skip. The clean code subject `0a0ba159` /
tree `65a095778d5af16a364314fec4a140cd08acb870` then ran the complete Phase C
gate:

```text
inherited tests      777
Phase C focused       98
Phase B focused       76
Phase A focused       91
platform skips         2
failures               0
network activity   false
provider generation false
phase D started    false
git clean           true
```

The later code-only commit `f838bf8` added the concrete pre-issued-authority
activation verifier and passed all six provider-capability-store tests.

Two initially green complete gates on documentation commit `af5e787` exposed a
reproducibility defect outside the feature logic: all semantic/state digests
matched, but five generated `.dist-info` ZIP timestamps changed the wheel hash.
A minimal two-build probe reproduced different hashes with exactly those five
timestamp changes. Commit `6547c3a` pins `SOURCE_DATE_EPOCH` to the exact
candidate commit timestamp in Phase B and C gates. The minimal control then
produced two byte-identical wheels.

Two consecutive clean complete Phase C gates on exact `6547c3a` / tree
`851fede0e18069b26d7faac19bf720e69104b478` produced identical evidence:

```text
inherited tests      778
failures               0
platform skips         2
wheel sha256          220e4f9907a81347d620dc9d93de3a5c89a47ebb0c996f466553ac87ad60f283
source date epoch     1788771048
network activity   false
provider generation false
phase D started    false
git clean           true
```

All Agent, semantic, graph, projection, attachment, commit and replay digests
were byte-identical between the two summaries.

### Governing-twin challenge and supersession

The governing twin rejected the earlier `af5e787`/`6547c3a` candidate despite
green gates. Its attacks proved that an injected allow-all verifier could
activate a tier, a rogue stored policy could exceed the GLM adapter ceiling, a
cached extended registry could survive an active-head downgrade, a foreign
state-root authority could activate the target policy store, and the initial
authority-digest column lacked schema migration.

Commits `c938136` and `36b73be` supersede that candidate:

- public raw activation is removed; `ProviderCapabilityGovernance` consumes a
  real pre-issued authority and private activation permit;
- store/effective reads and the GLM constructor accept only exact
  adapter-published standard/extended definitions;
- runtime and T1 reread current active head before approval/admission;
- governance requires canonical sibling
  `settings/provider-capability-policies.sqlite3` and
  `runtime/dispatch.sqlite3` under one state root;
- capability-store schema 2 migrates schema-1 active rows with
  `authority_digest=NULL`, preserves their policy/pointer fields, and refuses
  them until canonical reauthorization.

The twin independently replayed the foreign-root and literal schema-1 attacks
on `36b73be` / tree `ad6182a50afc1c15ba8b97e3ab2ed5cc707bbca9` and returned
`CONCUR`: 114 focused tests passed with one existing symbolic-link skip, no
network/provider/key/shared-state action, and a clean worktree.

The primary seat then ran two consecutive clean complete Phase C gates on that
exact subject. Both summaries were byte-identical:

```text
inherited tests      787
failures               0
platform skips         2
wheel sha256          b67e13954b4c85e12749169590d23953e72fc977aafa0f3bed757fdd4e613ccd
source date epoch     1788773322
network activity   false
provider generation false
phase D started    false
git clean           true
```

## Claude and Codex operational status

Claude Code can use the existing MACR PowerShell CLI now, as documented under
`integrations/claude-code`. That path is honestly attributed as `cli` /
`process_id` and uses no Anthropic API key. Codex can use the same route.

Live `task_local_host_observed` integration remains `NotMeasured`. Environment
variables and Claude hook JSON are model-shell-forgeable discovery evidence;
they cannot create trusted identity, authority or tier activation. A live host
embedding must supply a verifier unavailable to generic shells plus pre-issued
operator grants.

## Activation and live-use boundary

This checkpoint does not modify the shared capability pointer, migrate the
shared runtime/accounting databases, read a provider key or call a provider.
The built-in standard tier therefore remains the deterministic default.

After a separately accepted merge/release decision, initial GLM elevation still
requires this sequence:

1. read `capability-status` and `accounting-status`;
2. reconcile or explicitly retain legacy approval/accounting/queue evidence;
3. pre-issue operator authority scoped to the exact extended binding digest;
4. save the create-once extended policy and activate it using that authority;
5. confirm the active digest through read-only status;
6. regenerate and approve each still-needed task under approval schema 3;
7. conduct any real 301-900-second provider call only under separate explicit
   live authority.

No automatic retry, fallback, patch, filesystem write, tool use, verification,
acceptance, merge or deployment is implied.
