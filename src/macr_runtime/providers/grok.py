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
from .common import BOUNDED_WORKER_INSTRUCTION
from .http_json import JsonTransport, UrllibJsonTransport


def _extract_output_text(document: Mapping[str, Any]) -> str:
    output = document.get("output")
    if not isinstance(output, list):
        raise ProviderProtocolError("Grok response output must be an array")
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "output_text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
    if not parts:
        raise ProviderProtocolError("Grok response contains no output_text")
    return "".join(parts)


def _optional_non_negative_int(
    name: str,
    value: Any,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProviderProtocolError(f"Grok {name} must be a non-negative integer")
    return value


def _normalized_usage(document: Mapping[str, Any]) -> dict[str, Any]:
    usage = document.get("usage")
    if not isinstance(usage, dict):
        raise ProviderProtocolError("Grok response usage must be an object")
    output_details = usage.get("output_tokens_details")
    output_details = output_details if isinstance(output_details, dict) else {}
    input_details = usage.get("input_tokens_details")
    input_details = input_details if isinstance(input_details, dict) else {}
    return {
        "input_tokens": _optional_non_negative_int(
            "input_tokens", usage.get("input_tokens")
        ),
        "output_tokens": _optional_non_negative_int(
            "output_tokens", usage.get("output_tokens")
        ),
        "reasoning_tokens": _optional_non_negative_int(
            "reasoning_tokens", output_details.get("reasoning_tokens")
        ),
        "cached_tokens": _optional_non_negative_int(
            "cached_tokens", input_details.get("cached_tokens")
        ),
        "num_server_side_tools_used": _optional_non_negative_int(
            "num_server_side_tools_used",
            usage.get("num_server_side_tools_used", 0),
        ),
        "cost_in_usd_ticks": _optional_non_negative_int(
            "cost_in_usd_ticks", usage.get("cost_in_usd_ticks")
        ),
    }


def _cost_usd(cost_ticks: int) -> float:
    if isinstance(cost_ticks, bool) or not isinstance(cost_ticks, int) or cost_ticks < 0:
        raise ProviderProtocolError(
            "Grok cost_in_usd_ticks must be a non-negative integer"
        )
    return cost_ticks / 10_000_000_000


class GrokResponsesProvider(BaseProvider):
    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: JsonTransport | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        if config.kind != "grok_responses":
            raise ConfigurationError(
                "GrokResponsesProvider requires kind=grok_responses"
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
        if not self.config.api_usage_allowed:
            return ProviderHealth(
                self.provider_id,
                False,
                "policy_denied",
                "API use is forbidden",
            )
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
        if not self.config.enabled:
            raise ProviderPolicyError(f"provider {self.provider_id} is disabled")
        if not self.config.api_usage_allowed:
            raise ProviderPolicyError(
                f"API use is forbidden for provider {self.provider_id}"
            )
        if self.config.auth_mode is not AuthMode.API_KEY:
            raise ProviderPolicyError(
                f"provider {self.provider_id} must use API-key authentication"
            )
        if not task.constraints.internet:
            raise ProviderPolicyError(
                "Grok task contract must permit internet access"
            )
        if task.constraints.privacy.value not in self.config.approved_privacy:
            raise ProviderPolicyError(
                f"provider {self.provider_id} is not approved for privacy level "
                f"{task.constraints.privacy.value}"
            )
        if task.constraints.max_cost_usd <= 0:
            raise ProviderPolicyError(
                "Grok dispatch requires a positive max_cost_usd"
            )
        if task.constraints.max_latency_s <= 0:
            raise ProviderPolicyError(
                "Grok dispatch requires a positive max_latency_s"
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
        api_key = self._api_key()
        base_url = self.config.resolve_base_url(self.environ)
        model = self.config.resolve_model(self.environ)
        payload: dict[str, Any] = {
            "model": model,
            "input": [
                {"role": "system", "content": BOUNDED_WORKER_INSTRUCTION},
                {
                    "role": "user",
                    "content": json.dumps(
                        task.to_dict(),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            ],
            "store": False,
            "max_output_tokens": task.constraints.max_output_tokens,
        }
        if self.config.reasoning_effort:
            payload["reasoning"] = {"effort": self.config.reasoning_effort}
        timeout_s = max(0.001, min(task.constraints.max_latency_s, 3600.0))
        document = self.transport.post_json(
            f"{base_url.rstrip('/')}{self.config.endpoint_path}",
            headers={"Authorization": f"Bearer {api_key}"},
            payload=payload,
            timeout_s=timeout_s,
        )

        if document.get("status") not in {None, "completed"}:
            raise ProviderProtocolError("Grok response did not complete")
        returned_model = document.get("model")
        if returned_model != model:
            raise ProviderProtocolError(
                f"Grok response model mismatch: requested {model}, got {returned_model}"
            )
        answer = _extract_output_text(document)
        usage = _normalized_usage(document)
        if usage["num_server_side_tools_used"] != 0:
            raise ProviderProtocolError(
                "Grok response unexpectedly used server-side tools"
            )
        cost_ticks = usage["cost_in_usd_ticks"]
        if cost_ticks is None:
            raise ProviderProtocolError(
                "Grok response lacks cost_in_usd_ticks"
            )
        cost_usd = _cost_usd(cost_ticks)
        over_budget = cost_usd > task.constraints.max_cost_usd
        metrics = {
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "reasoning_tokens": usage["reasoning_tokens"],
            "cached_tokens": usage["cached_tokens"],
            "duration_ms": None,
        }
        warnings = [
            "Unverified Grok output; acceptance is separate.",
            "store=false does not prove account-level Zero Data Retention.",
        ]
        if over_budget:
            warnings.append("Actual provider cost exceeded max_cost_usd.")
        response_id = document.get("id")
        if response_id is not None and not isinstance(response_id, str):
            raise ProviderProtocolError("Grok response id must be a string")
        return ProviderResult(
            task_id=task.task_id,
            status=(
                ResultStatus.CANDIDATE_FAILURE
                if over_budget
                else ResultStatus.CANDIDATE_SUCCESS
            ),
            answer=answer,
            cost={
                "usage": usage,
                "cost_in_usd_ticks": cost_ticks,
                "currency_cost_usd": cost_usd,
            },
            warnings=tuple(warnings),
            provider_meta={
                "provider": self.provider_id,
                "model": returned_model,
                "response_id": response_id,
                "wire_format": "xai_responses",
                "metrics": metrics,
            },
        )
