from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence


_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FAILURE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,127}$")


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


class DelegationClass(str, Enum):
    NONE = "none"
    NON_SENSITIVE_ROUTINE = "non_sensitive_routine"
    FRONTIER_RESTRICTED = "frontier_restricted"
    PRIVATE_RESIDENT = "private_resident"


class ResultStatus(str, Enum):
    CANDIDATE_SUCCESS = "candidate_success"
    CANDIDATE_FAILURE = "candidate_failure"


class ReturnFormat(str, Enum):
    FREE_TEXT = "free_text"
    EXACT_TEXT = "exact_text"
    PLAIN_SOURCE = "plain_source"
    JSON_OBJECT = "json_object"


class ImportMode(str, Enum):
    UNSPECIFIED = "unspecified"
    NONE = "none"
    TYPE_ONLY = "type_only"
    RUNTIME = "runtime"
    ANY = "any"


class EolScope(str, Enum):
    UNSPECIFIED = "unspecified"
    OUT_OF_SCOPE = "out_of_scope"
    IN_SCOPE = "in_scope"


class EolNormalization(str, Enum):
    NONE = "none"
    PRESERVE = "preserve"
    LF = "lf"
    CRLF = "crlf"


@dataclass(frozen=True)
class RequiredImport:
    module: str
    kind: str

    def __post_init__(self) -> None:
        module = _non_empty("required import module", self.module)
        if len(module) > 256:
            raise ValueError("required import module is too long")
        if self.kind not in {ImportMode.TYPE_ONLY.value, ImportMode.RUNTIME.value}:
            raise ValueError("required import kind must be type_only or runtime")
        object.__setattr__(self, "module", module)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RequiredImport":
        data = _mapping("required import", data)
        return cls(module=data["module"], kind=data["kind"])

    def to_dict(self) -> dict[str, str]:
        return {"module": self.module, "kind": self.kind}


@dataclass(frozen=True)
class TaskPolicyClauses:
    import_mode: ImportMode = ImportMode.UNSPECIFIED
    required_imports: tuple[RequiredImport, ...] = ()
    eol_scope: EolScope = EolScope.UNSPECIFIED
    eol_normalization: EolNormalization = EolNormalization.NONE

    def __post_init__(self) -> None:
        if not isinstance(self.import_mode, ImportMode):
            raise ValueError("policy_clauses.import_mode must be an ImportMode")
        if not isinstance(self.eol_scope, EolScope):
            raise ValueError("policy_clauses.eol_scope must be an EolScope")
        if not isinstance(self.eol_normalization, EolNormalization):
            raise ValueError(
                "policy_clauses.eol_normalization must be an EolNormalization"
            )
        imports = tuple(self.required_imports)
        if any(not isinstance(item, RequiredImport) for item in imports):
            raise ValueError(
                "policy_clauses.required_imports must contain RequiredImport"
            )
        if len({(item.module, item.kind) for item in imports}) != len(imports):
            raise ValueError(
                "policy_clauses.required_imports must not contain duplicates"
            )
        object.__setattr__(self, "required_imports", imports)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskPolicyClauses":
        data = _mapping("policy_clauses", data)
        imports = _sequence(
            "policy_clauses.required_imports",
            data.get("required_imports", ()),
        )
        if any(not isinstance(item, Mapping) for item in imports):
            raise ValueError(
                "policy_clauses.required_imports entries must be objects"
            )
        return cls(
            import_mode=ImportMode(
                str(data.get("import_mode", ImportMode.UNSPECIFIED.value))
            ),
            required_imports=tuple(
                RequiredImport.from_dict(item) for item in imports
            ),
            eol_scope=EolScope(
                str(data.get("eol_scope", EolScope.UNSPECIFIED.value))
            ),
            eol_normalization=EolNormalization(
                str(
                    data.get(
                        "eol_normalization",
                        EolNormalization.NONE.value,
                    )
                )
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "import_mode": self.import_mode.value,
            "required_imports": [item.to_dict() for item in self.required_imports],
            "eol_scope": self.eol_scope.value,
            "eol_normalization": self.eol_normalization.value,
        }


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
    max_output_tokens: int = 16384
    max_context_tokens: int | None = None
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
        if not 1 <= self.max_output_tokens <= 65536:
            raise ValueError(
                "constraints.max_output_tokens must be between 1 and 65536"
            )
        if self.max_context_tokens is not None:
            if (
                isinstance(self.max_context_tokens, bool)
                or not isinstance(self.max_context_tokens, int)
                or not 1 <= self.max_context_tokens <= 1_048_576
            ):
                raise ValueError(
                    "constraints.max_context_tokens must be between 1 and 1048576"
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
            max_output_tokens=data.get("max_output_tokens", 16384),
            max_context_tokens=data.get("max_context_tokens"),
            internet=data.get("internet", False),
            privacy=PrivacyLevel(str(data.get("privacy", PrivacyLevel.LOCAL_ONLY.value))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_cost_usd": self.max_cost_usd,
            "max_latency_s": self.max_latency_s,
            "max_output_tokens": self.max_output_tokens,
            "max_context_tokens": self.max_context_tokens,
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
    format: ReturnFormat = ReturnFormat.FREE_TEXT
    exact_text: str | None = None
    language: str | None = None

    def __post_init__(self) -> None:
        _boolean("return_contract.summary", self.summary)
        _boolean("return_contract.patch", self.patch)
        _boolean("return_contract.evidence", self.evidence)
        if not isinstance(self.format, ReturnFormat):
            raise ValueError("return_contract.format must be a ReturnFormat")
        if self.exact_text is not None and (
            not isinstance(self.exact_text, str)
            or not self.exact_text
            or len(self.exact_text.encode("utf-8")) > 65536
        ):
            raise ValueError(
                "return_contract.exact_text must be bounded non-empty text"
            )
        if self.language is not None:
            if (
                not isinstance(self.language, str)
                or not re.fullmatch(r"[A-Za-z0-9.+#_-]{1,64}", self.language)
            ):
                raise ValueError("return_contract.language is invalid")
            object.__setattr__(self, "language", self.language.lower())
        if self.format is ReturnFormat.EXACT_TEXT:
            if self.exact_text is None:
                raise ValueError(
                    "return_contract exact_text format requires exact_text"
                )
            if self.language is not None:
                raise ValueError(
                    "return_contract exact_text format may not define language"
                )
            if self.summary or self.evidence or self.patch:
                raise ValueError(
                    "return_contract exact_text format forbids summary, evidence, and patch"
                )
        elif self.exact_text is not None:
            raise ValueError(
                "return_contract exact_text is allowed only for exact_text format"
            )
        if self.format is ReturnFormat.PLAIN_SOURCE:
            if self.language is None:
                raise ValueError(
                    "return_contract plain_source format requires language"
                )
            if self.summary or self.evidence or self.patch:
                raise ValueError(
                    "return_contract plain_source format forbids summary, evidence, and patch"
                )
        elif self.language is not None:
            raise ValueError(
                "return_contract language is allowed only for plain_source format"
            )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReturnContract":
        data = _mapping("return_contract", data)
        return cls(
            summary=data.get("summary", True),
            patch=data.get("patch", False),
            evidence=data.get("evidence", True),
            format=ReturnFormat(
                str(data.get("format", ReturnFormat.FREE_TEXT.value))
            ),
            exact_text=data.get("exact_text"),
            language=data.get("language"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "patch": self.patch,
            "evidence": self.evidence,
            "format": self.format.value,
            "exact_text": self.exact_text,
            "language": self.language,
        }


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
    delegable: bool = False
    delegation_class: DelegationClass = DelegationClass.NONE
    delegation_approval_sha256: str | None = None
    policy_clauses: TaskPolicyClauses = field(default_factory=TaskPolicyClauses)

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not _TASK_ID.fullmatch(self.task_id):
            raise ValueError("task_id must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}")
        object.__setattr__(self, "goal", _non_empty("goal", self.goal))
        object.__setattr__(self, "task_type", _non_empty("task_type", self.task_type))
        _boolean("delegable", self.delegable)
        if not isinstance(self.delegation_class, DelegationClass):
            raise ValueError("delegation_class must be a DelegationClass")
        if self.delegation_approval_sha256 is not None:
            if (
                not isinstance(self.delegation_approval_sha256, str)
                or not _SHA256.fullmatch(self.delegation_approval_sha256.lower())
            ):
                raise ValueError(
                    "delegation_approval_sha256 must be a SHA-256 hex digest"
                )
            object.__setattr__(
                self,
                "delegation_approval_sha256",
                self.delegation_approval_sha256.lower(),
            )
        if not isinstance(self.workspace, WorkspaceSpec):
            raise ValueError("workspace must be a WorkspaceSpec")
        if not isinstance(self.constraints, TaskConstraints):
            raise ValueError("constraints must be TaskConstraints")
        if not isinstance(self.verification, VerificationSpec):
            raise ValueError("verification must be a VerificationSpec")
        if not isinstance(self.return_contract, ReturnContract):
            raise ValueError("return_contract must be a ReturnContract")
        if not isinstance(self.policy_clauses, TaskPolicyClauses):
            raise ValueError("policy_clauses must be TaskPolicyClauses")
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
            delegable=_boolean("delegable", data.get("delegable", False)),
            delegation_class=DelegationClass(
                str(data.get("delegation_class", DelegationClass.NONE.value))
            ),
            delegation_approval_sha256=data.get("delegation_approval_sha256"),
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
            policy_clauses=TaskPolicyClauses.from_dict(
                _mapping("policy_clauses", data.get("policy_clauses", {}))
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "task_type": self.task_type,
            "delegable": self.delegable,
            "delegation_class": self.delegation_class.value,
            "delegation_approval_sha256": self.delegation_approval_sha256,
            "workspace": self.workspace.to_dict(),
            "inputs": [dict(item) for item in self.inputs],
            "constraints": self.constraints.to_dict(),
            "required_capabilities": list(self.required_capabilities),
            "verification": self.verification.to_dict(),
            "return_contract": self.return_contract.to_dict(),
            "policy_clauses": self.policy_clauses.to_dict(),
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
    failure_code: str | None = None
    failure_stage: str | None = None

    def __post_init__(self) -> None:
        if not _TASK_ID.fullmatch(self.task_id):
            raise ValueError("ProviderResult.task_id is invalid")
        if (self.failure_code is None) != (self.failure_stage is None):
            raise ValueError(
                "ProviderResult failure_code and failure_stage must be set together"
            )
        for name in ("failure_code", "failure_stage"):
            value = getattr(self, name)
            if value is not None and not _FAILURE_ID.fullmatch(value):
                raise ValueError(f"ProviderResult.{name} is invalid")

    def to_dict(self) -> dict[str, Any]:
        document = {
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
        if self.failure_code is not None:
            document["failure_code"] = self.failure_code
            document["failure_stage"] = self.failure_stage
        return document
