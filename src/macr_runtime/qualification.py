from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from .canonical import aware_iso8601, sha256_id
from .model_identity import QualificationKey
from .observatory_db import ObservatoryDatabase
from .probe_registry import ProbeDefinition, ProbeRegistry


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _payload(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("probe evidence payload must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("probe evidence payload must be an object")
    return parsed


def _required_boolean(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"probe evidence {key} must be boolean")
    return value


def _blind_spots(payload: Mapping[str, Any]) -> tuple[str, ...]:
    value = payload.get("blind_spots", ())
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValueError("probe evidence blind_spots must be strings")
    return tuple(value)


def wilson_lower_bound(
    successes: int,
    trials: int,
    z: float = 1.96,
) -> float:
    if (
        isinstance(successes, bool)
        or isinstance(trials, bool)
        or not isinstance(successes, int)
        or not isinstance(trials, int)
        or successes < 0
        or trials < 0
        or successes > trials
    ):
        raise ValueError("successes and trials must satisfy 0 <= successes <= trials")
    if isinstance(z, bool) or not isinstance(z, (int, float)):
        raise ValueError("z must be a finite positive number")
    normalized_z = float(z)
    if not math.isfinite(normalized_z) or normalized_z <= 0:
        raise ValueError("z must be a finite positive number")
    if trials == 0:
        return 0.0
    proportion = successes / trials
    z2 = normalized_z * normalized_z
    denominator = 1.0 + z2 / trials
    center = proportion + z2 / (2.0 * trials)
    margin = normalized_z * math.sqrt(
        (proportion * (1.0 - proportion) + z2 / (4.0 * trials)) / trials
    )
    return max(0.0, (center - margin) / denominator)


class QualificationState(str, Enum):
    UNTESTED = "untested"
    SHADOW_ONLY = "shadow_only"
    QUALIFIED = "qualified"
    STALE = "stale"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    REJECTED = "rejected"


@dataclass(frozen=True)
class QualificationPolicy:
    min_trials: int
    minimum_lower_bound: float
    max_evidence_age_days: int
    require_negative_controls: bool

    def __post_init__(self) -> None:
        if isinstance(self.min_trials, bool) or not isinstance(
            self.min_trials,
            int,
        ):
            raise ValueError("min_trials must be an integer")
        if not 1 <= self.min_trials <= 100_000:
            raise ValueError("min_trials is out of range")
        if isinstance(self.minimum_lower_bound, bool) or not isinstance(
            self.minimum_lower_bound,
            (int, float),
        ):
            raise ValueError("minimum_lower_bound must be between 0 and 1")
        lower = float(self.minimum_lower_bound)
        if not math.isfinite(lower) or not 0 <= lower <= 1:
            raise ValueError("minimum_lower_bound must be between 0 and 1")
        if isinstance(self.max_evidence_age_days, bool) or not isinstance(
            self.max_evidence_age_days,
            int,
        ):
            raise ValueError("max_evidence_age_days must be an integer")
        if not 1 <= self.max_evidence_age_days <= 36500:
            raise ValueError("max_evidence_age_days is out of range")
        if not isinstance(self.require_negative_controls, bool):
            raise ValueError("require_negative_controls must be boolean")
        object.__setattr__(self, "minimum_lower_bound", lower)

    @property
    def policy_digest(self) -> str:
        return sha256_id("qualification_policy_v1", self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "min_trials": self.min_trials,
            "minimum_lower_bound": self.minimum_lower_bound,
            "max_evidence_age_days": self.max_evidence_age_days,
            "require_negative_controls": self.require_negative_controls,
        }


@dataclass(frozen=True)
class QualificationDecision:
    decision_id: str
    qualification_key: str
    state: QualificationState
    evidence_set_digest: str
    policy_digest: str
    decided_at: str
    evidence_ids: tuple[str, ...]
    invalidation_ids: tuple[str, ...]
    successes: int
    trials: int
    lower_bound: float
    blind_spots: tuple[str, ...]

    def __post_init__(self) -> None:
        _digest("decision_id", self.decision_id)
        _digest("qualification_key", self.qualification_key)
        if not isinstance(self.state, QualificationState):
            raise ValueError("state must be a QualificationState")
        _digest("evidence_set_digest", self.evidence_set_digest)
        _digest("policy_digest", self.policy_digest)
        aware_iso8601("decided_at", self.decided_at)
        if any(not _SHA256.fullmatch(item) for item in self.evidence_ids):
            raise ValueError("evidence_ids must contain SHA-256 digests")
        if any(not _SHA256.fullmatch(item) for item in self.invalidation_ids):
            raise ValueError("invalidation_ids must contain SHA-256 digests")

    def to_dict(self) -> dict[str, object]:
        return {
            "decision_id": self.decision_id,
            "qualification_key": self.qualification_key,
            "state": self.state.value,
            "evidence_set_digest": self.evidence_set_digest,
            "policy_digest": self.policy_digest,
            "decided_at": self.decided_at,
            "evidence_ids": list(self.evidence_ids),
            "invalidation_ids": list(self.invalidation_ids),
            "successes": self.successes,
            "trials": self.trials,
            "lower_bound": self.lower_bound,
            "blind_spots": list(self.blind_spots),
        }


class QualificationEngine:
    def __init__(
        self,
        store: ObservatoryDatabase,
        probes: ProbeRegistry,
    ) -> None:
        if not isinstance(store, ObservatoryDatabase):
            raise ValueError("store must be an ObservatoryDatabase")
        if not isinstance(probes, ProbeRegistry):
            raise ValueError("probes must be a ProbeRegistry")
        self.store = store
        self.probes = probes

    def evaluate(
        self,
        key: QualificationKey,
        policy: QualificationPolicy,
        as_of: str,
    ) -> QualificationDecision:
        if not isinstance(key, QualificationKey):
            raise ValueError("key must be a QualificationKey")
        if not isinstance(policy, QualificationPolicy):
            raise ValueError("policy must be a QualificationPolicy")
        decided_at = aware_iso8601("as_of", as_of)
        blind_spots: set[str] = set()
        forced_state: QualificationState | None = None

        try:
            probe = self.probes.get(key.probe_digest)
        except KeyError:
            probe = None
            forced_state = QualificationState.UNTESTED
            blind_spots.add("probe_definition_missing")
        if probe is not None and not self._probe_matches_key(probe, key):
            forced_state = QualificationState.STALE
            blind_spots.add("probe_binding_changed")

        subject = self.store.read_model_subject(key.model_subject_id)
        if subject is None:
            forced_state = QualificationState.UNTESTED
            blind_spots.add("model_subject_missing")
            identity_status = None
        else:
            subject_payload = _payload(subject.canonical_json)
            identity_status = subject_payload.get("identity_status")
            if identity_status not in {"resolved", "claimed", "unresolved"}:
                forced_state = QualificationState.UNTESTED
                blind_spots.add("identity_status_invalid")
            elif identity_status == "unresolved":
                forced_state = QualificationState.SHADOW_ONLY
                blind_spots.add("identity_unresolved")

        route = self.store.read_execution_route(key.route_id)
        if route is None:
            forced_state = QualificationState.UNTESTED
            blind_spots.add("execution_route_missing")
        elif route.model_subject_id != key.model_subject_id:
            forced_state = QualificationState.STALE
            blind_spots.add("route_subject_binding_changed")

        evidence = tuple(
            item
            for item in self.store.read_evidence(key.digest)
            if item.kind == "probe_result" and item.observed_at <= decided_at
        )
        invalidations = tuple(
            item
            for item in self.store.read_qualification_invalidations(key.digest)
            if item.invalidated_at <= decided_at
        )
        invalidations = tuple(
            sorted(
                invalidations,
                key=lambda item: (item.invalidated_at, item.invalidation_id),
            )
        )

        successes = 0
        trials = 0
        saw_rejection = False
        saw_stale = False
        saw_incomplete_lineage = False
        trial_payloads: dict[str, str] = {}
        for item in evidence:
            trials += 1
            try:
                payload = _payload(item.canonical_json)
                blind_spots.update(_blind_spots(payload))
                trial_id = _digest("trial_id", payload.get("trial_id"))
                canonical_trial = item.canonical_json
                prior = trial_payloads.get(trial_id)
                if prior is not None:
                    blind_spots.add("duplicate_or_conflicting_trial_id")
                    saw_rejection = True
                else:
                    trial_payloads[trial_id] = canonical_trial
                if item.subject_digest != key.model_subject_id:
                    blind_spots.add("evidence_subject_mismatch")
                    saw_incomplete_lineage = True
                bindings = {
                    "model_subject_id": key.model_subject_id,
                    "route_id": key.route_id,
                    "role_digest": key.role_digest,
                    "context_class": key.context_class,
                    "verifier_suite_digest": key.verifier_suite_digest,
                    "probe_digest": key.probe_digest,
                }
                if any(payload.get(name) != value for name, value in bindings.items()):
                    blind_spots.add("bound_version_or_identity_mismatch")
                    saw_stale = True
                provider_success = _required_boolean(
                    payload,
                    "provider_terminal_success",
                )
                verifier_passed = _required_boolean(
                    payload,
                    "verifier_passed",
                )
                negative_control_passed = _required_boolean(
                    payload,
                    "negative_control_passed",
                )
                bound_versions_current = _required_boolean(
                    payload,
                    "bound_versions_current",
                )
                lineage_complete = _required_boolean(
                    payload,
                    "lineage_complete",
                )
                conflicting = _required_boolean(payload, "conflicting")
                if not bound_versions_current:
                    blind_spots.add("bound_versions_stale")
                    saw_stale = True
                if not lineage_complete:
                    blind_spots.add("lineage_incomplete")
                    saw_incomplete_lineage = True
                if conflicting:
                    blind_spots.add("conflicting_verifier_evidence")
                    saw_rejection = True
                if policy.require_negative_controls and not negative_control_passed:
                    blind_spots.add("negative_control_failed")
                    saw_rejection = True
                if provider_success and verifier_passed and negative_control_passed:
                    successes += 1
                elif not verifier_passed:
                    blind_spots.add("verifier_failures_observed")
            except ValueError:
                blind_spots.add("malformed_probe_evidence")
                saw_rejection = True

        lower_bound = wilson_lower_bound(successes, trials)
        if not evidence:
            blind_spots.add("no_probe_evidence")
            state = QualificationState.UNTESTED
        elif saw_rejection:
            state = QualificationState.REJECTED
        elif saw_stale:
            state = QualificationState.STALE
        elif saw_incomplete_lineage or identity_status == "unresolved":
            state = QualificationState.SHADOW_ONLY
        elif trials < policy.min_trials:
            state = QualificationState.SHADOW_ONLY
            blind_spots.add("minimum_trials_not_met")
        elif lower_bound < policy.minimum_lower_bound:
            state = QualificationState.SHADOW_ONLY
            blind_spots.add("confidence_lower_bound_below_policy")
        else:
            state = QualificationState.QUALIFIED

        if evidence:
            latest = datetime.fromisoformat(evidence[-1].observed_at)
            decision_time = datetime.fromisoformat(decided_at)
            age_days = (decision_time - latest).total_seconds() / 86400.0
            if age_days > policy.max_evidence_age_days:
                if state is not QualificationState.REJECTED:
                    state = QualificationState.STALE
                blind_spots.add("evidence_stale")

        if invalidations:
            reasons = tuple(item.reason_code.lower() for item in invalidations)
            if any("revok" in reason for reason in reasons):
                state = QualificationState.REVOKED
            elif any("suspend" in reason for reason in reasons):
                state = QualificationState.SUSPENDED
            elif state is not QualificationState.REJECTED:
                state = QualificationState.STALE
            blind_spots.add("qualification_invalidated")

        if forced_state is not None and state not in {
            QualificationState.REJECTED,
            QualificationState.REVOKED,
            QualificationState.SUSPENDED,
        }:
            state = forced_state

        evidence_ids = tuple(item.evidence_id for item in evidence)
        invalidation_ids = tuple(item.invalidation_id for item in invalidations)
        evidence_set_digest = sha256_id(
            "qualification_evidence_set_v1",
            {
                "evidence_ids": list(evidence_ids),
                "invalidation_ids": list(invalidation_ids),
            },
        )
        payload = {
            "policy_digest": policy.policy_digest,
            "model_subject_id": key.model_subject_id,
            "route_id": key.route_id,
            "role_digest": key.role_digest,
            "context_class": key.context_class,
            "verifier_suite_digest": key.verifier_suite_digest,
            "probe_digest": key.probe_digest,
            "evidence_ids": list(evidence_ids),
            "invalidation_ids": list(invalidation_ids),
            "successes": successes,
            "trials": trials,
            "lower_bound": lower_bound,
            "blind_spots": sorted(blind_spots),
        }
        persisted = self.store.append_qualification_decision(
            {
                "qualification_key": key.digest,
                "state": state.value,
                "evidence_set_digest": evidence_set_digest,
                "decided_at": decided_at,
                "payload": payload,
            }
        )
        return QualificationDecision(
            decision_id=persisted.decision_id,
            qualification_key=key.digest,
            state=state,
            evidence_set_digest=evidence_set_digest,
            policy_digest=policy.policy_digest,
            decided_at=decided_at,
            evidence_ids=evidence_ids,
            invalidation_ids=invalidation_ids,
            successes=successes,
            trials=trials,
            lower_bound=lower_bound,
            blind_spots=tuple(sorted(blind_spots)),
        )

    @staticmethod
    def _probe_matches_key(
        probe: ProbeDefinition,
        key: QualificationKey,
    ) -> bool:
        return (
            probe.probe_digest == key.probe_digest
            and probe.role_digest == key.role_digest
            and probe.context_class == key.context_class
            and probe.verifier_suite_digest == key.verifier_suite_digest
        )


__all__ = [
    "QualificationDecision",
    "QualificationEngine",
    "QualificationPolicy",
    "QualificationState",
    "wilson_lower_bound",
]
