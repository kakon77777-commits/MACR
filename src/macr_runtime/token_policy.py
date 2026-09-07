from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .canonical import sha256_id
from .errors import ProviderOutputBudgetTooSmallError, ProviderPolicyError


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_QWYTHOS_MODEL = "hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M"
_CLOUD_TEXT_QUALITY_FLOOR_TOKENS = 16_384


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded identifier")
    return value


def _model_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value.encode("utf-8")) > 512
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError("model_id must be bounded non-empty text")
    return value


def _positive_int(name: str, value: object, *, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= maximum
    ):
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True)
class ModelTokenPolicy:
    provider_id: str
    model_id: str
    connection_scope: str
    context_warning_tokens: int
    hard_context_tokens: int
    default_output_tokens: int
    max_output_tokens: int
    provider_context_ceiling_tokens: int
    provider_output_ceiling_tokens: int
    policy_source: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_id",
            _identifier("provider_id", self.provider_id),
        )
        object.__setattr__(self, "model_id", _model_id(self.model_id))
        if self.connection_scope not in {"external_https", "loopback_http"}:
            raise ValueError("connection_scope must be external_https or loopback_http")
        context_ceiling = _positive_int(
            "provider_context_ceiling_tokens",
            self.provider_context_ceiling_tokens,
            maximum=10_000_000,
        )
        output_ceiling = _positive_int(
            "provider_output_ceiling_tokens",
            self.provider_output_ceiling_tokens,
            maximum=1_000_000,
        )
        warning = _positive_int(
            "context_warning_tokens",
            self.context_warning_tokens,
            maximum=context_ceiling,
        )
        hard = _positive_int(
            "hard_context_tokens",
            self.hard_context_tokens,
            maximum=context_ceiling,
        )
        default_output = _positive_int(
            "default_output_tokens",
            self.default_output_tokens,
            maximum=output_ceiling,
        )
        max_output = _positive_int(
            "max_output_tokens",
            self.max_output_tokens,
            maximum=output_ceiling,
        )
        if warning >= hard:
            raise ValueError("context warning must be below hard context")
        if default_output > max_output:
            raise ValueError("default output must not exceed max output")
        if (
            self.connection_scope == "external_https"
            and default_output
            < min(
                _CLOUD_TEXT_QUALITY_FLOOR_TOKENS,
                output_ceiling,
            )
        ):
            raise ValueError(
                "external model default output is below the cloud quality floor"
            )
        if max_output >= hard:
            raise ValueError("max output must be below hard context")
        object.__setattr__(
            self,
            "policy_source",
            _identifier("policy_source", self.policy_source),
        )

    @property
    def policy_digest(self) -> str:
        return sha256_id("model_token_policy_v1", self.to_dict())

    @property
    def minimum_task_output_tokens(self) -> int:
        if self.connection_scope != "external_https":
            return 1
        return self.default_output_tokens

    def validate_task_output_tokens(self, requested: int) -> None:
        if requested < self.minimum_task_output_tokens:
            raise ProviderOutputBudgetTooSmallError(
                requested_max_output_tokens=requested,
                minimum_max_output_tokens=self.minimum_task_output_tokens,
                provider_id=self.provider_id,
                model_id=self.model_id,
                model_token_policy_digest=self.policy_digest,
                policy_source=self.policy_source,
            )
        if requested > self.max_output_tokens:
            raise ProviderPolicyError(
                "task output exceeds exact model token policy"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "connection_scope": self.connection_scope,
            "context_warning_tokens": self.context_warning_tokens,
            "hard_context_tokens": self.hard_context_tokens,
            "default_output_tokens": self.default_output_tokens,
            "max_output_tokens": self.max_output_tokens,
            "provider_context_ceiling_tokens": (
                self.provider_context_ceiling_tokens
            ),
            "provider_output_ceiling_tokens": self.provider_output_ceiling_tokens,
            "policy_source": self.policy_source,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ModelTokenPolicy":
        expected = {
            "provider_id",
            "model_id",
            "connection_scope",
            "context_warning_tokens",
            "hard_context_tokens",
            "default_output_tokens",
            "max_output_tokens",
            "provider_context_ceiling_tokens",
            "provider_output_ceiling_tokens",
            "policy_source",
        }
        if not isinstance(data, Mapping) or set(data) != expected:
            raise ValueError("model token policy fields must be exact")
        return cls(**data)


@dataclass(frozen=True)
class ModelTokenOverride:
    provider_id: str
    model_id: str
    revision: int
    context_warning_tokens: int
    hard_context_tokens: int
    default_output_tokens: int
    max_output_tokens: int
    base_policy_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_id",
            _identifier("provider_id", self.provider_id),
        )
        object.__setattr__(self, "model_id", _model_id(self.model_id))
        object.__setattr__(
            self,
            "revision",
            _positive_int("revision", self.revision, maximum=1_000_000),
        )
        for name in (
            "context_warning_tokens",
            "hard_context_tokens",
            "default_output_tokens",
            "max_output_tokens",
        ):
            object.__setattr__(
                self,
                name,
                _positive_int(name, getattr(self, name), maximum=10_000_000),
            )
        object.__setattr__(
            self,
            "base_policy_digest",
            _digest("base_policy_digest", self.base_policy_digest),
        )

    def apply(self, base: ModelTokenPolicy) -> ModelTokenPolicy:
        if not isinstance(base, ModelTokenPolicy):
            raise ValueError("base policy must be a ModelTokenPolicy")
        if (
            base.provider_id != self.provider_id
            or base.model_id != self.model_id
            or base.policy_digest != self.base_policy_digest
        ):
            raise ValueError("override base policy does not match exact model")
        return ModelTokenPolicy(
            provider_id=base.provider_id,
            model_id=base.model_id,
            connection_scope=base.connection_scope,
            context_warning_tokens=self.context_warning_tokens,
            hard_context_tokens=self.hard_context_tokens,
            default_output_tokens=self.default_output_tokens,
            max_output_tokens=self.max_output_tokens,
            provider_context_ceiling_tokens=base.provider_context_ceiling_tokens,
            provider_output_ceiling_tokens=base.provider_output_ceiling_tokens,
            policy_source=f"operator_override:{self.revision}",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "revision": self.revision,
            "context_warning_tokens": self.context_warning_tokens,
            "hard_context_tokens": self.hard_context_tokens,
            "default_output_tokens": self.default_output_tokens,
            "max_output_tokens": self.max_output_tokens,
            "base_policy_digest": self.base_policy_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ModelTokenOverride":
        expected = {
            "provider_id",
            "model_id",
            "revision",
            "context_warning_tokens",
            "hard_context_tokens",
            "default_output_tokens",
            "max_output_tokens",
            "base_policy_digest",
        }
        if not isinstance(data, Mapping) or set(data) != expected:
            raise ValueError("model token override fields must be exact")
        return cls(**data)


def builtin_model_token_policies() -> tuple[ModelTokenPolicy, ...]:
    rows = (
        ("grok", "grok-4.6", "external_https", 180_000, 400_000, 32_768, 65_536, 500_000, 131_072),
        ("grok_standard", "grok-4.3", "external_https", 180_000, 400_000, 32_768, 65_536, 1_000_000, 131_072),
        ("glm_flash_worker", "glm-5.3-flash", "external_https", 400_000, 512_000, 16_384, 65_536, 1_000_000, 131_072),
        ("google_gemini", "gemini-3.7-flash", "external_https", 400_000, 512_000, 16_384, 65_536, 1_048_576, 65_536),
        ("minimax", "MiniMax-M2.7", "external_https", 160_000, 180_000, 2_048, 2_048, 204_800, 2_048),
        ("minimax", "MiniMax-M2.7-highspeed", "external_https", 160_000, 180_000, 2_048, 2_048, 204_800, 2_048),
        ("ollama_qwythos", _QWYTHOS_MODEL, "loopback_http", 7_000, 8_192, 4_096, 4_096, 8_192, 4_096),
    )
    return tuple(
        ModelTokenPolicy(
            provider_id=provider_id,
            model_id=model_id,
            connection_scope=scope,
            context_warning_tokens=warning,
            hard_context_tokens=hard,
            default_output_tokens=default_output,
            max_output_tokens=max_output,
            provider_context_ceiling_tokens=context_ceiling,
            provider_output_ceiling_tokens=output_ceiling,
            policy_source="built_in",
        )
        for (
            provider_id,
            model_id,
            scope,
            warning,
            hard,
            default_output,
            max_output,
            context_ceiling,
            output_ceiling,
        ) in rows
    )


class ModelTokenPolicyResolver:
    def __init__(self, policies: Iterable[ModelTokenPolicy]) -> None:
        if isinstance(policies, (str, bytes)):
            raise ValueError("policies must contain ModelTokenPolicy values")
        items = tuple(policies)
        if not items or any(not isinstance(item, ModelTokenPolicy) for item in items):
            raise ValueError("policies must contain ModelTokenPolicy values")
        keys = tuple((item.provider_id, item.model_id) for item in items)
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate exact model token policy")
        self._by_key = dict(zip(keys, items))

    @classmethod
    def builtins_only(cls) -> "ModelTokenPolicyResolver":
        return cls(builtin_model_token_policies())

    def resolve(self, provider_id: str, model_id: str) -> ModelTokenPolicy:
        key = (_identifier("provider_id", provider_id), _model_id(model_id))
        try:
            return self._by_key[key]
        except KeyError as exc:
            raise ProviderPolicyError(
                "no exact model token policy is configured"
            ) from exc

    def policies(self) -> tuple[ModelTokenPolicy, ...]:
        return tuple(self._by_key[key] for key in sorted(self._by_key))


def t1_glm_live_policy() -> ModelTokenPolicy:
    return ModelTokenPolicy(
        provider_id="glm_flash_worker",
        model_id="glm-5.3-flash",
        connection_scope="external_https",
        context_warning_tokens=100_000,
        hard_context_tokens=128_000,
        default_output_tokens=16_384,
        max_output_tokens=16_384,
        provider_context_ceiling_tokens=1_000_000,
        provider_output_ceiling_tokens=131_072,
        policy_source="t1_live_preset",
    )


__all__ = [
    "ModelTokenOverride",
    "ModelTokenPolicy",
    "ModelTokenPolicyResolver",
    "builtin_model_token_policies",
    "t1_glm_live_policy",
]
