from __future__ import annotations

import importlib.util
import os
from pathlib import Path, PureWindowsPath
from typing import Mapping

from ..config import AuthMode, ConnectionScope, ProviderConfig
from ..contracts import TaskContract
from ..errors import (
    ConfigurationError,
    ProviderPolicyError,
    ProviderUnavailableError,
    StoragePolicyError,
)
from ..google_credentials import inspect_service_account
from ..google_media import ValidatedMediaInput, validate_google_media_inputs
from .base import BaseProvider, ProviderHealth
from .google_core import GoogleSdkTransport, GoogleTransport


GOOGLE_VERTEX_BASE_URL = "https://aiplatform.googleapis.com"


class BaseGoogleProvider(BaseProvider):
    def __init__(
        self,
        config: ProviderConfig,
        *,
        expected_kind: str,
        transport: GoogleTransport | None = None,
        environ: Mapping[str, str] | None = None,
        cwd: str | Path | None = None,
    ) -> None:
        if config.kind != expected_kind:
            raise ConfigurationError(
                f"Google provider requires kind={expected_kind}"
            )
        self.config = config
        self.provider_id = config.id
        self.connection_scope = config.connection_scope
        self.environ = os.environ if environ is None else environ
        self.cwd = Path.cwd() if cwd is None else Path(cwd)
        self.transport = transport or GoogleSdkTransport(
            config,
            environ=self.environ,
        )

    def _environment_value(self, name: str | None) -> str:
        value = self.environ.get(name, "").strip() if name else ""
        if not value:
            raise ProviderUnavailableError(
                f"provider {self.provider_id} is missing environment variable {name}"
            )
        return value

    def _validate_offline_configuration(self) -> None:
        if self.config.auth_mode is not AuthMode.SERVICE_ACCOUNT:
            raise ConfigurationError(
                f"provider {self.provider_id} must use service-account authentication"
            )
        if self.config.connection_scope is not ConnectionScope.EXTERNAL_HTTPS:
            raise ConfigurationError(
                f"provider {self.provider_id} must use external HTTPS"
            )
        if self.config.resolve_base_url(self.environ) != GOOGLE_VERTEX_BASE_URL:
            raise ConfigurationError(
                f"provider {self.provider_id} Google base URL is invalid"
            )
        self.config.resolve_model(self.environ)
        if self.config.location != "global":
            raise ConfigurationError(
                f"provider {self.provider_id} Google location must be global"
            )
        credential_path = self._environment_value(self.config.credential_path_env)
        self._environment_value(self.config.project_env)
        windows = PureWindowsPath(credential_path)
        if not windows.is_absolute() or windows.drive.upper() != "D:":
            raise ProviderUnavailableError(
                f"provider {self.provider_id} credential path must be on D:"
            )
        try:
            inspect_service_account(credential_path)
        except (OSError, StoragePolicyError) as exc:
            raise ProviderUnavailableError(
                f"provider {self.provider_id} credential file is unavailable or invalid"
            ) from exc
        if importlib.util.find_spec("google.genai") is None:
            raise ProviderUnavailableError("google-genai dependency is unavailable")
        if importlib.util.find_spec("PIL") is None:
            raise ProviderUnavailableError("Pillow dependency is unavailable")

    def health(self) -> ProviderHealth:
        if not self.config.enabled:
            return ProviderHealth(self.provider_id, False, "disabled")
        if not self.config.api_usage_allowed:
            return ProviderHealth(
                self.provider_id,
                False,
                "policy_denied",
                "Google API use is forbidden",
            )
        try:
            self._validate_offline_configuration()
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
            "offline configuration checks passed; Google was not contacted",
        )

    def _check_task_policy(self, task: TaskContract) -> None:
        if not self.config.enabled:
            raise ProviderPolicyError(f"provider {self.provider_id} is disabled")
        if not self.config.api_usage_allowed:
            raise ProviderPolicyError(
                f"API use is forbidden for provider {self.provider_id}"
            )
        if self.config.auth_mode is not AuthMode.SERVICE_ACCOUNT:
            raise ProviderPolicyError(
                f"provider {self.provider_id} must use service-account authentication"
            )
        if not task.constraints.internet:
            raise ProviderPolicyError(
                "Google task contract must permit internet access"
            )
        if task.constraints.privacy.value not in self.config.approved_privacy:
            raise ProviderPolicyError(
                f"provider {self.provider_id} is not approved for privacy level "
                f"{task.constraints.privacy.value}"
            )
        if task.constraints.max_cost_usd <= 0:
            raise ProviderPolicyError(
                "Google dispatch requires a positive max_cost_usd"
            )
        if task.constraints.max_latency_s <= 0:
            raise ProviderPolicyError(
                "Google dispatch requires a positive max_latency_s"
            )
        missing = sorted(
            set(task.required_capabilities) - set(self.config.capabilities)
        )
        if missing:
            raise ProviderPolicyError(
                f"provider {self.provider_id} lacks required capabilities: "
                f"{', '.join(missing)}"
            )

    def _validated_media(
        self,
        task: TaskContract,
    ) -> tuple[ValidatedMediaInput, ...]:
        return validate_google_media_inputs(task, cwd=self.cwd)

    @staticmethod
    def _timeout_s(task: TaskContract) -> float:
        return max(0.001, min(task.constraints.max_latency_s, 3600.0))
