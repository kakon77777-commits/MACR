from __future__ import annotations

import unittest

from macr_runtime.config import ConnectionScope
from macr_runtime.contracts import ProviderResult, ResultStatus, TaskContract
from macr_runtime.execution import CaptureState, ProviderState
from macr_runtime.providers.base import BaseProvider, ProviderHealth


class LegacySuccessProvider(BaseProvider):
    provider_id = "legacy"
    connection_scope = ConnectionScope.EXTERNAL_HTTPS

    def health(self) -> ProviderHealth:
        return ProviderHealth(self.provider_id, True, "configured_offline")

    def invoke(self, task: TaskContract) -> ProviderResult:
        return ProviderResult(
            task_id=task.task_id,
            status=ResultStatus.CANDIDATE_SUCCESS,
            answer="candidate",
            cost={
                "usage": {
                    "prompt_tokens": 2,
                    "completion_tokens": 1,
                    "reasoning_tokens": 0,
                    "cached_tokens": 0,
                },
                "currency_cost_usd": 0.001,
            },
            provider_meta={"model": "legacy-model"},
        )


class ProviderExecutionCompatibilityTests(unittest.TestCase):
    def test_default_invoke_observed_wraps_legacy_provider_result(self) -> None:
        task = TaskContract(
            task_id="legacy-observed",
            goal="Return one candidate.",
            task_type="testing",
        )

        execution = LegacySuccessProvider().invoke_observed(task)

        self.assertEqual(execution.result.status, ResultStatus.CANDIDATE_SUCCESS)
        self.assertEqual(execution.observation.provider_state, ProviderState.COMPLETED)
        self.assertEqual(execution.observation.answer_bytes, b"candidate")
        self.assertEqual(execution.capture_state, CaptureState.CAPTURED)


if __name__ == "__main__":
    unittest.main()
