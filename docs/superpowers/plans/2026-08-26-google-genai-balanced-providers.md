# Google GenAI Balanced Providers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Release MACR v0.3.0 with governed `gemini-3.7-flash` multimodal understanding and `gemini-3.1-flash-image` image generation, D-only artifact storage, copy-only Google credential custody, and disabled future Veo/TTS/Lyria profiles.

**Architecture:** Add two provider adapters over a shared, lazy Google SDK transport. Validate all local media before authentication, preserve generated image bytes through an atomic provider-neutral artifact store, and normalize content-free usage/cost metadata into the existing candidate-only ledger. Keep the research prototype separate from runtime code and keep all default tests offline.

**Tech Stack:** Python 3.11+, `unittest`, `google-genai>=2.17,<3`, `google-auth`, `Pillow>=12.3,<13`, PowerShell, Google Vertex AI GenerateContent API.

**Spec:** `docs/superpowers/specs/2026-08-26-google-genai-balanced-providers-design.md`

## Global Constraints

- Canonical source is `D:\Ai\work together\MACR`.
- Canonical runtime state is `D:\AI_RESIDENCE\AI_Runtime\macr-state`.
- The staged credential target is exactly `D:\KEY\GOOGLE_VERTEX.json`; copying is byte-preserving and never deletes the source.
- No persistent project, runtime, cache, log, test, credential, or artifact state may be created outside D:.
- Never commit a service-account JSON, private key, OAuth token, project ID, service-account email, billing ID, or promotion ID.
- Runtime reads the credential path and project only from `GOOGLE_APPLICATION_CREDENTIALS` and `GOOGLE_CLOUD_PROJECT`.
- `google_gemini` means exactly `gemini-3.7-flash`; `google_image` means exactly `gemini-3.1-flash-image` at 1K with at most one output image.
- `google_veo_fast`, `google_tts`, and `google_lyria` remain disabled and have no callable adapters.
- No Google Search/Maps grounding, tools, code execution, computer use, File Search, URL Context, external URL, `gs://` input, retry, or fallback is allowed.
- SDK retry attempts are exactly `1`, including the original request.
- Every result remains `candidate_success` or `candidate_failure`; no verification or acceptance transition is added.
- Live conformance is explicitly authorized after the complete offline gate passes. It has no additional campaign-wide cap or date-based shutdown.
- Ordinary task-level `max_cost_usd` behavior remains in force. Live conformance tasks use a positive task budget large enough for the authorized calls.
- `MODEL != RESIDENT`; provider and service-account identities do not bind a speaker or resident.
- Use `apply_patch` for repository source edits, stage audited paths explicitly, and make one reviewable commit per task.
- Do not initialize, modify, or delete files in `D:\Ai\work together\google-genai` except for the final authorized read of its credential source.

## File structure

New focused modules:

| File | Responsibility |
|---|---|
| `src/macr_runtime/google_credentials.py` | inspect and copy a service-account JSON without disclosing field values |
| `src/macr_runtime/google_media.py` | validate workspace-relative multimodal inputs and preserve their exact bytes |
| `src/macr_runtime/artifacts.py` | validate and atomically persist provider-neutral image artifacts |
| `src/macr_runtime/providers/google_core.py` | Google request/response dataclasses, pricing, lazy SDK client, one-attempt transport |
| `src/macr_runtime/providers/google_base.py` | shared Google health and task-policy gates |
| `src/macr_runtime/providers/google_gemini.py` | Gemini 3.7 text/multimodal adapter |
| `src/macr_runtime/providers/google_image.py` | Gemini 3.1 image-generation adapter |

The two provider adapters do not parse credentials, persist files, or import the research prototype. Shared modules expose typed interfaces so each task remains independently testable.

## Spec coverage map

| Approved spec requirement | Implemented by |
|---|---|
| service-account config with environment-only secrets | Tasks 1, 5, 6 |
| copy-only `D:\KEY\GOOGLE_VERTEX.json` custody | Tasks 2, 9 |
| bounded local image/video/audio/PDF input | Task 3 |
| exact-byte, MIME-aware, atomic image artifacts | Task 4 |
| lazy Google SDK, one transport attempt, no tools/grounding | Task 5 |
| exact Gemini 3.7 Flash multimodal candidate | Task 6 |
| exact Gemini 3.1 Flash Image candidate | Task 7 |
| disabled Veo/TTS/Lyria discovery profiles | Task 7 |
| content-free ledger, examples, docs, v0.3.0 | Task 8 |
| direct operator-authorized text/multimodal/image acceptance | Task 10 |
| candidate-only and `MODEL != RESIDENT` boundaries | Tasks 6-8, 10 |

---

### Task 1: Add service-account provider configuration primitives

**Files:**
- Modify: `src/macr_runtime/config.py:55-273`
- Modify: `tests/test_config.py:1-154`

**Interfaces:**
- Consumes: existing schema-v2 `ProviderConfig`.
- Produces: `AuthMode.SERVICE_ACCOUNT`, `credential_path_env`, `project_env`, and `location` with fail-closed environment validation.

- [ ] **Step 1: Write failing service-account configuration tests**

Add to `tests/test_config.py`:

```python
def test_service_account_provider_requires_named_environment(self) -> None:
    with self.assertRaisesRegex(ConfigurationError, "credential_path_env, project_env"):
        ProviderConfig(
            id="google",
            kind="google_vertex_gemini",
            enabled=True,
            auth_mode=AuthMode.SERVICE_ACCOUNT,
            api_usage_allowed=True,
            connection_scope=ConnectionScope.EXTERNAL_HTTPS,
            base_url="https://aiplatform.googleapis.com",
            model="gemini-3.7-flash",
            location="global",
            allowed_hosts=("aiplatform.googleapis.com", "oauth2.googleapis.com"),
        )

def test_service_account_environment_is_public_metadata_only(self) -> None:
    config = ProviderConfig(
        id="google",
        kind="google_vertex_gemini",
        enabled=True,
        auth_mode=AuthMode.SERVICE_ACCOUNT,
        api_usage_allowed=True,
        connection_scope=ConnectionScope.EXTERNAL_HTTPS,
        credential_path_env="GOOGLE_APPLICATION_CREDENTIALS",
        project_env="GOOGLE_CLOUD_PROJECT",
        base_url="https://aiplatform.googleapis.com",
        model="gemini-3.7-flash",
        location="global",
        allowed_hosts=("aiplatform.googleapis.com", "oauth2.googleapis.com"),
    )
    summary = config.public_summary(
        {
            "GOOGLE_APPLICATION_CREDENTIALS": r"D:\KEY\GOOGLE_VERTEX.json",
            "GOOGLE_CLOUD_PROJECT": "private-project",
        }
    )
    self.assertEqual(
        summary["required_environment"],
        ["GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT"],
    )
    self.assertNotIn("private-project", str(summary))
    self.assertNotIn("GOOGLE_VERTEX.json", str(summary))
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_config.ProviderConfigTests.test_service_account_provider_requires_named_environment tests.test_config.ProviderConfigTests.test_service_account_environment_is_public_metadata_only -v
```

Expected: import or attribute failure because `AuthMode.SERVICE_ACCOUNT` and the Google fields do not exist.

- [ ] **Step 3: Implement additive configuration fields**

Add the enum member and fields in `src/macr_runtime/config.py`:

```python
class AuthMode(str, Enum):
    API_KEY = "api_key"
    SERVICE_ACCOUNT = "service_account"
    SUBSCRIPTION_CLIENT = "subscription_client"
    PENDING = "pending"
    NONE = "none"


@dataclass(frozen=True)
class ProviderConfig:
    id: str
    kind: str
    enabled: bool
    auth_mode: AuthMode
    api_usage_allowed: bool
    connection_scope: ConnectionScope = ConnectionScope.DISABLED
    api_key_env: str | None = None
    credential_path_env: str | None = None
    project_env: str | None = None
    base_url: str | None = None
    base_url_env: str | None = None
    model: str | None = None
    model_env: str | None = None
    location: str | None = None
```

Parse the three fields with `_optional_string()`. Validate every named environment variable:

```python
for env_name in (
    self.api_key_env,
    self.credential_path_env,
    self.project_env,
    self.base_url_env,
    self.model_env,
):
    if env_name and not _ENV_NAME.fullmatch(env_name):
        raise ConfigurationError(
            f"provider {self.id} environment variable name is invalid: {env_name}"
        )
```

Add the exact service-account rule:

```python
if self.enabled and self.auth_mode is AuthMode.SERVICE_ACCOUNT:
    missing = [
        name
        for name, value in (
            ("credential_path_env", self.credential_path_env),
            ("project_env", self.project_env),
        )
        if not value
    ]
    if missing:
        raise ConfigurationError(
            f"provider {self.id} is enabled but lacks {', '.join(missing)}"
        )
    if self.api_key_env:
        raise ConfigurationError(
            f"provider {self.id} service-account auth may not use api_key_env"
        )
```

Return required environment names without values:

```python
def required_environment(self) -> tuple[str, ...]:
    return tuple(
        value
        for value in (
            self.api_key_env,
            self.credential_path_env,
            self.project_env,
            self.base_url_env,
            self.model_env,
        )
        if value
    )
```

Include `location` in `public_summary()`; never include resolved project or credential values.

- [ ] **Step 4: Run config regression tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_config -v
```

Expected: all configuration tests pass; canonical `providers.json` remains unchanged in this task.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/macr_runtime/config.py tests/test_config.py
git diff --cached --check
git commit -m "feat: add Google service-account provider config"
```

---

### Task 2: Add preservation-first Google credential staging

**Files:**
- Create: `src/macr_runtime/google_credentials.py`
- Create: `scripts/stage-google-credential.ps1`
- Create: `tests/test_google_credentials.py`

**Interfaces:**
- Produces: `CredentialInspection`, `CredentialStageResult`, `inspect_service_account(path)`, and `stage_service_account(source, target)`.
- Does not consume or modify Google provider code.

- [ ] **Step 1: Write failing copy, identical-target, and refusal tests**

Create `tests/test_google_credentials.py`:

```python
import json
import unittest

from macr_runtime.errors import StoragePolicyError
from macr_runtime.google_credentials import stage_service_account
from tests.support import d_drive_tempdir


def fake_service_account() -> bytes:
    document = {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "test-key-id",
        "private_key": "-----BEGIN " + "PRIVATE KEY-----\nTEST\n-----END " + "PRIVATE KEY-----\n",
        "client_email": "test@example.invalid",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    return json.dumps(document, sort_keys=True).encode("utf-8")


class GoogleCredentialTests(unittest.TestCase):
    def test_copy_is_byte_exact_and_source_remains(self) -> None:
        with d_drive_tempdir() as temp:
            source = temp / "source.json"
            target = temp / "key-area" / "GOOGLE_VERTEX.json"
            source.write_bytes(fake_service_account())
            result = stage_service_account(source, target)
            self.assertTrue(result.copied)
            self.assertTrue(result.sha256_equal)
            self.assertEqual(source.read_bytes(), target.read_bytes())

    def test_identical_target_is_idempotent_but_different_target_is_refused(self) -> None:
        with d_drive_tempdir() as temp:
            source = temp / "source.json"
            target = temp / "GOOGLE_VERTEX.json"
            source.write_bytes(fake_service_account())
            target.write_bytes(fake_service_account())
            self.assertFalse(stage_service_account(source, target).copied)
            target.write_bytes(b"different")
            with self.assertRaisesRegex(FileExistsError, "different bytes"):
                stage_service_account(source, target)

    def test_non_d_target_is_rejected_before_copy(self) -> None:
        with d_drive_tempdir() as temp:
            source = temp / "source.json"
            source.write_bytes(fake_service_account())
            with self.assertRaisesRegex(StoragePolicyError, "target must be on D"):
                stage_service_account(source, r"C:\temp\GOOGLE_VERTEX.json")
```

- [ ] **Step 2: Run the credential tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_google_credentials -v
```

Expected: import failure because `macr_runtime.google_credentials` does not exist.

- [ ] **Step 3: Implement byte-preserving inspection and copy**

Create `src/macr_runtime/google_credentials.py` with these public records:

```python
@dataclass(frozen=True)
class CredentialInspection:
    byte_length: int
    sha256: str
    shape_valid: bool


@dataclass(frozen=True)
class CredentialStageResult:
    copied: bool
    byte_length: int
    sha256_equal: bool
    shape_valid: bool
```

`inspect_service_account()` must read at most 64 KiB, parse UTF-8 JSON, require object type and these keys, and return no field values:

```python
_REQUIRED_FIELDS = frozenset(
    {"type", "project_id", "private_key_id", "private_key", "client_email", "token_uri"}
)


def inspect_service_account(path: str | Path) -> CredentialInspection:
    source = Path(path)
    if not source.is_file() or source.is_symlink():
        raise StoragePolicyError("Google credential source must be a regular file")
    raw = source.read_bytes()
    if not 1 <= len(raw) <= 64 * 1024:
        raise StoragePolicyError("Google credential file has an invalid size")
    document = json.loads(raw.decode("utf-8"))
    if not isinstance(document, dict) or not _REQUIRED_FIELDS.issubset(document):
        raise StoragePolicyError("Google credential file has an invalid service-account shape")
    if document.get("type") != "service_account":
        raise StoragePolicyError("Google credential type must be service_account")
    if document.get("token_uri") != "https://oauth2.googleapis.com/token":
        raise StoragePolicyError("Google credential token URI is not approved")
    for key in ("project_id", "private_key", "client_email"):
        if not isinstance(document.get(key), str) or not document[key].strip():
            raise StoragePolicyError("Google credential required string is invalid")
    return CredentialInspection(
        byte_length=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        shape_valid=True,
    )
```

`stage_service_account()` validates a D: target with `PureWindowsPath`, handles an identical existing target without writing, refuses different bytes, writes an exclusive sibling temp file, flushes and fsyncs, re-inspects it, renames without overwrite, and removes only its owned temp file on failure.

The module CLI prints only:

```json
{"status":"staged","copied":true,"byte_length":2391,"sha256_equal":true,"shape_valid":true}
```

It must not print either path, hash value, project ID, email, key ID, or private-key content.

Create `scripts/stage-google-credential.ps1`:

```powershell
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourcePath,
    [string]$TargetPath = 'D:\KEY\GOOGLE_VERTEX.json'
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:PYTHONPATH = Join-Path $repoRoot 'src'
python -m macr_runtime.google_credentials --source $SourcePath --target $TargetPath
exit $LASTEXITCODE
```

- [ ] **Step 4: Run credential tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_google_credentials -v
```

Expected: all tests pass using only guarded D: temporary directories; the real credential is untouched.

- [ ] **Step 5: Commit Task 2**

```powershell
git add scripts/stage-google-credential.ps1 src/macr_runtime/google_credentials.py tests/test_google_credentials.py
git diff --cached --check
git commit -m "feat: stage Google credentials preservation-first"
```

---

### Task 3: Validate bounded local multimodal inputs

**Files:**
- Create: `src/macr_runtime/google_media.py`
- Create: `tests/test_google_media.py`
- Modify: `pyproject.toml:5-12`

**Interfaces:**
- Produces: `ValidatedMediaInput` and `validate_google_media_inputs(task, cwd)`.
- Consumes: `TaskContract.workspace.repo`, `TaskContract.inputs`, and guarded D: test directories.

- [ ] **Step 1: Write failing media validation tests**

Create `tests/test_google_media.py` with Pillow-generated fixtures inside `d_drive_tempdir()`:

```python
import hashlib
import unittest
from pathlib import Path

from PIL import Image

from macr_runtime.contracts import TaskContract, WorkspaceSpec
from macr_runtime.errors import ProviderPolicyError
from macr_runtime.google_media import validate_google_media_inputs
from tests.support import d_drive_tempdir


def file_entry(path: Path, root: Path, mime: str) -> dict[str, str]:
    data = path.read_bytes()
    return {
        "type": "file",
        "path": path.relative_to(root).as_posix(),
        "mime_type": mime,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


class GoogleMediaTests(unittest.TestCase):
    def test_png_is_read_once_and_normalized(self) -> None:
        with d_drive_tempdir() as root:
            image = root / "blue.png"
            Image.new("RGB", (32, 24), "blue").save(image)
            task = TaskContract(
                task_id="media-png-001",
                goal="inspect image",
                task_type="multimodal",
                workspace=WorkspaceSpec(repo=str(root)),
                inputs=(file_entry(image, root, "image/png"),),
            )
            values = validate_google_media_inputs(task, cwd=root)
            self.assertEqual(values[0].mime_type, "image/png")
            self.assertEqual(values[0].data, image.read_bytes())

    def test_path_escape_hash_mismatch_and_mime_mismatch_are_rejected(self) -> None:
        with d_drive_tempdir() as root:
            image = root / "blue.png"
            Image.new("RGB", (8, 8), "blue").save(image)
            bad_entries = (
                {"type": "file", "path": "../blue.png", "mime_type": "image/png", "sha256": "0" * 64},
                {**file_entry(image, root, "image/png"), "sha256": "0" * 64},
                file_entry(image, root, "application/pdf"),
            )
            for index, entry in enumerate(bad_entries):
                with self.subTest(index=index):
                    task = TaskContract(
                        task_id=f"media-bad-{index}",
                        goal="reject input",
                        task_type="multimodal",
                        workspace=WorkspaceSpec(repo=str(root)),
                        inputs=(entry,),
                    )
                    with self.assertRaises(ProviderPolicyError):
                        validate_google_media_inputs(task, cwd=root)
```

Add these concrete boundary tests to the same class:

```python
def test_rejects_absolute_path_and_unknown_input_type(self) -> None:
    with d_drive_tempdir() as root:
        image = root / "blue.png"
        Image.new("RGB", (8, 8), "blue").save(image)
        invalid = (
            {**file_entry(image, root, "image/png"), "path": str(image)},
            {"type": "url", "url": "https://example.invalid/a.png"},
        )
        for index, entry in enumerate(invalid):
            task = TaskContract(
                task_id=f"media-shape-{index}",
                goal="reject input",
                task_type="multimodal",
                workspace=WorkspaceSpec(repo=str(root)),
                inputs=(entry,),
            )
            with self.assertRaises(ProviderPolicyError):
                validate_google_media_inputs(task, cwd=root)

def test_rejects_per_file_and_aggregate_size_limits(self) -> None:
    with d_drive_tempdir() as root:
        too_big = root / "too-big.pdf"
        too_big.write_bytes(b"%PDF-" + b"x" * (20 * 1024 * 1024))
        with self.assertRaisesRegex(ProviderPolicyError, "20 MiB"):
            validate_google_media_inputs(
                TaskContract(
                    task_id="media-size-one",
                    goal="reject input",
                    task_type="multimodal",
                    workspace=WorkspaceSpec(repo=str(root)),
                    inputs=(file_entry(too_big, root, "application/pdf"),),
                ),
                cwd=root,
            )

def test_audio_mp3_is_canonicalized_and_reparse_is_rejected(self) -> None:
    with d_drive_tempdir() as root:
        audio = root / "sample.mp3"
        audio.write_bytes(b"ID3" + b"\x00" * 64)
        task = TaskContract(
            task_id="media-mp3",
            goal="inspect audio",
            task_type="multimodal",
            workspace=WorkspaceSpec(repo=str(root)),
            inputs=(file_entry(audio, root, "audio/mp3"),),
        )
        self.assertEqual(
            validate_google_media_inputs(task, cwd=root)[0].mime_type,
            "audio/mpeg",
        )
        with patch("macr_runtime.google_media._is_reparse_point", return_value=True):
            with self.assertRaisesRegex(ProviderPolicyError, "reparse"):
                validate_google_media_inputs(task, cwd=root)
```

Add the aggregate test:

```python
def test_rejects_aggregate_size_above_32_mib(self) -> None:
    with d_drive_tempdir() as root:
        first = root / "first.pdf"
        second = root / "second.pdf"
        first.write_bytes(b"%PDF-" + b"a" * (16 * 1024 * 1024))
        second.write_bytes(b"%PDF-" + b"b" * (16 * 1024 * 1024))
        task = TaskContract(
            task_id="media-size-total",
            goal="reject aggregate",
            task_type="multimodal",
            workspace=WorkspaceSpec(repo=str(root)),
            inputs=(
                file_entry(first, root, "application/pdf"),
                file_entry(second, root, "application/pdf"),
            ),
        )
        with self.assertRaisesRegex(ProviderPolicyError, "32 MiB"):
            validate_google_media_inputs(task, cwd=root)
```

- [ ] **Step 2: Run media tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_google_media -v
```

Expected: import failure because `google_media` does not exist.

- [ ] **Step 3: Implement closed MIME, path, magic, hash, and size checks**

Add dependencies in `pyproject.toml`:

```toml
dependencies = [
  "google-genai>=2.17,<3",
  "Pillow>=12.3,<13",
]
```

Create the immutable result:

```python
@dataclass(frozen=True)
class ValidatedMediaInput:
    relative_path: str
    mime_type: str
    sha256: str
    data: bytes = field(repr=False)
```

Use the exact allowlist and aliases:

```python
ALLOWED_INPUT_MIME = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/webp",
        "video/mp4",
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "application/pdf",
    }
)
MIME_ALIASES = {"audio/mp3": "audio/mpeg"}
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
```

Resolve `workspace.repo == "current"` against the injected `cwd`; otherwise require an absolute D: workspace. Resolve the candidate, require `candidate.relative_to(workspace_root)`, reject `Path.is_symlink()` and Windows `FILE_ATTRIBUTE_REPARSE_POINT`, then read once. Match magic signatures for PNG, JPEG, WebP, MP4, MP3/MPEG, WAV, and PDF. Use `PIL.Image.open(BytesIO(data)).verify()` for image inputs. Require lowercase 64-hex SHA-256 equality and enforce per-file and aggregate limits before returning.

- [ ] **Step 4: Run media tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_google_media -v
```

Expected: all media tests pass without network or credential access.

- [ ] **Step 5: Commit Task 3**

```powershell
git add pyproject.toml src/macr_runtime/google_media.py tests/test_google_media.py
git diff --cached --check
git commit -m "feat: validate bounded Google media inputs"
```

---

### Task 4: Persist validated image artifacts atomically

**Files:**
- Create: `src/macr_runtime/artifacts.py`
- Create: `tests/test_artifacts.py`
- Modify: `src/macr_runtime/storage.py:54-68`

**Interfaces:**
- Produces: `ArtifactRecord.to_dict()` and `ImageArtifactStore.save_image(task_id, model, data, declared_mime, created_at=None)`.
- Consumes: D-only `StorageLayout.state_root` and Pillow.

- [ ] **Step 1: Write failing artifact validation tests**

Create `tests/test_artifacts.py`:

```python
import io
import unittest
from datetime import datetime, timezone

from PIL import Image

from macr_runtime.artifacts import ImageArtifactStore
from macr_runtime.errors import ProviderProtocolError
from tests.support import d_drive_tempdir


def jpeg_bytes() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (64, 48), "green").save(stream, format="JPEG")
    return stream.getvalue()


class ArtifactStoreTests(unittest.TestCase):
    def test_saves_exact_bytes_and_returns_relative_metadata(self) -> None:
        with d_drive_tempdir() as state_root:
            store = ImageArtifactStore(state_root)
            data = jpeg_bytes()
            record = store.save_image(
                task_id="image-artifact-001",
                model="gemini-3.1-flash-image",
                data=data,
                declared_mime="image/jpeg",
                created_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
            )
            saved = state_root / record.relative_path
            self.assertEqual(saved.read_bytes(), data)
            self.assertEqual((record.width, record.height), (64, 48))
            self.assertNotIn(str(state_root), str(record.to_dict()))

    def test_refuses_overwrite_mime_mismatch_and_invalid_bytes(self) -> None:
        with d_drive_tempdir() as state_root:
            store = ImageArtifactStore(state_root)
            data = jpeg_bytes()
            store.save_image("same-task", "gemini-3.1-flash-image", data, "image/jpeg")
            with self.assertRaises(FileExistsError):
                store.save_image("same-task", "gemini-3.1-flash-image", data, "image/jpeg")
            with self.assertRaises(ProviderProtocolError):
                store.save_image("mime-bad", "gemini-3.1-flash-image", data, "image/png")
            with self.assertRaises(ProviderProtocolError):
                store.save_image("bytes-bad", "gemini-3.1-flash-image", b"bad", "image/jpeg")
```

- [ ] **Step 2: Run artifact tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_artifacts -v
```

Expected: import failure because `artifacts.py` does not exist.

- [ ] **Step 3: Implement image record and atomic store**

Add `StorageLayout.google_artifact_root`:

```python
@property
def google_artifact_root(self) -> Path:
    return Path(self.state_root) / "artifacts" / "google"
```

Create `ArtifactRecord` with exact fields:

```python
@dataclass(frozen=True)
class ArtifactRecord:
    relative_path: str
    mime_type: str
    width: int
    height: int
    byte_length: int
    sha256: str
    model: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
```

`ImageArtifactStore.save_image()` accepts only JPEG/PNG magic, verifies full decoding, maps Pillow `JPEG`/`PNG` to MIME and suffix, rejects declared mismatch, creates `<state>/artifacts/google/<task_id>/image-001.<suffix>`, writes an exclusive UUID temp sibling, flushes and fsyncs, verifies the temp bytes, then uses `Path.rename()` without overwrite. On failure, remove only the owned temp sibling.

- [ ] **Step 4: Run artifact and storage tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_artifacts tests.test_storage -v
```

Expected: exact bytes, metadata, no-overwrite, and D-only storage tests pass.

- [ ] **Step 5: Commit Task 4**

```powershell
git add src/macr_runtime/artifacts.py src/macr_runtime/storage.py tests/test_artifacts.py
git diff --cached --check
git commit -m "feat: persist validated image artifacts"
```

---

### Task 5: Build the shared one-attempt Google SDK transport and pricing

**Files:**
- Create: `src/macr_runtime/providers/google_core.py`
- Create: `tests/test_google_core.py`

**Interfaces:**
- Produces: `GoogleGenerationRequest`, `GoogleUsage`, `GoogleImagePayload`, `GoogleNormalizedResponse`, `GoogleTransport`, `GoogleSdkTransport`, `estimate_gemini_cost()`, and `estimate_image_cost()`.
- Consumes: `ProviderConfig`, `ValidatedMediaInput`, named environment values, and explicit service-account credentials.

- [ ] **Step 1: Write failing request, normalization, retry, and pricing tests**

Create `tests/test_google_core.py` with these complete fake boundaries:

```python
from types import SimpleNamespace


class FakeModels:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return self.response


class FakeClientFactory:
    def __init__(self, response):
        self.models = FakeModels(response)
        self.kwargs = None
        self.http_options = None
        self.generate_config = None

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        self.http_options = kwargs["http_options"]
        return SimpleNamespace(models=self.models)


def text_request() -> GoogleGenerationRequest:
    return GoogleGenerationRequest(
        model="gemini-3.7-flash",
        system_instruction="bounded",
        goal="Return exactly: GOOGLE_OK",
        media=(),
        max_output_tokens=64,
        thinking_level="medium",
        response_modalities=("TEXT",),
        image_size=None,
    )
```

Construct the transport with `client_factory=factory` and `credential_loader=lambda path: object()`. After invocation, assign `factory.generate_config = factory.models.calls[0]["config"]`. Assert:

```python
request = GoogleGenerationRequest(
    model="gemini-3.7-flash",
    system_instruction="bounded",
    goal="Return exactly: GOOGLE_OK",
    media=(),
    max_output_tokens=64,
    thinking_level="medium",
    response_modalities=("TEXT",),
    image_size=None,
)
response = transport.generate(request, timeout_s=30)
self.assertEqual(response.model, "gemini-3.7-flash")
self.assertEqual(response.text, "GOOGLE_OK")
self.assertEqual(factory.http_options.retry_options.attempts, 1)
self.assertIsNone(factory.generate_config.tools)
self.assertEqual(factory.generate_config.thinking_config.thinking_level, "MEDIUM")
```

Use `types.SimpleNamespace` factories for SDK-shaped objects and add this normalization matrix:

```python
def sdk_part(*, text=None, thought=False, inline_data=None, function_call=None):
    return SimpleNamespace(
        text=text,
        thought=thought,
        inline_data=inline_data,
        function_call=function_call,
        executable_code=None,
        code_execution_result=None,
        tool_call=None,
        tool_response=None,
    )


def sdk_response(*, model="gemini-3.7-flash", parts=None, candidates_count=1):
    candidate = SimpleNamespace(
        content=SimpleNamespace(parts=list(parts or ())),
        finish_reason="STOP",
    )
    return SimpleNamespace(
        model_version=model,
        response_id="google-response-1",
        candidates=[candidate for _ in range(candidates_count)],
        usage_metadata=SimpleNamespace(
            prompt_token_count=10,
            candidates_token_count=4,
            thoughts_token_count=2,
            cached_content_token_count=0,
            total_token_count=16,
        ),
    )


def test_rejects_candidate_shape_tools_and_wrong_modality(self) -> None:
    invalid = (
        sdk_response(parts=[sdk_part(text="one")], candidates_count=2),
        sdk_response(parts=[]),
        sdk_response(parts=[sdk_part(function_call=object())]),
        sdk_response(
            parts=[sdk_part(inline_data=SimpleNamespace(mime_type="image/jpeg", data=b"x"))]
        ),
        sdk_response(model="gemini-other", parts=[sdk_part(text="one")]),
    )
    for document in invalid:
        with self.subTest(document=document):
            factory.response = document
            with self.assertRaises(ProviderProtocolError):
                transport.generate(text_request(), timeout_s=30)
```

Add the invalid-usage assertion:

```python
def test_usage_boolean_is_rejected(self) -> None:
    document = sdk_response(parts=[sdk_part(text="candidate")])
    document.usage_metadata.prompt_token_count = True
    factory.response = document
    with self.assertRaisesRegex(ProviderProtocolError, "prompt_token_count"):
        transport.generate(text_request(), timeout_s=30)
```

Add pricing assertions:

```python
self.assertEqual(
    estimate_gemini_cost(GoogleUsage(prompt_tokens=1000, output_tokens=500, thought_tokens=100)),
    1000 * 0.75 / 1_000_000 + 600 * 3.75 / 1_000_000,
)
self.assertGreaterEqual(
    estimate_image_cost(GoogleUsage(prompt_tokens=1000), image_count=1, image_size="1K"),
    0.067,
)
```

- [ ] **Step 2: Run Google core tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_google_core -v
```

Expected: import failure because `providers.google_core` does not exist.

- [ ] **Step 3: Implement typed request/response boundaries**

Create these immutable records:

```python
@dataclass(frozen=True)
class GoogleUsage:
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    thought_tokens: int | None = None
    cached_tokens: int | None = None
    total_tokens: int | None = None

    def to_dict(self) -> dict[str, int | None]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
            "thought_tokens": self.thought_tokens,
            "cached_tokens": self.cached_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class GoogleImagePayload:
    mime_type: str
    data: bytes = field(repr=False)


@dataclass(frozen=True)
class GoogleGenerationRequest:
    model: str
    system_instruction: str
    goal: str
    media: tuple[ValidatedMediaInput, ...]
    max_output_tokens: int
    thinking_level: str | None
    response_modalities: tuple[str, ...]
    image_size: str | None


@dataclass(frozen=True)
class GoogleNormalizedResponse:
    model: str
    response_id: str | None
    text: str
    images: tuple[GoogleImagePayload, ...]
    finish_reason: str | None
    usage: GoogleUsage


class GoogleTransport(Protocol):
    def generate(
        self,
        request: GoogleGenerationRequest,
        *,
        timeout_s: float,
    ) -> GoogleNormalizedResponse:
        raise NotImplementedError
```

`GoogleSdkTransport` has this constructor so tests do not authenticate:

```python
def __init__(
    self,
    config: ProviderConfig,
    *,
    environ: Mapping[str, str] | None = None,
    client_factory: Callable[..., object] | None = None,
    credential_loader: Callable[[str], object] | None = None,
) -> None:
```

It must lazy-import `google.genai`, `google.genai.types`, and `google.oauth2.service_account` only inside invocation. The default credential loader calls `Credentials.from_service_account_file(path, scopes=["https://www.googleapis.com/auth/cloud-platform"])`. It must load the exact file from `credential_path_env`, pass credentials explicitly, and never call `google.auth.default()`.

Construct the SDK client with:

```python
http_options = types.HttpOptions(
    base_url=config.resolve_base_url(environ),
    api_version="v1",
    timeout=max(1, round(timeout_s * 1000)),
    retry_options=types.HttpRetryOptions(attempts=1),
)
client = genai.Client(
    vertexai=True,
    project=environ[config.project_env],
    location=config.location,
    credentials=credentials,
    http_options=http_options,
)
```

Build one user `types.Content` from `Part.from_text(text=request.goal)` followed by `Part.from_bytes(data=item.data, mime_type=item.mime_type)` for each validated media item. Construct optional SDK configs explicitly:

```python
thinking_config = (
    None
    if request.thinking_level is None
    else types.ThinkingConfig(
        include_thoughts=False,
        thinking_level=request.thinking_level,
    )
)
image_config = (
    None
    if request.image_size is None
    else types.ImageConfig(
        image_size=request.image_size,
        output_mime_type="image/jpeg",
    )
)
generate_config = types.GenerateContentConfig(
    system_instruction=request.system_instruction,
    max_output_tokens=request.max_output_tokens,
    tools=None,
    response_modalities=list(request.response_modalities),
    thinking_config=thinking_config,
    image_config=image_config,
)
```

Normalize exactly one candidate. Skip thought parts, concatenate normal text, extract inline image bytes and MIME, reject tool/function/code parts, and map usage metadata fields. Catch SDK exceptions and raise sanitized `ProviderUnavailableError` or `ProviderProtocolError` without exception text or response body.

Define immutable pricing constants with basis `2026-08-26`: Gemini 3.7 input `$0.75/M`, text+thought output `$3.75/M`, Gemini 3.1 Flash Image prompt input `$0.50/M`, text/thought output `$3.00/M`, and one 1K image `$0.067`. Return estimates only when required usage is present.

- [ ] **Step 4: Run Google core tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_google_core -v
```

Expected: request construction, one-attempt retry policy, normalization, sanitization, and pricing tests pass without authentication or network.

- [ ] **Step 5: Commit Task 5**

```powershell
git add src/macr_runtime/providers/google_core.py tests/test_google_core.py
git diff --cached --check
git commit -m "feat: add bounded Google SDK transport"
```

---

### Task 6: Add the Gemini 3.7 multimodal provider

**Files:**
- Create: `src/macr_runtime/providers/google_base.py`
- Create: `src/macr_runtime/providers/google_gemini.py`
- Create: `tests/test_google_gemini_provider.py`
- Modify: `tests/support.py:1-29`
- Modify: `src/macr_runtime/providers/__init__.py:1-13`
- Modify: `src/macr_runtime/registry.py:1-78`
- Modify: `config/providers.json`
- Modify: `tests/test_config.py`
- Modify: `tests/test_registry_policy.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Produces: `BaseGoogleProvider` policy/health boundary and `GoogleGeminiProvider`.
- Consumes: config Task 1, media Task 3, and transport Task 5.

- [ ] **Step 1: Write failing Gemini provider tests**

Add a reusable structurally valid fake credential writer to `tests/support.py`:

```python
def write_fake_google_credential(path: Path) -> Path:
    document = {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "test-key-id",
        "private_key": "-----BEGIN " + "PRIVATE KEY-----\nTEST\n-----END " + "PRIVATE KEY-----\n",
        "client_email": "test@example.invalid",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    return path
```

Create `tests/test_google_gemini_provider.py` with these helpers:

```python
class FakeGoogleTransport:
    def __init__(self, response: GoogleNormalizedResponse):
        self.response = response
        self.requests = []

    def generate(self, request, *, timeout_s):
        self.requests.append(request)
        return self.response


def google_gemini_config() -> ProviderConfig:
    return ProviderConfig(
        id="google_gemini",
        kind="google_vertex_gemini",
        enabled=True,
        auth_mode=AuthMode.SERVICE_ACCOUNT,
        api_usage_allowed=True,
        connection_scope=ConnectionScope.EXTERNAL_HTTPS,
        credential_path_env="GOOGLE_APPLICATION_CREDENTIALS",
        project_env="GOOGLE_CLOUD_PROJECT",
        base_url="https://aiplatform.googleapis.com",
        model="gemini-3.7-flash",
        location="global",
        endpoint_path="/v1",
        allowed_hosts=("aiplatform.googleapis.com", "oauth2.googleapis.com"),
        capabilities=("text_generation", "multimodal_understanding"),
        approved_privacy=(PrivacyLevel.PUBLIC.value, PrivacyLevel.INTERNAL_APPROVED.value),
    )


def google_test_environment(credential_path: Path) -> dict[str, str]:
    return {
        "GOOGLE_APPLICATION_CREDENTIALS": str(credential_path),
        "GOOGLE_CLOUD_PROJECT": "test-project",
    }


def success_response() -> GoogleNormalizedResponse:
    return GoogleNormalizedResponse(
        model="gemini-3.7-flash",
        response_id="google-response-1",
        text="candidate",
        images=(),
        finish_reason="STOP",
        usage=GoogleUsage(prompt_tokens=20, output_tokens=10, thought_tokens=4),
    )


def gemini_task(
    workspace_root: Path,
    *,
    constraints: TaskConstraints | None = None,
    required_capabilities: tuple[str, ...] = ("text_generation",),
    inputs: tuple[dict[str, str], ...] = (),
) -> TaskContract:
    return TaskContract(
        task_id="google-gemini-test",
        goal="return a candidate",
        task_type="provider_test",
        workspace=WorkspaceSpec(repo=str(workspace_root)),
        inputs=inputs,
        constraints=constraints or TaskConstraints(
            max_cost_usd=1.0,
            max_latency_s=30,
            max_output_tokens=64,
            internet=True,
            privacy=PrivacyLevel.PUBLIC,
        ),
        required_capabilities=required_capabilities,
    )
```

The main success test must assert:

```python
result = GoogleGeminiProvider(
    google_gemini_config(),
    transport=transport,
    environ=google_test_environment(credential_path),
).invoke(gemini_task(workspace_root))
self.assertEqual(transport.requests[0].model, "gemini-3.7-flash")
self.assertEqual(transport.requests[0].thinking_level, "medium")
self.assertEqual(transport.requests[0].response_modalities, ("TEXT",))
self.assertEqual(result.answer, "candidate")
self.assertEqual(result.provider_meta["model"], "gemini-3.7-flash")
self.assertEqual(result.cost["cost_kind"], "estimated")
```

Add a policy matrix that proves every denial happens before transport:

```python
def test_policy_denials_happen_before_transport(self) -> None:
    cases = (
        TaskConstraints(max_cost_usd=1, internet=False, privacy=PrivacyLevel.PUBLIC),
        TaskConstraints(max_cost_usd=1, internet=True, privacy=PrivacyLevel.LOCAL_ONLY),
        TaskConstraints(max_cost_usd=0, internet=True, privacy=PrivacyLevel.PUBLIC),
    )
    for index, constraints in enumerate(cases):
        transport = FakeGoogleTransport(success_response())
        provider = GoogleGeminiProvider(
            google_gemini_config(),
            transport=transport,
            environ=google_test_environment(credential_path),
        )
        task = TaskContract(
            task_id=f"google-policy-{index}",
            goal="deny",
            task_type="policy_test",
            constraints=constraints,
            required_capabilities=("text_generation",),
        )
        with self.assertRaises(ProviderPolicyError):
            provider.invoke(task)
        self.assertEqual(transport.requests, [])

def test_health_is_offline_and_does_not_call_transport(self) -> None:
    transport = FakeGoogleTransport(success_response())
    provider = GoogleGeminiProvider(
        google_gemini_config(),
        transport=transport,
        environ=google_test_environment(credential_path),
    )
    self.assertEqual(provider.health().status, "configured_offline")
    self.assertEqual(transport.requests, [])
```

Add exact pre-transport and post-transport assertions:

```python
def test_capability_media_and_credential_fail_before_transport(self) -> None:
    bad_credential = workspace_root / "bad-credential.json"
    bad_credential.write_text("{}", encoding="utf-8")
    cases = (
        gemini_task(workspace_root, required_capabilities=("filesystem_write",)),
        gemini_task(workspace_root, inputs=({
            "type": "file",
            "path": "missing.png",
            "mime_type": "image/png",
            "sha256": "0" * 64,
        },)),
    )
    for task in cases:
        transport = FakeGoogleTransport(success_response())
        with self.assertRaises((ProviderPolicyError, ProviderUnavailableError)):
            GoogleGeminiProvider(
                google_gemini_config(),
                transport=transport,
                environ=google_test_environment(bad_credential),
            ).invoke(task)
        self.assertEqual(transport.requests, [])

def test_wrong_returned_model_fails_after_one_request(self) -> None:
    transport = FakeGoogleTransport(
        replace(success_response(), model="gemini-other")
    )
    provider = GoogleGeminiProvider(
        google_gemini_config(),
        transport=transport,
        environ=google_test_environment(credential_path),
    )
    with self.assertRaisesRegex(ProviderProtocolError, "model mismatch"):
        provider.invoke(gemini_task(workspace_root))
    self.assertEqual(len(transport.requests), 1)
```

- [ ] **Step 2: Run Gemini provider tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_google_gemini_provider -v
```

Expected: import failure because the Google provider classes do not exist.

- [ ] **Step 3: Implement shared Google policy and Gemini normalization**

`BaseGoogleProvider` validates enabled/API/auth/scope, `internet=True`, approved privacy, positive task budget and latency, required capabilities, exact global location, dependency presence, named environment presence, base URL allowlist, an absolute D: credential path, and credential shape. Production uses `D:\KEY\GOOGLE_VERTEX.json`; unit tests may use guarded D: temporary credential files. `health()` performs those offline checks only and returns `configured_offline` without creating the SDK client.

`GoogleGeminiProvider.invoke()` performs policy and media validation before transport, then sends:

```python
request = GoogleGenerationRequest(
    model=self.config.resolve_model(self.environ),
    system_instruction=bounded_worker_instruction(task.goal),
    goal=task.goal,
    media=validated_media,
    max_output_tokens=task.constraints.max_output_tokens,
    thinking_level="medium",
    response_modalities=("TEXT",),
    image_size=None,
)
```

Require no returned image and exact returned model. Normalize usage, estimated cost, warning text, response ID, finish reason, and content-free metrics. Actual estimated cost above the ordinary task budget becomes `candidate_failure` after response.

Use this cost envelope:

```python
cost={
    "currency_cost_usd": estimated_cost,
    "cost_kind": "estimated" if estimated_cost is not None else "unavailable",
    "pricing_basis_version": "2026-08-26",
    "usage": response.usage.to_dict(),
}
```

Add the provider to registry kind `google_vertex_gemini`. Add only the active `google_gemini` profile to canonical `providers.json` in this task:

```json
{
  "id": "google_gemini",
  "kind": "google_vertex_gemini",
  "enabled": true,
  "auth_mode": "service_account",
  "api_usage_allowed": true,
  "connection_scope": "external_https",
  "credential_path_env": "GOOGLE_APPLICATION_CREDENTIALS",
  "project_env": "GOOGLE_CLOUD_PROJECT",
  "base_url": "https://aiplatform.googleapis.com",
  "model": "gemini-3.7-flash",
  "location": "global",
  "endpoint_path": "/v1",
  "allowed_hosts": ["aiplatform.googleapis.com", "oauth2.googleapis.com"],
  "capabilities": ["text_generation", "multimodal_understanding"],
  "approved_privacy": ["public", "internal_approved"]
}
```

Update strict-doctor tests to create a fake structurally valid credential under `d_drive_tempdir()` and set both named Google variables. Do not add a credential fixture to Git.

- [ ] **Step 4: Run Gemini, config, registry, and CLI tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_google_gemini_provider tests.test_config tests.test_registry_policy tests.test_cli -v
```

Expected: all selected tests pass without SDK client creation or network.

- [ ] **Step 5: Commit Task 6**

```powershell
git add config/providers.json src/macr_runtime/providers/__init__.py src/macr_runtime/providers/google_base.py src/macr_runtime/providers/google_gemini.py src/macr_runtime/registry.py tests/support.py tests/test_cli.py tests/test_config.py tests/test_google_gemini_provider.py tests/test_registry_policy.py
git diff --cached --check
git commit -m "feat: add Gemini 3.7 multimodal provider"
```

---

### Task 7: Add image generation and disabled future Google profiles

**Files:**
- Create: `src/macr_runtime/providers/google_image.py`
- Create: `tests/test_google_image_provider.py`
- Modify: `src/macr_runtime/providers/__init__.py`
- Modify: `src/macr_runtime/registry.py`
- Modify: `config/providers.json`
- Modify: `tests/test_config.py`
- Modify: `tests/test_registry_policy.py`

**Interfaces:**
- Produces: `GoogleImageProvider` and final ten-profile Google-inclusive registry.
- Consumes: `ImageArtifactStore`, media validation, shared Google transport, and pricing.

- [ ] **Step 1: Write failing image-provider and disabled-profile tests**

Import `FakeGoogleTransport`, `google_test_environment`, and `write_fake_google_credential` from the Task 6 test boundaries. Define image-local helpers:

```python
def google_image_config() -> ProviderConfig:
    return ProviderConfig(
        id="google_image",
        kind="google_vertex_image",
        enabled=True,
        auth_mode=AuthMode.SERVICE_ACCOUNT,
        api_usage_allowed=True,
        connection_scope=ConnectionScope.EXTERNAL_HTTPS,
        credential_path_env="GOOGLE_APPLICATION_CREDENTIALS",
        project_env="GOOGLE_CLOUD_PROJECT",
        base_url="https://aiplatform.googleapis.com",
        model="gemini-3.1-flash-image",
        location="global",
        endpoint_path="/v1",
        allowed_hosts=("aiplatform.googleapis.com", "oauth2.googleapis.com"),
        capabilities=("image_generation",),
        approved_privacy=(PrivacyLevel.PUBLIC.value, PrivacyLevel.INTERNAL_APPROVED.value),
    )


def jpeg_bytes() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (1024, 1024), "green").save(stream, format="JPEG")
    return stream.getvalue()


def image_response(
    data: bytes,
    *,
    model: str = "gemini-3.1-flash-image",
) -> GoogleNormalizedResponse:
    return GoogleNormalizedResponse(
        model=model,
        response_id="google-image-response-1",
        text="",
        images=(GoogleImagePayload("image/jpeg", data),),
        finish_reason="STOP",
        usage=GoogleUsage(prompt_tokens=20, output_tokens=1120),
    )


def image_task(
    workspace_root: Path,
    *,
    reference_count: int,
    max_cost_usd: float,
) -> TaskContract:
    entries = []
    for index in range(reference_count):
        path = workspace_root / f"reference-{index}.png"
        Image.new("RGB", (16, 16), "blue").save(path, format="PNG")
        data = path.read_bytes()
        entries.append({
            "type": "file",
            "path": path.name,
            "mime_type": "image/png",
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    return TaskContract(
        task_id="google-image-test",
        goal="generate one green square",
        task_type="image_generation",
        workspace=WorkspaceSpec(repo=str(workspace_root)),
        inputs=tuple(entries),
        constraints=TaskConstraints(
            max_cost_usd=max_cost_usd,
            max_latency_s=60,
            max_output_tokens=64,
            internet=True,
            privacy=PrivacyLevel.PUBLIC,
        ),
        required_capabilities=("image_generation",),
    )


def image_provider(response, state_root, credential_path):
    return GoogleImageProvider(
        google_image_config(),
        artifact_store=ImageArtifactStore(state_root),
        transport=FakeGoogleTransport(response),
        environ=google_test_environment(credential_path),
    )
```

Add concrete denial and response-shape tests:

```python
def test_two_references_and_low_budget_fail_before_transport(self) -> None:
    for task in (
        image_task(workspace_root, reference_count=2, max_cost_usd=1.0),
        image_task(workspace_root, reference_count=0, max_cost_usd=0.05),
    ):
        transport = FakeGoogleTransport(image_response(jpeg_bytes()))
        provider = GoogleImageProvider(
            google_image_config(),
            artifact_store=ImageArtifactStore(state_root),
            transport=transport,
            environ=google_test_environment(credential_path),
        )
        with self.assertRaises(ProviderPolicyError):
            provider.invoke(task)
        self.assertEqual(transport.requests, [])

def test_requires_exactly_one_valid_image_and_exact_model(self) -> None:
    invalid = (
        GoogleNormalizedResponse("gemini-3.1-flash-image", None, "text", (), "STOP", GoogleUsage()),
        GoogleNormalizedResponse(
            "gemini-3.1-flash-image",
            None,
            "",
            (GoogleImagePayload("image/jpeg", jpeg_bytes()), GoogleImagePayload("image/jpeg", jpeg_bytes())),
            "STOP",
            GoogleUsage(),
        ),
        GoogleNormalizedResponse(
            "wrong-model",
            None,
            "",
            (GoogleImagePayload("image/jpeg", jpeg_bytes()),),
            "STOP",
            GoogleUsage(),
        ),
    )
    for response in invalid:
        with self.subTest(response=response):
            with self.assertRaises(ProviderProtocolError):
                image_provider(response, state_root, credential_path).invoke(
                    image_task(workspace_root, reference_count=0, max_cost_usd=1.0)
                )
```

Use `b"not-an-image"` to prove the artifact store rejects invalid bytes, and invoke the same fixed task ID twice to prove no-overwrite. Assert successful cost has `cost_kind="estimated"` and `pricing_basis_version="2026-08-26"`.

Use this central success assertion:

```python
result = GoogleImageProvider(
    google_image_config(),
    artifact_store=ImageArtifactStore(state_root),
    transport=FakeGoogleTransport(image_response(jpeg_bytes())),
    environ=google_test_environment(credential_path),
).invoke(image_task(workspace_root, max_cost_usd=1.0))
self.assertEqual(result.status.value, "candidate_success")
self.assertEqual(len(result.artifacts), 1)
self.assertEqual(result.artifacts[0]["mime_type"], "image/jpeg")
self.assertEqual(result.artifacts[0]["model"], "gemini-3.1-flash-image")
self.assertNotIn(jpeg_bytes().hex(), str(result.to_dict()))
```

Add exact config assertions:

```python
by_id = {item.id: item for item in load_provider_configs(ROOT / "config" / "providers.json")}
self.assertEqual(by_id["google_veo_fast"].model, "veo-3.1-fast-generate-001")
self.assertEqual(by_id["google_tts"].model, "gemini-3.1-flash-tts-preview")
self.assertEqual(by_id["google_lyria"].model, "lyria-3-clip-preview")
for provider_id in ("google_veo_fast", "google_tts", "google_lyria"):
    self.assertFalse(by_id[provider_id].enabled)
    self.assertFalse(by_id[provider_id].api_usage_allowed)
    self.assertIsNotNone(by_id[provider_id].disabled_reason)
```

- [ ] **Step 2: Run image and config tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_google_image_provider tests.test_config -v
```

Expected: missing provider plus missing profile failures.

- [ ] **Step 3: Implement exact one-image behavior and final profiles**

The image provider performs policy/media validation and rejects more than one reference before transport. Preflight estimate is `$0.067`; an ordinary task below it fails before authentication. Send:

```python
request = GoogleGenerationRequest(
    model="gemini-3.1-flash-image",
    system_instruction=bounded_worker_instruction(task.goal),
    goal=task.goal,
    media=validated_media,
    max_output_tokens=task.constraints.max_output_tokens,
    thinking_level=None,
    response_modalities=("TEXT", "IMAGE"),
    image_size="1K",
)
```

Require exact model and exactly one image. Persist it through `ImageArtifactStore` and return `ArtifactRecord.to_dict()`; optional non-thought text becomes `answer`. No image bytes enter `ProviderResult.to_dict()`.

Use the same cost-envelope keys as Gemini. `estimate_image_cost()` supplies `currency_cost_usd`; `cost_kind` is `estimated`, and `pricing_basis_version` is exactly `2026-08-26`.

Add registry kind `google_vertex_image`, the active image profile, and these exact disabled profiles:

```json
{
  "id": "google_veo_fast",
  "kind": "google_vertex_video_disabled",
  "enabled": false,
  "auth_mode": "service_account",
  "api_usage_allowed": false,
  "connection_scope": "disabled",
  "model": "veo-3.1-fast-generate-001",
  "capabilities": ["video_generation"],
  "approved_privacy": [],
  "disabled_reason": "MACR v0.3 does not implement or live-verify Veo long-running operations."
}
```

Add these two complete records after the Veo record:

```json
{
  "id": "google_tts",
  "kind": "google_vertex_audio_disabled",
  "enabled": false,
  "auth_mode": "service_account",
  "api_usage_allowed": false,
  "connection_scope": "disabled",
  "model": "gemini-3.1-flash-tts-preview",
  "capabilities": ["audio_generation"],
  "approved_privacy": [],
  "disabled_reason": "MACR v0.3 does not implement or live-verify Google TTS."
},
{
  "id": "google_lyria",
  "kind": "google_vertex_music_disabled",
  "enabled": false,
  "auth_mode": "service_account",
  "api_usage_allowed": false,
  "connection_scope": "disabled",
  "model": "lyria-3-clip-preview",
  "capabilities": ["music_generation"],
  "approved_privacy": [],
  "disabled_reason": "MACR v0.3 does not implement or live-verify Lyria music generation."
}
```

Do not add registry branches for disabled kinds; the existing disabled-first branch must create `DisabledProvider`.

- [ ] **Step 4: Run Google provider and registry tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_google_image_provider tests.test_google_gemini_provider tests.test_config tests.test_registry_policy -v
```

Expected: all selected tests pass, disabled profiles reject invocation, and no fallback occurs.

- [ ] **Step 5: Commit Task 7**

```powershell
git add config/providers.json src/macr_runtime/providers/__init__.py src/macr_runtime/providers/google_image.py src/macr_runtime/registry.py tests/test_config.py tests/test_google_image_provider.py tests/test_registry_policy.py
git diff --cached --check
git commit -m "feat: add Google image provider profiles"
```

---

### Task 8: Extend ledger, examples, docs, version, and offline gate

**Files:**
- Create: `examples/google-gemini-task.example.json`
- Create: `examples/google-image-task.example.json`
- Modify: `.env.example`
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/PROVIDER_STATUS.md`
- Modify: `docs/PROVENANCE.md`
- Modify: `pyproject.toml`
- Modify: `src/macr_runtime/__init__.py`
- Modify: `src/macr_runtime/cli.py`
- Modify: `src/macr_runtime/runtime.py`
- Modify: `scripts/verify.ps1`
- Modify: `tests/test_examples.py`
- Modify: `tests/test_runtime_ledger.py`
- Modify: `tests/test_version.py`
- Create: `tests/test_google_docs.py`

**Interfaces:**
- Produces: MACR v0.3.0 release metadata, content-free Google metrics, user-facing examples, and a complete offline release gate.

- [ ] **Step 1: Write failing version, example, ledger, and docs tests**

Update version expectations to `0.3.0`. Add exact example assertions:

```python
def test_google_gemini_example_is_public_bounded_cloud_task(self) -> None:
    task = load_example("google-gemini-task.example.json")
    self.assertEqual(task.goal, "Return exactly: MACR_GOOGLE_GEMINI_OK")
    self.assertTrue(task.constraints.internet)
    self.assertEqual(task.required_capabilities, ("text_generation",))

def test_google_image_example_requests_one_public_image(self) -> None:
    task = load_example("google-image-task.example.json")
    self.assertTrue(task.constraints.internet)
    self.assertEqual(task.constraints.privacy, PrivacyLevel.PUBLIC)
    self.assertEqual(task.constraints.max_cost_usd, 1.0)
    self.assertEqual(task.required_capabilities, ("image_generation",))
```

Add a ledger provider whose `provider_meta.metrics` contains:

```python
"input_media_count": 1,
"input_media_bytes": 1024,
"output_artifact_count": 1,
"output_artifact_bytes": 2048,
"cost_kind": "estimated",
"pricing_basis_version": "2026-08-26",
```

Assert ledger text excludes `PRIVATE GOOGLE PROMPT`, local filenames, `private_key`, and generated image byte encodings while retaining each allowlisted metric.

Create `tests/test_google_docs.py`:

```python
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GoogleDocumentationTests(unittest.TestCase):
    def test_docs_name_exact_active_and_disabled_models(self) -> None:
        text = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in ("README.md", "docs/ARCHITECTURE.md", "docs/PROVIDER_STATUS.md")
        )
        for value in (
            "gemini-3.7-flash",
            "gemini-3.1-flash-image",
            "google_veo_fast",
            "google_tts",
            "google_lyria",
            r"D:\AI_RESIDENCE\AI_Runtime\macr-state\artifacts\google",
            "MODEL != RESIDENT",
        ):
            self.assertIn(value, text)
        self.assertNotIn("credits guarantee free", text.lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run release tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = 'D:\Ai\work together\MACR\src'
python -m unittest tests.test_examples tests.test_runtime_ledger tests.test_version tests.test_google_docs -v
```

Expected: missing examples/docs/metrics and old 0.2.0 version failures.

- [ ] **Step 3: Implement release artifacts and privacy gate**

Extend `_LEDGER_METRIC_KEYS` and completion payload with the six Google metric keys, sourcing values only from `provider_meta.metrics`. Do not add artifact paths or content.

Create `examples/google-gemini-task.example.json` with exact goal `Return exactly: MACR_GOOGLE_GEMINI_OK`, `internet=true`, public privacy, positive task budget, output 256, and capability `text_generation`.

Create `examples/google-image-task.example.json` with a neutral public 1K image goal, `internet=true`, public privacy, task budget `1.0`, output 2048, and capability `image_generation`.

Add only names to `.env.example`:

```text
GOOGLE_APPLICATION_CREDENTIALS=
GOOGLE_CLOUD_PROJECT=
```

Add `gcp-key.json` and `*service-account*.json` to `.gitignore`. Extend secret scanning with PEM private-key headers and JSON `private_key` values while excluding no source directory.

Set `pyproject.toml`, `macr_runtime.__version__`, CLI version/description, README, architecture, provider status, and provenance to v0.3.0. Document the prototype as research evidence, not runtime authority. Preserve candidate-only and identity boundaries.

- [ ] **Step 4: Run the complete offline gate and verify GREEN**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

Expected: all tests pass, compileall succeeds, secret and operational-path scans are clean, `git diff --check` is clean, and doctor reports no network activity. Without Google environment variables, active Google profiles report `configuration_incomplete`; default non-strict doctor still exits 0.

- [ ] **Step 5: Commit Task 8**

```powershell
git add .env.example .gitignore README.md docs/ARCHITECTURE.md docs/PROVENANCE.md docs/PROVIDER_STATUS.md examples/google-gemini-task.example.json examples/google-image-task.example.json pyproject.toml scripts/verify.ps1 src/macr_runtime/__init__.py src/macr_runtime/cli.py src/macr_runtime/runtime.py tests/test_examples.py tests/test_google_docs.py tests/test_runtime_ledger.py tests/test_version.py
git diff --cached --check
git commit -m "docs: prepare MACR v0.3 Google release"
```

---

### Task 9: Run the full offline gate and stage the real credential copy

**Files:**
- Inspect only: `D:\Ai\work together\google-genai\gcp-key.json`
- Create outside Git: `D:\KEY\GOOGLE_VERTEX.json`
- Inspect only: Git worktree and `D:\KEY` target metadata

**Interfaces:**
- Consumes: credential staging tool from Task 2 and the operator-approved source/target.
- Produces: a verified copy with source unchanged; no repository diff.

- [ ] **Step 1: Run the exact-tree offline gate before credential access**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

Expected: exit 0. If any test or scan fails, do not read or copy the real credential.

- [ ] **Step 2: Resolve and validate exact paths before copy**

Run:

```powershell
$source = 'D:\Ai\work together\google-genai\gcp-key.json'
$target = 'D:\KEY\GOOGLE_VERTEX.json'
$sourceResolved = (Resolve-Path -LiteralPath $source).Path
$targetParent = (Resolve-Path -LiteralPath (Split-Path -Parent $target)).Path
if (-not $sourceResolved.StartsWith('D:\', [System.StringComparison]::OrdinalIgnoreCase)) { throw 'source is not on D:' }
if (-not $targetParent.StartsWith('D:\', [System.StringComparison]::OrdinalIgnoreCase)) { throw 'target is not on D:' }
```

Expected: both resolved paths remain on D:. Do not print file content.

- [ ] **Step 3: Stage the credential and verify bounded output**

Run:

```powershell
.\scripts\stage-google-credential.ps1 -SourcePath $sourceResolved -TargetPath $target
```

Expected: JSON reports `sha256_equal=true`, `shape_valid=true`, and either `copied=true` or an idempotent identical-target result. Output contains no project ID, email, key ID, private key, paths, or digest.

- [ ] **Step 4: Independently recheck equality and source preservation**

Run:

```powershell
$before = Get-FileHash -Algorithm SHA256 -LiteralPath $sourceResolved
$after = Get-FileHash -Algorithm SHA256 -LiteralPath $target
[pscustomobject]@{
    same_length = ((Get-Item -LiteralPath $sourceResolved).Length -eq (Get-Item -LiteralPath $target).Length)
    same_sha256 = ($before.Hash -eq $after.Hash)
    source_exists = Test-Path -LiteralPath $sourceResolved -PathType Leaf
} | ConvertTo-Json -Compress
```

Expected: all three booleans are true. Do not emit the hash values in the final report.

- [ ] **Step 5: Verify no Git side effect**

Run:

```powershell
git status --porcelain=v1
```

Expected: clean worktree. This task creates no commit because the credential target is outside Git.

---

### Task 10: Run authorized live conformance and record bounded evidence

**Files:**
- Create: `docs/LIVE_CONFORMANCE_GOOGLE_2026-08-26.md`
- Inspect only: `D:\AI_RESIDENCE\AI_Runtime\macr-state\ledger\events.jsonl`
- Runtime-only: deterministic image and temporary task JSON under `D:\AI_RESIDENCE\AI_Runtime\macr-state\test-tmp`

**Interfaces:**
- Consumes: complete v0.3 implementation, verified credential target, active project from credential JSON, and operator-authorized direct calls.
- Produces: text, multimodal, and image conformance evidence without prompt/content/key persistence.

- [ ] **Step 1: Set process-only Google environment without printing values**

Run:

```powershell
$credential = 'D:\KEY\GOOGLE_VERTEX.json'
$serviceAccount = Get-Content -LiteralPath $credential -Raw | ConvertFrom-Json
$env:GOOGLE_APPLICATION_CREDENTIALS = $credential
$env:GOOGLE_CLOUD_PROJECT = [string]$serviceAccount.project_id
$serviceAccount = $null
```

Expected: both environment variables are present in the process; no value is printed.

- [ ] **Step 2: Invoke exact-text Gemini conformance**

Run:

```powershell
.\scripts\macr.ps1 invoke google_gemini .\examples\google-gemini-task.example.json --allow-network
```

Expected: `candidate_success`, exact returned model `gemini-3.7-flash`, exact visible answer `MACR_GOOGLE_GEMINI_OK`, no artifacts, no tools/grounding, one transport attempt, and usage/cost metadata.

- [ ] **Step 3: Create a deterministic local image and invoke multimodal understanding**

Create the deterministic fixture and complete task with this command:

```powershell
$liveRoot = 'D:\AI_RESIDENCE\AI_Runtime\macr-state\test-tmp\google-live-20260826'
if (-not $liveRoot.StartsWith('D:\AI_RESIDENCE\AI_Runtime\macr-state\test-tmp\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'unexpected live-test root'
}
New-Item -ItemType Directory -Path $liveRoot -Force | Out-Null
$env:MACR_GOOGLE_LIVE_ROOT = $liveRoot
$fixtureCode = @'
import hashlib
import json
import os
from pathlib import Path
from PIL import Image

root = Path(os.environ["MACR_GOOGLE_LIVE_ROOT"])
image_path = root / "blue-square.png"
Image.new("RGB", (64, 64), "blue").save(image_path, format="PNG")
digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
task = {
    "task_id": "google-gemini-multimodal-001",
    "goal": "Return exactly: BLUE_SQUARE",
    "task_type": "provider_conformance",
    "workspace": {"repo": str(root), "write_scope": []},
    "inputs": [{
        "type": "file",
        "path": "blue-square.png",
        "mime_type": "image/png",
        "sha256": digest,
    }],
    "constraints": {
        "max_cost_usd": 1.0,
        "max_latency_s": 180,
        "max_output_tokens": 256,
        "internet": True,
        "privacy": "public",
    },
    "required_capabilities": ["multimodal_understanding"],
    "verification": {"required": True, "methods": ["exact_text_comparison"]},
    "return_contract": {"summary": False, "patch": False, "evidence": False},
}
(root / "multimodal-task.json").write_text(
    json.dumps(task, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
'@
python -c $fixtureCode
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$multimodalTaskPath = Join-Path $liveRoot 'multimodal-task.json'
```

Run the generated task:

```powershell
.\scripts\macr.ps1 invoke google_gemini $multimodalTaskPath --allow-network
```

Expected: `candidate_success`, exact answer `BLUE_SQUARE`, one input media item, no artifact, and no path/content in the ledger. If the model does not return the exact string, record the candidate as failed acceptance and diagnose before another call.

- [ ] **Step 4: Invoke one 1K image generation**

Run:

```powershell
$imageOutput = & .\scripts\macr.ps1 invoke google_image .\examples\google-image-task.example.json --allow-network
$imageExit = $LASTEXITCODE
if ($imageExit) { $imageOutput; exit $imageExit }
$imageResult = ($imageOutput -join "`n") | ConvertFrom-Json
if ($imageResult.artifacts.Count -ne 1) { throw 'expected exactly one image artifact' }
$imageArtifactPath = Join-Path 'D:\AI_RESIDENCE\AI_Runtime\macr-state' ([string]$imageResult.artifacts[0].relative_path)
```

Expected: `candidate_success`, exact model `gemini-3.1-flash-image`, exactly one JPEG/PNG artifact at 1K, no fallback, and estimated usage/cost provenance.

- [ ] **Step 5: Independently verify artifact and ledger privacy**

Use Pillow and SHA-256 to reopen the artifact and verify MIME, dimensions, decodability, byte length, and hash:

```powershell
$env:MACR_GOOGLE_ARTIFACT_PATH = $imageArtifactPath
$artifactCheck = @'
import hashlib
import json
import os
from pathlib import Path
from PIL import Image

path = Path(os.environ["MACR_GOOGLE_ARTIFACT_PATH"])
raw = path.read_bytes()
with Image.open(path) as image:
    image.verify()
with Image.open(path) as image:
    width, height = image.size
    mime = Image.MIME[image.format]
print(json.dumps({
    "exists": path.is_file(),
    "mime": mime,
    "width": width,
    "height": height,
    "byte_length": len(raw),
    "sha256_valid": len(hashlib.sha256(raw).hexdigest()) == 64,
}, separators=(",", ":")))
'@
python -c $artifactCheck
if ($LASTEXITCODE) { exit $LASTEXITCODE }
```

Read the ledger and assert it contains none of:

```text
MACR_GOOGLE_GEMINI_OK
BLUE_SQUARE
gcp-key.json
GOOGLE_VERTEX.json
private_key
client_email
project_id
```

Also assert the ledger contains the exact Google model IDs, media/artifact counts, `cost_kind`, and pricing-basis version.

Use this privacy check without printing ledger content:

```powershell
$ledgerPath = 'D:\AI_RESIDENCE\AI_Runtime\macr-state\ledger\events.jsonl'
$ledgerText = [System.IO.File]::ReadAllText($ledgerPath)
$forbidden = @(
    'MACR_GOOGLE_GEMINI_OK',
    'BLUE_SQUARE',
    'gcp-key.json',
    'GOOGLE_VERTEX.json',
    'private_key',
    'client_email',
    'project_id'
)
foreach ($value in $forbidden) {
    if ($ledgerText.Contains($value)) { throw "ledger privacy failure category detected" }
}
foreach ($required in @('gemini-3.7-flash', 'gemini-3.1-flash-image', 'cost_kind', 'pricing_basis_version')) {
    if (-not $ledgerText.Contains($required)) { throw "required ledger metric missing" }
}
```

- [ ] **Step 6: Write bounded conformance evidence**

Create `docs/LIVE_CONFORMANCE_GOOGLE_2026-08-26.md` containing only timestamps, provider/model IDs, candidate status, exact-match booleans, media/artifact counts, token counts, cost kind/estimate, artifact MIME/dimensions/byte length/hash-verification boolean, no-retry/fallback/grounding booleans, credential-copy equality boolean, ledger privacy booleans, and candidate-only warning. Do not include prompts, answers, local source/credential paths, project ID, account identifiers, response bodies, image bytes, or credential hashes.

- [ ] **Step 7: Clear process credentials, run final gate, and commit evidence**

Run:

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = $null
$env:GOOGLE_CLOUD_PROJECT = $null
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
git diff --check
git status --short
```

Expected: full gate exits 0 and only the bounded conformance document is uncommitted.

Commit:

```powershell
git add docs/LIVE_CONFORMANCE_GOOGLE_2026-08-26.md
git diff --cached --check
git commit -m "test: record Google GenAI live conformance"
```

Then verify:

```powershell
git status --porcelain=v1
git log -10 --oneline
```

Expected: clean feature worktree, reviewable task commits, no remote/push side effect, and no credential material in Git.
