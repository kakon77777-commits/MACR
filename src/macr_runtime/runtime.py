from __future__ import annotations

from .contracts import ProviderResult, ResultStatus, TaskContract
from .errors import MacrError
from .ledger import AppendOnlyLedger
from .registry import ProviderRegistry


class MacrRuntime:
    def __init__(self, registry: ProviderRegistry, ledger: AppendOnlyLedger) -> None:
        self.registry = registry
        self.ledger = ledger

    def invoke(self, provider_id: str, task: TaskContract) -> ProviderResult:
        dispatch = self.ledger.append(
            "provider.dispatch_requested",
            {
                "provider_id": provider_id,
                "task_id": task.task_id,
                "task_type": task.task_type,
                "privacy": task.constraints.privacy.value,
            },
        )
        try:
            result = self.registry.get(provider_id).invoke(task)
        except MacrError as exc:
            result = ProviderResult(
                task_id=task.task_id,
                status=ResultStatus.CANDIDATE_FAILURE,
                warnings=(str(exc),),
                provider_meta={
                    "provider": provider_id,
                    "dispatch_event_id": dispatch["event_id"],
                    "failure_type": type(exc).__name__,
                },
            )
        except Exception as exc:
            result = ProviderResult(
                task_id=task.task_id,
                status=ResultStatus.CANDIDATE_FAILURE,
                warnings=(
                    "Unexpected provider failure; no candidate was accepted. "
                    "The exception message was omitted to avoid reflecting sensitive data.",
                ),
                provider_meta={
                    "provider": provider_id,
                    "dispatch_event_id": dispatch["event_id"],
                    "failure_type": type(exc).__name__,
                },
            )
        self.ledger.append(
            "provider.candidate_completed",
            {
                "provider_id": provider_id,
                "task_id": task.task_id,
                "dispatch_event_id": dispatch["event_id"],
                "status": result.status.value,
                "response_id": result.provider_meta.get("response_id"),
            },
        )
        return result
