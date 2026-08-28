from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .authority import AuthorityScope
from .candidate_vault import CandidateCapture
from .direct_contracts import (
    DirectConversationSpec,
    DirectMessage,
    DirectRunSettings,
    DirectTurnResult,
)
from .direct_providers import DirectProviderReply
from .direct_settings import DirectSettingsStore
from .direct_store import DirectConversationStore
from .errors import MacrError
from .execution import (
    AuthorizationReference,
    DispatchContext,
    DispatchOrigin,
    InteractionPlane,
    RawProviderObservation,
)
from .runtime import RuntimeServices


_DIRECT_TASK_TYPE = "direct_chat"
_DIRECT_RESOURCE_PREFIX = "provider"


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
            providers=("grok", "ollama_qwythos"),
            planes=(InteractionPlane.DIRECT.value,),
            task_types=(_DIRECT_TASK_TYPE,),
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
    ) -> None:
        if not isinstance(services, RuntimeServices):
            raise ValueError("services must be RuntimeServices")
        if not isinstance(conversations, DirectConversationStore):
            raise ValueError("conversations must be DirectConversationStore")
        if not isinstance(settings, DirectSettingsStore):
            raise ValueError("settings must be DirectSettingsStore")
        if not isinstance(authority, AuthorizationReference):
            raise ValueError("authority must be AuthorizationReference")
        if not callable(getattr(registry, "get", None)):
            raise ValueError("registry must expose get(provider_id)")
        self.registry = registry
        self.services = services
        self.conversations = conversations
        self.settings = settings
        self.authority = authority

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
        spec = DirectConversationSpec.create(
            provider_id=provider_id,
            model=identity["model"],
            model_digest=identity.get("model_digest"),
            system_prompt=system_prompt,
            settings=settings,
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
        run_id: str,
        policy_snapshot_sha256: str,
        origin_native_id: str,
    ) -> DispatchContext:
        return DispatchContext(
            run_id=run_id,
            plane=InteractionPlane.DIRECT,
            origin=DispatchOrigin(
                "direct_ui",
                "browser_session",
                origin_native_id,
            ),
            authorization=self.authority,
            policy_snapshot_sha256=policy_snapshot_sha256,
        )

    def send_message(
        self,
        conversation_id: str,
        content: str,
        *,
        origin_native_id: str,
        run_id: str | None = None,
    ) -> DirectTurnResult:
        conversation = self.conversations.get(conversation_id)
        settings = self.settings.get_profile(
            conversation["settings_profile_name"],
            conversation["settings_profile_version"],
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

        provider_id = conversation["provider_id"]
        adapter = self.registry.get(provider_id)
        self.conversations.assert_identity(
            conversation_id,
            provider_id=provider_id,
            model=conversation["model"],
        )
        context = self._context(
            run_id=run,
            policy_snapshot_sha256=conversation["policy_snapshot_sha256"],
            origin_native_id=origin_native_id,
        )
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

        dispatch_event_id = str(uuid.uuid4())
        try:
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
                reply = adapter.invoke(messages, settings)
                if not isinstance(reply, DirectProviderReply):
                    raise TypeError("Direct adapter returned an invalid reply")
            except Exception as exc:
                return self._finish_failed_exception(
                    conversation_id=conversation_id,
                    run_id=run,
                    context=context,
                    dispatch_event_id=dispatch_event_id,
                    provider_id=provider_id,
                    failure_type=type(exc).__name__,
                    warning=warning,
                )
            return self._finish_reply(
                conversation=conversation,
                settings=settings,
                run_id=run,
                context=context,
                dispatch_event_id=dispatch_event_id,
                reply=reply,
                estimate=estimate,
                warning=warning,
            )
        finally:
            self.services.leases.release(
                permit.resource_key,
                permit.run_id,
                permit.fencing_token,
            )

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
        warning: bool,
    ) -> DirectTurnResult:
        observation = RawProviderObservation.empty(provider_id)
        self.services.accounting.record_observation(run_id, observation)
        self.services.accounting.record_terminal(
            run_id,
            candidate_status="candidate_failure",
            billing_state="unknown_after_dispatch",
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
                billing_state="unknown_after_dispatch",
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
        }
