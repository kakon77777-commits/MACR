from __future__ import annotations

from pathlib import Path
from typing import Mapping

from ..artifacts import ImageArtifactStore
from ..config import ProviderConfig
from ..contracts import ProviderResult, ResultStatus, TaskContract
from ..errors import ProviderPolicyError, ProviderProtocolError
from ..storage import StorageLayout
from .common import compile_worker_instruction
from .google_base import BaseGoogleProvider
from .google_core import (
    PRICING_BASIS_VERSION,
    GoogleGenerationRequest,
    GoogleTransport,
    GoogleUsage,
    estimate_image_cost,
)


class GoogleImageProvider(BaseGoogleProvider):
    def __init__(
        self,
        config: ProviderConfig,
        *,
        artifact_store: ImageArtifactStore | None = None,
        transport: GoogleTransport | None = None,
        environ: Mapping[str, str] | None = None,
        cwd: str | Path | None = None,
    ) -> None:
        super().__init__(
            config,
            expected_kind="google_vertex_image",
            transport=transport,
            environ=environ,
            cwd=cwd,
        )
        self.artifact_store = artifact_store or ImageArtifactStore(
            StorageLayout.from_environment(self.environ).state_root
        )

    def invoke(self, task: TaskContract) -> ProviderResult:
        self._check_task_policy(task)
        media = self._validated_media(task)
        if len(media) > 1:
            raise ProviderPolicyError(
                "Google image generation accepts at most one reference image"
            )
        preflight_cost = estimate_image_cost(
            GoogleUsage(prompt_tokens=0),
            image_count=1,
            image_size="1K",
        )
        if task.constraints.max_cost_usd < preflight_cost:
            raise ProviderPolicyError(
                "Google image task budget is below the 1K preflight estimate"
            )
        self._validate_offline_configuration()
        model = self.config.resolve_model(self.environ)
        response = self.transport.generate(
            GoogleGenerationRequest(
                model=model,
                system_instruction=compile_worker_instruction(task),
                goal=task.goal,
                media=media,
                max_output_tokens=task.constraints.max_output_tokens,
                thinking_level=None,
                response_modalities=("TEXT", "IMAGE"),
                image_size="1K",
            ),
            timeout_s=self._timeout_s(task),
        )
        if response.model != model:
            raise ProviderProtocolError(
                f"Google response model mismatch: requested {model}"
            )
        if response.finish_reason not in (None, "STOP"):
            raise ProviderProtocolError("Google image response did not finish normally")
        if len(response.images) != 1:
            raise ProviderProtocolError(
                "Google image response must contain exactly one image"
            )
        image = response.images[0]
        estimated_cost = estimate_image_cost(
            response.usage,
            image_count=1,
            image_size="1K",
        )
        over_budget = estimated_cost > task.constraints.max_cost_usd
        record = self.artifact_store.save_image(
            task_id=task.task_id,
            model=model,
            data=image.data,
            declared_mime=image.mime_type,
        )
        metrics = {
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.output_tokens,
            "reasoning_tokens": response.usage.thought_tokens,
            "cached_tokens": response.usage.cached_tokens,
            "duration_ms": None,
            "input_media_count": len(media),
            "input_media_bytes": sum(len(item.data) for item in media),
            "output_artifact_count": 1,
            "output_artifact_bytes": record.byte_length,
            "cost_kind": "estimated",
            "pricing_basis_version": PRICING_BASIS_VERSION,
        }
        warnings = [
            "Unverified Google image output; acceptance is separate.",
            "Currency cost is estimated; Cloud Billing remains authoritative.",
        ]
        if over_budget:
            warnings.append("Estimated provider cost exceeded max_cost_usd.")
        return ProviderResult(
            task_id=task.task_id,
            status=(
                ResultStatus.CANDIDATE_FAILURE
                if over_budget
                else ResultStatus.CANDIDATE_SUCCESS
            ),
            answer=response.text,
            artifacts=(record.to_dict(),),
            cost={
                "currency_cost_usd": estimated_cost,
                "cost_kind": "estimated",
                "pricing_basis_version": PRICING_BASIS_VERSION,
                "usage": response.usage.to_dict(),
            },
            warnings=tuple(warnings),
            provider_meta={
                "provider": self.provider_id,
                "model": response.model,
                "response_id": response.response_id,
                "finish_reason": response.finish_reason,
                "wire_format": "google_genai_vertex",
                "metrics": metrics,
            },
        )
