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

The clean Phase-C gate and any governing-Twin result belong to the later exact
documentation subject. A successful offline gate will not authorize a provider
probe, bulk approval, merge, or deployment.
