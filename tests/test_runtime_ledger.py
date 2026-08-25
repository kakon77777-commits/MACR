from __future__ import annotations

import unittest

from macr_runtime.config import AuthMode, ConnectionScope, ProviderConfig
from macr_runtime.contracts import PrivacyLevel, TaskConstraints, TaskContract
from macr_runtime.ledger import AppendOnlyLedger
from macr_runtime.registry import ProviderRegistry
from macr_runtime.runtime import MacrRuntime

from tests.support import d_drive_tempdir
from tests.test_minimax_provider import FakeTransport


class ExplodingTransport:
    def post_json(self, url, *, headers, payload, timeout_s):
        del url, headers, payload, timeout_s
        raise RuntimeError("simulated transport implementation crash")


class RuntimeLedgerTests(unittest.TestCase):
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
                "TEST_MODEL": "test-model",
            },
            transports={"minimax": transport},
        )
        with d_drive_tempdir() as temp:
            ledger = AppendOnlyLedger(temp / "events.jsonl")
            runtime = MacrRuntime(registry, ledger)
            result = runtime.invoke(
                "minimax",
                TaskContract(
                    task_id="ledger-test-001",
                    goal="produce one candidate",
                    task_type="testing",
                    constraints=TaskConstraints(
                        max_cost_usd=0.01,
                        max_latency_s=5,
                        internet=True,
                        privacy=PrivacyLevel.PUBLIC,
                    ),
                ),
            )
            events = ledger.read_all()
        self.assertEqual(result.status.value, "candidate_success")
        self.assertEqual(
            [event["event_type"] for event in events],
            ["provider.dispatch_requested", "provider.candidate_completed"],
        )
        self.assertEqual(
            events[1]["payload"]["dispatch_event_id"],
            events[0]["event_id"],
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
            ledger = AppendOnlyLedger(temp / "events.jsonl")
            result = MacrRuntime(registry, ledger).invoke(
                "grok",
                TaskContract(
                    task_id="grok-pending-001",
                    goal="must fail closed",
                    task_type="policy_test",
                ),
            )
            events = ledger.read_all()
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
                "TEST_MODEL": "test-model",
            },
            transports={"minimax": ExplodingTransport()},
        )
        with d_drive_tempdir() as temp:
            ledger = AppendOnlyLedger(temp / "events.jsonl")
            result = MacrRuntime(registry, ledger).invoke(
                "minimax",
                TaskContract(
                    task_id="unexpected-failure-001",
                    goal="record a sanitized terminal event",
                    task_type="testing",
                    constraints=TaskConstraints(
                        max_cost_usd=0.01,
                        max_latency_s=5,
                        internet=True,
                        privacy=PrivacyLevel.PUBLIC,
                    ),
                    required_capabilities=("text_generation",),
                ),
            )
            events = ledger.read_all()
        self.assertEqual(result.status.value, "candidate_failure")
        self.assertNotIn("simulated transport", str(result.to_dict()))
        self.assertEqual(result.provider_meta["failure_type"], "RuntimeError")
        self.assertEqual(events[-1]["payload"]["status"], "candidate_failure")


if __name__ == "__main__":
    unittest.main()
