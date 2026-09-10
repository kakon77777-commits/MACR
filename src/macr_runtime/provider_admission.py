from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .canonical import sha256_id


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_PROVIDER_CAPACITY = 8


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded identifier")
    return value


def _positive_int(name: str, value: object, *, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= maximum
    ):
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


class AdmissionLane(str, Enum):
    INTERACTIVE = "interactive"
    ROUTINE = "routine"
    BULK = "bulk"


@dataclass(frozen=True)
class ProjectAdmissionBinding:
    project_id: str
    revision: int
    binding_source: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "project_id",
            _identifier("project_id", self.project_id),
        )
        object.__setattr__(
            self,
            "revision",
            _positive_int("project binding revision", self.revision, maximum=1_000_000),
        )
        object.__setattr__(
            self,
            "binding_source",
            _identifier("binding_source", self.binding_source),
        )

    @property
    def binding_digest(self) -> str:
        return sha256_id("provider_admission_project_v1", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "revision": self.revision,
            "binding_source": self.binding_source,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ProjectAdmissionBinding":
        expected = {"project_id", "revision", "binding_source"}
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ValueError("project admission binding fields must be exact")
        return cls(**value)


@dataclass(frozen=True)
class ProviderAdmissionPolicy:
    provider_id: str
    revision: int
    capacity_unit: int
    effective_target: int
    candidate_target: int
    hard_max: int
    per_project_cap: int
    policy_source: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_id",
            _identifier("provider_id", self.provider_id),
        )
        object.__setattr__(
            self,
            "revision",
            _positive_int("policy revision", self.revision, maximum=1_000_000),
        )
        capacity_unit = _positive_int(
            "capacity_unit",
            self.capacity_unit,
            maximum=1,
        )
        effective = _positive_int(
            "effective_target",
            self.effective_target,
            maximum=_MAX_PROVIDER_CAPACITY,
        )
        candidate = _positive_int(
            "candidate_target",
            self.candidate_target,
            maximum=_MAX_PROVIDER_CAPACITY,
        )
        hard = _positive_int(
            "hard_max",
            self.hard_max,
            maximum=_MAX_PROVIDER_CAPACITY,
        )
        per_project = _positive_int(
            "per_project_cap",
            self.per_project_cap,
            maximum=_MAX_PROVIDER_CAPACITY,
        )
        if effective != 1:
            raise ValueError("effective target above one is not live measured")
        if candidate != 2:
            raise ValueError("candidate target must remain the bounded value two")
        if hard != _MAX_PROVIDER_CAPACITY:
            raise ValueError("hard_max must remain the bounded ceiling eight")
        if not effective <= candidate <= hard:
            raise ValueError("provider admission targets are inconsistent")
        if per_project > hard:
            raise ValueError("per-project cap exceeds provider hard maximum")
        if capacity_unit != 1:
            raise ValueError("weighted capacity units are not measured")
        object.__setattr__(
            self,
            "policy_source",
            _identifier("policy_source", self.policy_source),
        )

    @property
    def policy_digest(self) -> str:
        return sha256_id("provider_admission_policy_v1", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "revision": self.revision,
            "capacity_unit": self.capacity_unit,
            "effective_target": self.effective_target,
            "candidate_target": self.candidate_target,
            "hard_max": self.hard_max,
            "per_project_cap": self.per_project_cap,
            "policy_source": self.policy_source,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ProviderAdmissionPolicy":
        expected = {
            "provider_id",
            "revision",
            "capacity_unit",
            "effective_target",
            "candidate_target",
            "hard_max",
            "per_project_cap",
            "policy_source",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ValueError("provider admission policy fields must be exact")
        return cls(**value)


def glm_provider_admission_policy() -> ProviderAdmissionPolicy:
    return ProviderAdmissionPolicy(
        provider_id="glm_flash_worker",
        revision=1,
        capacity_unit=1,
        effective_target=1,
        candidate_target=2,
        hard_max=8,
        per_project_cap=2,
        policy_source="built_in",
    )


__all__ = [
    "AdmissionLane",
    "ProjectAdmissionBinding",
    "ProviderAdmissionPolicy",
    "glm_provider_admission_policy",
]
