from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from .errors import ConfigurationError
from .contracts import PrivacyLevel


_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
    SUBSCRIPTION_CLIENT = "subscription_client"
    PENDING = "pending"
    NONE = "none"


def _optional_string(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"provider {key} must be a non-empty string when present")
    return value.strip()


@dataclass(frozen=True)
class ProviderConfig:
    id: str
    kind: str
    enabled: bool
    auth_mode: AuthMode
    api_usage_allowed: bool
    api_key_env: str | None = None
    base_url_env: str | None = None
    model_env: str | None = None
    endpoint_path: str = "/chat/completions"
    allowed_hosts: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    approved_privacy: tuple[str, ...] = ()
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
        if self.enabled and self.auth_mode is AuthMode.API_KEY:
            missing = [
                name
                for name, value in (
                    ("api_key_env", self.api_key_env),
                    ("base_url_env", self.base_url_env),
                    ("model_env", self.model_env),
                    ("allowed_hosts", self.allowed_hosts),
                )
                if not value
            ]
            if missing:
                raise ConfigurationError(
                    f"provider {self.id} is enabled but lacks {', '.join(missing)}"
                )
        for env_name in (self.api_key_env, self.base_url_env, self.model_env):
            if env_name and not _ENV_NAME.fullmatch(env_name):
                raise ConfigurationError(
                    f"provider {self.id} environment variable name is invalid: {env_name}"
                )
        if len(self.capabilities) != len(set(self.capabilities)):
            raise ConfigurationError(f"provider {self.id} capabilities contains duplicates")
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

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProviderConfig":
        try:
            return cls(
                id=_required_string(data, "id"),
                kind=_required_string(data, "kind"),
                enabled=_boolean(data, "enabled", False),
                auth_mode=AuthMode(str(data.get("auth_mode", "none"))),
                api_usage_allowed=_boolean(data, "api_usage_allowed", False),
                api_key_env=_optional_string(data, "api_key_env"),
                base_url_env=_optional_string(data, "base_url_env"),
                model_env=_optional_string(data, "model_env"),
                endpoint_path=str(data.get("endpoint_path", "/chat/completions")),
                allowed_hosts=_string_array(data, "allowed_hosts"),
                capabilities=_string_array(data, "capabilities"),
                approved_privacy=_string_array(data, "approved_privacy"),
                disabled_reason=_optional_string(data, "disabled_reason"),
                notes=str(data.get("notes", "")),
            )
        except ConfigurationError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError(f"invalid provider configuration: {exc}") from exc

    def public_summary(self, environ: Mapping[str, str]) -> dict[str, Any]:
        required_env = tuple(
            value for value in (self.api_key_env, self.base_url_env, self.model_env) if value
        )
        return {
            "id": self.id,
            "kind": self.kind,
            "enabled": self.enabled,
            "auth_mode": self.auth_mode.value,
            "api_usage_allowed": self.api_usage_allowed,
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
    if document.get("schema_version") != 1:
        raise ConfigurationError("providers.json schema_version must be 1")
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
