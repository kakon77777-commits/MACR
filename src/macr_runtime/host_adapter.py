from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol

from .canonical import sha256_id
from .config import ConnectionScope
from .contracts import ProviderResult, TaskContract
from .errors import DispatchAuthorizationError, ProviderPolicyError
from .execution import (
    AuthorizationReference,
    DispatchContext,
    DispatchOrigin,
    InteractionPlane,
)
from .provider_capability import ProviderTierBinding
from .provider_admission import AdmissionLane, ProjectAdmissionBinding
from .registry import ProviderRegistry
from .runtime import MacrRuntime, RuntimeServices, task_contract_digest


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HOST_IDENTIFIER_KIND = {
    "codex": "codex_thread_id",
    "claude_code": "claude_code_session_id",
}


class HostKind(str, Enum):
    CODEX = "codex"
    CLAUDE_CODE = "claude_code"


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded identifier")
    return value


def _session_id(value: object) -> str:
    try:
        parsed = uuid.UUID(value)  # type: ignore[arg-type]
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("host native_id must be a canonical UUID") from exc
    if str(parsed) != value:
        raise ValueError("host native_id must be a canonical UUID")
    return str(parsed)


@dataclass(frozen=True)
class HostBindingEvidence:
    host_kind: HostKind
    identifier_kind: str
    native_id: str
    verifier_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.host_kind, HostKind):
            raise ValueError("host_kind must be a HostKind")
        expected = _HOST_IDENTIFIER_KIND[self.host_kind.value]
        if self.identifier_kind != expected:
            raise ValueError("host identifier kind does not match host kind")
        object.__setattr__(self, "native_id", _session_id(self.native_id))
        object.__setattr__(
            self,
            "verifier_digest",
            _digest("verifier_digest", self.verifier_digest),
        )


@dataclass(frozen=True, init=False)
class VerifiedHostBinding:
    host_kind: HostKind
    identifier_kind: str
    native_id: str
    binding_source: str
    verifier_digest: str

    @classmethod
    def _from_evidence(
        cls,
        evidence: HostBindingEvidence,
    ) -> "VerifiedHostBinding":
        if not isinstance(evidence, HostBindingEvidence):
            raise ProviderPolicyError(
                "host-owned verifier returned invalid binding evidence"
            )
        instance = object.__new__(cls)
        object.__setattr__(instance, "host_kind", evidence.host_kind)
        object.__setattr__(instance, "identifier_kind", evidence.identifier_kind)
        object.__setattr__(instance, "native_id", evidence.native_id)
        object.__setattr__(
            instance,
            "binding_source",
            "task_local_host_observed",
        )
        object.__setattr__(instance, "verifier_digest", evidence.verifier_digest)
        return instance

    @property
    def binding_digest(self) -> str:
        return sha256_id("verified_host_binding_v1", self.to_dict())

    def to_dict(self) -> dict[str, str]:
        return {
            "host_kind": self.host_kind.value,
            "identifier_kind": self.identifier_kind,
            "native_id": self.native_id,
            "binding_source": self.binding_source,
            "verifier_digest": self.verifier_digest,
        }


class HostBindingVerifier(Protocol):
    def verify(self) -> HostBindingEvidence: ...


@dataclass(frozen=True)
class HostInvocationGrant:
    authorization: AuthorizationReference
    provider_id: str
    connection_scope: str
    provider_tier_binding_digest: str | None
    grant_digest: str
    project_binding_digest: str | None = None
    admission_lane: str | None = None
    provider_admission_policy_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.authorization, AuthorizationReference):
            raise ValueError("host invocation authorization is invalid")
        object.__setattr__(
            self,
            "provider_id",
            _identifier("provider_id", self.provider_id),
        )
        if self.connection_scope not in {
            ConnectionScope.EXTERNAL_HTTPS.value,
            ConnectionScope.LOOPBACK_HTTP.value,
        }:
            raise ValueError("host invocation connection scope is invalid")
        if self.provider_tier_binding_digest is not None:
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
            "grant_digest",
            _digest("grant_digest", self.grant_digest),
        )
        admission_values = (
            self.project_binding_digest,
            self.admission_lane,
            self.provider_admission_policy_digest,
        )
        if any(item is not None for item in admission_values):
            if any(item is None for item in admission_values):
                raise ValueError(
                    "host invocation admission binding must be complete"
                )
            object.__setattr__(
                self,
                "project_binding_digest",
                _digest(
                    "project_binding_digest",
                    self.project_binding_digest,
                ),
            )
            if self.admission_lane not in {
                item.value for item in AdmissionLane
            }:
                raise ValueError("host invocation admission lane is invalid")
            object.__setattr__(
                self,
                "provider_admission_policy_digest",
                _digest(
                    "provider_admission_policy_digest",
                    self.provider_admission_policy_digest,
                ),
            )


class HostInvocationGrantVerifier(Protocol):
    def verify(
        self,
        grant: HostInvocationGrant,
        preparation: "HostDispatchPreparation",
    ) -> None: ...


@dataclass(frozen=True)
class HostDispatchPreparation:
    provider_id: str
    connection_scope: str
    task_digest: str
    model_token_policy_digest: str | None
    provider_tier_binding_digest: str | None
    approval_digest: str | None
    cost_ceiling_usd: float
    host_binding_digest: str
    request_digest: str
    project_binding_digest: str | None
    admission_lane: str | None
    provider_admission_policy_digest: str | None
    _binding: VerifiedHostBinding = field(repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "connection_scope": self.connection_scope,
            "task_digest": self.task_digest,
            "model_token_policy_digest": self.model_token_policy_digest,
            "provider_tier_binding_digest": self.provider_tier_binding_digest,
            "approval_digest": self.approval_digest,
            "cost_ceiling_usd": self.cost_ceiling_usd,
            "host_binding_digest": self.host_binding_digest,
            "request_digest": self.request_digest,
            "project_binding_digest": self.project_binding_digest,
            "admission_lane": self.admission_lane,
            "provider_admission_policy_digest": (
                self.provider_admission_policy_digest
            ),
        }


class MacrHostAdapter:
    def __init__(
        self,
        registry: ProviderRegistry,
        services: RuntimeServices,
        *,
        host_verifier: HostBindingVerifier,
        grant_verifier: HostInvocationGrantVerifier,
        admission_project: ProjectAdmissionBinding | None = None,
        admission_lane: AdmissionLane = AdmissionLane.ROUTINE,
    ) -> None:
        if not isinstance(registry, ProviderRegistry):
            raise ValueError("registry must be a ProviderRegistry")
        if not isinstance(services, RuntimeServices):
            raise ValueError("services must be RuntimeServices")
        self.registry = registry
        self.services = services
        self.host_verifier = host_verifier
        self.grant_verifier = grant_verifier
        if admission_project is not None and not isinstance(
            admission_project,
            ProjectAdmissionBinding,
        ):
            raise ValueError(
                "admission_project must be a ProjectAdmissionBinding"
            )
        if not isinstance(admission_lane, AdmissionLane):
            raise ValueError("admission_lane must be an AdmissionLane")
        self.admission_project = admission_project
        self.admission_lane = admission_lane

    def _verified_binding(self) -> VerifiedHostBinding:
        method = getattr(self.host_verifier, "verify", None)
        if not callable(method):
            raise ProviderPolicyError(
                "host adapter requires an injected host-owned verifier"
            )
        return VerifiedHostBinding._from_evidence(method())

    def _prepare(
        self,
        provider_id: str,
        task: TaskContract,
    ) -> HostDispatchPreparation:
        if provider_id == "claude_subscription":
            raise ProviderPolicyError(
                "Claude subscription is not an Anthropic API provider route"
            )
        if not isinstance(task, TaskContract):
            raise ValueError("task must be a TaskContract")
        binding = self._verified_binding()
        provider = self.registry.get(provider_id)
        requires_provider_admission = bool(
            getattr(provider, "requires_provider_admission", False)
        )
        provider_admission = self.services.provider_admission_for(provider_id)
        if requires_provider_admission and (
            self.admission_project is None
            or provider_admission is None
        ):
            raise ProviderPolicyError(
                "host adapter requires operator-bound provider admission identity"
            )
        model_token_policy_digest = None
        if self.registry.requires_model_token_policy(provider_id):
            token_policy = self.registry.token_policy(
                provider_id,
                store=self.services.token_policies,
            )
            model_token_policy_digest = token_policy.policy_digest
        provider_binding = getattr(provider, "capability_binding", None)
        provider_tier_binding_digest = (
            provider_binding.binding_digest
            if isinstance(provider_binding, ProviderTierBinding)
            else None
        )
        approval_digest = task.delegation_approval_sha256
        cost_ceiling = float(task.constraints.max_cost_usd)
        approval_metadata_method = getattr(provider, "approval_metadata", None)
        if callable(approval_metadata_method):
            metadata = approval_metadata_method(task)
            if not isinstance(metadata, Mapping):
                raise ProviderPolicyError("provider approval metadata is invalid")
            approval_digest = metadata.get("required_approval_sha256")
            if approval_digest is not None:
                _digest("approval_digest", approval_digest)
            metadata_binding = metadata.get("provider_tier_binding_digest")
            if metadata_binding != provider_tier_binding_digest:
                raise ProviderPolicyError(
                    "provider approval does not bind active capability tier"
                )
            reported_cost = metadata.get("conservative_cost_ceiling_usd")
            if isinstance(reported_cost, (int, float)) and not isinstance(
                reported_cost,
                bool,
            ):
                cost_ceiling = float(reported_cost)
        common = {
            "provider_id": provider_id,
            "connection_scope": provider.connection_scope.value,
            "task_digest": task_contract_digest(task),
            "model_token_policy_digest": model_token_policy_digest,
            "provider_tier_binding_digest": provider_tier_binding_digest,
            "approval_digest": approval_digest,
            "cost_ceiling_usd": cost_ceiling,
            "project_binding_digest": (
                self.admission_project.binding_digest
                if requires_provider_admission
                and self.admission_project is not None
                else None
            ),
            "admission_lane": (
                self.admission_lane.value
                if requires_provider_admission
                else None
            ),
            "provider_admission_policy_digest": (
                provider_admission.policy.policy_digest
                if requires_provider_admission
                and provider_admission is not None
                else None
            ),
        }
        host_binding_digest = binding.binding_digest
        request_digest = sha256_id(
            "host_dispatch_request_v1",
            {**common, "host_binding_digest": host_binding_digest},
        )
        return HostDispatchPreparation(
            **common,
            host_binding_digest=host_binding_digest,
            request_digest=request_digest,
            _binding=binding,
        )

    def preflight(
        self,
        provider_id: str,
        task: TaskContract,
    ) -> HostDispatchPreparation:
        return self._prepare(provider_id, task)

    def invoke(
        self,
        provider_id: str,
        task: TaskContract,
        grant: HostInvocationGrant | None,
    ) -> ProviderResult:
        if not isinstance(grant, HostInvocationGrant):
            raise DispatchAuthorizationError(
                "host invocation requires a pre-issued operator grant"
            )
        preparation = self._prepare(provider_id, task)
        verifier = getattr(self.grant_verifier, "verify", None)
        if not callable(verifier):
            raise DispatchAuthorizationError(
                "host invocation grant verifier is unavailable"
            )
        verifier(grant, preparation)
        if (
            grant.provider_id != preparation.provider_id
            or grant.connection_scope != preparation.connection_scope
            or grant.provider_tier_binding_digest
            != preparation.provider_tier_binding_digest
            or grant.project_binding_digest
            != preparation.project_binding_digest
            or grant.admission_lane != preparation.admission_lane
            or grant.provider_admission_policy_digest
            != preparation.provider_admission_policy_digest
        ):
            raise DispatchAuthorizationError(
                "host invocation grant does not match preparation"
            )
        binding = preparation._binding
        context = DispatchContext(
            run_id=str(uuid.uuid4()),
            plane=InteractionPlane.DELEGATION,
            origin=DispatchOrigin(
                binding.host_kind.value,
                binding.identifier_kind,
                binding.native_id,
            ),
            authorization=grant.authorization,
            policy_snapshot_sha256=preparation.request_digest,
            member_digest=task.delegation_approval_sha256,
            model_token_policy_digest=preparation.model_token_policy_digest,
            provider_tier_binding_digest=(
                preparation.provider_tier_binding_digest
            ),
            project_binding_digest=preparation.project_binding_digest,
            admission_lane=preparation.admission_lane,
            provider_admission_policy_digest=(
                preparation.provider_admission_policy_digest
            ),
        )
        return MacrRuntime(self.registry, self.services).invoke(
            provider_id,
            task,
            context,
        )


__all__ = [
    "HostBindingEvidence",
    "HostBindingVerifier",
    "HostDispatchPreparation",
    "HostInvocationGrant",
    "HostInvocationGrantVerifier",
    "HostKind",
    "MacrHostAdapter",
    "VerifiedHostBinding",
]
