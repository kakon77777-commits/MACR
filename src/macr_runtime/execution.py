from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Any, Mapping

from .contracts import ProviderResult


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_TELEMETRY_IDENTIFIER = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
)


def _non_empty(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_string(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    return _non_empty(name, value)


def _digest(name: str, value: str) -> str:
    normalized = value.lower() if isinstance(value, str) else ""
    if not _SHA256.fullmatch(normalized):
        raise ValueError(f"{name} must be a SHA-256 hex digest")
    return normalized


def _optional_non_negative_int(name: str, value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer or None")
    return value


def _optional_non_negative_float(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite non-negative number or None")
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0:
        raise ValueError(f"{name} must be a finite non-negative number or None")
    return normalized


def _optional_boolean(name: str, value: bool | None) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean or None")
    return value


def _optional_http_status(name: str, value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 100 <= value <= 599:
        raise ValueError(f"{name} must be an HTTP status or None")
    return value


def _optional_telemetry_identifier(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _SAFE_TELEMETRY_IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded identifier or None")
    return value


def _uuid4(name: str, value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a UUIDv4 string") from exc
    if parsed.version != 4 or str(parsed) != value.lower():
        raise ValueError(f"{name} must be a UUIDv4 string")
    return str(parsed)


class InteractionPlane(str, Enum):
    DIRECT = "direct"
    DELEGATION = "delegation"


class ProviderState(str, Enum):
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    MALFORMED = "malformed"


class CaptureState(str, Enum):
    CAPTURED = "captured"
    ABSENT = "absent"


class ReturnContractState(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    NOT_EVALUATED = "not_evaluated"


class MaterializationState(str, Enum):
    NONE = "none"
    VERBATIM = "verbatim"
    TRANSFORMED = "transformed"


class VerificationState(str, Enum):
    NOT_RUN = "not_run"
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"


class AcceptanceState(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class DispatchOrigin:
    host: str
    identifier_kind: str
    native_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "host", _non_empty("origin host", self.host))
        object.__setattr__(
            self,
            "identifier_kind",
            _non_empty("origin identifier_kind", self.identifier_kind),
        )
        object.__setattr__(
            self,
            "native_id",
            _non_empty("origin native_id", self.native_id),
        )


@dataclass(frozen=True)
class AuthorizationReference:
    source_kind: str
    source_id: str
    digest: str
    revision: int
    epoch: int
    scope: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_kind",
            _non_empty("authorization source_kind", self.source_kind),
        )
        object.__setattr__(
            self,
            "source_id",
            _non_empty("authorization source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "digest",
            _digest("authorization digest", self.digest),
        )
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision < 1
        ):
            raise ValueError("authorization revision must be a positive integer")
        if (
            isinstance(self.epoch, bool)
            or not isinstance(self.epoch, int)
            or self.epoch < 0
        ):
            raise ValueError("authorization epoch must be a non-negative integer")
        object.__setattr__(
            self,
            "scope",
            _non_empty("authorization scope", self.scope),
        )


@dataclass(frozen=True)
class DispatchContext:
    run_id: str
    plane: InteractionPlane
    origin: DispatchOrigin
    authorization: AuthorizationReference
    policy_snapshot_sha256: str
    batch_id: str | None = None
    member_digest: str | None = None
    relay_is_authorship: bool = False
    plan_digest: str | None = None
    plan_revision: int | None = None
    role_slot_id: str | None = None
    route_id: str | None = None
    model_token_policy_digest: str | None = None
    provider_tier_binding_digest: str | None = None
    project_binding_digest: str | None = None
    admission_lane: str | None = None
    provider_admission_policy_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _uuid4("run_id", self.run_id))
        if not isinstance(self.plane, InteractionPlane):
            raise ValueError("plane must be an InteractionPlane")
        if not isinstance(self.origin, DispatchOrigin):
            raise ValueError("origin must be a DispatchOrigin")
        if not isinstance(self.authorization, AuthorizationReference):
            raise ValueError("authorization must be an AuthorizationReference")
        object.__setattr__(
            self,
            "policy_snapshot_sha256",
            _digest("policy_snapshot_sha256", self.policy_snapshot_sha256),
        )
        object.__setattr__(
            self,
            "batch_id",
            _optional_string("batch_id", self.batch_id),
        )
        if self.member_digest is not None:
            object.__setattr__(
                self,
                "member_digest",
                _digest("member_digest", self.member_digest),
            )
        if self.relay_is_authorship is not False:
            raise ValueError("relay_is_authorship must remain false")
        if self.plan_digest is not None:
            object.__setattr__(
                self,
                "plan_digest",
                _digest("plan_digest", self.plan_digest),
            )
        if self.plan_revision is not None and (
            isinstance(self.plan_revision, bool)
            or not isinstance(self.plan_revision, int)
            or self.plan_revision < 1
        ):
            raise ValueError("plan_revision must be a positive integer or None")
        object.__setattr__(
            self,
            "role_slot_id",
            _optional_string("role_slot_id", self.role_slot_id),
        )
        if self.route_id is not None:
            object.__setattr__(
                self,
                "route_id",
                _digest("route_id", self.route_id),
            )
        if self.model_token_policy_digest is not None:
            object.__setattr__(
                self,
                "model_token_policy_digest",
                _digest(
                    "model_token_policy_digest",
                    self.model_token_policy_digest,
                ),
            )
        if self.provider_tier_binding_digest is not None:
            object.__setattr__(
                self,
                "provider_tier_binding_digest",
                _digest(
                    "provider_tier_binding_digest",
                    self.provider_tier_binding_digest,
                ),
            )
        if self.project_binding_digest is not None:
            object.__setattr__(
                self,
                "project_binding_digest",
                _digest(
                    "project_binding_digest",
                    self.project_binding_digest,
                ),
            )
        if self.admission_lane is not None:
            if self.admission_lane not in {"interactive", "routine", "bulk"}:
                raise ValueError("admission_lane is invalid")
        if self.provider_admission_policy_digest is not None:
            object.__setattr__(
                self,
                "provider_admission_policy_digest",
                _digest(
                    "provider_admission_policy_digest",
                    self.provider_admission_policy_digest,
                ),
            )


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    cached_tokens: int | None

    def __post_init__(self) -> None:
        for name in (
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "cached_tokens",
        ):
            object.__setattr__(
                self,
                name,
                _optional_non_negative_int(name, getattr(self, name)),
            )


@dataclass(frozen=True)
class RawProviderObservation:
    provider_id: str
    model: str | None
    response_id: str | None
    finish_reason: str | None
    usage: ProviderUsage
    currency_cost_usd: float | None
    cost_kind: str | None
    pricing_basis_version: str | None
    duration_ms: int | None
    answer_bytes: bytes | None
    provider_state: ProviderState
    network_attempted: bool | None = None
    response_received: bool | None = None
    provider_http_status: int | None = None
    provider_error_code: str | None = None
    transport_stage: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_id",
            _non_empty("provider_id", self.provider_id),
        )
        for name in (
            "model",
            "response_id",
            "finish_reason",
            "cost_kind",
            "pricing_basis_version",
        ):
            object.__setattr__(
                self,
                name,
                _optional_string(name, getattr(self, name)),
            )
        if not isinstance(self.usage, ProviderUsage):
            raise ValueError("usage must be a ProviderUsage")
        object.__setattr__(
            self,
            "currency_cost_usd",
            _optional_non_negative_float(
                "currency_cost_usd",
                self.currency_cost_usd,
            ),
        )
        object.__setattr__(
            self,
            "duration_ms",
            _optional_non_negative_int("duration_ms", self.duration_ms),
        )
        if self.answer_bytes is not None and not isinstance(self.answer_bytes, bytes):
            raise ValueError("answer_bytes must be bytes or None")
        if not isinstance(self.provider_state, ProviderState):
            raise ValueError("provider_state must be a ProviderState")
        object.__setattr__(
            self,
            "network_attempted",
            _optional_boolean("network_attempted", self.network_attempted),
        )
        object.__setattr__(
            self,
            "response_received",
            _optional_boolean("response_received", self.response_received),
        )
        object.__setattr__(
            self,
            "provider_http_status",
            _optional_http_status(
                "provider_http_status",
                self.provider_http_status,
            ),
        )
        object.__setattr__(
            self,
            "provider_error_code",
            _optional_telemetry_identifier(
                "provider_error_code",
                self.provider_error_code,
            ),
        )
        object.__setattr__(
            self,
            "transport_stage",
            _optional_telemetry_identifier(
                "transport_stage",
                self.transport_stage,
            ),
        )
        if self.response_received is True and self.network_attempted is not True:
            raise ValueError("response_received requires network_attempted")
        if (
            self.provider_http_status is not None
            or self.provider_error_code is not None
        ) and self.response_received is not True:
            raise ValueError(
                "provider response telemetry requires response_received"
            )

    @classmethod
    def empty(
        cls,
        provider_id: str,
        *,
        duration_ms: int | None = None,
        network_attempted: bool | None = None,
        response_received: bool | None = None,
        provider_http_status: int | None = None,
        provider_error_code: str | None = None,
        transport_stage: str | None = None,
    ) -> "RawProviderObservation":
        return cls(
            provider_id=provider_id,
            model=None,
            response_id=None,
            finish_reason=None,
            usage=ProviderUsage(None, None, None, None),
            currency_cost_usd=None,
            cost_kind=None,
            pricing_basis_version=None,
            duration_ms=duration_ms,
            answer_bytes=None,
            provider_state=ProviderState.MALFORMED,
            network_attempted=network_attempted,
            response_received=response_received,
            provider_http_status=provider_http_status,
            provider_error_code=provider_error_code,
            transport_stage=transport_stage,
        )

    def to_public_dict(self) -> dict[str, object]:
        data = self.answer_bytes
        return {
            "provider_id": self.provider_id,
            "model": self.model,
            "response_id": self.response_id,
            "finish_reason": self.finish_reason,
            "input_tokens": self.usage.input_tokens,
            "output_tokens": self.usage.output_tokens,
            "reasoning_tokens": self.usage.reasoning_tokens,
            "cached_tokens": self.usage.cached_tokens,
            "currency_cost_usd": self.currency_cost_usd,
            "cost_kind": self.cost_kind,
            "pricing_basis_version": self.pricing_basis_version,
            "duration_ms": self.duration_ms,
            "network_attempted": self.network_attempted,
            "response_received": self.response_received,
            "provider_http_status": self.provider_http_status,
            "provider_error_code": self.provider_error_code,
            "transport_stage": self.transport_stage,
            "answer_bytes": len(data) if data is not None else 0,
            "answer_sha256": (
                hashlib.sha256(data).hexdigest() if data is not None else None
            ),
            "provider_state": self.provider_state.value,
        }


@dataclass(frozen=True)
class ProviderExecution:
    observation: RawProviderObservation
    result: ProviderResult
    capture_state: CaptureState
    return_contract_state: ReturnContractState
    materialization_state: MaterializationState
    verification_state: VerificationState
    acceptance_state: AcceptanceState

    def __post_init__(self) -> None:
        expected_types = (
            ("observation", RawProviderObservation),
            ("result", ProviderResult),
            ("capture_state", CaptureState),
            ("return_contract_state", ReturnContractState),
            ("materialization_state", MaterializationState),
            ("verification_state", VerificationState),
            ("acceptance_state", AcceptanceState),
        )
        for name, expected in expected_types:
            if not isinstance(getattr(self, name), expected):
                raise ValueError(f"{name} must be a {expected.__name__}")

    @classmethod
    def from_result(
        cls,
        provider_id: str,
        result: ProviderResult,
    ) -> "ProviderExecution":
        usage = result.cost.get("usage")
        usage = usage if isinstance(usage, Mapping) else {}
        metrics = result.provider_meta.get("metrics")
        metrics = metrics if isinstance(metrics, Mapping) else {}
        answer_bytes = result.answer.encode("utf-8") if result.answer else None
        observation = RawProviderObservation(
            provider_id=provider_id,
            model=(
                result.provider_meta.get("model")
                if isinstance(result.provider_meta.get("model"), str)
                else None
            ),
            response_id=(
                result.provider_meta.get("response_id")
                if isinstance(result.provider_meta.get("response_id"), str)
                else None
            ),
            finish_reason=(
                result.provider_meta.get("finish_reason")
                if isinstance(result.provider_meta.get("finish_reason"), str)
                else None
            ),
            usage=ProviderUsage(
                usage.get("prompt_tokens", metrics.get("input_tokens")),
                usage.get("completion_tokens", metrics.get("output_tokens")),
                usage.get("reasoning_tokens", metrics.get("reasoning_tokens")),
                usage.get("cached_tokens", metrics.get("cached_tokens")),
            ),
            currency_cost_usd=result.cost.get("currency_cost_usd"),
            cost_kind=(
                result.cost.get("cost_kind") or metrics.get("cost_kind")
            ),
            pricing_basis_version=(
                result.cost.get("pricing_basis_version")
                or metrics.get("pricing_basis_version")
            ),
            duration_ms=metrics.get("duration_ms"),
            answer_bytes=answer_bytes,
            provider_state=ProviderState.COMPLETED,
            network_attempted=(
                result.provider_meta.get("network_attempted")
                if isinstance(
                    result.provider_meta.get("network_attempted"),
                    bool,
                )
                else None
            ),
            response_received=(
                result.provider_meta.get("response_received")
                if isinstance(
                    result.provider_meta.get("response_received"),
                    bool,
                )
                else None
            ),
            provider_http_status=(
                result.provider_meta.get("provider_http_status")
                if isinstance(
                    result.provider_meta.get("provider_http_status"),
                    int,
                )
                and not isinstance(
                    result.provider_meta.get("provider_http_status"),
                    bool,
                )
                else None
            ),
            provider_error_code=(
                result.provider_meta.get("provider_error_code")
                if isinstance(
                    result.provider_meta.get("provider_error_code"),
                    str,
                )
                else None
            ),
            transport_stage=(
                result.provider_meta.get("transport_stage")
                if isinstance(
                    result.provider_meta.get("transport_stage"),
                    str,
                )
                else None
            ),
        )
        return cls.from_observation(observation, result)

    @classmethod
    def from_observation(
        cls,
        observation: RawProviderObservation,
        result: ProviderResult,
    ) -> "ProviderExecution":
        return cls(
            observation=observation,
            result=result,
            capture_state=(
                CaptureState.CAPTURED
                if observation.answer_bytes is not None
                else CaptureState.ABSENT
            ),
            return_contract_state=ReturnContractState.NOT_EVALUATED,
            materialization_state=MaterializationState.NONE,
            verification_state=VerificationState.PENDING,
            acceptance_state=AcceptanceState.PENDING,
        )
