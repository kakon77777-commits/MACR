from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence


_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _non_empty(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _boolean(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


def _non_negative(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite non-negative number")
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0:
        raise ValueError(f"{name} must be a finite non-negative value")
    return normalized


def _sequence(name: str, value: Any) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be an array")
    return value


def _mapping(name: str, value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _relative_scope(value: str) -> str:
    normalized = _non_empty("write_scope item", value).replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("write_scope entries must be relative and may not contain '..'")
    return normalized


class PrivacyLevel(str, Enum):
    PUBLIC = "public"
    INTERNAL_APPROVED = "internal_approved"
    LOCAL_OR_APPROVED_CLOUD = "local_or_approved_cloud"
    LOCAL_ONLY = "local_only"


class ResultStatus(str, Enum):
    CANDIDATE_SUCCESS = "candidate_success"
    CANDIDATE_FAILURE = "candidate_failure"


@dataclass(frozen=True)
class WorkspaceSpec:
    repo: str = "current"
    write_scope: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "repo", _non_empty("workspace.repo", self.repo))
        object.__setattr__(
            self,
            "write_scope",
            tuple(_relative_scope(item) for item in self.write_scope),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WorkspaceSpec":
        data = _mapping("workspace", data)
        write_scope = _sequence("workspace.write_scope", data.get("write_scope", ()))
        return cls(
            repo=data.get("repo", "current"),
            write_scope=tuple(write_scope),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"repo": self.repo, "write_scope": list(self.write_scope)}


@dataclass(frozen=True)
class TaskConstraints:
    max_cost_usd: float = 0.0
    max_latency_s: float = 300.0
    max_output_tokens: int = 1024
    internet: bool = False
    privacy: PrivacyLevel = PrivacyLevel.LOCAL_ONLY

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_cost_usd",
            _non_negative("constraints.max_cost_usd", self.max_cost_usd),
        )
        object.__setattr__(
            self,
            "max_latency_s",
            _non_negative("constraints.max_latency_s", self.max_latency_s),
        )
        if isinstance(self.max_output_tokens, bool) or not isinstance(
            self.max_output_tokens, int
        ):
            raise ValueError("constraints.max_output_tokens must be an integer")
        if not 1 <= self.max_output_tokens <= 16384:
            raise ValueError(
                "constraints.max_output_tokens must be between 1 and 16384"
            )
        _boolean("constraints.internet", self.internet)
        if not isinstance(self.privacy, PrivacyLevel):
            raise ValueError("constraints.privacy must be a PrivacyLevel")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskConstraints":
        data = _mapping("constraints", data)
        return cls(
            max_cost_usd=data.get("max_cost_usd", 0.0),
            max_latency_s=data.get("max_latency_s", 300.0),
            max_output_tokens=data.get("max_output_tokens", 1024),
            internet=data.get("internet", False),
            privacy=PrivacyLevel(str(data.get("privacy", PrivacyLevel.LOCAL_ONLY.value))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_cost_usd": self.max_cost_usd,
            "max_latency_s": self.max_latency_s,
            "max_output_tokens": self.max_output_tokens,
            "internet": self.internet,
            "privacy": self.privacy.value,
        }


@dataclass(frozen=True)
class VerificationSpec:
    required: bool = True
    methods: tuple[str, ...] = ("human_review",)

    def __post_init__(self) -> None:
        _boolean("verification.required", self.required)
        methods = tuple(_non_empty("verification method", item) for item in self.methods)
        if self.required and not methods:
            raise ValueError("verification methods are required when verification.required is true")
        object.__setattr__(self, "methods", methods)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VerificationSpec":
        data = _mapping("verification", data)
        methods = _sequence(
            "verification.methods",
            data.get("method", data.get("methods", ("human_review",))),
        )
        return cls(
            required=data.get("required", True),
            methods=tuple(methods),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"required": self.required, "methods": list(self.methods)}


@dataclass(frozen=True)
class ReturnContract:
    summary: bool = True
    patch: bool = False
    evidence: bool = True

    def __post_init__(self) -> None:
        _boolean("return_contract.summary", self.summary)
        _boolean("return_contract.patch", self.patch)
        _boolean("return_contract.evidence", self.evidence)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReturnContract":
        data = _mapping("return_contract", data)
        return cls(
            summary=data.get("summary", True),
            patch=data.get("patch", False),
            evidence=data.get("evidence", True),
        )

    def to_dict(self) -> dict[str, bool]:
        return {"summary": self.summary, "patch": self.patch, "evidence": self.evidence}


@dataclass(frozen=True)
class TaskContract:
    task_id: str
    goal: str
    task_type: str
    workspace: WorkspaceSpec = field(default_factory=WorkspaceSpec)
    inputs: tuple[dict[str, Any], ...] = ()
    constraints: TaskConstraints = field(default_factory=TaskConstraints)
    required_capabilities: tuple[str, ...] = ()
    verification: VerificationSpec = field(default_factory=VerificationSpec)
    return_contract: ReturnContract = field(default_factory=ReturnContract)

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not _TASK_ID.fullmatch(self.task_id):
            raise ValueError("task_id must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}")
        object.__setattr__(self, "goal", _non_empty("goal", self.goal))
        object.__setattr__(self, "task_type", _non_empty("task_type", self.task_type))
        if not isinstance(self.workspace, WorkspaceSpec):
            raise ValueError("workspace must be a WorkspaceSpec")
        if not isinstance(self.constraints, TaskConstraints):
            raise ValueError("constraints must be TaskConstraints")
        if not isinstance(self.verification, VerificationSpec):
            raise ValueError("verification must be a VerificationSpec")
        if not isinstance(self.return_contract, ReturnContract):
            raise ValueError("return_contract must be a ReturnContract")
        capabilities = tuple(_non_empty("required capability", item) for item in self.required_capabilities)
        if len(capabilities) != len(set(capabilities)):
            raise ValueError("required_capabilities must not contain duplicates")
        object.__setattr__(self, "required_capabilities", capabilities)
        object.__setattr__(self, "inputs", tuple(dict(item) for item in self.inputs))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskContract":
        data = _mapping("TaskContract", data)
        inputs = _sequence("inputs", data.get("inputs", ()))
        if any(not isinstance(item, Mapping) for item in inputs):
            raise ValueError("inputs entries must be JSON objects")
        capabilities = _sequence(
            "required_capabilities",
            data.get("required_capabilities", ()),
        )
        return cls(
            task_id=data["task_id"],
            goal=data["goal"],
            task_type=data["task_type"],
            workspace=WorkspaceSpec.from_dict(_mapping("workspace", data.get("workspace", {}))),
            inputs=tuple(dict(item) for item in inputs),
            constraints=TaskConstraints.from_dict(
                _mapping("constraints", data.get("constraints", {}))
            ),
            required_capabilities=tuple(capabilities),
            verification=VerificationSpec.from_dict(
                _mapping("verification", data.get("verification", {}))
            ),
            return_contract=ReturnContract.from_dict(
                _mapping("return_contract", data.get("return_contract", {}))
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "task_type": self.task_type,
            "workspace": self.workspace.to_dict(),
            "inputs": [dict(item) for item in self.inputs],
            "constraints": self.constraints.to_dict(),
            "required_capabilities": list(self.required_capabilities),
            "verification": self.verification.to_dict(),
            "return_contract": self.return_contract.to_dict(),
        }


@dataclass(frozen=True)
class ProviderResult:
    task_id: str
    status: ResultStatus
    answer: str = ""
    artifacts: tuple[dict[str, Any], ...] = ()
    changes: tuple[dict[str, Any], ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()
    tool_events: tuple[dict[str, Any], ...] = ()
    cost: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    provider_meta: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _TASK_ID.fullmatch(self.task_id):
            raise ValueError("ProviderResult.task_id is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "answer": self.answer,
            "artifacts": [dict(item) for item in self.artifacts],
            "changes": [dict(item) for item in self.changes],
            "evidence": [dict(item) for item in self.evidence],
            "tool_events": [dict(item) for item in self.tool_events],
            "cost": dict(self.cost),
            "warnings": list(self.warnings),
            "provider_meta": dict(self.provider_meta),
        }
