# MACR v0.7.0a0 Host Adapters and GLM Capability Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the measured locale, timeout, failure-visibility and accounting defects; add operator-owned GLM capability tiers; and give Codex and Claude Code one shared, attributable MACR delegation path.

**Architecture:** Keep `TaskContract` provider-neutral. Resolve one immutable provider/model tier binding from a separate append-only operator policy store, then bind its exact digest through authority, approval, dispatch, accounting and T1 evidence. Codex and Claude use the same host adapter; only trusted host-provided environment bindings differ.

**Tech Stack:** Python 3.11+ dataclasses and `unittest`, SQLite WAL stores, PowerShell 5.1 launch/gate scripts, argparse CLI, existing MACR provider/runtime contracts.

**Spec:** `docs/superpowers/specs/2026-09-07-macr-v070a0-host-adapters-glm-policy-design.md`

## Global Constraints

- Work only on `feature/v070a0-host-adapters-glm-policy` in the D-drive linked worktree.
- Keep package version `0.7.0a0`; merge, tag, push, release and deployment are separate decisions.
- Do not read provider keys, call a provider, migrate shared state, or activate a shared capability policy.
- Claude subscription is not Anthropic API authority; add no `ANTHROPIC_API_KEY` path.
- Provider completion remains an unverified candidate; no retry, fallback, materialization, write or tool grant.
- GLM `extended_text_candidate` remains non-sensitive and text-only: 900 seconds, no patch, no write scope, no tools.
- Historical approval, authority, event, accounting/outbox and T1 bytes stay immutable and audit-readable as `legacy_pre_tier`; they cannot satisfy a new GLM dispatch.
- Every production behavior is introduced by a test that is observed RED before implementation and GREEN afterward.

---

### Task 1: Locale-safe process capture and machine-readable test counts

**Files:**
- Create: `tests/helpers/process_capture.py`
- Create: `tests/helpers/unittest_json.py`
- Create: `tests/test_process_capture.py`
- Create: `tests/test_unittest_json.py`
- Create: `tests/fixtures/unittest-json-subject/test_sample.py`
- Modify: `tests/test_direct_launcher_scripts.py`
- Modify: `scripts/verify.ps1`
- Modify: `scripts/verify-v07-phase-a.ps1`
- Modify: `scripts/verify-v07-phase-b.ps1`
- Modify: `scripts/verify-v07-phase-c.ps1`

**Interfaces:**
- Produces: `CapturedProcess(returncode, stdout_bytes, stderr_bytes)`, `render_utf8(bytes) -> str`, and `assert_canaries_absent(capture, canaries)`.
- Produces: `python tests/helpers/unittest_json.py <module>...` with one UTF-8 `UNITTEST_SUMMARY=<json>` line and an exit code derived from `unittest` success.
- Consumes: PowerShell wrappers parse only `UNITTEST_SUMMARY`, never localized `Ran N tests` prose.

- [ ] **Step 1: Write the raw-byte regression tests**

```python
def test_non_utf8_stderr_is_preserved_and_rendered_without_reader_failure():
    capture = run_bytes((sys.executable, "-c", "import os; os.write(2, b'bad\\xa6')"))
    self.assertEqual(capture.stderr_bytes, b"bad\xa6")
    self.assertEqual(render_utf8(capture.stderr_bytes), "bad\ufffd")

def test_canary_scan_checks_raw_stdout_and_stderr_before_rendering():
    capture = CapturedProcess(1, b"", b"uuid-token\xa6")
    with self.assertRaisesRegex(AssertionError, "stderr"):
        assert_canaries_absent(capture, (b"uuid-token",))
```

- [ ] **Step 2: Run the new tests and observe RED**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_process_capture -v`

Expected: import failure for `tests.helpers.process_capture`.

- [ ] **Step 3: Implement bytes-first capture and the JSON unittest runner**

```python
@dataclass(frozen=True)
class CapturedProcess:
    returncode: int
    stdout_bytes: bytes
    stderr_bytes: bytes

def run_bytes(argv, *, cwd=None, env=None):
    completed = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=False)
    return CapturedProcess(completed.returncode, completed.stdout, completed.stderr)

def render_utf8(value: bytes) -> str:
    return value.decode("utf-8-sig", errors="replace")
```

The unittest runner builds the requested suite directly, writes captured failure diagnostics to stderr as UTF-8 with replacement-safe serialization, and emits literal fields `tests_run`, `failures`, `errors`, `skipped`, and `successful` on stdout.

- [ ] **Step 4: Convert launcher assertions and Phase A-C gates**

`test_direct_launcher_scripts.py` must scan the exact raw secret and UUID bytes before rendering diagnostics. Each Phase script invokes the JSON runner, selects the `UNITTEST_SUMMARY=` line, requires `successful=true`, and reads `tests_run` as an integer.

- [ ] **Step 5: Run focused and wrapper controls**

Run:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_process_capture tests.test_direct_launcher_scripts -v
.\scripts\verify-v07-phase-c.ps1
```

Expected: focused tests pass; Phase C emits one summary with `network_activity=false` and `provider_generation=false`.

- [ ] **Step 6: Commit the locale repair**

```powershell
git add tests/helpers/process_capture.py tests/helpers/unittest_json.py tests/test_process_capture.py tests/test_unittest_json.py tests/fixtures/unittest-json-subject/test_sample.py tests/test_direct_launcher_scripts.py scripts/verify.ps1 scripts/verify-v07-phase-a.ps1 scripts/verify-v07-phase-b.ps1 scripts/verify-v07-phase-c.ps1
git commit -m "test: make Windows verification locale safe"
```

---

### Task 2: Immutable provider capability policies and operator activation

**Files:**
- Create: `src/macr_runtime/provider_capability.py`
- Create: `src/macr_runtime/provider_capability_store.py`
- Create: `tests/test_provider_capability.py`
- Create: `tests/test_provider_capability_store.py`
- Modify: `src/macr_runtime/storage.py`
- Modify: `src/macr_runtime/runtime.py`
- Modify: `src/macr_runtime/__init__.py`

**Interfaces:**
- Produces: `ProviderCapabilityPolicy`, `ProviderTierBinding`, `ProviderCapabilityResolver`, `ProviderCapabilityPolicyStore`, and `OperatorTierActivationVerifier`.
- Produces: `glm_standard_policy()` and `glm_extended_text_policy()` built-ins.
- Produces: `StorageLayout.provider_capability_policy_db_path` at `settings/provider-capability-policies.sqlite3`.
- Produces: a read-only resolution path that treats an absent database as built-in standard and never creates a file during preflight.
- Invariant: `binding_digest = SHA256(canonical_json(provider_id, model, tier_id, revision, complete_policy_digest, effective_limits))`.

- [ ] **Step 1: Write policy and outer-binding discriminator tests**

```python
def test_binding_digest_changes_when_any_outer_identity_field_changes():
    baseline = binding(provider="glm_flash_worker", model="glm-5.3-flash", tier="standard", revision=1, timeout=300)
    variants = (
        replace(baseline, provider_id="other"),
        replace(baseline, model="other"),
        replace(baseline, tier_id="extended_text_candidate"),
        replace(baseline, revision=2),
        replace(baseline, effective_limits={"max_latency_s": 301}),
    )
    self.assertTrue(all(item.binding_digest != baseline.binding_digest for item in variants))
```

Add literal tests for standard task types/300 seconds and extended task types/900 seconds, both rejecting patch, write scope, tools, disabled verification, frontier/private delegation, and non-approved privacy.

- [ ] **Step 2: Run policy tests and observe RED**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_provider_capability -v`

Expected: import failure for `macr_runtime.provider_capability`.

- [ ] **Step 3: Implement canonical policies and binding resolution**

```python
@dataclass(frozen=True)
class ProviderTierBinding:
    provider_id: str
    model: str
    tier_id: str
    revision: int
    complete_policy_digest: str
    effective_limits: Mapping[str, int]

    @property
    def binding_digest(self) -> str:
        return sha256_id("provider_tier_binding_v1", self.to_dict(include_digest=False))
```

The resolver returns immutable GLM standard revision 1 when no activation exists. A present but corrupt, stale, unsupported or mismatched activation raises `ProviderPolicyError` without fallback.

- [ ] **Step 4: Write store RED tests**

Cover create-once idempotence, conflicting same revision, authorized activation, absent-activation standard fallback, corrupt body/digest rejection, wrong provider/model/tier activation, another provider being unable to inherit GLM policy, and missing/fabricated activation witness leaving the active pointer byte-for-byte unchanged.

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_provider_capability_store -v`

Expected: import failure for `ProviderCapabilityPolicyStore`.

- [ ] **Step 5: Implement append-only SQLite policy store**

Use three tables: `provider_capability_schema_meta`, `provider_capability_policies`, and `provider_capability_active`. Save canonical policy bytes plus SHA-256; activation points to an existing exact revision and binding digest. `activate()` requires a separately injected verifier to validate a pre-existing operator witness for that exact digest; the store cannot issue one. All writes use `BEGIN IMMEDIATE`, WAL, FULL synchronous, and the existing D-drive storage policy. `read_effective_binding(path, provider_id, model)` opens an existing database read-only and returns built-in standard when the file is absent; it never initializes a database.

- [ ] **Step 6: Wire storage and runtime services, then run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_provider_capability tests.test_provider_capability_store tests.test_storage -v
```

Expected: all focused tests pass and no shared-state path is opened.

- [ ] **Step 7: Commit capability policy core**

```powershell
git add src/macr_runtime/provider_capability.py src/macr_runtime/provider_capability_store.py src/macr_runtime/storage.py src/macr_runtime/runtime.py src/macr_runtime/__init__.py tests/test_provider_capability.py tests/test_provider_capability_store.py tests/test_storage.py
git commit -m "feat: add operator-owned provider capability policies"
```

---

### Task 3: Bind capability identity through authority, outcomes and accounting

**Files:**
- Modify: `src/macr_runtime/authority.py`
- Modify: `src/macr_runtime/dispatch.py`
- Modify: `src/macr_runtime/execution.py`
- Modify: `src/macr_runtime/contracts.py`
- Modify: `src/macr_runtime/runtime.py`
- Modify: `src/macr_runtime/accounting.py`
- Modify: `tests/test_dispatch_authority.py`
- Modify: `tests/test_runtime_v05.py`
- Modify: `tests/test_accounting.py`

**Interfaces:**
- `AuthorityScope.provider_tier_binding_digests: tuple[str, ...]` and `permits(..., provider_tier_binding_digest)`.
- `AuthorityScope.to_dict()` emits `scope_contract_version=2`; legacy documents without it remain audit-readable but cannot permit a tier-bound request.
- `DispatchContext.provider_tier_binding_digest: str | None` plus `dispatch_contract_version=2` in new event payloads.
- `ProviderResult.failure_code` and `failure_stage` are optional stable top-level fields; exception messages/bodies remain absent.
- `AccountingStore.SCHEMA_VERSION = 3`; `status_snapshot() -> AccountingStatusSnapshot` uses a fixed number of SQL statements.

- [ ] **Step 1: Write authority mismatch RED tests**

Issue an authority for one literal binding digest and prove exact digest passes while a different digest and `None` fail. Verify old scopes parse for audit but report `legacy_pre_tier` and cannot authorize a tier-bound GLM request.

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_dispatch_authority -v`

Expected: `AuthorityScope` does not accept the new field.

- [ ] **Step 2: Implement authority/context binding**

Add the digest tuple to canonical scope JSON, thread the requested digest through `AdmissionGate.admit()` and `DispatchAuthorityStore.verify()`, and add it to `DispatchContext` validation. Existing non-tier providers may use `None`; GLM callers may not.

- [ ] **Step 3: Write typed failure RED tests**

```python
result = runtime.invoke("glm_flash_worker", task, context)
self.assertEqual(result.failure_code, "TimeoutError")
self.assertEqual(result.failure_stage, "provider_execution")
self.assertNotIn("remote secret", json.dumps(result.to_dict()))
```

Also assert return-contract rejection uses `ReturnContractError/return_contract` and admission/token failures expose their own stable stages.

- [ ] **Step 4: Implement typed result failure fields**

Add validated optional fields to `ProviderResult`; include them in `to_dict()` only when present. Populate them in the three runtime failure constructors and return-contract rejection. Keep `provider_meta.failure_type` temporarily for compatibility, but make top-level fields authoritative.

- [ ] **Step 5: Write accounting migration/outbox/status RED tests**

Create a real schema-2 database fixture, open it with the new store, and assert old invocation rows remain unchanged with null tier/failure columns. Record a new invocation and assert schema-2 outbox payload binds tier digest and typed failure. Install a SQLite trace callback and prove `status_snapshot()` executes the same statement count for 0, 1 and 100 runs while reporting:

```text
known_cost_usd
unknown_after_dispatch_count
unsettled_count
legacy_pre_tier_count
pending_invocation_outbox_count
pending_plan_cost_outbox_count
pending_bill_observation_outbox_count
```

- [ ] **Step 6: Implement schema-3 migration and fixed-query snapshot**

Use additive nullable columns `provider_tier_binding_digest`, `failure_code`, and `failure_stage`. Migrate version 2 to 3 inside the existing transaction, never rewriting payload JSON. New terminal outboxes use payload schema 2; old schema-1 rows remain byte-identical.

- [ ] **Step 7: Run focused cross-boundary tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_dispatch_authority tests.test_runtime_v05 tests.test_accounting tests.test_runtime_ledger -v
```

Expected: all tests pass; no key or network access occurs.

- [ ] **Step 8: Commit authority/outcome/accounting binding**

```powershell
git add src/macr_runtime/authority.py src/macr_runtime/dispatch.py src/macr_runtime/execution.py src/macr_runtime/contracts.py src/macr_runtime/runtime.py src/macr_runtime/accounting.py tests/test_dispatch_authority.py tests/test_runtime_v05.py tests/test_accounting.py tests/test_runtime_ledger.py
git commit -m "feat: bind provider tiers through dispatch accounting"
```

---

### Task 4: Remove GLM timeout clamp and require approval schema 3

**Files:**
- Modify: `src/macr_runtime/providers/glm.py`
- Modify: `src/macr_runtime/registry.py`
- Modify: `src/macr_runtime/cli.py`
- Modify: `tests/test_glm_provider.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- `GlmFlashWorkerProvider(..., capability_binding: ProviderTierBinding | None = None)` defaults to immutable standard.
- Registry resolves the active binding from `ProviderCapabilityPolicyStore` and exposes `capability_binding(provider_id)`.
- GLM approval schema 3 binds `task_id`, exact `max_latency_s`, and `provider_tier_binding_digest`.

- [ ] **Step 1: Write no-clamp and early-rejection RED tests**

Use a recording fake transport and key source that raises if touched. Prove standard 300 and extended 900 arrive at `post_json(timeout_s=...)` unchanged; standard 301 and extended 901 fail before key/transport. Prove allowed extended task types pass policy while patch/write/tools/frontier/private cases fail.

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_glm_provider -v`

Expected: the 900-second case records 300 and the new constructor argument is unsupported.

- [ ] **Step 2: Implement policy-driven task validation and exact timeout**

Replace `_ALLOWED_TASK_TYPES` and the literal clamp with the resolved binding policy. `_check_task_policy()` compares every task requirement against that policy; `_post_validated_task_once()` passes `task.constraints.max_latency_s` unchanged after the preflight ceiling check.

- [ ] **Step 3: Upgrade approval manifest to schema 3**

The canonical manifest includes:

```python
{
    "approval_schema": 3,
    "task_id": task.task_id,
    "max_latency_s": task.constraints.max_latency_s,
    "provider_tier_binding_digest": self.capability_binding.binding_digest,
    # existing provider/model/privacy/budget/token/request fields
}
```

Add discriminator tests changing task ID, latency, outer binding identity, request content and token policy independently. Existing schema-2 signatures must fail as stale without being rewritten.

- [ ] **Step 4: Wire registry and every GLM preflight/approval/invoke CLI path**

Construct `RuntimeServices` before the final registry whenever policy resolution is required. Include the binding digest/tier/revision/effective timeout in safe preflight metadata and the CLI policy snapshot. Do not add a task-side tier flag.

- [ ] **Step 5: Run GLM/CLI regression tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_glm_provider tests.test_cli tests.test_registry -v
```

Expected: all tests pass with fake transports only.

- [ ] **Step 6: Commit GLM policy enforcement**

```powershell
git add src/macr_runtime/providers/glm.py src/macr_runtime/registry.py src/macr_runtime/cli.py tests/test_glm_provider.py tests/test_cli.py tests/test_registry.py
git commit -m "fix: enforce exact GLM capability timeout and approval"
```

---

### Task 5: Version T1 evidence and reject legacy members distinctly

**Files:**
- Modify: `src/macr_runtime/t1_manifest.py`
- Modify: `src/macr_runtime/t1_dispatcher.py`
- Modify: `src/macr_runtime/scheduler.py`
- Modify: `src/macr_runtime/runtime_db.py`
- Modify: `tests/test_t1_manifest.py`
- Modify: `tests/test_t1_dispatcher.py`
- Modify: `tests/test_scheduler.py`

**Interfaces:**
- New `T1ExecutionMember.provider_tier_binding_digest` participates in `t1_execution_member_v2`.
- New manifests use `schema_version=2` and `t1_execution_manifest_v2`.
- Runtime schema 7 adds nullable `provider_tier_binding_digest` to queue rows; schema-6 rows remain null and globally countable as legacy.
- `inspect_t1_manifest()` returns content-free audit status for schema 1; `load_t1_manifest()` raises `LegacyPreTierIncompatibleError` before authority, lease, event or provider access.

- [ ] **Step 1: Write schema-2 digest and legacy RED tests**

Create one literal schema-1 fixture and prove inspection reports `legacy_pre_tier`, member count and manifest digest without task content. Prove dispatch loading raises code `legacy_pre_tier_incompatible`. For schema 2, changing only the provider tier binding digest must change every member and manifest digest.

- [ ] **Step 2: Run T1 manifest tests and observe RED**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_t1_manifest -v`

Expected: schema 2 is rejected and no binding field exists.

- [ ] **Step 3: Implement schema-2 member/manifest contracts**

Require the exact GLM binding on every member, include it in canonical member and manifest data, and retain an audit-only parser for schema 1. The production loader and dispatcher reject schema 1 with the distinct typed error.

- [ ] **Step 4: Thread the binding through queue/dispatcher authority**

T1 staging resolves one exact binding; all three members must match it. Issued `AuthorityScope` contains that digest, each `DispatchContext` repeats it, and reconciliation records preserve it. Mixed bindings fail before queue state changes.

- [ ] **Step 5: Run T1 complete-path mocks**

Run:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_t1_manifest tests.test_t1_dispatcher tests.test_scheduler -v
```

Expected: all offline complete-path and contention tests pass with no provider call.

- [ ] **Step 6: Commit T1 schema 2**

```powershell
git add src/macr_runtime/t1_manifest.py src/macr_runtime/t1_dispatcher.py src/macr_runtime/scheduler.py src/macr_runtime/runtime_db.py tests/test_t1_manifest.py tests/test_t1_dispatcher.py tests/test_scheduler.py
git commit -m "feat: bind T1 manifests to provider capability policy"
```

---

### Task 6: Shared Codex and Claude Code host adapter

**Files:**
- Create: `src/macr_runtime/host_adapter.py`
- Create: `tests/test_host_adapter.py`
- Modify: `src/macr_runtime/__init__.py`
- Create: `integrations/claude-code/README.md`
- Create: `integrations/codex/README.md`

**Interfaces:**
- `HostKind`: `codex` and `claude_code`.
- `HostBindingVerifier.verify() -> VerifiedHostBinding` is injected by a host-owned embedding; caller data and generic shell environment are never trusted as host-observed.
- `HostInvocationGrant` contains a pre-issued dispatch authority and connectivity grant; the adapter cannot issue either.
- `MacrHostAdapter.preflight(...) -> HostDispatchPreparation` performs no write/key/network action.
- `MacrHostAdapter.invoke(..., grant: HostInvocationGrant) -> ProviderResult` uses the same `MacrRuntime`, authority, budget, approval, vault and accounting services as the ordinary CLI.

- [ ] **Step 1: Write host-binding RED tests**

Cover trusted injected Codex and Claude verifiers. Add attacks for an ordinary shell fabricating `CODEX_THREAD_ID`, `CLAUDE_CODE_SESSION_ID`, `SessionStart` JSON and `CLAUDE_ENV_FILE`; direct construction of trusted-looking DTO data; empty, overlong or malformed IDs; wrong host/identifier-kind pair; manually supplied ID rejection; and `claude_subscription` provider rejection. Every attack must leave authority, activation, state, key and provider evidence unchanged. Assert no display/resident/model name or transcript path enters the verified binding.

- [ ] **Step 2: Run host tests and observe RED**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_host_adapter -v`

Expected: import failure for `macr_runtime.host_adapter`.

- [ ] **Step 3: Implement binding and preparation contracts**

```python
class HostKind(str, Enum):
    CODEX = "codex"
    CLAUDE_CODE = "claude_code"

@dataclass(frozen=True)
class VerifiedHostBinding:
    host_kind: HostKind
    identifier_kind: str
    native_id: str
    binding_source: str
    verifier_digest: str
```

`VerifiedHostBinding` has no trusted default and is not accepted directly from an invocation request. `MacrHostAdapter` calls its injected verifier and binds the returned verifier digest. Preflight resolves provider, token and capability policy, validates task/approval/connectivity requirements, and returns bounded metadata without issuing authority or opening a key. Concrete host-owned enrollment remains outside this slice and `NotMeasured`.

- [ ] **Step 4: Write equal-rights and invoke RED tests**

With identical task/provider inputs and synthetic host-owned verifiers, Codex and Claude preparations must match in provider, model-token digest, capability binding, task digest, budget and approval, differing only in origin/binding/request digests. Invoke must record exact host origin and binding through dispatch, accounting and terminal event. Invocation without a pre-issued authority/connectivity grant, or with a stale/mismatched grant, fails before state/key/provider access. Assert the adapter never calls `DispatchAuthorityStore.issue()`.

- [ ] **Step 5: Implement the shared adapter without a self-authorizing CLI**

Expose only the in-process adapter API. It consumes `HostInvocationGrant`; it has no `issue`, activation or caller-supplied native-ID path. A generic Claude or Codex shell continues to use the existing ordinary MACR CLI under `cli`/`operator_asserted` origin. The adapter never reads Direct Chat history.

- [ ] **Step 6: Add operator-facing integration instructions**

Document the exact existing PowerShell commands Claude Code can run from its shell subprocess to use MACR today, with honest CLI attribution. State that `SessionStart` JSON and environment variables alone are forgeable discovery evidence, Bridge liveness is not required for ordinary CLI invocation, both host-owned embeddings remain synthetic/not measured, and live provider acceptance remains unmeasured until the operator intentionally invokes it.

- [ ] **Step 7: Run host/CLI tests and commit**

Run:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_host_adapter tests.test_cli tests.test_runtime_v05 -v
```

Expected: all tests pass with fake transports and isolated D-drive state.

```powershell
git add src/macr_runtime/host_adapter.py src/macr_runtime/__init__.py tests/test_host_adapter.py integrations/claude-code/README.md integrations/codex/README.md
git commit -m "feat: add shared Codex Claude provider adapter"
```

---

### Task 7: Operator controls, accounting status and release-candidate verification

**Files:**
- Modify: `src/macr_runtime/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/helpers/v06_gate_summary.py`
- Modify: `tests/test_v06_release_gate.py`
- Create: `docs/checkpoints/MACR-v0.7.0a0-host-adapters-glm-policy.md`
- Modify: `README.md`
- Modify: `PROVENANCE.md`

**Interfaces:**
- `macr capability-status [--provider <id>]` is read-only and content-free.
- `macr accounting-status` prints the fixed-query `AccountingStatusSnapshot` without origin native IDs, tasks, prompts, answers, keys or remote bodies.
- No CLI command can issue an activation witness and activate a tier in the same path.

- [ ] **Step 1: Write CLI RED tests**

Assert status commands perform no network/key access; fabricated shell activation arguments are unrecognized and leave the capability database absent or byte-identical; accounting output contains only the documented aggregate fields. Invalid or legacy state returns typed, content-free failures.

- [ ] **Step 2: Implement operator commands**

`capability-status` displays current binding ID/digest and limits. `accounting-status` serializes the snapshot directly. Tier activation remains an internal operation that consumes a separately pre-issued operator witness; this slice exposes no self-authorizing shell mutation.

- [ ] **Step 3: Update gate summary and human documentation**

Record capability store schema 2, accounting schema 3, T1 schema 2 and the exact built-in binding-set digest in the offline gate summary. Document that shared-state activation and any real provider invocation are still separate operator actions.

- [ ] **Step 4: Run targeted verification**

Run:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_process_capture tests.test_provider_capability tests.test_provider_capability_store tests.test_dispatch_authority tests.test_accounting tests.test_glm_provider tests.test_t1_manifest tests.test_t1_dispatcher tests.test_host_adapter tests.test_cli -v
git diff --check
```

Expected: all targeted tests pass, diff check exit 0, no network/provider generation.

- [ ] **Step 5: Run complete verification twice**

Run: `.\scripts\verify-v07-phase-c.ps1` two consecutive times.

Expected: both exit 0; test counts match; summary digests match except the candidate commit/tree fields if the checkpoint commit is created between runs; `network_activity=false`, `provider_generation=false`, `phase_d_started=false`, and `git_clean` reflects the documented pre/post state.

- [ ] **Step 6: Commit checkpoint documentation**

```powershell
git add src/macr_runtime/cli.py tests/test_cli.py tests/helpers/v06_gate_summary.py tests/test_v06_release_gate.py README.md PROVENANCE.md docs/checkpoints/MACR-v0.7.0a0-host-adapters-glm-policy.md
git commit -m "docs: checkpoint host adapters and GLM policy"
```

- [ ] **Step 7: Independent review gate**

Give the governing twin the exact base commit, final commit/tree, design, plan and fresh verification summaries. Resolve every blocking finding with another RED/GREEN cycle, then rerun the targeted and complete gates before any merge/push/release decision.
