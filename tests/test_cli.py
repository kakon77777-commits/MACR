from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from macr_runtime.cli import _doctor, _glm_approve, _glm_preflight, _invoke
from macr_runtime.contracts import (
    DelegationClass,
    ImportMode,
    PrivacyLevel,
    RequiredImport,
    TaskConstraints,
    TaskContract,
    TaskPolicyClauses,
)
from macr_runtime.config import load_provider_configs
from macr_runtime.providers.glm import GlmFlashWorkerProvider
from macr_runtime.glm_approval import GlmApprovalStore
from tests.support import d_drive_tempdir, write_fake_google_credential


ROOT = Path(__file__).resolve().parents[1]


class StaticKeySource:
    def load(self):
        return "test-id." + "test-secret"

    def check_metadata(self):
        return None


class ExplodingKeySource:
    def load(self):
        raise AssertionError("contradiction must fail before key load")

    def check_metadata(self):
        raise AssertionError("contradiction must fail before key metadata")


class DoctorTests(unittest.TestCase):
    def test_glm_approve_rejects_contradiction_before_key_access(self) -> None:
        with d_drive_tempdir() as temp:
            task = TaskContract(
                task_id="contradictory-glm-task",
                goal="Use structured policy only.",
                task_type="delegated_routine",
                delegable=True,
                delegation_class=DelegationClass.NON_SENSITIVE_ROUTINE,
                delegation_approval_sha256="0" * 64,
                constraints=TaskConstraints(
                    max_cost_usd=0.01,
                    max_latency_s=30,
                    max_output_tokens=256,
                    internet=True,
                    privacy=PrivacyLevel.PUBLIC,
                ),
                required_capabilities=("text_generation",),
                policy_clauses=TaskPolicyClauses(
                    import_mode=ImportMode.NONE,
                    required_imports=(
                        RequiredImport("required-module", "type_only"),
                    ),
                ),
            )
            task_path = temp / "task.json"
            task_path.write_text(json.dumps(task.to_dict()), encoding="utf-8")
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                status = _glm_approve(
                    str(task_path),
                    str(ROOT / "config" / "providers.json"),
                    expires_in_days=1,
                    key_source=ExplodingKeySource(),
                )

        self.assertEqual(status, 4)
        self.assertIn("TaskContradictionError", output.getvalue())
    def test_strict_ignores_intentionally_disabled_providers(self) -> None:
        with d_drive_tempdir() as temp:
            credential = write_fake_google_credential(temp / "credential.json")
            environment = {
                "MINIMAX_API_KEY": "test-key",
                "MINIMAX_BASE_URL": "https://api.minimax.io/v1",
                "MINIMAX_MODEL": "test-model",
                "XAI_API_KEY": "test-key",
                "GOOGLE_APPLICATION_CREDENTIALS": str(credential),
                "GOOGLE_CLOUD_PROJECT": "test-project",
            }
            output = io.StringIO()
            with patch.dict(os.environ, environment, clear=False):
                with contextlib.redirect_stdout(output):
                    status = _doctor(
                        str(ROOT / "config" / "providers.json"),
                        strict=True,
                        key_sources={"glm_flash_worker": StaticKeySource()},
                    )
        self.assertEqual(status, 0)
        self.assertNotIn("test-key", output.getvalue())

    def test_strict_fails_when_enabled_provider_is_not_ready(self) -> None:
        without_minimax = {
            key: value
            for key, value in os.environ.items()
            if key not in {"MINIMAX_API_KEY", "MINIMAX_BASE_URL", "MINIMAX_MODEL"}
        }
        with patch.dict(os.environ, without_minimax, clear=True):
            with contextlib.redirect_stdout(io.StringIO()):
                status = _doctor(str(ROOT / "config" / "providers.json"), strict=True)
        self.assertEqual(status, 2)

    def test_invoke_requires_explicit_network_opt_in_before_reading_task(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = _invoke(
                "minimax",
                "this-file-must-not-be-read.json",
                str(ROOT / "config" / "providers.json"),
                allow_network=False,
                allow_local=False,
            )
        self.assertEqual(status, 3)
        self.assertIn("network_opt_in_required", output.getvalue())

    def test_local_provider_requires_local_opt_in_before_reading_task(self) -> None:
        output = io.StringIO()
        state_root = ROOT / "state-must-not-be-created"
        environment = {
            "MACR_ROOT": str(ROOT),
            "MACR_STATE_ROOT": str(state_root),
            "CODEX_HOME_TARGET": r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
        }
        with patch.dict(os.environ, environment, clear=False):
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
        self.assertFalse(state_root.exists())

    def test_external_provider_rejects_local_only_opt_in_before_reading_task(self) -> None:
        output = io.StringIO()
        state_root = ROOT / "state-must-not-be-created"
        environment = {
            "MACR_ROOT": str(ROOT),
            "MACR_STATE_ROOT": str(state_root),
            "CODEX_HOME_TARGET": r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
        }
        with patch.dict(os.environ, environment, clear=False):
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
        self.assertFalse(state_root.exists())

    def test_glm_preflight_emits_digest_without_key_or_task_content(self) -> None:
        with d_drive_tempdir() as temp:
            task = TaskContract(
                task_id="glm-preflight-digest",
                goal="PUBLIC PREFLIGHT BODY",
                task_type="delegated_routine",
                delegable=True,
                delegation_class=DelegationClass.NON_SENSITIVE_ROUTINE,
                constraints=TaskConstraints(
                    max_cost_usd=0.01,
                    max_latency_s=30,
                    max_output_tokens=256,
                    internet=True,
                    privacy=PrivacyLevel.PUBLIC,
                ),
                required_capabilities=("text_generation",),
            )
            task_path = temp / "task.json"
            task_path.write_text(
                json.dumps(task.to_dict()),
                encoding="utf-8",
            )
            output = io.StringIO()
            without_key = {
                key: value for key, value in os.environ.items() if key != "ZAI_API_KEY"
            }
            with patch.dict(os.environ, without_key, clear=True):
                with contextlib.redirect_stdout(output):
                    status = _glm_preflight(
                        str(task_path),
                        str(ROOT / "config" / "providers.json"),
                        show_required_digest=True,
                    )

        document = json.loads(output.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(document["status"], "approval_required")
        self.assertEqual(len(document["required_approval_sha256"]), 64)
        self.assertNotIn("PUBLIC PREFLIGHT BODY", output.getvalue())

    def test_glm_preflight_rejects_stale_digest_without_key(self) -> None:
        with d_drive_tempdir() as temp:
            task = TaskContract(
                task_id="glm-preflight-stale",
                goal="PUBLIC STALE BODY",
                task_type="delegated_routine",
                delegable=True,
                delegation_class=DelegationClass.NON_SENSITIVE_ROUTINE,
                delegation_approval_sha256="0" * 64,
                constraints=TaskConstraints(
                    max_cost_usd=0.01,
                    max_latency_s=30,
                    max_output_tokens=256,
                    internet=True,
                    privacy=PrivacyLevel.PUBLIC,
                ),
                required_capabilities=("text_generation",),
            )
            task_path = temp / "task.json"
            task_path.write_text(
                json.dumps(task.to_dict()),
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = _glm_preflight(
                    str(task_path),
                    str(ROOT / "config" / "providers.json"),
                    show_required_digest=False,
                )

        document = json.loads(output.getvalue())
        self.assertEqual(status, 4)
        self.assertEqual(document["status"], "approval_invalid")
        self.assertNotIn("PUBLIC STALE BODY", output.getvalue())

    def test_glm_approved_preflight_output_remains_content_free(self) -> None:
        with d_drive_tempdir() as temp:
            task = TaskContract(
                task_id="glm-preflight-approved",
                goal="PUBLIC APPROVED BODY",
                task_type="delegated_routine",
                delegable=True,
                delegation_class=DelegationClass.NON_SENSITIVE_ROUTINE,
                constraints=TaskConstraints(
                    max_cost_usd=0.01,
                    max_latency_s=30,
                    max_output_tokens=256,
                    internet=True,
                    privacy=PrivacyLevel.PUBLIC,
                ),
                required_capabilities=("text_generation",),
            )
            config = next(
                item
                for item in load_provider_configs(ROOT / "config" / "providers.json")
                if item.id == "glm_flash_worker"
            )
            digest = GlmFlashWorkerProvider(config, environ={}).approval_metadata(task)[
                "required_approval_sha256"
            ]
            task = TaskContract.from_dict(
                {
                    **task.to_dict(),
                    "delegation_approval_sha256": digest,
                }
            )
            task_path = temp / "task.json"
            task_path.write_text(json.dumps(task.to_dict()), encoding="utf-8")
            GlmApprovalStore(temp).create(
                digest,
                signing_key="test-id." + "test-secret",
                expires_in_days=30,
            )
            output = io.StringIO()
            environment = {**os.environ, "MACR_STATE_ROOT": str(temp)}
            with patch.dict(os.environ, environment, clear=True):
                with contextlib.redirect_stdout(output):
                    status = _glm_preflight(
                        str(task_path),
                        str(ROOT / "config" / "providers.json"),
                        show_required_digest=False,
                    )

        document = json.loads(output.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(document["status"], "preflight_structurally_valid")
        self.assertEqual(document["required_approval_sha256"], digest)
        self.assertNotIn("system_text", document)
        self.assertNotIn("user_text", document)
        self.assertNotIn("PUBLIC APPROVED BODY", output.getvalue())

    def test_glm_approve_creates_external_host_record_without_key_or_content(self) -> None:
        with d_drive_tempdir() as state_root:
            task = TaskContract(
                task_id="glm-host-approve",
                goal="PUBLIC HOST APPROVAL BODY",
                task_type="delegated_routine",
                delegable=True,
                delegation_class=DelegationClass.NON_SENSITIVE_ROUTINE,
                constraints=TaskConstraints(
                    max_cost_usd=0.01,
                    max_latency_s=30,
                    max_output_tokens=256,
                    internet=True,
                    privacy=PrivacyLevel.PUBLIC,
                ),
                required_capabilities=("text_generation",),
            )
            config_path = ROOT / "config" / "providers.json"
            config = next(
                item
                for item in load_provider_configs(config_path)
                if item.id == "glm_flash_worker"
            )
            digest = GlmFlashWorkerProvider(config, environ={}).approval_metadata(task)[
                "required_approval_sha256"
            ]
            task = TaskContract.from_dict(
                {
                    **task.to_dict(),
                    "delegation_approval_sha256": digest,
                }
            )
            task_path = state_root / "task.json"
            task_path.write_text(json.dumps(task.to_dict()), encoding="utf-8")
            output = io.StringIO()
            environment = {
                **os.environ,
                "MACR_STATE_ROOT": str(state_root),
            }
            environment.pop("ZAI_API_KEY", None)
            with patch.dict(os.environ, environment, clear=True):
                with contextlib.redirect_stdout(output):
                    status = _glm_approve(
                        str(task_path),
                        str(config_path),
                        expires_in_days=30,
                        key_source=StaticKeySource(),
                        replace_existing=True,
                    )

        document = json.loads(output.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(document["status"], "host_approval_created")
        self.assertEqual(document["approval_sha256"], digest)
        self.assertEqual(document["approved_by"], "host_operator")
        self.assertNotIn("PUBLIC HOST APPROVAL BODY", output.getvalue())


if __name__ == "__main__":
    unittest.main()
