# MACR v0.7.0a0 GLM output-budget selection and Windows UTF-8 design

Date: 2026-09-08

Status: operator-approved design. Implementation is governed by the paired
task-by-task TDD plan.

## Evidence and problem statement

P0 transport telemetry separated two failure classes that had previously been
collapsed. The four rapid historical failures remain unrecoverable
`provider_execution` / `unknown_after_dispatch` observations. A new bounded
test instead completed an HTTP 200 response after 220.623 seconds and failed at
`provider_response_validation`: `finish_reason=length`, 16,384 completion
tokens, and 15,887 reasoning tokens. The same semantic task, reissued as a new
exact task with 32,768 output tokens and a new approval, completed with
`finish_reason=stop`; 20,135 of its completion tokens were reasoning tokens.

This establishes an output-budget problem, not an input-context problem. The
general GLM policy already allows 512,000 input-context tokens. The current
16,384 minimum/default output and the T1 fixed 16,384 maximum are too small for
quality-first GLM max-reasoning work.

The first successful Korean call also exposed an independent Windows boundary:
when an outer `powershell.exe` left Python stdout on CP950, printing the complete
Korean candidate raised `UnicodeEncodeError` after provider success and private
capture. The candidate and accounting survived, but the CLI returned exit 1.
MACR must own its child-process encoding instead of requiring every AI host to
remember two environment variables.

## Selected policy

The exact ordinary `glm_flash_worker/glm-5.3-flash` policy becomes:

| Field | Current | Selected |
|---|---:|---:|
| minimum task output | 16,384 | 32,768 |
| default output | 16,384 | 65,536 |
| MACR maximum output | 65,536 | 65,536 |
| hard input context | 512,000 | 512,000 |
| provider output ceiling | 131,072 | 131,072 |

The T1 GLM preset becomes:

| Field | Current | Selected |
|---|---:|---:|
| minimum task output | 16,384 | 32,768 |
| default output | 16,384 | 65,536 |
| T1 maximum output | 16,384 | 65,536 |
| hard input context | 128,000 | 128,000 |
| provider output ceiling | 131,072 | 131,072 |

The global `TaskConstraints` ceiling remains 65,536. Grok, Gemini, MiniMax,
Qwythos, Direct Chat settings, and their token policies do not change.

Current Z.ai public documentation gives 65,536 as the default and 131,072 as
the maximum for published GLM-5-family chat models. The public model enum does
not identify the exact `glm-5.3-flash` alias. MACR therefore keeps 65,536 as its
maximum until that exact route separately demonstrates and documents a larger
accepted envelope.

## Pre-approval automatic selection

The model/provider never changes `max_output_tokens` after dispatch. A pure,
credential-free GLM rule derives a task-specific profile before approval:

### `short_exact_conformance`

Use 32,768 as the required and recommended output when all conditions hold:

- `task_type=provider_conformance`;
- return format is `exact_text`;
- expected exact text is present and at most 256 UTF-8 bytes.

An explicit higher value through 65,536 remains valid.

### `quality_first_work`

All other GLM tasks require and recommend 65,536. This includes delegated
translation, classification, analysis, review, and code-text candidates. Since
the maximum is also 65,536, accepted real-work tasks use exactly that value.

This is intentionally a two-band rule. The observed reasoning ratio does not
support a reliable content-length formula, and input size alone did not predict
reasoning consumption. A future Agent policy may use accumulated observations
to propose additional bands, but it must still produce one explicit integer
before digest and approval.

If a task is below its derived requirement, preflight returns a content-free
typed diagnostic containing:

- `minimum_max_output_tokens`;
- `recommended_max_output_tokens`;
- `output_budget_profile`;
- provider/model/policy identifiers already allowed by the current diagnostic.

An AI host may use that diagnostic to rewrite its own unapproved task and run
preflight again. MACR does not mutate the task file. Once selected, the integer
is covered by the request payload, task contract, model-token-policy digest,
provider approval digest, host approval record, and T1 member/manifest digest.

## Compatibility and authority

The model-token policy remains contract v2 because its shape is unchanged, but
the canonical policy digest changes. Consequently:

- existing GLM approval records remain immutable historical evidence but do
  not satisfy a task compiled against the new policy;
- every still-needed GLM task receives a new exact digest and host approval;
- the conformance example is regenerated for the 32,768 short profile and may
  receive one new local approval without a provider call;
- existing T1 schema-4 manifests bind the old T1 policy digest and cannot
  stage; they must be regenerated and reapproved;
- no approval is bulk-copied, rewritten, inferred, or silently promoted.

Increasing an output ceiling also raises the conservative pre-dispatch cost
ceiling. A task with insufficient `max_cost_usd` fails before credential access
or transport. MACR never silently raises its currency authority.

## Windows UTF-8 ownership

`scripts\macr.ps1` temporarily sets the Python child environment to:

```text
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
```

It captures whether each variable existed and its exact previous value, invokes
the existing Python module once, captures the exit code, and restores the
caller's environment in `finally`. It does not change a user- or machine-level
environment variable and does not alter the PowerShell profile. The wrapper
must preserve the Python process exit code.

`invoke-glm.ps1` continues to own its separate temporary removal/restoration of
`ZAI_API_KEY`. The two custody scopes must compose without exposing either
value.

## Failure semantics

- `finish_reason=length` with an HTTP 200 observation remains
  `provider_response_validation`, with usage/cost/candidate evidence preserved.
- The specialized all-reasoning exhaustion error remains when its existing
  exact predicate holds; other `length` results remain `ProviderProtocolError`.
- A later success never settles a prior failure or unknown charge.
- No automatic retry, fallback, model switch, output escalation after approval,
  provider pacing, or circuit breaker is added.
- The original four rapid `provider_execution` failures remain independent and
  unresolved.

## Verification design

TDD must first reproduce and then close these behaviors:

1. ordinary GLM policy is 32,768 minimum / 65,536 default and maximum;
2. T1 policy is 32,768 minimum / 65,536 default and maximum;
3. short exact conformance accepts 32,768 and exposes its profile;
4. real delegated work rejects 32,768 with a safe 65,536 recommendation;
5. real delegated work at 65,536 compiles that exact provider payload and
   approval digest;
6. T1 delegated members require 65,536 and retain dynamic member/worker/cost
   semantics;
7. stale policy digests, approvals, and manifests fail before transport;
8. forced CP950 parent environment can invoke the real wrapper on a Korean
   offline task and receive UTF-8 output without `UnicodeEncodeError`;
9. wrapper environment values and exit code are restored/preserved;
10. complete repository and Phase-C gates remain network/provider false.

After implementation, any live provider probe remains a separate explicit
operator action. Offline verification does not prove the provider accepts
65,536 on every task or that quality always increases.

## Non-goals

- TaskContract string value such as `max_output_tokens="auto"`;
- output above 65,536;
- changes to non-GLM provider policies;
- autonomous task-file mutation or approval creation;
- retry/backoff/fallback;
- resolving or rewriting historical unknown billing;
- Phase D Agent-loop implementation.
