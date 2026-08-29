from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from .canonical import aware_iso8601, canonical_json_bytes, sha256_id
from .contracts import PrivacyLevel


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _digest(name: str, value: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a 64-character lowercase SHA-256 digest")
    return value


def _identifier(name: str, value: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded ASCII identifier")
    return value


def _bounded_text(name: str, value: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    normalized = value.strip()
    if len(normalized.encode("utf-8")) > maximum:
        raise ValueError(f"{name} is too long")
    return normalized


def _boolean(name: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


def _non_negative_number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite non-negative number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return normalized


def _canonical_digests(
    name: str,
    values: Iterable[str],
    *,
    required: bool,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be an iterable of digests")
    normalized = tuple(_digest(f"{name} item", item) for item in values)
    if required and not normalized:
        raise ValueError(f"{name} must not be empty")
    return tuple(sorted(set(normalized)))


class BudgetMode(str, Enum):
    OBSERVE = "observe"
    WARN = "warn"
    ENFORCE = "enforce"


class ApprovalMode(str, Enum):
    EXACT_MEMBER = "exact_member"
    EXACT_BATCH = "exact_batch"
    POLICY_SESSION = "policy_session"


class FallbackMode(str, Enum):
    DISABLED = "disabled"
    EXPLICIT_PLAN_REVISION = "explicit_plan_revision"


@dataclass(frozen=True)
class OperatorPolicyProfile:
    profile_id: str
    budget_mode: BudgetMode
    approval_mode: ApprovalMode
    model_watch_enabled: bool
    discovery_only: bool
    auto_probe_max_cost_usd_per_day: float
    production_promotion: str
    fallback_mode: FallbackMode
    max_parallelism: int
    direct_context_import: str
    accounting_required: bool

    def __post_init__(self) -> None:
        profile_id = _identifier("profile_id", self.profile_id)
        if not isinstance(self.budget_mode, BudgetMode):
            raise ValueError("budget_mode must be a BudgetMode")
        if not isinstance(self.approval_mode, ApprovalMode):
            raise ValueError("approval_mode must be an ApprovalMode")
        model_watch_enabled = _boolean(
            "model_watch_enabled",
            self.model_watch_enabled,
        )
        discovery_only = _boolean("discovery_only", self.discovery_only)
        auto_probe_cost = _non_negative_number(
            "auto_probe_max_cost_usd_per_day",
            self.auto_probe_max_cost_usd_per_day,
        )
        production_promotion = _identifier(
            "production_promotion",
            self.production_promotion,
        )
        if production_promotion != "explicit":
            raise ValueError("production_promotion must be explicit")
        if not isinstance(self.fallback_mode, FallbackMode):
            raise ValueError("fallback_mode must be a FallbackMode")
        if isinstance(self.max_parallelism, bool) or not isinstance(
            self.max_parallelism,
            int,
        ):
            raise ValueError("max_parallelism must be an integer")
        if not 1 <= self.max_parallelism <= 64:
            raise ValueError("max_parallelism must be between 1 and 64")
        direct_context_import = _identifier(
            "direct_context_import",
            self.direct_context_import,
        )
        if direct_context_import != "manual":
            raise ValueError("direct_context_import must be manual")
        accounting_required = _boolean(
            "accounting_required",
            self.accounting_required,
        )

        object.__setattr__(self, "profile_id", profile_id)
        object.__setattr__(
            self,
            "model_watch_enabled",
            model_watch_enabled,
        )
        object.__setattr__(self, "discovery_only", discovery_only)
        object.__setattr__(
            self,
            "auto_probe_max_cost_usd_per_day",
            auto_probe_cost,
        )
        object.__setattr__(
            self,
            "production_promotion",
            production_promotion,
        )
        object.__setattr__(
            self,
            "direct_context_import",
            direct_context_import,
        )
        object.__setattr__(
            self,
            "accounting_required",
            accounting_required,
        )

    @classmethod
    def owner_default(cls) -> "OperatorPolicyProfile":
        return cls(
            profile_id="owner-warn-only-v1",
            budget_mode=BudgetMode.WARN,
            approval_mode=ApprovalMode.EXACT_MEMBER,
            model_watch_enabled=False,
            discovery_only=True,
            auto_probe_max_cost_usd_per_day=0.0,
            production_promotion="explicit",
            fallback_mode=FallbackMode.EXPLICIT_PLAN_REVISION,
            max_parallelism=1,
            direct_context_import="manual",
            accounting_required=True,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OperatorPolicyProfile":
        if not isinstance(data, Mapping):
            raise ValueError("operator policy must be a JSON object")
        return cls(
            profile_id=data["profile_id"],
            budget_mode=BudgetMode(data["budget_mode"]),
            approval_mode=ApprovalMode(data["approval_mode"]),
            model_watch_enabled=data["model_watch_enabled"],
            discovery_only=data["discovery_only"],
            auto_probe_max_cost_usd_per_day=data[
                "auto_probe_max_cost_usd_per_day"
            ],
            production_promotion=data["production_promotion"],
            fallback_mode=FallbackMode(data["fallback_mode"]),
            max_parallelism=data["max_parallelism"],
            direct_context_import=data["direct_context_import"],
            accounting_required=data["accounting_required"],
        )

    @property
    def snapshot_id(self) -> str:
        return sha256_id("operator_policy_profile_v1", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "budget_mode": self.budget_mode.value,
            "approval_mode": self.approval_mode.value,
            "model_watch_enabled": self.model_watch_enabled,
            "discovery_only": self.discovery_only,
            "auto_probe_max_cost_usd_per_day": (
                self.auto_probe_max_cost_usd_per_day
            ),
            "production_promotion": self.production_promotion,
            "fallback_mode": self.fallback_mode.value,
            "max_parallelism": self.max_parallelism,
            "direct_context_import": self.direct_context_import,
            "accounting_required": self.accounting_required,
        }


@dataclass(frozen=True)
class ContextSourceItem:
    source_id: str
    byte_sha256: str
    selected_ranges: tuple[tuple[int, int], ...]
    selection_authority_digest: str | None

    def __post_init__(self) -> None:
        source_id = _bounded_text("source_id", self.source_id)
        byte_sha256 = _digest("byte_sha256", self.byte_sha256)
        if isinstance(self.selected_ranges, (str, bytes)) or not isinstance(
            self.selected_ranges,
            Sequence,
        ):
            raise ValueError("selected_ranges must be byte intervals")
        normalized_ranges: list[tuple[int, int]] = []
        for item in self.selected_ranges:
            if not isinstance(item, Sequence) or isinstance(item, (str, bytes)):
                raise ValueError("selected_ranges must be byte intervals")
            if len(item) != 2:
                raise ValueError("selected_ranges must be byte intervals")
            start, end = item
            if (
                isinstance(start, bool)
                or isinstance(end, bool)
                or not isinstance(start, int)
                or not isinstance(end, int)
                or start < 0
                or end <= start
            ):
                raise ValueError("selected_ranges must be positive byte intervals")
            normalized_ranges.append((start, end))
        normalized_ranges.sort()
        for prior, current in zip(
            normalized_ranges,
            normalized_ranges[1:],
            strict=False,
        ):
            if current[0] < prior[1]:
                raise ValueError("selected_ranges must not overlap")

        selection_authority_digest = self.selection_authority_digest
        if selection_authority_digest is not None:
            selection_authority_digest = _digest(
                "selection_authority_digest",
                selection_authority_digest,
            )
        if source_id.startswith("direct_session:") and (
            selection_authority_digest is None
        ):
            raise ValueError(
                "direct session source requires explicit selection authority"
            )

        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "byte_sha256", byte_sha256)
        object.__setattr__(
            self,
            "selected_ranges",
            tuple(normalized_ranges),
        )
        object.__setattr__(
            self,
            "selection_authority_digest",
            selection_authority_digest,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "byte_sha256": self.byte_sha256,
            "selected_ranges": [list(item) for item in self.selected_ranges],
            "selection_authority_digest": self.selection_authority_digest,
        }


@dataclass(frozen=True)
class ContextCapsule:
    capsule_id: str
    schema_version: int
    source_items: tuple[ContextSourceItem, ...]
    compiled_bytes_sha256: str
    compiler_version: str
    token_estimate: int
    data_classification: PrivacyLevel
    redaction_profile: str
    allowed_role_ids: tuple[str, ...]
    allowed_route_ids: tuple[str, ...]
    expires_at: str | None
    parent_capsule_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        capsule_id = _digest("capsule_id", self.capsule_id)
        if self.schema_version != 1:
            raise ValueError("schema_version must be 1")
        source_items = tuple(self.source_items)
        if not source_items or any(
            not isinstance(item, ContextSourceItem) for item in source_items
        ):
            raise ValueError(
                "source_items must contain at least one ContextSourceItem"
            )
        source_ids = tuple(item.source_id for item in source_items)
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("source_items must not repeat source_id")
        compiled_bytes_sha256 = _digest(
            "compiled_bytes_sha256",
            self.compiled_bytes_sha256,
        )
        compiler_version = _identifier(
            "compiler_version",
            self.compiler_version,
        )
        if isinstance(self.token_estimate, bool) or not isinstance(
            self.token_estimate,
            int,
        ):
            raise ValueError("token_estimate must be an integer")
        if not 0 <= self.token_estimate <= 100_000_000:
            raise ValueError("token_estimate is out of range")
        if not isinstance(self.data_classification, PrivacyLevel):
            raise ValueError("data_classification must be a PrivacyLevel")
        redaction_profile = _identifier(
            "redaction_profile",
            self.redaction_profile,
        )
        allowed_role_ids = _canonical_digests(
            "allowed_role_ids",
            self.allowed_role_ids,
            required=True,
        )
        allowed_route_ids = _canonical_digests(
            "allowed_route_ids",
            self.allowed_route_ids,
            required=True,
        )
        expires_at = (
            aware_iso8601("expires_at", self.expires_at)
            if self.expires_at is not None
            else None
        )
        parent_capsule_ids = _canonical_digests(
            "parent_capsule_ids",
            self.parent_capsule_ids,
            required=False,
        )

        object.__setattr__(self, "source_items", source_items)
        object.__setattr__(
            self,
            "compiled_bytes_sha256",
            compiled_bytes_sha256,
        )
        object.__setattr__(self, "compiler_version", compiler_version)
        object.__setattr__(self, "redaction_profile", redaction_profile)
        object.__setattr__(self, "allowed_role_ids", allowed_role_ids)
        object.__setattr__(self, "allowed_route_ids", allowed_route_ids)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(self, "parent_capsule_ids", parent_capsule_ids)
        expected = sha256_id("context_capsule_v1", self.canonical_identity())
        if capsule_id != expected:
            raise ValueError("capsule_id does not match canonical context capsule")

    @classmethod
    def build(
        cls,
        source_items: Iterable[ContextSourceItem],
        compiler_version: str,
        data_classification: PrivacyLevel,
        allowed_role_ids: Iterable[str],
        allowed_route_ids: Iterable[str],
        *,
        token_estimate: int = 0,
        redaction_profile: str = "none-v1",
        expires_at: str | None = None,
        parent_capsule_ids: Iterable[str] = (),
        compiled_bytes_sha256: str | None = None,
    ) -> "ContextCapsule":
        if isinstance(source_items, (str, bytes)):
            raise ValueError("source_items must be ContextSourceItem values")
        normalized_sources = tuple(source_items)
        if not normalized_sources or any(
            not isinstance(item, ContextSourceItem)
            for item in normalized_sources
        ):
            raise ValueError(
                "source_items must contain at least one ContextSourceItem"
            )
        compiler_version = _identifier("compiler_version", compiler_version)
        roles = _canonical_digests(
            "allowed_role_ids",
            allowed_role_ids,
            required=True,
        )
        routes = _canonical_digests(
            "allowed_route_ids",
            allowed_route_ids,
            required=True,
        )
        parents = _canonical_digests(
            "parent_capsule_ids",
            parent_capsule_ids,
            required=False,
        )
        normalized_expiry = (
            aware_iso8601("expires_at", expires_at)
            if expires_at is not None
            else None
        )
        if compiled_bytes_sha256 is None:
            compilation_envelope = {
                "compiler_version": compiler_version,
                "source_items": [item.to_dict() for item in normalized_sources],
            }
            compiled_bytes_sha256 = hashlib.sha256(
                canonical_json_bytes(compilation_envelope)
            ).hexdigest()
        else:
            compiled_bytes_sha256 = _digest(
                "compiled_bytes_sha256",
                compiled_bytes_sha256,
            )

        provisional = {
            "schema_version": 1,
            "source_items": [item.to_dict() for item in normalized_sources],
            "compiled_bytes_sha256": compiled_bytes_sha256,
            "compiler_version": compiler_version,
            "token_estimate": token_estimate,
            "data_classification": (
                data_classification.value
                if isinstance(data_classification, PrivacyLevel)
                else data_classification
            ),
            "redaction_profile": redaction_profile,
            "allowed_role_ids": list(roles),
            "allowed_route_ids": list(routes),
            "expires_at": normalized_expiry,
            "parent_capsule_ids": list(parents),
        }
        return cls(
            capsule_id=sha256_id("context_capsule_v1", provisional),
            schema_version=1,
            source_items=normalized_sources,
            compiled_bytes_sha256=compiled_bytes_sha256,
            compiler_version=compiler_version,
            token_estimate=token_estimate,
            data_classification=data_classification,
            redaction_profile=redaction_profile,
            allowed_role_ids=roles,
            allowed_route_ids=routes,
            expires_at=normalized_expiry,
            parent_capsule_ids=parents,
        )

    def assert_allowed(self, role_id: str, route_id: str) -> None:
        role_id = _digest("role_id", role_id)
        route_id = _digest("route_id", route_id)
        if role_id not in self.allowed_role_ids:
            raise ValueError("role is not allowed by this Context Capsule")
        if route_id not in self.allowed_route_ids:
            raise ValueError("route is not allowed by this Context Capsule")

    def canonical_identity(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_items": [item.to_dict() for item in self.source_items],
            "compiled_bytes_sha256": self.compiled_bytes_sha256,
            "compiler_version": self.compiler_version,
            "token_estimate": self.token_estimate,
            "data_classification": self.data_classification.value,
            "redaction_profile": self.redaction_profile,
            "allowed_role_ids": list(self.allowed_role_ids),
            "allowed_route_ids": list(self.allowed_route_ids),
            "expires_at": self.expires_at,
            "parent_capsule_ids": list(self.parent_capsule_ids),
        }

    def to_dict(self) -> dict[str, object]:
        return {"capsule_id": self.capsule_id, **self.canonical_identity()}
