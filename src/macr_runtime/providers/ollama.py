from __future__ import annotations

import json
import os
import re
from typing import Any, Mapping

from ..config import AuthMode, ProviderConfig
from ..contracts import ProviderResult, ResultStatus, TaskContract
from ..errors import (
    ConfigurationError,
    ProviderPolicyError,
    ProviderProtocolError,
    ProviderUnavailableError,
)
from .base import BaseProvider, ProviderHealth
from .common import compile_worker_instruction
from .http_json import JsonTransport, UrllibJsonTransport


OLLAMA_LOOPBACK_BASE_URL = "http://127.0.0.1:11434"


def _resolve_keep_alive(environ: Mapping[str, str]) -> str:
    value = environ.get("MACR_OLLAMA_KEEP_ALIVE", "5m").strip()
    if value == "0":
        return value
    if not re.fullmatch(r"([1-9]|[1-5][0-9]|60)m", value):
        raise ProviderPolicyError(
            "MACR_OLLAMA_KEEP_ALIVE must be 0 or 1m..60m"
        )
    return value


def _optional_non_negative_int(name: str, value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProviderProtocolError(
            f"Ollama {name} must be a non-negative integer"
        )
    return value


def _duration_ms(name: str, value: Any) -> int | None:
    nanoseconds = _optional_non_negative_int(name, value)
    if nanoseconds is None:
        return None
    return round(nanoseconds / 1_000_000)


class OllamaChatProvider(BaseProvider):
    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: JsonTransport | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        if config.kind != "ollama_local_chat":
            raise ConfigurationError(
                "OllamaChatProvider requires kind=ollama_local_chat"
            )
        self.config = config
        self.provider_id = config.id
        self.connection_scope = config.connection_scope
        self.transport = transport or UrllibJsonTransport()
        self.environ = os.environ if environ is None else environ
        try:
            base_url = config.resolve_base_url(self.environ)
        except ConfigurationError as exc:
            raise ConfigurationError(
                "Ollama provider base URL must be exactly "
                f"{OLLAMA_LOOPBACK_BASE_URL}"
            ) from exc
        if base_url != OLLAMA_LOOPBACK_BASE_URL:
            raise ConfigurationError(
                "Ollama provider base URL must be exactly "
                f"{OLLAMA_LOOPBACK_BASE_URL}"
            )

    def health(self) -> ProviderHealth:
        if not self.config.enabled:
            return ProviderHealth(self.provider_id, False, "disabled")
        if not self.config.api_usage_allowed:
            return ProviderHealth(
                self.provider_id,
                False,
                "policy_denied",
                "local provider use is forbidden",
            )
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

    def _check_task_policy(self, task: TaskContract) -> None:
        if not self.config.enabled:
            raise ProviderPolicyError(f"provider {self.provider_id} is disabled")
        if not self.config.api_usage_allowed:
            raise ProviderPolicyError(
                f"local use is forbidden for provider {self.provider_id}"
            )
        if self.config.auth_mode is not AuthMode.NONE:
            raise ProviderPolicyError("local Ollama provider must use auth_mode none")
        if task.constraints.internet:
            raise ProviderPolicyError(
                "local Ollama task contract must disable internet access"
            )
        if task.constraints.privacy.value != "local_only":
            raise ProviderPolicyError(
                "local Ollama provider requires privacy level local_only"
            )
        if task.constraints.max_cost_usd != 0:
            raise ProviderPolicyError(
                "local Ollama provider requires max_cost_usd equal to zero"
            )
        if task.constraints.max_latency_s <= 0:
            raise ProviderPolicyError(
                "local Ollama dispatch requires a positive max_latency_s"
            )
        missing = sorted(
            set(task.required_capabilities) - set(self.config.capabilities)
        )
        if missing:
            raise ProviderPolicyError(
                f"provider {self.provider_id} lacks required capabilities: "
                f"{', '.join(missing)}"
            )

    def invoke(self, task: TaskContract) -> ProviderResult:
        self._check_task_policy(task)
        base_url = self.config.resolve_base_url(self.environ)
        model = self.config.resolve_model(self.environ)
        tags = self.transport.get_json(
            f"{base_url}/api/tags",
            headers={},
            timeout_s=max(0.001, min(task.constraints.max_latency_s, 30.0)),
        )
        models = tags.get("models")
        if not isinstance(models, list) or model not in {
            item.get("name") for item in models if isinstance(item, dict)
        }:
            raise ProviderUnavailableError(
                f"Ollama model is not installed: {model}"
            )

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": compile_worker_instruction(task),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        task.to_dict(),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
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
        document = self.transport.post_json(
            f"{base_url.rstrip('/')}{self.config.endpoint_path}",
            headers={},
            payload=payload,
            timeout_s=max(0.001, min(task.constraints.max_latency_s, 3600.0)),
        )
        if document.get("done") is not True:
            raise ProviderProtocolError("Ollama response did not complete")
        returned_model = document.get("model")
        if returned_model != model:
            raise ProviderProtocolError(
                f"Ollama response model mismatch: requested {model}, got {returned_model}"
            )
        message = document.get("message")
        if not isinstance(message, dict):
            raise ProviderProtocolError("Ollama response message must be an object")
        tool_calls = message.get("tool_calls")
        if tool_calls not in (None, (), []):
            raise ProviderProtocolError(
                "Ollama response unexpectedly contains tool calls"
            )
        answer = message.get("content")
        if not isinstance(answer, str):
            raise ProviderProtocolError(
                "Ollama response message.content must be a string"
            )

        input_tokens = _optional_non_negative_int(
            "prompt_eval_count", document.get("prompt_eval_count")
        )
        output_tokens = _optional_non_negative_int(
            "eval_count", document.get("eval_count")
        )
        metrics = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": None,
            "cached_tokens": None,
            "duration_ms": _duration_ms(
                "total_duration", document.get("total_duration")
            ),
            "load_duration_ms": _duration_ms(
                "load_duration", document.get("load_duration")
            ),
            "prompt_eval_duration_ms": _duration_ms(
                "prompt_eval_duration", document.get("prompt_eval_duration")
            ),
            "eval_duration_ms": _duration_ms(
                "eval_duration", document.get("eval_duration")
            ),
        }
        done_reason = document.get("done_reason")
        if done_reason is not None and not isinstance(done_reason, str):
            raise ProviderProtocolError(
                "Ollama response done_reason must be a string"
            )
        return ProviderResult(
            task_id=task.task_id,
            status=ResultStatus.CANDIDATE_SUCCESS,
            answer=answer,
            cost={
                "usage": {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                },
                "currency_cost_usd": 0.0,
            },
            warnings=(
                "Unverified local provider output; acceptance is separate.",
                "Low refusal does not imply correctness.",
            ),
            provider_meta={
                "provider": self.provider_id,
                "model": returned_model,
                "response_id": None,
                "wire_format": "ollama_chat",
                "done_reason": done_reason,
                "metrics": metrics,
            },
        )
