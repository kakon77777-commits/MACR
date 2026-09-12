from __future__ import annotations

import hashlib
import json
import math
import threading
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

from .authority import AuthorityScope
from .candidate_vault import CandidateCapture
from .canonical import sha256_id
from .direct_contracts import (
    canonical_policy_snapshot,
    DirectConversationSpec,
    DirectMessage,
    DirectRunSettings,
    DirectTurnResult,
)
from .direct_providers import DirectProviderReply
from .direct_settings import DirectSettingsStore
from .direct_store import DirectConversationStore
from .errors import (
    MacrError,
    LegacyDirectTokenPolicyIncompatibleError,
    ProviderAdmissionError,
    ProviderAdmissionConflict,
    ProviderAdmissionRequiredError,
)
from .execution import (
    AuthorizationReference,
    DispatchContext,
    DispatchOrigin,
    InteractionPlane,
    ProviderState,
    ProviderUsage,
    RawProviderObservation,
)
from .runtime import RuntimeServices
from .model_token_store import ModelTokenPolicyStore
from .provider_admission import (
    AdmissionLane,
    ProjectAdmissionBinding,
    ProviderAdmissionPermit,
    ProviderAdmissionRequest,
)
from .token_policy import ModelTokenPolicy, ModelTokenPolicyResolver


_DIRECT_TASK_TYPE = "direct_chat"
_DIRECT_RESOURCE_PREFIX = "provider"
_DIRECT_GROK_PROJECT = ProjectAdmissionBinding(
    "direct-chat",
    1,
    "operator_asserted",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _billing_state(observation: RawProviderObservation) -> str:
    if observation.currency_cost_usd is None:
        return "unknown_after_dispatch"
    if observation.cost_kind in {"provider_reported", "actual"}:
        return "provider_reported"
    if observation.cost_kind == "zero_local":
        return "zero_local"
    return "estimated"


def _failed_direct_observation(
    provider_id: str,
    exc: BaseException,
    *,
    known_pre_network: bool = False,
) -> RawProviderObservation:
    diagnostic_method = getattr(exc, "safe_diagnostic", None)
    raw = diagnostic_method() if callable(diagnostic_method) else {}
    diagnostic = raw if isinstance(raw, dict) else {}
    pre_network = (
        known_pre_network
        or diagnostic.get("network_attempted") is False
    )
    return RawProviderObservation(
        provider_id=provider_id,
        model=None,
        response_id=None,
        finish_reason=None,
        usage=ProviderUsage(None, None, None, None),
        currency_cost_usd=0.0 if pre_network else None,
        cost_kind="zero_local" if pre_network else None,
        pricing_basis_version=(
            "macr-pre-network-v1" if pre_network else None
        ),
        duration_ms=None,
        answer_bytes=None,
        provider_state=ProviderState.MALFORMED,
        network_attempted=(
            False if pre_network else diagnostic.get("network_attempted")
        ),
        response_received=(
            False if pre_network else diagnostic.get("response_received")
        ),
        provider_http_status=diagnostic.get("provider_http_status"),
        provider_error_code=diagnostic.get("provider_error_code"),
        transport_stage=(
            "pre_network"
            if pre_network
            else diagnostic.get("transport_stage")
        ),
    )


def issue_operator_direct_authority(
    services: RuntimeServices,
    *,
    lifetime_days: int = 365,
) -> AuthorizationReference:
    if not isinstance(services, RuntimeServices):
        raise ValueError("services must be RuntimeServices")
    if (
        isinstance(lifetime_days, bool)
        or not isinstance(lifetime_days, int)
        or not 1 <= lifetime_days <= 3650
    ):
        raise ValueError("lifetime_days must be between 1 and 3650")
    return services.authorities.issue(
        source_kind="local_operator_profile",
        source_id="direct-chat-operator-managed-v1",
        scope=AuthorityScope(
            providers=("ollama_qwythos",),
            planes=(InteractionPlane.DIRECT.value,),
            task_types=(_DIRECT_TASK_TYPE,),
        ),
        expires_at=(
            datetime.now(timezone.utc) + timedelta(days=lifetime_days)
        ).isoformat(),
    )


def issue_operator_grok_direct_authority(
    services: RuntimeServices,
    *,
    lifetime_days: int = 365,
) -> AuthorizationReference:
    if not isinstance(services, RuntimeServices):
        raise ValueError("services must be RuntimeServices")
    if (
        isinstance(lifetime_days, bool)
        or not isinstance(lifetime_days, int)
        or not 1 <= lifetime_days <= 3650
    ):
        raise ValueError("lifetime_days must be between 1 and 3650")
    kernel = services.provider_admission_for("grok")
    if kernel is None:
        raise ProviderAdmissionRequiredError(
            "Grok Direct admission kernel is unavailable"
        )
    return services.authorities.issue(
        source_kind="local_operator_profile",
        source_id="direct-chat-grok-admission-v1",
        scope=AuthorityScope(
            providers=("grok",),
            planes=(InteractionPlane.DIRECT.value,),
            task_types=(_DIRECT_TASK_TYPE,),
            project_binding_digests=(
                _DIRECT_GROK_PROJECT.binding_digest,
            ),
            admission_lanes=(AdmissionLane.INTERACTIVE.value,),
            provider_admission_policy_digests=(
                kernel.policy.policy_digest,
            ),
            scope_contract_version=3,
        ),
        expires_at=(
            datetime.now(timezone.utc) + timedelta(days=lifetime_days)
        ).isoformat(),
    )


class DirectRuntime:
    def __init__(
        self,
        registry: Any,
        services: RuntimeServices,
        conversations: DirectConversationStore,
        settings: DirectSettingsStore,
        authority: AuthorizationReference,
        grok_admission_authority: AuthorizationReference,
        *,
        token_policies: ModelTokenPolicyStore | None = None,
    ) -> None:
        if not isinstance(services, RuntimeServices):
            raise ValueError("services must be RuntimeServices")
        if not isinstance(conversations, DirectConversationStore):
            raise ValueError("conversations must be DirectConversationStore")
        if not isinstance(settings, DirectSettingsStore):
            raise ValueError("settings must be DirectSettingsStore")
        if not isinstance(authority, AuthorizationReference):
            raise ValueError("authority must be AuthorizationReference")
        if not isinstance(
            grok_admission_authority,
            AuthorizationReference,
        ):
            raise ValueError(
                "grok_admission_authority must be AuthorizationReference"
            )
        if not callable(getattr(registry, "get", None)):
            raise ValueError("registry must expose get(provider_id)")
        self.registry = registry
        self.services = services
        self.conversations = conversations
        self.settings = settings
        self.authority = authority
        self.grok_admission_authority = grok_admission_authority
        self.token_policies = token_policies
        self._builtin_token_policies = ModelTokenPolicyResolver.builtins_only()
        self._conversation_locks_guard = threading.Lock()
        self._conversation_locks: dict[str, threading.RLock] = {}

    def provider_health(self) -> tuple[dict[str, object], ...]:
        health = getattr(self.registry, "health", None)
        if not callable(health):
            raise ValueError("registry must expose health()")
        return tuple(health())

    def accounting_summary(self) -> dict[str, dict[str, float]]:
        return self.services.accounting.account_summary()

    def create_conversation(
        self,
        provider_id: str,
        *,
        title: str = "New conversation",
        system_prompt: str = "",
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        adapter = self.registry.get(provider_id)
        identity = adapter.model_identity()
        settings = self.settings.active_profile()
        token_policy = (
            self.token_policies.effective_policy(provider_id, identity["model"])
            if self.token_policies is not None
            else self._builtin_token_policies.resolve(provider_id, identity["model"])
        )
        spec = DirectConversationSpec.create(
            provider_id=provider_id,
            model=identity["model"],
            model_digest=identity.get("model_digest"),
            system_prompt=system_prompt,
            settings=settings,
            model_token_policy=token_policy,
        )
        return self.conversations.create(
            spec,
            title=title,
            conversation_id=conversation_id,
        )

    def _messages_for(
        self,
        conversation: dict[str, Any],
    ) -> tuple[DirectMessage, ...]:
        result: list[DirectMessage] = []
        system_prompt = conversation["system_prompt"]
        if system_prompt:
            result.append(DirectMessage("system", system_prompt))
        result.extend(
            DirectMessage(item["role"], item["content"])
            for item in self.conversations.messages(
                conversation["conversation_id"]
            )
        )
        return tuple(result)

    @staticmethod
    def _context_estimate(messages: tuple[DirectMessage, ...]) -> int:
        byte_count = sum(len(item.content.encode("utf-8")) for item in messages)
        return math.ceil(byte_count / 4)

    @staticmethod
    def _turn_digest(
        conversation_id: str,
        run_id: str,
        policy_snapshot_sha256: str,
    ) -> str:
        document = {
            "schema": "macr_direct_turn_v1",
            "conversation_id": conversation_id,
            "run_id": run_id,
            "policy_snapshot_sha256": policy_snapshot_sha256,
        }
        return hashlib.sha256(
            _canonical_json(document).encode("utf-8")
        ).hexdigest()

    def _context(
        self,
        *,
        provider_id: str,
        run_id: str,
        policy_snapshot_sha256: str,
        origin_native_id: str,
    ) -> DispatchContext:
        is_grok = provider_id == "grok"
        return DispatchContext(
            run_id=run_id,
            plane=InteractionPlane.DIRECT,
            origin=DispatchOrigin(
                "direct_ui",
                "browser_session",
                origin_native_id,
            ),
            authorization=(
                self.grok_admission_authority
                if is_grok
                else self.authority
            ),
            policy_snapshot_sha256=policy_snapshot_sha256,
            project_binding_digest=(
                _DIRECT_GROK_PROJECT.binding_digest if is_grok else None
            ),
            admission_lane=(
                AdmissionLane.INTERACTIVE.value if is_grok else None
            ),
            provider_admission_policy_digest=(
                self.services.provider_admission_for("grok").policy.policy_digest
                if is_grok
                and self.services.provider_admission_for("grok") is not None
                else None
            ),
        )

    def _conversation_lock(self, conversation_id: str) -> threading.RLock:
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ValueError("conversation_id must be non-empty")
        with self._conversation_locks_guard:
            return self._conversation_locks.setdefault(
                conversation_id,
                threading.RLock(),
            )

    def send_message(
        self,
        conversation_id: str,
        content: str,
        *,
        origin_native_id: str,
        run_id: str | None = None,
    ) -> DirectTurnResult:
        with self._conversation_lock(conversation_id):
            return self._send_message_locked(
                conversation_id,
                content,
                origin_native_id=origin_native_id,
                run_id=run_id,
            )

    def _send_message_locked(
        self,
        conversation_id: str,
        content: str,
        *,
        origin_native_id: str,
        run_id: str | None = None,
    ) -> DirectTurnResult:
        conversation = self.conversations.get(conversation_id)
        provider_id = conversation["provider_id"]
        settings = self.settings.get_profile(
            conversation["settings_profile_name"],
            conversation["settings_profile_version"],
        )
        token_json = conversation.get("model_token_policy_json")
        token_digest = conversation.get("model_token_policy_sha256")
        legacy_token_policy_snapshot = False
        if provider_id == "grok" and token_json is None and token_digest is None:
            raise LegacyDirectTokenPolicyIncompatibleError(
                "legacy_direct_token_policy_incompatible: create a new Grok "
                "conversation with a current pinned token policy"
            )
        if token_json is not None or token_digest is not None:
            try:
                token_document = json.loads(token_json)
                validated_digest = None
                if isinstance(token_document, dict) and (
                    "minimum_task_output_tokens" not in token_document
                ):
                    if provider_id == "grok":
                        raise LegacyDirectTokenPolicyIncompatibleError(
                            "legacy_direct_token_policy_incompatible: create a "
                            "new Grok conversation with a current pinned token policy"
                        )
                    if provider_id != "ollama_qwythos":
                        raise ValueError("unsupported legacy Direct token policy")
                    validated_digest = sha256_id(
                        "model_token_policy_v1",
                        token_document,
                    )
                    legacy_token_policy_snapshot = True
                    token_document = {
                        **token_document,
                        "minimum_task_output_tokens": 1,
                    }
                token_policy = ModelTokenPolicy.from_dict(token_document)
                if validated_digest is None:
                    validated_digest = token_policy.policy_digest
            except LegacyDirectTokenPolicyIncompatibleError:
                raise
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise MacrError(
                    "Direct model token policy snapshot is invalid"
                ) from exc
            if (
                validated_digest != token_digest
                or token_policy.provider_id != conversation["provider_id"]
                or token_policy.model_id != conversation["model"]
            ):
                raise MacrError("Direct model token policy snapshot is invalid")
            if not legacy_token_policy_snapshot:
                _, expected_policy_snapshot = canonical_policy_snapshot(
                    settings,
                    token_policy,
                )
                if (
                    expected_policy_snapshot
                    != conversation["policy_snapshot_sha256"]
                ):
                    raise MacrError(
                        "Direct combined policy snapshot is invalid"
                    )
            settings = replace(
                settings,
                max_output_tokens=token_policy.default_output_tokens,
                context_warning_tokens=token_policy.context_warning_tokens,
                hard_context_tokens=token_policy.hard_context_tokens,
            )
        run = run_id or str(uuid.uuid4())
        user = self.conversations.append_user(
            conversation_id,
            content,
            run_id=run,
        )
        self.conversations.start_run(
            run_id=run,
            conversation_id=conversation_id,
            user_ordinal=user["ordinal"],
        )
        messages = self._messages_for(conversation)
        estimate = self._context_estimate(messages)
        projected = estimate + settings.max_output_tokens
        warning = projected >= settings.context_warning_tokens
        if projected > settings.hard_context_tokens:
            self.conversations.fail_run(
                run,
                state="refused_before_network",
                failure_type="ContextLimitExceeded",
            )
            return DirectTurnResult(
                run_id=run,
                conversation_id=conversation_id,
                status="refused_before_network",
                assistant_message=None,
                observation={},
                context_warning=True,
                failure_type="ContextLimitExceeded",
            )

        adapter = self.registry.get(provider_id)
        self.conversations.assert_identity(
            conversation_id,
            provider_id=provider_id,
            model=conversation["model"],
        )
        context = self._context(
            provider_id=provider_id,
            run_id=run,
            policy_snapshot_sha256=conversation["policy_snapshot_sha256"],
            origin_native_id=origin_native_id,
        )
        if provider_id == "grok":
            resource_digest = sha256_id(
                "direct_conversation_resource_v1",
                {
                    "provider_id": provider_id,
                    "conversation_id": conversation_id,
                },
            )
            resource_key = (
                f"{_DIRECT_RESOURCE_PREFIX}:{provider_id}:direct:"
                f"{resource_digest}"
            )
        else:
            resource_key = f"{_DIRECT_RESOURCE_PREFIX}:{provider_id}:direct"
        ttl_seconds = max(1, min(86400, math.ceil(settings.timeout_s) + 60))
        try:
            permit = self.services.admission.admit(
                context,
                resource_key=resource_key,
                provider_id=provider_id,
                task_type=_DIRECT_TASK_TYPE,
                ttl_seconds=ttl_seconds,
            )
        except MacrError as exc:
            failure_type = type(exc).__name__
            self.conversations.fail_run(
                run,
                state="refused_before_network",
                failure_type=failure_type,
            )
            return DirectTurnResult(
                run_id=run,
                conversation_id=conversation_id,
                status="refused_before_network",
                assistant_message=None,
                observation={},
                context_warning=warning,
                failure_type=failure_type,
            )

        provider_kernel = self.services.provider_admission_for(provider_id)
        provider_request: ProviderAdmissionRequest | None = None
        provider_permit: ProviderAdmissionPermit | None = None
        provider_admission_finished = False
        admission_observation: RawProviderObservation | None = None
        try:
            if provider_id == "grok":
                if provider_kernel is None:
                    raise ProviderAdmissionRequiredError(
                        "Grok Direct admission kernel is unavailable"
                    )
                provider_request = ProviderAdmissionRequest(
                    request_id=str(uuid.uuid4()),
                    provider_id=provider_id,
                    project_binding_digest=(
                        _DIRECT_GROK_PROJECT.binding_digest
                    ),
                    lane=AdmissionLane.INTERACTIVE,
                    run_id=run,
                    authorization=context.authorization,
                    plane=InteractionPlane.DIRECT.value,
                    task_type=_DIRECT_TASK_TYPE,
                    task_digest=self._turn_digest(
                        conversation_id,
                        run,
                        conversation["policy_snapshot_sha256"],
                    ),
                    member_digest=None,
                    batch_id=None,
                    provider_tier_binding_digest=None,
                )
                try:
                    provider_permit = provider_kernel.try_admit(
                        provider_request,
                        ttl_seconds=ttl_seconds,
                    )
                except MacrError as exc:
                    if isinstance(exc, ProviderAdmissionError):
                        try:
                            record = provider_kernel.read_request(
                                provider_request.request_id
                            )
                            if record.state == "waiting":
                                provider_kernel.cancel_waiting(
                                    provider_request.request_id,
                                    provider_request.run_id,
                                )
                        except ProviderAdmissionConflict:
                            pass
                    failure_type = type(exc).__name__
                    self.conversations.fail_run(
                        run,
                        state="refused_before_network",
                        failure_type=failure_type,
                    )
                    return DirectTurnResult(
                        run_id=run,
                        conversation_id=conversation_id,
                        status="refused_before_network",
                        assistant_message=None,
                        observation={},
                        context_warning=warning,
                        failure_type=failure_type,
                    )
            dispatch_event_id = str(uuid.uuid4())
            self.services.events.start_run(
                run_id=run,
                dispatch_event_id=dispatch_event_id,
                payload=self._dispatch_payload(
                    provider_id,
                    conversation_id,
                    context,
                    permit.fencing_token,
                ),
            )
            self.services.accounting.record_dispatch(
                run,
                context,
                provider_id=provider_id,
                model=conversation["model"],
                estimate_usd=None,
                soft_warning=False,
            )
            try:
                reply = (
                    adapter.invoke(
                        messages,
                        settings,
                        admission_permit=provider_permit,
                        admission_request=provider_request,
                    )
                    if provider_id == "grok"
                    else adapter.invoke(messages, settings)
                )
                if not isinstance(reply, DirectProviderReply):
                    raise TypeError("Direct adapter returned an invalid reply")
            except Exception as exc:
                known_pre_network = False
                if provider_permit is not None:
                    assert provider_kernel is not None
                    record = provider_kernel.read_request(
                        provider_permit.request_id
                    )
                    known_pre_network = record.state in {
                        "granted",
                        "cancelled",
                    }
                admission_observation = _failed_direct_observation(
                    provider_id,
                    exc,
                    known_pre_network=known_pre_network,
                )
                result = self._finish_failed_exception(
                    conversation_id=conversation_id,
                    run_id=run,
                    context=context,
                    dispatch_event_id=dispatch_event_id,
                    provider_id=provider_id,
                    failure_type=type(exc).__name__,
                    observation=admission_observation,
                    warning=warning,
                )
            else:
                admission_observation = reply.observation
                result = self._finish_reply(
                    conversation=conversation,
                    settings=settings,
                    run_id=run,
                    context=context,
                    dispatch_event_id=dispatch_event_id,
                    reply=reply,
                    estimate=estimate,
                    warning=warning,
                )
            if provider_permit is not None:
                assert provider_kernel is not None
                assert admission_observation is not None
                record = provider_kernel.read_request(
                    provider_permit.request_id
                )
                if record.state == "dispatched":
                    provider_kernel.finish(
                        provider_permit,
                        network_attempted=(
                            admission_observation.network_attempted
                        ),
                        response_received=(
                            admission_observation.response_received
                        ),
                        provider_http_status=(
                            admission_observation.provider_http_status
                        ),
                        terminal_persisted=True,
                        terminal_evidence_digest=sha256_id(
                            "direct_provider_admission_terminal_v1",
                            {
                                "run_id": run,
                                "status": result.status,
                                "failure_type": result.failure_type,
                            },
                        ),
                    )
                elif (
                    record.state == "granted"
                    and admission_observation.network_attempted is False
                ):
                    provider_kernel.cancel_before_transport(provider_permit)
                elif (
                    record.state in {"cancelled", "reconciliation_required"}
                    and admission_observation.network_attempted is False
                ):
                    pass
                else:
                    raise ProviderAdmissionConflict(
                        "Grok Direct admission terminal state is inconsistent"
                    )
                provider_admission_finished = True
            return result
        finally:
            if (
                provider_permit is not None
                and provider_kernel is not None
                and not provider_admission_finished
            ):
                try:
                    record = provider_kernel.read_request(
                        provider_permit.request_id
                    )
                    if record.state == "granted":
                        provider_kernel.cancel_before_transport(
                            provider_permit
                        )
                    elif record.state == "dispatched":
                        observation = (
                            admission_observation
                            if admission_observation is not None
                            else RawProviderObservation.empty(provider_id)
                        )
                        provider_kernel.finish(
                            provider_permit,
                            network_attempted=observation.network_attempted,
                            response_received=observation.response_received,
                            provider_http_status=(
                                observation.provider_http_status
                            ),
                            terminal_persisted=False,
                            terminal_evidence_digest=sha256_id(
                                "direct_provider_admission_incomplete_v1",
                                {"run_id": run},
                            ),
                        )
                except Exception:
                    pass
            self.services.leases.release(
                permit.resource_key,
                permit.run_id,
                permit.fencing_token,
            )

    def delete_conversation(
        self,
        conversation_id: str,
        *,
        confirmation: str,
        origin_native_id: str,
    ) -> dict[str, object]:
        origin = DispatchOrigin(
            "direct_ui",
            "browser_session",
            origin_native_id,
        )
        with self._conversation_lock(conversation_id):
            manifest = self.conversations.deletion_manifest(
                conversation_id,
                confirmation=confirmation,
            )
            candidate_files_removed = 0
            for run_id, provider_id in manifest.run_providers:
                if self.services.vault.purge_direct_run(
                    provider_id,
                    run_id,
                    confirmation=confirmation,
                ):
                    candidate_files_removed += 1
            deletion = self.conversations.delete_permanently(
                conversation_id,
                confirmation=confirmation,
            )
            public = deletion.to_public_dict(
                candidate_files_removed=candidate_files_removed
            )
            self.services.events.append_standalone(
                "direct.conversation_deleted",
                str(uuid.uuid4()),
                {
                    **public,
                    "deletion_mode": "operator_confirmed_privacy_delete",
                    "origin_host": origin.host,
                    "origin_identifier_kind": origin.identifier_kind,
                    "origin_native_id": origin.native_id,
                },
            )
            return public

    def _capture(
        self,
        *,
        provider_id: str,
        conversation_id: str,
        run_id: str,
        context: DispatchContext,
        observation: RawProviderObservation,
    ) -> CandidateCapture | None:
        if observation.answer_bytes is None:
            return None
        return self.services.vault.capture(
            provider_id,
            run_id,
            observation.answer_bytes,
            task_digest=self._turn_digest(
                conversation_id,
                run_id,
                context.policy_snapshot_sha256,
            ),
            approval_digest=context.authorization.digest,
        )

    def _finish_reply(
        self,
        *,
        conversation: dict[str, Any],
        settings: DirectRunSettings,
        run_id: str,
        context: DispatchContext,
        dispatch_event_id: str,
        reply: DirectProviderReply,
        estimate: int,
        warning: bool,
    ) -> DirectTurnResult:
        provider_id = conversation["provider_id"]
        observation = reply.observation
        capture = self._capture(
            provider_id=provider_id,
            conversation_id=conversation["conversation_id"],
            run_id=run_id,
            context=context,
            observation=observation,
        )
        self.services.accounting.record_observation(run_id, observation)
        if (
            settings.budget_behavior == "warn_only"
            and settings.soft_budget_usd is not None
            and observation.currency_cost_usd is not None
            and observation.currency_cost_usd > settings.soft_budget_usd
        ):
            self.services.accounting.mark_soft_warning(run_id)
        candidate_status = (
            "candidate_success"
            if reply.validation_error is None
            else "candidate_failure"
        )
        billing_state = _billing_state(observation)
        self.services.accounting.record_terminal(
            run_id,
            candidate_status=candidate_status,
            billing_state=billing_state,
        )
        self.services.events.finish_run(
            run_id=run_id,
            terminal_event_id=str(uuid.uuid4()),
            state=candidate_status,
            payload=self._terminal_payload(
                provider_id=provider_id,
                conversation_id=conversation["conversation_id"],
                context=context,
                dispatch_event_id=dispatch_event_id,
                observation=observation,
                capture=capture,
                billing_state=billing_state,
                status=candidate_status,
                failure_type=reply.validation_error,
            ),
        )
        if reply.validation_error is not None:
            self.conversations.fail_run(
                run_id,
                state="failed_after_dispatch",
                failure_type=reply.validation_error,
            )
            return DirectTurnResult(
                run_id=run_id,
                conversation_id=conversation["conversation_id"],
                status="failed_after_dispatch",
                assistant_message=None,
                observation=observation.to_public_dict(),
                context_warning=warning,
                failure_type=reply.validation_error,
            )
        answer_bytes = observation.answer_bytes
        if answer_bytes is None:
            raise AssertionError("validated Direct reply must contain answer bytes")
        answer = answer_bytes.decode("utf-8")
        assistant = self.conversations.append_assistant_atomic(
            conversation_id=conversation["conversation_id"],
            run_id=run_id,
            content=answer,
            observation_id=observation.response_id,
            context_estimate=estimate,
            context_warning=warning,
        )
        return DirectTurnResult(
            run_id=run_id,
            conversation_id=conversation["conversation_id"],
            status="completed",
            assistant_message=assistant,
            observation=observation.to_public_dict(),
            context_warning=warning,
            failure_type=None,
        )

    def _finish_failed_exception(
        self,
        *,
        conversation_id: str,
        run_id: str,
        context: DispatchContext,
        dispatch_event_id: str,
        provider_id: str,
        failure_type: str,
        observation: RawProviderObservation,
        warning: bool,
    ) -> DirectTurnResult:
        billing_state = _billing_state(observation)
        self.services.accounting.record_observation(run_id, observation)
        self.services.accounting.record_terminal(
            run_id,
            candidate_status="candidate_failure",
            billing_state=billing_state,
        )
        self.services.events.finish_run(
            run_id=run_id,
            terminal_event_id=str(uuid.uuid4()),
            state="candidate_failure",
            payload=self._terminal_payload(
                provider_id=provider_id,
                conversation_id=conversation_id,
                context=context,
                dispatch_event_id=dispatch_event_id,
                observation=observation,
                capture=None,
                billing_state=billing_state,
                status="candidate_failure",
                failure_type=failure_type,
            ),
        )
        self.conversations.fail_run(
            run_id,
            state="failed_after_dispatch",
            failure_type=failure_type,
        )
        return DirectTurnResult(
            run_id=run_id,
            conversation_id=conversation_id,
            status="failed_after_dispatch",
            assistant_message=None,
            observation=observation.to_public_dict(),
            context_warning=warning,
            failure_type=failure_type,
        )

    @staticmethod
    def _dispatch_payload(
        provider_id: str,
        conversation_id: str,
        context: DispatchContext,
        fencing_token: int,
    ) -> dict[str, Any]:
        return {
            "provider_id": provider_id,
            "task_id": conversation_id,
            "task_type": _DIRECT_TASK_TYPE,
            "interaction_plane": context.plane.value,
            "origin_host": context.origin.host,
            "origin_identifier_kind": context.origin.identifier_kind,
            "origin_native_id": context.origin.native_id,
            "authority_source_kind": context.authorization.source_kind,
            "authority_source_id": context.authorization.source_id,
            "authority_digest": context.authorization.digest,
            "authority_revision": context.authorization.revision,
            "authority_epoch": context.authorization.epoch,
            "authority_scope_sha256": hashlib.sha256(
                context.authorization.scope.encode("utf-8")
            ).hexdigest(),
            "policy_snapshot_sha256": context.policy_snapshot_sha256,
            "project_binding_digest": context.project_binding_digest,
            "admission_lane": context.admission_lane,
            "provider_admission_policy_digest": (
                context.provider_admission_policy_digest
            ),
            "batch_id": None,
            "member_digest": None,
            "relay_is_authorship": False,
            "fencing_token": fencing_token,
        }

    @staticmethod
    def _terminal_payload(
        *,
        provider_id: str,
        conversation_id: str,
        context: DispatchContext,
        dispatch_event_id: str,
        observation: RawProviderObservation,
        capture: CandidateCapture | None,
        billing_state: str,
        status: str,
        failure_type: str | None,
    ) -> dict[str, Any]:
        return {
            "provider_id": provider_id,
            "task_id": conversation_id,
            "dispatch_event_id": dispatch_event_id,
            "status": status,
            "model": observation.model,
            "response_id": observation.response_id,
            "finish_reason": observation.finish_reason,
            "provider_state": observation.provider_state.value,
            "input_tokens": observation.usage.input_tokens,
            "output_tokens": observation.usage.output_tokens,
            "reasoning_tokens": observation.usage.reasoning_tokens,
            "cached_tokens": observation.usage.cached_tokens,
            "currency_cost_usd": observation.currency_cost_usd,
            "cost_kind": observation.cost_kind,
            "pricing_basis_version": observation.pricing_basis_version,
            "duration_ms": observation.duration_ms,
            "input_media_count": None,
            "input_media_bytes": None,
            "output_artifact_count": None,
            "output_artifact_bytes": None,
            "billing_state": billing_state,
            "capture_state": "captured" if capture is not None else "absent",
            "candidate_capture": (
                capture.to_public_dict() if capture is not None else None
            ),
            "return_contract_state": "not_evaluated",
            "return_contract_reason": None,
            "failure_type": failure_type,
            "authority_digest": context.authorization.digest,
            "authority_revision": context.authorization.revision,
            "authority_epoch": context.authorization.epoch,
            "project_binding_digest": context.project_binding_digest,
            "admission_lane": context.admission_lane,
            "provider_admission_policy_digest": (
                context.provider_admission_policy_digest
            ),
        }
