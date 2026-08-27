from __future__ import annotations

import json
import os
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
from .common import bounded_worker_instruction
from .http_json import JsonTransport, UrllibJsonTransport


_LIST_INPUT_USD_PER_M = 0.15
_LIST_OUTPUT_USD_PER_M = 0.50
_CURRENT_INPUT_USD_PER_M = 0.075
_CURRENT_OUTPUT_USD_PER_M = 0.25
_PRICING_BASIS_VERSION = "zai-2026-08-27"
_MAX_TEXT_INPUT_BYTES = 1_000_000
_FIXED_BASE_URL = "https://api.z.ai/api/paas/v4"
_FIXED_ENDPOINT_PATH = "/chat/completions"
_FIXED_MODEL = "glm-5.3-flash"


def _non_negative_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProviderProtocolError(f"GLM {name} must be a non-negative integer")
    return value


def _estimated_cost(
    prompt_tokens: int,
    completion_tokens: int,
    *,
    input_rate: float,
    output_rate: float,
) -> float:
    return (
        prompt_tokens * input_rate + completion_tokens * output_rate
    ) / 1_000_000


def _validated_text_inputs(task: TaskContract) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    aggregate_bytes = 0
    for item in task.inputs:
        if set(item) - {"type", "name", "content"}:
            raise ProviderPolicyError(
                "GLM delegation accepts only bounded text inputs"
            )
        if item.get("type") != "text":
            raise ProviderPolicyError(
                "GLM delegation accepts only bounded text inputs"
            )
        name = item.get("name")
        content = item.get("content")
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name.strip()) > 128
            or any(character in name for character in ("/", "\\", ":"))
        ):
            raise ProviderPolicyError(
                "GLM text inputs require a bounded non-path name"
            )
        if not isinstance(content, str) or not content.strip():
            raise ProviderPolicyError(
                "GLM text inputs require non-empty content"
            )
        aggregate_bytes += len(content.encode("utf-8"))
        if aggregate_bytes > _MAX_TEXT_INPUT_BYTES:
            raise ProviderPolicyError("GLM text inputs exceed the aggregate size limit")
        normalized.append(
            {
                "type": "text",
                "name": name.strip(),
                "content": content,
            }
        )
    return normalized


class GlmFlashWorkerProvider(BaseProvider):
    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: JsonTransport | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        if config.kind != "zai_glm_worker":
            raise ConfigurationError(
                "GlmFlashWorkerProvider requires kind=zai_glm_worker"
            )
        if (
            config.base_url != _FIXED_BASE_URL
            or config.base_url_env is not None
            or config.endpoint_path != _FIXED_ENDPOINT_PATH
            or config.model != _FIXED_MODEL
            or config.model_env is not None
            or config.reasoning_effort != "max"
            or config.allowed_hosts != ("api.z.ai",)
        ):
            raise ConfigurationError(
                "GLM worker requires the fixed direct profile"
            )
        self.config = config
        self.provider_id = config.id
        self.connection_scope = config.connection_scope
        self.transport = transport or UrllibJsonTransport()
        self.environ = os.environ if environ is None else environ

    def _api_key(self) -> str:
        name = self.config.api_key_env
        value = self.environ.get(name, "").strip() if name else ""
        if not value:
            raise ProviderUnavailableError(
                f"provider {self.provider_id} is missing environment variable {name}"
            )
        return value

    def health(self) -> ProviderHealth:
        if not self.config.enabled:
            return ProviderHealth(self.provider_id, False, "disabled")
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

    def _check_task_policy(self, task: TaskContract) -> None:
        if not self.config.enabled or not self.config.api_usage_allowed:
            raise ProviderPolicyError(f"provider {self.provider_id} is not enabled")
        if self.config.auth_mode is not AuthMode.API_KEY:
            raise ProviderPolicyError(
                f"provider {self.provider_id} must use API-key authentication"
            )
        if not task.delegable:
            raise ProviderPolicyError(
                "GLM dispatch requires explicit delegable=true"
            )
        if not task.constraints.internet:
            raise ProviderPolicyError("GLM task contract must permit internet access")
        if task.constraints.privacy.value not in self.config.approved_privacy:
            raise ProviderPolicyError(
                f"GLM worker is not approved for privacy level "
                f"{task.constraints.privacy.value}"
            )
        if task.constraints.max_cost_usd <= 0:
            raise ProviderPolicyError("GLM dispatch requires a positive max_cost_usd")
        if task.constraints.max_latency_s <= 0:
            raise ProviderPolicyError("GLM dispatch requires a positive max_latency_s")
        if task.workspace.write_scope:
            raise ProviderPolicyError("GLM worker may not receive write_scope authority")
        if task.return_contract.patch:
            raise ProviderPolicyError("GLM worker may not receive patch authority")
        if not task.verification.required:
            raise ProviderPolicyError("GLM output requires independent verification")
        missing = sorted(
            set(task.required_capabilities) - set(self.config.capabilities)
        )
        if missing:
            raise ProviderPolicyError(
                f"GLM worker lacks required capabilities: {', '.join(missing)}"
            )

    def _delegation_envelope(self, task: TaskContract) -> dict[str, Any]:
        return {
            "task_id": task.task_id,
            "goal": task.goal,
            "task_type": task.task_type,
            "delegable": task.delegable,
            "inputs": _validated_text_inputs(task),
            "required_capabilities": list(task.required_capabilities),
            "verification": task.verification.to_dict(),
            "return_contract": task.return_contract.to_dict(),
            "max_output_tokens": task.constraints.max_output_tokens,
        }

    def _check_conservative_budget(
        self,
        task: TaskContract,
        system_text: str,
        user_text: str,
    ) -> None:
        prompt_token_ceiling = (
            len(system_text.encode("utf-8"))
            + len(user_text.encode("utf-8"))
            + 512
        )
        cost_ceiling = _estimated_cost(
            prompt_token_ceiling,
            task.constraints.max_output_tokens,
            input_rate=_LIST_INPUT_USD_PER_M,
            output_rate=_LIST_OUTPUT_USD_PER_M,
        )
        if cost_ceiling > task.constraints.max_cost_usd:
            raise ProviderPolicyError(
                "GLM task budget is below the conservative ceiling"
            )

    def invoke(self, task: TaskContract) -> ProviderResult:
        self._check_task_policy(task)
        envelope = self._delegation_envelope(task)
        system_text = bounded_worker_instruction(task.goal)
        user_text = json.dumps(
            envelope,
            ensure_ascii=False,
            sort_keys=True,
        )
        self._check_conservative_budget(task, system_text, user_text)
        api_key = self._api_key()
        base_url = self.config.resolve_base_url(self.environ)
        model = self.config.resolve_model(self.environ)
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": system_text,
                },
                {
                    "role": "user",
                    "content": user_text,
                },
            ],
            "temperature": 1.0,
            "top_p": 0.95,
            "reasoning_effort": self.config.reasoning_effort,
            "thinking": {"type": "enabled", "clear_thinking": False},
            "max_tokens": task.constraints.max_output_tokens,
            "stream": False,
        }
        timeout_s = max(0.001, min(task.constraints.max_latency_s, 300.0))
        document = self.transport.post_json(
            f"{base_url.rstrip('/')}{self.config.endpoint_path}",
            headers={"Authorization": f"Bearer {api_key}"},
            payload=payload,
            timeout_s=timeout_s,
        )
        returned_model = document.get("model")
        if returned_model != model:
            raise ProviderProtocolError(
                f"GLM response model mismatch: requested {model}, got {returned_model}"
            )
        choices = document.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise ProviderProtocolError("GLM response must contain exactly one choice")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise ProviderProtocolError("GLM response choice must be an object")
        if choice.get("finish_reason") != "stop":
            raise ProviderProtocolError("GLM response finish_reason must be stop")
        message = choice.get("message")
        if (
            not isinstance(message, dict)
            or not isinstance(message.get("content"), str)
            or not message["content"].strip()
        ):
            raise ProviderProtocolError("GLM response contains no text content")
        if message.get("tool_calls") not in (None, []):
            raise ProviderProtocolError("GLM response unexpectedly contained tool calls")
        usage = document.get("usage")
        if not isinstance(usage, dict):
            raise ProviderProtocolError("GLM response usage must be an object")
        prompt_tokens = _non_negative_int("prompt_tokens", usage.get("prompt_tokens"))
        completion_tokens = _non_negative_int(
            "completion_tokens", usage.get("completion_tokens")
        )
        if completion_tokens > task.constraints.max_output_tokens:
            raise ProviderProtocolError(
                "GLM completion tokens exceeded the requested output bound"
            )
        total_tokens = _non_negative_int("total_tokens", usage.get("total_tokens"))
        if total_tokens != prompt_tokens + completion_tokens:
            raise ProviderProtocolError(
                "GLM total_tokens must equal prompt_tokens plus completion_tokens"
            )
        prompt_details = usage.get("prompt_tokens_details")
        prompt_details = prompt_details if isinstance(prompt_details, dict) else {}
        completion_details = usage.get("completion_tokens_details")
        completion_details = (
            completion_details if isinstance(completion_details, dict) else {}
        )
        cached_tokens = _non_negative_int(
            "cached_tokens", prompt_details.get("cached_tokens", 0)
        )
        reasoning_tokens = _non_negative_int(
            "reasoning_tokens", completion_details.get("reasoning_tokens", 0)
        )
        list_cost = _estimated_cost(
            prompt_tokens,
            completion_tokens,
            input_rate=_LIST_INPUT_USD_PER_M,
            output_rate=_LIST_OUTPUT_USD_PER_M,
        )
        current_cost = _estimated_cost(
            prompt_tokens,
            completion_tokens,
            input_rate=_CURRENT_INPUT_USD_PER_M,
            output_rate=_CURRENT_OUTPUT_USD_PER_M,
        )
        response_id = document.get("id")
        if response_id is not None and not isinstance(response_id, str):
            raise ProviderProtocolError("GLM response id must be a string")
        return ProviderResult(
            task_id=task.task_id,
            status=ResultStatus.CANDIDATE_SUCCESS,
            answer=message["content"],
            cost={
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "cached_tokens": cached_tokens,
                    "reasoning_tokens": reasoning_tokens,
                },
                "currency_cost_usd": list_cost,
                "current_price_estimated_usd": current_cost,
                "cost_kind": "estimated",
                "pricing_basis_version": _PRICING_BASIS_VERSION,
            },
            warnings=(
                "Unverified GLM output; acceptance is separate.",
                "Cost uses conservative list pricing; current promotional pricing may be lower.",
            ),
            provider_meta={
                "provider": self.provider_id,
                "model": returned_model,
                "response_id": response_id,
                "wire_format": "zai_chat_completions",
                "metrics": {
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "reasoning_tokens": reasoning_tokens,
                    "cached_tokens": cached_tokens,
                    "duration_ms": None,
                    "cost_kind": "estimated",
                    "pricing_basis_version": _PRICING_BASIS_VERSION,
                },
            },
        )
