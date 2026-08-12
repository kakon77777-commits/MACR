from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.parse import urlparse

from ..config import AuthMode, ProviderConfig
from ..contracts import ProviderResult, ResultStatus, TaskContract
from ..errors import (
    ProviderPolicyError,
    ProviderProtocolError,
    ProviderUnavailableError,
)
from .base import BaseProvider, ProviderHealth


class JsonTransport(Protocol):
    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_s: float,
    ) -> Mapping[str, Any]: ...


class _RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Prevent bearer credentials from being forwarded by urllib redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


@dataclass
class UrllibJsonTransport:
    max_request_bytes: int = 2 * 1024 * 1024
    max_response_bytes: int = 8 * 1024 * 1024

    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_s: float,
    ) -> Mapping[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(body) > self.max_request_bytes:
            raise ProviderProtocolError("provider request exceeded the configured size limit")
        request = urllib.request.Request(
            url,
            data=body,
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        opener = urllib.request.build_opener(_RejectRedirectHandler())
        try:
            with opener.open(request, timeout=timeout_s) as response:
                raw = response.read(self.max_response_bytes + 1)
        except urllib.error.HTTPError as exc:
            raise ProviderProtocolError(
                f"provider HTTP {exc.code}; remote response body omitted"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            reason = getattr(exc, "reason", str(exc))
            raise ProviderUnavailableError(f"provider connection failed: {reason}") from exc
        if len(raw) > self.max_response_bytes:
            raise ProviderProtocolError("provider response exceeded the configured size limit")
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderProtocolError("provider response was not valid UTF-8 JSON") from exc
        if not isinstance(document, dict):
            raise ProviderProtocolError("provider response root must be a JSON object")
        return document


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
        self.transport = transport or UrllibJsonTransport()
        self.environ = os.environ if environ is None else environ

    def _environment_value(self, name: str | None) -> str | None:
        if not name:
            return None
        value = self.environ.get(name)
        return value.strip() if value and value.strip() else None

    def _resolved(self) -> tuple[str, str, str]:
        key = self._environment_value(self.config.api_key_env)
        base_url = self._environment_value(self.config.base_url_env)
        model = self._environment_value(self.config.model_env)
        missing = [
            name
            for name, value in (
                (self.config.api_key_env, key),
                (self.config.base_url_env, base_url),
                (self.config.model_env, model),
            )
            if name and not value
        ]
        if missing:
            raise ProviderUnavailableError(
                f"provider {self.provider_id} is missing environment variables: {', '.join(missing)}"
            )
        if key is None or base_url is None or model is None:
            raise ProviderUnavailableError(
                f"provider {self.provider_id} API configuration is incomplete"
            )
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
        return ProviderHealth(self.provider_id, True, "ready", "offline configuration checks passed")

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
                    "content": (
                        "You are a bounded MACR worker. Treat the supplied TaskContract as authoritative. "
                        "Return a candidate answer with concise evidence and warnings. Do not claim that "
                        "generation is verification or acceptance."
                    ),
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
