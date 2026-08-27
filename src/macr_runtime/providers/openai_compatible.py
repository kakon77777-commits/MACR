from __future__ import annotations

import json
import os
from typing import Any, Mapping
from urllib.parse import urlparse

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


class OpenAICompatibleProvider(BaseProvider):
    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: JsonTransport | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.config = config
        self.provider_id = config.id
        self.connection_scope = config.connection_scope
        self.transport = transport or UrllibJsonTransport()
        self.environ = os.environ if environ is None else environ

    def _environment_value(self, name: str | None) -> str | None:
        if not name:
            return None
        value = self.environ.get(name)
        return value.strip() if value and value.strip() else None

    def _resolved(self) -> tuple[str, str, str]:
        key = self._environment_value(self.config.api_key_env)
        if not key:
            raise ProviderUnavailableError(
                f"provider {self.provider_id} is missing environment variable: "
                f"{self.config.api_key_env}"
            )
        try:
            base_url = self.config.resolve_base_url(self.environ)
        except ConfigurationError as exc:
            if "not configured" in str(exc):
                raise ProviderUnavailableError(str(exc)) from exc
            raise ProviderPolicyError(str(exc)) from exc
        try:
            model = self.config.resolve_model(self.environ)
        except ConfigurationError as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        self._validate_base_url(base_url)
        return key, base_url, model

    def _validate_base_url(self, base_url: str) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise ProviderPolicyError("external provider base_url must use absolute HTTPS")
        if parsed.username or parsed.password:
            raise ProviderPolicyError("provider credentials must not be embedded in base_url")
        hostname = parsed.hostname.lower() if parsed.hostname else ""
        if self.config.allowed_hosts and hostname not in self.config.allowed_hosts:
            raise ProviderPolicyError(
                f"provider {self.provider_id} base_url host is not allowlisted"
            )

    def _endpoint_url(self, base_url: str) -> str:
        return f"{base_url.rstrip('/')}{self.config.endpoint_path}"

    def health(self) -> ProviderHealth:
        if not self.config.enabled:
            return ProviderHealth(
                self.provider_id,
                False,
                "disabled",
                self.config.disabled_reason or "provider is disabled",
            )
        if not self.config.api_usage_allowed:
            return ProviderHealth(self.provider_id, False, "policy_denied", "API use is forbidden")
        if self.config.auth_mode is not AuthMode.API_KEY:
            return ProviderHealth(
                self.provider_id,
                False,
                "unsupported_auth_mode",
                self.config.auth_mode.value,
            )
        try:
            self._resolved()
        except (ProviderPolicyError, ProviderUnavailableError) as exc:
            return ProviderHealth(self.provider_id, False, "configuration_incomplete", str(exc))
        return ProviderHealth(
            self.provider_id,
            True,
            "configured_offline",
            "offline configuration checks passed; reachability was not tested",
        )

    def _check_task_policy(self, task: TaskContract) -> None:
        if not task.constraints.internet:
            raise ProviderPolicyError("task contract does not permit internet access")
        if task.constraints.privacy.value not in self.config.approved_privacy:
            raise ProviderPolicyError(
                f"provider {self.provider_id} is not approved for privacy level "
                f"{task.constraints.privacy.value}"
            )
        if task.constraints.max_cost_usd <= 0:
            raise ProviderPolicyError(
                "billable API dispatch requires a positive constraints.max_cost_usd"
            )
        if task.constraints.max_latency_s <= 0:
            raise ProviderPolicyError(
                "external provider dispatch requires a positive constraints.max_latency_s"
            )
        missing_capabilities = sorted(
            set(task.required_capabilities) - set(self.config.capabilities)
        )
        if missing_capabilities:
            raise ProviderPolicyError(
                f"provider {self.provider_id} lacks required capabilities: "
                f"{', '.join(missing_capabilities)}"
            )

    @staticmethod
    def _extract_content(document: Mapping[str, Any]) -> str:
        try:
            content = document["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderProtocolError(
                "provider response lacks choices[0].message.content"
            ) from exc
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = [
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("type") in {"text", "output_text"}
            ]
            if text_parts:
                return "".join(text_parts)
        raise ProviderProtocolError("provider message content is not supported text")

    def invoke(self, task: TaskContract) -> ProviderResult:
        if not self.config.enabled:
            raise ProviderPolicyError(f"provider {self.provider_id} is disabled")
        if not self.config.api_usage_allowed:
            raise ProviderPolicyError(f"API use is forbidden for provider {self.provider_id}")
        if self.config.auth_mode is not AuthMode.API_KEY:
            raise ProviderPolicyError(
                f"provider {self.provider_id} does not use the required API-key auth mode"
            )
        self._check_task_policy(task)
        api_key, base_url, model = self._resolved()
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": compile_worker_instruction(task),
                },
                {
                    "role": "user",
                    "content": json.dumps(task.to_dict(), ensure_ascii=False, sort_keys=True),
                },
            ],
        }
        timeout_s = max(0.001, min(task.constraints.max_latency_s, 300.0))
        document = self.transport.post_json(
            self._endpoint_url(base_url),
            headers={"Authorization": f"Bearer {api_key}"},
            payload=payload,
            timeout_s=timeout_s,
        )
        answer = self._extract_content(document)
        usage = document.get("usage") if isinstance(document.get("usage"), dict) else {}
        response_id = document.get("id") if isinstance(document.get("id"), str) else None
        return ProviderResult(
            task_id=task.task_id,
            status=ResultStatus.CANDIDATE_SUCCESS,
            answer=answer,
            cost={"usage": dict(usage), "currency_cost_usd": None},
            warnings=(
                "Unverified provider output; acceptance is a separate step.",
                "The positive task budget authorized dispatch, but billed currency cost is not independently verified in v0.1.",
            ),
            provider_meta={
                "provider": self.provider_id,
                "model": model,
                "response_id": response_id,
                "wire_format": "openai_compatible_chat_completions",
            },
        )
