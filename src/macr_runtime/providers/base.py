from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..config import ConnectionScope
from ..contracts import ProviderResult, TaskContract


@dataclass(frozen=True)
class ProviderHealth:
    provider_id: str
    ready: bool
    status: str
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "ready": self.ready,
            "status": self.status,
            "detail": self.detail,
        }


class BaseProvider(ABC):
    provider_id: str
    connection_scope: ConnectionScope

    @abstractmethod
    def health(self) -> ProviderHealth:
        raise NotImplementedError

    @abstractmethod
    def invoke(self, task: TaskContract) -> ProviderResult:
        raise NotImplementedError
