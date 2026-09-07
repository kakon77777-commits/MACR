from __future__ import annotations

from typing import Mapping

from ..config import ProviderConfig
from ..contracts import TaskContract
from ..errors import ConfigurationError
from ..token_policy import ModelTokenPolicyResolver
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

    def _check_task_policy(self, task: TaskContract) -> None:
        super()._check_task_policy(task)
        model = self.config.resolve_model(self.environ)
        policy = ModelTokenPolicyResolver.builtins_only().resolve(
            self.provider_id,
            model,
        )
        if policy.connection_scope != self.connection_scope.value:
            raise ConfigurationError(
                "MiniMax token policy must match the configured connection scope"
            )
        policy.validate_task_output_tokens(task.constraints.max_output_tokens)
