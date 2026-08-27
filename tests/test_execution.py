from __future__ import annotations

import unittest

from macr_runtime.contracts import ProviderResult, ResultStatus
from macr_runtime.execution import (
    AcceptanceState,
    AuthorizationReference,
    CaptureState,
    DispatchContext,
    DispatchOrigin,
    InteractionPlane,
    MaterializationState,
    ProviderExecution,
    ProviderState,
    ProviderUsage,
    RawProviderObservation,
    ReturnContractState,
    VerificationState,
)


class ExecutionContractTests(unittest.TestCase):
    def test_public_observation_omits_raw_answer_bytes(self) -> None:
        observation = RawProviderObservation(
            provider_id="glm_flash_worker",
            model="glm-5.3-flash",
            response_id="response-1",
            finish_reason="length",
            usage=ProviderUsage(10, 20, 20, 0),
            currency_cost_usd=0.0000115,
            cost_kind="estimated",
            pricing_basis_version="zai-2026-08-27",
            duration_ms=100,
            answer_bytes=b"PRIVATE ANSWER",
            provider_state=ProviderState.INCOMPLETE,
        )

        public = observation.to_public_dict()

        self.assertNotIn("PRIVATE ANSWER", str(public))
        self.assertEqual(public["answer_bytes"], 14)
        self.assertEqual(len(public["answer_sha256"]), 64)
        self.assertEqual(public["provider_state"], "incomplete")

    def test_dispatch_context_keeps_origin_and_authority_distinct(self) -> None:
        context = DispatchContext(
            run_id="11111111-1111-4111-8111-111111111111",
            plane=InteractionPlane.DELEGATION,
            origin=DispatchOrigin("codex", "codex_thread_id", "thread-1"),
            authorization=AuthorizationReference(
                source_kind="cli_opt_in",
                source_id="authority-1",
                digest="a" * 64,
                revision=1,
                epoch=2,
                scope="provider:glm_flash_worker",
            ),
            policy_snapshot_sha256="b" * 64,
        )

        self.assertEqual(context.origin.native_id, "thread-1")
        self.assertEqual(context.authorization.epoch, 2)
        self.assertFalse(context.relay_is_authorship)

    def test_execution_lifecycle_fields_are_orthogonal(self) -> None:
        result = ProviderResult(
            task_id="observed-failure",
            status=ResultStatus.CANDIDATE_FAILURE,
        )
        execution = ProviderExecution(
            observation=RawProviderObservation.empty("glm_flash_worker"),
            result=result,
            capture_state=CaptureState.ABSENT,
            return_contract_state=ReturnContractState.NOT_EVALUATED,
            materialization_state=MaterializationState.NONE,
            verification_state=VerificationState.PENDING,
            acceptance_state=AcceptanceState.PENDING,
        )

        self.assertEqual(
            execution.observation.provider_state,
            ProviderState.MALFORMED,
        )
        self.assertEqual(execution.result.status, ResultStatus.CANDIDATE_FAILURE)

    def test_from_result_preserves_answer_privately_and_normalizes_usage(self) -> None:
        result = ProviderResult(
            task_id="observed-success",
            status=ResultStatus.CANDIDATE_SUCCESS,
            answer="candidate",
            cost={
                "usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 3,
                    "reasoning_tokens": 1,
                    "cached_tokens": 0,
                },
                "currency_cost_usd": 0.00000255,
                "cost_kind": "estimated",
                "pricing_basis_version": "test-v1",
            },
            provider_meta={
                "model": "test-model",
                "response_id": "response-1",
                "finish_reason": "stop",
            },
        )

        execution = ProviderExecution.from_result("test-provider", result)

        self.assertEqual(execution.observation.answer_bytes, b"candidate")
        self.assertEqual(execution.observation.usage.input_tokens, 7)
        self.assertEqual(execution.capture_state, CaptureState.CAPTURED)

    def test_invalid_hash_and_relay_authorship_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "authorization digest"):
            AuthorizationReference(
                source_kind="test",
                source_id="authority-1",
                digest="bad",
                revision=1,
                epoch=1,
                scope="provider:test",
            )

        with self.assertRaisesRegex(ValueError, "relay_is_authorship"):
            DispatchContext(
                run_id="11111111-1111-4111-8111-111111111111",
                plane=InteractionPlane.DELEGATION,
                origin=DispatchOrigin("test", "process_id", "1234"),
                authorization=AuthorizationReference(
                    source_kind="test",
                    source_id="authority-1",
                    digest="a" * 64,
                    revision=1,
                    epoch=1,
                    scope="provider:test",
                ),
                policy_snapshot_sha256="b" * 64,
                relay_is_authorship=True,
            )


if __name__ == "__main__":
    unittest.main()
