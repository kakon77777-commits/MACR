from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta, timezone

from macr_runtime.authority import AuthorityScope
from macr_runtime.config import AuthMode, ConnectionScope, ProviderConfig
from macr_runtime.contracts import (
    DelegationClass,
    ImportMode,
    PrivacyLevel,
    ProviderResult,
    ResultStatus,
    TaskConstraints,
    TaskContract,
    TaskPolicyClauses,
    RequiredImport,
)
from macr_runtime.execution import DispatchContext, DispatchOrigin, InteractionPlane
from macr_runtime.registry import ProviderRegistry
from macr_runtime.runtime import MacrRuntime
from macr_runtime.providers.base import BaseProvider, ProviderHealth
from macr_runtime.errors import TaskContradictionError

from tests.support import build_test_services, d_drive_tempdir
from tests.test_minimax_provider import FakeTransport


class ExplodingTransport:
    def post_json(self, url, *, headers, payload, timeout_s):
        del url, headers, payload, timeout_s
        raise RuntimeError("simulated transport implementation crash")


class FixedResultProvider(BaseProvider):
    provider_id = "grok"
    connection_scope = ConnectionScope.EXTERNAL_HTTPS

    def health(self):
        return ProviderHealth("grok", True, "configured_offline")

    def invoke(self, task):
        return ProviderResult(
            task_id=task.task_id,
            status=ResultStatus.CANDIDATE_SUCCESS,
            answer="PRIVATE ANSWER",
            cost={"currency_cost_usd": 0.00025},
            provider_meta={
                "provider": "grok",
                "model": "grok-4.6",
                "response_id": "resp-private-1",
                "metrics": {
                    "input_tokens": 20,
                    "output_tokens": 10,
                    "reasoning_tokens": 6,
                    "cached_tokens": 0,
                    "duration_ms": None,
                },
            },
        )


class GoogleFixedResultProvider(BaseProvider):
    provider_id = "google_image"
    connection_scope = ConnectionScope.EXTERNAL_HTTPS

    def health(self):
        return ProviderHealth("google_image", True, "configured_offline")

    def invoke(self, task):
        return ProviderResult(
            task_id=task.task_id,
            status=ResultStatus.CANDIDATE_SUCCESS,
            answer="PRIVATE GOOGLE ANSWER",
            artifacts=(
                {
                    "relative_path": "artifacts/google/private-file.jpg",
                    "mime_type": "image/jpeg",
                    "sha256": "abc",
                },
            ),
            cost={
                "currency_cost_usd": 0.067,
                "cost_kind": "estimated",
                "pricing_basis_version": "2026-08-26",
            },
            provider_meta={
                "provider": "google_image",
                "model": "gemini-3.1-flash-image",
                "response_id": "google-private-response",
                "metrics": {
                    "input_tokens": 20,
                    "output_tokens": 1120,
                    "reasoning_tokens": 0,
                    "cached_tokens": 0,
                    "duration_ms": None,
                    "input_media_count": 1,
                    "input_media_bytes": 1024,
                    "output_artifact_count": 1,
                    "output_artifact_bytes": 2048,
                    "cost_kind": "estimated",
                    "pricing_basis_version": "2026-08-26",
                },
            },
        )


def invoke_authorized(registry, services, provider_id, task):
    reference = services.authorities.issue(
        source_kind="test",
        source_id=f"{provider_id}:{task.task_id}:{uuid.uuid4()}",
        scope=AuthorityScope(
            providers=(provider_id,),
            planes=(InteractionPlane.DELEGATION.value,),
            task_types=(task.task_type,),
        ),
        expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    )
    context = DispatchContext(
        run_id=str(uuid.uuid4()),
        plane=InteractionPlane.DELEGATION,
        origin=DispatchOrigin("test", "process_id", "1234"),
        authorization=reference,
        policy_snapshot_sha256="a" * 64,
    )
    result = MacrRuntime(registry, services).invoke(provider_id, task, context)
    return result, context


class RuntimeLedgerTests(unittest.TestCase):
    def test_contradiction_fails_before_provider_or_ledger(self) -> None:
        provider = FixedResultProvider()
        registry = ProviderRegistry((provider,))
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            task = TaskContract(
                task_id="ledger-contradiction",
                goal="Use structured clauses.",
                task_type="testing",
                policy_clauses=TaskPolicyClauses(
                    import_mode=ImportMode.NONE,
                    required_imports=(
                        RequiredImport("required", "type_only"),
                    ),
                ),
            )
            with self.assertRaisesRegex(
                TaskContradictionError,
                "imports_none_but_required",
            ):
                invoke_authorized(registry, services, "grok", task)

            self.assertEqual(services.events.read_events(), ())

    def test_ledger_records_metrics_but_not_candidate_content(self) -> None:
        registry = ProviderRegistry((FixedResultProvider(),))
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            _, context = invoke_authorized(
                registry,
                services,
                "grok",
                TaskContract(
                    task_id="ledger-private-001",
                    goal="keep content out of ledger",
                    task_type="testing",
                ),
            )
            events = services.events.read_events(run_id=context.run_id)
            serialized = services.events.path.read_bytes()
        self.assertNotIn(b"PRIVATE ANSWER", serialized)
        self.assertNotIn(b"test-key", serialized)
        self.assertEqual(events[-1]["payload"]["model"], "grok-4.6")
        self.assertEqual(events[-1]["payload"]["input_tokens"], 20)
        self.assertEqual(
            events[-1]["payload"]["currency_cost_usd"],
            0.00025,
        )

    def test_google_ledger_records_allowlisted_metrics_without_content(self) -> None:
        registry = ProviderRegistry((GoogleFixedResultProvider(),))
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            _, context = invoke_authorized(
                registry,
                services,
                "google_image",
                TaskContract(
                    task_id="google-ledger-private",
                    goal="PRIVATE GOOGLE PROMPT",
                    task_type="image_generation",
                    inputs=(
                        {
                            "type": "file",
                            "path": "private-input.png",
                            "mime_type": "image/png",
                            "sha256": "0" * 64,
                        },
                    ),
                ),
            )
            events = services.events.read_events(run_id=context.run_id)
            serialized = services.events.path.read_bytes()
        for forbidden in (
            b"PRIVATE GOOGLE PROMPT",
            b"PRIVATE GOOGLE ANSWER",
            b"private-input.png",
            b"private-file.jpg",
            b"private_key",
        ):
            self.assertNotIn(forbidden, serialized)
        payload = events[-1]["payload"]
        self.assertEqual(payload["input_media_count"], 1)
        self.assertEqual(payload["input_media_bytes"], 1024)
        self.assertEqual(payload["output_artifact_count"], 1)
        self.assertEqual(payload["output_artifact_bytes"], 2048)
        self.assertEqual(payload["cost_kind"], "estimated")
        self.assertEqual(payload["pricing_basis_version"], "2026-08-26")

    def test_dispatch_and_candidate_are_append_only_events(self) -> None:
        config = ProviderConfig(
            id="minimax",
            kind="minimax_openai_compatible",
            enabled=True,
            auth_mode=AuthMode.API_KEY,
            api_usage_allowed=True,
            connection_scope=ConnectionScope.EXTERNAL_HTTPS,
            api_key_env="TEST_KEY",
            base_url_env="TEST_BASE",
            model_env="TEST_MODEL",
            allowed_hosts=("example.invalid",),
            approved_privacy=(PrivacyLevel.PUBLIC.value,),
        )
        transport = FakeTransport(
            {"id": "candidate-1", "choices": [{"message": {"content": "ok"}}]}
        )
        registry = ProviderRegistry.from_configs(
            (config,),
            environ={
                "TEST_KEY": "test-key",
                "TEST_BASE": "https://example.invalid/v1",
                "TEST_MODEL": "MiniMax-M2.7",
            },
            transports={"minimax": transport},
        )
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            result, context = invoke_authorized(
                registry,
                services,
                "minimax",
                TaskContract(
                    task_id="ledger-test-001",
                    goal="produce one candidate",
                    task_type="testing",
                    delegable=True,
                    delegation_class=DelegationClass.NON_SENSITIVE_ROUTINE,
                    delegation_approval_sha256="b" * 64,
                    constraints=TaskConstraints(
                        max_cost_usd=0.01,
                        max_latency_s=5,
                        max_output_tokens=2_048,
                        internet=True,
                        privacy=PrivacyLevel.PUBLIC,
                    ),
                ),
            )
            events = services.events.read_events(run_id=context.run_id)
        self.assertEqual(result.status.value, "candidate_success")
        self.assertEqual(
            [event["event_type"] for event in events],
            ["provider.dispatch_requested", "provider.candidate_completed"],
        )
        self.assertEqual(
            events[1]["payload"]["dispatch_event_id"],
            events[0]["event_id"],
        )
        self.assertEqual(events[0]["payload"]["origin_host"], "test")
        self.assertEqual(
            events[0]["payload"]["authority_digest"],
            context.authorization.digest,
        )
        self.assertEqual(
            events[0]["payload"]["authority_revision"],
            context.authorization.revision,
        )
        self.assertNotEqual(events[0]["event_id"], events[1]["event_id"])

    def test_policy_failure_is_recorded_as_candidate_failure(self) -> None:
        config = ProviderConfig(
            id="grok",
            kind="grok_responses_pending",
            enabled=False,
            auth_mode=AuthMode.PENDING,
            api_usage_allowed=True,
            disabled_reason="pending credentials",
        )
        registry = ProviderRegistry.from_configs((config,), environ={})
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            result, context = invoke_authorized(
                registry,
                services,
                "grok",
                TaskContract(
                    task_id="grok-pending-001",
                    goal="must fail closed",
                    task_type="policy_test",
                ),
            )
            events = services.events.read_events(run_id=context.run_id)
        self.assertEqual(result.status.value, "candidate_failure")
        self.assertEqual(events[-1]["payload"]["status"], "candidate_failure")

    def test_unexpected_provider_failure_is_sanitized_and_recorded(self) -> None:
        config = ProviderConfig(
            id="minimax",
            kind="minimax_openai_compatible",
            enabled=True,
            auth_mode=AuthMode.API_KEY,
            api_usage_allowed=True,
            connection_scope=ConnectionScope.EXTERNAL_HTTPS,
            api_key_env="TEST_KEY",
            base_url_env="TEST_BASE",
            model_env="TEST_MODEL",
            allowed_hosts=("example.invalid",),
            capabilities=("text_generation",),
            approved_privacy=(PrivacyLevel.PUBLIC.value,),
        )
        registry = ProviderRegistry.from_configs(
            (config,),
            environ={
                "TEST_KEY": "test-key",
                "TEST_BASE": "https://example.invalid/v1",
                "TEST_MODEL": "MiniMax-M2.7",
            },
            transports={"minimax": ExplodingTransport()},
        )
        with d_drive_tempdir() as temp:
            services = build_test_services(temp)
            result, context = invoke_authorized(
                registry,
                services,
                "minimax",
                TaskContract(
                    task_id="unexpected-failure-001",
                    goal="record a sanitized terminal event",
                    task_type="testing",
                    constraints=TaskConstraints(
                        max_cost_usd=0.01,
                        max_latency_s=5,
                        max_output_tokens=2_048,
                        internet=True,
                        privacy=PrivacyLevel.PUBLIC,
                    ),
                    required_capabilities=("text_generation",),
                ),
            )
            events = services.events.read_events(run_id=context.run_id)
        self.assertEqual(result.status.value, "candidate_failure")
        self.assertNotIn("simulated transport", str(result.to_dict()))
        self.assertEqual(result.provider_meta["failure_type"], "RuntimeError")
        self.assertEqual(events[-1]["payload"]["status"], "candidate_failure")


if __name__ == "__main__":
    unittest.main()
