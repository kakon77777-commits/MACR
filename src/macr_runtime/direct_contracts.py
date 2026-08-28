from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GROK_MODEL = "grok-4.6"
_QWYTHOS_MODEL = "hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M"
_MESSAGE_ROLES = frozenset({"system", "user", "assistant"})
_TURN_STATES = frozenset(
    {
        "completed",
        "refused_before_network",
        "failed_after_dispatch",
        "unsettled",
    }
)


def _bounded_text(
    name: str,
    value: str,
    *,
    maximum: int,
    allow_blank: bool = False,
    preserve: bool = False,
) -> str:
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f"{name} must be a bounded string")
    if not allow_blank and not value.strip():
        raise ValueError(f"{name} must be a bounded non-empty string")
    return value if preserve else value.strip()


def _positive_int(name: str, value: int, *, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= maximum
    ):
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


def _finite_number(
    name: str,
    value: float,
    *,
    minimum: float,
    maximum: float,
    minimum_inclusive: bool = True,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    normalized = float(value)
    lower_ok = normalized >= minimum if minimum_inclusive else normalized > minimum
    if not math.isfinite(normalized) or not lower_ok or normalized > maximum:
        raise ValueError(f"{name} is outside the supported range")
    return normalized


def _uuid4(name: str, value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a UUIDv4 string") from exc
    if parsed.version != 4 or str(parsed) != value.lower():
        raise ValueError(f"{name} must be a UUIDv4 string")
    return str(parsed)


class DirectProviderId(str, Enum):
    GROK = "grok"
    QWYTHOS = "ollama_qwythos"

    @classmethod
    def _missing_(cls, value: object) -> None:
        raise ValueError(
            "Direct provider must be grok or ollama_qwythos"
        )


@dataclass(frozen=True)
class DirectMessage:
    role: str
    content: str

    def __post_init__(self) -> None:
        role = _bounded_text("message role", self.role, maximum=16)
        if role not in _MESSAGE_ROLES:
            raise ValueError("message role is not supported")
        object.__setattr__(self, "role", role)
        object.__setattr__(
            self,
            "content",
            _bounded_text(
                "message content",
                self.content,
                maximum=1_048_576,
                preserve=True,
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class DirectRunSettings:
    profile_name: str
    profile_version: int
    max_output_tokens: int
    timeout_s: float
    temperature: float
    top_p: float
    context_warning_tokens: int
    hard_context_tokens: int
    budget_behavior: str
    soft_budget_usd: float | None
    provider_improvement_preference: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "profile_name",
            _bounded_text("profile_name", self.profile_name, maximum=128),
        )
        object.__setattr__(
            self,
            "profile_version",
            _positive_int("profile_version", self.profile_version, maximum=1_000_000),
        )
        object.__setattr__(
            self,
            "max_output_tokens",
            _positive_int(
                "max_output_tokens",
                self.max_output_tokens,
                maximum=131_072,
            ),
        )
        object.__setattr__(
            self,
            "timeout_s",
            _finite_number(
                "timeout_s",
                self.timeout_s,
                minimum=0.001,
                maximum=3600.0,
            ),
        )
        object.__setattr__(
            self,
            "temperature",
            _finite_number(
                "temperature",
                self.temperature,
                minimum=0.0,
                maximum=2.0,
            ),
        )
        object.__setattr__(
            self,
            "top_p",
            _finite_number(
                "top_p",
                self.top_p,
                minimum=0.0,
                maximum=1.0,
                minimum_inclusive=False,
            ),
        )
        warning = _positive_int(
            "context_warning_tokens",
            self.context_warning_tokens,
            maximum=10_000_000,
        )
        hard = _positive_int(
            "hard_context_tokens",
            self.hard_context_tokens,
            maximum=10_000_000,
        )
        if warning >= hard:
            raise ValueError(
                "context_warning_tokens must be below hard_context_tokens"
            )
        object.__setattr__(self, "context_warning_tokens", warning)
        object.__setattr__(self, "hard_context_tokens", hard)
        if self.budget_behavior not in {"warn_only", "hard_cap"}:
            raise ValueError("budget_behavior must be warn_only or hard_cap")
        if self.soft_budget_usd is not None:
            object.__setattr__(
                self,
                "soft_budget_usd",
                _finite_number(
                    "soft_budget_usd",
                    self.soft_budget_usd,
                    minimum=0.0,
                    maximum=1_000_000_000.0,
                ),
            )
        if self.provider_improvement_preference not in {
            "allowed",
            "disabled",
            "not_asserted",
        }:
            raise ValueError(
                "provider_improvement_preference is not supported"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "profile_name": self.profile_name,
            "profile_version": self.profile_version,
            "max_output_tokens": self.max_output_tokens,
            "timeout_s": self.timeout_s,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "context_warning_tokens": self.context_warning_tokens,
            "hard_context_tokens": self.hard_context_tokens,
            "budget_behavior": self.budget_behavior,
            "soft_budget_usd": self.soft_budget_usd,
            "provider_improvement_preference": (
                self.provider_improvement_preference
            ),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DirectRunSettings":
        if not isinstance(data, Mapping):
            raise ValueError("Direct settings must be an object")
        expected = {
            "profile_name",
            "profile_version",
            "max_output_tokens",
            "timeout_s",
            "temperature",
            "top_p",
            "context_warning_tokens",
            "hard_context_tokens",
            "budget_behavior",
            "soft_budget_usd",
            "provider_improvement_preference",
        }
        if set(data) != expected:
            raise ValueError("Direct settings fields are incomplete or unknown")
        return cls(**dict(data))


def canonical_policy_snapshot(
    settings: DirectRunSettings,
) -> tuple[str, str]:
    if not isinstance(settings, DirectRunSettings):
        raise ValueError("settings must be DirectRunSettings")
    document = {
        "schema": "macr_direct_policy_v1",
        **settings.to_dict(),
    }
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DirectConversationSpec:
    provider_id: DirectProviderId
    model: str
    model_digest: str | None
    system_prompt: str
    system_prompt_sha256: str
    settings_profile_name: str
    settings_profile_version: int
    policy_snapshot_sha256: str
    encryption: str
    dataset_role: str
    training_eligible: bool
    provider_improvement_preference: str

    @classmethod
    def create(
        cls,
        *,
        provider_id: DirectProviderId | str,
        model: str,
        system_prompt: str,
        settings: DirectRunSettings,
        model_digest: str | None = None,
    ) -> "DirectConversationSpec":
        provider = DirectProviderId(provider_id)
        requested_model = _bounded_text("model", model, maximum=512)
        expected_model = (
            _GROK_MODEL
            if provider is DirectProviderId.GROK
            else _QWYTHOS_MODEL
        )
        if requested_model != expected_model:
            raise ValueError(
                f"Direct provider model must remain pinned to {expected_model}"
            )
        if not isinstance(settings, DirectRunSettings):
            raise ValueError("settings must be DirectRunSettings")
        if not isinstance(system_prompt, str) or len(system_prompt) > 262_144:
            raise ValueError("system_prompt must be a bounded string")
        normalized_digest: str | None = None
        if provider is DirectProviderId.QWYTHOS:
            normalized_digest = (
                model_digest.lower() if isinstance(model_digest, str) else ""
            )
            if not _SHA256.fullmatch(normalized_digest):
                raise ValueError(
                    "Qwythos model_digest must be a SHA-256 hex digest"
                )
        elif model_digest is not None:
            raise ValueError("Grok model_digest must be omitted")
        _, policy_digest = canonical_policy_snapshot(settings)
        return cls(
            provider_id=provider,
            model=requested_model,
            model_digest=normalized_digest,
            system_prompt=system_prompt,
            system_prompt_sha256=hashlib.sha256(
                system_prompt.encode("utf-8")
            ).hexdigest(),
            settings_profile_name=settings.profile_name,
            settings_profile_version=settings.profile_version,
            policy_snapshot_sha256=policy_digest,
            encryption="none",
            dataset_role=(
                "archive_only"
                if provider is DirectProviderId.GROK
                else "eval_only"
            ),
            training_eligible=False,
            provider_improvement_preference=(
                settings.provider_improvement_preference
            ),
        )


@dataclass(frozen=True)
class DirectTurnResult:
    run_id: str
    conversation_id: str
    status: str
    assistant_message: Mapping[str, Any] | None
    observation: Mapping[str, Any]
    context_warning: bool
    failure_type: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _uuid4("run_id", self.run_id))
        object.__setattr__(
            self,
            "conversation_id",
            _uuid4("conversation_id", self.conversation_id),
        )
        if self.status not in _TURN_STATES:
            raise ValueError("Direct turn status is not supported")
        if self.assistant_message is not None and not isinstance(
            self.assistant_message,
            Mapping,
        ):
            raise ValueError("assistant_message must be an object or None")
        if not isinstance(self.observation, Mapping):
            raise ValueError("observation must be an object")
        if not isinstance(self.context_warning, bool):
            raise ValueError("context_warning must be boolean")
        if self.failure_type is not None:
            object.__setattr__(
                self,
                "failure_type",
                _bounded_text("failure_type", self.failure_type, maximum=128),
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "conversation_id": self.conversation_id,
            "status": self.status,
            "assistant_message": (
                dict(self.assistant_message)
                if self.assistant_message is not None
                else None
            ),
            "observation": dict(self.observation),
            "context_warning": self.context_warning,
            "failure_type": self.failure_type,
        }
