# GLM from Claude Code or Codex

This is the operator-facing route for using `glm_flash_worker` from an ordinary
Claude Code or Codex shell without disclosing or copying the Z.ai credential.

## Credential custody

MACR does not load `ZAI_API_KEY` from `.env`, user environment, machine
environment, a task manifest, or an AI prompt. The exact committed provider
profile uses `auth_mode=api_key_file` and the bounded loader reads only:

```text
D:\KEY\GLM.txt
```

The file must be an ordinary D-drive file beneath the fixed key root, not a
symbolic link or junction, and must pass the provider's bounded shape check.
`scripts\invoke-glm.ps1` temporarily removes any inherited `ZAI_API_KEY` before
invocation and restores the caller's environment afterwards. Do not paste the
key into Claude Code, Codex, `.env`, JSON, logs, or chat.

## 1. Check the route without reading the key or contacting Z.ai

Run from any Claude Code or Codex session:

```powershell
Set-Location 'D:\Ai\work together\MACR'
$report = .\scripts\macr.ps1 doctor | ConvertFrom-Json
$report.providers |
  Where-Object provider_id -eq 'glm_flash_worker'
```

Expected GLM row:

```text
ready  = true
status = configured_offline
```

Do not use `doctor --strict` as a GLM-only test: strict mode also reports other
enabled providers whose unrelated environment variables are absent.

## 2. Bind and approve each exact task

The credential and the task approval are different gates. A present key does
not authorize arbitrary work.

```powershell
# Credential-free and network-free: compute the exact current envelope digest.
.\scripts\macr.ps1 glm-preflight .\path\to\task.json --show-required-digest

# A trusted operator or host copies required_approval_sha256 into the task's
# delegation_approval_sha256 field, then signs that exact digest locally.
.\scripts\macr.ps1 glm-approve .\path\to\task.json --expires-in-days 30

# Credential-free and network-free: verify task digest plus host record.
.\scripts\macr.ps1 glm-preflight .\path\to\task.json
```

`glm-approve` reads the fixed D-drive key only inside the bounded provider path
to authenticate the local approval record. It does not contact Z.ai and does
not print the key or its digest. If an exact approval already exists but must be
renewed after an intentional task/policy/key change, a trusted operator may add
`--replace-existing`.

Every materially different task gets its own digest and approval. Eight
translation tasks are eight exact members; a prior conformance approval is not
authority for them. Business categories such as translation or classification
belong in `task_id` and task content. The standard MACR execution class remains
`delegated_routine` unless a separately activated tier authorizes another exact
type.

GLM max reasoning uses two pre-approval output profiles:

- `short_exact_conformance`: `task_type=provider_conformance`, return format
  `exact_text`, and expected text at most 256 UTF-8 bytes; minimum and
  recommendation are 32,768;
- `quality_first_work`: every other task; minimum and recommendation are
  65,536.

Preflight exposes `output_budget_profile`, `required_minimum_output_tokens`,
and `recommended_max_output_tokens`. An AI host may update its unapproved task
and preflight again, but MACR never rewrites the file or raises the value after
approval. The higher envelope also needs a `max_cost_usd` large enough for the
reported conservative ceiling.

`scripts\macr.ps1` temporarily forces its Python child to UTF-8 and restores
the caller's prior `PYTHONUTF8` and `PYTHONIOENCODING` values. Multilingual
output therefore does not require session-specific encoding setup.

## 3. The only paid step

After the final preflight succeeds:

```powershell
.\scripts\invoke-glm.ps1 -TaskPath .\path\to\task.json
```

Equivalent lower-level form:

```powershell
.\scripts\macr.ps1 invoke glm_flash_worker .\path\to\task.json --allow-network
```

These commands perform one provider attempt. There is no automatic retry or
fallback. Start with one bounded single-language task, inspect its candidate and
accounting result, and only then stage a larger schema-4 T1 batch. T1
`worker_count` is manifest-configurable and is not fixed at three.

Inspect only the relevant provider and time window:

```powershell
.\scripts\macr.ps1 accounting-status `
  --provider glm_flash_worker `
  --since 2026-09-08T00:00:00+00:00
```

The `by_failure` rows can contain safe HTTP status, Z.ai business code,
network-attempt, response-received, and transport-stage evidence for
new invocations. Historical failures remain null. `unsettled_count=0` means the
runtime wrote terminal records; any `unknown_after_dispatch` rows still require
billing reconciliation and must not be read as zero-cost.

## Failure map

| Observation | Meaning | Next check |
|---|---|---|
| GLM `configured_offline` | Fixed key-file metadata and route configuration passed; no network test was made. | Continue to task preflight. |
| `approval_invalid` / `ProviderPolicyError` | Task digest is missing/stale or its exact host approval is absent/stale. It is not evidence that the key is missing. | Run `--show-required-digest`, update the task, then approve it. |
| `ProviderProtocolError` with `http_response` | Z.ai returned a non-2xx HTTP response. Safe status/business code is retained; remote prose is omitted. Billing remains unknown unless separately reconciled. | Stop the batch and classify the exact code; do not blind retry. |
| `ProviderUnavailableError` with `connection` | A network attempt produced no HTTP response. | Stop and inspect connectivity; do not blind retry. |
| `ProviderOutputBudgetTooSmallError` | The requested output is below its GLM task profile. | Apply the safe preflight recommendation: 32,768 for short exact conformance, otherwise 65,536; then obtain a new digest and approval. |
| `ProviderTaskTypeError` | The active capability tier does not allow the declared MACR execution class. | Use `delegated_routine` for eligible routine work or obtain separate tier activation. |
| `network_opt_in_required` | No provider call was authorized. | Add `--allow-network`, or use `invoke-glm.ps1`. |
| `configuration_incomplete` on the GLM row | Fixed key-file metadata or fixed provider configuration failed. | Ask the MACR operator to inspect D-drive custody; never request the raw key. |

Provider completion remains an unverified candidate. It does not grant file
writes, patching, verification, acceptance, merge, deployment, or resident
identity.
