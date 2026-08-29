from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .canonical import aware_iso8601, sha256_id
from .coordination import ModelBinding
from .errors import MacrError, ProviderUnavailableError
from .model_identity import ExecutionRouteIdentity
from .registry import ProviderRegistry


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class RouteResolutionError(MacrError):
    """A plan binding cannot become an execution proposal."""


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded identifier")
    return value


def _identifiers(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must contain identifiers")
    normalized = tuple(_identifier(f"{name} item", item) for item in values)
    if not normalized or len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must be non-empty and unique")
    return tuple(sorted(normalized))


@dataclass(frozen=True)
class ExecutionRouteSnapshot:
    snapshot_id: str
    observed_at: str
    routes: tuple[ExecutionRouteIdentity, ...]
    discovery_only_route_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        snapshot_id = _digest("snapshot_id", self.snapshot_id)
        observed_at = aware_iso8601("observed_at", self.observed_at)
        routes = tuple(sorted(self.routes, key=lambda item: item.route_id))
        if not routes or any(
            not isinstance(item, ExecutionRouteIdentity) for item in routes
        ):
            raise ValueError("routes must contain ExecutionRouteIdentity values")
        if len({item.route_id for item in routes}) != len(routes):
            raise ValueError("routes contain duplicate route_id")
        discovery = tuple(sorted(self.discovery_only_route_ids))
        if any(not _SHA256.fullmatch(item) for item in discovery):
            raise ValueError("discovery_only_route_ids must contain digests")
        if len(set(discovery)) != len(discovery):
            raise ValueError("discovery_only_route_ids contain duplicates")
        if not set(discovery).issubset({item.route_id for item in routes}):
            raise ValueError("discovery-only route is absent from route snapshot")
        canonical = {
            "observed_at": observed_at,
            "routes": [
                {"route_id": item.route_id, **item.canonical_identity()}
                for item in routes
            ],
            "discovery_only_route_ids": list(discovery),
        }
        expected = sha256_id("execution_route_snapshot_v1", canonical)
        if snapshot_id != expected:
            raise ValueError("route snapshot digest does not match routes")
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "routes", routes)
        object.__setattr__(self, "discovery_only_route_ids", discovery)

    @classmethod
    def build(
        cls,
        routes: Iterable[ExecutionRouteIdentity],
        *,
        discovery_only_route_ids: Iterable[str],
        observed_at: str,
    ) -> "ExecutionRouteSnapshot":
        routes_tuple = tuple(routes)
        if not routes_tuple or any(
            not isinstance(item, ExecutionRouteIdentity) for item in routes_tuple
        ):
            raise ValueError("routes must contain ExecutionRouteIdentity values")
        routes_tuple = tuple(sorted(routes_tuple, key=lambda item: item.route_id))
        discovery = tuple(
            sorted(_digest("discovery route id", item) for item in discovery_only_route_ids)
        )
        normalized_time = aware_iso8601("observed_at", observed_at)
        canonical = {
            "observed_at": normalized_time,
            "routes": [
                {"route_id": item.route_id, **item.canonical_identity()}
                for item in routes_tuple
            ],
            "discovery_only_route_ids": list(discovery),
        }
        return cls(
            snapshot_id=sha256_id("execution_route_snapshot_v1", canonical),
            observed_at=normalized_time,
            routes=routes_tuple,
            discovery_only_route_ids=discovery,
        )

    def get(self, route_id: str) -> ExecutionRouteIdentity:
        route_id = _digest("route_id", route_id)
        try:
            return next(item for item in self.routes if item.route_id == route_id)
        except StopIteration as exc:
            raise RouteResolutionError("route is absent from exact route snapshot") from exc


@dataclass(frozen=True)
class RouteResolutionPolicy:
    policy_snapshot_id: str
    allowed_provider_ids: tuple[str, ...]
    require_exact_model: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_snapshot_id",
            _digest("policy_snapshot_id", self.policy_snapshot_id),
        )
        object.__setattr__(
            self,
            "allowed_provider_ids",
            _identifiers("allowed_provider_ids", self.allowed_provider_ids),
        )
        if not isinstance(self.require_exact_model, bool):
            raise ValueError("require_exact_model must be boolean")
        if self.require_exact_model is not True:
            raise ValueError("route resolution requires exact model matching")


@dataclass(frozen=True)
class ExecutionRouteProposal:
    proposal_digest: str
    route_id: str
    route_snapshot_id: str
    policy_snapshot_id: str
    provider_id: str
    provider_kind: str
    provider_model_id: str
    connection_scope: str
    endpoint_identity: str
    parameter_profile_digest: str
    prompt_compiler_version: str
    data_policy_snapshot_id: str
    resolution_state: str = "proposal_only"
    authority_issued: bool = False
    network_activity: bool = False

    def __post_init__(self) -> None:
        expected = sha256_id(
            "execution_route_proposal_v1",
            self.canonical_proposal(),
        )
        if self.proposal_digest != expected:
            raise ValueError("proposal digest does not match route proposal")
        if self.resolution_state != "proposal_only":
            raise ValueError("route resolution state must be proposal_only")
        if self.authority_issued or self.network_activity:
            raise ValueError("route proposal cannot issue authority or use network")

    def canonical_proposal(self) -> dict[str, object]:
        return {
            "route_id": self.route_id,
            "route_snapshot_id": self.route_snapshot_id,
            "policy_snapshot_id": self.policy_snapshot_id,
            "provider_id": self.provider_id,
            "provider_kind": self.provider_kind,
            "provider_model_id": self.provider_model_id,
            "connection_scope": self.connection_scope,
            "endpoint_identity": self.endpoint_identity,
            "parameter_profile_digest": self.parameter_profile_digest,
            "prompt_compiler_version": self.prompt_compiler_version,
            "data_policy_snapshot_id": self.data_policy_snapshot_id,
            "resolution_state": self.resolution_state,
            "authority_issued": self.authority_issued,
            "network_activity": self.network_activity,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "proposal_digest": self.proposal_digest,
            **self.canonical_proposal(),
        }


class ExecutionProviderResolver:
    def __init__(
        self,
        registry: ProviderRegistry,
        route_snapshot: ExecutionRouteSnapshot,
    ) -> None:
        if not isinstance(registry, ProviderRegistry):
            raise ValueError("registry must be a ProviderRegistry")
        if not isinstance(route_snapshot, ExecutionRouteSnapshot):
            raise ValueError("route_snapshot must be an ExecutionRouteSnapshot")
        self.registry = registry
        self.route_snapshot = route_snapshot

    def resolve(
        self,
        binding: ModelBinding,
        policy: RouteResolutionPolicy,
    ) -> ExecutionRouteProposal:
        if not isinstance(binding, ModelBinding):
            raise ValueError("binding must be a ModelBinding")
        if not isinstance(policy, RouteResolutionPolicy):
            raise ValueError("policy must be a RouteResolutionPolicy")
        route = self.route_snapshot.get(binding.route_id)
        if (
            route.route_id in self.route_snapshot.discovery_only_route_ids
            or "discovery" in route.provider_id
        ):
            raise RouteResolutionError(
                "discovery-only route cannot resolve as execution provider"
            )
        if route.model_subject_id != binding.model_subject_id:
            raise RouteResolutionError("binding model subject does not match route")
        if route.parameter_profile_digest != binding.parameter_profile_digest:
            raise RouteResolutionError("binding parameter profile does not match route")
        if route.provider_id not in policy.allowed_provider_ids:
            raise RouteResolutionError("provider is denied by route resolution policy")
        try:
            profile = self.registry.execution_profile(route.provider_id)
        except ProviderUnavailableError as exc:
            raise RouteResolutionError("execution provider is unavailable") from exc
        if not profile["enabled"] or not profile["api_usage_allowed"]:
            raise RouteResolutionError("execution provider policy is disabled")
        configured_model = profile["model"]
        if (
            policy.require_exact_model
            and configured_model != route.provider_model_id
        ):
            raise RouteResolutionError(
                "execution provider model does not match exact route model"
            )
        if profile["base_url"] != route.endpoint_identity:
            raise RouteResolutionError(
                "execution provider endpoint does not match exact route endpoint"
            )
        canonical = {
            "route_id": route.route_id,
            "route_snapshot_id": self.route_snapshot.snapshot_id,
            "policy_snapshot_id": policy.policy_snapshot_id,
            "provider_id": route.provider_id,
            "provider_kind": profile["kind"],
            "provider_model_id": route.provider_model_id,
            "connection_scope": profile["connection_scope"],
            "endpoint_identity": route.endpoint_identity,
            "parameter_profile_digest": route.parameter_profile_digest,
            "prompt_compiler_version": route.prompt_compiler_version,
            "data_policy_snapshot_id": route.data_policy_snapshot_id,
            "resolution_state": "proposal_only",
            "authority_issued": False,
            "network_activity": False,
        }
        return ExecutionRouteProposal(
            proposal_digest=sha256_id(
                "execution_route_proposal_v1",
                canonical,
            ),
            **canonical,
        )


__all__ = [
    "ExecutionProviderResolver",
    "ExecutionRouteProposal",
    "ExecutionRouteSnapshot",
    "RouteResolutionError",
    "RouteResolutionPolicy",
]
