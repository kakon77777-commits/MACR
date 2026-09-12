from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from macr_runtime.authority import AuthorityScope
from macr_runtime.canonical import sha256_id
from macr_runtime.direct_contracts import DirectConversationSpec, DirectMessage
from macr_runtime.direct_providers import DirectProviderReply
from macr_runtime.direct_runtime import (
    DirectRuntime,
    issue_operator_direct_authority,
    issue_operator_grok_direct_authority,
)
from macr_runtime.direct_settings import DirectSettingsStore
from macr_runtime.direct_store import DirectConversationStore
from macr_runtime.errors import (
    DirectStoreConflict,
    LegacyDirectTokenPolicyIncompatibleError,
    MacrError,
    ProviderAdmissionBusyError,
)
from macr_runtime.execution import (
    DispatchContext,
    DispatchOrigin,
    InteractionPlane,
    ProviderState,
    ProviderUsage,
    RawProviderObservation,
)
from macr_runtime.model_token_store import ModelTokenPolicyStore
from macr_runtime.provider_admission import (
    AdmissionLane,
    ProjectAdmissionBinding,
    ProviderAdmissionDirectory,
    ProviderAdmissionRequest,
    ProviderAdmissionTargetBinding,
)
from macr_runtime.providers.grok import GrokResponsesProvider
from macr_runtime.registry import ProviderRegistry
from macr_runtime.runtime import MacrRuntime
from macr_runtime.token_policy import ModelTokenOverride, ModelTokenPolicyResolver
from tests.support import build_test_services, d_drive_tempdir
from tests.test_grok_provider import (
    FakeTransport as DelegatedGrokTransport,
    cloud_task as delegated_grok_task,
    grok_config as delegated_grok_config,
    success_document as delegated_grok_success_document,
)


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

    def invoke(
        self,
        messages,
        settings,
        *,
        admission_permit=None,
        admission_request=None,
    ):
        if self.provider_id == "grok":
            if getattr(self, "admission_guard", None) is None:
                raise AssertionError("test Grok adapter has no admission guard")
            self.admission_guard.begin_transport(
                admission_permit,
                admission_request,
            )
        self.calls.append((tuple(messages), settings))
        if self.failure is not None:
            raise self.failure
        return self._reply()

    def _reply(self):
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
            network_attempted=(True if self.provider_id == "grok" else None),
            response_received=(True if self.provider_id == "grok" else None),
            transport_stage=(
                "response_received" if self.provider_id == "grok" else None
            ),
        )
        return DirectProviderReply(observation, self.validation_error)


class BlockingGrokAdapter(FakeAdapter):
    def __init__(self) -> None:
        super().__init__(
            "grok",
            "grok-4.6",
            model_digest=None,
            cost_usd=0.0003,
            cost_kind="provider_reported",
        )
        self.release = threading.Event()
        self._condition = threading.Condition()
        self.active = 0
        self.max_active = 0

    def invoke(
        self,
        messages,
        settings,
        *,
        admission_permit=None,
        admission_request=None,
    ):
        self.admission_guard.begin_transport(
            admission_permit,
            admission_request,
        )
        with self._condition:
            self.calls.append((tuple(messages), settings))
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self._condition.notify_all()
        if not self.release.wait(timeout=10):
            raise TimeoutError("test transport release was not signalled")
        with self._condition:
            self.active -= 1
            self._condition.notify_all()
        return self._reply()

    def wait_for_active(self, expected: int, *, timeout: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout
        with self._condition:
            while self.active < expected:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True


class BeforeBeginHookGrokAdapter(FakeAdapter):
    def __init__(self) -> None:
        super().__init__(
            "grok",
            "grok-4.6",
            model_digest=None,
            cost_usd=0.0003,
            cost_kind="provider_reported",
        )
        self.before_begin = lambda: None

    def invoke(
        self,
        messages,
        settings,
        *,
        admission_permit=None,
        admission_request=None,
    ):
        self.before_begin()
        return super().invoke(
            messages,
            settings,
            admission_permit=admission_permit,
            admission_request=admission_request,
        )


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
        provider_admissions = ProviderAdmissionDirectory.offline_test(
            services.events.path
        )
        services = replace(
            services,
            provider_admission=provider_admissions.get("glm_flash_worker"),
            provider_admissions=provider_admissions,
        )
        settings = DirectSettingsStore(root / "settings" / "settings.sqlite3")
        settings.ensure_operator_managed()
        conversations = DirectConversationStore(
            root / "direct" / "conversations.sqlite3"
        )
        token_policies = ModelTokenPolicyStore(
            root / "settings" / "model-token-policies.sqlite3"
        )
        grok.admission_guard = services.provider_admission_for("grok")
        authority = issue_operator_direct_authority(services)
        grok_authority = issue_operator_grok_direct_authority(services)
        runtime = DirectRuntime(
            FakeRegistry(grok, qwythos),
            services,
            conversations,
            settings,
            authority,
            grok_authority,
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

    def test_legacy_qwythos_policy_v1_remains_local_only_compatible(self) -> None:
        with d_drive_tempdir() as root:
            runtime, _, conversations, _, _, qwythos = self.build_runtime(root)
            conversation = runtime.create_conversation(
                "ollama_qwythos",
                conversation_id="00000000-0000-4000-8000-000000000710",
            )
            current = conversations.get(conversation["conversation_id"])
            legacy_policy = json.loads(current["model_token_policy_json"])
            legacy_policy.pop("minimum_task_output_tokens")
            legacy_json = json.dumps(
                legacy_policy,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            legacy_digest = sha256_id("model_token_policy_v1", legacy_policy)
            connection = sqlite3.connect(conversations.database.path)
            connection.execute(
                """UPDATE conversations
                SET model_token_policy_json = ?, model_token_policy_sha256 = ?
                WHERE conversation_id = ?""",
                (legacy_json, legacy_digest, conversation["conversation_id"]),
            )
            connection.commit()
            connection.close()

            result = runtime.send_message(
                conversation["conversation_id"],
                "local legacy turn",
                origin_native_id="browser-session-local-legacy",
            )

        self.assertEqual(result.status, "completed")
        self.assertEqual(len(qwythos.calls), 1)
        self.assertEqual(qwythos.calls[0][1].max_output_tokens, 4_096)

    def test_tampered_grok_token_snapshot_cannot_bypass_combined_policy(self) -> None:
        with d_drive_tempdir() as root:
            runtime, services, conversations, _, grok, _ = self.build_runtime(root)
            conversation = runtime.create_conversation(
                "grok",
                conversation_id="00000000-0000-4000-8000-000000000711",
            )
            current = ModelTokenPolicyResolver.builtins_only().resolve(
                "grok",
                "grok-4.6",
            )
            historical = replace(
                current,
                context_warning_tokens=180_000,
                hard_context_tokens=400_000,
                default_output_tokens=32_768,
                max_output_tokens=65_536,
            )
            historical_json = json.dumps(
                historical.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            connection = sqlite3.connect(conversations.database.path)
            connection.execute(
                """UPDATE conversations
                SET model_token_policy_json = ?, model_token_policy_sha256 = ?
                WHERE conversation_id = ?""",
                (
                    historical_json,
                    historical.policy_digest,
                    conversation["conversation_id"],
                ),
            )
            connection.commit()
            connection.close()

            with self.assertRaisesRegex(MacrError, "combined policy snapshot"):
                runtime.send_message(
                    conversation["conversation_id"],
                    "must not dispatch",
                    origin_native_id="browser-tamper",
                )

            events = services.events.read_events()

        self.assertEqual(grok.calls, [])
        self.assertEqual(events, ())

    def test_new_grok_conversation_pins_large_context_policy(self) -> None:
        with d_drive_tempdir() as root:
            runtime, _, _, _, grok, _ = self.build_runtime(root)
            conversation = runtime.create_conversation(
                "grok",
                conversation_id="00000000-0000-4000-8000-000000000712",
            )
            pinned = json.loads(conversation["model_token_policy_json"])

            result = runtime.send_message(
                conversation["conversation_id"],
                "use the current envelope",
                origin_native_id="browser-current",
            )

        self.assertEqual(result.status, "completed")
        self.assertEqual(pinned["context_warning_tokens"], 400_000)
        self.assertEqual(pinned["hard_context_tokens"], 500_000)
        self.assertEqual(pinned["default_output_tokens"], 65_536)
        self.assertEqual(pinned["max_output_tokens"], 131_072)
        self.assertEqual(grok.calls[0][1].max_output_tokens, 65_536)
        self.assertEqual(grok.calls[0][1].hard_context_tokens, 500_000)

    def test_historical_grok_snapshot_stays_pinned_after_policy_upgrade(self) -> None:
        with d_drive_tempdir() as root:
            runtime, _, conversations, settings, grok, qwythos = (
                self.build_runtime(root)
            )
            base = ModelTokenPolicyResolver.builtins_only().resolve(
                "grok",
                "grok-4.6",
            )
            historical = replace(
                base,
                context_warning_tokens=180_000,
                hard_context_tokens=400_000,
                default_output_tokens=32_768,
                max_output_tokens=65_536,
            )
            old_spec = DirectConversationSpec.create(
                provider_id="grok",
                model="grok-4.6",
                system_prompt="",
                settings=settings.active_profile(),
                model_token_policy=historical,
            )
            old_grok = conversations.create(
                old_spec,
                conversation_id="00000000-0000-4000-8000-000000000701",
            )
            local = runtime.create_conversation(
                "ollama_qwythos",
                conversation_id="00000000-0000-4000-8000-000000000702",
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
        self.assertEqual(grok.calls[-2][1].hard_context_tokens, 400_000)
        self.assertEqual(grok.calls[-1][1].max_output_tokens, 40_000)
        self.assertEqual(qwythos.calls[-1][1].max_output_tokens, 4_096)
        self.assertEqual(qwythos.calls[-1][1].hard_context_tokens, 8_192)
        self.assertEqual(
            reopened_old["model_token_policy_sha256"],
            old_grok["model_token_policy_sha256"],
        )

    def test_same_grok_conversation_remains_strictly_serial(self) -> None:
        with d_drive_tempdir() as root:
            grok = BlockingGrokAdapter()
            runtime, _, _, _, _, _ = self.build_runtime(root, grok=grok)
            conversation = runtime.create_conversation(
                "grok",
                conversation_id="00000000-0000-4000-8000-000000000713",
            )
            results = []
            failures = []

            def send(content: str) -> None:
                try:
                    results.append(
                        runtime.send_message(
                            conversation["conversation_id"],
                            content,
                            origin_native_id=f"browser-{content}",
                        )
                    )
                except Exception as exc:  # pragma: no cover - assertion aid
                    failures.append(exc)

            first = threading.Thread(target=send, args=("first",))
            second = threading.Thread(target=send, args=("second",))
            first.start()
            self.assertTrue(grok.wait_for_active(1))
            second.start()
            time.sleep(0.1)
            self.assertEqual(grok.active, 1)
            self.assertEqual(len(grok.calls), 1)
            grok.release.set()
            first.join(timeout=10)
            second.join(timeout=10)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(len(results), 2)
        self.assertTrue(all(item.status == "completed" for item in results))
        self.assertEqual(grok.max_active, 1)
        self.assertEqual(len(grok.calls), 2)

    def test_distinct_grok_conversations_share_eight_slot_provider_cap(self) -> None:
        with d_drive_tempdir() as root:
            grok = BlockingGrokAdapter()
            runtime, services, _, _, _, _ = self.build_runtime(
                root,
                grok=grok,
            )
            conversations = [
                runtime.create_conversation(
                    "grok",
                    conversation_id=(
                        f"00000000-0000-4000-8000-{index:012d}"
                    ),
                )
                for index in range(720, 729)
            ]
            results = {}
            failures = []

            def send(index: int) -> None:
                try:
                    results[index] = runtime.send_message(
                        conversations[index]["conversation_id"],
                        f"message-{index}",
                        origin_native_id=f"browser-{index}",
                    )
                except Exception as exc:  # pragma: no cover - assertion aid
                    failures.append(exc)

            threads = [
                threading.Thread(target=send, args=(index,))
                for index in range(8)
            ]
            try:
                for thread in threads:
                    thread.start()
                self.assertTrue(grok.wait_for_active(8))
                refused = runtime.send_message(
                    conversations[8]["conversation_id"],
                    "ninth",
                    origin_native_id="browser-ninth",
                )
                self.assertEqual(
                    refused.failure_type,
                    "ProviderAdmissionBusyError",
                )
                self.assertEqual(refused.status, "refused_before_network")
                self.assertEqual(len(grok.calls), 8)
            finally:
                grok.release.set()
                for thread in threads:
                    thread.join(timeout=10)
            status = services.provider_admission_for("grok").status("grok")

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        self.assertEqual(len(results), 8)
        self.assertTrue(all(item.status == "completed" for item in results.values()))
        self.assertEqual(grok.max_active, 8)
        self.assertEqual(status.counts["completed"], 8)
        self.assertEqual(status.counts["cancelled"], 1)

    def test_direct_and_delegated_grok_contend_in_one_provider_pool(self) -> None:
        with d_drive_tempdir() as root:
            direct_grok = BlockingGrokAdapter()
            runtime, services, _, _, _, _ = self.build_runtime(
                root,
                grok=direct_grok,
            )
            kernel = services.provider_admission_for("grok")
            target = ProviderAdmissionTargetBinding.create(
                kernel.policy,
                target=1,
            )
            target_authority = services.authorities.issue(
                source_kind="operator_test",
                source_id="grok-mixed-plane-target-one",
                scope=AuthorityScope(
                    providers=("grok",),
                    planes=("provider_capacity_activation",),
                    task_types=("provider_capacity_target",),
                    provider_admission_target_digests=(
                        target.binding_digest,
                    ),
                    scope_contract_version=3,
                ),
                expires_at=(
                    datetime.now(timezone.utc) + timedelta(minutes=5)
                ).isoformat(),
            )
            kernel.activate_target(target, target_authority)
            conversation = runtime.create_conversation(
                "grok",
                conversation_id="00000000-0000-4000-8000-000000000730",
            )
            direct_results = []
            direct_failures = []

            def send_direct() -> None:
                try:
                    direct_results.append(
                        runtime.send_message(
                            conversation["conversation_id"],
                            "hold the shared slot",
                            origin_native_id="browser-mixed-plane",
                        )
                    )
                except Exception as exc:  # pragma: no cover - assertion aid
                    direct_failures.append(exc)

            direct_thread = threading.Thread(target=send_direct)
            direct_thread.start()
            try:
                self.assertTrue(direct_grok.wait_for_active(1))
                delegated_transport = DelegatedGrokTransport(
                    delegated_grok_success_document("grok-4.6")
                )
                delegated_provider = GrokResponsesProvider(
                    delegated_grok_config("grok", "grok-4.6", "high"),
                    transport=delegated_transport,
                    environ={"XAI_API_KEY": "test-key"},
                    admission_guard=kernel,
                    offline_test_transport=True,
                )
                task = delegated_grok_task(max_output_tokens=65_536)
                project = ProjectAdmissionBinding(
                    "delegated-mixed-plane",
                    1,
                    "operator_asserted",
                )
                run_id = str(uuid.uuid4())
                reference = services.authorities.issue(
                    source_kind="operator_test",
                    source_id=f"grok-mixed-plane-{run_id}",
                    scope=AuthorityScope(
                        providers=("grok",),
                        planes=(InteractionPlane.DELEGATION.value,),
                        task_types=(task.task_type,),
                        project_binding_digests=(project.binding_digest,),
                        admission_lanes=(AdmissionLane.ROUTINE.value,),
                        provider_admission_policy_digests=(
                            kernel.policy.policy_digest,
                        ),
                        scope_contract_version=3,
                    ),
                    expires_at=(
                        datetime.now(timezone.utc) + timedelta(minutes=5)
                    ).isoformat(),
                )
                context = DispatchContext(
                    run_id=run_id,
                    plane=InteractionPlane.DELEGATION,
                    origin=DispatchOrigin("test", "process_id", "1234"),
                    authorization=reference,
                    policy_snapshot_sha256="f" * 64,
                    project_binding_digest=project.binding_digest,
                    admission_lane=AdmissionLane.ROUTINE.value,
                    provider_admission_policy_digest=(
                        kernel.policy.policy_digest
                    ),
                )

                with self.assertRaises(ProviderAdmissionBusyError):
                    MacrRuntime(
                        ProviderRegistry((delegated_provider,)),
                        services,
                    ).invoke("grok", task, context)
                self.assertEqual(delegated_transport.posts, [])
            finally:
                direct_grok.release.set()
                direct_thread.join(timeout=10)
            status = kernel.status("grok")

        self.assertFalse(direct_thread.is_alive())
        self.assertEqual(direct_failures, [])
        self.assertEqual(len(direct_results), 1)
        self.assertEqual(direct_results[0].status, "completed")
        self.assertEqual(status.counts["completed"], 1)
        self.assertEqual(status.counts["cancelled"], 1)

    def test_circuit_open_between_grant_and_transport_is_zero_local(self) -> None:
        with d_drive_tempdir() as root:
            grok = BeforeBeginHookGrokAdapter()
            runtime, services, conversations, _, _, _ = self.build_runtime(
                root,
                grok=grok,
            )
            kernel = services.provider_admission_for("grok")
            scope = json.loads(runtime.grok_admission_authority.scope)
            trigger_request = ProviderAdmissionRequest(
                request_id=str(uuid.uuid4()),
                provider_id="grok",
                project_binding_digest=scope[
                    "project_binding_digests"
                ][0],
                lane=AdmissionLane.INTERACTIVE,
                run_id=str(uuid.uuid4()),
                authorization=runtime.grok_admission_authority,
                plane=InteractionPlane.DIRECT.value,
                task_type="direct_chat",
                task_digest="a" * 64,
                member_digest=None,
                batch_id=None,
                provider_tier_binding_digest=None,
            )
            trigger_permit = kernel.try_admit(
                trigger_request,
                ttl_seconds=60,
            )
            kernel.begin_transport(trigger_permit, trigger_request)
            grok.before_begin = lambda: kernel.finish(
                trigger_permit,
                network_attempted=True,
                response_received=True,
                provider_http_status=429,
                terminal_persisted=True,
                terminal_evidence_digest="b" * 64,
            )
            conversation = runtime.create_conversation(
                "grok",
                conversation_id="00000000-0000-4000-8000-000000000731",
            )

            result = runtime.send_message(
                conversation["conversation_id"],
                "race the circuit",
                origin_native_id="browser-circuit-race",
            )
            status = kernel.status("grok")
            invocation = services.accounting.read_invocation(result.run_id)
            stored_run = conversations.read_run(result.run_id)

        self.assertEqual(result.status, "failed_after_dispatch")
        self.assertEqual(
            result.failure_type,
            "ProviderAdmissionReconciliationError",
        )
        self.assertFalse(result.observation["network_attempted"])
        self.assertFalse(result.observation["response_received"])
        self.assertEqual(invocation["billing_state"], "zero_local")
        self.assertEqual(invocation["currency_cost_usd"], 0.0)
        self.assertEqual(grok.calls, [])
        self.assertEqual(status.circuit_state, "open")
        self.assertEqual(status.counts["completed"], 1)
        self.assertEqual(status.counts["cancelled"], 1)
        self.assertEqual(stored_run["state"], "failed_after_dispatch")

    def test_operator_authorities_separate_local_and_admitted_grok(self) -> None:
        with d_drive_tempdir() as root:
            services = build_test_services(root)
            directory = ProviderAdmissionDirectory.offline_test(
                services.events.path
            )
            services = replace(
                services,
                provider_admission=directory.get("glm_flash_worker"),
                provider_admissions=directory,
            )
            reference = issue_operator_direct_authority(services)
            grok_reference = issue_operator_grok_direct_authority(services)
            self.assertEqual(reference.source_kind, "local_operator_profile")
            self.assertEqual(reference.source_id, "direct-chat-operator-managed-v1")
            scope = reference.scope
            self.assertEqual(
                scope,
            '{"batch_ids":[],"member_digests":[],"planes":["direct"],'
            '"provider_tier_binding_digests":[],"providers":'
            '["ollama_qwythos"],"scope_contract_version":2,'
            '"task_types":["direct_chat"]}',
            )
            grok_scope = json.loads(grok_reference.scope)
            self.assertEqual(grok_scope["providers"], ["grok"])
            self.assertEqual(grok_scope["admission_lanes"], ["interactive"])
            self.assertEqual(grok_scope["scope_contract_version"], 3)
            services.authorities.verify(
                grok_reference,
                provider_id="grok",
                plane="direct",
                task_type="direct_chat",
                project_binding_digest=grok_scope[
                    "project_binding_digests"
                ][0],
                admission_lane="interactive",
                provider_admission_policy_digest=(
                    services.provider_admission_for("grok").policy.policy_digest
                ),
            )
            with self.assertRaises(Exception):
                services.authorities.verify(
                    reference,
                    provider_id="grok",
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
