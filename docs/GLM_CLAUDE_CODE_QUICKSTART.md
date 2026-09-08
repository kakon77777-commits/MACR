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

## Failure map

| Observation | Meaning | Next check |
|---|---|---|
| GLM `configured_offline` | Fixed key-file metadata and route configuration passed; no network test was made. | Continue to task preflight. |
| `approval_invalid` / `ProviderPolicyError` | Task digest is missing/stale or its exact host approval is absent/stale. It is not evidence that the key is missing. | Run `--show-required-digest`, update the task, then approve it. |
| `ProviderOutputBudgetTooSmallError` | The requested output is below the model policy floor. | Use at least 16,384 output tokens for GLM max reasoning. |
| `ProviderTaskTypeError` | The active capability tier does not allow the declared MACR execution class. | Use `delegated_routine` for eligible routine work or obtain separate tier activation. |
| `network_opt_in_required` | No provider call was authorized. | Add `--allow-network`, or use `invoke-glm.ps1`. |
| `configuration_incomplete` on the GLM row | Fixed key-file metadata or fixed provider configuration failed. | Ask the MACR operator to inspect D-drive custody; never request the raw key. |

Provider completion remains an unverified candidate. It does not grant file
writes, patching, verification, acceptance, merge, deployment, or resident
identity.
