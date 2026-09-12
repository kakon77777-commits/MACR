from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Mapping

from .config import ProviderConfig
from .errors import ConfigurationError, ProviderPolicyError, ProviderUnavailableError
from .model_token_store import ModelTokenPolicyStore
from .provider_capability import ProviderTierBinding
from .provider_capability_store import ProviderCapabilityPolicyStore
from .provider_admission import (
    ProviderAdmissionDirectory,
    ProviderAdmissionKernel,
)
from .providers.base import BaseProvider
from .providers.disabled import DisabledProvider
from .providers.grok import GrokResponsesProvider
from .providers.glm import GlmFlashWorkerProvider
from .providers.google_gemini import GoogleGeminiProvider
from .providers.google_image import GoogleImageProvider
from .providers.minimax import MiniMaxProvider
from .providers.ollama import OllamaChatProvider
from .providers.http_json import JsonTransport
from .token_policy import ModelTokenPolicy, ModelTokenPolicyResolver


_MODEL_TOKEN_POLICY_KINDS = frozenset(
    {
        "minimax_openai_compatible",
        "grok_responses",
        "zai_glm_worker",
        "ollama_local_chat",
        "google_vertex_gemini",
    }
)


class ProviderRegistry:
    def __init__(self, providers: Iterable[BaseProvider]) -> None:
        self._providers = {provider.provider_id: provider for provider in providers}
        if not self._providers:
            raise ConfigurationError("provider registry must not be empty")
        self._token_policy_resolver = ModelTokenPolicyResolver.builtins_only()

    @classmethod
    def from_configs(
        cls,
        configs: Iterable[ProviderConfig],
        *,
        environ: Mapping[str, str] | None = None,
        transports: Mapping[str, JsonTransport] | None = None,
        key_sources: Mapping[str, Any] | None = None,
        token_policy_store: ModelTokenPolicyStore | None = None,
        capability_policy_store: ProviderCapabilityPolicyStore | None = None,
        provider_admission_kernel: ProviderAdmissionKernel | None = None,
        provider_admission_directory: ProviderAdmissionDirectory | None = None,
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
                admission_guard = (
                    provider_admission_directory.get(config.id)
                    if provider_admission_directory is not None
                    and config.id == "grok"
                    else None
                )
                providers.append(
                    GrokResponsesProvider(
                        config,
                        environ=environ,
                        transport=transport_map.get(config.id),
                        admission_guard=admission_guard,
                    )
                )
            elif config.kind == "zai_glm_worker":
                if config.model is None:
                    raise ConfigurationError(
                        "GLM worker requires an exact configured model"
                    )
                token_policy = (
                    token_policy_store.effective_policy(config.id, config.model)
                    if token_policy_store is not None
                    else None
                )
                capability_policy = (
                    capability_policy_store.effective_policy(
                        config.id,
                        config.model,
                    )
                    if capability_policy_store is not None
                    else None
                )
                providers.append(
                    GlmFlashWorkerProvider(
                        config,
                        environ=environ,
                        transport=transport_map.get(config.id),
                        key_source=key_source_map.get(config.id),
                        token_policy=token_policy,
                        capability_policy=capability_policy,
                        admission_guard=(
                            provider_admission_directory.get(config.id)
                            if provider_admission_directory is not None
                            else provider_admission_kernel
                        ),
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
        direct_model = getattr(provider, "model", None)
        if isinstance(direct_model, str) and direct_model.strip():
            return direct_model.strip()
        config = getattr(provider, "config", None)
        model = getattr(config, "model", None)
        if isinstance(model, str) and model.strip():
            return model.strip()
        environ = getattr(provider, "environ", None)
        if isinstance(config, ProviderConfig) and isinstance(environ, Mapping):
            try:
                return config.resolve_model(environ)
            except ConfigurationError:
                return None
        return None

    def token_policy(
        self,
        provider_id: str,
        *,
        store: ModelTokenPolicyStore | None = None,
    ) -> ModelTokenPolicy:
        provider = self.get(provider_id)
        explicit = getattr(provider, "token_policy", None)
        if (
            isinstance(explicit, ModelTokenPolicy)
            and getattr(provider, "token_policy_is_explicit", False)
        ):
            return explicit
        model = self.requested_model(provider_id)
        if model is None:
            raise ProviderPolicyError(
                "provider exact model is unavailable for token policy"
            )
        if store is not None:
            return store.effective_policy(provider_id, model)
        if isinstance(explicit, ModelTokenPolicy):
            return explicit
        return self._token_policy_resolver.resolve(provider_id, model)

    def requires_model_token_policy(self, provider_id: str) -> bool:
        provider = self.get(provider_id)
        config = getattr(provider, "config", None)
        if isinstance(config, ProviderConfig):
            return config.kind in _MODEL_TOKEN_POLICY_KINDS
        return self.requested_model(provider_id) is not None

    def capability_binding(self, provider_id: str) -> ProviderTierBinding:
        provider = self.get(provider_id)
        binding = getattr(provider, "capability_binding", None)
        if not isinstance(binding, ProviderTierBinding):
            raise ProviderPolicyError(
                "provider has no exact capability tier binding"
            )
        return binding

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
