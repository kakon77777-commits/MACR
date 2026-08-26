from __future__ import annotations

import hashlib
import io
import unittest
from pathlib import Path

from PIL import Image

from macr_runtime.artifacts import ImageArtifactStore
from macr_runtime.config import AuthMode, ConnectionScope, ProviderConfig
from macr_runtime.contracts import (
    PrivacyLevel,
    TaskConstraints,
    TaskContract,
    WorkspaceSpec,
)
from macr_runtime.errors import ProviderPolicyError, ProviderProtocolError
from macr_runtime.providers.google_core import (
    GoogleImagePayload,
    GoogleNormalizedResponse,
    GoogleUsage,
)
from macr_runtime.providers.google_image import GoogleImageProvider
from tests.support import d_drive_tempdir, write_fake_google_credential
from tests.test_google_gemini_provider import (
    FakeGoogleTransport,
    google_test_environment,
)


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
        approved_privacy=(
            PrivacyLevel.PUBLIC.value,
            PrivacyLevel.INTERNAL_APPROVED.value,
        ),
    )


def image_bytes(image_format: str = "JPEG") -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (1024, 1024), "green").save(stream, format=image_format)
    return stream.getvalue()


def image_response(
    data: bytes,
    *,
    model: str = "gemini-3.1-flash-image",
    mime_type: str = "image/jpeg",
    count: int = 1,
) -> GoogleNormalizedResponse:
    return GoogleNormalizedResponse(
        model=model,
        response_id="google-image-response-1",
        text="",
        images=tuple(
            GoogleImagePayload(mime_type=mime_type, data=data)
            for _ in range(count)
        ),
        finish_reason="STOP",
        usage=GoogleUsage(prompt_tokens=20, output_tokens=1120),
    )


def image_task(
    workspace_root: Path,
    *,
    reference_count: int,
    max_cost_usd: float,
    task_id: str = "google-image-test",
) -> TaskContract:
    entries = []
    for index in range(reference_count):
        path = workspace_root / f"reference-{index}.png"
        Image.new("RGB", (16, 16), "blue").save(path, format="PNG")
        data = path.read_bytes()
        entries.append(
            {
                "type": "file",
                "path": path.name,
                "mime_type": "image/png",
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return TaskContract(
        task_id=task_id,
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


def image_provider(
    response: GoogleNormalizedResponse,
    state_root: Path,
    credential_path: Path,
) -> tuple[GoogleImageProvider, FakeGoogleTransport]:
    transport = FakeGoogleTransport(response)
    provider = GoogleImageProvider(
        google_image_config(),
        artifact_store=ImageArtifactStore(state_root),
        transport=transport,
        environ=google_test_environment(credential_path),
        cwd=state_root,
    )
    return provider, transport


class GoogleImageProviderTests(unittest.TestCase):
    def test_generates_one_exact_1k_artifact_with_estimated_cost(self) -> None:
        with d_drive_tempdir() as root:
            credential = write_fake_google_credential(root / "credential.json")
            data = image_bytes()
            provider, transport = image_provider(
                image_response(data),
                root,
                credential,
            )
            result = provider.invoke(image_task(root, reference_count=0, max_cost_usd=1.0))
            saved = root / result.artifacts[0]["relative_path"]
            self.assertEqual(saved.read_bytes(), data)
        request = transport.requests[0]["request"]
        self.assertEqual(request.model, "gemini-3.1-flash-image")
        self.assertEqual(request.response_modalities, ("TEXT", "IMAGE"))
        self.assertEqual(request.image_size, "1K")
        self.assertEqual(len(result.artifacts), 1)
        self.assertEqual(result.artifacts[0]["mime_type"], "image/jpeg")
        self.assertEqual(result.artifacts[0]["model"], "gemini-3.1-flash-image")
        self.assertEqual(result.cost["cost_kind"], "estimated")
        self.assertEqual(result.cost["pricing_basis_version"], "2026-08-26")
        self.assertNotIn(data.hex(), str(result.to_dict()))

    def test_one_reference_reaches_transport_as_validated_media(self) -> None:
        with d_drive_tempdir() as root:
            credential = write_fake_google_credential(root / "credential.json")
            provider, transport = image_provider(
                image_response(image_bytes()),
                root,
                credential,
            )
            provider.invoke(image_task(root, reference_count=1, max_cost_usd=1.0))
            self.assertEqual(len(transport.requests[0]["request"].media), 1)

    def test_two_references_and_low_budget_fail_before_transport(self) -> None:
        with d_drive_tempdir() as root:
            credential = write_fake_google_credential(root / "credential.json")
            cases = (
                image_task(root, reference_count=2, max_cost_usd=1.0, task_id="two-refs"),
                image_task(root, reference_count=0, max_cost_usd=0.05, task_id="low-budget"),
            )
            for task in cases:
                with self.subTest(task_id=task.task_id):
                    provider, transport = image_provider(
                        image_response(image_bytes()),
                        root,
                        credential,
                    )
                    with self.assertRaises(ProviderPolicyError):
                        provider.invoke(task)
                    self.assertEqual(transport.requests, [])

    def test_requires_exactly_one_image_and_exact_model(self) -> None:
        invalid = (
            image_response(image_bytes(), count=0),
            image_response(image_bytes(), count=2),
            image_response(image_bytes(), model="wrong-model"),
        )
        for index, response in enumerate(invalid):
            with self.subTest(index=index):
                with d_drive_tempdir() as root:
                    credential = write_fake_google_credential(root / "credential.json")
                    provider, _ = image_provider(response, root, credential)
                    with self.assertRaises(ProviderProtocolError):
                        provider.invoke(
                            image_task(
                                root,
                                reference_count=0,
                                max_cost_usd=1.0,
                                task_id=f"bad-response-{index}",
                            )
                        )

    def test_invalid_bytes_and_no_overwrite_are_rejected(self) -> None:
        with d_drive_tempdir() as root:
            credential = write_fake_google_credential(root / "credential.json")
            bad_provider, _ = image_provider(
                image_response(b"not-an-image"),
                root,
                credential,
            )
            with self.assertRaises(ProviderProtocolError):
                bad_provider.invoke(
                    image_task(
                        root,
                        reference_count=0,
                        max_cost_usd=1.0,
                        task_id="bad-bytes",
                    )
                )
            good_provider, _ = image_provider(
                image_response(image_bytes()),
                root,
                credential,
            )
            task = image_task(
                root,
                reference_count=0,
                max_cost_usd=1.0,
                task_id="no-overwrite",
            )
            good_provider.invoke(task)
            with self.assertRaises(FileExistsError):
                good_provider.invoke(task)


if __name__ == "__main__":
    unittest.main()
