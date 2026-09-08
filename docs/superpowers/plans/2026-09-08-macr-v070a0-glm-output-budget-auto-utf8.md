# GLM Quality-First Output Budget and Windows UTF-8 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise GLM max-reasoning work to a quality-first 32K/65K output policy, derive a safe task-specific output requirement before approval, and make the Windows CLI emit multilingual UTF-8 without caller setup.

**Architecture:** Keep provider/model authority exact: a pure GLM selector derives either `short_exact_conformance` or `quality_first_work`, then validates one explicit integer before request compilation, digesting, and host approval. Ordinary and T1 GLM policies share 32,768 minimum and 65,536 default/maximum, while the global task ceiling and every non-GLM policy remain unchanged. The PowerShell entry point temporarily owns Python UTF-8 environment variables and restores caller state in `finally`.

**Tech Stack:** Python 3.11+ dataclasses and `unittest`; PowerShell 5.1/7 wrapper; canonical SHA-256 policy/approval manifests; existing SQLite event/accounting stores; offline Phase-C verification scripts.

**Spec:** `docs/superpowers/specs/2026-09-08-macr-v070a0-glm-output-budget-auto-utf8-design.md`

## Global Constraints

- Package version remains `0.7.0a0`; `0.7.0a1` remains reserved for the bounded Agent MVP.
- Ordinary GLM: minimum 32,768; default 65,536; MACR maximum 65,536; hard input context 512,000; provider output ceiling 131,072.
- T1 GLM: minimum 32,768; default/maximum 65,536; hard input context 128,000; provider output ceiling 131,072.
- `short_exact_conformance` requires `provider_conformance`, `exact_text`, and at most 256 UTF-8 expected bytes; its requirement/recommendation is 32,768.
- Every other GLM task is `quality_first_work` and requires/recommends 65,536.
- Selection occurs before provider request digest and host approval; no task file is silently rewritten.
- The global `TaskConstraints.max_output_tokens` ceiling remains 65,536.
- Existing approvals and T1 manifests are not rewritten; changed policy/digest subjects require new exact approvals/manifests.
- No automatic retry, fallback, model switch, post-approval escalation, pacing, circuit breaker, historical-billing rewrite, or non-GLM policy change.
- No provider call, credential read, or shared-state mutation during implementation and offline verification.
- Implementation is inline in the existing isolated worktree; do not dispatch implementation subagents.

---

## File structure

### New or expanded interfaces

- `src/macr_runtime/providers/glm.py`
  - owns `GlmOutputBudgetDecision` and `glm_output_budget_decision(task, policy)`;
  - enforces the derived task requirement before request compilation;
  - projects the safe profile/requirement/recommendation through approval metadata.
- `src/macr_runtime/errors.py`
  - extends `ProviderOutputBudgetTooSmallError` with optional task-specific recommendation/profile fields without changing existing callers.
- `src/macr_runtime/token_policy.py`
  - owns the new immutable ordinary and T1 numeric policy values only.
- `src/macr_runtime/t1_manifest.py`
  - consumes the GLM decision and policy validator instead of requiring literal 16,384.
- `scripts/macr.ps1`
  - owns temporary Python UTF-8 process configuration and exact restoration.

### Tests

- `tests/test_token_policy.py`: exact ordinary/T1 policy values and digest changes.
- `tests/test_glm_provider.py`: two-band selection, safe diagnostics, exact 65K request/approval binding.
- `tests/test_t1_manifest.py`: T1 65K real-work enforcement and stale policy rejection.
- `tests/test_glm_wrapper.py`: real PowerShell/CLI multilingual output under a forced CP950 parent and environment restoration.
- `tests/test_examples.py`: conformance example remains the exact current offline envelope.
- Existing runtime/CLI/release-gate suites provide non-GLM and no-network regression coverage.

### Documentation

- `examples/glm-worker-task.example.json`
- `README.md`
- `CURRENT_VERSION_USAGE.md`
- `docs/ARCHITECTURE.md`
- `docs/PROVIDER_STATUS.md`
- `docs/GLM_CLAUDE_CODE_QUICKSTART.md`
- `docs/PROVENANCE.md`
- `docs/checkpoints/MACR-v0.7.0a0-glm-output-budget-auto-utf8.md`

---

### Task 1: Raise immutable GLM policy values

**Files:**
- Modify: `tests/test_token_policy.py`
- Modify: `src/macr_runtime/token_policy.py`

**Interfaces:**
- Consumes: existing `ModelTokenPolicyResolver.builtins_only()` and `t1_glm_live_policy()`.
- Produces: ordinary and T1 `ModelTokenPolicy` objects with the exact selected numeric fields; later tasks consume their `policy_digest`, minimum/default/maximum, and provider ceilings.

- [ ] **Step 1: Change the ordinary-policy test to the selected literal values**

Update `test_external_and_local_models_have_distinct_exact_policies` to assert:

```python
self.assertEqual(
    (
        glm.minimum_task_output_tokens,
        glm.default_output_tokens,
        glm.max_output_tokens,
    ),
    (32_768, 65_536, 65_536),
)
```

Retain every Grok/Gemini/MiniMax/Qwythos assertion unchanged.

- [ ] **Step 2: Change the T1-policy test to the selected literal values**

Update `test_t1_live_policy_is_separate_and_stricter_than_general_glm`:

```python
self.assertEqual(
    (
        live.minimum_task_output_tokens,
        live.default_output_tokens,
        live.max_output_tokens,
    ),
    (32_768, 65_536, 65_536),
)
self.assertEqual(live.hard_context_tokens, 128_000)
self.assertNotEqual(live.policy_digest, general.policy_digest)
```

- [ ] **Step 3: Run the two tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = 'src'
python -m unittest `
  tests.test_token_policy.ModelTokenPolicyTests.test_external_and_local_models_have_distinct_exact_policies `
  tests.test_token_policy.ModelTokenPolicyTests.test_t1_live_policy_is_separate_and_stricter_than_general_glm `
  -v
```

Expected: FAIL because ordinary GLM and T1 still expose 16,384 defaults/limits.

- [ ] **Step 4: Update only the two GLM policy constructors**

In `builtin_model_token_policies()`, change the `glm_flash_worker` row to:

```python
(
    "glm_flash_worker",
    "glm-5.3-flash",
    "external_https",
    32_768,
    400_000,
    512_000,
    65_536,
    65_536,
    1_000_000,
    131_072,
),
```

In `t1_glm_live_policy()`, use:

```python
minimum_task_output_tokens=32_768,
context_warning_tokens=100_000,
hard_context_tokens=128_000,
default_output_tokens=65_536,
max_output_tokens=65_536,
provider_context_ceiling_tokens=1_000_000,
provider_output_ceiling_tokens=131_072,
```

Do not change `_CLOUD_TEXT_QUALITY_FLOOR_TOKENS`; it remains the cross-provider structural floor, while the exact GLM policy is stricter.

- [ ] **Step 5: Re-run the two tests and verify GREEN**

Run the Step 3 command. Expected: PASS.

- [ ] **Step 6: Run the full token-policy/store adjacency**

```powershell
python -m unittest `
  tests.test_token_policy `
  tests.test_model_token_store `
  -q
```

Expected: PASS. Any old-base override fixture must remain immutable legacy evidence rather than becoming current under the new digest.

- [ ] **Step 7: Commit**

```powershell
git add src/macr_runtime/token_policy.py tests/test_token_policy.py
git commit -m "feat: raise GLM output quality policy"
```

---

### Task 2: Derive and enforce the pre-approval GLM output profile

**Files:**
- Modify: `tests/test_glm_provider.py`
- Modify: `src/macr_runtime/errors.py`
- Modify: `src/macr_runtime/providers/glm.py`

**Interfaces:**
- Consumes: `TaskContract`, `ReturnFormat`, and the exact `ModelTokenPolicy` from Task 1.
- Produces:
  - `GlmOutputBudgetDecision(profile: str, minimum_max_output_tokens: int, recommended_max_output_tokens: int)`;
  - `glm_output_budget_decision(task: TaskContract, token_policy: ModelTokenPolicy) -> GlmOutputBudgetDecision`;
  - safe diagnostic/approval fields `output_budget_profile`, `required_minimum_output_tokens`, and `recommended_max_output_tokens`.

- [ ] **Step 1: Write RED tests for the two profiles**

Add tests using the real provider preparation path and existing fake key/approval/transport helpers:

```python
def test_short_exact_conformance_uses_32768_profile(self):
    provider = _GlmFlashWorkerProvider(
        glm_config(),
        transport=FakeTransport(success_document()),
        environ={},
        key_source=StaticKeySource(),
        approval_store=AllowingApprovalStore(),
    )
    base = delegated_task(max_cost_usd=0.10)
    task = replace(
        base,
        task_type="provider_conformance",
        constraints=replace(base.constraints, max_output_tokens=32_768),
        return_contract=ReturnContract(
            summary=False,
            evidence=False,
            format=ReturnFormat.EXACT_TEXT,
            exact_text="MACR_GLM_OK",
        ),
    )
    metadata = provider.approval_metadata(task)
    self.assertEqual(metadata["output_budget_profile"], "short_exact_conformance")
    self.assertEqual(metadata["required_minimum_output_tokens"], 32_768)
    self.assertEqual(metadata["recommended_max_output_tokens"], 32_768)
```

```python
def test_quality_first_work_rejects_32768_and_recommends_65536(self):
    provider = _GlmFlashWorkerProvider(
        glm_config(),
        transport=FakeTransport(success_document()),
        environ={},
        key_source=StaticKeySource(),
        approval_store=AllowingApprovalStore(),
    )
    base = delegated_task(max_cost_usd=0.10)
    task = replace(
        base,
        constraints=replace(base.constraints, max_output_tokens=32_768),
    )
    with self.assertRaises(ProviderOutputBudgetTooSmallError) as raised:
        provider.approval_metadata(task)
    self.assertEqual(
        raised.exception.safe_diagnostic()["output_budget_profile"],
        "quality_first_work",
    )
    self.assertEqual(
        raised.exception.safe_diagnostic()["recommended_max_output_tokens"],
        65_536,
    )
```

```python
def test_quality_first_work_binds_exact_65536_request(self):
    provider = _GlmFlashWorkerProvider(
        glm_config(),
        transport=FakeTransport(success_document()),
        environ={},
        key_source=StaticKeySource(),
        approval_store=AllowingApprovalStore(),
    )
    base = delegated_task(max_cost_usd=0.10)
    task = replace(
        base,
        constraints=replace(base.constraints, max_output_tokens=65_536),
    )
    metadata = provider.approval_metadata(task)
    self.assertEqual(metadata["output_budget_profile"], "quality_first_work")
    self.assertEqual(metadata["required_minimum_output_tokens"], 65_536)
    self.assertEqual(metadata["recommended_max_output_tokens"], 65_536)
```

- [ ] **Step 2: Run the three tests and verify RED**

```powershell
python -m unittest `
  tests.test_glm_provider.GlmFlashWorkerProviderTests.test_short_exact_conformance_uses_32768_profile `
  tests.test_glm_provider.GlmFlashWorkerProviderTests.test_quality_first_work_rejects_32768_and_recommends_65536 `
  tests.test_glm_provider.GlmFlashWorkerProviderTests.test_quality_first_work_binds_exact_65536_request `
  -v
```

Expected: FAIL because profile metadata and task-specific enforcement do not exist.

- [ ] **Step 3: Extend the bounded output-budget diagnostic**

Add optional keyword parameters to `ProviderOutputBudgetTooSmallError`:

```python
recommended_max_output_tokens: int | None = None,
output_budget_profile: str | None = None,
```

Validate any profile with `_SAFE_DIAGNOSTIC_IDENTIFIER`. Add the two keys to
`safe_diagnostic()` only when supplied. Existing generic model-policy callers
remain byte-for-byte equivalent except for the unchanged existing fields.

- [ ] **Step 4: Implement the pure selector**

In `providers/glm.py` add:

```python
@dataclass(frozen=True)
class GlmOutputBudgetDecision:
    profile: str
    minimum_max_output_tokens: int
    recommended_max_output_tokens: int


def glm_output_budget_decision(
    task: TaskContract,
    token_policy: ModelTokenPolicy,
) -> GlmOutputBudgetDecision:
    exact = task.return_contract.exact_text
    short_exact = (
        task.task_type == "provider_conformance"
        and task.return_contract.format is ReturnFormat.EXACT_TEXT
        and isinstance(exact, str)
        and len(exact.encode("utf-8")) <= 256
    )
    value = (
        token_policy.minimum_task_output_tokens
        if short_exact
        else token_policy.default_output_tokens
    )
    return GlmOutputBudgetDecision(
        profile=(
            "short_exact_conformance"
            if short_exact
            else "quality_first_work"
        ),
        minimum_max_output_tokens=value,
        recommended_max_output_tokens=value,
    )
```

The function must reject non-`TaskContract`/non-`ModelTokenPolicy` arguments.

- [ ] **Step 5: Enforce the decision before generic max validation**

In `_check_task_policy`, derive the decision. If the requested value is below
its minimum, raise `ProviderOutputBudgetTooSmallError` with the task-specific
minimum, recommendation, and profile. Then call
`self.token_policy.validate_task_output_tokens()` to enforce the exact maximum.

Do not mutate `task.constraints`.

- [ ] **Step 6: Bind safe metadata to preflight/approval output**

In `_safe_approval_metadata`, add:

```python
decision = glm_output_budget_decision(task, self.token_policy)
```

and project:

```python
"output_budget_profile": decision.profile,
"required_minimum_output_tokens": decision.minimum_max_output_tokens,
"recommended_max_output_tokens": decision.recommended_max_output_tokens,
```

The already existing `request_payload.max_tokens` and approval manifest
continue to bind the caller-selected exact integer.

- [ ] **Step 7: Re-run the three RED tests and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 8: Add falsifying controls**

Add literal tests proving:

- a 257-byte exact expected string selects `quality_first_work`;
- `delegated_routine` plus a short exact return still selects
  `quality_first_work`;
- 65,537 is rejected by the existing exact policy maximum;
- no key/transport call occurs for an under-profile request;
- the safe diagnostic contains no goal/input/expected-text bytes.

Run:

```powershell
python -m unittest tests.test_glm_provider -q
```

Expected: PASS with no network.

- [ ] **Step 9: Commit**

```powershell
git add src/macr_runtime/errors.py src/macr_runtime/providers/glm.py tests/test_glm_provider.py
git commit -m "feat: derive GLM output budget before approval"
```

---

### Task 3: Apply quality-first output semantics to T1

**Files:**
- Modify: `tests/test_t1_manifest.py`
- Modify: `tests/test_t1_dispatcher.py`
- Modify: `tests/test_multiprocess_runtime.py`
- Modify: `tests/test_cli.py`
- Modify: `src/macr_runtime/t1_manifest.py`

**Interfaces:**
- Consumes: `t1_glm_live_policy()` from Task 1 and `glm_output_budget_decision()` from Task 2.
- Produces: schema-4 T1 members whose exact output is profile-valid and digest-bound; schema number stays 4.

- [ ] **Step 1: Change T1 task fixtures from 16,384 to 65,536**

In the shared `task(ordinal)` helper, use:

```python
max_output_tokens=65_536,
max_cost_usd=0.05,
```

Keep dynamic member count, worker count, aggregate sum, campaign ceiling,
privacy, target, and dispatcher behavior unchanged. Update helper aggregate
cost calculations from `0.010 * member_count` to `0.050 * member_count` only
where those helpers represent the new ordinary T1 real-work preset.

- [ ] **Step 2: Add a RED test for T1 task-specific output enforcement**

```python
def test_t1_real_work_requires_quality_first_output(self):
    accepted = manifest(member_count=1, worker_count=1)
    self.assertEqual(accepted.members[0].task.constraints.max_output_tokens, 65_536)

    task_32k = replace(
        accepted.members[0].task,
        constraints=replace(
            accepted.members[0].task.constraints,
            max_output_tokens=32_768,
        ),
    )
    with self.assertRaisesRegex(ValueError, "output budget"):
        T1ExecutionMember.create(
            plan_digest=accepted.plan_digest,
            ordinal=0,
            task=task_32k,
            route=accepted.members[0].route,
            token_policy_digest=t1_glm_live_policy().policy_digest,
            provider_tier_binding_digest=accepted.members[0].provider_tier_binding_digest,
            role_digest=accepted.members[0].role_digest,
            privacy=accepted.members[0].privacy,
            context_class=accepted.members[0].context_class,
            cost_ceiling_usd=accepted.members[0].cost_ceiling_usd,
            target_claims=accepted.members[0].target_claims,
        )
```

- [ ] **Step 3: Run the T1 manifest test and verify RED**

```powershell
python -m unittest `
  tests.test_t1_manifest.T1ManifestTests.test_t1_real_work_requires_quality_first_output `
  -v
```

Expected: FAIL while `T1ExecutionMember` still requires literal 16,384.

- [ ] **Step 4: Replace the literal T1 check with shared policy/decision checks**

In `_validate_task()`:

```python
policy = t1_glm_live_policy()
decision = glm_output_budget_decision(task, policy)
policy.validate_task_output_tokens(task.constraints.max_output_tokens)
if task.constraints.max_output_tokens < decision.minimum_max_output_tokens:
    raise ValueError("T1 task output budget is below its GLM output profile")
```

Remove only the literal `max_output_tokens != 16_384` branch. Keep every other
T1 restriction intact.

- [ ] **Step 5: Re-run T1 manifest tests and verify GREEN**

```powershell
python -m unittest tests.test_t1_manifest -q
```

Expected: PASS.

- [ ] **Step 6: Update dispatcher/CLI/multiprocess fixtures mechanically**

Raise fixture task output and exact member costs where the new conservative
65K request envelope requires it. Do not weaken aggregate equality or campaign
coverage. Run:

```powershell
python -m unittest `
  tests.test_t1_dispatcher `
  tests.test_multiprocess_runtime `
  tests.test_cli `
  -q
```

Expected: PASS. The five-member/four-worker and five-process complete-path
controls must retain the same queue/provider-attempt counts.

- [ ] **Step 7: Prove old T1 policy evidence fails closed**

Construct a schema-4 manifest document using the pre-change T1 policy digest
literal captured from the parent commit and assert `load_t1_manifest()` rejects
it before staging. Read the bytes before and after and assert equality. Do not
label it as schema 1/2/3 legacy evidence; it is a stale schema-4 exact subject.

- [ ] **Step 8: Commit**

```powershell
git add `
  src/macr_runtime/t1_manifest.py `
  tests/test_t1_manifest.py `
  tests/test_t1_dispatcher.py `
  tests/test_multiprocess_runtime.py `
  tests/test_cli.py
git commit -m "feat: raise T1 GLM output budget"
```

---

### Task 4: Make the PowerShell entry point own UTF-8

**Files:**
- Modify: `tests/test_glm_wrapper.py`
- Modify: `scripts/macr.ps1`

**Interfaces:**
- Consumes: current positional `macr.ps1` argument forwarding.
- Produces: one Python invocation with child-only UTF-8 settings, restored caller environment, and unchanged exit-code semantics.

- [ ] **Step 1: Write a real forced-CP950 Korean-output test**

Import `os`, `TaskContract`, and `tests.helpers.process_capture.run_bytes`. Use
a D-drive temporary task and build it exactly as follows:

```python
korean_goal = "한국어 출력 검증"
task_path = temp / "korean-task.json"
task_path.write_text(
    json.dumps(
        TaskContract(
            task_id="utf8-korean-validation",
            goal=korean_goal,
        ).to_dict(),
        ensure_ascii=False,
    ),
    encoding="utf-8",
)
environment = {
    **os.environ,
    "PYTHONUTF8": "0",
    "PYTHONIOENCODING": "cp950",
    "MACR_ROOT": str(ROOT),
    "MACR_STATE_ROOT": str(temp),
}
capture = run_bytes(
    [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ROOT / "scripts" / "macr.ps1"),
        "validate-task",
        str(task_path),
    ],
    cwd=ROOT,
    env=environment,
)
self.assertEqual(capture.returncode, 0, capture.stderr)
self.assertIn(korean_goal.encode("utf-8"), capture.stdout_bytes)
self.assertNotIn(b"UnicodeEncodeError", capture.stderr_bytes)
```

- [ ] **Step 2: Run the test and verify RED**

```powershell
python -m unittest `
  tests.test_glm_wrapper.GlmWrapperTests.test_macr_wrapper_forces_utf8_for_korean_output `
  -v
```

Expected: FAIL with the current CP950 child output path.

- [ ] **Step 3: Add a caller-environment restoration RED test**

Run one outer `powershell.exe -Command` that sets sentinel values, invokes
`macr.ps1 validate-task` with output redirected to `$null`, and then prints the
two exact sentinel values. Assert the outer values remain unchanged and the
invalid-task exit code remains the Python exit code.

- [ ] **Step 4: Implement child-only UTF-8 with `try/finally`**

In `scripts/macr.ps1`, preserve both existence and value:

```powershell
$hadPythonUtf8 = Test-Path Env:PYTHONUTF8
$previousPythonUtf8 = $env:PYTHONUTF8
$hadPythonIoEncoding = Test-Path Env:PYTHONIOENCODING
$previousPythonIoEncoding = $env:PYTHONIOENCODING
$exitCode = 1
try {
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    python -X utf8 -m macr_runtime @MacrArguments
    $exitCode = $LASTEXITCODE
}
finally {
    if ($hadPythonUtf8) { $env:PYTHONUTF8 = $previousPythonUtf8 }
    else { Remove-Item Env:PYTHONUTF8 -ErrorAction SilentlyContinue }
    if ($hadPythonIoEncoding) {
        $env:PYTHONIOENCODING = $previousPythonIoEncoding
    }
    else {
        Remove-Item Env:PYTHONIOENCODING -ErrorAction SilentlyContinue
    }
    $previousPythonUtf8 = $null
    $previousPythonIoEncoding = $null
}
exit $exitCode
```

Do not alter `MACR_ROOT`, `MACR_STATE_ROOT`, `PYTHONPATH`, or the separate
`invoke-glm.ps1` Z.ai-key scope.

- [ ] **Step 5: Re-run wrapper tests and verify GREEN**

```powershell
python -W error::ResourceWarning -m unittest tests.test_glm_wrapper -q
```

Expected: PASS with Korean UTF-8 bytes and restored caller environment.

- [ ] **Step 6: Commit**

```powershell
git add scripts/macr.ps1 tests/test_glm_wrapper.py
git commit -m "fix: make MACR PowerShell output UTF-8"
```

---

### Task 5: Regenerate the conformance example and offline approval subject

**Files:**
- Modify: `examples/glm-worker-task.example.json`
- Modify: `tests/test_examples.py`

**Interfaces:**
- Consumes: policy and selector from Tasks 1–2.
- Produces: a 32,768-token short-conformance example whose carried digest equals the current compiled offline envelope.

- [ ] **Step 1: Change the example test to require 32,768**

In `test_glm_example_requires_explicit_public_delegation`:

```python
self.assertEqual(task.constraints.max_output_tokens, 32_768)
```

Keep `test_glm_example_digest_matches_current_offline_envelope` unchanged; it
must catch the stale carried digest.

- [ ] **Step 2: Run both example tests and verify RED**

```powershell
python -m unittest `
  tests.test_examples.ExampleContractTests.test_glm_example_requires_explicit_public_delegation `
  tests.test_examples.ExampleContractTests.test_glm_example_digest_matches_current_offline_envelope `
  -v
```

Expected: FAIL for the 16,384 value and old policy/approval digest.

- [ ] **Step 3: Update the example output value**

Use `apply_patch` to set:

```json
"max_output_tokens": 32768
```

Temporarily set `delegation_approval_sha256` to 64 lowercase zeroes so the JSON
remains structurally complete while computing the required current digest.

- [ ] **Step 4: Compute the current digest without credentials or network**

```powershell
.\scripts\macr.ps1 glm-preflight `
  .\examples\glm-worker-task.example.json `
  --show-required-digest
```

Expected: exit 0 with `requested_max_output_tokens=32768`,
`output_budget_profile=short_exact_conformance`, and one lowercase
`required_approval_sha256`. Use `apply_patch` to copy that exact returned value
into the example. Do not create a host approval in the feature worktree.

- [ ] **Step 5: Re-run the example tests and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 6: Prove preflight still requires a new host record**

```powershell
.\scripts\macr.ps1 glm-preflight .\examples\glm-worker-task.example.json
```

Expected before deployment approval: `approval_invalid`, exit 4, no credential
read, and no network.

- [ ] **Step 7: Commit**

```powershell
git add examples/glm-worker-task.example.json tests/test_examples.py
git commit -m "test: refresh GLM conformance envelope"
```

---

### Task 6: Update active operator documentation and checkpoint

**Files:**
- Modify: `README.md`
- Modify: `CURRENT_VERSION_USAGE.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/PROVIDER_STATUS.md`
- Modify: `docs/GLM_CLAUDE_CODE_QUICKSTART.md`
- Modify: `docs/PROVENANCE.md`
- Create: `docs/checkpoints/MACR-v0.7.0a0-glm-output-budget-auto-utf8.md`

**Interfaces:**
- Consumes: exact implementation commits, policy digests, test counts, and offline evidence from Tasks 1–5.
- Produces: one current user/AI operating contract and one version-bound checkpoint; historical checkpoints remain unchanged.

- [ ] **Step 1: Update every active policy table and command explanation**

Record ordinary GLM 32K minimum / 65K default+maximum and T1 32K minimum /
65K default+maximum. Explain the two profiles and that real work uses 65K.
Remove active claims that T1 is fixed at 16K. Do not rewrite historical v0.6
or earlier checkpoint evidence.

- [ ] **Step 2: Document compatibility and cost consequences**

State explicitly:

- old approval/T1 digests are immutable but unusable under the new policy;
- every still-needed task is regenerated/reapproved;
- `max_cost_usd` must cover the new conservative envelope;
- actual billing remains based on provider observation, not the cap;
- no automatic retry or post-approval escalation exists.

- [ ] **Step 3: Document Windows UTF-8 ownership**

Record that `macr.ps1` owns temporary child values and restores outer
`PYTHONUTF8`/`PYTHONIOENCODING`. Include no environment secret or Korean
candidate text.

- [ ] **Step 4: Write the checkpoint with exact evidence**

The checkpoint must contain:

- implementation commit/tree;
- old and new ordinary/T1 policy digests;
- RED/GREEN test names;
- full/Phase-C gate counts;
- `network_activity=false`, `provider_generation=false`;
- explicit statement that the original four `provider_execution` failures are
  unresolved and unrelated to the new HTTP-200 reasoning-exhaustion witness;
- exact source paths but no credential, prompt, answer, or private task body.

- [ ] **Step 5: Run documentation/release tests**

```powershell
python -m unittest `
  tests.test_examples `
  tests.test_google_docs `
  tests.test_v06_release_gate `
  tests.test_v07_release `
  -q
git diff --check
```

Expected: PASS and no whitespace errors.

- [ ] **Step 6: Commit**

```powershell
git add `
  README.md `
  CURRENT_VERSION_USAGE.md `
  docs/ARCHITECTURE.md `
  docs/PROVIDER_STATUS.md `
  docs/GLM_CLAUDE_CODE_QUICKSTART.md `
  docs/PROVENANCE.md `
  docs/checkpoints/MACR-v0.7.0a0-glm-output-budget-auto-utf8.md
git commit -m "docs: checkpoint GLM quality-first output policy"
```

---

### Task 7: Verify, review, and prepare deployment

**Files:**
- Verify all changed source/tests/docs.
- Do not modify shared provider/accounting state during the feature gate.

**Interfaces:**
- Consumes: exact clean feature branch from Tasks 1–6.
- Produces: an exact merge candidate and a separately gated deployment sequence.

- [ ] **Step 1: Run focused policy/provider/T1/wrapper regression**

```powershell
$env:PYTHONPATH = 'src'
python -W error::ResourceWarning -m unittest `
  tests.test_token_policy `
  tests.test_model_token_store `
  tests.test_glm_provider `
  tests.test_t1_manifest `
  tests.test_t1_dispatcher `
  tests.test_multiprocess_runtime `
  tests.test_glm_wrapper `
  tests.test_examples `
  tests.test_cli `
  -q
```

Expected: PASS with only documented platform capability skips.

- [ ] **Step 2: Run the complete repository suite**

```powershell
python -W error::ResourceWarning -m unittest discover -s tests -q
```

Expected: PASS with no warning output and only existing Windows capability
skips.

- [ ] **Step 3: Commit any verification-only checkpoint correction**

If the actual counts/digests differ from pre-gate documentation, update only
the checkpoint/provenance with observed values via `apply_patch`, rerun the
focused documentation tests, and commit:

```powershell
git commit -m "docs: finalize GLM output policy checkpoint"
```

Do not change product code merely to match a predicted count.

- [ ] **Step 4: Run the clean Phase-C gate**

```powershell
.\scripts\verify-v07-phase-c.ps1
```

Expected: exit 0, exact candidate commit/tree, full and focused counts,
deterministic wheel replay, `network_activity=false`,
`provider_generation=false`, `phase_d_started=false`, and `git_clean=true`.

- [ ] **Step 5: Run one narrow governing-Twin review if the existing Twin responds**

Provide only the exact commit/tree, selected policy values, selector contract,
UTF-8 wrapper contract, changed-file list, and gate summary. Ask for
`IDLE`/`CONCUR`/`CHALLENGE` on policy bypass, silent mutation, non-GLM drift,
locale restoration, and stale approval/T1 behavior. If the Twin remains
unavailable after one bounded wait, interrupt it and record degraded review;
do not simulate concurrence or spawn additional agents.

- [ ] **Step 6: Present the exact merge candidate for operator integration authority**

Report the feature commit/tree, tests, skips, no-network evidence, stale
approval consequence, and the pending post-merge local approval action. Do not
merge/push merely because tests are green unless the operator has explicitly
authorized integration for this exact subject.

---

### Task 8: Post-approval merge and local activation

**Files:**
- Merge-only Git state.
- Shared state mutation: one exact conformance host-approval record only.
- Do not modify or delete unrelated untracked files.

**Interfaces:**
- Consumes: explicit operator integration authority and exact green candidate from Task 7.
- Produces: local/GitHub `main`, refreshed conformance approval, and a no-network activation receipt.

- [ ] **Step 1: Fetch and verify fast-forward ancestry**

```powershell
git fetch origin main
git merge-base --is-ancestor origin/main feature/glm-output-budget-auto-utf8
git -C 'D:\Ai\work together\MACR' status --short
```

Expected: ancestry exit 0; only the pre-existing untracked
`REQUEST_FOR_CODEX_T1_LIVE_ROUTE.md` may appear in the canonical checkout.

- [ ] **Step 2: Fast-forward local `main`**

```powershell
Set-Location 'D:\Ai\work together\MACR'
git merge --ff-only feature/glm-output-budget-auto-utf8
```

- [ ] **Step 3: Re-run the complete suite on merged `main`**

```powershell
$env:PYTHONPATH = 'src'
python -W error::ResourceWarning -m unittest discover -s tests -q
```

Expected: the same test count/result as the feature candidate.

- [ ] **Step 4: Create the exact new conformance host approval without network**

```powershell
.\scripts\macr.ps1 glm-preflight `
  .\examples\glm-worker-task.example.json `
  --show-required-digest
.\scripts\macr.ps1 glm-approve `
  .\examples\glm-worker-task.example.json `
  --expires-in-days 30
.\scripts\macr.ps1 glm-preflight `
  .\examples\glm-worker-task.example.json
```

Expected: carried/required digest equality, one new host approval, then
`preflight_structurally_valid`; no provider call. Use `--replace-existing` only
if the exact new digest already exists and the operator explicitly intends to
renew it.

- [ ] **Step 5: Do not bulk-approve external task files**

Report that Claude's remaining Korean tasks must be regenerated at 65,536,
receive new exact digests, satisfy their larger conservative cost ceilings, and
be individually approved. Do not scan or mutate private task directories by
assumption.

- [ ] **Step 6: Push and verify GitHub main**

```powershell
git push origin main
git ls-remote origin refs/heads/main
git rev-parse HEAD
```

Expected: remote and local exact SHA equality.

- [ ] **Step 7: Clean the owned worktree only after successful merge/push**

From `D:\Ai\work together\MACR`, verify the feature worktree is clean, resolve
its exact path beneath `.worktrees`, remove it with `git worktree remove`, run
`git worktree prune`, and delete the merged feature branch with `git branch -d`.
Never use `--force`.

- [ ] **Step 8: Hand off one bounded live test, not a batch**

Tell Claude to generate a new exact 65,536-token task and perform one separately
authorized invocation with UTF-8 variables deliberately absent. It must report
finish reason, reasoning/completion tokens, safe transport telemetry, cost,
accounting delta, and absence of retry/fallback. This step is not executed by
the implementation plan itself.
