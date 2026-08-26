from __future__ import annotations

import hashlib
import unittest
from dataclasses import replace
from pathlib import Path

from PIL import Image

from macr_runtime.config import AuthMode, ConnectionScope, ProviderConfig
from macr_runtime.contracts import (
    PrivacyLevel,
    TaskConstraints,
    TaskContract,
    WorkspaceSpec,
)
from macr_runtime.errors import (
    ProviderPolicyError,
    ProviderProtocolError,
    ProviderUnavailableError,
)
from macr_runtime.providers.google_core import (
    GoogleNormalizedResponse,
    GoogleUsage,
)
from macr_runtime.providers.google_gemini import GoogleGeminiProvider
from tests.support import d_drive_tempdir, write_fake_google_credential


class FakeGoogleTransport:
    def __init__(self, response: GoogleNormalizedResponse):
        self.response = response
        self.requests = []

    def generate(self, request, *, timeout_s):
        self.requests.append({"request": request, "timeout_s": timeout_s})
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
        approved_privacy=(
            PrivacyLevel.PUBLIC.value,
            PrivacyLevel.INTERNAL_APPROVED.value,
        ),
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
        usage=GoogleUsage(
            prompt_tokens=20,
            output_tokens=10,
            thought_tokens=4,
            cached_tokens=0,
            total_tokens=34,
        ),
    )


def gemini_task(
    workspace_root: Path,
    *,
    constraints: TaskConstraints | None = None,
    required_capabilities: tuple[str, ...] = ("text_generation",),
    inputs: tuple[dict[str, str], ...] = (),
    task_id: str = "google-gemini-test",
) -> TaskContract:
    return TaskContract(
        task_id=task_id,
        goal="return a candidate",
        task_type="provider_test",
        workspace=WorkspaceSpec(repo=str(workspace_root)),
        inputs=inputs,
        constraints=constraints
        or TaskConstraints(
            max_cost_usd=1.0,
            max_latency_s=30,
            max_output_tokens=64,
            internet=True,
            privacy=PrivacyLevel.PUBLIC,
        ),
        required_capabilities=required_capabilities,
    )


class GoogleGeminiProviderTests(unittest.TestCase):
    def test_request_is_exact_medium_text_and_cost_is_estimated(self) -> None:
        with d_drive_tempdir() as root:
            credential = write_fake_google_credential(root / "credential.json")
            transport = FakeGoogleTransport(success_response())
            result = GoogleGeminiProvider(
                google_gemini_config(),
                transport=transport,
                environ=google_test_environment(credential),
                cwd=root,
            ).invoke(gemini_task(root))
        request = transport.requests[0]["request"]
        self.assertEqual(request.model, "gemini-3.7-flash")
        self.assertEqual(request.thinking_level, "medium")
        self.assertEqual(request.response_modalities, ("TEXT",))
        self.assertEqual(result.answer, "candidate")
        self.assertEqual(result.provider_meta["model"], "gemini-3.7-flash")
        self.assertEqual(result.cost["cost_kind"], "estimated")
        self.assertEqual(result.cost["pricing_basis_version"], "2026-08-26")

    def test_validated_multimodal_bytes_reach_transport(self) -> None:
        with d_drive_tempdir() as root:
            credential = write_fake_google_credential(root / "credential.json")
            image = root / "blue.png"
            Image.new("RGB", (16, 16), "blue").save(image)
            data = image.read_bytes()
            entry = {
                "type": "file",
                "path": image.name,
                "mime_type": "image/png",
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            transport = FakeGoogleTransport(success_response())
            GoogleGeminiProvider(
                google_gemini_config(),
                transport=transport,
                environ=google_test_environment(credential),
                cwd=root,
            ).invoke(
                gemini_task(
                    root,
                    inputs=(entry,),
                    required_capabilities=("multimodal_understanding",),
                )
            )
        media = transport.requests[0]["request"].media
        self.assertEqual(media[0].data, data)
        self.assertEqual(media[0].mime_type, "image/png")

    def test_policy_denials_happen_before_transport(self) -> None:
        cases = (
            TaskConstraints(
                max_cost_usd=1,
                internet=False,
                privacy=PrivacyLevel.PUBLIC,
            ),
            TaskConstraints(
                max_cost_usd=1,
                internet=True,
                privacy=PrivacyLevel.LOCAL_ONLY,
            ),
            TaskConstraints(
                max_cost_usd=0,
                internet=True,
                privacy=PrivacyLevel.PUBLIC,
            ),
        )
        with d_drive_tempdir() as root:
            credential = write_fake_google_credential(root / "credential.json")
            for index, constraints in enumerate(cases):
                with self.subTest(index=index):
                    transport = FakeGoogleTransport(success_response())
                    provider = GoogleGeminiProvider(
                        google_gemini_config(),
                        transport=transport,
                        environ=google_test_environment(credential),
                        cwd=root,
                    )
                    with self.assertRaises(ProviderPolicyError):
                        provider.invoke(
                            gemini_task(
                                root,
                                constraints=constraints,
                                task_id=f"google-policy-{index}",
                            )
                        )
                    self.assertEqual(transport.requests, [])

    def test_capability_media_and_credential_fail_before_transport(self) -> None:
        with d_drive_tempdir() as root:
            bad_credential = root / "bad-credential.json"
            bad_credential.write_text("{}", encoding="utf-8")
            cases = (
                gemini_task(
                    root,
                    required_capabilities=("filesystem_write",),
                    task_id="google-bad-capability",
                ),
                gemini_task(
                    root,
                    inputs=(
                        {
                            "type": "file",
                            "path": "missing.png",
                            "mime_type": "image/png",
                            "sha256": "0" * 64,
                        },
                    ),
                    task_id="google-bad-media",
                ),
            )
            for task in cases:
                with self.subTest(task_id=task.task_id):
                    transport = FakeGoogleTransport(success_response())
                    provider = GoogleGeminiProvider(
                        google_gemini_config(),
                        transport=transport,
                        environ=google_test_environment(bad_credential),
                        cwd=root,
                    )
                    with self.assertRaises(
                        (ProviderPolicyError, ProviderUnavailableError)
                    ):
                        provider.invoke(task)
                    self.assertEqual(transport.requests, [])

    def test_invalid_credential_shape_fails_before_transport(self) -> None:
        with d_drive_tempdir() as root:
            bad_credential = root / "bad-credential.json"
            bad_credential.write_text("{}", encoding="utf-8")
            transport = FakeGoogleTransport(success_response())
            provider = GoogleGeminiProvider(
                google_gemini_config(),
                transport=transport,
                environ=google_test_environment(bad_credential),
                cwd=root,
            )
            with self.assertRaises(ProviderUnavailableError):
                provider.invoke(gemini_task(root))
            self.assertEqual(transport.requests, [])

    def test_wrong_returned_model_fails_after_one_request(self) -> None:
        with d_drive_tempdir() as root:
            credential = write_fake_google_credential(root / "credential.json")
            transport = FakeGoogleTransport(
                replace(success_response(), model="gemini-other")
            )
            provider = GoogleGeminiProvider(
                google_gemini_config(),
                transport=transport,
                environ=google_test_environment(credential),
                cwd=root,
            )
            with self.assertRaisesRegex(ProviderProtocolError, "model mismatch"):
                provider.invoke(gemini_task(root))
            self.assertEqual(len(transport.requests), 1)

    def test_health_is_offline_and_does_not_call_transport(self) -> None:
        with d_drive_tempdir() as root:
            credential = write_fake_google_credential(root / "credential.json")
            transport = FakeGoogleTransport(success_response())
            provider = GoogleGeminiProvider(
                google_gemini_config(),
                transport=transport,
                environ=google_test_environment(credential),
                cwd=root,
            )
            health = provider.health()
            self.assertTrue(health.ready)
            self.assertEqual(health.status, "configured_offline")
            self.assertEqual(transport.requests, [])


if __name__ == "__main__":
    unittest.main()
