from __future__ import annotations

from pathlib import Path
from typing import Mapping

from ..config import ProviderConfig
from ..contracts import ProviderResult, ResultStatus, TaskContract
from ..errors import ConfigurationError, ProviderProtocolError
from ..token_policy import ModelTokenPolicyResolver
from .common import compile_worker_instruction
from .google_base import BaseGoogleProvider
from .google_core import (
    PRICING_BASIS_VERSION,
    GoogleGenerationRequest,
    GoogleTransport,
    estimate_gemini_cost,
)


class GoogleGeminiProvider(BaseGoogleProvider):
    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: GoogleTransport | None = None,
        environ: Mapping[str, str] | None = None,
        cwd: str | Path | None = None,
    ) -> None:
        super().__init__(
            config,
            expected_kind="google_vertex_gemini",
            transport=transport,
            environ=environ,
            cwd=cwd,
        )
        model = config.resolve_model(self.environ)
        self.token_policy = ModelTokenPolicyResolver.builtins_only().resolve(
            self.provider_id,
            model,
        )
        if self.token_policy.connection_scope != self.connection_scope.value:
            raise ConfigurationError(
                "Google Gemini token policy must match the configured scope"
            )

    def invoke(self, task: TaskContract) -> ProviderResult:
        self._check_task_policy(task)
        self.token_policy.validate_task_output_tokens(
            task.constraints.max_output_tokens
        )
        media = self._validated_media(task)
        self._validate_offline_configuration()
        model = self.config.resolve_model(self.environ)
        response = self.transport.generate(
            GoogleGenerationRequest(
                model=model,
                system_instruction=compile_worker_instruction(task),
                goal=task.goal,
                media=media,
                max_output_tokens=task.constraints.max_output_tokens,
                thinking_level="medium",
                response_modalities=("TEXT",),
                image_size=None,
            ),
            timeout_s=self._timeout_s(task),
        )
        if response.model != model:
            raise ProviderProtocolError(
                f"Google response model mismatch: requested {model}"
            )
        if response.images:
            raise ProviderProtocolError(
                "Google Gemini text response unexpectedly contained images"
            )
        if not response.text:
            raise ProviderProtocolError("Google Gemini response contained no text")
        if response.finish_reason not in (None, "STOP"):
            raise ProviderProtocolError("Google Gemini response did not finish normally")
        estimated_cost = estimate_gemini_cost(response.usage)
        over_budget = (
            estimated_cost is not None
            and estimated_cost > task.constraints.max_cost_usd
        )
        cost_kind = "estimated" if estimated_cost is not None else "unavailable"
        metrics = {
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.output_tokens,
            "reasoning_tokens": response.usage.thought_tokens,
            "cached_tokens": response.usage.cached_tokens,
            "duration_ms": None,
            "input_media_count": len(media),
            "input_media_bytes": sum(len(item.data) for item in media),
            "output_artifact_count": 0,
            "output_artifact_bytes": 0,
            "cost_kind": cost_kind,
            "pricing_basis_version": PRICING_BASIS_VERSION,
        }
        warnings = [
            "Unverified Google output; acceptance is separate.",
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
            cost={
                "currency_cost_usd": estimated_cost,
                "cost_kind": cost_kind,
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
