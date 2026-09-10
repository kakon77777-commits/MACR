from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from .authority import DispatchAuthorityStore
from .canonical import canonical_json_bytes, sha256_id
from .errors import (
    DispatchAuthorizationError,
    ProviderAdmissionBusyError,
    ProviderAdmissionConflict,
    ProviderAdmissionReconciliationError,
    ProviderAdmissionRequiredError,
)
from .execution import AuthorizationReference
from .runtime_db import RuntimeDatabase


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_PROVIDER_CAPACITY = 8
_ZERO_DIGEST = "0" * 64


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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


def _uuid4(name: str, value: object) -> str:
    try:
        parsed = uuid.UUID(value)  # type: ignore[arg-type]
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a UUIDv4 string") from exc
    if parsed.version != 4 or str(parsed) != value:
        raise ValueError(f"{name} must be a UUIDv4 string")
    return str(parsed)


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _optional_digest(name: str, value: object) -> str | None:
    if value is None:
        return None
    return _digest(name, value)


def _optional_identifier(name: str, value: object) -> str | None:
    if value is None:
        return None
    return _identifier(name, value)


def _aware(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ProviderAdmissionConflict(
            "provider admission timestamp is invalid"
        ) from exc
    if parsed.tzinfo is None:
        raise ProviderAdmissionConflict(
            "provider admission timestamp is invalid"
        )
    return parsed.astimezone(timezone.utc)


def _validated_control_state(
    connection: sqlite3.Connection,
    policy: "ProviderAdmissionPolicy",
    *,
    deployment_mode: str | None = None,
    deployment_digest: str | None = None,
) -> sqlite3.Row:
    """Verify the active projection against its immutable latest receipt."""

    state = connection.execute(
        "SELECT * FROM provider_admission_state WHERE provider_id=?",
        (policy.provider_id,),
    ).fetchone()
    if (
        state is None
        or state["policy_digest"] != policy.policy_digest
        or state["deployment_mode"]
        not in {"canonical_runtime", "offline_test"}
        or not _SHA256.fullmatch(state["deployment_digest"] or "")
        or (
            deployment_mode is not None
            and state["deployment_mode"] != deployment_mode
        )
        or (
            deployment_digest is not None
            and state["deployment_digest"] != deployment_digest
        )
        or not 1 <= state["effective_target"] <= policy.candidate_target
        or state["control_revision"] < 1
        or not _SHA256.fullmatch(state["control_digest"] or "")
        or (
            state["circuit_state"] == "half_open"
            and not _SHA256.fullmatch(
                state["half_open_probe_request_digest"] or ""
            )
        )
        or (
            state["circuit_state"] != "half_open"
            and state["half_open_probe_request_digest"] is not None
        )
    ):
        raise ProviderAdmissionConflict(
            "provider admission control state is invalid"
        )
    transition = connection.execute(
        """SELECT * FROM provider_admission_transitions
        WHERE provider_id=? AND control_revision=?""",
        (policy.provider_id, state["control_revision"]),
    ).fetchone()
    bounds = connection.execute(
        """SELECT COUNT(*) AS count, MIN(control_revision) AS minimum,
                  MAX(control_revision) AS maximum
        FROM provider_admission_transitions WHERE provider_id=?""",
        (policy.provider_id,),
    ).fetchone()
    if (
        transition is None
        or bounds["count"] != state["control_revision"]
        or bounds["minimum"] != 1
        or bounds["maximum"] != state["control_revision"]
    ):
        raise ProviderAdmissionConflict(
            "provider admission control receipt sequence is invalid"
        )
    body_sha256 = hashlib.sha256(
        transition["body_json"].encode("utf-8")
    ).hexdigest()
    try:
        body = json.loads(transition["body_json"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise ProviderAdmissionConflict(
            "provider admission control receipt is invalid"
        ) from exc
    expected = {
        "schema": "provider_admission_control_transition_v1",
        "provider_id": policy.provider_id,
        "policy_digest": policy.policy_digest,
        "deployment_mode": state["deployment_mode"],
        "deployment_digest": state["deployment_digest"],
        "control_revision": state["control_revision"],
        "prior_control_digest": transition["prior_control_digest"],
        "transition_kind": transition["transition_kind"],
        "effective_target": state["effective_target"],
        "circuit_state": state["circuit_state"],
        "half_open_probe_request_digest": (
            state["half_open_probe_request_digest"]
        ),
        "last_signal": state["last_signal"],
        "authority_digest": transition["authority_digest"],
        "binding_digest": transition["binding_digest"],
        "request_id": transition["request_id"],
        "evidence_digest": transition["evidence_digest"],
        "created_at": transition["created_at"],
    }
    previous = None
    if state["control_revision"] > 1:
        previous = connection.execute(
            """SELECT body_sha256 FROM provider_admission_transitions
            WHERE provider_id=? AND control_revision=?""",
            (policy.provider_id, state["control_revision"] - 1),
        ).fetchone()
    expected_prior = (
        _ZERO_DIGEST if previous is None else previous["body_sha256"]
    )
    if (
        body != expected
        or body_sha256 != transition["body_sha256"]
        or body_sha256 != state["control_digest"]
        or transition["prior_control_digest"] != expected_prior
    ):
        raise ProviderAdmissionConflict(
            "provider admission control projection does not match receipt"
        )
    return state


class AdmissionLane(str, Enum):
    INTERACTIVE = "interactive"
    ROUTINE = "routine"
    BULK = "bulk"


class AdmissionDeploymentMode(str, Enum):
    CANONICAL_RUNTIME = "canonical_runtime"
    OFFLINE_TEST = "offline_test"


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


@dataclass(frozen=True)
class ProviderAdmissionTargetBinding:
    provider_id: str
    policy_digest: str
    target: int
    policy_revision: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_id",
            _identifier("provider_id", self.provider_id),
        )
        object.__setattr__(
            self,
            "policy_digest",
            _digest("policy_digest", self.policy_digest),
        )
        if self.target not in {1, 2}:
            raise ValueError("provider admission target is not measured")
        object.__setattr__(
            self,
            "policy_revision",
            _positive_int(
                "policy_revision",
                self.policy_revision,
                maximum=1_000_000,
            ),
        )

    @classmethod
    def create(
        cls,
        policy: ProviderAdmissionPolicy,
        *,
        target: int,
    ) -> "ProviderAdmissionTargetBinding":
        if not isinstance(policy, ProviderAdmissionPolicy):
            raise ValueError("policy must be a ProviderAdmissionPolicy")
        if target not in {policy.effective_target, policy.candidate_target}:
            raise ValueError("provider admission target is not measured")
        return cls(
            provider_id=policy.provider_id,
            policy_digest=policy.policy_digest,
            target=target,
            policy_revision=policy.revision,
        )

    @property
    def binding_digest(self) -> str:
        return sha256_id("provider_admission_target_v1", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "policy_digest": self.policy_digest,
            "target": self.target,
            "policy_revision": self.policy_revision,
        }


@dataclass(frozen=True)
class ProviderAdmissionCircuitBinding:
    provider_id: str
    policy_digest: str
    from_state: str
    to_state: str
    policy_revision: int
    probe_request_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_id",
            _identifier("provider_id", self.provider_id),
        )
        object.__setattr__(
            self,
            "policy_digest",
            _digest("policy_digest", self.policy_digest),
        )
        if (self.from_state, self.to_state) != ("open", "half_open"):
            raise ValueError(
                "provider admission circuit transition is unsupported"
            )
        object.__setattr__(
            self,
            "policy_revision",
            _positive_int(
                "policy_revision",
                self.policy_revision,
                maximum=1_000_000,
            ),
        )
        object.__setattr__(
            self,
            "probe_request_digest",
            _digest(
                "probe_request_digest",
                self.probe_request_digest,
            ),
        )

    @classmethod
    def create(
        cls,
        policy: ProviderAdmissionPolicy,
        *,
        from_state: str,
        to_state: str,
        probe_request_digest: str,
    ) -> "ProviderAdmissionCircuitBinding":
        if not isinstance(policy, ProviderAdmissionPolicy):
            raise ValueError("policy must be a ProviderAdmissionPolicy")
        return cls(
            provider_id=policy.provider_id,
            policy_digest=policy.policy_digest,
            from_state=from_state,
            to_state=to_state,
            policy_revision=policy.revision,
            probe_request_digest=probe_request_digest,
        )

    @property
    def binding_digest(self) -> str:
        return sha256_id("provider_admission_circuit_v1", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "policy_digest": self.policy_digest,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "policy_revision": self.policy_revision,
            "probe_request_digest": self.probe_request_digest,
        }


@dataclass(frozen=True)
class ProviderAdmissionRequest:
    request_id: str
    provider_id: str
    project_binding_digest: str
    lane: AdmissionLane
    run_id: str
    authorization: AuthorizationReference
    plane: str
    task_type: str
    task_digest: str
    member_digest: str | None
    batch_id: str | None
    provider_tier_binding_digest: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _uuid4("request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "provider_id",
            _identifier("provider_id", self.provider_id),
        )
        object.__setattr__(
            self,
            "project_binding_digest",
            _digest(
                "project_binding_digest",
                self.project_binding_digest,
            ),
        )
        if not isinstance(self.lane, AdmissionLane):
            raise ValueError("lane must be an AdmissionLane")
        object.__setattr__(self, "run_id", _uuid4("run_id", self.run_id))
        if not isinstance(self.authorization, AuthorizationReference):
            raise ValueError("authorization must be an AuthorizationReference")
        object.__setattr__(self, "plane", _identifier("plane", self.plane))
        object.__setattr__(
            self,
            "task_type",
            _identifier("task_type", self.task_type),
        )
        object.__setattr__(
            self,
            "task_digest",
            _digest("task_digest", self.task_digest),
        )
        object.__setattr__(
            self,
            "member_digest",
            _optional_digest("member_digest", self.member_digest),
        )
        object.__setattr__(
            self,
            "batch_id",
            _optional_identifier("batch_id", self.batch_id),
        )
        object.__setattr__(
            self,
            "provider_tier_binding_digest",
            _optional_digest(
                "provider_tier_binding_digest",
                self.provider_tier_binding_digest,
            ),
        )

    @property
    def binding_digest(self) -> str:
        return sha256_id("provider_admission_request_v1", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "provider_id": self.provider_id,
            "project_binding_digest": self.project_binding_digest,
            "lane": self.lane.value,
            "run_id": self.run_id,
            "authorization_digest": self.authorization.digest,
            "authorization_epoch": self.authorization.epoch,
            "plane": self.plane,
            "task_type": self.task_type,
            "task_digest": self.task_digest,
            "member_digest": self.member_digest,
            "batch_id": self.batch_id,
            "provider_tier_binding_digest": (
                self.provider_tier_binding_digest
            ),
        }


@dataclass(frozen=True)
class ProviderAdmissionPermit:
    request_id: str
    provider_id: str
    project_binding_digest: str
    admission_lane: str
    run_id: str
    authority_digest: str
    authority_epoch: int
    task_digest: str
    member_digest: str | None
    provider_tier_binding_digest: str | None
    policy_digest: str
    capacity_unit: int
    fencing_token: int
    acquired_at: str
    expires_at: str

    def __post_init__(self) -> None:
        _uuid4("permit request_id", self.request_id)
        _identifier("permit provider_id", self.provider_id)
        _digest("permit project_binding_digest", self.project_binding_digest)
        if self.admission_lane not in {item.value for item in AdmissionLane}:
            raise ValueError("permit admission_lane is invalid")
        _uuid4("permit run_id", self.run_id)
        _digest("permit authority_digest", self.authority_digest)
        if (
            isinstance(self.authority_epoch, bool)
            or not isinstance(self.authority_epoch, int)
            or self.authority_epoch < 0
        ):
            raise ValueError("permit authority_epoch must be non-negative")
        _digest("permit task_digest", self.task_digest)
        _optional_digest("permit member_digest", self.member_digest)
        _optional_digest(
            "permit provider_tier_binding_digest",
            self.provider_tier_binding_digest,
        )
        _digest("permit policy_digest", self.policy_digest)
        if self.capacity_unit != 1:
            raise ValueError("permit capacity_unit must be one")
        _positive_int(
            "permit fencing_token",
            self.fencing_token,
            maximum=2**63 - 1,
        )
        _aware(self.acquired_at)
        _aware(self.expires_at)


@dataclass(frozen=True)
class ProviderAdmissionRecord:
    request_id: str
    provider_id: str
    project_binding_digest: str
    admission_lane: str
    run_id: str
    state: str
    fencing_token: int | None
    requested_at: str
    granted_at: str | None
    transport_started_at: str | None
    terminal_at: str | None
    expires_at: str
    terminal_evidence_digest: str | None
    resolution_evidence_digest: str | None
    resolved_at: str | None


@dataclass(frozen=True)
class ProviderAdmissionStatus:
    initialized: bool
    provider_id: str
    policy_digest: str
    deployment_mode: str | None
    deployment_digest: str | None
    effective_target: int
    candidate_target: int
    hard_max: int
    per_project_cap: int
    circuit_state: str
    last_signal: str | None
    counts: Mapping[str, int]
    lane_counts: Mapping[str, int]
    project_active_counts: tuple[Mapping[str, object], ...]
    legacy_pre_provider_admission_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "initialized": self.initialized,
            "provider_id": self.provider_id,
            "policy_digest": self.policy_digest,
            "deployment_mode": self.deployment_mode,
            "deployment_digest": self.deployment_digest,
            "effective_target": self.effective_target,
            "candidate_target": self.candidate_target,
            "hard_max": self.hard_max,
            "per_project_cap": self.per_project_cap,
            "circuit_state": self.circuit_state,
            "last_signal": self.last_signal,
            "counts": dict(self.counts),
            "lane_counts": dict(self.lane_counts),
            "project_active_counts": [
                dict(item) for item in self.project_active_counts
            ],
            "legacy_pre_provider_admission_count": (
                self.legacy_pre_provider_admission_count
            ),
        }


class ProviderAdmissionKernel:
    def __init__(
        self,
        path: str | Path,
        *,
        policy: ProviderAdmissionPolicy | None = None,
        now: Callable[[], datetime] = _utc_now,
        deployment_mode: AdmissionDeploymentMode = (
            AdmissionDeploymentMode.OFFLINE_TEST
        ),
    ) -> None:
        if not isinstance(deployment_mode, AdmissionDeploymentMode):
            raise ValueError(
                "deployment_mode must be an AdmissionDeploymentMode"
            )
        self.database = RuntimeDatabase(path)
        self.authorities = DispatchAuthorityStore(path, now=now)
        self.policy = policy or glm_provider_admission_policy()
        self._now = now
        self._deployment_mode = deployment_mode
        self._install_policy()

    @classmethod
    def canonical_runtime(
        cls,
        path: str | Path,
        *,
        policy: ProviderAdmissionPolicy | None = None,
        now: Callable[[], datetime] = _utc_now,
    ) -> "ProviderAdmissionKernel":
        return cls(
            path,
            policy=policy,
            now=now,
            deployment_mode=AdmissionDeploymentMode.CANONICAL_RUNTIME,
        )

    @property
    def path(self) -> Path:
        return self.database.path

    @property
    def deployment_mode(self) -> AdmissionDeploymentMode:
        return self._deployment_mode

    @property
    def deployment_digest(self) -> str:
        normalized = str(self.path.resolve(strict=False)).replace(
            "\\",
            "/",
        ).casefold()
        return sha256_id(
            "provider_admission_deployment_v1",
            {
                "deployment_mode": self.deployment_mode.value,
                "runtime_path_sha256": hashlib.sha256(
                    normalized.encode("utf-8")
                ).hexdigest(),
                "provider_id": self.policy.provider_id,
                "policy_digest": self.policy.policy_digest,
            },
        )

    def require_transport_binding(
        self,
        expected_runtime_path: str | Path,
        *,
        offline_test: bool,
    ) -> None:
        if not isinstance(offline_test, bool):
            raise ValueError("offline_test must be boolean")
        expected = Path(expected_runtime_path).resolve(strict=False)
        actual = self.path.resolve(strict=False)
        if offline_test:
            if self.deployment_mode is not AdmissionDeploymentMode.OFFLINE_TEST:
                raise ProviderAdmissionRequiredError(
                    "offline provider transport requires an offline-test kernel"
                )
            return
        if (
            self.deployment_mode is not AdmissionDeploymentMode.CANONICAL_RUNTIME
            or actual != expected
        ):
            raise ProviderAdmissionRequiredError(
                "provider transport is not bound to the canonical runtime"
            )

    def _current_time(self) -> datetime:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("provider admission clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def _validated_state(
        self,
        connection: sqlite3.Connection,
    ) -> sqlite3.Row:
        return _validated_control_state(
            connection,
            self.policy,
            deployment_mode=self.deployment_mode.value,
            deployment_digest=self.deployment_digest,
        )

    @staticmethod
    def _consume_activation_authority(
        connection: sqlite3.Connection,
        reference: AuthorizationReference,
        now: str,
    ) -> None:
        changed = connection.execute(
            """UPDATE dispatch_authorities SET revoked_at=?
            WHERE source_kind=? AND source_id=? AND revision=? AND epoch=?
              AND body_sha256=? AND revoked_at IS NULL""",
            (
                now,
                reference.source_kind,
                reference.source_id,
                reference.revision,
                reference.epoch,
                reference.digest,
            ),
        ).rowcount
        if changed != 1:
            raise ProviderAdmissionConflict(
                "provider admission activation authority was already consumed"
            )

    def _append_control_transition(
        self,
        connection: sqlite3.Connection,
        state: sqlite3.Row | None,
        *,
        transition_kind: str,
        effective_target: int,
        circuit_state: str,
        half_open_probe_request_digest: str | None,
        last_signal: str,
        now: str,
        authority_digest: str | None = None,
        binding_digest: str | None = None,
        request_id: str | None = None,
        evidence_digest: str | None = None,
    ) -> sqlite3.Row:
        kind = _identifier("transition_kind", transition_kind)
        signal = _identifier("last_signal", last_signal)
        if effective_target not in {
            self.policy.effective_target,
            self.policy.candidate_target,
        }:
            raise ProviderAdmissionConflict(
                "provider admission transition target is invalid"
            )
        if circuit_state not in {"closed", "open", "half_open"}:
            raise ProviderAdmissionConflict(
                "provider admission transition circuit is invalid"
            )
        probe_digest = _optional_digest(
            "half_open_probe_request_digest",
            half_open_probe_request_digest,
        )
        if (circuit_state == "half_open") != (probe_digest is not None):
            raise ProviderAdmissionConflict(
                "half-open control state requires one exact probe"
            )
        authority = _optional_digest("authority_digest", authority_digest)
        binding = _optional_digest("binding_digest", binding_digest)
        evidence = _optional_digest("evidence_digest", evidence_digest)
        normalized_request = (
            _uuid4("request_id", request_id)
            if request_id is not None
            else None
        )
        revision = 1 if state is None else state["control_revision"] + 1
        prior_digest = _ZERO_DIGEST if state is None else state["control_digest"]
        document = {
            "schema": "provider_admission_control_transition_v1",
            "provider_id": self.policy.provider_id,
            "policy_digest": self.policy.policy_digest,
            "deployment_mode": self.deployment_mode.value,
            "deployment_digest": self.deployment_digest,
            "control_revision": revision,
            "prior_control_digest": prior_digest,
            "transition_kind": kind,
            "effective_target": effective_target,
            "circuit_state": circuit_state,
            "half_open_probe_request_digest": probe_digest,
            "last_signal": signal,
            "authority_digest": authority,
            "binding_digest": binding,
            "request_id": normalized_request,
            "evidence_digest": evidence,
            "created_at": now,
        }
        body_json = canonical_json_bytes(document).decode("utf-8")
        body_sha256 = hashlib.sha256(body_json.encode("utf-8")).hexdigest()
        connection.execute(
            """INSERT INTO provider_admission_transitions(
                transition_id, provider_id, control_revision,
                prior_control_digest, transition_kind, authority_digest,
                binding_digest, request_id, evidence_digest, body_json,
                body_sha256, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                self.policy.provider_id,
                revision,
                prior_digest,
                kind,
                authority,
                binding,
                normalized_request,
                evidence,
                body_json,
                body_sha256,
                now,
            ),
        )
        if state is None:
            connection.execute(
                """INSERT INTO provider_admission_state(
                    provider_id, policy_digest, deployment_mode,
                    deployment_digest, effective_target,
                    circuit_state, grant_sequence, last_granted_lane,
                    half_open_probe_request_digest, control_revision,
                    control_digest, last_signal, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?, ?, ?, ?, ?)""",
                (
                    self.policy.provider_id,
                    self.policy.policy_digest,
                    self.deployment_mode.value,
                    self.deployment_digest,
                    effective_target,
                    circuit_state,
                    probe_digest,
                    revision,
                    body_sha256,
                    signal,
                    now,
                ),
            )
        else:
            changed = connection.execute(
                """UPDATE provider_admission_state
                SET effective_target=?, circuit_state=?,
                    half_open_probe_request_digest=?, control_revision=?,
                    control_digest=?, last_signal=?, updated_at=?
                WHERE provider_id=? AND control_revision=?
                  AND control_digest=?""",
                (
                    effective_target,
                    circuit_state,
                    probe_digest,
                    revision,
                    body_sha256,
                    signal,
                    now,
                    self.policy.provider_id,
                    state["control_revision"],
                    state["control_digest"],
                ),
            ).rowcount
            if changed != 1:
                raise ProviderAdmissionConflict(
                    "provider admission control projection changed concurrently"
                )
        return _validated_control_state(
            connection,
            self.policy,
            deployment_mode=self.deployment_mode.value,
            deployment_digest=self.deployment_digest,
        )

    def _install_policy(self) -> None:
        body = canonical_json_bytes(self.policy.to_dict()).decode("utf-8")
        body_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
        now = self._current_time().isoformat()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            state = connection.execute(
                "SELECT * FROM provider_admission_state WHERE provider_id = ?",
                (self.policy.provider_id,),
            ).fetchone()
            if state is None:
                nonterminal_runs = connection.execute(
                    """SELECT COUNT(*) FROM runs
                    WHERE terminal_event_id IS NULL OR terminal_at IS NULL
                       OR state='dispatched'"""
                ).fetchone()[0]
                active_dispatch_leases = connection.execute(
                    "SELECT COUNT(*) FROM dispatch_leases"
                ).fetchone()[0]
                if nonterminal_runs or active_dispatch_leases:
                    raise ProviderAdmissionConflict(
                        "provider admission bootstrap requires a quiescent legacy runtime"
                    )
            row = connection.execute(
                """SELECT body_json, body_sha256, policy_digest
                FROM provider_admission_policies
                WHERE provider_id = ? AND revision = ?""",
                (self.policy.provider_id, self.policy.revision),
            ).fetchone()
            if row is None:
                connection.execute(
                    """INSERT INTO provider_admission_policies(
                        provider_id, revision, body_json, body_sha256,
                        policy_digest, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        self.policy.provider_id,
                        self.policy.revision,
                        body,
                        body_sha256,
                        self.policy.policy_digest,
                        now,
                    ),
                )
            elif (
                row["body_json"] != body
                or row["body_sha256"] != body_sha256
                or row["policy_digest"] != self.policy.policy_digest
            ):
                raise ProviderAdmissionConflict(
                    "provider admission policy revision conflicts"
                )
            if state is None:
                self._append_control_transition(
                    connection,
                    None,
                    transition_kind="genesis",
                    effective_target=self.policy.effective_target,
                    circuit_state="closed",
                    half_open_probe_request_digest=None,
                    last_signal="policy_installed",
                    now=now,
                )
            else:
                self._validated_state(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def activate_target(
        self,
        target: ProviderAdmissionTargetBinding,
        reference: AuthorizationReference,
    ) -> ProviderAdmissionStatus:
        if not isinstance(target, ProviderAdmissionTargetBinding):
            raise ValueError(
                "target must be a ProviderAdmissionTargetBinding"
            )
        if (
            target.provider_id != self.policy.provider_id
            or target.policy_digest != self.policy.policy_digest
            or target.policy_revision != self.policy.revision
            or target.target
            not in {
                self.policy.effective_target,
                self.policy.candidate_target,
            }
        ):
            raise ProviderAdmissionConflict(
                "provider admission target binding is stale"
            )
        self.authorities.verify(
            reference,
            provider_id=self.policy.provider_id,
            plane="provider_capacity_activation",
            task_type="provider_capacity_target",
            provider_admission_target_digest=target.binding_digest,
        )
        now = self._current_time().isoformat()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            state = self._validated_state(connection)
            if state["circuit_state"] != "closed":
                raise ProviderAdmissionConflict(
                    "provider admission target cannot change in current state"
                )
            if state["effective_target"] == target.target:
                raise ProviderAdmissionConflict(
                    "provider admission target is already active"
                )
            active_or_waiting = connection.execute(
                """SELECT COUNT(*) FROM provider_admission_requests
                WHERE provider_id=? AND state IN (
                    'waiting','granted','dispatched','reconciliation_required'
                )""",
                (self.policy.provider_id,),
            ).fetchone()[0]
            if active_or_waiting:
                raise ProviderAdmissionConflict(
                    "provider admission target requires an idle provider"
                )
            self._consume_activation_authority(connection, reference, now)
            self._append_control_transition(
                connection,
                state,
                transition_kind="target_activated",
                effective_target=target.target,
                circuit_state="closed",
                half_open_probe_request_digest=None,
                last_signal="target_activated",
                now=now,
                authority_digest=reference.digest,
                binding_digest=target.binding_digest,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.status(self.policy.provider_id)

    def activate_half_open(
        self,
        binding: ProviderAdmissionCircuitBinding,
        reference: AuthorizationReference,
        probe_request: ProviderAdmissionRequest,
    ) -> ProviderAdmissionStatus:
        if not isinstance(binding, ProviderAdmissionCircuitBinding):
            raise ValueError(
                "binding must be a ProviderAdmissionCircuitBinding"
            )
        if (
            binding.provider_id != self.policy.provider_id
            or binding.policy_digest != self.policy.policy_digest
            or binding.policy_revision != self.policy.revision
        ):
            raise ProviderAdmissionConflict(
                "provider admission circuit binding is stale"
            )
        if (
            not isinstance(probe_request, ProviderAdmissionRequest)
            or probe_request.provider_id != self.policy.provider_id
            or probe_request.lane is not AdmissionLane.INTERACTIVE
            or probe_request.binding_digest != binding.probe_request_digest
        ):
            raise ProviderAdmissionConflict(
                "half-open binding does not name one exact interactive request"
            )
        self._verify_authority(probe_request)
        self.authorities.verify(
            reference,
            provider_id=self.policy.provider_id,
            plane="provider_circuit_activation",
            task_type="provider_circuit_half_open",
            provider_admission_circuit_digest=binding.binding_digest,
        )
        now = self._current_time().isoformat()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            state = self._validated_state(connection)
            self._verify_authority_locked(connection, probe_request)
            unresolved = connection.execute(
                """SELECT COUNT(*) FROM provider_admission_requests
                WHERE provider_id=? AND state='reconciliation_required'""",
                (self.policy.provider_id,),
            ).fetchone()[0]
            active_or_waiting = connection.execute(
                """SELECT COUNT(*) FROM provider_admission_requests
                WHERE provider_id=? AND state IN (
                    'waiting','granted','dispatched'
                )""",
                (self.policy.provider_id,),
            ).fetchone()[0]
            existing_probe = connection.execute(
                """SELECT COUNT(*) FROM provider_admission_requests
                WHERE request_id=? OR run_id=?""",
                (probe_request.request_id, probe_request.run_id),
            ).fetchone()[0]
            if (
                state["circuit_state"] != binding.from_state
                or unresolved
                or active_or_waiting
                or existing_probe
            ):
                raise ProviderAdmissionConflict(
                    "provider admission circuit cannot enter half-open"
                )
            self._consume_activation_authority(connection, reference, now)
            self._append_control_transition(
                connection,
                state,
                transition_kind="half_open_activated",
                effective_target=state["effective_target"],
                circuit_state="half_open",
                half_open_probe_request_digest=(
                    binding.probe_request_digest
                ),
                last_signal="half_open_authorized",
                now=now,
                authority_digest=reference.digest,
                binding_digest=binding.binding_digest,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.status(self.policy.provider_id)

    def _verify_authority(self, request: ProviderAdmissionRequest) -> None:
        self.authorities.verify(
            request.authorization,
            provider_id=request.provider_id,
            plane=request.plane,
            task_type=request.task_type,
            batch_id=request.batch_id,
            member_digest=request.member_digest,
            provider_tier_binding_digest=request.provider_tier_binding_digest,
            project_binding_digest=request.project_binding_digest,
            admission_lane=request.lane.value,
            provider_admission_policy_digest=self.policy.policy_digest,
        )

    def _verify_authority_locked(
        self,
        connection: sqlite3.Connection,
        request: ProviderAdmissionRequest,
    ) -> None:
        self.authorities.verify_in_transaction(
            connection,
            request.authorization,
            provider_id=request.provider_id,
            plane=request.plane,
            task_type=request.task_type,
            batch_id=request.batch_id,
            member_digest=request.member_digest,
            provider_tier_binding_digest=(
                request.provider_tier_binding_digest
            ),
            project_binding_digest=request.project_binding_digest,
            admission_lane=request.lane.value,
            provider_admission_policy_digest=self.policy.policy_digest,
        )

    @staticmethod
    def _row_matches_request(
        row: sqlite3.Row,
        request: ProviderAdmissionRequest,
        policy_digest: str,
    ) -> bool:
        return (
            row["provider_id"] == request.provider_id
            and row["project_binding_digest"]
            == request.project_binding_digest
            and row["admission_lane"] == request.lane.value
            and row["run_id"] == request.run_id
            and row["authority_digest"] == request.authorization.digest
            and row["authority_epoch"] == request.authorization.epoch
            and row["task_digest"] == request.task_digest
            and row["member_digest"] == request.member_digest
            and row["provider_tier_binding_digest"]
            == request.provider_tier_binding_digest
            and row["policy_digest"] == policy_digest
            and row["capacity_unit"] == 1
        )

    @staticmethod
    def _permit_from_row(row: sqlite3.Row) -> ProviderAdmissionPermit:
        return ProviderAdmissionPermit(
            request_id=row["request_id"],
            provider_id=row["provider_id"],
            project_binding_digest=row["project_binding_digest"],
            admission_lane=row["admission_lane"],
            run_id=row["run_id"],
            authority_digest=row["authority_digest"],
            authority_epoch=row["authority_epoch"],
            task_digest=row["task_digest"],
            member_digest=row["member_digest"],
            provider_tier_binding_digest=row[
                "provider_tier_binding_digest"
            ],
            policy_digest=row["policy_digest"],
            capacity_unit=row["capacity_unit"],
            fencing_token=row["fencing_token"],
            acquired_at=row["granted_at"],
            expires_at=row["expires_at"],
        )

    @staticmethod
    def _decrement_project(
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        now: str,
    ) -> None:
        changed = connection.execute(
            """UPDATE provider_admission_projects
            SET active_units = active_units - 1, updated_at = ?
            WHERE provider_id = ? AND project_binding_digest = ?
              AND active_units >= 1""",
            (now, row["provider_id"], row["project_binding_digest"]),
        ).rowcount
        if changed != 1:
            raise ProviderAdmissionConflict(
                "provider admission project capacity is inconsistent"
            )

    def _cancel_granted_row(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        state: sqlite3.Row,
        *,
        now: str,
        reason: str,
    ) -> None:
        if row["state"] != "granted":
            raise ProviderAdmissionConflict(
                "provider admission request is not an unused grant"
            )
        self._decrement_project(connection, row, now)
        changed = connection.execute(
            """UPDATE provider_admission_requests
            SET state='cancelled', terminal_at=?
            WHERE request_id=? AND state='granted'""",
            (now, row["request_id"]),
        ).rowcount
        if changed != 1:
            raise ProviderAdmissionConflict(
                "provider admission grant cancellation lost ownership"
            )
        if state["circuit_state"] == "half_open":
            self._append_control_transition(
                connection,
                state,
                transition_kind="half_open_cancelled",
                effective_target=state["effective_target"],
                circuit_state="open",
                half_open_probe_request_digest=None,
                last_signal=reason,
                now=now,
                request_id=row["request_id"],
            )

    def _expire(
        self,
        connection: sqlite3.Connection,
        now: datetime,
    ) -> None:
        state = self._validated_state(connection)
        expired_active_request_id: str | None = None
        rows = connection.execute(
            """SELECT * FROM provider_admission_requests
            WHERE provider_id = ?
              AND state IN ('waiting', 'granted', 'dispatched')""",
            (self.policy.provider_id,),
        ).fetchall()
        for row in rows:
            if _aware(row["expires_at"]) > now:
                continue
            if row["state"] == "waiting":
                connection.execute(
                    """UPDATE provider_admission_requests
                    SET state='cancelled', terminal_at=?
                    WHERE request_id=? AND state='waiting'""",
                    (now.isoformat(), row["request_id"]),
                )
                continue
            connection.execute(
                """UPDATE provider_admission_requests
                SET state='reconciliation_required', terminal_at=?
                WHERE request_id=?
                  AND state IN ('granted', 'dispatched')""",
                (now.isoformat(), row["request_id"]),
            )
            if expired_active_request_id is None:
                expired_active_request_id = row["request_id"]
        if expired_active_request_id is not None:
            self._append_control_transition(
                connection,
                state,
                transition_kind="permit_expired",
                effective_target=state["effective_target"],
                circuit_state="open",
                half_open_probe_request_digest=None,
                last_signal="permit_expired",
                now=now.isoformat(),
                request_id=expired_active_request_id,
            )

    def _selected_waiting(
        self,
        connection: sqlite3.Connection,
    ) -> sqlite3.Row | None:
        state = connection.execute(
            "SELECT * FROM provider_admission_state WHERE provider_id=?",
            (self.policy.provider_id,),
        ).fetchone()
        rows = connection.execute(
            """SELECT r.*,
                      COALESCE((
                          SELECT SUM(a.capacity_unit)
                          FROM provider_admission_requests a
                          WHERE a.provider_id=r.provider_id
                            AND a.project_binding_digest=r.project_binding_digest
                            AND a.state IN (
                                'granted','dispatched','reconciliation_required'
                            )
                      ), 0) AS project_active,
                      COALESCE(p.last_grant_sequence, 0)
                          AS project_last_grant
            FROM provider_admission_requests r
            LEFT JOIN provider_admission_projects p
              ON p.provider_id=r.provider_id
             AND p.project_binding_digest=r.project_binding_digest
            WHERE r.provider_id=? AND r.state='waiting'
            ORDER BY r.requested_at, r.request_id""",
            (self.policy.provider_id,),
        ).fetchall()
        eligible = [
            row
            for row in rows
            if row["project_active"] + row["capacity_unit"]
            <= self.policy.per_project_cap
        ]
        if not eligible:
            return None
        interactive = [
            row
            for row in eligible
            if row["admission_lane"] == AdmissionLane.INTERACTIVE.value
        ]
        non_interactive = [
            row
            for row in eligible
            if row["admission_lane"] != AdmissionLane.INTERACTIVE.value
        ]
        if interactive and state["last_granted_lane"] != "interactive":
            lane_rows = interactive
        elif non_interactive:
            lane_rows = non_interactive
        else:
            lane_rows = interactive
        return min(
            lane_rows,
            key=lambda row: (
                row["project_last_grant"],
                row["requested_at"],
                row["request_id"],
            ),
        )

    def try_admit(
        self,
        request: ProviderAdmissionRequest,
        *,
        ttl_seconds: int,
    ) -> ProviderAdmissionPermit:
        if not isinstance(request, ProviderAdmissionRequest):
            raise ValueError("request must be a ProviderAdmissionRequest")
        if request.provider_id != self.policy.provider_id:
            raise ProviderAdmissionConflict(
                "provider admission request uses another provider"
            )
        ttl = _positive_int("ttl_seconds", ttl_seconds, maximum=86_400)
        self._verify_authority(request)
        now = self._current_time()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._expire(connection, now)
            state = self._validated_state(connection)
            if state["circuit_state"] not in {"closed", "half_open"}:
                connection.commit()
                raise ProviderAdmissionReconciliationError(
                    "provider admission circuit requires reconciliation"
                )
            if (
                state["circuit_state"] == "half_open"
                and request.binding_digest
                != state["half_open_probe_request_digest"]
            ):
                connection.commit()
                raise ProviderAdmissionReconciliationError(
                    "provider admission half-open slot is bound to another probe"
                )
            unresolved = connection.execute(
                """SELECT COUNT(*) FROM provider_admission_requests
                WHERE provider_id=? AND state='reconciliation_required'""",
                (request.provider_id,),
            ).fetchone()[0]
            if unresolved:
                connection.commit()
                raise ProviderAdmissionReconciliationError(
                    "provider admission has unresolved capacity"
                )
            row = connection.execute(
                "SELECT * FROM provider_admission_requests WHERE request_id=?",
                (request.request_id,),
            ).fetchone()
            if row is not None:
                if not self._row_matches_request(
                    row,
                    request,
                    self.policy.policy_digest,
                ):
                    raise ProviderAdmissionConflict(
                        "provider admission request identity conflicts"
                    )
                if row["state"] == "granted":
                    connection.commit()
                    return self._permit_from_row(row)
                if row["state"] != "waiting":
                    raise ProviderAdmissionConflict(
                        "provider admission request is already terminal or dispatched"
                    )
            else:
                connection.execute(
                    """INSERT INTO provider_admission_requests(
                        request_id, provider_id, project_binding_digest,
                        admission_lane, run_id, authority_digest,
                        authority_epoch, task_digest, member_digest,
                        provider_tier_binding_digest, policy_digest,
                        capacity_unit, state, fencing_token, requested_at,
                        granted_at, transport_started_at, terminal_at,
                        expires_at, terminal_evidence_digest
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1,
                              'waiting', NULL, ?, NULL, NULL, NULL, ?, NULL)""",
                    (
                        request.request_id,
                        request.provider_id,
                        request.project_binding_digest,
                        request.lane.value,
                        request.run_id,
                        request.authorization.digest,
                        request.authorization.epoch,
                        request.task_digest,
                        request.member_digest,
                        request.provider_tier_binding_digest,
                        self.policy.policy_digest,
                        now.isoformat(),
                        (now + timedelta(seconds=ttl)).isoformat(),
                    ),
                )
            active = connection.execute(
                """SELECT COALESCE(SUM(capacity_unit), 0)
                FROM provider_admission_requests
                WHERE provider_id=? AND state IN (
                    'granted', 'dispatched', 'reconciliation_required'
                )""",
                (request.provider_id,),
            ).fetchone()[0]
            effective_capacity = (
                1
                if state["circuit_state"] == "half_open"
                else state["effective_target"]
            )
            if active + 1 > effective_capacity:
                connection.commit()
                raise ProviderAdmissionBusyError(
                    "provider admission capacity is busy"
                )
            selected = self._selected_waiting(connection)
            if (
                selected is None
                or selected["request_id"] != request.request_id
            ):
                connection.commit()
                raise ProviderAdmissionBusyError(
                    "provider admission request is waiting for its fair turn"
                )
            connection.execute(
                "UPDATE fencing_counter SET value=value+1 WHERE singleton=1"
            )
            token = connection.execute(
                "SELECT value FROM fencing_counter WHERE singleton=1"
            ).fetchone()[0]
            sequence = state["grant_sequence"] + 1
            connection.execute(
                """INSERT INTO provider_admission_projects(
                    provider_id, project_binding_digest, active_units,
                    last_grant_sequence, updated_at
                ) VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(provider_id, project_binding_digest) DO UPDATE SET
                    active_units=active_units+1,
                    last_grant_sequence=excluded.last_grant_sequence,
                    updated_at=excluded.updated_at""",
                (
                    request.provider_id,
                    request.project_binding_digest,
                    sequence,
                    now.isoformat(),
                ),
            )
            connection.execute(
                """UPDATE provider_admission_state
                SET grant_sequence=?, last_granted_lane=?, updated_at=?
                WHERE provider_id=?""",
                (
                    sequence,
                    request.lane.value,
                    now.isoformat(),
                    request.provider_id,
                ),
            )
            connection.execute(
                """UPDATE provider_admission_requests
                SET state='granted', fencing_token=?, granted_at=?
                WHERE request_id=? AND state='waiting'""",
                (token, now.isoformat(), request.request_id),
            )
            row = connection.execute(
                "SELECT * FROM provider_admission_requests WHERE request_id=?",
                (request.request_id,),
            ).fetchone()
            connection.commit()
            return self._permit_from_row(row)
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _require_permit_row(
        connection: sqlite3.Connection,
        permit: ProviderAdmissionPermit,
    ) -> sqlite3.Row:
        if not isinstance(permit, ProviderAdmissionPermit):
            raise ValueError("permit must be a ProviderAdmissionPermit")
        row = connection.execute(
            "SELECT * FROM provider_admission_requests WHERE request_id=?",
            (permit.request_id,),
        ).fetchone()
        if row is None or (
            row["provider_id"] != permit.provider_id
            or row["project_binding_digest"]
            != permit.project_binding_digest
            or row["admission_lane"] != permit.admission_lane
            or row["run_id"] != permit.run_id
            or row["authority_digest"] != permit.authority_digest
            or row["authority_epoch"] != permit.authority_epoch
            or row["task_digest"] != permit.task_digest
            or row["member_digest"] != permit.member_digest
            or row["provider_tier_binding_digest"]
            != permit.provider_tier_binding_digest
            or row["policy_digest"] != permit.policy_digest
            or row["capacity_unit"] != permit.capacity_unit
            or row["fencing_token"] != permit.fencing_token
            or row["granted_at"] != permit.acquired_at
            or row["expires_at"] != permit.expires_at
        ):
            raise ProviderAdmissionConflict(
                "provider admission permit identity is invalid"
            )
        return row

    def cancel_before_transport(
        self,
        permit: ProviderAdmissionPermit,
    ) -> None:
        now = self._current_time().isoformat()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            state = self._validated_state(connection)
            row = self._require_permit_row(connection, permit)
            if row["state"] != "granted":
                raise ProviderAdmissionConflict(
                    "provider admission permit cannot be cancelled"
                )
            self._cancel_granted_row(
                connection,
                row,
                state,
                now=now,
                reason="half_open_cancelled",
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def cancel_waiting(self, request_id: str, run_id: str) -> bool:
        request = _uuid4("request_id", request_id)
        run = _uuid4("run_id", run_id)
        now = self._current_time().isoformat()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT state, run_id FROM provider_admission_requests
                WHERE request_id=?""",
                (request,),
            ).fetchone()
            if row is None:
                connection.commit()
                return False
            if row["run_id"] != run:
                raise ProviderAdmissionConflict(
                    "provider admission waiting identity is invalid"
                )
            if row["state"] != "waiting":
                raise ProviderAdmissionConflict(
                    "provider admission request is not waiting"
                )
            changed = connection.execute(
                """UPDATE provider_admission_requests
                SET state='cancelled', terminal_at=?
                WHERE request_id=? AND state='waiting'""",
                (now, request),
            ).rowcount
            connection.commit()
            return changed == 1
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def begin_transport(
        self,
        permit: ProviderAdmissionPermit,
        request: ProviderAdmissionRequest,
    ) -> None:
        if not isinstance(request, ProviderAdmissionRequest):
            raise ValueError("request must be a ProviderAdmissionRequest")
        current_time = self._current_time()
        now = current_time.isoformat()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._expire(connection, current_time)
            state = self._validated_state(connection)
            row = self._require_permit_row(connection, permit)
            if not self._row_matches_request(
                row,
                request,
                self.policy.policy_digest,
            ):
                connection.commit()
                raise ProviderAdmissionConflict(
                    "provider admission permit does not match request"
                )
            if row["state"] == "reconciliation_required":
                connection.commit()
                raise ProviderAdmissionReconciliationError(
                    "expired provider admission grant requires reconciliation"
                )
            if row["state"] != "granted":
                connection.commit()
                raise ProviderAdmissionConflict(
                    "provider admission permit is not a fresh grant"
                )
            unresolved = connection.execute(
                """SELECT COUNT(*) FROM provider_admission_requests
                WHERE provider_id=? AND state='reconciliation_required'""",
                (permit.provider_id,),
            ).fetchone()[0]
            if unresolved or state["circuit_state"] == "open":
                self._cancel_granted_row(
                    connection,
                    row,
                    state,
                    now=now,
                    reason="grant_blocked_by_open_circuit",
                )
                connection.commit()
                raise ProviderAdmissionReconciliationError(
                    "provider admission circuit opened before transport"
                )
            if (
                state["circuit_state"] == "half_open"
                and request.binding_digest
                != state["half_open_probe_request_digest"]
            ):
                self._cancel_granted_row(
                    connection,
                    row,
                    state,
                    now=now,
                    reason="half_open_probe_mismatch",
                )
                connection.commit()
                raise ProviderAdmissionConflict(
                    "provider admission permit is not the authorized probe"
                )
            try:
                self._verify_authority_locked(connection, request)
            except DispatchAuthorizationError:
                self._cancel_granted_row(
                    connection,
                    row,
                    state,
                    now=now,
                    reason="half_open_authority_invalid",
                )
                connection.commit()
                raise
            connection.execute(
                """UPDATE provider_admission_requests
                SET state='dispatched', transport_started_at=?
                WHERE request_id=? AND state='granted'""",
                (now, permit.request_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def finish(
        self,
        permit: ProviderAdmissionPermit,
        *,
        network_attempted: bool | None,
        response_received: bool | None,
        provider_http_status: int | None,
        terminal_persisted: bool,
        terminal_evidence_digest: str,
    ) -> None:
        if network_attempted not in {True, False, None}:
            raise ValueError("network_attempted must be boolean or None")
        if response_received not in {True, False, None}:
            raise ValueError("response_received must be boolean or None")
        if response_received is True and network_attempted is not True:
            raise ValueError("response_received requires network_attempted")
        if provider_http_status is not None and (
            isinstance(provider_http_status, bool)
            or not isinstance(provider_http_status, int)
            or not 100 <= provider_http_status <= 599
            or response_received is not True
        ):
            raise ValueError("provider_http_status is invalid")
        if not isinstance(terminal_persisted, bool):
            raise ValueError("terminal_persisted must be boolean")
        evidence = _digest(
            "terminal_evidence_digest",
            terminal_evidence_digest,
        )
        now = self._current_time().isoformat()
        ambiguous = (
            not terminal_persisted
            or network_attempted is None
            or (network_attempted is True and response_received is not True)
        )
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            state = self._validated_state(connection)
            row = self._require_permit_row(connection, permit)
            if row["state"] != "dispatched":
                raise ProviderAdmissionConflict(
                    "provider admission permit has no active transport"
                )
            if ambiguous:
                request_state = "reconciliation_required"
                circuit_state = "open"
                signal = "unknown_after_dispatch"
            else:
                request_state = "completed"
                provider_pressure = (
                    provider_http_status == 429
                    or (
                        provider_http_status is not None
                        and 500 <= provider_http_status <= 599
                    )
                )
                circuit_state = "open" if provider_pressure else "closed"
                if (
                    state["circuit_state"] == "half_open"
                    and network_attempted is False
                ):
                    # A local failure does not prove provider recovery.
                    circuit_state = "open"
                signal = (
                    f"http_{provider_http_status}"
                    if provider_http_status is not None
                    else (
                        "known_pre_network_terminal"
                        if network_attempted is False
                        else "response_received"
                    )
                )
                self._decrement_project(connection, row, now)
            connection.execute(
                """UPDATE provider_admission_requests
                SET state=?, terminal_at=?, terminal_evidence_digest=?
                WHERE request_id=?""",
                (request_state, now, evidence, permit.request_id),
            )
            transition_kind = (
                "unknown_after_dispatch"
                if ambiguous
                else (
                    "half_open_succeeded"
                    if state["circuit_state"] == "half_open"
                    and circuit_state == "closed"
                    else (
                        "half_open_failed"
                        if state["circuit_state"] == "half_open"
                        else (
                            "circuit_opened"
                            if circuit_state == "open"
                            else "terminal_observed"
                        )
                    )
                )
            )
            self._append_control_transition(
                connection,
                state,
                transition_kind=transition_kind,
                effective_target=state["effective_target"],
                circuit_state=circuit_state,
                half_open_probe_request_digest=None,
                last_signal=signal,
                now=now,
                request_id=permit.request_id,
                evidence_digest=evidence,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def read_request(self, request_id: str) -> ProviderAdmissionRecord:
        normalized = _uuid4("request_id", request_id)
        connection = self.database.connect()
        try:
            row = connection.execute(
                """SELECT * FROM provider_admission_requests
                WHERE request_id=?""",
                (normalized,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise ProviderAdmissionConflict(
                "provider admission request does not exist"
            )
        return ProviderAdmissionRecord(
            request_id=row["request_id"],
            provider_id=row["provider_id"],
            project_binding_digest=row["project_binding_digest"],
            admission_lane=row["admission_lane"],
            run_id=row["run_id"],
            state=row["state"],
            fencing_token=row["fencing_token"],
            requested_at=row["requested_at"],
            granted_at=row["granted_at"],
            transport_started_at=row["transport_started_at"],
            terminal_at=row["terminal_at"],
            expires_at=row["expires_at"],
            terminal_evidence_digest=row["terminal_evidence_digest"],
            resolution_evidence_digest=row["resolution_evidence_digest"],
            resolved_at=row["resolved_at"],
        )

    def resolve_reconciliation(
        self,
        request_id: str,
        reference: AuthorizationReference,
        *,
        resolution_evidence_digest: str,
    ) -> ProviderAdmissionRecord:
        request = _uuid4("request_id", request_id)
        if not isinstance(reference, AuthorizationReference):
            raise ValueError("reference must be an AuthorizationReference")
        evidence = _digest(
            "resolution_evidence_digest",
            resolution_evidence_digest,
        )
        connection = self.database.connect()
        try:
            row = connection.execute(
                """SELECT * FROM provider_admission_requests
                WHERE request_id=?""",
                (request,),
            ).fetchone()
        finally:
            connection.close()
        if row is None or row["state"] != "reconciliation_required":
            raise ProviderAdmissionConflict(
                "provider admission request does not require reconciliation"
            )
        self.authorities.verify(
            reference,
            provider_id=row["provider_id"],
            plane="provider_admission_reconciliation",
            task_type="provider_admission_resolution",
            member_digest=row["member_digest"],
            provider_tier_binding_digest=row[
                "provider_tier_binding_digest"
            ],
            project_binding_digest=row["project_binding_digest"],
            admission_lane=row["admission_lane"],
            provider_admission_policy_digest=row["policy_digest"],
        )
        now = self._current_time().isoformat()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            state = self._validated_state(connection)
            row = connection.execute(
                """SELECT * FROM provider_admission_requests
                WHERE request_id=?""",
                (request,),
            ).fetchone()
            if row is None or row["state"] != "reconciliation_required":
                raise ProviderAdmissionConflict(
                    "provider admission reconciliation state changed"
                )
            self._decrement_project(connection, row, now)
            connection.execute(
                """UPDATE provider_admission_requests
                SET state='reconciled', resolution_evidence_digest=?,
                    resolved_at=? WHERE request_id=?""",
                (evidence, now, request),
            )
            remaining = connection.execute(
                """SELECT COUNT(*) FROM provider_admission_requests
                WHERE provider_id=? AND state='reconciliation_required'""",
                (row["provider_id"],),
            ).fetchone()[0]
            self._append_control_transition(
                connection,
                state,
                transition_kind="reconciliation_resolved",
                effective_target=state["effective_target"],
                circuit_state="open" if remaining else "closed",
                half_open_probe_request_digest=None,
                last_signal="reconciled",
                now=now,
                request_id=request,
                evidence_digest=evidence,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.read_request(request)

    def status(self, provider_id: str) -> ProviderAdmissionStatus:
        provider = _identifier("provider_id", provider_id)
        if provider != self.policy.provider_id:
            raise ProviderAdmissionConflict(
                "provider admission status uses another provider"
            )
        connection = self.database.connect()
        try:
            state = self._validated_state(connection)
            rows = connection.execute(
                """SELECT state, COUNT(*) AS count
                FROM provider_admission_requests WHERE provider_id=?
                GROUP BY state""",
                (provider,),
            ).fetchall()
            lane_rows = connection.execute(
                """SELECT admission_lane, COUNT(*) AS count
                FROM provider_admission_requests
                WHERE provider_id=? AND state IN ('waiting','granted','dispatched')
                GROUP BY admission_lane""",
                (provider,),
            ).fetchall()
            project_rows = connection.execute(
                """SELECT project_binding_digest, active_units
                FROM provider_admission_projects
                WHERE provider_id=? AND active_units > 0
                ORDER BY project_binding_digest""",
                (provider,),
            ).fetchall()
            batch_columns = {
                item[1]
                for item in connection.execute(
                    "PRAGMA table_info(plan_queue_batches)"
                ).fetchall()
            }
            legacy_count = (
                connection.execute(
                    """SELECT COUNT(*) FROM plan_queue_batches
                    WHERE project_binding_digest IS NULL
                       OR admission_lane IS NULL
                       OR provider_admission_policy_digest IS NULL"""
                ).fetchone()[0]
                if {
                    "project_binding_digest",
                    "admission_lane",
                    "provider_admission_policy_digest",
                }
                <= batch_columns
                else 0
            )
        finally:
            connection.close()
        counts = {
            name: 0
            for name in (
                "waiting",
                "granted",
                "dispatched",
                "completed",
                "cancelled",
                "reconciliation_required",
                "reconciled",
            )
        }
        counts.update({row["state"]: row["count"] for row in rows})
        lane_counts = {item.value: 0 for item in AdmissionLane}
        lane_counts.update(
            {row["admission_lane"]: row["count"] for row in lane_rows}
        )
        return ProviderAdmissionStatus(
            initialized=True,
            provider_id=provider,
            policy_digest=self.policy.policy_digest,
            deployment_mode=state["deployment_mode"],
            deployment_digest=state["deployment_digest"],
            effective_target=state["effective_target"],
            candidate_target=self.policy.candidate_target,
            hard_max=self.policy.hard_max,
            per_project_cap=self.policy.per_project_cap,
            circuit_state=state["circuit_state"],
            last_signal=state["last_signal"],
            counts=counts,
            lane_counts=lane_counts,
            project_active_counts=tuple(
                {
                    "project_binding_digest": row[
                        "project_binding_digest"
                    ],
                    "active_units": row["active_units"],
                }
                for row in project_rows
            ),
            legacy_pre_provider_admission_count=legacy_count,
        )


def read_provider_admission_status(
    path: str | Path,
    provider_id: str,
) -> ProviderAdmissionStatus:
    candidate = Path(path)
    provider = _identifier("provider_id", provider_id)
    policy = glm_provider_admission_policy()
    if provider != policy.provider_id:
        raise ProviderAdmissionConflict(
            "provider admission status uses another provider"
        )
    empty_counts = {
        name: 0
        for name in (
            "waiting",
            "granted",
            "dispatched",
            "completed",
            "cancelled",
            "reconciliation_required",
            "reconciled",
        )
    }
    if not candidate.is_file():
        return ProviderAdmissionStatus(
            initialized=False,
            provider_id=provider,
            policy_digest=policy.policy_digest,
            deployment_mode=None,
            deployment_digest=None,
            effective_target=policy.effective_target,
            candidate_target=policy.candidate_target,
            hard_max=policy.hard_max,
            per_project_cap=policy.per_project_cap,
            circuit_state="closed",
            last_signal=None,
            counts=empty_counts,
            lane_counts={item.value: 0 for item in AdmissionLane},
            project_active_counts=(),
            legacy_pre_provider_admission_count=0,
        )
    connection = sqlite3.connect(candidate.absolute().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        meta = connection.execute(
            "SELECT version FROM schema_meta WHERE component='runtime'"
        ).fetchone()
        if meta is None or meta["version"] < 8:
            return ProviderAdmissionStatus(
                initialized=False,
                provider_id=provider,
                policy_digest=policy.policy_digest,
                deployment_mode=None,
                deployment_digest=None,
                effective_target=policy.effective_target,
                candidate_target=policy.candidate_target,
                hard_max=policy.hard_max,
                per_project_cap=policy.per_project_cap,
                circuit_state="closed",
                last_signal=None,
                counts=empty_counts,
                lane_counts={item.value: 0 for item in AdmissionLane},
                project_active_counts=(),
                legacy_pre_provider_admission_count=0,
            )
        if meta["version"] != RuntimeDatabase.SCHEMA_VERSION:
            raise ProviderAdmissionConflict(
                "provider admission runtime schema is unsupported"
            )
        policy_row = connection.execute(
            """SELECT body_json, body_sha256, policy_digest
            FROM provider_admission_policies
            WHERE provider_id=? AND revision=?""",
            (provider, policy.revision),
        ).fetchone()
        if policy_row is None:
            raise ProviderAdmissionConflict(
                "provider admission policy is missing"
            )
        expected_body_sha = hashlib.sha256(
            policy_row["body_json"].encode("utf-8")
        ).hexdigest()
        try:
            stored_policy = ProviderAdmissionPolicy.from_dict(
                json.loads(policy_row["body_json"])
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderAdmissionConflict(
                "provider admission policy is invalid"
            ) from exc
        if (
            expected_body_sha != policy_row["body_sha256"]
            or stored_policy != policy
            or stored_policy.policy_digest != policy_row["policy_digest"]
        ):
            raise ProviderAdmissionConflict(
                "provider admission policy is invalid"
            )
        state = _validated_control_state(connection, policy)
        rows = connection.execute(
            """SELECT state, COUNT(*) AS count
            FROM provider_admission_requests WHERE provider_id=?
            GROUP BY state""",
            (provider,),
        ).fetchall()
        lane_rows = connection.execute(
            """SELECT admission_lane, COUNT(*) AS count
            FROM provider_admission_requests
            WHERE provider_id=? AND state IN ('waiting','granted','dispatched')
            GROUP BY admission_lane""",
            (provider,),
        ).fetchall()
        project_rows = connection.execute(
            """SELECT project_binding_digest, active_units
            FROM provider_admission_projects
            WHERE provider_id=? AND active_units > 0
            ORDER BY project_binding_digest""",
            (provider,),
        ).fetchall()
        batch_columns = {
            item[1]
            for item in connection.execute(
                "PRAGMA table_info(plan_queue_batches)"
            ).fetchall()
        }
        legacy_count = (
            connection.execute(
                """SELECT COUNT(*) FROM plan_queue_batches
                WHERE project_binding_digest IS NULL
                   OR admission_lane IS NULL
                   OR provider_admission_policy_digest IS NULL"""
            ).fetchone()[0]
            if {
                "project_binding_digest",
                "admission_lane",
                "provider_admission_policy_digest",
            }
            <= batch_columns
            else 0
        )
        counts = dict(empty_counts)
        counts.update({row["state"]: row["count"] for row in rows})
        lane_counts = {item.value: 0 for item in AdmissionLane}
        lane_counts.update(
            {row["admission_lane"]: row["count"] for row in lane_rows}
        )
        return ProviderAdmissionStatus(
            initialized=True,
            provider_id=provider,
            policy_digest=policy.policy_digest,
            deployment_mode=state["deployment_mode"],
            deployment_digest=state["deployment_digest"],
            effective_target=state["effective_target"],
            candidate_target=policy.candidate_target,
            hard_max=policy.hard_max,
            per_project_cap=policy.per_project_cap,
            circuit_state=state["circuit_state"],
            last_signal=state["last_signal"],
            counts=counts,
            lane_counts=lane_counts,
            project_active_counts=tuple(
                {
                    "project_binding_digest": row[
                        "project_binding_digest"
                    ],
                    "active_units": row["active_units"],
                }
                for row in project_rows
            ),
            legacy_pre_provider_admission_count=legacy_count,
        )
    except sqlite3.Error as exc:
        raise ProviderAdmissionConflict(
            "provider admission runtime database is invalid"
        ) from exc
    finally:
        connection.close()


__all__ = [
    "AdmissionDeploymentMode",
    "AdmissionLane",
    "ProjectAdmissionBinding",
    "ProviderAdmissionCircuitBinding",
    "ProviderAdmissionKernel",
    "ProviderAdmissionPermit",
    "ProviderAdmissionPolicy",
    "ProviderAdmissionRecord",
    "ProviderAdmissionRequest",
    "ProviderAdmissionStatus",
    "ProviderAdmissionTargetBinding",
    "read_provider_admission_status",
    "glm_provider_admission_policy",
]
