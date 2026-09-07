from __future__ import annotations

import hashlib
import sqlite3
import uuid
import unittest
from dataclasses import replace

from macr_runtime.direct_contracts import DirectMessage
from macr_runtime.direct_providers import DirectProviderReply
from macr_runtime.direct_runtime import (
    DirectRuntime,
    issue_operator_direct_authority,
)
from macr_runtime.direct_settings import DirectSettingsStore
from macr_runtime.direct_store import DirectConversationStore
from macr_runtime.errors import (
    DirectStoreConflict,
    LegacyDirectTokenPolicyIncompatibleError,
)
from macr_runtime.execution import ProviderState, ProviderUsage, RawProviderObservation
from macr_runtime.model_token_store import ModelTokenPolicyStore
from macr_runtime.token_policy import ModelTokenOverride, ModelTokenPolicyResolver
from tests.support import build_test_services, d_drive_tempdir


QWYTHOS_MODEL = "hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M"


class FakeAdapter:
    def __init__(
        self,
        provider_id: str,
        model: str,
        *,
        model_digest: str | None,
        answer: str = "assistant answer",
        cost_usd: float = 0.0,
        cost_kind: str = "zero_local",
        validation_error: str | None = None,
        failure: Exception | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.model = model
        self.model_digest = model_digest
        self.answer = answer
        self.cost_usd = cost_usd
        self.cost_kind = cost_kind
        self.validation_error = validation_error
        self.failure = failure
        self.calls: list[tuple[tuple[DirectMessage, ...], object]] = []

    def health(self):
        return type(
            "Health",
            (),
            {
                "to_dict": lambda self: {
                    "provider_id": provider_id,
                    "ready": True,
                    "status": "test_ready",
                    "detail": "",
                }
            },
        )()

    def model_identity(self):
        return {"model": self.model, "model_digest": self.model_digest}

    def invoke(self, messages, settings):
        self.calls.append((tuple(messages), settings))
        if self.failure is not None:
            raise self.failure
        observation = RawProviderObservation(
            provider_id=self.provider_id,
            model=self.model,
            response_id=f"response-{len(self.calls)}",
            finish_reason="stop",
            usage=ProviderUsage(20, 10, 0, 0),
            currency_cost_usd=self.cost_usd,
            cost_kind=self.cost_kind,
            pricing_basis_version="test-v1",
            duration_ms=25,
            answer_bytes=self.answer.encode("utf-8"),
            provider_state=ProviderState.COMPLETED,
        )
        return DirectProviderReply(observation, self.validation_error)


class FakeRegistry:
    def __init__(self, grok: FakeAdapter, qwythos: FakeAdapter) -> None:
        self.providers = {
            "grok": grok,
            "ollama_qwythos": qwythos,
        }

    def get(self, provider_id):
        return self.providers[provider_id]

    def health(self):
        return tuple(item.health().to_dict() for item in self.providers.values())


def adapters(**qwythos_overrides):
    return (
        FakeAdapter(
            "grok",
            "grok-4.6",
            model_digest=None,
            cost_usd=0.0003,
            cost_kind="provider_reported",
        ),
        FakeAdapter(
            "ollama_qwythos",
            QWYTHOS_MODEL,
            model_digest="d" * 64,
            **qwythos_overrides,
        ),
    )


class DirectRuntimeTests(unittest.TestCase):
    def build_runtime(self, root, *, grok=None, qwythos=None):
        if grok is None or qwythos is None:
            default_grok, default_qwythos = adapters()
            grok = default_grok if grok is None else grok
            qwythos = default_qwythos if qwythos is None else qwythos
        services = build_test_services(root)
        settings = DirectSettingsStore(root / "settings" / "settings.sqlite3")
        settings.ensure_operator_managed()
        conversations = DirectConversationStore(
            root / "direct" / "conversations.sqlite3"
        )
        token_policies = ModelTokenPolicyStore(
            root / "settings" / "model-token-policies.sqlite3"
        )
        authority = issue_operator_direct_authority(services)
        runtime = DirectRuntime(
            FakeRegistry(grok, qwythos),
            services,
            conversations,
            settings,
            authority,
            token_policies=token_policies,
        )
        return runtime, services, conversations, settings, grok, qwythos

    def test_legacy_grok_without_pinned_token_policy_fails_before_dispatch(self) -> None:
        with d_drive_tempdir() as root:
            runtime, services, conversations, _, grok, _ = self.build_runtime(root)
            conversation = runtime.create_conversation(
                "grok",
                conversation_id="00000000-0000-4000-8000-000000000709",
            )
            connection = sqlite3.connect(conversations.database.path)
            connection.execute(
                """UPDATE conversations
                SET model_token_policy_json = NULL,
                    model_token_policy_sha256 = NULL
                WHERE conversation_id = ?""",
                (conversation["conversation_id"],),
            )
            connection.commit()
            connection.close()

            with self.assertRaisesRegex(
                LegacyDirectTokenPolicyIncompatibleError,
                "legacy_direct_token_policy_incompatible",
            ):
                runtime.send_message(
                    conversation["conversation_id"],
                    "must not dispatch",
                    origin_native_id="browser-session-legacy",
                )

            events = services.events.read_events()

        self.assertEqual(grok.calls, [])
        self.assertEqual(events, ())

    def test_model_override_is_local_and_existing_conversation_stays_pinned(self) -> None:
        with d_drive_tempdir() as root:
            runtime, _, conversations, _, grok, qwythos = self.build_runtime(root)
            old_grok = runtime.create_conversation(
                "grok",
                conversation_id="00000000-0000-4000-8000-000000000701",
            )
            local = runtime.create_conversation(
                "ollama_qwythos",
                conversation_id="00000000-0000-4000-8000-000000000702",
            )
            base = ModelTokenPolicyResolver.builtins_only().resolve(
                "grok",
                "grok-4.6",
            )
            runtime.token_policies.save_override(
                ModelTokenOverride(
                    provider_id="grok",
                    model_id="grok-4.6",
                    revision=2,
                    context_warning_tokens=200_000,
                    hard_context_tokens=450_000,
                    default_output_tokens=40_000,
                    max_output_tokens=48_000,
                    base_policy_digest=base.policy_digest,
                ),
                activate=True,
            )
            new_grok = runtime.create_conversation(
                "grok",
                conversation_id="00000000-0000-4000-8000-000000000703",
            )

            runtime.send_message(
                old_grok["conversation_id"],
                "old",
                origin_native_id="browser-old",
            )
            runtime.send_message(
                new_grok["conversation_id"],
                "new",
                origin_native_id="browser-new",
            )
            runtime.send_message(
                local["conversation_id"],
                "local",
                origin_native_id="browser-local",
            )
            reopened = DirectConversationStore(
                root / "direct" / "conversations.sqlite3"
            )
            reopened_old = reopened.get(old_grok["conversation_id"])

        self.assertNotEqual(
            old_grok["model_token_policy_sha256"],
            new_grok["model_token_policy_sha256"],
        )
        self.assertEqual(grok.calls[-2][1].max_output_tokens, 32_768)
        self.assertEqual(grok.calls[-1][1].max_output_tokens, 40_000)
        self.assertEqual(qwythos.calls[-1][1].max_output_tokens, 4_096)
        self.assertEqual(qwythos.calls[-1][1].hard_context_tokens, 8_192)
        self.assertEqual(
            reopened_old["model_token_policy_sha256"],
            old_grok["model_token_policy_sha256"],
        )

    def test_operator_authority_is_exact_to_direct_grok_and_qwythos(self) -> None:
        with d_drive_tempdir() as root:
            services = build_test_services(root)
            reference = issue_operator_direct_authority(services)
            self.assertEqual(reference.source_kind, "local_operator_profile")
            self.assertEqual(reference.source_id, "direct-chat-operator-managed-v1")
            scope = reference.scope
            self.assertEqual(
                scope,
            '{"batch_ids":[],"member_digests":[],"planes":["direct"],'
            '"provider_tier_binding_digests":[],"providers":'
            '["grok","ollama_qwythos"],"scope_contract_version":2,'
            '"task_types":["direct_chat"]}',
            )
            services.authorities.verify(
                reference,
                provider_id="grok",
                plane="direct",
                task_type="direct_chat",
            )
            with self.assertRaises(Exception):
                services.authorities.verify(
                    reference,
                    provider_id="glm_flash_worker",
                    plane="direct",
                    task_type="direct_chat",
                )

    def test_successful_turn_preserves_full_history_and_private_capture(self) -> None:
        with d_drive_tempdir() as root:
            runtime, services, store, _, _, qwythos = self.build_runtime(root)
            conversation = runtime.create_conversation(
                "ollama_qwythos",
                title="Runtime test",
                system_prompt="Visible system only",
                conversation_id="00000000-0000-4000-8000-000000000101",
            )
            first = runtime.send_message(
                conversation["conversation_id"],
                "first question SECRET_PROMPT_ONE",
                origin_native_id="browser-session-test",
                run_id="00000000-0000-4000-8000-000000000102",
            )
            second = runtime.send_message(
                conversation["conversation_id"],
                "second question SECRET_PROMPT_TWO",
                origin_native_id="browser-session-test",
                run_id="00000000-0000-4000-8000-000000000103",
            )

            self.assertEqual(first.status, "completed")
            self.assertEqual(second.status, "completed")
            self.assertEqual(
                [item.to_dict() for item in qwythos.calls[0][0]],
                [
                    {"role": "system", "content": "Visible system only"},
                    {"role": "user", "content": "first question SECRET_PROMPT_ONE"},
                ],
            )
            self.assertEqual(
                [item.to_dict() for item in qwythos.calls[1][0]],
                [
                    {"role": "system", "content": "Visible system only"},
                    {"role": "user", "content": "first question SECRET_PROMPT_ONE"},
                    {"role": "assistant", "content": "assistant answer"},
                    {"role": "user", "content": "second question SECRET_PROMPT_TWO"},
                ],
            )
            messages = store.messages(conversation["conversation_id"])
            self.assertEqual([item["ordinal"] for item in messages], [1, 2, 3, 4])
            events = services.events.read_events(run_id=second.run_id)
            self.assertEqual(
                [item["event_type"] for item in events],
                ["provider.dispatch_requested", "provider.candidate_completed"],
            )
            capture = events[1]["payload"]["candidate_capture"]
            self.assertEqual(
                services.vault.read(capture["capture_id"]),
                b"assistant answer",
            )
            invocation = services.accounting.read_invocation(second.run_id)
            self.assertEqual(invocation["interaction_plane"], "direct")
            self.assertEqual(invocation["billing_state"], "zero_local")
            self.assertEqual(invocation["candidate_status"], "candidate_success")

            runtime_bytes = (root / "runtime" / "dispatch.sqlite3").read_bytes()
            accounting_bytes = (root / "accounting" / "accounting.sqlite3").read_bytes()
            for marker in (
                b"SECRET_PROMPT_ONE",
                b"SECRET_PROMPT_TWO",
                b"assistant answer",
                b"Visible system only",
            ):
                self.assertNotIn(marker, runtime_bytes)
                self.assertNotIn(marker, accounting_bytes)

    def test_stale_authority_and_lease_contention_refuse_before_adapter(self) -> None:
        with d_drive_tempdir() as root:
            runtime, services, _, _, _, qwythos = self.build_runtime(root)
            conversation = runtime.create_conversation(
                "ollama_qwythos",
                conversation_id="00000000-0000-4000-8000-000000000111",
            )
            services.authorities.advance_epoch(
                reason_digest=hashlib.sha256(b"stop").hexdigest(),
                state="revoked",
            )
            stale = runtime.send_message(
                conversation["conversation_id"],
                "must not dispatch",
                origin_native_id="browser-session-test",
                run_id="00000000-0000-4000-8000-000000000112",
            )
            self.assertEqual(stale.status, "refused_before_network")
            self.assertEqual(qwythos.calls, [])
            self.assertEqual(services.events.read_events(run_id=stale.run_id), ())

        with d_drive_tempdir() as root:
            runtime, services, _, _, _, qwythos = self.build_runtime(root)
            conversation = runtime.create_conversation(
                "ollama_qwythos",
                conversation_id="00000000-0000-4000-8000-000000000121",
            )
            holder = str(uuid.uuid4())
            permit = services.leases.acquire(
                "provider:ollama_qwythos:direct",
                holder,
                ttl_seconds=300,
            )
            try:
                blocked = runtime.send_message(
                    conversation["conversation_id"],
                    "must not overlap",
                    origin_native_id="browser-session-test",
                    run_id="00000000-0000-4000-8000-000000000122",
                )
            finally:
                services.leases.release(
                    permit.resource_key,
                    permit.run_id,
                    permit.fencing_token,
                )
            self.assertEqual(blocked.status, "refused_before_network")
            self.assertEqual(qwythos.calls, [])

    def test_protocol_rejection_keeps_observation_and_capture_without_message(self) -> None:
        with d_drive_tempdir() as root:
            grok, qwythos = adapters(validation_error="unexpected_tools")
            runtime, services, store, _, _, _ = self.build_runtime(
                root,
                grok=grok,
                qwythos=qwythos,
            )
            conversation = runtime.create_conversation(
                "ollama_qwythos",
                conversation_id="00000000-0000-4000-8000-000000000131",
            )
            result = runtime.send_message(
                conversation["conversation_id"],
                "candidate should be rejected",
                origin_native_id="browser-session-test",
                run_id="00000000-0000-4000-8000-000000000132",
            )
            self.assertEqual(result.status, "failed_after_dispatch")
            self.assertEqual(result.failure_type, "unexpected_tools")
            self.assertEqual(len(store.messages(conversation["conversation_id"])), 1)
            terminal = services.events.read_events(run_id=result.run_id)[1]
            capture = terminal["payload"]["candidate_capture"]
            self.assertEqual(
                services.vault.read(capture["capture_id"]),
                b"assistant answer",
            )
            invocation = services.accounting.read_invocation(result.run_id)
            self.assertEqual(invocation["input_tokens"], 20)
            self.assertEqual(invocation["candidate_status"], "candidate_failure")

    def test_transport_failure_is_unknown_after_dispatch_without_retry(self) -> None:
        with d_drive_tempdir() as root:
            grok, qwythos = adapters(failure=TimeoutError("private remote detail"))
            runtime, services, store, _, _, _ = self.build_runtime(
                root,
                grok=grok,
                qwythos=qwythos,
            )
            conversation = runtime.create_conversation(
                "ollama_qwythos",
                conversation_id="00000000-0000-4000-8000-000000000141",
            )
            result = runtime.send_message(
                conversation["conversation_id"],
                "one attempt only",
                origin_native_id="browser-session-test",
                run_id="00000000-0000-4000-8000-000000000142",
            )
            self.assertEqual(result.status, "failed_after_dispatch")
            self.assertEqual(result.failure_type, "TimeoutError")
            self.assertEqual(len(qwythos.calls), 1)
            self.assertEqual(len(store.messages(conversation["conversation_id"])), 1)
            invocation = services.accounting.read_invocation(result.run_id)
            self.assertEqual(invocation["billing_state"], "unknown_after_dispatch")

    def test_context_hard_limit_refuses_and_warning_keeps_full_history(self) -> None:
        with d_drive_tempdir() as root:
            runtime, _, _, settings_store, _, qwythos = self.build_runtime(root)
            current = settings_store.active_profile()
            constrained = replace(
                current,
                profile_name="tiny-context",
                profile_version=1,
            )
            settings_store.save_profile(constrained, activate=True)
            local_base = ModelTokenPolicyResolver.builtins_only().resolve(
                "ollama_qwythos",
                QWYTHOS_MODEL,
            )
            runtime.token_policies.save_override(
                ModelTokenOverride(
                    provider_id="ollama_qwythos",
                    model_id=QWYTHOS_MODEL,
                    revision=2,
                    context_warning_tokens=6,
                    hard_context_tokens=12,
                    default_output_tokens=4,
                    max_output_tokens=4,
                    base_policy_digest=local_base.policy_digest,
                ),
                activate=True,
            )
            conversation = runtime.create_conversation(
                "ollama_qwythos",
                conversation_id="00000000-0000-4000-8000-000000000151",
            )
            warning = runtime.send_message(
                conversation["conversation_id"],
                "123456",
                origin_native_id="browser-session-test",
                run_id="00000000-0000-4000-8000-000000000152",
            )
            self.assertEqual(warning.status, "completed")
            self.assertTrue(warning.context_warning)
            refused = runtime.send_message(
                conversation["conversation_id"],
                "this input makes the complete history too large",
                origin_native_id="browser-session-test",
                run_id="00000000-0000-4000-8000-000000000153",
            )
            self.assertEqual(refused.status, "refused_before_network")
            self.assertEqual(refused.failure_type, "ContextLimitExceeded")
            self.assertEqual(len(qwythos.calls), 1)

    def test_warn_only_budget_marks_accounting_without_blocking(self) -> None:
        with d_drive_tempdir() as root:
            costly_grok = FakeAdapter(
                "grok",
                "grok-4.6",
                model_digest=None,
                cost_usd=0.5,
                cost_kind="provider_reported",
            )
            _, default_qwythos = adapters()
            runtime, services, _, settings_store, _, _ = self.build_runtime(
                root,
                grok=costly_grok,
                qwythos=default_qwythos,
            )
            current = settings_store.active_profile()
            budgeted = replace(
                current,
                profile_name="warn-budget",
                profile_version=1,
                soft_budget_usd=0.01,
            )
            settings_store.save_profile(budgeted, activate=True)
            conversation = runtime.create_conversation(
                "grok",
                conversation_id="00000000-0000-4000-8000-000000000161",
            )
            result = runtime.send_message(
                conversation["conversation_id"],
                "authorized expensive turn",
                origin_native_id="browser-session-test",
                run_id="00000000-0000-4000-8000-000000000162",
            )
            self.assertEqual(result.status, "completed")
            invocation = services.accounting.read_invocation(result.run_id)
            self.assertEqual(invocation["soft_warning"], 1)
            self.assertEqual(invocation["currency_cost_usd"], 0.5)

    def test_confirmed_delete_purges_candidate_and_keeps_content_free_accounting(self) -> None:
        with d_drive_tempdir() as root:
            runtime, services, store, _, _, _ = self.build_runtime(root)
            conversation = runtime.create_conversation(
                "ollama_qwythos",
                conversation_id="00000000-0000-4000-8000-000000000171",
            )
            turn = runtime.send_message(
                conversation["conversation_id"],
                "PRIVATE_DELETE_RUNTIME_SENTINEL_8A31",
                origin_native_id="browser-session-delete",
                run_id="00000000-0000-4000-8000-000000000172",
            )
            capture = services.vault.read_by_run(turn.run_id)
            self.assertIsNotNone(capture)
            target = services.vault.root / capture.relative_path
            self.assertTrue(target.is_file())

            with self.assertRaisesRegex(ValueError, "DELETE"):
                runtime.delete_conversation(
                    conversation["conversation_id"],
                    confirmation="delete",
                    origin_native_id="browser-session-delete",
                )
            self.assertTrue(target.is_file())

            result = runtime.delete_conversation(
                conversation["conversation_id"],
                confirmation="DELETE",
                origin_native_id="browser-session-delete",
            )

            self.assertEqual(
                result,
                {
                    "conversation_id": conversation["conversation_id"],
                    "message_count": 2,
                    "run_count": 1,
                    "candidate_files_removed": 1,
                    "secure_delete": True,
                    "wal_truncated": True,
                },
            )
            self.assertFalse(target.exists())
            with self.assertRaisesRegex(DirectStoreConflict, "missing"):
                store.get(conversation["conversation_id"])
            invocation = services.accounting.read_invocation(turn.run_id)
            self.assertEqual(invocation["candidate_status"], "candidate_success")
            tombstones = services.events.read_events(
                event_type="direct.conversation_deleted"
            )
            self.assertEqual(len(tombstones), 1)
            self.assertEqual(
                tombstones[0]["payload"],
                {
                    "candidate_files_removed": 1,
                    "conversation_id": conversation["conversation_id"],
                    "deletion_mode": "operator_confirmed_privacy_delete",
                    "message_count": 2,
                    "origin_host": "direct_ui",
                    "origin_identifier_kind": "browser_session",
                    "origin_native_id": "browser-session-delete",
                    "run_count": 1,
                    "secure_delete": True,
                    "wal_truncated": True,
                },
            )


if __name__ == "__main__":
    unittest.main()
