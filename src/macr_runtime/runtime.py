from __future__ import annotations

from .contracts import ProviderResult, ResultStatus, TaskContract
from .errors import MacrError
from .ledger import AppendOnlyLedger
from .registry import ProviderRegistry


_LEDGER_METRIC_KEYS = (
    "model",
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "cached_tokens",
    "currency_cost_usd",
    "duration_ms",
    "input_media_count",
    "input_media_bytes",
    "output_artifact_count",
    "output_artifact_bytes",
    "cost_kind",
    "pricing_basis_version",
)


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
                "delegable": task.delegable,
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
        raw_metrics = result.provider_meta.get("metrics")
        metrics = raw_metrics if isinstance(raw_metrics, dict) else {}
        completion_payload = {
            "provider_id": provider_id,
            "task_id": task.task_id,
            "dispatch_event_id": dispatch["event_id"],
            "status": result.status.value,
            "response_id": result.provider_meta.get("response_id"),
            "model": result.provider_meta.get("model"),
            "input_tokens": metrics.get("input_tokens"),
            "output_tokens": metrics.get("output_tokens"),
            "reasoning_tokens": metrics.get("reasoning_tokens"),
            "cached_tokens": metrics.get("cached_tokens"),
            "currency_cost_usd": result.cost.get("currency_cost_usd"),
            "duration_ms": metrics.get("duration_ms"),
            "input_media_count": metrics.get("input_media_count"),
            "input_media_bytes": metrics.get("input_media_bytes"),
            "output_artifact_count": metrics.get("output_artifact_count"),
            "output_artifact_bytes": metrics.get("output_artifact_bytes"),
            "cost_kind": metrics.get("cost_kind"),
            "pricing_basis_version": metrics.get("pricing_basis_version"),
        }
        assert all(key in completion_payload for key in _LEDGER_METRIC_KEYS)
        self.ledger.append("provider.candidate_completed", completion_payload)
        return result
