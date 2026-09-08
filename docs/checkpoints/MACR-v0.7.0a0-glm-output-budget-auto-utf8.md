# MACR v0.7.0a0 GLM quality-first output and Windows UTF-8 checkpoint

Date: 2026-09-09

Status: offline implementation candidate. No live provider acceptance,
host-approval activation, merge, release, or deployment is claimed.

## Exact implementation subject

```text
implementation_commit = ac536cd4309ec044d32a4f97fc2c53f24440dbd4
implementation_tree   = 78520df1465b18085ca913660f3c8051d5eb8387
branch                = feature/glm-output-budget-auto-utf8
package_version       = 0.7.0a0
```

## Observed trigger

The post-P0 evidence contains three separate outcomes:

1. One provider-successful Korean result was captured/accounted but printing it
   under CP950 raised `UnicodeEncodeError`; this is a Windows CLI boundary.
2. One 16,384-token HTTP-200 result ran 220.623 seconds, ended `length`, used
   15,887 reasoning tokens, and retained estimated cost USD 0.0082952 under
   `provider_response_validation`.
3. A new exact 32,768-token task completed `stop`, used 20,135 reasoning tokens,
   and retained estimated cost USD 0.01097435.

The four earlier rapid `provider_execution` / `unknown_after_dispatch` rows are
independent, retain null historical transport telemetry, and remain unresolved.

## Exact policy transition

| Policy | Previous digest | Current digest |
|---|---|---|
| ordinary GLM | `334cc8f26181a2e0aea6213c572e4dba3e612986efc2b71e9914d76351c20e26` | `c268567d90ec2e6f821587315bd126044d30acb949b8f5049397b1ce44602067` |
| T1 GLM | `ecfafac42410cc8f6b21db637989eb33ac92c347cc513720bfe204678bab3490` | `ebde549215ec2489daa6d8dffffc86441ebab3eca725ed183716e28da7f0c55b` |

Ordinary GLM now uses 32,768 minimum, 65,536 default/maximum, 512,000 hard
context, and 131,072 provider-output ceiling. T1 uses 32,768 minimum,
65,536 default/maximum, 128,000 hard context, and the same provider ceiling.
No non-GLM policy changed, and the global task maximum remains 65,536.

## Automatic pre-approval selection

`short_exact_conformance` requires/recommends 32,768 only when the task is
`provider_conformance`, return format is `exact_text`, and expected text is at
most 256 UTF-8 bytes. `quality_first_work` requires/recommends 65,536 for every
other GLM task, including translation, classification, analysis, review and
code-text candidates.

The selector is pure and credential-free. Preflight publishes only the profile
and numeric requirement/recommendation. The AI host may update its unapproved
task and preflight again. MACR does not write the task, mint approval, or change
the integer after approval. The exact value remains covered by task, request,
policy, approval and T1 digests. An active operator override cannot lower the
65,536 real-work requirement.

## T1 and compatibility

T1 remains schema 4 with dynamic members, `worker_count`, dispatchers, and cost
envelopes. Real-work members require 65,536. A schema-4 manifest with the prior
T1 policy digest fails before staging and its bytes remain unchanged.

Existing GLM host approvals remain immutable but cannot satisfy the new policy
digest. Every still-needed task and T1 manifest must be regenerated and
reapproved. The refreshed repository conformance example carries 32,768,
max-cost USD 0.05, current short-profile digest
`5a81004ca5f795b58534a27599db6f923dcb1a9820327643a2b56db731f15a77`,
and deliberately has no matching new host record at this checkpoint.

## Windows UTF-8 boundary

`scripts\macr.ps1` temporarily sets `PYTHONUTF8=1` and
`PYTHONIOENCODING=utf-8`, invokes `python -X utf8` once, records its exit code,
and restores the exact presence/value of both outer variables in `finally`.
It does not mutate user/machine environment or the PowerShell profile and does
not alter the separate `ZAI_API_KEY` custody wrapper.

## Verification evidence

RED/GREEN and falsifying controls cover:

- ordinary/T1 exact policy values;
- 256-byte conformance acceptance and 257-byte quality-first selection;
- delegated short exact work remaining quality-first;
- operator override unable to lower real-work requirement;
- exact 65,536 provider request and approval metadata;
- under-profile failure before key/transport with no task-content echo;
- T1 65,536 member acceptance, 32,768 rejection and old-policy failure;
- Korean output through real `powershell.exe` with forced CP950 parent state;
- restoration of outer encoding variables;
- preservation of Grok/Gemini/MiniMax/Qwythos limits.

```text
focused_tests             = 155
focused_existing_skips    = 1
complete_tests            = 832
complete_existing_skips   = 2
failures                  = 0
network_activity          = false
provider_generation       = false
credential_read           = false
shared_state_mutation     = false
```

The first exact clean code-and-documentation subject was commit
`fc964dfa89fa9a096f3654aacc586b37b5e7e56a` / tree
`973fa9e5e1372469f9e6fe572cf374c7479127eb`. Its Phase-C gate returned exit 0
with:

```text
inherited_tests            = 832
phase_c_focused_tests       = 98
phase_b_focused_tests       = 76
phase_a_focused_tests       = 91
required_test_ids           = 50
bootstrap_processes         = 32
semantic_commit_contenders  = 8
fresh_package_replay        = true
installed_import_isolated   = true
wheel_sha256                = 4b4d7254426a5c91dd2b546b09d0b8a4809aa56b8cfeddff21c9506e7cf49956
network_activity            = false
provider_generation         = false
phase_d_started             = false
git_clean                   = true
```

This remains offline evidence. It does not authorize a provider probe, bulk
approval, merge, release, or deployment. Any governing-Twin result belongs to
a separately identified review subject.

## Local activation and publication receipt

On 2026-09-09 Neo explicitly authorized merge, update, and activation. The
canonical `main` checkout fast-forwarded from
`b5b2120033af09bff330022e116fc411a7b87131` to the exact reviewed candidate
`bcf3f2ec7fa70d815f74cf5169713c2beeeaff54` / tree
`fee634c7c20758ca787095c1d221757528f0ac3a`. The pre-existing untracked
`REQUEST_FOR_CODEX_T1_LIVE_ROUTE.md` remained outside the merge and was not
modified. A fresh replay on the merged `main` checkout ran 832 tests with zero
failures and two existing platform capability skips while treating
`ResourceWarning` as an error.

The refreshed public conformance envelope then demonstrated the intended
fail-closed transition: ordinary preflight first returned `approval_invalid`
with exit 4 and required digest
`5a81004ca5f795b58534a27599db6f923dcb1a9820327643a2b56db731f15a77`.
Neo's standing activation authority was used to create exactly one 30-day
`host_operator` approval for that digest at
`2026-09-08T16:46:53.604586+00:00`, expiring
`2026-10-08T16:46:53.604586+00:00`; ordinary preflight then returned
`preflight_structurally_valid` with exit 0. The short conformance profile kept
the task's explicit 32,768-token output budget.

This activation made no provider request, generation, retry, fallback, or
currency expenditure and created no bulk or Korean-work approval. Existing
translation/classification/analysis tasks must be regenerated with the 65,536
quality-first budget and receive their own exact approval before dispatch. A
later bounded live conformance or real-work task is operational evidence, not
part of this activation receipt.
