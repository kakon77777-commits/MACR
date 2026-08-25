from __future__ import annotations

from collections.abc import Iterable
from typing import Mapping

from .config import ProviderConfig
from .errors import ConfigurationError, ProviderUnavailableError
from .providers.base import BaseProvider
from .providers.disabled import DisabledProvider
from .providers.grok import GrokResponsesProvider
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
    ) -> "ProviderRegistry":
        transport_map = {} if transports is None else dict(transports)
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
            elif config.kind == "ollama_local_chat":
                providers.append(
                    OllamaChatProvider(
                        config,
                        environ=environ,
                        transport=transport_map.get(config.id),
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

    def health(self) -> tuple[dict[str, object], ...]:
        return tuple(
            self._providers[key].health().to_dict() for key in sorted(self._providers)
        )
