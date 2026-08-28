from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Mapping

from ..config import AuthMode, ConnectionScope, ProviderConfig
from ..contracts import (
    DelegationClass,
    PrivacyLevel,
    ProviderResult,
    ResultStatus,
    TaskContract,
)
from ..errors import (
    ConfigurationError,
    MacrError,
    ProviderPolicyError,
    ProviderProtocolError,
    ProviderUnavailableError,
)
from ..execution import (
    ProviderExecution,
    ProviderState,
    ProviderUsage,
    RawProviderObservation,
)
from ..glm_approval import GlmApprovalStore
from ..task_preflight import validate_task_consistency
from .base import BaseProvider, ProviderHealth
from .common import compile_worker_instruction
from .http_json import JsonTransport, UrllibJsonTransport


_LIST_INPUT_USD_PER_M = 0.15
_LIST_OUTPUT_USD_PER_M = 0.50
_PROMOTIONAL_INPUT_USD_PER_M = 0.075
_PROMOTIONAL_OUTPUT_USD_PER_M = 0.25
_PROMOTIONAL_PRICE_OBSERVED_ON = "2026-08-27"
_PRICING_BASIS_VERSION = "zai-2026-08-27"
_MAX_TEXT_INPUT_BYTES = 1_000_000
_FIXED_BASE_URL = "https://api.z.ai/api/paas/v4"
_FIXED_ENDPOINT_PATH = "/chat/completions"
_FIXED_MODEL = "glm-5.3-flash"
_ZAI_KEY_SHAPE = re.compile(r"^[^.\s]+\.[^.\s]+$")
_ALLOWED_TASK_TYPES = frozenset({"delegated_routine", "provider_conformance"})
_OBVIOUS_CREDENTIAL_MARKER = re.compile(
    r"(?i)(?:-----BEGIN (?:[a-z0-9]+ )*PRIVATE KEY-----|"
    r"(?:api(?:[\s_-]+)?key|access(?:[\s_-]+)?token|"
    r"private(?:[\s_-]+)?key)\s*[:=])"
)
_WINDOWS_UNC_PATH_CANDIDATE = re.compile(
    r"(?i)\\{2,}(?P<server>[^\s\\/:*?\"<>|{}\[\]]+)"
    r"\\+(?P<share>[^\s\\/:*?\"<>|{}\[\]]+)"
)
_FORWARD_UNC_PATH_CANDIDATE = re.compile(
    r"(?i)(?<![:/])//(?P<server>[^\s\\/:*?\"<>|{}\[\]]+)"
    r"/(?P<share>[^\s\\/:*?\"<>|{}\[\]]+)"
)
_URI_TOKEN = re.compile(
    r"(?i)(?<![a-z0-9+.-])(?P<scheme>[a-z][a-z0-9+.-]*):/{2}[^\s]*"
)
_FILE_URI = re.compile(r"(?i)(?<![a-z0-9+.-])file:/{2,}[^\s]*")
_WINDOWS_DRIVE_PATH_CANDIDATE = re.compile(
    r"(?i)(?<![a-z0-9])(?P<drive>[a-z]):(?P<separator>[\\/])"
)
_LATEX_CONTROL_SEQUENCE = re.compile(r"\\+(?P<command>[a-zA-Z]+)")
_WINDOWS_COMPONENT_FORBIDDEN = frozenset('<>:"|?*')
# This is intentionally a closed ambiguity list, not a general LaTeX stripper.
# Unlisted words and recognized words followed by path-like continuation remain denied.
_LATEX_DRIVE_AMBIGUITIES = frozenset(
    {
        "delta",
        "exists",
        "forall",
        "neg",
        "qquad",
        "quad",
        "text",
        "texttt",
    }
)


def _is_uri_drive_ambiguity(value: str, candidate: re.Match[str]) -> bool:
    for uri in _URI_TOKEN.finditer(value):
        if not (uri.start() <= candidate.start() < uri.end()):
            continue
        if candidate.start() == uri.end("scheme") - 1:
            return True
        return (
            candidate.group("separator") == "/"
            and uri.group("scheme").lower() in {"http", "https"}
        )
    return False


def _has_path_like_continuation(value: str, start: int) -> bool:
    suffix = value[start:]
    separators = [
        index
        for index in (suffix.find("\\"), suffix.find("/"))
        if index >= 0
    ]
    if not separators:
        return False
    separator_index = min(separators)
    component = suffix[:separator_index]
    after_separator = separator_index
    while (
        after_separator < len(suffix)
        and suffix[after_separator] in {"\\", "/"}
    ):
        after_separator += 1
    if after_separator < len(suffix) and suffix[after_separator] in "}])":
        remainder = suffix[after_separator + 1 :]
        if "\\" not in remainder and "/" not in remainder:
            return False
    return not any(character in _WINDOWS_COMPONENT_FORBIDDEN for character in component)


def _contains_obvious_sensitive_marker(value: str) -> bool:
    if _OBVIOUS_CREDENTIAL_MARKER.search(value):
        return True
    if _FILE_URI.search(value):
        return True
    if _WINDOWS_UNC_PATH_CANDIDATE.search(value):
        return True
    if _FORWARD_UNC_PATH_CANDIDATE.search(value):
        return True
    for candidate in _WINDOWS_DRIVE_PATH_CANDIDATE.finditer(value):
        if _is_uri_drive_ambiguity(value, candidate):
            continue
        if candidate.group("separator") == "\\":
            control = _LATEX_CONTROL_SEQUENCE.match(value, candidate.end() - 1)
            if (
                control is not None
                and control.group("command").lower() in _LATEX_DRIVE_AMBIGUITIES
                and not _has_path_like_continuation(value, control.end())
            ):
                continue
        return True
    return False


class GlmFixedKeySource:
    def __init__(
        self,
        canonical_root: str | Path = r"D:\KEY",
        key_path: str | Path = r"D:\KEY\GLM.txt",
    ) -> None:
        self.canonical_root = Path(canonical_root)
        self.key_path = Path(key_path)

    @staticmethod
    def _is_reparse(path: Path) -> bool:
        return path.is_symlink() or (
            hasattr(os.path, "isjunction") and os.path.isjunction(path)
        )

    def _validated_path(self) -> Path:
        try:
            absolute_root = self.canonical_root.absolute()
            absolute_key = self.key_path.absolute()
            if absolute_root.drive.upper() != "D:" or absolute_key.drive.upper() != "D:":
                raise ProviderUnavailableError("GLM key custody must remain on D:")
            current = Path(absolute_root.anchor)
            for component in absolute_root.parts[1:]:
                current = current / component
                if self._is_reparse(current):
                    raise ProviderUnavailableError(
                        "GLM canonical key-root ancestry contains a reparse point"
                    )
            if self._is_reparse(absolute_key):
                raise ProviderUnavailableError("GLM key file may not be a reparse point")
            resolved_root = absolute_root.resolve(strict=True)
            resolved_key = absolute_key.resolve(strict=True)
            if not resolved_key.is_relative_to(resolved_root):
                raise ProviderUnavailableError(
                    "GLM key file is outside the canonical key root"
                )
            current = resolved_root
            for component in resolved_key.relative_to(resolved_root).parts[:-1]:
                current = current / component
                if self._is_reparse(current):
                    raise ProviderUnavailableError(
                        "GLM key parent contains a reparse point"
                    )
            size = resolved_key.stat().st_size
            if size <= 0 or size > 16384:
                raise ProviderUnavailableError("GLM key file size is invalid")
            return resolved_key
        except ProviderUnavailableError:
            raise
        except OSError as exc:
            raise ProviderUnavailableError(
                "GLM fixed key file is unavailable"
            ) from exc

    def check_metadata(self) -> None:
        self._validated_path()

    def load(self) -> str:
        path = self._validated_path()
        try:
            value = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exc:
            raise ProviderUnavailableError(
                "GLM fixed key file is unavailable"
            ) from exc
        if not _ZAI_KEY_SHAPE.fullmatch(value):
            raise ProviderUnavailableError("GLM key file shape is invalid")
        return value


def _non_negative_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProviderProtocolError(f"GLM {name} must be a non-negative integer")
    return value


def _safe_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _safe_non_empty_string(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
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


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


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
        key_source: GlmFixedKeySource | None = None,
        approval_store: Any | None = None,
    ) -> None:
        if config.kind != "zai_glm_worker":
            raise ConfigurationError(
                "GlmFlashWorkerProvider requires kind=zai_glm_worker"
            )
        if (
            config.id != "glm_flash_worker"
            or config.base_url != _FIXED_BASE_URL
            or config.base_url_env is not None
            or config.endpoint_path != _FIXED_ENDPOINT_PATH
            or config.model != _FIXED_MODEL
            or config.model_env is not None
            or config.reasoning_effort != "max"
            or config.allowed_hosts != ("api.z.ai",)
            or config.auth_mode is not AuthMode.API_KEY_FILE
            or config.connection_scope is not ConnectionScope.EXTERNAL_HTTPS
            or config.api_key_env is not None
            or config.api_key_file != r"D:\KEY\GLM.txt"
            or config.credential_path_env is not None
            or config.project_env is not None
            or config.capabilities != ("text_generation",)
            or config.approved_privacy
            != (
                PrivacyLevel.PUBLIC.value,
                PrivacyLevel.INTERNAL_APPROVED.value,
            )
        ):
            raise ConfigurationError(
                "GLM worker requires the fixed direct profile"
            )
        self.config = config
        self.provider_id = config.id
        self.connection_scope = config.connection_scope
        self.transport = transport or UrllibJsonTransport()
        self.environ = os.environ if environ is None else environ
        self.key_source = key_source or GlmFixedKeySource()
        self.approval_store = approval_store or GlmApprovalStore(
            self.environ.get(
                "MACR_STATE_ROOT",
                r"D:\AI_RESIDENCE\AI_Runtime\macr-state",
            )
        )

    def _api_key(self) -> str:
        value = self.key_source.load()
        if not _ZAI_KEY_SHAPE.fullmatch(value):
            raise ProviderUnavailableError(
                f"provider {self.provider_id} credential shape is invalid"
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
            self.key_source.check_metadata()
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
        if self.config.auth_mode is not AuthMode.API_KEY_FILE:
            raise ProviderPolicyError(
                f"provider {self.provider_id} must use fixed API-key-file authentication"
            )
        if not task.delegable:
            raise ProviderPolicyError(
                "GLM dispatch requires explicit delegable=true"
            )
        if task.delegation_class is not DelegationClass.NON_SENSITIVE_ROUTINE:
            raise ProviderPolicyError(
                "GLM dispatch requires non_sensitive_routine delegation class"
            )
        if task.task_type not in _ALLOWED_TASK_TYPES:
            raise ProviderPolicyError(
                "GLM dispatch requires an approved routine task type"
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
        if task.required_capabilities != ("text_generation",):
            raise ProviderPolicyError(
                "GLM worker requires exactly text_generation capability"
            )

    def _delegation_envelope(self, task: TaskContract) -> dict[str, Any]:
        inputs = _validated_text_inputs(task)
        if _contains_obvious_sensitive_marker(task.goal) or any(
            _contains_obvious_sensitive_marker(item["content"])
            for item in inputs
        ):
            raise ProviderPolicyError(
                "GLM delegation contains an obvious sensitive marker"
            )
        return {
            "goal": task.goal,
            "delegable": task.delegable,
            "inputs": inputs,
            "required_capabilities": list(task.required_capabilities),
            "verification": task.verification.to_dict(),
            "return_contract": task.return_contract.to_dict(),
            "policy_clauses": task.policy_clauses.to_dict(),
            "max_output_tokens": task.constraints.max_output_tokens,
        }

    def _check_conservative_budget(
        self,
        task: TaskContract,
        system_text: str,
        user_text: str,
    ) -> float:
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
        return cost_ceiling

    def _prepare(self, task: TaskContract) -> dict[str, Any]:
        validate_task_consistency(task)
        self._check_task_policy(task)
        envelope = self._delegation_envelope(task)
        system_text = compile_worker_instruction(task)
        user_text = _canonical_json(envelope)
        cost_ceiling = self._check_conservative_budget(
            task,
            system_text,
            user_text,
        )
        endpoint = f"{_FIXED_BASE_URL}{_FIXED_ENDPOINT_PATH}"
        request_payload = {
            "model": _FIXED_MODEL,
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ],
            "temperature": 1.0,
            "top_p": 0.95,
            "reasoning_effort": "max",
            "thinking": {"type": "enabled", "clear_thinking": False},
            "max_tokens": task.constraints.max_output_tokens,
            "stream": False,
        }
        approval_manifest = {
            "approval_schema": 1,
            "provider_id": "glm_flash_worker",
            "endpoint": endpoint,
            "model": _FIXED_MODEL,
            "pricing_basis_version": _PRICING_BASIS_VERSION,
            "delegation_class": task.delegation_class.value,
            "task_type": task.task_type,
            "privacy": task.constraints.privacy.value,
            "max_cost_usd": task.constraints.max_cost_usd,
            "max_output_tokens": task.constraints.max_output_tokens,
            "request_payload": request_payload,
        }
        approval_sha256 = hashlib.sha256(
            _canonical_json(approval_manifest).encode("utf-8")
        ).hexdigest()
        return {
            "system_text": system_text,
            "user_text": user_text,
            "approval_sha256": approval_sha256,
            "request_bytes": len(_canonical_json(request_payload).encode("utf-8")),
            "cost_ceiling": cost_ceiling,
            "endpoint": endpoint,
            "request_payload": request_payload,
        }

    def _safe_approval_metadata(
        self,
        task: TaskContract,
        prepared: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model": _FIXED_MODEL,
            "endpoint": prepared["endpoint"],
            "delegation_class": task.delegation_class.value,
            "required_approval_sha256": prepared["approval_sha256"],
            "request_bytes": prepared["request_bytes"],
            "conservative_cost_ceiling_usd": prepared["cost_ceiling"],
            "pricing_basis_version": _PRICING_BASIS_VERSION,
        }

    def approval_metadata(self, task: TaskContract) -> dict[str, Any]:
        prepared = self._prepare(task)
        return self._safe_approval_metadata(task, prepared)

    def _validate_approval_prepared(self, task: TaskContract) -> dict[str, Any]:
        prepared = self._prepare(task)
        supplied = task.delegation_approval_sha256 or ""
        if not hmac.compare_digest(supplied, prepared["approval_sha256"]):
            raise ProviderPolicyError(
                "GLM delegation approval digest is missing or stale"
            )
        self.approval_store.inspect(prepared["approval_sha256"])
        return prepared

    def validate_approval(self, task: TaskContract) -> dict[str, Any]:
        prepared = self._validate_approval_prepared(task)
        return self._safe_approval_metadata(task, prepared)

    def _post_validated_task_once(self, task: TaskContract) -> Mapping[str, Any]:
        prepared = self._validate_approval_prepared(task)
        api_key = self._api_key()
        self.approval_store.verify(
            prepared["approval_sha256"],
            signing_key=api_key,
        )
        timeout_s = max(0.001, min(task.constraints.max_latency_s, 300.0))
        return self.transport.post_json(
            prepared["endpoint"],
            headers={"Authorization": f"Bearer {api_key}"},
            payload=prepared["request_payload"],
            timeout_s=timeout_s,
        )

    @staticmethod
    def _safe_usage_detail(
        usage: Mapping[str, Any] | None,
        details_name: str,
        field_name: str,
    ) -> int | None:
        if usage is None:
            return None
        if details_name not in usage or usage.get(details_name) is None:
            return 0
        details = usage.get(details_name)
        if not isinstance(details, Mapping):
            return None
        if field_name not in details:
            return 0
        return _safe_non_negative_int(details.get(field_name))

    def _observe_response(
        self,
        document: Mapping[str, Any],
        elapsed_ms: int,
    ) -> RawProviderObservation:
        choices = document.get("choices")
        choice = (
            choices[0]
            if isinstance(choices, list)
            and len(choices) == 1
            and isinstance(choices[0], dict)
            else None
        )
        finish_reason = _safe_non_empty_string(
            choice.get("finish_reason") if choice is not None else None
        )
        message = choice.get("message") if choice is not None else None
        content = message.get("content") if isinstance(message, dict) else None
        answer_bytes = None
        if isinstance(content, str):
            try:
                answer_bytes = content.encode("utf-8")
            except UnicodeEncodeError:
                answer_bytes = None

        raw_usage = document.get("usage")
        usage = raw_usage if isinstance(raw_usage, Mapping) else None
        prompt_tokens = _safe_non_negative_int(
            usage.get("prompt_tokens") if usage is not None else None
        )
        completion_tokens = _safe_non_negative_int(
            usage.get("completion_tokens") if usage is not None else None
        )
        cached_tokens = self._safe_usage_detail(
            usage,
            "prompt_tokens_details",
            "cached_tokens",
        )
        reasoning_tokens = self._safe_usage_detail(
            usage,
            "completion_tokens_details",
            "reasoning_tokens",
        )
        list_cost = (
            _estimated_cost(
                prompt_tokens,
                completion_tokens,
                input_rate=_LIST_INPUT_USD_PER_M,
                output_rate=_LIST_OUTPUT_USD_PER_M,
            )
            if prompt_tokens is not None and completion_tokens is not None
            else None
        )
        provider_state = ProviderState.MALFORMED
        if finish_reason == "stop":
            provider_state = ProviderState.COMPLETED
        elif finish_reason is not None:
            provider_state = ProviderState.INCOMPLETE

        return RawProviderObservation(
            provider_id=self.provider_id,
            model=_safe_non_empty_string(document.get("model")),
            response_id=_safe_non_empty_string(document.get("id")),
            finish_reason=finish_reason,
            usage=ProviderUsage(
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                reasoning_tokens=reasoning_tokens,
                cached_tokens=cached_tokens,
            ),
            currency_cost_usd=list_cost,
            cost_kind="estimated" if list_cost is not None else None,
            pricing_basis_version=(
                _PRICING_BASIS_VERSION if list_cost is not None else None
            ),
            duration_ms=elapsed_ms,
            answer_bytes=answer_bytes,
            provider_state=provider_state,
        )

    @staticmethod
    def _observed_total_tokens(document: Mapping[str, Any]) -> int | None:
        usage = document.get("usage")
        if not isinstance(usage, Mapping):
            return None
        return _safe_non_negative_int(usage.get("total_tokens"))

    def _cost_from_observation(
        self,
        document: Mapping[str, Any],
        observation: RawProviderObservation,
    ) -> dict[str, Any]:
        prompt_tokens = observation.usage.input_tokens
        completion_tokens = observation.usage.output_tokens
        promotional_cost = (
            _estimated_cost(
                prompt_tokens,
                completion_tokens,
                input_rate=_PROMOTIONAL_INPUT_USD_PER_M,
                output_rate=_PROMOTIONAL_OUTPUT_USD_PER_M,
            )
            if prompt_tokens is not None and completion_tokens is not None
            else None
        )
        return {
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": self._observed_total_tokens(document),
                "cached_tokens": observation.usage.cached_tokens,
                "reasoning_tokens": observation.usage.reasoning_tokens,
            },
            "currency_cost_usd": observation.currency_cost_usd,
            "promotional_price_estimated_usd": promotional_cost,
            "promotional_price_observed_on": (
                _PROMOTIONAL_PRICE_OBSERVED_ON
                if promotional_cost is not None
                else None
            ),
            "cost_kind": observation.cost_kind,
            "pricing_basis_version": observation.pricing_basis_version,
        }

    def _provider_meta_from_observation(
        self,
        observation: RawProviderObservation,
        *,
        failure_type: str | None = None,
    ) -> dict[str, Any]:
        meta = {
            "provider": self.provider_id,
            "model": observation.model,
            "response_id": observation.response_id,
            "finish_reason": observation.finish_reason,
            "wire_format": "zai_chat_completions",
            "metrics": {
                "input_tokens": observation.usage.input_tokens,
                "output_tokens": observation.usage.output_tokens,
                "reasoning_tokens": observation.usage.reasoning_tokens,
                "cached_tokens": observation.usage.cached_tokens,
                "duration_ms": observation.duration_ms,
                "cost_kind": observation.cost_kind,
                "pricing_basis_version": observation.pricing_basis_version,
            },
        }
        if failure_type is not None:
            meta["failure_type"] = failure_type
        return meta

    def _validate_observation(
        self,
        task: TaskContract,
        document: Mapping[str, Any],
        observation: RawProviderObservation,
    ) -> ProviderResult:
        if document.get("web_search") not in (None, {}, []):
            raise ProviderProtocolError(
                "GLM response unexpectedly contained web search metadata"
            )
        returned_model = document.get("model")
        if returned_model != _FIXED_MODEL:
            raise ProviderProtocolError(
                "GLM response model did not match the fixed requested model"
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
        if not isinstance(usage, Mapping):
            raise ProviderProtocolError("GLM response usage must be an object")
        prompt_tokens = _non_negative_int(
            "prompt_tokens",
            observation.usage.input_tokens,
        )
        completion_tokens = _non_negative_int(
            "completion_tokens",
            observation.usage.output_tokens,
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
        cached_tokens = _non_negative_int(
            "cached_tokens",
            observation.usage.cached_tokens,
        )
        reasoning_tokens = _non_negative_int(
            "reasoning_tokens",
            observation.usage.reasoning_tokens,
        )
        list_cost = observation.currency_cost_usd
        assert list_cost is not None
        over_budget = list_cost > task.constraints.max_cost_usd
        response_id = document.get("id")
        if response_id is not None and not isinstance(response_id, str):
            raise ProviderProtocolError("GLM response id must be a string")
        warnings = [
            "Unverified GLM output; acceptance is separate.",
            "Cost uses conservative list pricing; the dated promotional estimate may be lower.",
        ]
        if over_budget:
            warnings.append("Estimated conservative provider cost exceeded max_cost_usd.")
        return ProviderResult(
            task_id=task.task_id,
            status=(
                ResultStatus.CANDIDATE_FAILURE
                if over_budget
                else ResultStatus.CANDIDATE_SUCCESS
            ),
            answer="" if over_budget else message["content"],
            cost=self._cost_from_observation(document, observation),
            warnings=tuple(warnings),
            provider_meta=self._provider_meta_from_observation(observation),
        )

    def invoke_observed(self, task: TaskContract) -> ProviderExecution:
        started = time.perf_counter()
        document = self._post_validated_task_once(task)
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        observation = self._observe_response(document, elapsed_ms)
        try:
            result = self._validate_observation(task, document, observation)
        except MacrError as exc:
            result = ProviderResult(
                task_id=task.task_id,
                status=ResultStatus.CANDIDATE_FAILURE,
                answer="",
                cost=self._cost_from_observation(document, observation),
                warnings=(str(exc),),
                provider_meta=self._provider_meta_from_observation(
                    observation,
                    failure_type=type(exc).__name__,
                ),
            )
        return ProviderExecution.from_observation(observation, result)

    def invoke(self, task: TaskContract) -> ProviderResult:
        return self.invoke_observed(task).result
