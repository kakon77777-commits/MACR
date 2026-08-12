from __future__ import annotations

from typing import Mapping

from ..config import ProviderConfig
from ..errors import ConfigurationError
from .openai_compatible import JsonTransport, OpenAICompatibleProvider


class MiniMaxProvider(OpenAICompatibleProvider):
    """MiniMax adapter with all endpoint and model values supplied externally."""

    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: JsonTransport | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        if config.kind != "minimax_openai_compatible":
            raise ConfigurationError(
                f"MiniMaxProvider requires kind=minimax_openai_compatible, got {config.kind}"
            )
        super().__init__(config, transport=transport, environ=environ)
