from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..._v07_contracts import (
    canonical_record_digest,
    freeze_json_value,
    normalize_timestamp,
    public_json_value,
    require_closed_mapping,
    require_json_object,
    require_non_empty,
    require_non_negative_int,
    require_non_negative_number,
    require_optional_non_empty,
    require_positive_int,
    require_sha256,
    require_string_tuple,
    require_uuid4,
)
from ...action import EffectName
from ...canonical import canonical_json_bytes
from ...contracts import DelegationClass, PrivacyLevel


HOSTED_AGENT_CELL_SCHEMA_VERSION = "macr-hosted-agent-cell/v1"
HOSTED_CONTEXT_ENVELOPE_SCHEMA_VERSION = "macr-hosted-context-envelope/v1"
_OPAQUE_PROJECT_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class HostedAgentCellStatus(str, Enum):
    READY = "ready"
    RUNNING = "running"
    CHECKPOINTED = "checkpointed"
    COMPLETION_PENDING = "completion_pending"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    RECONCILIATION_REQUIRED = "reconciliation_required"


class HostedContextKind(str, Enum):
    OPERATOR_BRIEF = "operator_brief"
    PROJECT_FACT = "project_fact"
    TOOL_RESULT = "tool_result"
    TOOL_DENIAL = "tool_denial"


class HostedDecisionKind(str, Enum):
    TOOL_REQUEST = "tool_request"
    FINAL_CANDIDATE = "final_candidate"


class HostedToolResultStatus(str, Enum):
    COMPLETED = "completed"
    DENIED = "denied"
    FAILED = "failed"


class HostedBlobRole(str, Enum):
    CONTEXT = "context"
    PROJECTION = "projection"
    MODEL_RAW = "model_raw"
    MODEL_DECISION = "model_decision"
    TOOL_ARGUMENTS = "tool_arguments"
    TOOL_RESULT = "tool_result"


def _bounded_positive(name: str, value: object, maximum: int) -> int:
    selected = require_positive_int(name, value)
    if selected > maximum:
        raise ValueError(f"{name} must not exceed {maximum}")
    return selected


def _bounded_non_negative_number(
    name: str,
    value: object,
    maximum: float,
) -> int | float:
    selected = require_non_negative_number(name, value)
    if selected > maximum:
        raise ValueError(f"{name} exceeds its finite maximum")
    return selected


def _strict_json_object(raw: bytes) -> dict[str, object]:
    if not isinstance(raw, bytes) or not raw:
        raise ValueError("model decision must be non-empty UTF-8 JSON bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("model decision must be UTF-8") from exc

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("model decision contains duplicate keys")
            result[key] = value
        return result

    try:
        value = json.loads(text, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as exc:
        raise ValueError("model decision must be one JSON object") from exc
    if not isinstance(value, dict):
        raise ValueError("model decision must be one JSON object")
    return value


@dataclass(frozen=True)
class HostedBlobRef:
    agent_run_id: str
    role: HostedBlobRole
    sha256: str
    byte_count: int
    blob_ref: str = field(init=False)
    reference_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "agent_run_id",
            require_uuid4("agent_run_id", self.agent_run_id),
        )
        if not isinstance(self.role, HostedBlobRole):
            raise ValueError("role must be a HostedBlobRole")
        object.__setattr__(self, "sha256", require_sha256("sha256", self.sha256))
        object.__setattr__(
            self,
            "byte_count",
            require_non_negative_int("byte_count", self.byte_count),
        )
        blob_ref = f"hosted-blob:{self.agent_run_id}:{self.role.value}:{self.sha256}"
        object.__setattr__(self, "blob_ref", blob_ref)
        object.__setattr__(
            self,
            "reference_digest",
            canonical_record_digest(
                "macr.hosted-blob-ref.v1",
                {
                    "agent_run_id": self.agent_run_id,
                    "role": self.role.value,
                    "sha256": self.sha256,
                    "byte_count": self.byte_count,
                    "blob_ref": blob_ref,
                },
            ),
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "agent_run_id": self.agent_run_id,
            "role": self.role.value,
            "sha256": self.sha256,
            "byte_count": self.byte_count,
            "blob_ref": self.blob_ref,
            "reference_digest": self.reference_digest,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HostedBlobRef":
        data = require_closed_mapping(
            "HostedBlobRef",
            value,
            required=frozenset(
                {
                    "agent_run_id",
                    "role",
                    "sha256",
                    "byte_count",
                    "blob_ref",
                    "reference_digest",
                }
            ),
            optional=frozenset(),
        )
        result = cls(
            agent_run_id=data["agent_run_id"],
            role=HostedBlobRole(data["role"]),
            sha256=data["sha256"],
            byte_count=data["byte_count"],
        )
        if (
            data["blob_ref"] != result.blob_ref
            or require_sha256(
                "reference_digest",
                data["reference_digest"],
            )
            != result.reference_digest
        ):
            raise ValueError("HostedBlobRef identity does not match")
        return result


@dataclass(frozen=True)
class HostedAgentCellPolicy:
    agent_run_id: str
    provider_id: str
    model_id: str
    model_token_policy_digest: str
    provider_execution_profile_digest: str
    prompt_compiler_version: str
    project_ref: str
    delegation_class: DelegationClass
    privacy: PrivacyLevel
    provider_tier_binding_digest: str | None
    project_binding_digest: str | None
    admission_lane: str | None
    provider_admission_policy_digest: str | None
    tool_catalog_digest: str
    allowed_tool_ids: tuple[str, ...]
    max_steps: int
    max_provider_calls: int
    max_tool_calls: int
    max_active_wall_seconds: int | float
    max_currency_cost_usd: int | float
    max_provider_call_cost_usd: int | float
    max_latency_s: int | float
    max_output_tokens: int
    max_provider_context_tokens: int
    max_context_bytes: int
    max_raw_model_response_bytes: int
    max_tool_result_bytes: int
    max_final_output_bytes: int
    revision: int = 1
    schema_version: str = field(
        init=False,
        default=HOSTED_AGENT_CELL_SCHEMA_VERSION,
    )
    policy_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "agent_run_id",
            require_uuid4("agent_run_id", self.agent_run_id),
        )
        for name, maximum in (
            ("provider_id", 128),
            ("model_id", 512),
            ("prompt_compiler_version", 128),
        ):
            object.__setattr__(
                self,
                name,
                require_non_empty(name, getattr(self, name), maximum),
            )
        project_ref = require_non_empty("project_ref", self.project_ref, 128)
        if not _OPAQUE_PROJECT_REF.fullmatch(project_ref):
            raise ValueError("project_ref must be an opaque bounded reference")
        object.__setattr__(self, "project_ref", project_ref)
        if not isinstance(self.delegation_class, DelegationClass):
            raise ValueError("delegation_class must be a DelegationClass")
        if not isinstance(self.privacy, PrivacyLevel):
            raise ValueError("privacy must be a PrivacyLevel")
        for name in (
            "provider_tier_binding_digest",
            "project_binding_digest",
            "provider_admission_policy_digest",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, require_sha256(name, value))
        if self.admission_lane is not None:
            lane = require_non_empty("admission_lane", self.admission_lane, 32)
            if lane not in {"interactive", "routine", "bulk"}:
                raise ValueError("admission_lane is invalid")
            object.__setattr__(self, "admission_lane", lane)
        admission_values = (
            self.project_binding_digest,
            self.admission_lane,
            self.provider_admission_policy_digest,
        )
        if any(value is not None for value in admission_values) and not all(
            value is not None for value in admission_values
        ):
            raise ValueError("provider admission binding must be complete")
        object.__setattr__(
            self,
            "model_token_policy_digest",
            require_sha256(
                "model_token_policy_digest",
                self.model_token_policy_digest,
            ),
        )
        object.__setattr__(
            self,
            "provider_execution_profile_digest",
            require_sha256(
                "provider_execution_profile_digest",
                self.provider_execution_profile_digest,
            ),
        )
        object.__setattr__(
            self,
            "tool_catalog_digest",
            require_sha256("tool_catalog_digest", self.tool_catalog_digest),
        )
        tools = require_string_tuple(
            "allowed_tool_ids",
            self.allowed_tool_ids,
            maximum=64,
        )
        if not tools:
            raise ValueError("allowed_tool_ids must not be empty")
        object.__setattr__(self, "allowed_tool_ids", tools)
        steps = _bounded_positive("max_steps", self.max_steps, 10_000)
        provider_calls = _bounded_positive(
            "max_provider_calls",
            self.max_provider_calls,
            10_000,
        )
        tool_calls = _bounded_positive(
            "max_tool_calls",
            self.max_tool_calls,
            10_000,
        )
        if provider_calls > steps or tool_calls > steps:
            raise ValueError("provider/tool calls cannot exceed max_steps")
        object.__setattr__(self, "max_steps", steps)
        object.__setattr__(self, "max_provider_calls", provider_calls)
        object.__setattr__(self, "max_tool_calls", tool_calls)
        object.__setattr__(
            self,
            "max_active_wall_seconds",
            _bounded_non_negative_number(
                "max_active_wall_seconds",
                self.max_active_wall_seconds,
                7 * 24 * 3600,
            ),
        )
        object.__setattr__(
            self,
            "max_currency_cost_usd",
            _bounded_non_negative_number(
                "max_currency_cost_usd",
                self.max_currency_cost_usd,
                1_000_000_000.0,
            ),
        )
        object.__setattr__(
            self,
            "max_provider_call_cost_usd",
            _bounded_non_negative_number(
                "max_provider_call_cost_usd",
                self.max_provider_call_cost_usd,
                1_000_000_000.0,
            ),
        )
        if self.max_provider_call_cost_usd > self.max_currency_cost_usd:
            raise ValueError(
                "per-call cost ceiling cannot exceed total currency budget"
            )
        object.__setattr__(
            self,
            "max_latency_s",
            _bounded_non_negative_number(
                "max_latency_s",
                self.max_latency_s,
                86_400,
            ),
        )
        if self.max_latency_s <= 0:
            raise ValueError("max_latency_s must be positive")
        object.__setattr__(
            self,
            "max_output_tokens",
            _bounded_positive("max_output_tokens", self.max_output_tokens, 131_072),
        )
        object.__setattr__(
            self,
            "max_provider_context_tokens",
            _bounded_positive(
                "max_provider_context_tokens",
                self.max_provider_context_tokens,
                1_048_576,
            ),
        )
        for name, maximum in (
            ("max_context_bytes", 32 * 1024 * 1024),
            ("max_raw_model_response_bytes", 8 * 1024 * 1024),
            ("max_tool_result_bytes", 8 * 1024 * 1024),
            ("max_final_output_bytes", 8 * 1024 * 1024),
        ):
            object.__setattr__(
                self,
                name,
                _bounded_positive(name, getattr(self, name), maximum),
            )
        object.__setattr__(
            self,
            "revision",
            _bounded_positive("revision", self.revision, 1_000_000),
        )
        object.__setattr__(
            self,
            "policy_digest",
            canonical_record_digest(
                "macr.hosted-agent-cell.policy.v1",
                self._identity_dict(),
            ),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "agent_run_id": self.agent_run_id,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "model_token_policy_digest": self.model_token_policy_digest,
            "provider_execution_profile_digest": (
                self.provider_execution_profile_digest
            ),
            "prompt_compiler_version": self.prompt_compiler_version,
            "project_ref": self.project_ref,
            "delegation_class": self.delegation_class.value,
            "privacy": self.privacy.value,
            "provider_tier_binding_digest": self.provider_tier_binding_digest,
            "project_binding_digest": self.project_binding_digest,
            "admission_lane": self.admission_lane,
            "provider_admission_policy_digest": (self.provider_admission_policy_digest),
            "tool_catalog_digest": self.tool_catalog_digest,
            "allowed_tool_ids": list(self.allowed_tool_ids),
            "max_steps": self.max_steps,
            "max_provider_calls": self.max_provider_calls,
            "max_tool_calls": self.max_tool_calls,
            "max_active_wall_seconds": self.max_active_wall_seconds,
            "max_currency_cost_usd": self.max_currency_cost_usd,
            "max_provider_call_cost_usd": self.max_provider_call_cost_usd,
            "max_latency_s": self.max_latency_s,
            "max_output_tokens": self.max_output_tokens,
            "max_provider_context_tokens": self.max_provider_context_tokens,
            "max_context_bytes": self.max_context_bytes,
            "max_raw_model_response_bytes": self.max_raw_model_response_bytes,
            "max_tool_result_bytes": self.max_tool_result_bytes,
            "max_final_output_bytes": self.max_final_output_bytes,
            "revision": self.revision,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "policy_digest": self.policy_digest}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HostedAgentCellPolicy":
        required = frozenset(
            {
                "schema_version",
                "agent_run_id",
                "provider_id",
                "model_id",
                "model_token_policy_digest",
                "provider_execution_profile_digest",
                "prompt_compiler_version",
                "project_ref",
                "delegation_class",
                "privacy",
                "provider_tier_binding_digest",
                "project_binding_digest",
                "admission_lane",
                "provider_admission_policy_digest",
                "tool_catalog_digest",
                "allowed_tool_ids",
                "max_steps",
                "max_provider_calls",
                "max_tool_calls",
                "max_active_wall_seconds",
                "max_currency_cost_usd",
                "max_provider_call_cost_usd",
                "max_latency_s",
                "max_output_tokens",
                "max_provider_context_tokens",
                "max_context_bytes",
                "max_raw_model_response_bytes",
                "max_tool_result_bytes",
                "max_final_output_bytes",
                "revision",
                "policy_digest",
            }
        )
        data = require_closed_mapping(
            "HostedAgentCellPolicy",
            value,
            required=required,
            optional=frozenset(),
        )
        if data["schema_version"] != HOSTED_AGENT_CELL_SCHEMA_VERSION:
            raise ValueError("hosted Agent cell schema version is unsupported")
        arguments = {
            name: data[name]
            for name in required
            if name not in {"schema_version", "policy_digest"}
        }
        arguments["delegation_class"] = DelegationClass(data["delegation_class"])
        arguments["privacy"] = PrivacyLevel(data["privacy"])
        result = cls(**arguments)
        if result.policy_digest != require_sha256(
            "policy_digest",
            data["policy_digest"],
        ):
            raise ValueError("HostedAgentCellPolicy digest does not match")
        return result


@dataclass(frozen=True)
class HostedContextSection:
    section_id: str
    agent_run_id: str
    kind: HostedContextKind
    label: str
    body: str
    source_ref: str
    source_digest: str
    created_at: str
    body_digest: str = field(init=False)
    section_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "section_id",
            require_uuid4("section_id", self.section_id),
        )
        object.__setattr__(
            self,
            "agent_run_id",
            require_uuid4("agent_run_id", self.agent_run_id),
        )
        if not isinstance(self.kind, HostedContextKind):
            raise ValueError("kind must be a HostedContextKind")
        object.__setattr__(
            self,
            "label",
            require_non_empty("context label", self.label, 512),
        )
        if not isinstance(self.body, str) or not self.body:
            raise ValueError("context body must be non-empty text")
        if len(self.body.encode("utf-8")) > 8 * 1024 * 1024:
            raise ValueError("context body exceeds its private blob limit")
        object.__setattr__(
            self,
            "source_ref",
            require_non_empty("source_ref", self.source_ref, 1024),
        )
        object.__setattr__(
            self,
            "source_digest",
            require_sha256("source_digest", self.source_digest),
        )
        object.__setattr__(
            self,
            "created_at",
            normalize_timestamp("created_at", self.created_at),
        )
        body_digest = hashlib.sha256(self.body.encode("utf-8")).hexdigest()
        object.__setattr__(self, "body_digest", body_digest)
        object.__setattr__(
            self,
            "section_digest",
            canonical_record_digest(
                "macr.hosted-context-section.v1",
                self._identity_dict(),
            ),
        )

    @property
    def evidence_ref(self) -> str:
        return f"hosted-context:{self.section_id}"

    def _identity_dict(self) -> dict[str, object]:
        return {
            "section_id": self.section_id,
            "agent_run_id": self.agent_run_id,
            "kind": self.kind.value,
            "label": self.label,
            "body_digest": self.body_digest,
            "source_ref": self.source_ref,
            "source_digest": self.source_digest,
            "created_at": self.created_at,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {
            **self._identity_dict(),
            "evidence_ref": self.evidence_ref,
            "body_bytes": len(self.body.encode("utf-8")),
            "section_digest": self.section_digest,
        }

    def to_private_dict(self) -> dict[str, object]:
        return {**self.to_public_dict(), "body": self.body}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_private_dict())

    @classmethod
    def from_private_dict(
        cls,
        value: Mapping[str, Any],
    ) -> "HostedContextSection":
        data = require_closed_mapping(
            "HostedContextSection",
            value,
            required=frozenset(
                {
                    "section_id",
                    "agent_run_id",
                    "kind",
                    "label",
                    "body",
                    "body_digest",
                    "body_bytes",
                    "source_ref",
                    "source_digest",
                    "created_at",
                    "evidence_ref",
                    "section_digest",
                }
            ),
            optional=frozenset(),
        )
        result = cls(
            section_id=data["section_id"],
            agent_run_id=data["agent_run_id"],
            kind=HostedContextKind(data["kind"]),
            label=data["label"],
            body=data["body"],
            source_ref=data["source_ref"],
            source_digest=data["source_digest"],
            created_at=data["created_at"],
        )
        if (
            data["body_digest"] != result.body_digest
            or data["body_bytes"] != len(result.body.encode("utf-8"))
            or data["evidence_ref"] != result.evidence_ref
            or data["section_digest"] != result.section_digest
        ):
            raise ValueError("HostedContextSection identity does not match")
        return result


@dataclass(frozen=True)
class HostedToolManifest:
    tool_id: str
    description: str
    effect: EffectName
    argument_schema: Mapping[str, object]
    adapter_version: str
    manifest_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tool_id",
            require_non_empty("tool_id", self.tool_id, 128),
        )
        object.__setattr__(
            self,
            "description",
            require_non_empty("tool description", self.description, 2048),
        )
        if not isinstance(self.effect, EffectName):
            raise ValueError("effect must be an EffectName")
        schema = require_json_object("argument_schema", self.argument_schema)
        object.__setattr__(
            self,
            "argument_schema",
            freeze_json_value("argument_schema", schema),
        )
        object.__setattr__(
            self,
            "adapter_version",
            require_non_empty("adapter_version", self.adapter_version, 128),
        )
        object.__setattr__(
            self,
            "manifest_digest",
            canonical_record_digest(
                "macr.hosted-tool-manifest.v1",
                self._identity_dict(),
            ),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "tool_id": self.tool_id,
            "description": self.description,
            "effect": self.effect.value,
            "argument_schema": public_json_value(self.argument_schema),
            "adapter_version": self.adapter_version,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "manifest_digest": self.manifest_digest}


@dataclass(frozen=True)
class HostedToolCatalog:
    tools: tuple[HostedToolManifest, ...]
    catalog_digest: str = field(init=False)

    def __post_init__(self) -> None:
        tools = tuple(self.tools)
        if not tools or any(not isinstance(item, HostedToolManifest) for item in tools):
            raise ValueError("tools must contain HostedToolManifest values")
        ids = [item.tool_id for item in tools]
        if len(ids) != len(set(ids)):
            raise ValueError("tool catalog contains duplicate IDs")
        tools = tuple(sorted(tools, key=lambda item: item.tool_id))
        object.__setattr__(self, "tools", tools)
        object.__setattr__(
            self,
            "catalog_digest",
            canonical_record_digest(
                "macr.hosted-tool-catalog.v1",
                {"tools": [item.to_public_dict() for item in tools]},
            ),
        )

    def get(self, tool_id: str) -> HostedToolManifest:
        selected = require_non_empty("tool_id", tool_id, 128)
        try:
            return next(item for item in self.tools if item.tool_id == selected)
        except StopIteration as exc:
            raise KeyError(f"unknown hosted tool: {selected}") from exc

    def to_public_dict(self) -> dict[str, object]:
        return {
            "tools": [item.to_public_dict() for item in self.tools],
            "catalog_digest": self.catalog_digest,
        }


@dataclass(frozen=True)
class HostedToolRequest:
    request_id: str
    tool_id: str
    arguments: Mapping[str, object]
    arguments_digest: str = field(init=False)
    request_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            require_uuid4("request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "tool_id",
            require_non_empty("tool_id", self.tool_id, 128),
        )
        arguments = require_json_object("tool arguments", self.arguments)
        object.__setattr__(
            self,
            "arguments",
            freeze_json_value("tool arguments", arguments),
        )
        digest = hashlib.sha256(canonical_json_bytes(arguments)).hexdigest()
        object.__setattr__(self, "arguments_digest", digest)
        object.__setattr__(
            self,
            "request_digest",
            canonical_record_digest(
                "macr.hosted-tool-request.v1",
                {
                    "request_id": self.request_id,
                    "tool_id": self.tool_id,
                    "arguments_digest": digest,
                },
            ),
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "tool_id": self.tool_id,
            "arguments_digest": self.arguments_digest,
            "request_digest": self.request_digest,
        }

    def to_private_dict(self) -> dict[str, object]:
        return {**self.to_public_dict(), "arguments": public_json_value(self.arguments)}

    @classmethod
    def from_private_dict(cls, value: Mapping[str, Any]) -> "HostedToolRequest":
        data = require_closed_mapping(
            "HostedToolRequest",
            value,
            required=frozenset(
                {
                    "request_id",
                    "tool_id",
                    "arguments",
                    "arguments_digest",
                    "request_digest",
                }
            ),
            optional=frozenset(),
        )
        result = cls(
            request_id=data["request_id"],
            tool_id=data["tool_id"],
            arguments=data["arguments"],
        )
        if result.arguments_digest != require_sha256(
            "arguments_digest",
            data["arguments_digest"],
        ) or result.request_digest != require_sha256(
            "request_digest",
            data["request_digest"],
        ):
            raise ValueError("HostedToolRequest digest does not match")
        return result


@dataclass(frozen=True)
class HostedModelDecision:
    decision_id: str
    kind: HostedDecisionKind
    tool_request: HostedToolRequest | None
    final_candidate: str | None
    evidence_refs: tuple[str, ...]
    proposal_digest: str = field(init=False)
    decision_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_id",
            require_uuid4("decision_id", self.decision_id),
        )
        if not isinstance(self.kind, HostedDecisionKind):
            raise ValueError("kind must be a HostedDecisionKind")
        refs = require_string_tuple("evidence_refs", self.evidence_refs, maximum=256)
        object.__setattr__(self, "evidence_refs", refs)
        if self.kind is HostedDecisionKind.TOOL_REQUEST:
            if not isinstance(self.tool_request, HostedToolRequest):
                raise ValueError("tool_request decision requires one request")
            if self.final_candidate is not None or refs:
                raise ValueError("tool_request decision cannot carry final fields")
        else:
            if self.tool_request is not None:
                raise ValueError("final_candidate decision cannot carry a tool request")
            if not isinstance(self.final_candidate, str) or not self.final_candidate:
                raise ValueError("final_candidate must contain text")
            if not refs:
                raise ValueError("final_candidate requires evidence_refs")
        object.__setattr__(
            self,
            "proposal_digest",
            canonical_record_digest(
                "macr.hosted-model-proposal.v1",
                self._proposal_dict(),
            ),
        )
        object.__setattr__(
            self,
            "decision_digest",
            canonical_record_digest(
                "macr.hosted-model-decision.v1",
                self._identity_dict(),
            ),
        )

    def _proposal_dict(self) -> dict[str, object]:
        final_digest = (
            None
            if self.final_candidate is None
            else hashlib.sha256(self.final_candidate.encode("utf-8")).hexdigest()
        )
        return {
            "kind": self.kind.value,
            "tool_id": (
                None if self.tool_request is None else self.tool_request.tool_id
            ),
            "arguments_digest": (
                None
                if self.tool_request is None
                else self.tool_request.arguments_digest
            ),
            "final_candidate_digest": final_digest,
            "evidence_refs": list(self.evidence_refs),
        }

    def _identity_dict(self) -> dict[str, object]:
        return {
            "decision_id": self.decision_id,
            "proposal_digest": self.proposal_digest,
            "tool_request": (
                None
                if self.tool_request is None
                else self.tool_request.to_public_dict()
            ),
            **self._proposal_dict(),
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "decision_digest": self.decision_digest}

    def to_private_dict(self) -> dict[str, object]:
        return {
            "decision_id": self.decision_id,
            "kind": self.kind.value,
            "tool_request": (
                None
                if self.tool_request is None
                else self.tool_request.to_private_dict()
            ),
            "final_candidate": self.final_candidate,
            "evidence_refs": list(self.evidence_refs),
            "proposal_digest": self.proposal_digest,
            "decision_digest": self.decision_digest,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_private_dict())

    @classmethod
    def from_private_dict(
        cls,
        value: Mapping[str, Any],
    ) -> "HostedModelDecision":
        data = require_closed_mapping(
            "HostedModelDecision",
            value,
            required=frozenset(
                {
                    "decision_id",
                    "kind",
                    "tool_request",
                    "final_candidate",
                    "evidence_refs",
                    "proposal_digest",
                    "decision_digest",
                }
            ),
            optional=frozenset(),
        )
        request = data["tool_request"]
        result = cls(
            decision_id=data["decision_id"],
            kind=HostedDecisionKind(data["kind"]),
            tool_request=(
                None
                if request is None
                else HostedToolRequest.from_private_dict(request)
            ),
            final_candidate=data["final_candidate"],
            evidence_refs=tuple(data["evidence_refs"]),
        )
        if result.proposal_digest != require_sha256(
            "proposal_digest", data["proposal_digest"]
        ) or result.decision_digest != require_sha256(
            "decision_digest", data["decision_digest"]
        ):
            raise ValueError("HostedModelDecision identity does not match")
        return result

    @classmethod
    def from_json_bytes(
        cls,
        raw: bytes,
        *,
        id_factory=None,
    ) -> "HostedModelDecision":
        data = _strict_json_object(raw)
        factory = (lambda: str(uuid.uuid4())) if id_factory is None else id_factory
        if not callable(factory):
            raise ValueError("id_factory must be callable")
        kind = HostedDecisionKind(data.get("kind"))
        if kind is HostedDecisionKind.TOOL_REQUEST:
            parsed = require_closed_mapping(
                "hosted tool proposal",
                data,
                required=frozenset({"kind", "tool_id", "arguments"}),
                optional=frozenset(),
            )
            request = HostedToolRequest(
                request_id=factory(),
                tool_id=parsed["tool_id"],
                arguments=parsed["arguments"],
            )
            return cls(
                decision_id=factory(),
                kind=kind,
                tool_request=request,
                final_candidate=None,
                evidence_refs=(),
            )
        parsed = require_closed_mapping(
            "hosted final proposal",
            data,
            required=frozenset({"kind", "final_candidate", "evidence_refs"}),
            optional=frozenset(),
        )
        return cls(
            decision_id=factory(),
            kind=kind,
            tool_request=None,
            final_candidate=parsed["final_candidate"],
            evidence_refs=tuple(parsed["evidence_refs"]),
        )


@dataclass(frozen=True)
class HostedModelRequest:
    provider_invocation_id: str
    agent_run_id: str
    agent_run_epoch: int
    agent_state_revision: int
    step_index: int
    provider_id: str
    model_id: str
    context_blob_ref: str
    context_digest: str
    context_bytes: int
    policy_digest: str
    model_token_policy_digest: str
    provider_execution_profile_digest: str
    prompt_compiler_version: str
    delegation_class: DelegationClass
    privacy: PrivacyLevel
    provider_tier_binding_digest: str | None
    project_binding_digest: str | None
    admission_lane: str | None
    provider_admission_policy_digest: str | None
    max_latency_s: int | float
    max_output_tokens: int
    max_provider_context_tokens: int
    cost_ceiling_usd: int | float
    request_digest: str = field(init=False)

    def __post_init__(self) -> None:
        for name in ("provider_invocation_id", "agent_run_id"):
            object.__setattr__(self, name, require_uuid4(name, getattr(self, name)))
        object.__setattr__(
            self,
            "agent_run_epoch",
            require_positive_int("agent_run_epoch", self.agent_run_epoch),
        )
        object.__setattr__(
            self,
            "agent_state_revision",
            require_positive_int(
                "agent_state_revision",
                self.agent_state_revision,
            ),
        )
        object.__setattr__(
            self,
            "step_index",
            require_positive_int("step_index", self.step_index),
        )
        for name, maximum in (
            ("provider_id", 128),
            ("model_id", 512),
            ("context_blob_ref", 512),
        ):
            object.__setattr__(
                self,
                name,
                require_non_empty(name, getattr(self, name), maximum),
            )
        object.__setattr__(
            self,
            "context_digest",
            require_sha256("context_digest", self.context_digest),
        )
        object.__setattr__(
            self,
            "context_bytes",
            _bounded_positive("context_bytes", self.context_bytes, 32 * 1024 * 1024),
        )
        object.__setattr__(
            self,
            "policy_digest",
            require_sha256("policy_digest", self.policy_digest),
        )
        object.__setattr__(
            self,
            "model_token_policy_digest",
            require_sha256(
                "model_token_policy_digest",
                self.model_token_policy_digest,
            ),
        )
        object.__setattr__(
            self,
            "provider_execution_profile_digest",
            require_sha256(
                "provider_execution_profile_digest",
                self.provider_execution_profile_digest,
            ),
        )
        object.__setattr__(
            self,
            "prompt_compiler_version",
            require_non_empty(
                "prompt_compiler_version",
                self.prompt_compiler_version,
                128,
            ),
        )
        if not isinstance(self.delegation_class, DelegationClass):
            raise ValueError("delegation_class must be a DelegationClass")
        if not isinstance(self.privacy, PrivacyLevel):
            raise ValueError("privacy must be a PrivacyLevel")
        for name in (
            "provider_tier_binding_digest",
            "project_binding_digest",
            "provider_admission_policy_digest",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, require_sha256(name, value))
        if self.admission_lane is not None:
            lane = require_non_empty("admission_lane", self.admission_lane, 32)
            if lane not in {"interactive", "routine", "bulk"}:
                raise ValueError("admission_lane is invalid")
            object.__setattr__(self, "admission_lane", lane)
        admission_values = (
            self.project_binding_digest,
            self.admission_lane,
            self.provider_admission_policy_digest,
        )
        if any(value is not None for value in admission_values) and not all(
            value is not None for value in admission_values
        ):
            raise ValueError("provider admission binding must be complete")
        object.__setattr__(
            self,
            "max_latency_s",
            _bounded_non_negative_number(
                "max_latency_s",
                self.max_latency_s,
                86_400,
            ),
        )
        if self.max_latency_s <= 0:
            raise ValueError("max_latency_s must be positive")
        object.__setattr__(
            self,
            "max_output_tokens",
            _bounded_positive("max_output_tokens", self.max_output_tokens, 131_072),
        )
        object.__setattr__(
            self,
            "max_provider_context_tokens",
            _bounded_positive(
                "max_provider_context_tokens",
                self.max_provider_context_tokens,
                1_048_576,
            ),
        )
        object.__setattr__(
            self,
            "cost_ceiling_usd",
            _bounded_non_negative_number(
                "cost_ceiling_usd",
                self.cost_ceiling_usd,
                1_000_000_000.0,
            ),
        )
        object.__setattr__(
            self,
            "request_digest",
            canonical_record_digest(
                "macr.hosted-model-request.v1",
                self._identity_dict(),
            ),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "provider_invocation_id": self.provider_invocation_id,
            "agent_run_id": self.agent_run_id,
            "agent_run_epoch": self.agent_run_epoch,
            "agent_state_revision": self.agent_state_revision,
            "step_index": self.step_index,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "context_blob_ref": self.context_blob_ref,
            "context_digest": self.context_digest,
            "context_bytes": self.context_bytes,
            "policy_digest": self.policy_digest,
            "model_token_policy_digest": self.model_token_policy_digest,
            "provider_execution_profile_digest": (
                self.provider_execution_profile_digest
            ),
            "prompt_compiler_version": self.prompt_compiler_version,
            "delegation_class": self.delegation_class.value,
            "privacy": self.privacy.value,
            "provider_tier_binding_digest": self.provider_tier_binding_digest,
            "project_binding_digest": self.project_binding_digest,
            "admission_lane": self.admission_lane,
            "provider_admission_policy_digest": (self.provider_admission_policy_digest),
            "max_latency_s": self.max_latency_s,
            "max_output_tokens": self.max_output_tokens,
            "max_provider_context_tokens": self.max_provider_context_tokens,
            "cost_ceiling_usd": self.cost_ceiling_usd,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "request_digest": self.request_digest}


@dataclass(frozen=True)
class HostedModelResult:
    provider_invocation_id: str
    provider_id: str
    model_id: str
    decision: HostedModelDecision
    currency_cost_usd: int | float
    duration_ms: int
    network_attempted: bool | None
    response_received: bool | None
    result_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_invocation_id",
            require_uuid4("provider_invocation_id", self.provider_invocation_id),
        )
        for name, maximum in (("provider_id", 128), ("model_id", 512)):
            object.__setattr__(
                self,
                name,
                require_non_empty(name, getattr(self, name), maximum),
            )
        if not isinstance(self.decision, HostedModelDecision):
            raise ValueError("decision must be a HostedModelDecision")
        object.__setattr__(
            self,
            "currency_cost_usd",
            _bounded_non_negative_number(
                "currency_cost_usd",
                self.currency_cost_usd,
                1_000_000_000.0,
            ),
        )
        object.__setattr__(
            self,
            "duration_ms",
            require_non_negative_int("duration_ms", self.duration_ms),
        )
        for name in ("network_attempted", "response_received"):
            value = getattr(self, name)
            if value not in {True, False, None}:
                raise ValueError(f"{name} must be boolean or None")
        if self.response_received is True and self.network_attempted is not True:
            raise ValueError("response_received requires network_attempted")
        object.__setattr__(
            self,
            "result_digest",
            canonical_record_digest(
                "macr.hosted-model-result.v1",
                self._identity_dict(),
            ),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "provider_invocation_id": self.provider_invocation_id,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "decision_digest": self.decision.decision_digest,
            "currency_cost_usd": self.currency_cost_usd,
            "duration_ms": self.duration_ms,
            "network_attempted": self.network_attempted,
            "response_received": self.response_received,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "result_digest": self.result_digest}


@dataclass(frozen=True)
class HostedToolResultRef:
    action_id: str
    request_digest: str
    tool_id: str
    status: HostedToolResultStatus
    result_blob_ref: str | None
    result_digest: str | None
    result_bytes: int | None
    observed_at: str
    reference_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "action_id", require_uuid4("action_id", self.action_id)
        )
        object.__setattr__(
            self,
            "request_digest",
            require_sha256("request_digest", self.request_digest),
        )
        object.__setattr__(
            self,
            "tool_id",
            require_non_empty("tool_id", self.tool_id, 128),
        )
        if not isinstance(self.status, HostedToolResultStatus):
            raise ValueError("status must be a HostedToolResultStatus")
        blob_ref = require_optional_non_empty(
            "result_blob_ref",
            self.result_blob_ref,
            512,
        )
        digest = self.result_digest
        if digest is not None:
            digest = require_sha256("result_digest", digest)
        size = self.result_bytes
        if size is not None:
            size = require_non_negative_int("result_bytes", size)
        has_result = (blob_ref is not None, digest is not None, size is not None)
        if any(has_result) and not all(has_result):
            raise ValueError("tool result fields must be all present or absent")
        if self.status is HostedToolResultStatus.COMPLETED and not all(has_result):
            raise ValueError("completed tool result requires exact blob evidence")
        if self.status is HostedToolResultStatus.DENIED and any(has_result):
            raise ValueError("denied tool result cannot claim executed bytes")
        object.__setattr__(self, "result_blob_ref", blob_ref)
        object.__setattr__(self, "result_digest", digest)
        object.__setattr__(self, "result_bytes", size)
        object.__setattr__(
            self,
            "observed_at",
            normalize_timestamp("observed_at", self.observed_at),
        )
        object.__setattr__(
            self,
            "reference_digest",
            canonical_record_digest(
                "macr.hosted-tool-result-ref.v1",
                self._identity_dict(),
            ),
        )

    @property
    def evidence_ref(self) -> str:
        return f"hosted-tool-result:{self.action_id}"

    def _identity_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "request_digest": self.request_digest,
            "tool_id": self.tool_id,
            "status": self.status.value,
            "result_blob_ref": self.result_blob_ref,
            "result_digest": self.result_digest,
            "result_bytes": self.result_bytes,
            "observed_at": self.observed_at,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {
            **self._identity_dict(),
            "evidence_ref": self.evidence_ref,
            "reference_digest": self.reference_digest,
        }


@dataclass(frozen=True)
class HostedAgentCellState:
    agent_run_id: str
    cell_revision: int
    policy_digest: str
    semantic_request_digest: str
    status: HostedAgentCellStatus
    next_step: int
    provider_calls: int
    tool_calls: int
    active_wall_ms: int
    currency_cost_usd: int | float
    latest_checkpoint_digest: str | None
    candidate_run_id: str | None
    final_capture_id: str | None
    final_answer_digest: str | None
    created_at: str
    updated_at: str
    state_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "agent_run_id",
            require_uuid4("agent_run_id", self.agent_run_id),
        )
        object.__setattr__(
            self,
            "cell_revision",
            require_positive_int("cell_revision", self.cell_revision),
        )
        for name in ("policy_digest", "semantic_request_digest"):
            object.__setattr__(
                self,
                name,
                require_sha256(name, getattr(self, name)),
            )
        if not isinstance(self.status, HostedAgentCellStatus):
            raise ValueError("status must be a HostedAgentCellStatus")
        object.__setattr__(
            self,
            "next_step",
            require_positive_int("next_step", self.next_step),
        )
        for name in ("provider_calls", "tool_calls", "active_wall_ms"):
            object.__setattr__(
                self,
                name,
                require_non_negative_int(name, getattr(self, name)),
            )
        object.__setattr__(
            self,
            "currency_cost_usd",
            require_non_negative_number(
                "currency_cost_usd",
                self.currency_cost_usd,
            ),
        )
        checkpoint = self.latest_checkpoint_digest
        if checkpoint is not None:
            checkpoint = require_sha256("latest_checkpoint_digest", checkpoint)
        candidate = self.candidate_run_id
        if candidate is not None:
            candidate = require_uuid4("candidate_run_id", candidate)
        capture = require_optional_non_empty(
            "final_capture_id",
            self.final_capture_id,
            128,
        )
        answer = self.final_answer_digest
        if answer is not None:
            answer = require_sha256("final_answer_digest", answer)
        final_fields = (candidate is not None, capture is not None, answer is not None)
        if any(final_fields) and not all(final_fields):
            raise ValueError("final candidate fields must be all present or absent")
        if self.status in {
            HostedAgentCellStatus.COMPLETION_PENDING,
            HostedAgentCellStatus.COMPLETED,
        } and not all(final_fields):
            raise ValueError("completion state requires final candidate evidence")
        object.__setattr__(self, "latest_checkpoint_digest", checkpoint)
        object.__setattr__(self, "candidate_run_id", candidate)
        object.__setattr__(self, "final_capture_id", capture)
        object.__setattr__(self, "final_answer_digest", answer)
        object.__setattr__(
            self,
            "created_at",
            normalize_timestamp("created_at", self.created_at),
        )
        object.__setattr__(
            self,
            "updated_at",
            normalize_timestamp("updated_at", self.updated_at),
        )
        object.__setattr__(
            self,
            "state_digest",
            canonical_record_digest(
                "macr.hosted-agent-cell.state.v1",
                self._identity_dict(),
            ),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "agent_run_id": self.agent_run_id,
            "cell_revision": self.cell_revision,
            "policy_digest": self.policy_digest,
            "semantic_request_digest": self.semantic_request_digest,
            "status": self.status.value,
            "next_step": self.next_step,
            "provider_calls": self.provider_calls,
            "tool_calls": self.tool_calls,
            "active_wall_ms": self.active_wall_ms,
            "currency_cost_usd": self.currency_cost_usd,
            "latest_checkpoint_digest": self.latest_checkpoint_digest,
            "candidate_run_id": self.candidate_run_id,
            "final_capture_id": self.final_capture_id,
            "final_answer_digest": self.final_answer_digest,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "state_digest": self.state_digest}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HostedAgentCellState":
        required = frozenset(
            {
                "agent_run_id",
                "cell_revision",
                "policy_digest",
                "semantic_request_digest",
                "status",
                "next_step",
                "provider_calls",
                "tool_calls",
                "active_wall_ms",
                "currency_cost_usd",
                "latest_checkpoint_digest",
                "candidate_run_id",
                "final_capture_id",
                "final_answer_digest",
                "created_at",
                "updated_at",
                "state_digest",
            }
        )
        data = require_closed_mapping(
            "HostedAgentCellState",
            value,
            required=required,
            optional=frozenset(),
        )
        result = cls(
            agent_run_id=data["agent_run_id"],
            cell_revision=data["cell_revision"],
            policy_digest=data["policy_digest"],
            semantic_request_digest=data["semantic_request_digest"],
            status=HostedAgentCellStatus(data["status"]),
            next_step=data["next_step"],
            provider_calls=data["provider_calls"],
            tool_calls=data["tool_calls"],
            active_wall_ms=data["active_wall_ms"],
            currency_cost_usd=data["currency_cost_usd"],
            latest_checkpoint_digest=data["latest_checkpoint_digest"],
            candidate_run_id=data["candidate_run_id"],
            final_capture_id=data["final_capture_id"],
            final_answer_digest=data["final_answer_digest"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )
        if result.state_digest != require_sha256(
            "state_digest",
            data["state_digest"],
        ):
            raise ValueError("HostedAgentCellState digest does not match")
        return result
