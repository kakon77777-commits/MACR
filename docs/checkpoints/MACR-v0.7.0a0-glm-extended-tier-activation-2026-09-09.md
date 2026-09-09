# MACR v0.7.0a0 GLM Extended Tier Activation Receipt

Status: active on the canonical local D-drive runtime; no task approval or
provider call performed

Date: 2026-09-09

## Exact subject and authority

```text
repository       D:\Ai\work together\MACR
code commit      098fbfe37b43f665401c29d20171516fcc6fecf8
code tree        1a7590c4f6517407c12ad94345b5b2ecdd0cbbd0
state root       D:\AI_RESIDENCE\AI_Runtime\macr-state
provider         glm_flash_worker
model            glm-5.3-flash
```

Neo had explicitly authorized an initial GLM capability elevation. The
immediate operational trigger was two consecutive, unchanged 290-second
`ProviderUnavailableError` results for a German translation candidate. The
task-local Claude shell correctly demonstrated that changing only
`max_latency_s` to 600 could not cross the active standard-tier boundary.
Claude's task content and shell were not treated as activation authority.

Before activation, `capability-status` resolved the built-in `standard`
fallback at revision 1, maximum latency 300 seconds and binding
`ad88c6730fd2ad6f6fddc834b698cfc6572944a7584ac7fa7823e58d394de793`.
The schema-2 capability database contained no saved policy and no active row.
Five consecutive quiet-census samples observed zero GLM invokers.

## Backup and activation

SQLite backup API snapshots were written under:

```text
D:\AI_RESIDENCE\AI_Runtime\macr-state\backups\provider-tier-activation-20260909T094632Z
```

| Backup | Bytes | SHA-256 |
|---|---:|---|
| `provider-capability-policies-before.sqlite3` | 32,768 | `7ba9e094b59a57a33fdc138d2a41d3ca9aa12aa47b9b1bbdb84381d07644bcdc` |
| `dispatch-before.sqlite3` | 4,300,800 | `66865d7b0d3166113d764cfd0c3e5434f4d14c78e5560c4e98408dedc6713492` |

Both backups and both sources returned `PRAGMA integrity_check=ok`. Complete
logical-table comparison was equal: capability digest
`a1d947874f68cd0a4ba406aa76e24864e76347d34cfd2c238e4e5f7275778fa3`
and runtime digest
`f67640fdce96cd29090b5e1a3e1963e7ff11b1c8123cfe31623903fb22cf4b73`.

A separate first process pre-issued authority
`1d93c96d3cd8efbd45f6eb8b9d6b81446bc8c45b2655cd7d484e0dfbd05b6130`.
Its scope contained only `glm_flash_worker`, `policy_activation`,
`provider_tier_activation`, and extended binding
`66fa1fa1cdf233c81c2e0c8c8e1dd6586d0673e679178752783533edd3a5b242`.
A second process saved the exact built-in standard and extended policies and
consumed that authority through `ProviderCapabilityGovernance` against the
canonical sibling runtime database. The consumed authority was revoked at
`2026-09-09T09:49:35.696120+00:00` and cannot authorize another activation.

The persistent active head is now:

```text
tier_id                 extended_text_candidate
revision                1
max_latency_s           900
complete_policy_digest  ee4e6d26ffaaa797cf46d71a13dbab29874e2823c1a23185b70bb0524bced177
binding_digest          66fa1fa1cdf233c81c2e0c8c8e1dd6586d0673e679178752783533edd3a5b242
authority_digest        1d93c96d3cd8efbd45f6eb8b9d6b81446bc8c45b2655cd7d484e0dfbd05b6130
patch_allowed           false
write_scope_allowed     false
tools_allowed           false
verification_required   true
```

Revoking or expiring the action authority does not roll back the persistent
active head. That distinction is intentional.

## Postconditions and 600-second witness

Pre/post comparison proved that activation did not alter provider work:

```text
approval root records       594 unchanged
approval history files        1 unchanged
approval tree SHA-256        43898d2406983862ea0b286f3e73bf6042ba0349a1afcefe60eaa55088945719 unchanged
accounting DB SHA-256        53d03724727a00a82df510e74a6ca26049e106fc96ee348ab5c26cef9f2f49b4 unchanged
accounting invocations       623 unchanged
provider events             1324 unchanged
runs                         623 unchanged
dispatch/target/queue leases  0 unchanged
runtime non-authority digest 97d74c7931e7726863ef79ea51a194682296688ddfdc2abdeb73a1d5ae623502 unchanged
dispatch authorities        618 -> 619, exact activation authority only
post quiet census             5 consecutive zero samples
```

The exact Claude-prepared 600-second task bytes had SHA-256
`2FBF64B2498CAC839C089AA24A655E6A62B3F021E1EB7F3883F816B58B622C51`.
Offline `glm-preflight --show-required-digest` returned exit 0 with
`status=approval_required`, `quality_first_work`, 65,536 output tokens,
600-second latency and the active extended binding. Its required approval
digest is
`5679454c7c6c5d38345ac8184b5e9efb7b2128158199b0388fafecddee918af2`.
This is a required digest, not an approval. No key, provider transport,
generation, retry, fallback, billing reconciliation or currency cost occurred.

## Recovery and next boundary

The standard policy is saved create-once. Normal rollback must issue a new
authority bound exactly to standard binding
`ad88c6730fd2ad6f6fddc834b698cfc6572944a7584ac7fa7823e58d394de793`
and perform a forward governance activation, followed by readback of
`standard/300`. Restoring the runtime backup is emergency evidence recovery,
not normal rollback, because it could erase legitimate later runtime events.
No rollback has been executed.

The task-local governing Twin returned `CONCUR`: behavioral, structural and
discriminative activation closure passed. This receipt does not approve the
600-second task and does not authorize its single-flight half-open provider
call. Those remain separate operator actions.
