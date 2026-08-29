from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .canonical import canonical_json_bytes, sha256_id
from .coordination import CoordinationPlan, TopologyId
from .errors import CoordinatorPolicyError


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_FIELD_PATH = re.compile(r"^[A-Za-z0-9_.\[\]-]{1,256}$")
_FORBIDDEN_CONTROL_WORDS = (
    "authority",
    "authorization",
    "accept",
    "merge",
    "deploy",
    "resident",
    "provider",
    "route",
    "model",
    "credential",
    "prompt",
    "answer",
    "path",
    "tool",
)
_PROPOSAL_KEYS = frozenset(
    {
        "schema_version",
        "parent_plan_digest",
        "source_candidate_digest",
        "children",
    }
)
_CHILD_KEYS = frozenset(
    {
        "child_id",
        "task_digest",
        "role_template_digest",
        "context_capsule_ids",
        "required_capabilities",
        "cost_ceiling_usd",
    }
)


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded identifier")
    return value


def _positive_integer(name: str, value: object, *, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= maximum
    ):
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


def _cost(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite non-negative")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError(f"{name} must be finite non-negative")
    return normalized


def _digest_set(
    name: str,
    values: Iterable[str],
    *,
    required: bool,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must contain digests")
    normalized = tuple(_digest(f"{name} item", item) for item in values)
    if required and not normalized:
        raise ValueError(f"{name} must not be empty")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} must not contain duplicates")
    return tuple(sorted(normalized))


def _identifier_set(
    name: str,
    values: Iterable[str],
    *,
    required: bool,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must contain identifiers")
    normalized = tuple(_identifier(f"{name} item", item) for item in values)
    if required and not normalized:
        raise ValueError(f"{name} must not be empty")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} must not contain duplicates")
    return tuple(sorted(normalized))


def _field_paths(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError("rejected fields must be an array")
    normalized = tuple(values)
    if any(not isinstance(item, str) or not _FIELD_PATH.fullmatch(item) for item in normalized):
        raise ValueError("rejected field path is invalid")
    return tuple(sorted(set(normalized)))


@dataclass(frozen=True)
class CoordinatorChildRequest:
    child_id: str
    task_digest: str
    role_template_digest: str
    context_capsule_ids: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    cost_ceiling_usd: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "child_id", _identifier("child_id", self.child_id))
        object.__setattr__(
            self,
            "task_digest",
            _digest("task_digest", self.task_digest),
        )
        object.__setattr__(
            self,
            "role_template_digest",
            _digest("role_template_digest", self.role_template_digest),
        )
        object.__setattr__(
            self,
            "context_capsule_ids",
            _digest_set(
                "context_capsule_ids",
                self.context_capsule_ids,
                required=True,
            ),
        )
        object.__setattr__(
            self,
            "required_capabilities",
            _identifier_set(
                "required_capabilities",
                self.required_capabilities,
                required=True,
            ),
        )
        object.__setattr__(
            self,
            "cost_ceiling_usd",
            _cost("cost_ceiling_usd", self.cost_ceiling_usd),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "child_id": self.child_id,
            "task_digest": self.task_digest,
            "role_template_digest": self.role_template_digest,
            "context_capsule_ids": list(self.context_capsule_ids),
            "required_capabilities": list(self.required_capabilities),
            "cost_ceiling_usd": self.cost_ceiling_usd,
        }


@dataclass(frozen=True)
class CoordinatorProposal:
    schema_version: int
    parent_plan_digest: str
    source_candidate_digest: str
    children: tuple[CoordinatorChildRequest, ...]
    rejected_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("coordinator proposal schema_version must be 1")
        object.__setattr__(
            self,
            "parent_plan_digest",
            _digest("parent_plan_digest", self.parent_plan_digest),
        )
        object.__setattr__(
            self,
            "source_candidate_digest",
            _digest("source_candidate_digest", self.source_candidate_digest),
        )
        if isinstance(self.children, (str, bytes)):
            raise ValueError("coordinator proposal children must be an array")
        children = tuple(self.children)
        if not children or any(
            not isinstance(item, CoordinatorChildRequest) for item in children
        ):
            raise ValueError(
                "coordinator proposal children must contain child requests"
            )
        children = tuple(sorted(children, key=lambda item: item.child_id))
        if len({item.child_id for item in children}) != len(children):
            raise ValueError("coordinator proposal contains duplicate child_id")
        object.__setattr__(self, "children", children)
        object.__setattr__(
            self,
            "rejected_fields",
            _field_paths(self.rejected_fields),
        )

    @property
    def proposal_digest(self) -> str:
        return sha256_id("coordinator_proposal_v1", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "parent_plan_digest": self.parent_plan_digest,
            "source_candidate_digest": self.source_candidate_digest,
            "children": [item.to_dict() for item in self.children],
            "rejected_fields": list(self.rejected_fields),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CoordinatorProposal":
        if not isinstance(data, Mapping):
            raise ValueError("coordinator proposal must be an object")
        if any(not isinstance(key, str) for key in data):
            raise ValueError("coordinator proposal keys must be strings")
        rejected = [key for key in data if key not in _PROPOSAL_KEYS]
        raw_children = data.get("children")
        if not isinstance(raw_children, list) or not raw_children:
            raise ValueError("coordinator proposal children must be a non-empty array")
        children: list[CoordinatorChildRequest] = []
        for index, raw_child in enumerate(raw_children):
            if not isinstance(raw_child, Mapping):
                raise ValueError("coordinator proposal child must be an object")
            if any(not isinstance(key, str) for key in raw_child):
                raise ValueError("coordinator proposal child keys must be strings")
            rejected.extend(
                f"children[{index}].{key}"
                for key in raw_child
                if key not in _CHILD_KEYS
            )
            children.append(
                CoordinatorChildRequest(
                    child_id=raw_child.get("child_id"),
                    task_digest=raw_child.get("task_digest"),
                    role_template_digest=raw_child.get("role_template_digest"),
                    context_capsule_ids=tuple(
                        raw_child.get("context_capsule_ids", ())
                    ),
                    required_capabilities=tuple(
                        raw_child.get("required_capabilities", ())
                    ),
                    cost_ceiling_usd=raw_child.get("cost_ceiling_usd"),
                )
            )
        return cls(
            schema_version=data.get("schema_version"),
            parent_plan_digest=data.get("parent_plan_digest"),
            source_candidate_digest=data.get("source_candidate_digest"),
            children=tuple(children),
            rejected_fields=tuple(rejected),
        )

    @classmethod
    def from_json(cls, data: str | bytes) -> "CoordinatorProposal":
        if isinstance(data, str):
            raw = data.encode("utf-8")
        elif isinstance(data, bytes):
            raw = data
        else:
            raise ValueError("coordinator proposal JSON must be text or bytes")
        if len(raw) > 1024 * 1024:
            raise ValueError("coordinator proposal JSON exceeds 1 MiB")

        def no_duplicates(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("coordinator proposal JSON has duplicate keys")
                result[key] = value
            return result

        try:
            decoded = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
        except UnicodeDecodeError as exc:
            raise ValueError("coordinator proposal JSON must be UTF-8") from exc
        except json.JSONDecodeError as exc:
            raise ValueError("coordinator proposal JSON is invalid") from exc
        return cls.from_dict(decoded)


@dataclass(frozen=True)
class CoordinatorConstraints:
    parent_plan_digest: str
    parent_plan_revision: int
    allowed_role_template_digests: tuple[str, ...]
    allowed_task_digests: tuple[str, ...]
    allowed_context_capsule_ids: tuple[str, ...]
    allowed_capabilities: tuple[str, ...]
    max_children: int
    per_child_cost_ceiling_usd: float
    aggregate_cost_ceiling_usd: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "parent_plan_digest",
            _digest("constraint parent_plan_digest", self.parent_plan_digest),
        )
        object.__setattr__(
            self,
            "parent_plan_revision",
            _positive_integer(
                "parent_plan_revision",
                self.parent_plan_revision,
                maximum=2_147_483_647,
            ),
        )
        for name in (
            "allowed_role_template_digests",
            "allowed_task_digests",
            "allowed_context_capsule_ids",
        ):
            object.__setattr__(
                self,
                name,
                _digest_set(name, getattr(self, name), required=True),
            )
        object.__setattr__(
            self,
            "allowed_capabilities",
            _identifier_set(
                "allowed_capabilities",
                self.allowed_capabilities,
                required=True,
            ),
        )
        object.__setattr__(
            self,
            "max_children",
            _positive_integer("max_children", self.max_children, maximum=32),
        )
        object.__setattr__(
            self,
            "per_child_cost_ceiling_usd",
            _cost(
                "per_child_cost_ceiling_usd",
                self.per_child_cost_ceiling_usd,
            ),
        )
        object.__setattr__(
            self,
            "aggregate_cost_ceiling_usd",
            _cost(
                "aggregate_cost_ceiling_usd",
                self.aggregate_cost_ceiling_usd,
            ),
        )

    @classmethod
    def from_parent(
        cls,
        parent: CoordinationPlan,
        *,
        allowed_role_template_digests: Iterable[str],
        allowed_task_digests: Iterable[str],
        allowed_context_capsule_ids: Iterable[str],
        allowed_capabilities: Iterable[str],
        max_children: int,
        per_child_cost_ceiling_usd: float,
        aggregate_cost_ceiling_usd: float,
    ) -> "CoordinatorConstraints":
        if not isinstance(parent, CoordinationPlan):
            raise ValueError("parent must be a CoordinationPlan")
        capsules = _digest_set(
            "allowed_context_capsule_ids",
            allowed_context_capsule_ids,
            required=True,
        )
        if not set(capsules).issubset(parent.context_capsule_ids):
            raise ValueError(
                "allowed context capsules must be present in parent plan"
            )
        return cls(
            parent_plan_digest=parent.plan_digest,
            parent_plan_revision=parent.plan_revision,
            allowed_role_template_digests=tuple(allowed_role_template_digests),
            allowed_task_digests=tuple(allowed_task_digests),
            allowed_context_capsule_ids=capsules,
            allowed_capabilities=tuple(allowed_capabilities),
            max_children=max_children,
            per_child_cost_ceiling_usd=per_child_cost_ceiling_usd,
            aggregate_cost_ceiling_usd=aggregate_cost_ceiling_usd,
        )

    @property
    def constraint_digest(self) -> str:
        return sha256_id("coordinator_constraints_v1", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "parent_plan_digest": self.parent_plan_digest,
            "parent_plan_revision": self.parent_plan_revision,
            "allowed_role_template_digests": list(
                self.allowed_role_template_digests
            ),
            "allowed_task_digests": list(self.allowed_task_digests),
            "allowed_context_capsule_ids": list(
                self.allowed_context_capsule_ids
            ),
            "allowed_capabilities": list(self.allowed_capabilities),
            "max_children": self.max_children,
            "per_child_cost_ceiling_usd": self.per_child_cost_ceiling_usd,
            "aggregate_cost_ceiling_usd": self.aggregate_cost_ceiling_usd,
        }


@dataclass(frozen=True)
class ProposedCoordinatorMember:
    child_id: str
    member_digest: str
    task_digest: str
    role_template_digest: str
    context_capsule_ids: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    cost_ceiling_usd: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "child_id", _identifier("child_id", self.child_id))
        for name in (
            "member_digest",
            "task_digest",
            "role_template_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name)),
            )
        object.__setattr__(
            self,
            "context_capsule_ids",
            _digest_set(
                "context_capsule_ids",
                self.context_capsule_ids,
                required=True,
            ),
        )
        object.__setattr__(
            self,
            "required_capabilities",
            _identifier_set(
                "required_capabilities",
                self.required_capabilities,
                required=True,
            ),
        )
        object.__setattr__(
            self,
            "cost_ceiling_usd",
            _cost("cost_ceiling_usd", self.cost_ceiling_usd),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "child_id": self.child_id,
            "member_digest": self.member_digest,
            "task_digest": self.task_digest,
            "role_template_digest": self.role_template_digest,
            "context_capsule_ids": list(self.context_capsule_ids),
            "required_capabilities": list(self.required_capabilities),
            "cost_ceiling_usd": self.cost_ceiling_usd,
        }


@dataclass(frozen=True)
class PlanRevisionProposal:
    parent_plan_digest: str
    parent_plan_revision: int
    proposed_revision: int
    topology_id: TopologyId
    source_proposal_digest: str
    constraint_digest: str
    members: tuple[ProposedCoordinatorMember, ...]
    aggregate_cost_ceiling_usd: float
    execution_mode: str = "shadow_only"
    host_authorization_required: bool = True
    authority_issued: bool = False
    network_activity: bool = False

    def __post_init__(self) -> None:
        _digest("parent_plan_digest", self.parent_plan_digest)
        _digest("source_proposal_digest", self.source_proposal_digest)
        _digest("constraint_digest", self.constraint_digest)
        _positive_integer(
            "parent_plan_revision",
            self.parent_plan_revision,
            maximum=2_147_483_647,
        )
        _positive_integer(
            "proposed_revision",
            self.proposed_revision,
            maximum=2_147_483_647,
        )
        if self.proposed_revision != self.parent_plan_revision + 1:
            raise ValueError("proposed revision must immediately follow parent")
        if self.topology_id is not TopologyId.T2_SUPERVISOR_WORKER:
            raise ValueError("coordinator revision topology must be T2")
        members = tuple(self.members)
        if not members or any(
            not isinstance(item, ProposedCoordinatorMember) for item in members
        ):
            raise ValueError("coordinator revision must contain valid members")
        members = tuple(sorted(members, key=lambda item: item.child_id))
        if (
            len({item.child_id for item in members}) != len(members)
            or len({item.member_digest for item in members}) != len(members)
        ):
            raise ValueError("coordinator revision members must be unique")
        if self.execution_mode != "shadow_only":
            raise ValueError("coordinator revision must remain shadow_only")
        if self.host_authorization_required is not True:
            raise ValueError("host authorization must remain required")
        if self.authority_issued is not False or self.network_activity is not False:
            raise ValueError("coordinator revision cannot issue authority or use network")
        aggregate = _cost(
            "aggregate_cost_ceiling_usd",
            self.aggregate_cost_ceiling_usd,
        )
        if abs(aggregate - sum(item.cost_ceiling_usd for item in members)) > 1e-12:
            raise ValueError(
                "aggregate cost must equal exact member cost ceilings"
            )
        object.__setattr__(self, "members", members)
        object.__setattr__(self, "aggregate_cost_ceiling_usd", aggregate)

    @property
    def revision_digest(self) -> str:
        return sha256_id("coordinator_plan_revision_v1", self.canonical_dict())

    def canonical_dict(self) -> dict[str, object]:
        return {
            "parent_plan_digest": self.parent_plan_digest,
            "parent_plan_revision": self.parent_plan_revision,
            "proposed_revision": self.proposed_revision,
            "topology_id": self.topology_id.value,
            "source_proposal_digest": self.source_proposal_digest,
            "constraint_digest": self.constraint_digest,
            "members": [item.to_dict() for item in self.members],
            "aggregate_cost_ceiling_usd": self.aggregate_cost_ceiling_usd,
            "execution_mode": self.execution_mode,
            "host_authorization_required": self.host_authorization_required,
            "authority_issued": self.authority_issued,
            "network_activity": self.network_activity,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self.canonical_dict(), "revision_digest": self.revision_digest}


def _reject_requested_controls(fields: tuple[str, ...]) -> None:
    if not fields:
        return
    for field in fields:
        lowered = field.casefold()
        for word in _FORBIDDEN_CONTROL_WORDS:
            if word in lowered:
                raise CoordinatorPolicyError(
                    f"coordinator proposal requests forbidden {word} control"
                )
    raise CoordinatorPolicyError(
        f"coordinator proposal contains unknown field {fields[0]}"
    )


def compile_coordinator_proposal(
    proposal: CoordinatorProposal,
    constraints: CoordinatorConstraints,
) -> PlanRevisionProposal:
    if not isinstance(proposal, CoordinatorProposal):
        raise ValueError("proposal must be a CoordinatorProposal")
    if not isinstance(constraints, CoordinatorConstraints):
        raise ValueError("constraints must be CoordinatorConstraints")
    _reject_requested_controls(proposal.rejected_fields)
    if proposal.parent_plan_digest != constraints.parent_plan_digest:
        raise CoordinatorPolicyError(
            "coordinator proposal parent plan does not match constraints"
        )
    if len(proposal.children) > constraints.max_children:
        raise CoordinatorPolicyError(
            "coordinator proposal exceeds maximum child count"
        )
    total = 0.0
    members: list[ProposedCoordinatorMember] = []
    for child in proposal.children:
        if child.role_template_digest not in constraints.allowed_role_template_digests:
            raise CoordinatorPolicyError(
                "coordinator proposal role template is not allowed"
            )
        if child.task_digest not in constraints.allowed_task_digests:
            raise CoordinatorPolicyError(
                "coordinator proposal task digest is not allowed"
            )
        if not set(child.context_capsule_ids).issubset(
            constraints.allowed_context_capsule_ids
        ):
            raise CoordinatorPolicyError(
                "coordinator proposal context expansion is not allowed"
            )
        if not set(child.required_capabilities).issubset(
            constraints.allowed_capabilities
        ):
            raise CoordinatorPolicyError(
                "coordinator proposal capability expansion is not allowed"
            )
        if (
            child.cost_ceiling_usd
            > constraints.per_child_cost_ceiling_usd + 1e-12
        ):
            raise CoordinatorPolicyError(
                "coordinator proposal child cost exceeds hard ceiling"
            )
        total += child.cost_ceiling_usd
        member_digest = sha256_id(
            "coordinator_member_v1",
            {
                "parent_plan_digest": constraints.parent_plan_digest,
                "proposed_revision": constraints.parent_plan_revision + 1,
                "child": child.to_dict(),
            },
        )
        members.append(
            ProposedCoordinatorMember(
                child_id=child.child_id,
                member_digest=member_digest,
                task_digest=child.task_digest,
                role_template_digest=child.role_template_digest,
                context_capsule_ids=child.context_capsule_ids,
                required_capabilities=child.required_capabilities,
                cost_ceiling_usd=child.cost_ceiling_usd,
            )
        )
    if total > constraints.aggregate_cost_ceiling_usd + 1e-12:
        raise CoordinatorPolicyError(
            "coordinator proposal aggregate cost exceeds hard ceiling"
        )
    return PlanRevisionProposal(
        parent_plan_digest=constraints.parent_plan_digest,
        parent_plan_revision=constraints.parent_plan_revision,
        proposed_revision=constraints.parent_plan_revision + 1,
        topology_id=TopologyId.T2_SUPERVISOR_WORKER,
        source_proposal_digest=proposal.proposal_digest,
        constraint_digest=constraints.constraint_digest,
        members=tuple(members),
        aggregate_cost_ceiling_usd=total,
    )


__all__ = [
    "CoordinatorChildRequest",
    "CoordinatorConstraints",
    "CoordinatorProposal",
    "PlanRevisionProposal",
    "ProposedCoordinatorMember",
    "compile_coordinator_proposal",
]
