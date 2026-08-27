from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from .contracts import PrivacyLevel
from .errors import ConfigurationError


_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_REASONING_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})


def _boolean(data: Mapping[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigurationError(f"provider {key} must be boolean")
    return value


def _required_string(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"provider {key} must be a non-empty string")
    return value.strip()


def _optional_string(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"provider {key} must be a non-empty string when present")
    return value.strip()


def _string_array(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key, ())
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ConfigurationError(f"provider {key} must be an array")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ConfigurationError(f"provider {key} entries must be non-empty strings")
        normalized.append(item.strip())
    return tuple(normalized)


class AuthMode(str, Enum):
    API_KEY = "api_key"
    SERVICE_ACCOUNT = "service_account"
    SUBSCRIPTION_CLIENT = "subscription_client"
    PENDING = "pending"
    NONE = "none"


class ConnectionScope(str, Enum):
    EXTERNAL_HTTPS = "external_https"
    LOOPBACK_HTTP = "loopback_http"
    DISABLED = "disabled"


@dataclass(frozen=True)
class ProviderConfig:
    id: str
    kind: str
    enabled: bool
    auth_mode: AuthMode
    api_usage_allowed: bool
    connection_scope: ConnectionScope = ConnectionScope.DISABLED
    api_key_env: str | None = None
    credential_path_env: str | None = None
    project_env: str | None = None
    base_url: str | None = None
    base_url_env: str | None = None
    model: str | None = None
    model_env: str | None = None
    location: str | None = None
    endpoint_path: str = "/chat/completions"
    allowed_hosts: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    approved_privacy: tuple[str, ...] = ()
    reasoning_effort: str | None = None
    disabled_reason: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ConfigurationError("provider id must be non-empty")
        if not self.kind or not self.kind.strip():
            raise ConfigurationError(f"provider {self.id} kind must be non-empty")
        if not isinstance(self.enabled, bool) or not isinstance(self.api_usage_allowed, bool):
            raise ConfigurationError(f"provider {self.id} policy flags must be boolean")
        if not isinstance(self.auth_mode, AuthMode):
            raise ConfigurationError(f"provider {self.id} auth_mode is invalid")
        if not isinstance(self.connection_scope, ConnectionScope):
            raise ConfigurationError(f"provider {self.id} connection_scope is invalid")
        if self.base_url and self.base_url_env:
            raise ConfigurationError(
                f"provider {self.id} may not define both base_url and base_url_env"
            )
        if self.model and self.model_env:
            raise ConfigurationError(
                f"provider {self.id} may not define both model and model_env"
            )
        if self.reasoning_effort is not None and self.reasoning_effort not in _REASONING_EFFORTS:
            raise ConfigurationError(f"provider {self.id} reasoning_effort is invalid")
        if self.enabled and self.connection_scope is ConnectionScope.DISABLED:
            raise ConfigurationError(
                f"provider {self.id} enabled provider cannot use disabled scope"
            )

        for env_name in (
            self.api_key_env,
            self.credential_path_env,
            self.project_env,
            self.base_url_env,
            self.model_env,
        ):
            if env_name and not _ENV_NAME.fullmatch(env_name):
                raise ConfigurationError(
                    f"provider {self.id} environment variable name is invalid: {env_name}"
                )

        normalized_hosts = tuple(host.lower() for host in self.allowed_hosts)
        if any(
            not host
            or ":" in host
            or "/" in host
            or host.startswith(".")
            or host.endswith(".")
            for host in normalized_hosts
        ):
            raise ConfigurationError(f"provider {self.id} allowed_hosts contains an invalid host")
        if len(normalized_hosts) != len(set(normalized_hosts)):
            raise ConfigurationError(f"provider {self.id} allowed_hosts contains duplicates")
        object.__setattr__(self, "allowed_hosts", normalized_hosts)

        if len(self.capabilities) != len(set(self.capabilities)):
            raise ConfigurationError(f"provider {self.id} capabilities contains duplicates")
        valid_privacy = {item.value for item in PrivacyLevel}
        if len(self.approved_privacy) != len(set(self.approved_privacy)):
            raise ConfigurationError(f"provider {self.id} approved_privacy contains duplicates")
        invalid_privacy = sorted(set(self.approved_privacy) - valid_privacy)
        if invalid_privacy:
            raise ConfigurationError(
                f"provider {self.id} approved_privacy is invalid: {', '.join(invalid_privacy)}"
            )

        if (
            not isinstance(self.endpoint_path, str)
            or not self.endpoint_path.startswith("/")
            or self.endpoint_path.startswith("//")
            or ".." in self.endpoint_path.split("/")
            or "?" in self.endpoint_path
            or "#" in self.endpoint_path
        ):
            raise ConfigurationError(f"provider {self.id} endpoint_path must be an absolute safe path")

        if self.connection_scope is ConnectionScope.EXTERNAL_HTTPS and not normalized_hosts:
            raise ConfigurationError(f"provider {self.id} external scope needs allowed_hosts")
        if self.connection_scope is ConnectionScope.LOOPBACK_HTTP:
            if self.auth_mode is not AuthMode.NONE:
                raise ConfigurationError(
                    f"provider {self.id} loopback scope must use auth_mode none"
                )
            if self.api_key_env:
                raise ConfigurationError(
                    f"provider {self.id} loopback scope may not use an API key"
                )

        if self.enabled:
            missing: list[str] = []
            if self.auth_mode is AuthMode.API_KEY and not self.api_key_env:
                missing.append("api_key_env")
            if self.auth_mode is AuthMode.SERVICE_ACCOUNT:
                if not self.credential_path_env:
                    missing.append("credential_path_env")
                if not self.project_env:
                    missing.append("project_env")
                if self.api_key_env:
                    raise ConfigurationError(
                        f"provider {self.id} service-account auth may not use api_key_env"
                    )
            if not self.base_url and not self.base_url_env:
                missing.append("base_url or base_url_env")
            if not self.model and not self.model_env:
                missing.append("model or model_env")
            if missing:
                raise ConfigurationError(
                    f"provider {self.id} is enabled but lacks {', '.join(missing)}"
                )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProviderConfig":
        try:
            return cls(
                id=_required_string(data, "id"),
                kind=_required_string(data, "kind"),
                enabled=_boolean(data, "enabled", False),
                auth_mode=AuthMode(str(data.get("auth_mode", "none"))),
                api_usage_allowed=_boolean(data, "api_usage_allowed", False),
                connection_scope=ConnectionScope(
                    str(data.get("connection_scope", ConnectionScope.DISABLED.value))
                ),
                api_key_env=_optional_string(data, "api_key_env"),
                credential_path_env=_optional_string(data, "credential_path_env"),
                project_env=_optional_string(data, "project_env"),
                base_url=_optional_string(data, "base_url"),
                base_url_env=_optional_string(data, "base_url_env"),
                model=_optional_string(data, "model"),
                model_env=_optional_string(data, "model_env"),
                location=_optional_string(data, "location"),
                endpoint_path=str(data.get("endpoint_path", "/chat/completions")),
                allowed_hosts=_string_array(data, "allowed_hosts"),
                capabilities=_string_array(data, "capabilities"),
                approved_privacy=_string_array(data, "approved_privacy"),
                reasoning_effort=_optional_string(data, "reasoning_effort"),
                disabled_reason=_optional_string(data, "disabled_reason"),
                notes=str(data.get("notes", "")),
            )
        except ConfigurationError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError(f"invalid provider configuration: {exc}") from exc

    def required_environment(self) -> tuple[str, ...]:
        return tuple(
            value
            for value in (
                self.api_key_env,
                self.credential_path_env,
                self.project_env,
                self.base_url_env,
                self.model_env,
            )
            if value
        )

    def resolve_base_url(self, environ: Mapping[str, str]) -> str:
        value = self.base_url or (
            environ.get(self.base_url_env, "") if self.base_url_env else ""
        )
        if not value.strip():
            raise ConfigurationError(f"provider {self.id} base URL is not configured")
        value = value.strip()
        parsed = urlparse(value)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ConfigurationError(
                f"provider {self.id} base URL contains forbidden components"
            )
        hostname = parsed.hostname.lower() if parsed.hostname else ""
        if self.connection_scope is ConnectionScope.EXTERNAL_HTTPS:
            if parsed.scheme != "https" or not parsed.netloc:
                raise ConfigurationError(
                    f"provider {self.id} external base URL must use HTTPS"
                )
            if hostname not in self.allowed_hosts:
                raise ConfigurationError(
                    f"provider {self.id} base URL host is not allowlisted"
                )
        if self.connection_scope is ConnectionScope.LOOPBACK_HTTP:
            if parsed.scheme != "http" or hostname != "127.0.0.1":
                raise ConfigurationError(
                    f"provider {self.id} loopback base URL is invalid"
                )
        return value

    def resolve_model(self, environ: Mapping[str, str]) -> str:
        value = self.model or (
            environ.get(self.model_env, "") if self.model_env else ""
        )
        if not value.strip():
            raise ConfigurationError(f"provider {self.id} model is not configured")
        return value.strip()

    def public_summary(self, environ: Mapping[str, str]) -> dict[str, Any]:
        required_env = self.required_environment()
        return {
            "id": self.id,
            "kind": self.kind,
            "enabled": self.enabled,
            "auth_mode": self.auth_mode.value,
            "api_usage_allowed": self.api_usage_allowed,
            "connection_scope": self.connection_scope.value,
            "base_url": self.base_url,
            "model": self.model,
            "location": self.location,
            "reasoning_effort": self.reasoning_effort,
            "allowed_hosts": list(self.allowed_hosts),
            "capabilities": list(self.capabilities),
            "required_environment": list(required_env),
            "environment_present": {name: bool(environ.get(name)) for name in required_env},
            "disabled_reason": self.disabled_reason,
        }


def load_provider_configs(path: str | Path) -> tuple[ProviderConfig, ...]:
    config_path = Path(path)
    try:
        document = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"cannot load provider config {config_path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ConfigurationError("providers.json root must be an object")
    schema_version = document.get("schema_version")
    if schema_version == 1:
        raise ConfigurationError("providers.json schema_version 1 must migrate to 2")
    if schema_version != 2:
        raise ConfigurationError("providers.json schema_version must be 2")
    raw = document.get("providers")
    if not isinstance(raw, list):
        raise ConfigurationError("providers.json providers must be an array")
    if any(not isinstance(item, Mapping) for item in raw):
        raise ConfigurationError("providers.json provider entries must be objects")
    configs = tuple(ProviderConfig.from_dict(item) for item in raw)
    ids = [item.id for item in configs]
    if len(ids) != len(set(ids)):
        raise ConfigurationError("provider ids must be unique")
    return configs
