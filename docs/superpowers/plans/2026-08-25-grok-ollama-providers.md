# Grok and Ollama Provider Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Release MACR v0.2.0 with an explicit Grok 4.6 frontier profile, a manual Grok 4.3 standard profile, and a loopback-only Ollama Qwythos worker while preserving candidate-only results, external secrets, and D:-only persistent state.

**Architecture:** Extend the provider configuration with connection scope and static non-secret model/base-URL values. Keep wire formats in separate Grok, Ollama, and MiniMax adapters that share a bounded JSON HTTP transport; authorize external HTTPS and loopback HTTP with different CLI flags before reading a task file. Normalize provider metrics into `ProviderResult`, then append content-free metrics to the existing JSONL ledger.

**Tech Stack:** Python 3.11+ standard library, `dataclasses`, `urllib.request`, `unittest`, PowerShell 7/Windows PowerShell launchers, Ollama local API, xAI Responses API.

**Spec:** `docs/superpowers/specs/2026-08-25-grok-ollama-providers-design.md`

## Global Constraints

- Canonical source is `D:\Ai\work together\MACR`.
- Canonical runtime state is `D:\AI_RESIDENCE\AI_Runtime\macr-state`.
- The inactive future Codex target is `D:\AI_RESIDENCE\AI_Runtime\codex-home`; this plan does not move active Codex state.
- Ollama models remain in `D:\Ai\work together\LocalModels\models`.
- No operational persistent path may use C: or historical R:.
- `grok` means exactly `grok-4.6` with `reasoning.effort = high`.
- `grok_standard` means exactly `grok-4.3` and is never selected implicitly.
- There is no automatic Grok fallback: failure of `grok` never invokes `grok_standard`.
- Grok requests always send `store: false`, no tools, and no previous response ID.
- `ollama_qwythos` accepts only `http://127.0.0.1:11434`; Ollama Cloud is out of scope.
- Claude API billing remains forbidden and the Claude subscription route remains disabled.
- Provider/model profiles are not resident identities. Current speaker identity remains `unresolved` without a task-local HOST-OBSERVED binding.
- Default tests are offline. Live conformance is a separate final task with explicit opt-in.
- Every provider result remains `candidate_success` or `candidate_failure`; no acceptance automation is added.
- No third-party Python runtime dependency is added.
- Use `apply_patch` for repository file edits and stage audited paths explicitly.

---

### Task 1: Move persistent defaults and test state to the D: Residence

**Files:**
- Modify: `src/macr_runtime/storage.py:11-79`
- Modify: `tests/test_storage.py:1-32`
- Modify: `tests/support.py:1-27`
- Modify: `tests/test_runtime_ledger.py:10-148`
- Modify: `config/storage.json:1-17`
- Modify: `.env.example:1-12`
- Modify: `scripts/init-state.ps1:1-19`
- Modify: `scripts/macr.ps1:1-15`
- Modify: `scripts/verify.ps1:1-45`
- Modify: `AGENTS.md:1-16`

**Interfaces:**
- Consumes: the approved D: placement in the design spec.
- Produces: `StorageLayout` defaults rooted on D: and `d_drive_tempdir()` for every filesystem-writing test.

- [ ] **Step 1: Write failing D-only storage tests**

Replace the default-path test and add historical R rejection in `tests/test_storage.py`:

```python
def test_defaults_use_only_d_residence(self) -> None:
    layout = StorageLayout.from_environment({})
    self.assertEqual(layout.source_root, r"D:\Ai\work together\MACR")
    self.assertEqual(
        layout.state_root,
        r"D:\AI_RESIDENCE\AI_Runtime\macr-state",
    )
    self.assertEqual(
        layout.codex_home_target,
        r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
    )

def test_rejects_historical_r_state_root(self) -> None:
    with self.assertRaisesRegex(StoragePolicyError, "must be on D:"):
        StorageLayout(
            source_root=r"D:\Ai\work together\MACR",
            state_root=r"R:\AI_Runtime\macr-state",
            codex_home_target=r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
        )
```

Rename the test helper import and use sites in `tests/test_runtime_ledger.py` from `r_drive_tempdir` to `d_drive_tempdir`.

- [ ] **Step 2: Run the storage tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_storage tests.test_runtime_ledger -v
```

Expected: `test_defaults_use_only_d_residence` and `test_rejects_historical_r_state_root` fail because v0.1 still defaults to and permits R:.

- [ ] **Step 3: Implement D-only defaults and launchers**

Set these exact constants in `src/macr_runtime/storage.py`:

```python
DEFAULT_SOURCE_ROOT = r"D:\Ai\work together\MACR"
DEFAULT_STATE_ROOT = r"D:\AI_RESIDENCE\AI_Runtime\macr-state"
DEFAULT_CODEX_HOME_TARGET = r"D:\AI_RESIDENCE\AI_Runtime\codex-home"
ALLOWED_PERSISTENT_DRIVES = frozenset({"D:"})
```

Change the storage error to:

```python
raise StoragePolicyError(
    f"{name} must be on D:; persistent writes to {drive or 'an unknown drive'} are denied"
)
```

Replace `tests/support.py` with the D-scoped helper while preserving guarded cleanup:

```python
DEFAULT_TEST_ROOT = Path(r"D:\AI_RESIDENCE\AI_Runtime\macr-state\test-tmp")


@contextmanager
def d_drive_tempdir() -> Iterator[Path]:
    root = Path(os.environ.get("MACR_TEST_TMP", str(DEFAULT_TEST_ROOT)))
    if root.drive.upper() != "D:":
        raise RuntimeError("MACR tests may create state only on D:")
    root.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="macr-test-", dir=root))
    try:
        yield path
    finally:
        resolved = path.resolve()
        if resolved.parent.resolve() != root.resolve():
            raise RuntimeError("refusing to clean an unexpected test directory")
        shutil.rmtree(resolved)
```

Use the exact D: state and future Codex paths in all three PowerShell scripts. In `scripts/init-state.ps1`, accept only `D:\`. Update `config/storage.json` to D-only policy and update `AGENTS.md` so later tasks cannot reintroduce R:.

Set the first three `.env.example` values to:

```text
MACR_ROOT=D:\Ai\work together\MACR
MACR_STATE_ROOT=D:\AI_RESIDENCE\AI_Runtime\macr-state
CODEX_HOME_TARGET=D:\AI_RESIDENCE\AI_Runtime\codex-home
```

- [ ] **Step 4: Run the storage and ledger tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_storage tests.test_runtime_ledger -v
```

Expected: all selected tests pass and temporary test directories are removed from the canonical `test-tmp` directory.

- [ ] **Step 5: Commit Task 1**

```powershell
git add .env.example AGENTS.md config/storage.json scripts/init-state.ps1 scripts/macr.ps1 scripts/verify.ps1 src/macr_runtime/storage.py tests/support.py tests/test_storage.py tests/test_runtime_ledger.py
git diff --cached --check
git commit -m "feat: move MACR runtime state to D residence"
```

---

### Task 2: Add TaskContract output bounds and provider configuration schema v2

**Files:**
- Modify: `src/macr_runtime/contracts.py:94-132`
- Modify: `src/macr_runtime/config.py:1-200`
- Create: `src/macr_runtime/providers/common.py`
- Modify: `src/macr_runtime/providers/base.py:1-34`
- Modify: `src/macr_runtime/providers/disabled.py:1-27`
- Modify: `src/macr_runtime/providers/openai_compatible.py:84-188`
- Modify: `config/providers.json:1-47`
- Modify: `tests/test_contracts.py:1-80`
- Modify: `tests/test_config.py:1-60`
- Modify: `tests/test_minimax_provider.py:30-178`

**Interfaces:**
- Consumes: D-only storage from Task 1.
- Produces: `ConnectionScope`, schema-v2 `ProviderConfig`, `resolve_base_url()`, `resolve_model()`, `required_environment()`, and `TaskConstraints.max_output_tokens` for both new adapters.

- [ ] **Step 1: Write failing contract and schema-v2 tests**

Add to `tests/test_contracts.py`:

```python
def test_max_output_tokens_round_trip(self) -> None:
    task = TaskContract.from_dict(
        {
            "task_id": "output-bound-001",
            "goal": "bound output",
            "task_type": "testing",
            "constraints": {"max_output_tokens": 64},
        }
    )
    self.assertEqual(task.constraints.max_output_tokens, 64)
    self.assertEqual(task.to_dict()["constraints"]["max_output_tokens"], 64)

def test_rejects_invalid_output_token_bounds(self) -> None:
    for value in (True, "64", 0, 16385):
        with self.subTest(value=value):
            with self.assertRaisesRegex(ValueError, "max_output_tokens"):
                TaskConstraints(max_output_tokens=value)
```

Add to `tests/test_config.py`:

```python
def test_schema_v1_is_rejected_with_migration_message(self) -> None:
    with self.assertRaisesRegex(ConfigurationError, "schema_version 1.*migrate.*2"):
        load_provider_configs(ROOT / "tests" / "fixtures" / "providers-v1.json")

def test_static_and_environment_values_are_mutually_exclusive(self) -> None:
    with self.assertRaisesRegex(ConfigurationError, "base_url.*base_url_env"):
        ProviderConfig.from_dict(
            {
                "id": "ambiguous",
                "kind": "grok_responses",
                "enabled": True,
                "auth_mode": "api_key",
                "api_usage_allowed": True,
                "connection_scope": "external_https",
                "api_key_env": "TEST_KEY",
                "base_url": "https://api.x.ai/v1",
                "base_url_env": "TEST_BASE",
                "model": "grok-4.6",
                "allowed_hosts": ["api.x.ai"],
            }
        )

def test_external_base_url_requires_https_and_allowlisted_host(self) -> None:
    for base_url in ("http://api.x.ai/v1", "https://not-xai.invalid/v1"):
        with self.subTest(base_url=base_url):
            config = ProviderConfig.from_dict(
                {
                    "id": "external",
                    "kind": "grok_responses",
                    "enabled": True,
                    "auth_mode": "api_key",
                    "api_usage_allowed": True,
                    "connection_scope": "external_https",
                    "api_key_env": "TEST_KEY",
                    "base_url": base_url,
                    "model": "grok-4.6",
                    "allowed_hosts": ["api.x.ai"],
                }
            )
            with self.assertRaises(ConfigurationError):
                config.resolve_base_url({})

def test_loopback_scope_rejects_localhost_and_credentials(self) -> None:
    for base_url in (
        "http://localhost:11434",
        "http://user:password@127.0.0.1:11434",
    ):
        with self.subTest(base_url=base_url):
            config = ProviderConfig.from_dict(
                {
                    "id": "local",
                    "kind": "ollama_local_chat",
                    "enabled": True,
                    "auth_mode": "none",
                    "api_usage_allowed": True,
                    "connection_scope": "loopback_http",
                    "base_url": base_url,
                    "model": "local-model",
                    "allowed_hosts": ["127.0.0.1"],
                }
            )
            with self.assertRaises(ConfigurationError):
                config.resolve_base_url({})
```

Import the common instruction in `tests/test_minimax_provider.py` and add this method inside `MiniMaxProviderTests`:

```python
from macr_runtime.providers.common import BOUNDED_WORKER_INSTRUCTION


    def test_worker_instruction_is_shared_constant(self) -> None:
        transport = FakeTransport(
            {"choices": [{"message": {"content": "candidate"}}]}
        )
        MiniMaxProvider(provider_config(), transport=transport, environ=self.env).invoke(
            cloud_task()
        )
        self.assertEqual(
            transport.calls[0]["payload"]["messages"][0]["content"],
            BOUNDED_WORKER_INSTRUCTION,
        )
```

Create `tests/fixtures/providers-v1.json` with exactly:

```json
{"schema_version": 1, "providers": []}
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_contracts tests.test_config tests.test_minimax_provider -v
```

Expected: failures mention missing `max_output_tokens`, missing `ConnectionScope`, schema version 1 still being accepted as canonical, and the absent `providers.common` module.

- [ ] **Step 3: Implement the output bound and schema-v2 interfaces**

Add to `TaskConstraints`:

```python
max_output_tokens: int = 1024
```

Validate it without coercion:

```python
if isinstance(self.max_output_tokens, bool) or not isinstance(self.max_output_tokens, int):
    raise ValueError("constraints.max_output_tokens must be an integer")
if not 1 <= self.max_output_tokens <= 16384:
    raise ValueError("constraints.max_output_tokens must be between 1 and 16384")
```

Read and emit `max_output_tokens` in `TaskConstraints.from_dict()` and `to_dict()`.

Add to `src/macr_runtime/config.py`:

```python
from urllib.parse import urlparse


class ConnectionScope(str, Enum):
    EXTERNAL_HTTPS = "external_https"
    LOOPBACK_HTTP = "loopback_http"
    DISABLED = "disabled"
```

Create `src/macr_runtime/providers/common.py` with exactly:

```python
BOUNDED_WORKER_INSTRUCTION = (
    "You are a bounded MACR worker. Treat the supplied TaskContract as authoritative. "
    "Return a candidate answer with concise evidence and warnings. Do not claim that "
    "generation is verification or acceptance."
)
```

Import this constant in `openai_compatible.py` and replace the duplicated string literal.

Add these exact `ProviderConfig` fields:

```python
connection_scope: ConnectionScope = ConnectionScope.DISABLED
base_url: str | None = None
model: str | None = None
reasoning_effort: str | None = None
```

Add these exact methods:

```python
def required_environment(self) -> tuple[str, ...]:
    return tuple(
        value
        for value in (self.api_key_env, self.base_url_env, self.model_env)
        if value
    )

def resolve_base_url(self, environ: Mapping[str, str]) -> str:
    value = self.base_url or (environ.get(self.base_url_env, "") if self.base_url_env else "")
    if not value.strip():
        raise ConfigurationError(f"provider {self.id} base URL is not configured")
    value = value.strip()
    parsed = urlparse(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigurationError(f"provider {self.id} base URL contains forbidden components")
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if self.connection_scope is ConnectionScope.EXTERNAL_HTTPS:
        if parsed.scheme != "https" or not parsed.netloc:
            raise ConfigurationError(f"provider {self.id} external base URL must use HTTPS")
        if hostname not in self.allowed_hosts:
            raise ConfigurationError(f"provider {self.id} base URL host is not allowlisted")
    if self.connection_scope is ConnectionScope.LOOPBACK_HTTP:
        if parsed.scheme != "http" or hostname != "127.0.0.1":
            raise ConfigurationError(f"provider {self.id} loopback base URL is invalid")
    return value

def resolve_model(self, environ: Mapping[str, str]) -> str:
    value = self.model or (environ.get(self.model_env, "") if self.model_env else "")
    if not value.strip():
        raise ConfigurationError(f"provider {self.id} model is not configured")
    return value.strip()
```

Reject literal/environment duplicates, invalid reasoning levels, external providers without an allowlist, loopback providers with credentials, and disabled providers with a non-disabled scope. Make `load_provider_configs()` require schema version 2 and emit a specific migration error for version 1.

Implement those validations directly in `ProviderConfig.__post_init__()`:

```python
if self.base_url and self.base_url_env:
    raise ConfigurationError(
        f"provider {self.id} may not define both base_url and base_url_env"
    )
if self.model and self.model_env:
    raise ConfigurationError(
        f"provider {self.id} may not define both model and model_env"
    )
if self.reasoning_effort not in {None, "low", "medium", "high", "xhigh"}:
    raise ConfigurationError(f"provider {self.id} reasoning_effort is invalid")
if self.connection_scope is ConnectionScope.EXTERNAL_HTTPS:
    if not self.allowed_hosts:
        raise ConfigurationError(f"provider {self.id} external scope needs allowed_hosts")
    if self.auth_mode is AuthMode.API_KEY and not self.api_key_env:
        raise ConfigurationError(f"provider {self.id} API key environment is missing")
if self.connection_scope is ConnectionScope.LOOPBACK_HTTP:
    if self.auth_mode is not AuthMode.NONE:
        raise ConfigurationError(f"provider {self.id} loopback scope must use auth_mode none")
    if self.api_key_env:
        raise ConfigurationError(f"provider {self.id} loopback scope may not use an API key")
if self.connection_scope is ConnectionScope.DISABLED and self.enabled:
    raise ConfigurationError(f"provider {self.id} enabled provider cannot use disabled scope")
```

Use this schema gate in `load_provider_configs()`:

```python
schema_version = document.get("schema_version")
if schema_version == 1:
    raise ConfigurationError("providers.json schema_version 1 must migrate to 2")
if schema_version != 2:
    raise ConfigurationError("providers.json schema_version must be 2")
```

Expose `connection_scope` as a class attribute on `BaseProvider`; set it from config in `DisabledProvider` and `OpenAICompatibleProvider`. Change MiniMax resolution to use `ProviderConfig.resolve_base_url()` and `resolve_model()` while retaining environment-only MiniMax values.

Update every enabled provider's offline health success to:

```python
return ProviderHealth(
    self.provider_id,
    True,
    "configured_offline",
    "offline configuration checks passed; reachability was not tested",
)
```

Advance `config/providers.json` to schema version 2. Keep Grok disabled during this intermediate commit, set MiniMax to `external_https`, and set Claude to `disabled`.

- [ ] **Step 4: Run focused and MiniMax regression tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_contracts tests.test_config tests.test_minimax_provider tests.test_registry_policy -v
```

Expected: all selected tests pass; public summaries show environment presence booleans but no values.

- [ ] **Step 5: Commit Task 2**

```powershell
git add config/providers.json src/macr_runtime/config.py src/macr_runtime/contracts.py src/macr_runtime/providers/base.py src/macr_runtime/providers/common.py src/macr_runtime/providers/disabled.py src/macr_runtime/providers/openai_compatible.py tests/fixtures/providers-v1.json tests/test_config.py tests/test_contracts.py tests/test_minimax_provider.py
git diff --cached --check
git commit -m "feat: add provider schema v2 and output bounds"
```

---

### Task 3: Extract a shared bounded JSON HTTP transport

**Files:**
- Create: `src/macr_runtime/providers/http_json.py`
- Create: `tests/test_http_transport.py`
- Modify: `src/macr_runtime/providers/openai_compatible.py:1-83`
- Modify: `src/macr_runtime/registry.py:1-45`
- Modify: `tests/test_minimax_provider.py:1-160`
- Modify: `tests/test_runtime_ledger.py:10-20`

**Interfaces:**
- Consumes: provider schema v2 from Task 2.
- Produces: `JsonTransport.get_json()`, `JsonTransport.post_json()`, and `UrllibJsonTransport` shared by MiniMax, Grok, and Ollama.

- [ ] **Step 1: Write failing shared-transport tests**

Create `tests/test_http_transport.py` with a context-manager response and opener:

```python
import json
import unittest
from unittest.mock import patch

from macr_runtime.errors import ProviderProtocolError
from macr_runtime.providers.http_json import UrllibJsonTransport


class FakeResponse:
    def __init__(self, document):
        self.raw = json.dumps(document).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, limit):
        return self.raw[:limit]


class FakeOpener:
    def __init__(self, document):
        self.document = document
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return FakeResponse(self.document)


class HttpJsonTransportTests(unittest.TestCase):
    def test_get_json_uses_get_without_authorization_by_default(self):
        opener = FakeOpener({"models": []})
        with patch("urllib.request.build_opener", return_value=opener):
            document = UrllibJsonTransport().get_json(
                "http://127.0.0.1:11434/api/tags",
                headers={},
                timeout_s=2,
            )
        self.assertEqual(document, {"models": []})
        self.assertEqual(opener.requests[0][0].method, "GET")
        self.assertIsNone(opener.requests[0][0].data)

    def test_post_json_rejects_oversized_request_before_open(self):
        transport = UrllibJsonTransport(max_request_bytes=10)
        with self.assertRaisesRegex(ProviderProtocolError, "request exceeded"):
            transport.post_json(
                "https://example.invalid/v1/responses",
                headers={},
                payload={"input": "larger than ten bytes"},
                timeout_s=2,
            )
```

- [ ] **Step 2: Run the transport tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_http_transport -v
```

Expected: import fails because `providers.http_json` does not exist.

- [ ] **Step 3: Implement and adopt the shared transport**

Create `JsonTransport` with these signatures:

```python
class JsonTransport(Protocol):
    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_s: float,
    ) -> Mapping[str, Any]:
        raise NotImplementedError

    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_s: float,
    ) -> Mapping[str, Any]:
        raise NotImplementedError
```

Implement both through one private method:

```python
def _request_json(
    self,
    method: str,
    url: str,
    *,
    headers: Mapping[str, str],
    payload: Mapping[str, Any] | None,
    timeout_s: float,
) -> Mapping[str, Any]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if body is not None and len(body) > self.max_request_bytes:
        raise ProviderProtocolError("provider request exceeded the configured size limit")
    request_headers = dict(headers)
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=body,
        headers=request_headers,
        method=method,
    )
    return self._open_and_decode(request, timeout_s)
```

Define `_open_and_decode()` in the same class:

```python
def _open_and_decode(
    self,
    request: urllib.request.Request,
    timeout_s: float,
) -> Mapping[str, Any]:
    opener = urllib.request.build_opener(_RejectRedirectHandler())
    try:
        with opener.open(request, timeout=timeout_s) as response:
            raw = response.read(self.max_response_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise ProviderProtocolError(
            f"provider HTTP {exc.code}; remote response body omitted"
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        reason = getattr(exc, "reason", str(exc))
        raise ProviderUnavailableError(f"provider connection failed: {reason}") from exc
    if len(raw) > self.max_response_bytes:
        raise ProviderProtocolError("provider response exceeded the configured size limit")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderProtocolError("provider response was not valid UTF-8 JSON") from exc
    if not isinstance(document, dict):
        raise ProviderProtocolError("provider response root must be a JSON object")
    return document
```

Move the existing redirect rejection, response-size cap, UTF-8 JSON decoding, and sanitized HTTP/URL errors unchanged into `http_json.py`. Remove transport definitions from `openai_compatible.py` and import them from the new module. Update registry and tests to import `JsonTransport` and `UrllibJsonTransport` from `providers.http_json`.

- [ ] **Step 4: Run transport and MiniMax tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_http_transport tests.test_minimax_provider tests.test_runtime_ledger -v
```

Expected: all selected tests pass and no test opens a real socket.

- [ ] **Step 5: Commit Task 3**

```powershell
git add src/macr_runtime/providers/http_json.py src/macr_runtime/providers/openai_compatible.py src/macr_runtime/registry.py tests/test_http_transport.py tests/test_minimax_provider.py tests/test_runtime_ledger.py
git diff --cached --check
git commit -m "refactor: share bounded JSON provider transport"
```

---

### Task 4: Implement Grok 4.6 frontier and Grok 4.3 standard profiles

**Files:**
- Create: `src/macr_runtime/providers/grok.py`
- Create: `tests/test_grok_provider.py`
- Modify: `src/macr_runtime/providers/__init__.py:1-4`
- Modify: `src/macr_runtime/registry.py:1-56`
- Modify: `config/providers.json:1-55`
- Modify: `tests/test_config.py:1-90`
- Modify: `tests/test_registry_policy.py:1-45`
- Modify: `tests/test_cli.py:1-70`

**Interfaces:**
- Consumes: schema-v2 `ProviderConfig`, `TaskConstraints.max_output_tokens`, and shared `JsonTransport`.
- Produces: `GrokResponsesProvider`, enabled `grok`/`grok_standard` registry entries, actual xAI cost normalization, and strict model identity checks.

- [ ] **Step 1: Write failing Grok adapter tests**

Create a `FakeTransport` that records calls and returns a supplied document, then add these core assertions in `tests/test_grok_provider.py`:

```python
from __future__ import annotations

import unittest
from typing import Any, Mapping

from macr_runtime.config import AuthMode, ConnectionScope, ProviderConfig
from macr_runtime.contracts import (
    PrivacyLevel,
    ResultStatus,
    TaskConstraints,
    TaskContract,
)
from macr_runtime.errors import (
    ProviderPolicyError,
    ProviderProtocolError,
    ProviderUnavailableError,
)
from macr_runtime.providers.grok import GrokResponsesProvider


class FakeTransport:
    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = response
        self.posts: list[dict[str, Any]] = []

    def get_json(self, url, *, headers, timeout_s):
        raise AssertionError("Grok adapter must not issue GET requests")

    def post_json(self, url, *, headers, payload, timeout_s):
        self.posts.append(
            {
                "url": url,
                "headers": dict(headers),
                "payload": dict(payload),
                "timeout_s": timeout_s,
            }
        )
        return self.response


def grok_config(provider_id: str, model: str, reasoning_effort: str | None):
    return ProviderConfig(
        id=provider_id,
        kind="grok_responses",
        enabled=True,
        auth_mode=AuthMode.API_KEY,
        api_usage_allowed=True,
        connection_scope=ConnectionScope.EXTERNAL_HTTPS,
        api_key_env="XAI_API_KEY",
        base_url="https://api.x.ai/v1",
        model=model,
        reasoning_effort=reasoning_effort,
        endpoint_path="/responses",
        allowed_hosts=("api.x.ai",),
        capabilities=("text_generation",),
        approved_privacy=(PrivacyLevel.PUBLIC.value,),
    )


def cloud_task(max_cost_usd: float = 0.01, max_output_tokens: int = 64):
    return TaskContract(
        task_id="grok-test-001",
        goal="return a bounded candidate",
        task_type="provider_test",
        constraints=TaskConstraints(
            max_cost_usd=max_cost_usd,
            max_latency_s=30,
            max_output_tokens=max_output_tokens,
            internet=True,
            privacy=PrivacyLevel.PUBLIC,
        ),
        required_capabilities=("text_generation",),
    )


def success_document(model: str) -> dict[str, Any]:
    return {
        "id": "resp-test-1",
        "model": model,
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "candidate"}],
            }
        ],
        "usage": {
            "input_tokens": 20,
            "output_tokens": 10,
            "output_tokens_details": {"reasoning_tokens": 6},
            "cost_in_usd_ticks": 2500000,
            "num_server_side_tools_used": 0,
        },
    }


class GrokProviderTests(unittest.TestCase):
    def test_frontier_request_is_stateless_high_reasoning_and_normalized(self):
    transport = FakeTransport(
        {
            "id": "resp-frontier-1",
            "model": "grok-4.6",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "candidate"}],
                }
            ],
            "usage": {
                "input_tokens": 20,
                "output_tokens": 10,
                "output_tokens_details": {"reasoning_tokens": 6},
                "cost_in_usd_ticks": 2500000,
                "num_server_side_tools_used": 0,
            },
        }
    )
        result = GrokResponsesProvider(
            grok_config("grok", "grok-4.6", "high"),
            transport=transport,
            environ={"XAI_API_KEY": "test-key"},
        ).invoke(cloud_task(max_cost_usd=0.01, max_output_tokens=64))
        call = transport.posts[0]
        self.assertEqual(call["url"], "https://api.x.ai/v1/responses")
        self.assertEqual(call["payload"]["model"], "grok-4.6")
        self.assertFalse(call["payload"]["store"])
        self.assertEqual(call["payload"]["reasoning"], {"effort": "high"})
        self.assertEqual(call["payload"]["max_output_tokens"], 64)
        self.assertNotIn("tools", call["payload"])
        self.assertEqual(result.answer, "candidate")
        self.assertEqual(result.cost["currency_cost_usd"], 0.00025)

    def test_standard_profile_uses_4_3_without_reasoning_override(self):
        transport = FakeTransport(success_document(model="grok-4.3"))
        GrokResponsesProvider(
            grok_config("grok_standard", "grok-4.3", None),
            transport=transport,
            environ={"XAI_API_KEY": "test-key"},
        ).invoke(cloud_task())
        payload = transport.posts[0]["payload"]
        self.assertEqual(payload["model"], "grok-4.3")
        self.assertNotIn("reasoning", payload)

    def test_returned_model_mismatch_is_rejected(self):
        transport = FakeTransport(success_document(model="grok-4.3"))
        provider = GrokResponsesProvider(
            grok_config("grok", "grok-4.6", "high"),
            transport=transport,
            environ={"XAI_API_KEY": "test-key"},
        )
        with self.assertRaisesRegex(ProviderProtocolError, "model mismatch"):
            provider.invoke(cloud_task())
        self.assertEqual(len(transport.posts), 1)
```

Add these failure/policy tests to the same class:

```python
def test_missing_key_fails_before_transport(self):
    transport = FakeTransport(success_document(model="grok-4.6"))
    provider = GrokResponsesProvider(
        grok_config("grok", "grok-4.6", "high"),
        transport=transport,
        environ={},
    )
    with self.assertRaisesRegex(ProviderUnavailableError, "XAI_API_KEY"):
        provider.invoke(cloud_task())
    self.assertEqual(transport.posts, [])

def test_nonzero_server_tools_are_rejected(self):
    document = success_document(model="grok-4.6")
    document["usage"]["num_server_side_tools_used"] = 1
    provider = GrokResponsesProvider(
        grok_config("grok", "grok-4.6", "high"),
        transport=FakeTransport(document),
        environ={"XAI_API_KEY": "test-key"},
    )
    with self.assertRaisesRegex(ProviderProtocolError, "server-side tools"):
        provider.invoke(cloud_task())

def test_budget_overrun_is_a_failure_with_actual_cost(self):
    provider = GrokResponsesProvider(
        grok_config("grok", "grok-4.6", "high"),
        transport=FakeTransport(success_document(model="grok-4.6")),
        environ={"XAI_API_KEY": "test-key"},
    )
    result = provider.invoke(cloud_task(max_cost_usd=0.0001))
    self.assertEqual(result.status, ResultStatus.CANDIDATE_FAILURE)
    self.assertEqual(result.answer, "candidate")
    self.assertEqual(result.cost["currency_cost_usd"], 0.00025)
    self.assertTrue(any("exceeded" in warning for warning in result.warnings))

def test_cloud_policy_gates_fail_before_transport(self):
    cases = (
        TaskConstraints(max_cost_usd=0.01, internet=False, privacy=PrivacyLevel.PUBLIC),
        TaskConstraints(max_cost_usd=0.01, internet=True, privacy=PrivacyLevel.LOCAL_ONLY),
        TaskConstraints(max_cost_usd=0, internet=True, privacy=PrivacyLevel.PUBLIC),
    )
    for index, constraints in enumerate(cases):
        with self.subTest(index=index):
            transport = FakeTransport(success_document(model="grok-4.6"))
            provider = GrokResponsesProvider(
                grok_config("grok", "grok-4.6", "high"),
                transport=transport,
                environ={"XAI_API_KEY": "test-key"},
            )
            task = TaskContract(
                task_id=f"grok-policy-{index}",
                goal="fail before transport",
                task_type="policy_test",
                constraints=constraints,
            )
            with self.assertRaises(ProviderPolicyError):
                provider.invoke(task)
            self.assertEqual(transport.posts, [])

def test_missing_capability_fails_before_transport(self):
    transport = FakeTransport(success_document(model="grok-4.6"))
    provider = GrokResponsesProvider(
        grok_config("grok", "grok-4.6", "high"),
        transport=transport,
        environ={"XAI_API_KEY": "test-key"},
    )
    task = cloud_task()
    task = TaskContract(
        task_id=task.task_id,
        goal=task.goal,
        task_type=task.task_type,
        constraints=task.constraints,
        required_capabilities=("filesystem_write",),
    )
    with self.assertRaisesRegex(ProviderPolicyError, "lacks required capabilities"):
        provider.invoke(task)
    self.assertEqual(transport.posts, [])

def test_invalid_output_shape_is_rejected(self):
    provider = GrokResponsesProvider(
        grok_config("grok", "grok-4.6", "high"),
        transport=FakeTransport({"model": "grok-4.6", "usage": {}}),
        environ={"XAI_API_KEY": "test-key"},
    )
    with self.assertRaisesRegex(ProviderProtocolError, "output"):
        provider.invoke(cloud_task())
```

- [ ] **Step 2: Run Grok tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_grok_provider -v
```

Expected: import fails because `GrokResponsesProvider` does not exist.

- [ ] **Step 3: Implement `GrokResponsesProvider` and registry support**

Import the shared instruction and define the class boundary:

```python
from .common import BOUNDED_WORKER_INSTRUCTION


class GrokResponsesProvider(BaseProvider):
    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: JsonTransport | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        if config.kind != "grok_responses":
            raise ConfigurationError("GrokResponsesProvider requires kind=grok_responses")
        self.config = config
        self.provider_id = config.id
        self.connection_scope = config.connection_scope
        self.transport = transport or UrllibJsonTransport()
        self.environ = os.environ if environ is None else environ
```

Resolve the API key without exposing it:

```python
def _api_key(self) -> str:
    name = self.config.api_key_env
    value = self.environ.get(name, "").strip() if name else ""
    if not value:
        raise ProviderUnavailableError(
            f"provider {self.provider_id} is missing environment variable {name}"
        )
    return value
```

Keep `health()` offline:

```python
def health(self) -> ProviderHealth:
    try:
        self.config.resolve_base_url(self.environ)
        self.config.resolve_model(self.environ)
        self._api_key()
    except (ConfigurationError, ProviderUnavailableError) as exc:
        return ProviderHealth(
            self.provider_id,
            False,
            "configuration_incomplete",
            str(exc),
        )
    return ProviderHealth(
        self.provider_id,
        True,
        "configured_offline",
        "offline configuration checks passed; reachability was not tested",
    )
```

Apply cloud task policy before `_api_key()` or transport access:

```python
def _check_task_policy(self, task: TaskContract) -> None:
    if not task.constraints.internet:
        raise ProviderPolicyError("Grok task contract must permit internet access")
    if task.constraints.privacy.value not in self.config.approved_privacy:
        raise ProviderPolicyError(
            f"provider {self.provider_id} is not approved for privacy level "
            f"{task.constraints.privacy.value}"
        )
    if task.constraints.max_cost_usd <= 0:
        raise ProviderPolicyError("Grok dispatch requires a positive max_cost_usd")
    missing = sorted(set(task.required_capabilities) - set(self.config.capabilities))
    if missing:
        raise ProviderPolicyError(
            f"provider {self.provider_id} lacks required capabilities: {', '.join(missing)}"
        )
```

Use these exact request-building semantics:

```python
payload: dict[str, Any] = {
    "model": model,
    "input": [
        {"role": "system", "content": BOUNDED_WORKER_INSTRUCTION},
        {
            "role": "user",
            "content": json.dumps(task.to_dict(), ensure_ascii=False, sort_keys=True),
        },
    ],
    "store": False,
    "max_output_tokens": task.constraints.max_output_tokens,
}
if self.config.reasoning_effort:
    payload["reasoning"] = {"effort": self.config.reasoning_effort}
```

Provide focused helpers with these exact implementations:

```python
def _extract_output_text(document: Mapping[str, Any]) -> str:
    output = document.get("output")
    if not isinstance(output, list):
        raise ProviderProtocolError("Grok response output must be an array")
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "output_text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
    if not parts:
        raise ProviderProtocolError("Grok response contains no output_text")
    return "".join(parts)


def _normalized_usage(document: Mapping[str, Any]) -> dict[str, Any]:
    usage = document.get("usage")
    if not isinstance(usage, dict):
        raise ProviderProtocolError("Grok response usage must be an object")
    details = usage.get("output_tokens_details")
    details = details if isinstance(details, dict) else {}
    return {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": details.get("reasoning_tokens"),
        "cached_tokens": (
            usage.get("input_tokens_details", {}).get("cached_tokens")
            if isinstance(usage.get("input_tokens_details"), dict)
            else None
        ),
        "num_server_side_tools_used": usage.get("num_server_side_tools_used", 0),
        "cost_in_usd_ticks": usage.get("cost_in_usd_ticks"),
    }


def _cost_usd(cost_ticks: int) -> float:
    if isinstance(cost_ticks, bool) or not isinstance(cost_ticks, int) or cost_ticks < 0:
        raise ProviderProtocolError("Grok cost_in_usd_ticks must be a non-negative integer")
    return cost_ticks / 10_000_000_000
```

The implementation must require exact returned-model equality, reject nonzero `num_server_side_tools_used`, and set result status to `candidate_failure` when actual cost exceeds `max_cost_usd`. It must retain the answer in the returned failure candidate, record actual cost, and add a budget-overrun warning; the ledger remains content-free in Task 6.

Construct the result with one metrics dictionary shared with the ledger:

```python
usage = _normalized_usage(document)
cost_ticks = usage["cost_in_usd_ticks"]
cost_usd = _cost_usd(cost_ticks)
over_budget = cost_usd > task.constraints.max_cost_usd
metrics = {
    "input_tokens": usage["input_tokens"],
    "output_tokens": usage["output_tokens"],
    "reasoning_tokens": usage["reasoning_tokens"],
    "cached_tokens": usage["cached_tokens"],
    "duration_ms": None,
}
return ProviderResult(
    task_id=task.task_id,
    status=(ResultStatus.CANDIDATE_FAILURE if over_budget else ResultStatus.CANDIDATE_SUCCESS),
    answer=answer,
    cost={
        "usage": usage,
        "cost_in_usd_ticks": cost_ticks,
        "currency_cost_usd": cost_usd,
    },
    warnings=(
        "Unverified Grok output; acceptance is separate.",
        "store=false does not prove account-level Zero Data Retention.",
        *(("Actual provider cost exceeded max_cost_usd.",) if over_budget else ()),
    ),
    provider_meta={
        "provider": self.provider_id,
        "model": returned_model,
        "response_id": document.get("id"),
        "wire_format": "xai_responses",
        "metrics": metrics,
    },
)
```

Register `kind == "grok_responses"` in `ProviderRegistry.from_configs()`. Export `GrokResponsesProvider` from `providers/__init__.py`.

Update `config/providers.json` with enabled profiles:

```json
{
  "id": "grok",
  "kind": "grok_responses",
  "enabled": true,
  "auth_mode": "api_key",
  "api_usage_allowed": true,
  "connection_scope": "external_https",
  "api_key_env": "XAI_API_KEY",
  "base_url": "https://api.x.ai/v1",
  "model": "grok-4.6",
  "reasoning_effort": "high",
  "endpoint_path": "/responses",
  "allowed_hosts": ["api.x.ai"],
  "capabilities": ["text_generation"],
  "approved_privacy": ["public", "internal_approved"]
}
```

Add a second enabled profile with ID `grok_standard`, model `grok-4.3`, and no `reasoning_effort`. Add this exact config assertion:

```python
def test_grok_profiles_are_enabled_and_fixed(self) -> None:
    configs = load_provider_configs(ROOT / "config" / "providers.json")
    by_id = {item.id: item for item in configs}
    self.assertTrue(by_id["grok"].enabled)
    self.assertEqual(by_id["grok"].model, "grok-4.6")
    self.assertEqual(by_id["grok"].reasoning_effort, "high")
    self.assertTrue(by_id["grok_standard"].enabled)
    self.assertEqual(by_id["grok_standard"].model, "grok-4.3")
    self.assertIsNone(by_id["grok_standard"].reasoning_effort)
```

Update doctor test environments with `XAI_API_KEY: "test-key"`. Assert the printed report contains both profile IDs and no occurrence of `test-key`; doctor must not call either fake or live transport.

- [ ] **Step 4: Run Grok, config, registry, and doctor tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_grok_provider tests.test_config tests.test_registry_policy tests.test_cli -v
```

Expected: all selected tests pass; fake transports see no fallback call and no live network occurs.

- [ ] **Step 5: Commit Task 4**

```powershell
git add config/providers.json src/macr_runtime/providers/__init__.py src/macr_runtime/providers/grok.py src/macr_runtime/registry.py tests/test_cli.py tests/test_config.py tests/test_grok_provider.py tests/test_registry_policy.py
git diff --cached --check
git commit -m "feat: add Grok frontier and standard profiles"
```

---

### Task 5: Implement the loopback-only Ollama Qwythos adapter

**Files:**
- Create: `src/macr_runtime/providers/ollama.py`
- Create: `tests/test_ollama_provider.py`
- Modify: `src/macr_runtime/providers/__init__.py:1-8`
- Modify: `src/macr_runtime/registry.py:1-65`
- Modify: `config/providers.json`
- Modify: `.env.example:1-12`
- Modify: `tests/test_config.py`
- Modify: `tests/test_registry_policy.py`

**Interfaces:**
- Consumes: `JsonTransport.get_json()/post_json()`, schema-v2 static values, and TaskContract output bounds.
- Produces: `OllamaChatProvider`, exact model-presence preflight, bounded keep-alive parsing, and normalized local performance metrics.

- [ ] **Step 1: Write failing Ollama adapter tests**

Create `tests/test_ollama_provider.py` with a fake transport that has distinct `gets` and `posts`, then assert:

```python
from __future__ import annotations

import unittest

from macr_runtime.config import AuthMode, ConnectionScope, ProviderConfig
from macr_runtime.contracts import PrivacyLevel, TaskConstraints, TaskContract
from macr_runtime.errors import (
    ConfigurationError,
    ProviderPolicyError,
    ProviderProtocolError,
    ProviderUnavailableError,
)
from macr_runtime.providers.ollama import OllamaChatProvider, _resolve_keep_alive


class FakeTransport:
    def __init__(self, get_response, post_response):
        self.get_response = get_response
        self.post_response = post_response
        self.gets = []
        self.posts = []

    def get_json(self, url, *, headers, timeout_s):
        self.gets.append({"url": url, "headers": dict(headers), "timeout_s": timeout_s})
        return self.get_response

    def post_json(self, url, *, headers, payload, timeout_s):
        self.posts.append(
            {
                "url": url,
                "headers": dict(headers),
                "payload": dict(payload),
                "timeout_s": timeout_s,
            }
        )
        return self.post_response


def ollama_config(base_url: str = "http://127.0.0.1:11434"):
    return ProviderConfig(
        id="ollama_qwythos",
        kind="ollama_local_chat",
        enabled=True,
        auth_mode=AuthMode.NONE,
        api_usage_allowed=True,
        connection_scope=ConnectionScope.LOOPBACK_HTTP,
        base_url=base_url,
        model="hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M",
        endpoint_path="/api/chat",
        allowed_hosts=("127.0.0.1",),
        capabilities=("text_generation",),
        approved_privacy=(PrivacyLevel.LOCAL_ONLY.value,),
    )


def local_task(max_output_tokens: int = 64):
    return TaskContract(
        task_id="ollama-test-001",
        goal="return a local candidate",
        task_type="provider_test",
        constraints=TaskConstraints(
            max_cost_usd=0,
            max_latency_s=180,
            max_output_tokens=max_output_tokens,
            internet=False,
            privacy=PrivacyLevel.LOCAL_ONLY,
        ),
        required_capabilities=("text_generation",),
    )


class OllamaProviderTests(unittest.TestCase):
    def test_local_request_checks_exact_model_and_normalizes_metrics(self):
        transport = FakeTransport(
            get_response={
                "models": [
                    {"name": "hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M"}
                ]
            },
            post_response={
                "model": "hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M",
                "done": True,
                "done_reason": "stop",
                "message": {"role": "assistant", "content": "local candidate", "thinking": "omit"},
                "total_duration": 2_000_000_000,
                "load_duration": 1_000_000_000,
                "prompt_eval_count": 20,
                "eval_count": 10,
                "eval_duration": 500_000_000,
            },
        )
        result = OllamaChatProvider(
            ollama_config(),
            transport=transport,
            environ={"MACR_OLLAMA_KEEP_ALIVE": "5m"},
        ).invoke(local_task(max_output_tokens=64))
        self.assertEqual(transport.gets[0]["url"], "http://127.0.0.1:11434/api/tags")
        payload = transport.posts[0]["payload"]
        self.assertFalse(payload["stream"])
        self.assertFalse(payload["think"])
        self.assertEqual(payload["keep_alive"], "5m")
        self.assertEqual(payload["options"]["num_ctx"], 8192)
        self.assertEqual(payload["options"]["num_predict"], 64)
        self.assertEqual(result.answer, "local candidate")
        self.assertEqual(result.cost["currency_cost_usd"], 0.0)
        self.assertNotIn("omit", str(result.to_dict()))

    def test_external_or_cloud_ollama_url_is_rejected(self):
        config = ollama_config(base_url="https://ollama.com/api")
        with self.assertRaisesRegex(ConfigurationError, "127.0.0.1:11434"):
            OllamaChatProvider(config, transport=FakeTransport({}, {}), environ={})
```

Add these failure/policy tests to `OllamaProviderTests`:

```python
def test_missing_exact_model_fails_before_generation(self):
    transport = FakeTransport({"models": [{"name": "another-model"}]}, {})
    provider = OllamaChatProvider(ollama_config(), transport=transport, environ={})
    with self.assertRaisesRegex(ProviderUnavailableError, "not installed"):
        provider.invoke(local_task())
    self.assertEqual(transport.posts, [])

def test_local_policy_gates_fail_before_any_transport(self):
    cases = (
        TaskConstraints(max_cost_usd=0, internet=True, privacy=PrivacyLevel.LOCAL_ONLY),
        TaskConstraints(max_cost_usd=0, internet=False, privacy=PrivacyLevel.PUBLIC),
        TaskConstraints(max_cost_usd=0.01, internet=False, privacy=PrivacyLevel.LOCAL_ONLY),
    )
    for index, constraints in enumerate(cases):
        with self.subTest(index=index):
            transport = FakeTransport({"models": []}, {})
            provider = OllamaChatProvider(ollama_config(), transport=transport, environ={})
            task = TaskContract(
                task_id=f"ollama-policy-{index}",
                goal="fail before transport",
                task_type="policy_test",
                constraints=constraints,
            )
            with self.assertRaises(ProviderPolicyError):
                provider.invoke(task)
            self.assertEqual(transport.gets, [])
            self.assertEqual(transport.posts, [])

def test_keep_alive_allowlist(self):
    for value in ("0", "1m", "5m", "60m"):
        with self.subTest(value=value):
            self.assertEqual(_resolve_keep_alive({"MACR_OLLAMA_KEEP_ALIVE": value}), value)
    for value in ("-1", "61m", "1h", "forever"):
        with self.subTest(value=value):
            with self.assertRaisesRegex(ProviderPolicyError, "1m..60m"):
                _resolve_keep_alive({"MACR_OLLAMA_KEEP_ALIVE": value})

def test_malformed_chat_response_is_rejected(self):
    transport = FakeTransport(
        {"models": [{"name": "hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M"}]},
        {
            "model": "hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M",
            "done": True,
            "message": {"content": 42},
        },
    )
    provider = OllamaChatProvider(ollama_config(), transport=transport, environ={})
    with self.assertRaisesRegex(ProviderProtocolError, "message.content"):
        provider.invoke(local_task())

def test_returned_model_mismatch_and_tool_calls_are_rejected(self):
    base_response = {
        "model": "another-model",
        "done": True,
        "message": {"content": "candidate"},
    }
    transport = FakeTransport(
        {"models": [{"name": "hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M"}]},
        base_response,
    )
    provider = OllamaChatProvider(ollama_config(), transport=transport, environ={})
    with self.assertRaisesRegex(ProviderProtocolError, "model mismatch"):
        provider.invoke(local_task())

    base_response["model"] = "hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M"
    base_response["message"] = {
        "content": "candidate",
        "tool_calls": [{"function": {"name": "unexpected", "arguments": {}}}],
    }
    with self.assertRaisesRegex(ProviderProtocolError, "tool calls"):
        provider.invoke(local_task())
```

The required `--allow-local` behavior is tested in Task 6 because it belongs to CLI authorization rather than the adapter.

- [ ] **Step 2: Run Ollama tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_ollama_provider -v
```

Expected: import fails because `OllamaChatProvider` does not exist.

- [ ] **Step 3: Implement `OllamaChatProvider` and registry support**

Validate exact base URL in the constructor:

```python
self.config = config
self.provider_id = config.id
self.connection_scope = config.connection_scope
self.transport = transport or UrllibJsonTransport()
self.environ = os.environ if environ is None else environ
if config.resolve_base_url(self.environ) != "http://127.0.0.1:11434":
    raise ConfigurationError(
        "Ollama provider base URL must be exactly http://127.0.0.1:11434"
    )
```

Define offline health without calling `/api/tags`:

```python
def health(self) -> ProviderHealth:
    try:
        self.config.resolve_base_url(self.environ)
        self.config.resolve_model(self.environ)
        _resolve_keep_alive(self.environ)
    except (ConfigurationError, ProviderPolicyError) as exc:
        return ProviderHealth(
            self.provider_id,
            False,
            "configuration_incomplete",
            str(exc),
        )
    return ProviderHealth(
        self.provider_id,
        True,
        "configured_offline",
        "offline configuration checks passed; Ollama was not contacted",
    )
```

Use an exact keep-alive parser:

```python
def _resolve_keep_alive(environ: Mapping[str, str]) -> str:
    value = environ.get("MACR_OLLAMA_KEEP_ALIVE", "5m").strip()
    if value == "0":
        return value
    match = re.fullmatch(r"([1-9]|[1-5][0-9]|60)m", value)
    if not match:
        raise ProviderPolicyError("MACR_OLLAMA_KEEP_ALIVE must be 0 or 1m..60m")
    return value
```

Fetch `/api/tags`, require one `models[].name` to equal the configured model, then post `/api/chat` with the exact fields from the design. Discard `message.thinking`. Store nanosecond timings as integer milliseconds in `provider_meta["metrics"]` and set currency cost to zero.

Use this exact preflight and payload construction:

```python
base_url = self.config.resolve_base_url(self.environ)
model = self.config.resolve_model(self.environ)
tags = self.transport.get_json(
    f"{base_url}/api/tags",
    headers={},
    timeout_s=min(task.constraints.max_latency_s, 30.0),
)
models = tags.get("models")
if not isinstance(models, list) or model not in {
    item.get("name") for item in models if isinstance(item, dict)
}:
    raise ProviderUnavailableError(f"Ollama model is not installed: {model}")

payload = {
    "model": model,
    "messages": [
        {"role": "system", "content": BOUNDED_WORKER_INSTRUCTION},
        {
            "role": "user",
            "content": json.dumps(task.to_dict(), ensure_ascii=False, sort_keys=True),
        },
    ],
    "stream": False,
    "think": False,
    "keep_alive": _resolve_keep_alive(self.environ),
    "options": {
        "num_ctx": 8192,
        "num_predict": task.constraints.max_output_tokens,
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 20,
    },
}
```

Require `task.constraints.internet is False`, privacy exactly `local_only`, cost exactly zero, and declared capabilities before either transport call. Require `document["done"] is True`, exact returned model equality, a string `document["message"]["content"]`, and no nonempty `document["message"]["tool_calls"]`.

Normalize metrics exactly:

```python
metrics = {
    "input_tokens": document.get("prompt_eval_count"),
    "output_tokens": document.get("eval_count"),
    "reasoning_tokens": None,
    "cached_tokens": None,
    "duration_ms": round(document.get("total_duration", 0) / 1_000_000),
    "load_duration_ms": round(document.get("load_duration", 0) / 1_000_000),
    "eval_duration_ms": round(document.get("eval_duration", 0) / 1_000_000),
}
```

Return `candidate_success`, `currency_cost_usd: 0.0`, the answer string, completion reason, and the metrics dictionary. Do not copy the response `thinking` field into any result field.

Register `kind == "ollama_local_chat"` and export `OllamaChatProvider`. Add this enabled canonical profile:

```json
{
  "id": "ollama_qwythos",
  "kind": "ollama_local_chat",
  "enabled": true,
  "auth_mode": "none",
  "api_usage_allowed": true,
  "connection_scope": "loopback_http",
  "base_url": "http://127.0.0.1:11434",
  "model": "hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M",
  "endpoint_path": "/api/chat",
  "allowed_hosts": ["127.0.0.1"],
  "capabilities": ["text_generation"],
  "approved_privacy": ["local_only"]
}
```

Add `MACR_OLLAMA_KEEP_ALIVE=5m` to `.env.example`; do not add an Ollama API key or cloud URL.

- [ ] **Step 4: Run Ollama, config, and registry tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_ollama_provider tests.test_config tests.test_registry_policy -v
```

Expected: all selected tests pass without contacting the running Ollama service.

- [ ] **Step 5: Commit Task 5**

```powershell
git add .env.example config/providers.json src/macr_runtime/providers/__init__.py src/macr_runtime/providers/ollama.py src/macr_runtime/registry.py tests/test_config.py tests/test_ollama_provider.py tests/test_registry_policy.py
git diff --cached --check
git commit -m "feat: add local Qwythos Ollama provider"
```

---

### Task 6: Separate CLI authorization scopes and append content-free metrics

**Files:**
- Modify: `src/macr_runtime/cli.py:1-140`
- Modify: `src/macr_runtime/runtime.py:1-61`
- Modify: `tests/test_cli.py:1-70`
- Modify: `tests/test_runtime_ledger.py:1-180`

**Interfaces:**
- Consumes: provider `connection_scope` from Task 2 and normalized provider metrics from Tasks 4-5.
- Produces: `_invoke()` with `allow_network` and `allow_local`, `--allow-local`, pre-task-read scope gates, and bounded ledger metrics.

- [ ] **Step 1: Write failing CLI scope and ledger privacy tests**

Add to `tests/test_cli.py`:

```python
def test_local_provider_requires_local_opt_in_before_reading_task(self) -> None:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        status = _invoke(
            "ollama_qwythos",
            "this-file-must-not-be-read.json",
            str(ROOT / "config" / "providers.json"),
            allow_network=True,
            allow_local=False,
        )
    self.assertEqual(status, 3)
    self.assertIn("local_opt_in_required", output.getvalue())

def test_external_provider_rejects_local_only_opt_in_before_reading_task(self) -> None:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        status = _invoke(
            "grok",
            "this-file-must-not-be-read.json",
            str(ROOT / "config" / "providers.json"),
            allow_network=False,
            allow_local=True,
        )
    self.assertEqual(status, 3)
    self.assertIn("network_opt_in_required", output.getvalue())
```

Add a ledger assertion in `tests/test_runtime_ledger.py` using a result with answer `PRIVATE ANSWER` and metrics:

```python
from macr_runtime.config import ConnectionScope
from macr_runtime.contracts import ProviderResult, ResultStatus
from macr_runtime.providers.base import ProviderHealth


class FixedResultProvider:
    provider_id = "grok"
    connection_scope = ConnectionScope.EXTERNAL_HTTPS

    def health(self):
        return ProviderHealth("grok", True, "configured_offline")

    def invoke(self, task):
        return ProviderResult(
            task_id=task.task_id,
            status=ResultStatus.CANDIDATE_SUCCESS,
            answer="PRIVATE ANSWER",
            cost={"currency_cost_usd": 0.00025},
            provider_meta={
                "provider": "grok",
                "model": "grok-4.6",
                "response_id": "resp-private-1",
                "metrics": {
                    "input_tokens": 20,
                    "output_tokens": 10,
                    "reasoning_tokens": 6,
                    "cached_tokens": 0,
                    "duration_ms": None,
                },
            },
        )


def test_ledger_records_metrics_but_not_candidate_content(self):
    registry = ProviderRegistry((FixedResultProvider(),))
    with d_drive_tempdir() as temp:
        ledger = AppendOnlyLedger(temp / "events.jsonl")
        runtime = MacrRuntime(registry, ledger)
        runtime.invoke(
            "grok",
            TaskContract(
                task_id="ledger-private-001",
                goal="keep content out of ledger",
                task_type="testing",
            ),
        )
        events = ledger.read_all()
        serialized = ledger.path.read_text(encoding="utf-8")
    self.assertNotIn("PRIVATE ANSWER", serialized)
    self.assertNotIn("test-key", serialized)
    self.assertEqual(events[-1]["payload"]["model"], "grok-4.6")
    self.assertEqual(events[-1]["payload"]["input_tokens"], 20)
    self.assertEqual(events[-1]["payload"]["currency_cost_usd"], 0.00025)
```

- [ ] **Step 2: Run CLI and ledger tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_cli tests.test_runtime_ledger -v
```

Expected: `_invoke` rejects the new `allow_local` argument and ledger events lack metrics.

- [ ] **Step 3: Implement scope-aware invocation before task reading**

Change `_invoke` signature to:

```python
def _invoke(
    provider_id: str,
    task_path: str,
    config_path: str | None,
    allow_network: bool,
    allow_local: bool,
) -> int:
```

Load storage/config/registry without creating directories, select the provider, then gate before opening `task_path`:

```python
provider = registry.get(provider_id)
if provider.connection_scope is ConnectionScope.EXTERNAL_HTTPS and not allow_network:
    return _print_opt_in_error("network_opt_in_required", "--allow-network")
if provider.connection_scope is ConnectionScope.LOOPBACK_HTTP and not allow_local:
    return _print_opt_in_error("local_opt_in_required", "--allow-local")
```

Only after the selected scope's opt-in passes may `_invoke()` call `layout.ensure_state_tree()` and read `task_path`. Add CLI tests asserting a missing opt-in leaves a nonexistent state root nonexistent.

Define the helper before `_invoke()`:

```python
def _print_opt_in_error(status: str, flag: str) -> int:
    print(
        json.dumps(
            {
                "status": status,
                "detail": f"Re-run with {flag} only after reviewing provider policy.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 3
```

Add `--allow-local` to the invoke parser and pass both flags from `main()`. Preserve exit code 3 for missing opt-in and exit code 4 for candidate failure.

Add this exact metric allowlist in `runtime.py`:

```python
_LEDGER_METRIC_KEYS = (
    "model",
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "cached_tokens",
    "currency_cost_usd",
    "duration_ms",
)
```

Build completion payload values only from `result.provider_meta["metrics"]`, `result.provider_meta["model"]`, and `result.cost["currency_cost_usd"]`. Do not serialize `result.answer`, warnings, task inputs, authorization headers, or provider response bodies.

- [ ] **Step 4: Run CLI and ledger tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_cli tests.test_runtime_ledger -v
```

Expected: all selected tests pass, both opt-in errors happen before task file access, and ledger text excludes private content.

- [ ] **Step 5: Commit Task 6**

```powershell
git add src/macr_runtime/cli.py src/macr_runtime/runtime.py tests/test_cli.py tests/test_runtime_ledger.py
git diff --cached --check
git commit -m "feat: separate local and external provider gates"
```

---

### Task 7: Complete v0.2 configuration, examples, documentation, and offline release gate

**Files:**
- Create: `examples/grok-task.example.json`
- Create: `examples/ollama-task.example.json`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/PROVIDER_STATUS.md`
- Modify: `docs/STORAGE_AND_MIGRATION.md`
- Modify: `docs/PROVENANCE.md`
- Modify: `config/providers.json`
- Modify: `config/storage.json`
- Modify: `pyproject.toml:1-17`
- Modify: `src/macr_runtime/__init__.py:1-27`
- Modify: `src/macr_runtime/cli.py:21-130`
- Modify: `scripts/verify.ps1`
- Modify: `tests/test_config.py`
- Modify: `tests/test_storage.py`
- Create: `tests/test_version.py`
- Create: `tests/test_docs.py`

**Interfaces:**
- Consumes: all implemented provider and CLI behavior from Tasks 1-6.
- Produces: coherent v0.2.0 artifacts, offline verification, and exact live-conformance inputs.

- [ ] **Step 1: Write failing release-artifact assertions**

Add tests that assert the canonical profile order and exact models:

```python
def test_repository_config_has_v2_provider_profiles(self) -> None:
    configs = load_provider_configs(ROOT / "config" / "providers.json")
    self.assertEqual(
        [item.id for item in configs],
        ["minimax", "grok", "grok_standard", "ollama_qwythos", "claude_subscription"],
    )
    by_id = {item.id: item for item in configs}
    self.assertEqual(by_id["grok"].model, "grok-4.6")
    self.assertEqual(by_id["grok"].reasoning_effort, "high")
    self.assertEqual(by_id["grok_standard"].model, "grok-4.3")
    self.assertEqual(
        by_id["ollama_qwythos"].base_url,
        "http://127.0.0.1:11434",
    )
```

Add storage assertions for the exact D paths and package-version assertions for `0.2.0`.

Create `tests/test_version.py`:

```python
import tomllib
import unittest
from pathlib import Path

import macr_runtime


ROOT = Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def test_package_versions_are_0_2_0(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(project["project"]["version"], "0.2.0")
        self.assertEqual(macr_runtime.__version__, "0.2.0")


if __name__ == "__main__":
    unittest.main()
```

Create `tests/test_docs.py` to hold storage and identity documentation invariants:

```python
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DocumentationContractTests(unittest.TestCase):
    def test_active_docs_use_d_runtime_root(self) -> None:
        for relative in ("README.md", "docs/ARCHITECTURE.md", "docs/STORAGE_AND_MIGRATION.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(r"D:\AI_RESIDENCE\AI_Runtime\macr-state", text)
            self.assertNotIn(r"R:\AI_Runtime\macr-state", text)

    def test_architecture_preserves_speaker_identity_boundary(self) -> None:
        text = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        self.assertIn("MODEL != RESIDENT", text)
        self.assertIn("unresolved", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run config/storage tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_config tests.test_storage -v
```

Expected: version and final artifact assertions fail until all metadata/docs are updated.

- [ ] **Step 3: Update examples, versions, docs, and verification policy**

Create `examples/grok-task.example.json` with `internet: true`, `privacy: public`, `max_cost_usd: 0.01`, `max_output_tokens: 64`, and exact fixed-string goal `Return exactly: MACR_GROK_46_OK`.

Use this complete document:

```json
{
  "task_id": "grok-46-conformance-001",
  "goal": "Return exactly: MACR_GROK_46_OK",
  "task_type": "provider_conformance",
  "workspace": {"repo": "current", "write_scope": []},
  "inputs": [],
  "constraints": {
    "max_cost_usd": 0.01,
    "max_latency_s": 180,
    "max_output_tokens": 64,
    "internet": true,
    "privacy": "public"
  },
  "required_capabilities": ["text_generation"],
  "verification": {
    "required": true,
    "methods": ["exact_text_comparison", "operator_review"]
  },
  "return_contract": {"summary": true, "patch": false, "evidence": true}
}
```

Create `examples/ollama-task.example.json` with `internet: false`, `privacy: local_only`, `max_cost_usd: 0`, `max_output_tokens: 64`, and exact fixed-string goal `Return exactly: MACR_OLLAMA_OK`.

Use this complete document:

```json
{
  "task_id": "ollama-qwythos-conformance-001",
  "goal": "Return exactly: MACR_OLLAMA_OK",
  "task_type": "provider_conformance",
  "workspace": {"repo": "current", "write_scope": []},
  "inputs": [],
  "constraints": {
    "max_cost_usd": 0,
    "max_latency_s": 240,
    "max_output_tokens": 64,
    "internet": false,
    "privacy": "local_only"
  },
  "required_capabilities": ["text_generation"],
  "verification": {
    "required": true,
    "methods": ["exact_text_comparison", "operator_review"]
  },
  "return_contract": {"summary": true, "patch": false, "evidence": true}
}
```

Set both package versions to `0.2.0`:

```toml
version = "0.2.0"
```

```python
__version__ = "0.2.0"
```

Update CLI description/version output, all active storage documentation, provider tables, architecture diagrams, activation gates, commands, and limitations. Preserve historical R: references only in provenance/migration history; active instructions must use D:.

Add a `Speaker identity boundary` section to `docs/ARCHITECTURE.md` containing both exact literals `MODEL != RESIDENT` and `unresolved`. State that provider IDs are service profiles, model-emitted labels are claims, and named private residence access requires a future task-local HOST-OBSERVED binding.

Apply this exact documentation map:

| File | Required v0.2 content |
|---|---|
| `README.md` | v0.2 title, D roots, five provider profiles, separate `--allow-network`/`--allow-local` examples, candidate-only warning |
| `docs/ARCHITECTURE.md` | Grok/Ollama branches, D ledger, offline doctor semantics, no fallback, speaker identity boundary |
| `docs/PROVIDER_STATUS.md` | Grok 4.6 default, Grok 4.3 manual, Qwythos installed digest/size, Claude API forbidden |
| `docs/STORAGE_AND_MIGRATION.md` | former R became C on 2026-08-16, current D roots, same-medium backup limitation, inactive Codex target |
| `docs/PROVENANCE.md` | append design commits `2b0e589` and `6b6da53`; do not rewrite historical source hashes |

Extend `scripts/verify.ps1` with operational-path scans that fail when source/config/scripts/examples contain `C:\` or `R:\`, while excluding documentation provenance. Keep the existing credential-shaped secret scan and offline doctor.

- [ ] **Step 4: Run the complete offline gate and verify GREEN**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

Expected: every unit test passes, compileall succeeds, secret and operational-path scans are clean, `git diff --check` is clean, and doctor reports `network_activity: false` with provider statuses `configured_offline` or intentionally disabled.

- [ ] **Step 5: Commit Task 7**

```powershell
git add README.md config/providers.json config/storage.json docs/ARCHITECTURE.md docs/PROVENANCE.md docs/PROVIDER_STATUS.md docs/STORAGE_AND_MIGRATION.md examples/grok-task.example.json examples/ollama-task.example.json pyproject.toml scripts/verify.ps1 src/macr_runtime/__init__.py src/macr_runtime/cli.py tests/test_config.py tests/test_docs.py tests/test_storage.py tests/test_version.py
git diff --cached --check
git commit -m "docs: prepare MACR v0.2 provider release"
```

---

### Task 8: Run live Grok 4.6 and Ollama acceptance without persisting secrets

**Files:**
- Create: `docs/LIVE_CONFORMANCE_2026-08-26.md`
- Inspect only: `D:\AI_RESIDENCE\AI_Runtime\macr-state\ledger\events.jsonl`
- Inspect only: operator-provided Grok credential source

**Interfaces:**
- Consumes: completed v0.2 CLI, examples, installed Qwythos model, and operator-authorized xAI key.
- Produces: bounded live evidence for exact model, response status, usage/cost, local performance, ledger privacy, and final clean Git state.

- [ ] **Step 1: Re-run the full offline gate before any live cost**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

Expected: exit 0. If it fails, do not make either live provider call.

- [ ] **Step 2: Invoke Grok 4.6 with a transient process-only key**

Use a PowerShell process that reads and validates one `xai-` key without printing it:

```powershell
$raw = [System.IO.File]::ReadAllText('C:\Users\kakon\Downloads\GROK.txt')
$match = [regex]::Match($raw, 'xai-[A-Za-z0-9_-]{20,}')
if (-not $match.Success) { throw 'No xAI API key detected' }
$env:XAI_API_KEY = $match.Value
try {
    .\scripts\macr.ps1 invoke grok .\examples\grok-task.example.json --allow-network
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
} finally {
    $env:XAI_API_KEY = $null
    $raw = $null
    $match = $null
}
```

Expected: candidate status succeeds, returned model is exactly `grok-4.6`, exact visible answer is `MACR_GROK_46_OK`, tools used is zero, actual `cost_in_usd_ticks` converts to the returned USD cost, and warnings state `store: false` is not ZDR.

- [ ] **Step 3: Invoke Qwythos locally and unload after acceptance**

Run:

```powershell
$env:MACR_OLLAMA_KEEP_ALIVE = '0'
try {
    .\scripts\macr.ps1 invoke ollama_qwythos .\examples\ollama-task.example.json --allow-local
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
} finally {
    $env:MACR_OLLAMA_KEEP_ALIVE = $null
}
ollama ps
```

Expected: candidate status succeeds, exact visible answer is `MACR_OLLAMA_OK`, model name matches the installed Qwythos tag, currency cost is zero, timing/token metrics are present, and `ollama ps` has no loaded model row after unload settles.

- [ ] **Step 4: Verify ledger privacy and record bounded evidence**

Read the ledger as JSONL and assert:

```python
from pathlib import Path

ledger = Path(r"D:\AI_RESIDENCE\AI_Runtime\macr-state\ledger\events.jsonl")
text = ledger.read_text(encoding="utf-8")
assert "MACR_GROK_46_OK" not in text
assert "MACR_OLLAMA_OK" not in text
assert "xai-" not in text
assert '"model": "grok-4.6"' in text
```

Write `docs/LIVE_CONFORMANCE_2026-08-26.md` with only:

- observed timestamps;
- provider/model IDs;
- HTTP/completion status;
- exact-match booleans, not prompt or answer bodies;
- token counts and actual Grok USD cost;
- Ollama timing, context, and processor allocation observations;
- ledger content-exclusion results;
- explicit statement that provider output remains candidate-only.

- [ ] **Step 5: Run final release verification and commit evidence**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
git diff --check
git status --short
```

Expected: full gate exits 0; only the bounded conformance document is uncommitted.

Commit:

```powershell
git add docs/LIVE_CONFORMANCE_2026-08-26.md
git diff --cached --check
git commit -m "test: record Grok and Ollama live conformance"
```

Then verify:

```powershell
git status --porcelain=v1
git log -8 --oneline
```

Expected: clean worktree, no remote/push side effect, and a reviewable local commit chain for all eight tasks.
