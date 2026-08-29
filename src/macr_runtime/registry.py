from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Mapping

from .config import ProviderConfig
from .errors import ConfigurationError, ProviderUnavailableError
from .providers.base import BaseProvider
from .providers.disabled import DisabledProvider
from .providers.grok import GrokResponsesProvider
from .providers.glm import GlmFlashWorkerProvider
from .providers.google_gemini import GoogleGeminiProvider
from .providers.google_image import GoogleImageProvider
from .providers.minimax import MiniMaxProvider
from .providers.ollama import OllamaChatProvider
from .providers.http_json import JsonTransport


class ProviderRegistry:
    def __init__(self, providers: Iterable[BaseProvider]) -> None:
        self._providers = {provider.provider_id: provider for provider in providers}
        if not self._providers:
            raise ConfigurationError("provider registry must not be empty")

    @classmethod
    def from_configs(
        cls,
        configs: Iterable[ProviderConfig],
        *,
        environ: Mapping[str, str] | None = None,
        transports: Mapping[str, JsonTransport] | None = None,
        key_sources: Mapping[str, Any] | None = None,
    ) -> "ProviderRegistry":
        transport_map = {} if transports is None else dict(transports)
        key_source_map = {} if key_sources is None else dict(key_sources)
        providers: list[BaseProvider] = []
        for config in configs:
            if config.kind == "minimax_openai_compatible":
                providers.append(
                    MiniMaxProvider(
                        config,
                        environ=environ,
                        transport=transport_map.get(config.id),
                    )
                )
            elif config.kind == "grok_responses":
                providers.append(
                    GrokResponsesProvider(
                        config,
                        environ=environ,
                        transport=transport_map.get(config.id),
                    )
                )
            elif config.kind == "zai_glm_worker":
                providers.append(
                    GlmFlashWorkerProvider(
                        config,
                        environ=environ,
                        transport=transport_map.get(config.id),
                        key_source=key_source_map.get(config.id),
                    )
                )
            elif config.kind == "ollama_local_chat":
                providers.append(
                    OllamaChatProvider(
                        config,
                        environ=environ,
                        transport=transport_map.get(config.id),
                    )
                )
            elif config.kind == "google_vertex_gemini":
                providers.append(
                    GoogleGeminiProvider(
                        config,
                        environ=environ,
                    )
                )
            elif config.kind == "google_vertex_image":
                providers.append(
                    GoogleImageProvider(
                        config,
                        environ=environ,
                    )
                )
            elif not config.enabled:
                providers.append(DisabledProvider(config))
            else:
                raise ConfigurationError(
                    f"enabled provider {config.id} uses unsupported kind {config.kind}"
                )
        return cls(providers)

    def get(self, provider_id: str) -> BaseProvider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise ProviderUnavailableError(f"unknown provider: {provider_id}") from exc

    def requested_model(self, provider_id: str) -> str | None:
        provider = self.get(provider_id)
        config = getattr(provider, "config", None)
        model = getattr(config, "model", None)
        return model if isinstance(model, str) and model.strip() else None

    def execution_profile(self, provider_id: str) -> dict[str, object]:
        provider = self.get(provider_id)
        config = getattr(provider, "config", None)
        if not isinstance(config, ProviderConfig):
            raise ProviderUnavailableError(
                f"provider has no static execution profile: {provider_id}"
            )
        return {
            "provider_id": config.id,
            "kind": config.kind,
            "enabled": config.enabled,
            "api_usage_allowed": config.api_usage_allowed,
            "connection_scope": config.connection_scope.value,
            "base_url": config.base_url,
            "endpoint_path": config.endpoint_path,
            "model": config.model,
        }

    def health(self) -> tuple[dict[str, object], ...]:
        return tuple(
            self._providers[key].health().to_dict() for key in sorted(self._providers)
        )
