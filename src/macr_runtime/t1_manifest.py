from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .batch_authority import BatchAuthorityReference
from .canonical import aware_iso8601, sha256_id
from .contracts import DelegationClass, PrivacyLevel, TaskContract
from .execution import AuthorizationReference
from .errors import LegacyPreTierIncompatibleError
from .providers.glm import contains_obvious_sensitive_marker
from .route_resolution import ExecutionRouteProposal
from .runtime import task_contract_digest
from .scheduler import TargetClaim
from .task_preflight import validate_task_consistency
from .token_policy import t1_glm_live_policy


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_T1_TOPOLOGY = "T1_FANOUT_VERIFIED"
_T1_PROVIDER = "glm_flash_worker"
_T1_PROVIDER_KIND = "zai_glm_worker"
_T1_MODEL = "glm-5.3-flash"
_T1_ENDPOINT = "https://api.z.ai/api/paas/v4"
_T1_CONTEXT_CLASS = "non_sensitive_routine"
_T1_MEMBER_COST_USD = 0.010
_T1_AGGREGATE_COST_USD = 0.030
_T1_CAMPAIGN_COST_USD = 0.040
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
T1_MANIFEST_SCHEMA_VERSION = 2


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded identifier")
    return value


def _cost(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite non-negative")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError(f"{name} must be finite non-negative")
    return normalized


def _exact_cost(name: str, value: object, expected: float) -> float:
    normalized = _cost(name, value)
    if not math.isclose(normalized, expected, rel_tol=0, abs_tol=1e-12):
        raise ValueError(f"{name} does not match the fixed T1 ceiling")
    return normalized


def _exact_keys(name: str, value: object, expected: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError(f"{name} fields must be exact")
    return value


def _all_strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield from _all_strings(key)
            yield from _all_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _all_strings(item)


def _task_from_dict(value: object) -> TaskContract:
    if not isinstance(value, Mapping):
        raise ValueError("T1 task must be an object")
    task = TaskContract.from_dict(value)
    if dict(value) != task.to_dict():
        raise ValueError("T1 task must be a complete exact TaskContract")
    return task


_ROUTE_FIELDS = {
    "proposal_digest",
    "route_id",
    "route_snapshot_id",
    "policy_snapshot_id",
    "provider_id",
    "provider_kind",
    "provider_model_id",
    "connection_scope",
    "endpoint_identity",
    "parameter_profile_digest",
    "prompt_compiler_version",
    "data_policy_snapshot_id",
    "resolution_state",
    "authority_issued",
    "network_activity",
}


def _route_from_dict(value: object) -> ExecutionRouteProposal:
    route = _exact_keys("T1 route proposal", value, _ROUTE_FIELDS)
    for name in (
        "proposal_digest",
        "route_id",
        "route_snapshot_id",
        "policy_snapshot_id",
        "parameter_profile_digest",
        "data_policy_snapshot_id",
    ):
        _digest(name, route[name])
    _identifier("prompt_compiler_version", route["prompt_compiler_version"])
    return ExecutionRouteProposal(**route)


_TARGET_FIELDS = {
    "target_key",
    "alternative_group",
    "materialize_automatically",
}


def _target_from_dict(value: object) -> TargetClaim:
    target = _exact_keys("T1 target claim", value, _TARGET_FIELDS)
    return TargetClaim(
        target_key=target["target_key"],
        alternative_group=target["alternative_group"],
        materialize_automatically=target["materialize_automatically"],
    )


@dataclass(frozen=True)
class T1ExecutionMember:
    member_digest: str
    plan_digest: str
    ordinal: int
    task: TaskContract
    route: ExecutionRouteProposal
    token_policy_digest: str
    provider_tier_binding_digest: str
    role_digest: str
    privacy: str
    context_class: str
    cost_ceiling_usd: float
    target_claims: tuple[TargetClaim, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_digest", _digest("plan_digest", self.plan_digest))
        if (
            isinstance(self.ordinal, bool)
            or not isinstance(self.ordinal, int)
            or not 0 <= self.ordinal <= 2
        ):
            raise ValueError("T1 member ordinal must be between 0 and 2")
        if not isinstance(self.task, TaskContract):
            raise ValueError("T1 member task must be a TaskContract")
        if not isinstance(self.route, ExecutionRouteProposal):
            raise ValueError("T1 member route must be an ExecutionRouteProposal")
        object.__setattr__(
            self,
            "token_policy_digest",
            _digest("token_policy_digest", self.token_policy_digest),
        )
        object.__setattr__(
            self,
            "provider_tier_binding_digest",
            _digest(
                "provider_tier_binding_digest",
                self.provider_tier_binding_digest,
            ),
        )
        object.__setattr__(
            self,
            "role_digest",
            _digest("role_digest", self.role_digest),
        )
        object.__setattr__(self, "privacy", _identifier("privacy", self.privacy))
        object.__setattr__(
            self,
            "context_class",
            _identifier("context_class", self.context_class),
        )
        object.__setattr__(
            self,
            "cost_ceiling_usd",
            _exact_cost(
                "cost_ceiling_usd",
                self.cost_ceiling_usd,
                _T1_MEMBER_COST_USD,
            ),
        )
        if isinstance(self.target_claims, (str, bytes)):
            raise ValueError("T1 target_claims must be an array")
        claims = tuple(self.target_claims)
        if any(not isinstance(item, TargetClaim) for item in claims):
            raise ValueError("T1 target_claims must contain TargetClaim values")
        claims = tuple(sorted(claims, key=lambda item: item.target_key))
        if len({item.target_key for item in claims}) != len(claims):
            raise ValueError("T1 target_claims must not contain duplicates")
        object.__setattr__(self, "target_claims", claims)
        self._validate_fixed_route()
        self._validate_task()
        expected = sha256_id("t1_execution_member_v2", self.canonical_member())
        if self.member_digest != expected:
            raise ValueError("T1 member digest does not match exact member")

    def _validate_fixed_route(self) -> None:
        route = self.route
        if (
            route.provider_id != _T1_PROVIDER
            or route.provider_kind != _T1_PROVIDER_KIND
            or route.provider_model_id != _T1_MODEL
            or route.connection_scope != "external_https"
            or route.endpoint_identity != _T1_ENDPOINT
        ):
            raise ValueError("T1 route does not match the fixed GLM execution route")
        if self.token_policy_digest != t1_glm_live_policy().policy_digest:
            raise ValueError("T1 member token policy does not match the live preset")
        if self.context_class != _T1_CONTEXT_CLASS:
            raise ValueError("T1 context class must be non_sensitive_routine")

    def _validate_task(self) -> None:
        task = self.task
        validate_task_consistency(task)
        if any(
            contains_obvious_sensitive_marker(value)
            for value in _all_strings(task.to_dict())
        ):
            raise ValueError("T1 task contains a sensitive marker or absolute path")
        if (
            not task.delegable
            or task.delegation_class is not DelegationClass.NON_SENSITIVE_ROUTINE
            or task.delegation_approval_sha256 is None
            or task.task_type != "delegated_routine"
            or task.constraints.privacy
            not in {PrivacyLevel.PUBLIC, PrivacyLevel.INTERNAL_APPROVED}
            or self.privacy != task.constraints.privacy.value
            or not task.constraints.internet
            or task.constraints.max_cost_usd > _T1_MEMBER_COST_USD + 1e-12
            or not math.isclose(
                task.constraints.max_cost_usd,
                self.cost_ceiling_usd,
                rel_tol=0,
                abs_tol=1e-12,
            )
            or task.constraints.max_output_tokens != 16_384
            or (
                task.constraints.max_context_tokens is not None
                and task.constraints.max_context_tokens > 128_000
            )
            or task.workspace.repo != "current"
            or bool(task.workspace.write_scope)
            or task.return_contract.patch
            or not task.verification.required
            or task.required_capabilities != ("text_generation",)
        ):
            raise ValueError("T1 task does not match the bounded worker contract")
        for item in task.inputs:
            if not isinstance(item, Mapping) or set(item) != {"type", "name", "content"}:
                raise ValueError("T1 inputs must be exact bounded text inputs")
            if item["type"] != "text":
                raise ValueError("T1 inputs must be exact bounded text inputs")

    @classmethod
    def create(
        cls,
        *,
        plan_digest: str,
        ordinal: int,
        task: TaskContract,
        route: ExecutionRouteProposal,
        token_policy_digest: str,
        provider_tier_binding_digest: str,
        role_digest: str,
        privacy: str,
        context_class: str,
        cost_ceiling_usd: float,
        target_claims: Sequence[TargetClaim],
    ) -> "T1ExecutionMember":
        if not isinstance(task, TaskContract):
            raise ValueError("T1 member task must be a TaskContract")
        if not isinstance(route, ExecutionRouteProposal):
            raise ValueError("T1 member route must be an ExecutionRouteProposal")
        if isinstance(target_claims, (str, bytes)) or any(
            not isinstance(item, TargetClaim) for item in target_claims
        ):
            raise ValueError("T1 target_claims must contain TargetClaim values")
        normalized_claims = tuple(sorted(target_claims, key=lambda item: item.target_key))
        values = {
            "plan_digest": _digest("plan_digest", plan_digest),
            "ordinal": ordinal,
            "task": task,
            "route": route,
            "token_policy_digest": token_policy_digest,
            "provider_tier_binding_digest": provider_tier_binding_digest,
            "role_digest": role_digest,
            "privacy": privacy,
            "context_class": context_class,
            "cost_ceiling_usd": _cost("cost_ceiling_usd", cost_ceiling_usd),
            "target_claims": normalized_claims,
        }
        canonical = {
            "plan_digest": values["plan_digest"],
            "ordinal": ordinal,
            "task_contract_digest": task_contract_digest(task),
            "route_proposal_digest": route.proposal_digest,
            "token_policy_digest": token_policy_digest,
            "provider_tier_binding_digest": provider_tier_binding_digest,
            "role_digest": role_digest,
            "privacy": privacy,
            "context_class": context_class,
            "cost_ceiling_usd": values["cost_ceiling_usd"],
            "target_claims": [item.to_dict() for item in normalized_claims],
        }
        digest = sha256_id("t1_execution_member_v2", canonical)
        return cls(member_digest=digest, **values)

    @classmethod
    def from_dict(cls, value: object) -> "T1ExecutionMember":
        expected = {
            "member_digest",
            "plan_digest",
            "ordinal",
            "task",
            "route",
            "token_policy_digest",
            "provider_tier_binding_digest",
            "role_digest",
            "privacy",
            "context_class",
            "cost_ceiling_usd",
            "target_claims",
        }
        data = _exact_keys("T1 member", value, expected)
        raw_targets = data["target_claims"]
        if not isinstance(raw_targets, list):
            raise ValueError("T1 target_claims must be an array")
        return cls(
            member_digest=data["member_digest"],
            plan_digest=data["plan_digest"],
            ordinal=data["ordinal"],
            task=_task_from_dict(data["task"]),
            route=_route_from_dict(data["route"]),
            token_policy_digest=data["token_policy_digest"],
            provider_tier_binding_digest=data["provider_tier_binding_digest"],
            role_digest=data["role_digest"],
            privacy=data["privacy"],
            context_class=data["context_class"],
            cost_ceiling_usd=data["cost_ceiling_usd"],
            target_claims=tuple(_target_from_dict(item) for item in raw_targets),
        )

    def canonical_member(self) -> dict[str, object]:
        return {
            "plan_digest": self.plan_digest,
            "ordinal": self.ordinal,
            "task_contract_digest": task_contract_digest(self.task),
            "route_proposal_digest": self.route.proposal_digest,
            "token_policy_digest": self.token_policy_digest,
            "provider_tier_binding_digest": self.provider_tier_binding_digest,
            "role_digest": self.role_digest,
            "privacy": self.privacy,
            "context_class": self.context_class,
            "cost_ceiling_usd": self.cost_ceiling_usd,
            "target_claims": [item.to_dict() for item in self.target_claims],
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "member_digest": self.member_digest,
            "plan_digest": self.plan_digest,
            "ordinal": self.ordinal,
            "task": self.task.to_dict(),
            "route": self.route.to_dict(),
            "token_policy_digest": self.token_policy_digest,
            "provider_tier_binding_digest": self.provider_tier_binding_digest,
            "role_digest": self.role_digest,
            "privacy": self.privacy,
            "context_class": self.context_class,
            "cost_ceiling_usd": self.cost_ceiling_usd,
            "target_claims": [item.to_dict() for item in self.target_claims],
        }


@dataclass(frozen=True)
class T1ExecutionManifest:
    manifest_digest: str
    plan_digest: str
    plan_revision: int
    members: tuple[T1ExecutionMember, ...]
    aggregate_cost_ceiling_usd: float
    campaign_cost_ceiling_usd: float
    expires_at: str
    authorized_dispatchers: tuple[str, ...]
    schema_version: int = T1_MANIFEST_SCHEMA_VERSION
    topology_id: str = _T1_TOPOLOGY

    def __post_init__(self) -> None:
        if self.schema_version != T1_MANIFEST_SCHEMA_VERSION:
            raise ValueError("T1 manifest schema_version must be 2")
        if self.topology_id != _T1_TOPOLOGY:
            raise ValueError("T1 manifest topology must be T1_FANOUT_VERIFIED")
        object.__setattr__(self, "plan_digest", _digest("plan_digest", self.plan_digest))
        if (
            isinstance(self.plan_revision, bool)
            or not isinstance(self.plan_revision, int)
            or self.plan_revision < 1
        ):
            raise ValueError("T1 plan_revision must be a positive integer")
        members = tuple(self.members)
        if len(members) != 3 or any(
            not isinstance(item, T1ExecutionMember) for item in members
        ):
            raise ValueError("T1 manifest must contain exactly three members")
        if tuple(item.ordinal for item in members) != (0, 1, 2):
            raise ValueError("T1 manifest member ordinals must be exact and ordered")
        if any(item.plan_digest != self.plan_digest for item in members):
            raise ValueError("T1 member plan digest does not match manifest")
        if len({item.member_digest for item in members}) != 3:
            raise ValueError("T1 manifest members must be unique")
        if len({item.task.task_id for item in members}) != 3:
            raise ValueError("T1 manifest task IDs must be unique")
        if len({item.provider_tier_binding_digest for item in members}) != 1:
            raise ValueError("T1 manifest members must use one provider tier binding")
        object.__setattr__(self, "members", members)
        object.__setattr__(
            self,
            "aggregate_cost_ceiling_usd",
            _exact_cost(
                "aggregate_cost_ceiling_usd",
                self.aggregate_cost_ceiling_usd,
                _T1_AGGREGATE_COST_USD,
            ),
        )
        object.__setattr__(
            self,
            "campaign_cost_ceiling_usd",
            _exact_cost(
                "campaign_cost_ceiling_usd",
                self.campaign_cost_ceiling_usd,
                _T1_CAMPAIGN_COST_USD,
            ),
        )
        if not math.isclose(
            sum(item.cost_ceiling_usd for item in members),
            self.aggregate_cost_ceiling_usd,
            rel_tol=0,
            abs_tol=1e-12,
        ):
            raise ValueError("T1 member costs do not match aggregate ceiling")
        object.__setattr__(
            self,
            "expires_at",
            aware_iso8601("expires_at", self.expires_at),
        )
        if isinstance(self.authorized_dispatchers, (str, bytes)):
            raise ValueError("authorized_dispatchers must be an array")
        dispatchers = tuple(
            sorted(
                _identifier("authorized dispatcher", item)
                for item in self.authorized_dispatchers
            )
        )
        if len(dispatchers) != 3 or len(set(dispatchers)) != 3:
            raise ValueError("T1 manifest requires three unique dispatchers")
        object.__setattr__(self, "authorized_dispatchers", dispatchers)
        expected = sha256_id("t1_execution_manifest_v2", self.canonical_manifest())
        if self.manifest_digest != expected:
            raise ValueError("T1 manifest digest does not match exact manifest")

    @classmethod
    def create(
        cls,
        *,
        plan_digest: str,
        members: Sequence[T1ExecutionMember],
        aggregate_cost_ceiling_usd: float,
        campaign_cost_ceiling_usd: float,
        expires_at: str,
        authorized_dispatchers: Sequence[str],
        plan_revision: int = 1,
    ) -> "T1ExecutionManifest":
        if isinstance(members, (str, bytes)) or any(
            not isinstance(item, T1ExecutionMember) for item in members
        ):
            raise ValueError("T1 manifest members must contain execution members")
        normalized_members = tuple(members)
        if isinstance(authorized_dispatchers, (str, bytes)):
            raise ValueError("authorized_dispatchers must be an array")
        normalized_dispatchers = tuple(
            sorted(
                _identifier("authorized dispatcher", item)
                for item in authorized_dispatchers
            )
        )
        canonical = {
            "schema_version": 2,
            "topology_id": _T1_TOPOLOGY,
            "plan_digest": plan_digest,
            "plan_revision": plan_revision,
            "ordered_member_digests": [item.member_digest for item in normalized_members],
            "aggregate_cost_ceiling_usd": float(aggregate_cost_ceiling_usd),
            "campaign_cost_ceiling_usd": float(campaign_cost_ceiling_usd),
            "expires_at": aware_iso8601("expires_at", expires_at),
            "authorized_dispatchers": list(normalized_dispatchers),
        }
        return cls(
            manifest_digest=sha256_id("t1_execution_manifest_v2", canonical),
            plan_digest=plan_digest,
            plan_revision=plan_revision,
            members=normalized_members,
            aggregate_cost_ceiling_usd=aggregate_cost_ceiling_usd,
            campaign_cost_ceiling_usd=campaign_cost_ceiling_usd,
            expires_at=expires_at,
            authorized_dispatchers=normalized_dispatchers,
        )

    @classmethod
    def from_dict(cls, value: object) -> "T1ExecutionManifest":
        if isinstance(value, Mapping) and value.get("schema_version") == 1:
            raise LegacyPreTierIncompatibleError(
                "legacy_pre_tier_incompatible: T1 schema 1 is audit-only"
            )
        expected = {
            "manifest_digest",
            "schema_version",
            "topology_id",
            "plan_digest",
            "plan_revision",
            "members",
            "aggregate_cost_ceiling_usd",
            "campaign_cost_ceiling_usd",
            "expires_at",
            "authorized_dispatchers",
        }
        data = _exact_keys("T1 manifest", value, expected)
        if not isinstance(data["members"], list):
            raise ValueError("T1 manifest members must be an array")
        if not isinstance(data["authorized_dispatchers"], list):
            raise ValueError("authorized_dispatchers must be an array")
        return cls(
            manifest_digest=data["manifest_digest"],
            schema_version=data["schema_version"],
            topology_id=data["topology_id"],
            plan_digest=data["plan_digest"],
            plan_revision=data["plan_revision"],
            members=tuple(T1ExecutionMember.from_dict(item) for item in data["members"]),
            aggregate_cost_ceiling_usd=data["aggregate_cost_ceiling_usd"],
            campaign_cost_ceiling_usd=data["campaign_cost_ceiling_usd"],
            expires_at=data["expires_at"],
            authorized_dispatchers=tuple(data["authorized_dispatchers"]),
        )

    def canonical_manifest(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "topology_id": self.topology_id,
            "plan_digest": self.plan_digest,
            "plan_revision": self.plan_revision,
            "ordered_member_digests": [item.member_digest for item in self.members],
            "aggregate_cost_ceiling_usd": self.aggregate_cost_ceiling_usd,
            "campaign_cost_ceiling_usd": self.campaign_cost_ceiling_usd,
            "expires_at": self.expires_at,
            "authorized_dispatchers": list(self.authorized_dispatchers),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_digest": self.manifest_digest,
            "schema_version": self.schema_version,
            "topology_id": self.topology_id,
            "plan_digest": self.plan_digest,
            "plan_revision": self.plan_revision,
            "members": [item.to_dict() for item in self.members],
            "aggregate_cost_ceiling_usd": self.aggregate_cost_ceiling_usd,
            "campaign_cost_ceiling_usd": self.campaign_cost_ceiling_usd,
            "expires_at": self.expires_at,
            "authorized_dispatchers": list(self.authorized_dispatchers),
        }


@dataclass(frozen=True)
class T1AuthorityBundle:
    manifest_digest: str
    batch_authority: BatchAuthorityReference
    dispatch_authority: AuthorizationReference
    member_ids: tuple[str, ...]
    expires_at: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "manifest_digest",
            _digest("manifest_digest", self.manifest_digest),
        )
        if not isinstance(self.batch_authority, BatchAuthorityReference):
            raise ValueError("batch_authority is invalid")
        if not isinstance(self.dispatch_authority, AuthorizationReference):
            raise ValueError("dispatch_authority is invalid")
        members = tuple(_digest("member_id", item) for item in self.member_ids)
        if len(members) != 3 or len(set(members)) != 3:
            raise ValueError("T1 authority bundle requires three member IDs")
        object.__setattr__(self, "member_ids", members)
        object.__setattr__(
            self,
            "expires_at",
            aware_iso8601("expires_at", self.expires_at),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_digest": self.manifest_digest,
            "batch_authority": {
                "authority_id": self.batch_authority.authority_id,
                "digest": self.batch_authority.digest,
                "revision": self.batch_authority.revision,
                "plan_digest": self.batch_authority.plan_digest,
            },
            "dispatch_authority": {
                "source_kind": self.dispatch_authority.source_kind,
                "source_id": self.dispatch_authority.source_id,
                "digest": self.dispatch_authority.digest,
                "revision": self.dispatch_authority.revision,
                "epoch": self.dispatch_authority.epoch,
                "scope": self.dispatch_authority.scope,
            },
            "member_ids": list(self.member_ids),
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class T1ManifestInspection:
    status: str
    schema_version: int
    manifest_digest: str
    member_count: int


def _reject_duplicate_keys(pairs):
    document = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"duplicate JSON key: {key}")
        document[key] = value
    return document


def _load_t1_document(path: str | Path) -> Mapping[str, Any]:
    candidate = Path(path)
    if not candidate.is_file():
        raise ValueError("T1 manifest path must be a file")
    raw = candidate.read_bytes()
    if not raw or len(raw) > _MAX_MANIFEST_BYTES:
        raise ValueError("T1 manifest file size is invalid")
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"invalid JSON constant: {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("T1 manifest must be strict UTF-8 JSON") from exc
    if not isinstance(document, Mapping):
        raise ValueError("T1 manifest must be a JSON object")
    return document


def inspect_t1_manifest(path: str | Path) -> T1ManifestInspection:
    document = _load_t1_document(path)
    schema_version = document.get("schema_version")
    members = document.get("members")
    manifest_digest = document.get("manifest_digest")
    if schema_version not in {1, 2}:
        raise ValueError("T1 manifest schema_version is unsupported")
    if not isinstance(members, list) or len(members) != 3:
        raise ValueError("T1 manifest must contain exactly three members")
    digest = _digest("manifest_digest", manifest_digest)
    if schema_version == 2:
        T1ExecutionManifest.from_dict(document)
    return T1ManifestInspection(
        status=("legacy_pre_tier" if schema_version == 1 else "current"),
        schema_version=schema_version,
        manifest_digest=digest,
        member_count=len(members),
    )


def load_t1_manifest(path: str | Path) -> T1ExecutionManifest:
    document = _load_t1_document(path)
    if document.get("schema_version") == 1:
        raise LegacyPreTierIncompatibleError(
            "legacy_pre_tier_incompatible: T1 schema 1 is audit-only"
        )
    return T1ExecutionManifest.from_dict(document)


__all__ = [
    "T1AuthorityBundle",
    "T1ExecutionManifest",
    "T1ExecutionMember",
    "T1ManifestInspection",
    "T1_MANIFEST_SCHEMA_VERSION",
    "inspect_t1_manifest",
    "load_t1_manifest",
]
