from __future__ import annotations

import os
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .config import AuthMode, ConnectionScope, ProviderConfig
from .direct_contracts import DirectMessage, DirectRunSettings
from .errors import (
    ConfigurationError,
    ProviderAdmissionRequiredError,
    ProviderPolicyError,
    ProviderProtocolError,
    ProviderUnavailableError,
)
from .execution import ProviderState, ProviderUsage, RawProviderObservation
from .providers.base import ProviderHealth
from .providers.http_json import JsonTransport, UrllibJsonTransport
from .providers.ollama import OLLAMA_LOOPBACK_BASE_URL, _resolve_keep_alive
from .provider_admission import (
    ProviderAdmissionDirectory,
    ProviderAdmissionKernel,
    ProviderAdmissionPermit,
    ProviderAdmissionRequest,
)
from .token_policy import ModelTokenPolicyResolver


_QWYTHOS_MODEL = "hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_XAI_SECRET = re.compile(r"^xai-[A-Za-z0-9_-]{20,4092}$")


@dataclass(frozen=True)
class DirectProviderReply:
    observation: RawProviderObservation
    validation_error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.observation, RawProviderObservation):
            raise ValueError("observation must be RawProviderObservation")
        if self.validation_error is not None:
            if (
                not isinstance(self.validation_error, str)
                or not re.fullmatch(r"[a-z0-9_]{1,64}", self.validation_error)
            ):
                raise ValueError("validation_error must be a safe reason code")

    def to_public_dict(self) -> dict[str, object]:
        return {
            **self.observation.to_public_dict(),
            "validation_error": self.validation_error,
        }


class DirectProviderAdapter(Protocol):
    provider_id: str

    def health(self) -> ProviderHealth:
        raise NotImplementedError

    def model_identity(self) -> dict[str, str | None]:
        raise NotImplementedError

    def invoke(
        self,
        messages: Sequence[DirectMessage],
        settings: DirectRunSettings,
        *,
        admission_permit: ProviderAdmissionPermit | None = None,
        admission_request: ProviderAdmissionRequest | None = None,
    ) -> DirectProviderReply:
        raise NotImplementedError


def _validate_messages(
    messages: Sequence[DirectMessage],
) -> tuple[DirectMessage, ...]:
    if isinstance(messages, (str, bytes)) or not isinstance(messages, Sequence):
        raise ProviderProtocolError("Direct messages must be a sequence")
    normalized = tuple(messages)
    if not normalized or any(
        not isinstance(item, DirectMessage) for item in normalized
    ):
        raise ProviderProtocolError("Direct messages are missing or malformed")
    system_indexes = [
        index for index, item in enumerate(normalized) if item.role == "system"
    ]
    if len(system_indexes) > 1 or (system_indexes and system_indexes[0] != 0):
        raise ProviderProtocolError(
            "Direct system message must appear at most once and first"
        )
    conversation = normalized[1:] if system_indexes else normalized
    if not conversation or conversation[0].role != "user":
        raise ProviderProtocolError("Direct history must begin with a user message")
    if normalized[-1].role != "user":
        raise ProviderProtocolError("Direct request must end with a user message")
    for index, item in enumerate(conversation):
        expected = "user" if index % 2 == 0 else "assistant"
        if item.role != expected:
            raise ProviderProtocolError(
                "Direct history roles must alternate user and assistant"
            )
    return normalized


def _safe_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _nanoseconds_to_ms(value: Any) -> int | None:
    normalized = _safe_non_negative_int(value)
    return None if normalized is None else round(normalized / 1_000_000)


def _safe_grok_output(document: Mapping[str, Any]) -> bytes | None:
    output = document.get("output")
    if not isinstance(output, list):
        return None
    parts: list[str] = []
    for item in output:
        if not isinstance(item, Mapping) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, Mapping) or block.get("type") != "output_text":
                continue
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    if not parts:
        return None
    return "".join(parts).encode("utf-8")


class GrokDirectAdapter:
    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: JsonTransport | None = None,
        environ: Mapping[str, str] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        admission_guard: ProviderAdmissionKernel | None = None,
        offline_test_transport: bool = False,
    ) -> None:
        if not isinstance(offline_test_transport, bool):
            raise ValueError("offline_test_transport must be boolean")
        if (
            config.id != "grok"
            or config.kind != "grok_responses"
            or config.auth_mode is not AuthMode.API_KEY
            or config.connection_scope is not ConnectionScope.EXTERNAL_HTTPS
        ):
            raise ConfigurationError(
                "Grok Direct requires the exact grok API-key profile"
            )
        self.config = config
        self.provider_id = config.id
        self._transport_injected = transport is not None
        self.transport = transport or UrllibJsonTransport()
        self.environ = os.environ if environ is None else environ
        self._monotonic = monotonic
        self.admission_guard = admission_guard
        self.offline_test_transport = offline_test_transport
        self.requires_provider_admission = True
        if config.resolve_model(self.environ) != "grok-4.6":
            raise ConfigurationError("Grok Direct model must be grok-4.6")
        self.token_policy = ModelTokenPolicyResolver.builtins_only().resolve(
            "grok",
            "grok-4.6",
        )
        if config.resolve_base_url(self.environ) != "https://api.x.ai/v1":
            raise ConfigurationError("Grok Direct route must use api.x.ai/v1")

    def _api_key(self) -> str:
        name = self.config.api_key_env
        value = self.environ.get(name, "").strip() if name else ""
        if not value:
            raise ProviderUnavailableError(
                f"provider grok is missing environment variable {name}",
                network_attempted=False,
                response_received=False,
                transport_stage="pre_network",
            )
        if not _XAI_SECRET.fullmatch(value):
            raise ProviderUnavailableError(
                "provider grok credential has an invalid format",
                network_attempted=False,
                response_received=False,
                transport_stage="pre_network",
            )
        return value

    def _check_policy(self) -> None:
        if not self.config.enabled or not self.config.api_usage_allowed:
            raise ProviderPolicyError("Grok Direct use is disabled")

    def health(self) -> ProviderHealth:
        try:
            self._check_policy()
            self._api_key()
        except (ProviderPolicyError, ProviderUnavailableError) as exc:
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
            "credential and route configuration passed; no provider call was made",
        )

    def model_identity(self) -> dict[str, str | None]:
        return {"model": "grok-4.6", "model_digest": None}

    def validate_admission_transport_binding(self) -> None:
        if not isinstance(self.admission_guard, ProviderAdmissionKernel):
            raise ProviderAdmissionRequiredError(
                "Grok Direct requires the shared provider admission kernel"
            )
        if self.offline_test_transport:
            if not self._transport_injected or isinstance(
                self.transport,
                UrllibJsonTransport,
            ):
                raise ProviderAdmissionRequiredError(
                    "offline-test admission cannot use production transport"
                )
            expected_runtime_path = self.admission_guard.path
        else:
            state_root = Path(
                self.environ.get(
                    "MACR_STATE_ROOT",
                    r"D:\AI_RESIDENCE\AI_Runtime\macr-state",
                )
            )
            expected_runtime_path = (
                state_root / "runtime" / "dispatch.sqlite3"
            )
        ProviderAdmissionKernel.require_transport_binding(
            self.admission_guard,
            expected_runtime_path,
            offline_test=self.offline_test_transport,
        )

    def invoke(
        self,
        messages: Sequence[DirectMessage],
        settings: DirectRunSettings,
        *,
        admission_permit: ProviderAdmissionPermit | None = None,
        admission_request: ProviderAdmissionRequest | None = None,
    ) -> DirectProviderReply:
        self._check_policy()
        normalized = _validate_messages(messages)
        if not isinstance(settings, DirectRunSettings):
            raise ValueError("settings must be DirectRunSettings")
        self.token_policy.validate_task_output_tokens(settings.max_output_tokens)
        if (
            not isinstance(admission_permit, ProviderAdmissionPermit)
            or not isinstance(admission_request, ProviderAdmissionRequest)
        ):
            raise ProviderAdmissionRequiredError(
                "Grok Direct requires a one-use provider admission permit"
            )
        self.validate_admission_transport_binding()
        api_key = self._api_key()
        payload: dict[str, Any] = {
            "model": "grok-4.6",
            "input": [item.to_dict() for item in normalized],
            "store": False,
            "max_output_tokens": settings.max_output_tokens,
        }
        if self.config.reasoning_effort:
            payload["reasoning"] = {"effort": self.config.reasoning_effort}
        ProviderAdmissionKernel.begin_transport(
            self.admission_guard,
            admission_permit,
            admission_request,
        )
        started = self._monotonic()
        document = self.transport.post_json(
            "https://api.x.ai/v1/responses",
            headers={"Authorization": f"Bearer {api_key}"},
            payload=payload,
            timeout_s=settings.timeout_s,
        )
        duration_ms = max(0, round((self._monotonic() - started) * 1000))
        return self._parse(document, duration_ms=duration_ms)

    def _parse(
        self,
        document: Mapping[str, Any],
        *,
        duration_ms: int,
    ) -> DirectProviderReply:
        status = document.get("status")
        status_completed = status in {None, "completed"}
        returned_model = (
            document.get("model") if isinstance(document.get("model"), str) else None
        )
        response_id = (
            document.get("id") if isinstance(document.get("id"), str) else None
        )
        usage = document.get("usage")
        usage = usage if isinstance(usage, Mapping) else {}
        input_details = usage.get("input_tokens_details")
        input_details = input_details if isinstance(input_details, Mapping) else {}
        output_details = usage.get("output_tokens_details")
        output_details = output_details if isinstance(output_details, Mapping) else {}
        tools = _safe_non_negative_int(usage.get("num_server_side_tools_used"))
        cost_ticks = _safe_non_negative_int(usage.get("cost_in_usd_ticks"))
        answer_bytes = _safe_grok_output(document)
        if not status_completed:
            validation_error = "provider_incomplete"
            provider_state = ProviderState.INCOMPLETE
        elif returned_model != "grok-4.6":
            validation_error = "model_mismatch"
            provider_state = ProviderState.COMPLETED
        elif tools != 0:
            validation_error = "unexpected_tools"
            provider_state = ProviderState.COMPLETED
        elif answer_bytes is None or not answer_bytes.strip():
            validation_error = "answer_missing"
            provider_state = ProviderState.MALFORMED
        else:
            validation_error = None
            provider_state = ProviderState.COMPLETED
        observation = RawProviderObservation(
            provider_id=self.provider_id,
            model=returned_model,
            response_id=response_id,
            finish_reason=(
                "stop"
                if status_completed
                else (status if isinstance(status, str) and status.strip() else "other")
            ),
            usage=ProviderUsage(
                _safe_non_negative_int(usage.get("input_tokens")),
                _safe_non_negative_int(usage.get("output_tokens")),
                _safe_non_negative_int(output_details.get("reasoning_tokens")),
                _safe_non_negative_int(input_details.get("cached_tokens")),
            ),
            currency_cost_usd=(
                cost_ticks / 10_000_000_000 if cost_ticks is not None else None
            ),
            cost_kind=("provider_reported" if cost_ticks is not None else None),
            pricing_basis_version=("xai-cost-ticks-v1" if cost_ticks is not None else None),
            duration_ms=duration_ms,
            answer_bytes=answer_bytes,
            provider_state=provider_state,
            network_attempted=True,
            response_received=True,
            transport_stage="response_received",
        )
        return DirectProviderReply(observation, validation_error)


class QwythosDirectAdapter:
    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: JsonTransport | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        if (
            config.id != "ollama_qwythos"
            or config.kind != "ollama_local_chat"
            or config.auth_mode is not AuthMode.NONE
            or config.connection_scope is not ConnectionScope.LOOPBACK_HTTP
        ):
            raise ConfigurationError(
                "Qwythos Direct requires the exact local Ollama profile"
            )
        self.config = config
        self.provider_id = config.id
        self.transport = transport or UrllibJsonTransport()
        self.environ = os.environ if environ is None else environ
        if config.resolve_base_url(self.environ) != OLLAMA_LOOPBACK_BASE_URL:
            raise ConfigurationError(
                "Qwythos Direct route must be exactly 127.0.0.1:11434"
            )
        if config.resolve_model(self.environ) != _QWYTHOS_MODEL:
            raise ConfigurationError("Qwythos Direct model tag is not canonical")

    def _check_policy(self) -> None:
        if not self.config.enabled or not self.config.api_usage_allowed:
            raise ProviderPolicyError("Qwythos Direct use is disabled")
        _resolve_keep_alive(self.environ)

    def model_identity(self) -> dict[str, str | None]:
        self._check_policy()
        document = self.transport.get_json(
            f"{OLLAMA_LOOPBACK_BASE_URL}/api/tags",
            headers={},
            timeout_s=30.0,
        )
        models = document.get("models")
        if not isinstance(models, list):
            raise ProviderProtocolError("Ollama model list is malformed")
        matches = [
            item
            for item in models
            if isinstance(item, Mapping)
            and item.get("name", item.get("model")) == _QWYTHOS_MODEL
        ]
        if len(matches) != 1:
            raise ProviderUnavailableError(
                f"Ollama model is not installed: {_QWYTHOS_MODEL}"
            )
        digest = matches[0].get("digest")
        normalized_digest = digest.lower() if isinstance(digest, str) else ""
        if not _SHA256.fullmatch(normalized_digest):
            raise ProviderProtocolError("Ollama model digest is malformed")
        return {"model": _QWYTHOS_MODEL, "model_digest": normalized_digest}

    def health(self) -> ProviderHealth:
        try:
            identity = self.model_identity()
        except (ProviderPolicyError, ProviderProtocolError, ProviderUnavailableError) as exc:
            return ProviderHealth(
                self.provider_id,
                False,
                "unavailable_local",
                str(exc),
            )
        return ProviderHealth(
            self.provider_id,
            True,
            "available_local",
            f"exact local model is installed; digest {identity['model_digest']}",
        )

    def invoke(
        self,
        messages: Sequence[DirectMessage],
        settings: DirectRunSettings,
    ) -> DirectProviderReply:
        normalized = _validate_messages(messages)
        if not isinstance(settings, DirectRunSettings):
            raise ValueError("settings must be DirectRunSettings")
        self.model_identity()
        payload = {
            "model": _QWYTHOS_MODEL,
            "messages": [item.to_dict() for item in normalized],
            "stream": False,
            "think": False,
            "keep_alive": _resolve_keep_alive(self.environ),
            "options": {
                "num_ctx": settings.hard_context_tokens,
                "num_predict": settings.max_output_tokens,
                "temperature": settings.temperature,
                "top_p": settings.top_p,
                "top_k": 20,
            },
        }
        document = self.transport.post_json(
            f"{OLLAMA_LOOPBACK_BASE_URL}/api/chat",
            headers={},
            payload=payload,
            timeout_s=settings.timeout_s,
        )
        return self._parse(document)

    def _parse(self, document: Mapping[str, Any]) -> DirectProviderReply:
        done = document.get("done") is True
        returned_model = (
            document.get("model") if isinstance(document.get("model"), str) else None
        )
        message = document.get("message")
        message = message if isinstance(message, Mapping) else {}
        content = message.get("content")
        answer_bytes = content.encode("utf-8") if isinstance(content, str) else None
        tool_calls = message.get("tool_calls")
        if not done:
            validation_error = "provider_incomplete"
            provider_state = ProviderState.INCOMPLETE
        elif returned_model != _QWYTHOS_MODEL:
            validation_error = "model_mismatch"
            provider_state = ProviderState.COMPLETED
        elif tool_calls not in (None, (), []):
            validation_error = "unexpected_tools"
            provider_state = ProviderState.COMPLETED
        elif message.get("role", "assistant") != "assistant":
            validation_error = "message_role_mismatch"
            provider_state = ProviderState.MALFORMED
        elif answer_bytes is None or not answer_bytes.strip():
            validation_error = "answer_missing"
            provider_state = ProviderState.MALFORMED
        else:
            validation_error = None
            provider_state = ProviderState.COMPLETED
        done_reason = document.get("done_reason")
        finish_reason = (
            done_reason
            if isinstance(done_reason, str) and done_reason.strip()
            else ("stop" if done else "other")
        )
        observation = RawProviderObservation(
            provider_id=self.provider_id,
            model=returned_model,
            response_id=None,
            finish_reason=finish_reason,
            usage=ProviderUsage(
                _safe_non_negative_int(document.get("prompt_eval_count")),
                _safe_non_negative_int(document.get("eval_count")),
                None,
                None,
            ),
            currency_cost_usd=0.0,
            cost_kind="zero_local",
            pricing_basis_version="local-zero-api-v1",
            duration_ms=_nanoseconds_to_ms(document.get("total_duration")),
            answer_bytes=answer_bytes,
            provider_state=provider_state,
        )
        return DirectProviderReply(observation, validation_error)


class DirectProviderRegistry:
    def __init__(self, providers: Mapping[str, DirectProviderAdapter]) -> None:
        if set(providers) != {"grok", "ollama_qwythos"}:
            raise ConfigurationError(
                "Direct provider registry requires both grok and ollama_qwythos"
            )
        self._providers = dict(providers)

    @classmethod
    def from_configs(
        cls,
        configs: Sequence[ProviderConfig],
        *,
        transports: Mapping[str, JsonTransport] | None = None,
        environ: Mapping[str, str] | None = None,
        provider_admissions: ProviderAdmissionDirectory | None = None,
        offline_test_transport: bool = False,
    ) -> "DirectProviderRegistry":
        selected: dict[str, ProviderConfig] = {}
        for config in configs:
            if config.id in {"grok", "ollama_qwythos"}:
                if config.id in selected:
                    raise ConfigurationError(
                        f"duplicate Direct provider configuration: {config.id}"
                    )
                selected[config.id] = config
        if set(selected) != {"grok", "ollama_qwythos"}:
            raise ConfigurationError(
                "Direct provider registry requires both grok and ollama_qwythos"
            )
        transport_map = {} if transports is None else dict(transports)
        return cls(
            {
                "grok": GrokDirectAdapter(
                    selected["grok"],
                    transport=transport_map.get("grok"),
                    environ=environ,
                    admission_guard=(
                        provider_admissions.get("grok")
                        if provider_admissions is not None
                        else None
                    ),
                    offline_test_transport=offline_test_transport,
                ),
                "ollama_qwythos": QwythosDirectAdapter(
                    selected["ollama_qwythos"],
                    transport=transport_map.get("ollama_qwythos"),
                    environ=environ,
                ),
            }
        )

    def provider_ids(self) -> tuple[str, ...]:
        return ("grok", "ollama_qwythos")

    def get(self, provider_id: str) -> DirectProviderAdapter:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise KeyError(f"{provider_id} is not a Direct provider") from exc

    def health(self) -> tuple[dict[str, object], ...]:
        return tuple(
            self._providers[provider_id].health().to_dict()
            for provider_id in self.provider_ids()
        )
