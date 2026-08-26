from __future__ import annotations

import os
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from ..config import ProviderConfig
from ..errors import ProviderProtocolError, ProviderUnavailableError
from ..google_media import ValidatedMediaInput


PRICING_BASIS_VERSION = "2026-08-26"
_GEMINI_INPUT_PER_MILLION = 0.75
_GEMINI_OUTPUT_PER_MILLION = 3.75
_IMAGE_INPUT_PER_MILLION = 0.50
_IMAGE_THOUGHT_PER_MILLION = 3.00
_IMAGE_1K_OUTPUT_USD = 0.067
_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


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


def _optional_non_negative_int(name: str, value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProviderProtocolError(
            f"Google {name} must be a non-negative integer"
        )
    return value


def _usage_from_response(response: object) -> GoogleUsage:
    metadata = getattr(response, "usage_metadata", None)
    if metadata is None:
        return GoogleUsage()
    return GoogleUsage(
        prompt_tokens=_optional_non_negative_int(
            "prompt_token_count",
            getattr(metadata, "prompt_token_count", None),
        ),
        output_tokens=_optional_non_negative_int(
            "candidates_token_count",
            getattr(metadata, "candidates_token_count", None),
        ),
        thought_tokens=_optional_non_negative_int(
            "thoughts_token_count",
            getattr(metadata, "thoughts_token_count", None),
        ),
        cached_tokens=_optional_non_negative_int(
            "cached_content_token_count",
            getattr(metadata, "cached_content_token_count", None),
        ),
        total_tokens=_optional_non_negative_int(
            "total_token_count",
            getattr(metadata, "total_token_count", None),
        ),
    )


def estimate_gemini_cost(usage: GoogleUsage) -> float | None:
    if usage.prompt_tokens is None and usage.output_tokens is None:
        return None
    prompt = usage.prompt_tokens or 0
    output = (usage.output_tokens or 0) + (usage.thought_tokens or 0)
    return (
        prompt * _GEMINI_INPUT_PER_MILLION / 1_000_000
        + output * _GEMINI_OUTPUT_PER_MILLION / 1_000_000
    )


def estimate_image_cost(
    usage: GoogleUsage,
    *,
    image_count: int,
    image_size: str,
) -> float:
    if image_size != "1K":
        raise ProviderProtocolError("Google image cost supports only 1K output")
    if isinstance(image_count, bool) or not isinstance(image_count, int) or image_count < 1:
        raise ProviderProtocolError("Google image count must be a positive integer")
    prompt = usage.prompt_tokens or 0
    thoughts = usage.thought_tokens or 0
    return (
        image_count * _IMAGE_1K_OUTPUT_USD
        + prompt * _IMAGE_INPUT_PER_MILLION / 1_000_000
        + thoughts * _IMAGE_THOUGHT_PER_MILLION / 1_000_000
    )


class GoogleSdkTransport:
    def __init__(
        self,
        config: ProviderConfig,
        *,
        environ: Mapping[str, str] | None = None,
        client_factory: Callable[..., object] | None = None,
        credential_loader: Callable[[str], object] | None = None,
    ) -> None:
        self.config = config
        self.environ = os.environ if environ is None else environ
        self.client_factory = client_factory
        self.credential_loader = credential_loader

    def _credential_path(self) -> str:
        name = self.config.credential_path_env
        value = self.environ.get(name, "").strip() if name else ""
        if not value:
            raise ProviderUnavailableError(
                f"provider {self.config.id} is missing environment variable {name}"
            )
        return value

    def _project(self) -> str:
        name = self.config.project_env
        value = self.environ.get(name, "").strip() if name else ""
        if not value:
            raise ProviderUnavailableError(
                f"provider {self.config.id} is missing environment variable {name}"
            )
        return value

    @staticmethod
    def _default_credential_loader(path: str) -> object:
        from google.oauth2 import service_account

        return service_account.Credentials.from_service_account_file(
            path,
            scopes=[_CLOUD_PLATFORM_SCOPE],
        )

    def generate(
        self,
        request: GoogleGenerationRequest,
        *,
        timeout_s: float,
    ) -> GoogleNormalizedResponse:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="'_UnionGenericAlias' is deprecated.*",
                    category=DeprecationWarning,
                    module=r"google\.genai\.types",
                )
                from google import genai
                from google.genai import types

            loader = self.credential_loader or self._default_credential_loader
            credentials = loader(self._credential_path())
            http_options = types.HttpOptions(
                base_url=self.config.resolve_base_url(self.environ),
                api_version="v1",
                timeout=max(1, round(timeout_s * 1000)),
                retry_options=types.HttpRetryOptions(attempts=1),
            )
            factory = self.client_factory or genai.Client
            client = factory(
                vertexai=True,
                project=self._project(),
                location=self.config.location,
                credentials=credentials,
                http_options=http_options,
            )
            parts = [types.Part.from_text(text=request.goal)]
            parts.extend(
                types.Part.from_bytes(data=item.data, mime_type=item.mime_type)
                for item in request.media
            )
            content = types.Content(role="user", parts=parts)
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
            response = client.models.generate_content(
                model=request.model,
                contents=content,
                config=generate_config,
            )
        except (ProviderProtocolError, ProviderUnavailableError):
            raise
        except Exception as exc:
            raise ProviderUnavailableError(
                "Google provider request failed; remote details omitted"
            ) from exc
        return self._normalize_response(response, request)

    @staticmethod
    def _normalize_response(
        response: object,
        request: GoogleGenerationRequest,
    ) -> GoogleNormalizedResponse:
        model = getattr(response, "model_version", None)
        if model != request.model:
            raise ProviderProtocolError(
                f"Google response model mismatch: requested {request.model}"
            )
        response_id = getattr(response, "response_id", None)
        if response_id is not None and not isinstance(response_id, str):
            raise ProviderProtocolError("Google response ID must be a string")
        candidates = getattr(response, "candidates", None)
        if not isinstance(candidates, list) or len(candidates) != 1:
            raise ProviderProtocolError(
                "Google response must contain exactly one candidate"
            )
        candidate = candidates[0]
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None)
        if not isinstance(parts, list) or not parts:
            raise ProviderProtocolError("Google response candidate has no parts")
        text_parts: list[str] = []
        images: list[GoogleImagePayload] = []
        for part in parts:
            if getattr(part, "thought", False):
                continue
            for forbidden in (
                "function_call",
                "function_response",
                "executable_code",
                "code_execution_result",
                "tool_call",
                "tool_response",
            ):
                if getattr(part, forbidden, None) is not None:
                    raise ProviderProtocolError(
                        "Google response unexpectedly used a tool or code part"
                    )
            text = getattr(part, "text", None)
            inline = getattr(part, "inline_data", None)
            if isinstance(text, str):
                text_parts.append(text)
                continue
            if inline is not None:
                mime_type = getattr(inline, "mime_type", None)
                data = getattr(inline, "data", None)
                if not isinstance(mime_type, str) or not isinstance(data, bytes):
                    raise ProviderProtocolError(
                        "Google response image payload is malformed"
                    )
                images.append(GoogleImagePayload(mime_type=mime_type, data=data))
                continue
            raise ProviderProtocolError("Google response part has no allowed content")
        modalities = set(request.response_modalities)
        if modalities == {"TEXT"} and images:
            raise ProviderProtocolError(
                "Google text response unexpectedly contained an image"
            )
        if modalities == {"TEXT"} and not text_parts:
            raise ProviderProtocolError("Google text response contained no text")
        if not text_parts and not images:
            raise ProviderProtocolError("Google response contained no output")
        finish = getattr(candidate, "finish_reason", None)
        if finish is not None:
            finish = getattr(finish, "name", str(finish))
        return GoogleNormalizedResponse(
            model=model,
            response_id=response_id,
            text="".join(text_parts),
            images=tuple(images),
            finish_reason=finish,
            usage=_usage_from_response(response),
        )
