# MACR v0.7.0a0 GLM fixed-key Claude/Codex handoff

Date: 2026-09-08

Status: credential custody and exact example approval verified locally. No
provider generation or live model acceptance is claimed.

## Exact repository subject

```text
implementation_commit = 7377f27fb3385c903ae4db538f14fcedce3260df
implementation_tree   = 07d0ed6ce5788363741a22ce046971bc79211a52
branch                = fix/glm-claude-custody-quickstart
```

## Root cause

The GLM credential was already persisted through the intended mechanism. The
provider uses `auth_mode=api_key_file` and the fixed bounded loader accepts only
`D:\KEY\GLM.txt`. `ZAI_API_KEY` is intentionally unsupported and is cleared by
`scripts\invoke-glm.ps1` before MACR invocation.

The observed failure was an obsolete `delegation_approval_sha256` in
`examples\glm-worker-task.example.json`. The current compiled request,
model-token policy, capability tier, latency, task ID, and approval schema
produce a different exact digest. MACR correctly rejected the stale task before
credential access or transport.

## Content-free observations

```text
fixed_key_file_exists       = true
fixed_key_file_ordinary     = true
fixed_key_file_reparse      = false
fixed_key_file_shape_valid  = true
process_ZAI_API_KEY         = absent
user_ZAI_API_KEY            = absent
machine_ZAI_API_KEY         = absent
glm_doctor_ready            = true
glm_doctor_status           = configured_offline
old_example_preflight_exit  = 4
old_example_failure_type    = ProviderPolicyError
current_approval_sha256     = 98a788f1ca05d70cd3648e196e7ad5f025b4cdffe3282f5137284855ae47d26b
host_approval_created_at    = 2026-09-08T05:37:57.455252+00:00
host_approval_expires_at    = 2026-10-08T05:37:57.455252+00:00
no_env_preflight_exit       = 0
network_activity            = false
provider_generation         = false
currency_cost               = 0
```

No credential value, credential digest, account identifier, prompt body, or
answer body is recorded here.

## Verification boundary

The new integration test was observed RED with the old example digest and GREEN
after updating the example. The focused GLM/config/wrapper/example/CLI replay
ran 100 tests with zero failures and one existing platform capability skip.

The host approval applies only to the exact conformance task above. It does not
authorize the planned multilingual batch, T1 staging, automatic retry,
provider fallback, file writes, patching, verification, acceptance, merge, or
deployment. Claude Code or Codex may perform the separately authorized paid
single-task invocation without receiving the credential value.

The cross-provider Bridge was independently observed `installed=true` and
`verified=true`, but `live=false` with `herdr_not_running`. Bridge liveness is
not required for an ordinary Claude Code process to execute the local MACR CLI.
