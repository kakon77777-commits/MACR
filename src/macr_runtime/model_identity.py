from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .canonical import sha256_id


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


def _text(name: str, value: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    normalized = value.strip()
    if len(normalized.encode("utf-8")) > maximum:
        raise ValueError(f"{name} is too long")
    return normalized


def _optional_text(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    return _text(name, value, maximum=512)


def _canonical_identifiers(
    name: str,
    values: Iterable[str],
    *,
    required: bool,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be an iterable of identifiers")
    normalized = tuple(_identifier(f"{name} item", item) for item in values)
    if required and not normalized:
        raise ValueError(f"{name} must not be empty")
    return tuple(sorted(set(normalized)))


class IdentityStatus(str, Enum):
    RESOLVED = "resolved"
    CLAIMED = "claimed"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class ModelSubject:
    subject_id: str
    vendor: str
    vendor_model_id: str
    concrete_revision: str | None
    identity_status: IdentityStatus
    first_seen_snapshot_id: str

    def __post_init__(self) -> None:
        vendor = _identifier("vendor", self.vendor)
        vendor_model_id = _text("vendor_model_id", self.vendor_model_id, maximum=512)
        concrete_revision = _optional_text(
            "concrete_revision",
            self.concrete_revision,
        )
        if not isinstance(self.identity_status, IdentityStatus):
            raise ValueError("identity_status must be an IdentityStatus")
        first_seen_snapshot_id = _digest(
            "first_seen_snapshot_id",
            self.first_seen_snapshot_id,
        )
        subject_id = _digest("subject_id", self.subject_id)

        object.__setattr__(self, "vendor", vendor)
        object.__setattr__(self, "vendor_model_id", vendor_model_id)
        object.__setattr__(self, "concrete_revision", concrete_revision)
        object.__setattr__(self, "first_seen_snapshot_id", first_seen_snapshot_id)
        expected = sha256_id("model_subject_v1", self.canonical_identity())
        if subject_id != expected:
            raise ValueError("subject_id does not match canonical model identity")

    @classmethod
    def create(
        cls,
        vendor: str,
        vendor_model_id: str,
        concrete_revision: str | None,
        identity_status: IdentityStatus,
        first_seen_snapshot_id: str,
    ) -> "ModelSubject":
        canonical = {
            "vendor": _identifier("vendor", vendor),
            "vendor_model_id": _text(
                "vendor_model_id",
                vendor_model_id,
                maximum=512,
            ),
            "concrete_revision": _optional_text(
                "concrete_revision",
                concrete_revision,
            ),
        }
        return cls(
            subject_id=sha256_id("model_subject_v1", canonical),
            vendor=canonical["vendor"],
            vendor_model_id=canonical["vendor_model_id"],
            concrete_revision=canonical["concrete_revision"],
            identity_status=identity_status,
            first_seen_snapshot_id=first_seen_snapshot_id,
        )

    def canonical_identity(self) -> dict[str, str | None]:
        return {
            "vendor": self.vendor,
            "vendor_model_id": self.vendor_model_id,
            "concrete_revision": self.concrete_revision,
        }


@dataclass(frozen=True)
class ExecutionRouteIdentity:
    route_id: str
    model_subject_id: str
    provider_id: str
    endpoint_identity: str
    provider_model_id: str
    parameter_profile_digest: str
    prompt_compiler_version: str
    data_policy_snapshot_id: str

    def __post_init__(self) -> None:
        route_id = _digest("route_id", self.route_id)
        model_subject_id = _digest("model_subject_id", self.model_subject_id)
        provider_id = _identifier("provider_id", self.provider_id)
        endpoint_identity = _text("endpoint_identity", self.endpoint_identity)
        provider_model_id = _text(
            "provider_model_id",
            self.provider_model_id,
            maximum=512,
        )
        parameter_profile_digest = _digest(
            "parameter_profile_digest",
            self.parameter_profile_digest,
        )
        prompt_compiler_version = _identifier(
            "prompt_compiler_version",
            self.prompt_compiler_version,
        )
        data_policy_snapshot_id = _digest(
            "data_policy_snapshot_id",
            self.data_policy_snapshot_id,
        )

        object.__setattr__(self, "model_subject_id", model_subject_id)
        object.__setattr__(self, "provider_id", provider_id)
        object.__setattr__(self, "endpoint_identity", endpoint_identity)
        object.__setattr__(self, "provider_model_id", provider_model_id)
        object.__setattr__(
            self,
            "parameter_profile_digest",
            parameter_profile_digest,
        )
        object.__setattr__(
            self,
            "prompt_compiler_version",
            prompt_compiler_version,
        )
        object.__setattr__(
            self,
            "data_policy_snapshot_id",
            data_policy_snapshot_id,
        )
        expected = sha256_id("execution_route_v1", self.canonical_identity())
        if route_id != expected:
            raise ValueError("route_id does not match canonical execution route")

    @classmethod
    def create(
        cls,
        model_subject_id: str,
        provider_id: str,
        endpoint_identity: str,
        provider_model_id: str,
        parameter_profile_digest: str,
        prompt_compiler_version: str,
        data_policy_snapshot_id: str,
    ) -> "ExecutionRouteIdentity":
        canonical = {
            "model_subject_id": _digest("model_subject_id", model_subject_id),
            "provider_id": _identifier("provider_id", provider_id),
            "endpoint_identity": _text("endpoint_identity", endpoint_identity),
            "provider_model_id": _text(
                "provider_model_id",
                provider_model_id,
                maximum=512,
            ),
            "parameter_profile_digest": _digest(
                "parameter_profile_digest",
                parameter_profile_digest,
            ),
            "prompt_compiler_version": _identifier(
                "prompt_compiler_version",
                prompt_compiler_version,
            ),
            "data_policy_snapshot_id": _digest(
                "data_policy_snapshot_id",
                data_policy_snapshot_id,
            ),
        }
        return cls(
            route_id=sha256_id("execution_route_v1", canonical),
            **canonical,
        )

    def canonical_identity(self) -> dict[str, str]:
        return {
            "model_subject_id": self.model_subject_id,
            "provider_id": self.provider_id,
            "endpoint_identity": self.endpoint_identity,
            "provider_model_id": self.provider_model_id,
            "parameter_profile_digest": self.parameter_profile_digest,
            "prompt_compiler_version": self.prompt_compiler_version,
            "data_policy_snapshot_id": self.data_policy_snapshot_id,
        }


@dataclass(frozen=True)
class RoleDefinition:
    role_digest: str
    role_id: str
    authority: tuple[str, ...]
    context_classes: tuple[str, ...]
    required_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        role_digest = _digest("role_digest", self.role_digest)
        role_id = _identifier("role_id", self.role_id)
        authority = _canonical_identifiers(
            "authority",
            self.authority,
            required=True,
        )
        context_classes = _canonical_identifiers(
            "context_classes",
            self.context_classes,
            required=True,
        )
        required_capabilities = _canonical_identifiers(
            "required_capabilities",
            self.required_capabilities,
            required=False,
        )
        object.__setattr__(self, "role_id", role_id)
        object.__setattr__(self, "authority", authority)
        object.__setattr__(self, "context_classes", context_classes)
        object.__setattr__(
            self,
            "required_capabilities",
            required_capabilities,
        )
        expected = sha256_id("role_definition_v1", self.canonical_identity())
        if role_digest != expected:
            raise ValueError("role_digest does not match canonical role definition")

    @classmethod
    def create(
        cls,
        role_id: str,
        *,
        authority: Iterable[str],
        context_classes: Iterable[str],
        required_capabilities: Iterable[str] = (),
    ) -> "RoleDefinition":
        canonical = {
            "role_id": _identifier("role_id", role_id),
            "authority": list(
                _canonical_identifiers("authority", authority, required=True)
            ),
            "context_classes": list(
                _canonical_identifiers(
                    "context_classes",
                    context_classes,
                    required=True,
                )
            ),
            "required_capabilities": list(
                _canonical_identifiers(
                    "required_capabilities",
                    required_capabilities,
                    required=False,
                )
            ),
        }
        return cls(
            role_digest=sha256_id("role_definition_v1", canonical),
            role_id=canonical["role_id"],
            authority=tuple(canonical["authority"]),
            context_classes=tuple(canonical["context_classes"]),
            required_capabilities=tuple(canonical["required_capabilities"]),
        )

    def canonical_identity(self) -> dict[str, object]:
        return {
            "role_id": self.role_id,
            "authority": list(self.authority),
            "context_classes": list(self.context_classes),
            "required_capabilities": list(self.required_capabilities),
        }


@dataclass(frozen=True)
class QualificationKey:
    digest: str
    model_subject_id: str
    route_id: str
    role_digest: str
    context_class: str
    verifier_suite_digest: str
    probe_digest: str

    def __post_init__(self) -> None:
        digest = _digest("qualification digest", self.digest)
        model_subject_id = _digest("model_subject_id", self.model_subject_id)
        route_id = _digest("route_id", self.route_id)
        role_digest = _digest("role_digest", self.role_digest)
        context_class = _identifier("context_class", self.context_class)
        verifier_suite_digest = _digest(
            "verifier_suite_digest",
            self.verifier_suite_digest,
        )
        probe_digest = _digest("probe_digest", self.probe_digest)
        object.__setattr__(self, "model_subject_id", model_subject_id)
        object.__setattr__(self, "route_id", route_id)
        object.__setattr__(self, "role_digest", role_digest)
        object.__setattr__(self, "context_class", context_class)
        object.__setattr__(
            self,
            "verifier_suite_digest",
            verifier_suite_digest,
        )
        object.__setattr__(self, "probe_digest", probe_digest)
        expected = sha256_id("qualification_key_v1", self.canonical_identity())
        if digest != expected:
            raise ValueError("qualification digest does not match bound components")

    @classmethod
    def create(
        cls,
        model_subject: ModelSubject | str,
        route: ExecutionRouteIdentity | str,
        role: RoleDefinition | str,
        context_class: str,
        verifier_suite_digest: str,
        probe_digest: str,
        *,
        identity_status: IdentityStatus | None = None,
    ) -> "QualificationKey":
        if isinstance(model_subject, ModelSubject):
            model_subject_id = model_subject.subject_id
            status = model_subject.identity_status
        else:
            model_subject_id = _digest("model_subject_id", model_subject)
            status = identity_status
        if status not in {IdentityStatus.RESOLVED, IdentityStatus.CLAIMED}:
            raise ValueError("model identity must be resolved or claimed")

        if isinstance(route, ExecutionRouteIdentity):
            if route.model_subject_id != model_subject_id:
                raise ValueError("route does not bind the supplied model subject")
            route_id = route.route_id
        else:
            route_id = _digest("route_id", route)

        role_digest = role.role_digest if isinstance(role, RoleDefinition) else role
        canonical = {
            "model_subject_id": model_subject_id,
            "route_id": _digest("route_id", route_id),
            "role_digest": _digest("role_digest", role_digest),
            "context_class": _identifier("context_class", context_class),
            "verifier_suite_digest": _digest(
                "verifier_suite_digest",
                verifier_suite_digest,
            ),
            "probe_digest": _digest("probe_digest", probe_digest),
        }
        return cls(
            digest=sha256_id("qualification_key_v1", canonical),
            **canonical,
        )

    def canonical_identity(self) -> dict[str, str]:
        return {
            "model_subject_id": self.model_subject_id,
            "route_id": self.route_id,
            "role_digest": self.role_digest,
            "context_class": self.context_class,
            "verifier_suite_digest": self.verifier_suite_digest,
            "probe_digest": self.probe_digest,
        }
