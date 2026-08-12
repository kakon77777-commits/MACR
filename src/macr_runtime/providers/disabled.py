from __future__ import annotations

from ..config import ProviderConfig
from ..contracts import ProviderResult, TaskContract
from ..errors import ProviderPolicyError
from .base import BaseProvider, ProviderHealth


class DisabledProvider(BaseProvider):
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.provider_id = config.id

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_id=self.provider_id,
            ready=False,
            status="disabled",
            detail=self.config.disabled_reason or "provider is disabled",
        )

    def invoke(self, task: TaskContract) -> ProviderResult:
        del task
        raise ProviderPolicyError(
            f"provider {self.provider_id} is disabled: "
            f"{self.config.disabled_reason or 'no reason recorded'}"
        )
