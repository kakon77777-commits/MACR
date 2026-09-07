from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .canonical import sha256_id
from .errors import ProviderPolicyError


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GLM_PROVIDER = "glm_flash_worker"
_GLM_MODEL = "glm-5.3-flash"


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


def _string_tuple(name: str, value: object) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise ValueError(f"{name} must be an array of identifiers")
    try:
        items = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError(f"{name} must be an array of identifiers") from exc
    normalized = tuple(sorted(_identifier(name, item) for item in items))
    if not normalized or len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} must contain unique identifiers")
    return normalized


@dataclass(frozen=True)
class ProviderTierBinding:
    provider_id: str
    model_id: str
    tier_id: str
    revision: int
    complete_policy_digest: str
    max_latency_s: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_id",
            _identifier("provider_id", self.provider_id),
        )
        object.__setattr__(self, "model_id", _model_id(self.model_id))
        object.__setattr__(self, "tier_id", _identifier("tier_id", self.tier_id))
        object.__setattr__(
            self,
            "revision",
            _positive_int("revision", self.revision, maximum=1_000_000),
        )
        object.__setattr__(
            self,
            "complete_policy_digest",
            _digest("complete_policy_digest", self.complete_policy_digest),
        )
        object.__setattr__(
            self,
            "max_latency_s",
            _positive_int(
                "max_latency_s",
                self.max_latency_s,
                maximum=86_400,
            ),
        )

    @property
    def binding_digest(self) -> str:
        return sha256_id("provider_tier_binding_v1", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "tier_id": self.tier_id,
            "revision": self.revision,
            "complete_policy_digest": self.complete_policy_digest,
            "effective_limits": {"max_latency_s": self.max_latency_s},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProviderTierBinding":
        expected = {
            "provider_id",
            "model_id",
            "tier_id",
            "revision",
            "complete_policy_digest",
            "effective_limits",
        }
        if not isinstance(data, Mapping) or set(data) != expected:
            raise ValueError("provider tier binding fields must be exact")
        limits = data["effective_limits"]
        if not isinstance(limits, Mapping) or set(limits) != {"max_latency_s"}:
            raise ValueError("provider tier binding effective limits must be exact")
        return cls(
            provider_id=data["provider_id"],
            model_id=data["model_id"],
            tier_id=data["tier_id"],
            revision=data["revision"],
            complete_policy_digest=data["complete_policy_digest"],
            max_latency_s=limits["max_latency_s"],
        )


@dataclass(frozen=True)
class ProviderCapabilityPolicy:
    provider_id: str
    model_id: str
    tier_id: str
    revision: int
    allowed_task_types: tuple[str, ...]
    delegation_class: str
    approved_privacy: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    max_latency_s: int
    patch_allowed: bool
    write_scope_allowed: bool
    tools_allowed: bool
    verification_required: bool
    policy_source: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_id",
            _identifier("provider_id", self.provider_id),
        )
        object.__setattr__(self, "model_id", _model_id(self.model_id))
        object.__setattr__(self, "tier_id", _identifier("tier_id", self.tier_id))
        object.__setattr__(
            self,
            "revision",
            _positive_int("revision", self.revision, maximum=1_000_000),
        )
        object.__setattr__(
            self,
            "allowed_task_types",
            _string_tuple("allowed_task_types", self.allowed_task_types),
        )
        object.__setattr__(
            self,
            "delegation_class",
            _identifier("delegation_class", self.delegation_class),
        )
        object.__setattr__(
            self,
            "approved_privacy",
            _string_tuple("approved_privacy", self.approved_privacy),
        )
        object.__setattr__(
            self,
            "required_capabilities",
            _string_tuple("required_capabilities", self.required_capabilities),
        )
        object.__setattr__(
            self,
            "max_latency_s",
            _positive_int(
                "max_latency_s",
                self.max_latency_s,
                maximum=86_400,
            ),
        )
        for name in (
            "patch_allowed",
            "write_scope_allowed",
            "tools_allowed",
            "verification_required",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be boolean")
        object.__setattr__(
            self,
            "policy_source",
            _identifier("policy_source", self.policy_source),
        )

    @property
    def complete_policy_digest(self) -> str:
        return sha256_id("provider_capability_policy_v1", self.to_dict())

    def binding(self) -> ProviderTierBinding:
        return ProviderTierBinding(
            provider_id=self.provider_id,
            model_id=self.model_id,
            tier_id=self.tier_id,
            revision=self.revision,
            complete_policy_digest=self.complete_policy_digest,
            max_latency_s=self.max_latency_s,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "tier_id": self.tier_id,
            "revision": self.revision,
            "allowed_task_types": list(self.allowed_task_types),
            "delegation_class": self.delegation_class,
            "approved_privacy": list(self.approved_privacy),
            "required_capabilities": list(self.required_capabilities),
            "max_latency_s": self.max_latency_s,
            "patch_allowed": self.patch_allowed,
            "write_scope_allowed": self.write_scope_allowed,
            "tools_allowed": self.tools_allowed,
            "verification_required": self.verification_required,
            "policy_source": self.policy_source,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProviderCapabilityPolicy":
        expected = {
            "provider_id",
            "model_id",
            "tier_id",
            "revision",
            "allowed_task_types",
            "delegation_class",
            "approved_privacy",
            "required_capabilities",
            "max_latency_s",
            "patch_allowed",
            "write_scope_allowed",
            "tools_allowed",
            "verification_required",
            "policy_source",
        }
        if not isinstance(data, Mapping) or set(data) != expected:
            raise ValueError("provider capability policy fields must be exact")
        return cls(**data)


def glm_standard_policy() -> ProviderCapabilityPolicy:
    return ProviderCapabilityPolicy(
        provider_id=_GLM_PROVIDER,
        model_id=_GLM_MODEL,
        tier_id="standard",
        revision=1,
        allowed_task_types=("delegated_routine", "provider_conformance"),
        delegation_class="non_sensitive_routine",
        approved_privacy=("internal_approved", "public"),
        required_capabilities=("text_generation",),
        max_latency_s=300,
        patch_allowed=False,
        write_scope_allowed=False,
        tools_allowed=False,
        verification_required=True,
        policy_source="built_in",
    )


def glm_extended_text_policy() -> ProviderCapabilityPolicy:
    return ProviderCapabilityPolicy(
        provider_id=_GLM_PROVIDER,
        model_id=_GLM_MODEL,
        tier_id="extended_text_candidate",
        revision=1,
        allowed_task_types=(
            "delegated_analysis",
            "delegated_code",
            "delegated_review",
            "delegated_routine",
            "provider_conformance",
        ),
        delegation_class="non_sensitive_routine",
        approved_privacy=("internal_approved", "public"),
        required_capabilities=("text_generation",),
        max_latency_s=900,
        patch_allowed=False,
        write_scope_allowed=False,
        tools_allowed=False,
        verification_required=True,
        policy_source="built_in",
    )


def builtin_provider_capability_policies() -> tuple[ProviderCapabilityPolicy, ...]:
    return (glm_extended_text_policy(), glm_standard_policy())


class ProviderCapabilityResolver:
    def __init__(self, policies: Iterable[ProviderCapabilityPolicy]) -> None:
        if isinstance(policies, (str, bytes)):
            raise ValueError("policies must contain ProviderCapabilityPolicy values")
        items = tuple(policies)
        if not items or any(
            not isinstance(item, ProviderCapabilityPolicy) for item in items
        ):
            raise ValueError("policies must contain ProviderCapabilityPolicy values")
        keys = tuple(
            (item.provider_id, item.model_id, item.tier_id, item.revision)
            for item in items
        )
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate provider capability policy")
        self._by_key = dict(zip(keys, items))

    @classmethod
    def builtins_only(cls) -> "ProviderCapabilityResolver":
        return cls(builtin_provider_capability_policies())

    def resolve(
        self,
        provider_id: str,
        model_id: str,
        tier_id: str,
        revision: int,
    ) -> ProviderCapabilityPolicy:
        key = (
            _identifier("provider_id", provider_id),
            _model_id(model_id),
            _identifier("tier_id", tier_id),
            _positive_int("revision", revision, maximum=1_000_000),
        )
        try:
            return self._by_key[key]
        except KeyError as exc:
            raise ProviderPolicyError(
                "no exact provider capability policy is configured"
            ) from exc

    def default_binding(
        self,
        provider_id: str,
        model_id: str,
    ) -> ProviderTierBinding:
        try:
            return self.resolve(provider_id, model_id, "standard", 1).binding()
        except ProviderPolicyError as exc:
            raise ValueError("no default provider capability policy is configured") from exc

    def policies(self) -> tuple[ProviderCapabilityPolicy, ...]:
        return tuple(self._by_key[key] for key in sorted(self._by_key))


__all__ = [
    "ProviderCapabilityPolicy",
    "ProviderCapabilityResolver",
    "ProviderTierBinding",
    "builtin_provider_capability_policies",
    "glm_extended_text_policy",
    "glm_standard_policy",
]
