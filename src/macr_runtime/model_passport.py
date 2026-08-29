from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .canonical import aware_iso8601, sha256_id
from .errors import ObservatoryConflict
from .observatory_db import ObservatoryDatabase


def _payload(canonical_json: str) -> dict[str, Any]:
    try:
        value = json.loads(canonical_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ObservatoryConflict("observatory canonical JSON is invalid") from exc
    if not isinstance(value, dict):
        raise ObservatoryConflict("observatory canonical JSON must be an object")
    return value


def _blind_spots(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ObservatoryConflict("blind_spots observation is invalid")
    return tuple(value)


@dataclass(frozen=True)
class PriceObservation:
    observation_id: str
    route_id: str
    observed_at: str
    price_kind: str
    amount: Decimal

    def to_dict(self) -> dict[str, str]:
        return {
            "observation_id": self.observation_id,
            "route_id": self.route_id,
            "observed_at": self.observed_at,
            "price_kind": self.price_kind,
            "amount": str(self.amount),
        }


@dataclass(frozen=True)
class MarketObservations:
    prices: tuple[PriceObservation, ...]
    benchmark_digests: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "prices": [item.to_dict() for item in self.prices],
            "benchmark_digests": list(self.benchmark_digests),
        }


@dataclass(frozen=True)
class RoutePrivacyObservation:
    observation_id: str
    route_id: str
    observed_at: str
    status: str

    def to_dict(self) -> dict[str, str]:
        return {
            "observation_id": self.observation_id,
            "route_id": self.route_id,
            "observed_at": self.observed_at,
            "status": self.status,
        }


@dataclass(frozen=True)
class QualificationProjection:
    decision_id: str
    qualification_key: str
    state: str
    evidence_set_digest: str
    decided_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "decision_id": self.decision_id,
            "qualification_key": self.qualification_key,
            "state": self.state,
            "evidence_set_digest": self.evidence_set_digest,
            "decided_at": self.decided_at,
        }


@dataclass(frozen=True)
class ModelPassport:
    digest: str
    subject_id: str
    identity_status: str
    first_seen_snapshot_id: str
    as_of: str
    route_ids: tuple[str, ...]
    observation_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    decision_ids: tuple[str, ...]
    invalidation_ids: tuple[str, ...]
    market_observations: MarketObservations
    route_privacy_observations: tuple[RoutePrivacyObservation, ...]
    qualification_states: tuple[QualificationProjection, ...]
    latest_evidence_at: str | None
    known_failure_modes: tuple[str, ...]
    blind_spots: tuple[str, ...]

    def __post_init__(self) -> None:
        expected = sha256_id("model_passport_v1", self.canonical_projection())
        if self.digest != expected:
            raise ValueError("passport digest does not match canonical projection")

    def canonical_projection(self) -> dict[str, object]:
        return {
            "subject_id": self.subject_id,
            "identity_status": self.identity_status,
            "first_seen_snapshot_id": self.first_seen_snapshot_id,
            "as_of": self.as_of,
            "route_ids": list(self.route_ids),
            "observation_ids": list(self.observation_ids),
            "evidence_ids": list(self.evidence_ids),
            "decision_ids": list(self.decision_ids),
            "invalidation_ids": list(self.invalidation_ids),
            "market_observations": self.market_observations.to_dict(),
            "route_privacy_observations": [
                item.to_dict() for item in self.route_privacy_observations
            ],
            "qualification_states": [
                item.to_dict() for item in self.qualification_states
            ],
            "latest_evidence_at": self.latest_evidence_at,
            "known_failure_modes": list(self.known_failure_modes),
            "blind_spots": list(self.blind_spots),
        }

    def to_dict(self) -> dict[str, object]:
        return {"digest": self.digest, **self.canonical_projection()}


class ModelPassportProjector:
    """Rebuildable immutable view over append-only observatory evidence."""

    def __init__(self, store: ObservatoryDatabase) -> None:
        if not isinstance(store, ObservatoryDatabase):
            raise ValueError("store must be an ObservatoryDatabase")
        self.store = store
        self._cache: dict[tuple[str, str], ModelPassport] = {}

    def build(self, subject_id: str, as_of: str) -> ModelPassport:
        normalized_as_of = aware_iso8601("as_of", as_of)
        key = (subject_id, normalized_as_of)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        passport = self._build(subject_id, normalized_as_of)
        self._cache[key] = passport
        return passport

    def rebuild_digest(self, subject_id: str, as_of: str) -> str:
        return self._build(
            subject_id,
            aware_iso8601("as_of", as_of),
        ).digest

    def clear_cache(self, subject_id: str | None = None) -> None:
        if subject_id is None:
            self._cache.clear()
            return
        for key in tuple(self._cache):
            if key[0] == subject_id:
                del self._cache[key]

    def _build(self, subject_id: str, as_of: str) -> ModelPassport:
        subject = self.store.read_model_subject(subject_id)
        if subject is None:
            raise ObservatoryConflict("model subject does not exist")
        subject_data = _payload(subject.canonical_json)
        identity_status = subject_data.get("identity_status")
        if identity_status not in {"resolved", "claimed", "unresolved"}:
            raise ObservatoryConflict("model subject identity status is invalid")
        first_snapshot = self.store.read_snapshot(
            subject.first_seen_snapshot_id
        )
        if first_snapshot is None:
            raise ObservatoryConflict("model subject first-seen snapshot is missing")
        if as_of < first_snapshot.observed_at:
            raise ValueError("as_of is before first seen model subject")

        observations = tuple(
            item
            for item in self.store.read_observations(subject.subject_id)
            if item.observed_at <= as_of
        )
        referenced_route_ids = tuple(
            sorted(
                {
                    item.route_id
                    for item in observations
                    if item.route_id is not None
                }
            )
        )
        known_routes = {
            item.route_id: item
            for item in self.store.read_routes_for_subject(subject.subject_id)
        }
        missing_routes = sorted(set(referenced_route_ids) - set(known_routes))
        if missing_routes:
            raise ObservatoryConflict(
                "model observation references a missing execution route"
            )

        prices: list[PriceObservation] = []
        privacy: list[RoutePrivacyObservation] = []
        benchmark_digests: set[str] = set()
        known_failures: set[str] = set()
        blind_spots: set[str] = set()
        for observation in observations:
            payload = _payload(observation.canonical_json)
            raw_prices = payload.get("pricing", ())
            if raw_prices is not None:
                if not isinstance(raw_prices, list):
                    raise ObservatoryConflict("pricing observation is invalid")
                for raw_price in raw_prices:
                    if not isinstance(raw_price, Mapping):
                        raise ObservatoryConflict("pricing observation is invalid")
                    kind = raw_price.get("price_kind")
                    amount_text = raw_price.get("usd_per_unit")
                    if (
                        observation.route_id is None
                        or not isinstance(kind, str)
                        or not isinstance(amount_text, str)
                    ):
                        raise ObservatoryConflict("pricing observation is invalid")
                    try:
                        amount = Decimal(amount_text)
                    except InvalidOperation as exc:
                        raise ObservatoryConflict(
                            "pricing observation amount is invalid"
                        ) from exc
                    if not amount.is_finite() or amount < 0:
                        raise ObservatoryConflict(
                            "pricing observation amount is invalid"
                        )
                    prices.append(
                        PriceObservation(
                            observation_id=observation.observation_id,
                            route_id=observation.route_id,
                            observed_at=observation.observed_at,
                            price_kind=kind,
                            amount=amount,
                        )
                    )
            status = payload.get("privacy_status")
            if status is not None:
                if observation.route_id is None or not isinstance(status, str):
                    raise ObservatoryConflict("privacy observation is invalid")
                privacy.append(
                    RoutePrivacyObservation(
                        observation_id=observation.observation_id,
                        route_id=observation.route_id,
                        observed_at=observation.observed_at,
                        status=status,
                    )
                )
            benchmark = payload.get("benchmark_digest")
            if benchmark is not None:
                if not isinstance(benchmark, str):
                    raise ObservatoryConflict("benchmark digest is invalid")
                benchmark_digests.add(benchmark)
            failure_mode = payload.get("failure_mode")
            if failure_mode is not None:
                if not isinstance(failure_mode, str):
                    raise ObservatoryConflict("failure mode is invalid")
                known_failures.add(failure_mode)
            blind_spots.update(_blind_spots(payload.get("blind_spots")))

        evidence = tuple(
            item
            for item in self.store.read_evidence_for_subject(subject.subject_id)
            if item.observed_at <= as_of
        )
        qualification_keys = tuple(
            sorted({item.qualification_key for item in evidence})
        )
        for item in evidence:
            payload = _payload(item.canonical_json)
            failure_mode = payload.get("failure_mode")
            if failure_mode is not None:
                if not isinstance(failure_mode, str):
                    raise ObservatoryConflict("evidence failure mode is invalid")
                known_failures.add(failure_mode)
            blind_spots.update(_blind_spots(payload.get("blind_spots")))

        decisions = tuple(
            item
            for key in qualification_keys
            for item in self.store.read_qualification_decisions(key)
            if item.decided_at <= as_of
        )
        decisions = tuple(sorted(decisions, key=lambda item: (item.decided_at, item.decision_id)))
        for item in decisions:
            blind_spots.update(
                _blind_spots(_payload(item.canonical_json).get("blind_spots"))
            )
            if item.state in {"rejected", "suspended", "revoked", "stale"}:
                known_failures.add(f"qualification_{item.state}")

        invalidations = tuple(
            item
            for key in qualification_keys
            for item in self.store.read_qualification_invalidations(key)
            if item.invalidated_at <= as_of
        )
        invalidations = tuple(
            sorted(
                invalidations,
                key=lambda item: (item.invalidated_at, item.invalidation_id),
            )
        )
        known_failures.update(item.reason_code for item in invalidations)

        if not evidence:
            blind_spots.add("no_subject_evidence")
        if not privacy:
            blind_spots.add("no_route_privacy_evidence")
        if not decisions:
            blind_spots.add("no_qualification_decision")
        if identity_status == "unresolved":
            blind_spots.add("identity_unresolved")

        canonical = {
            "subject_id": subject.subject_id,
            "identity_status": identity_status,
            "first_seen_snapshot_id": subject.first_seen_snapshot_id,
            "as_of": as_of,
            "route_ids": list(referenced_route_ids),
            "observation_ids": [item.observation_id for item in observations],
            "evidence_ids": [item.evidence_id for item in evidence],
            "decision_ids": [item.decision_id for item in decisions],
            "invalidation_ids": [
                item.invalidation_id for item in invalidations
            ],
            "market_observations": MarketObservations(
                prices=tuple(prices),
                benchmark_digests=tuple(sorted(benchmark_digests)),
            ).to_dict(),
            "route_privacy_observations": [item.to_dict() for item in privacy],
            "qualification_states": [
                QualificationProjection(
                    decision_id=item.decision_id,
                    qualification_key=item.qualification_key,
                    state=item.state,
                    evidence_set_digest=item.evidence_set_digest,
                    decided_at=item.decided_at,
                ).to_dict()
                for item in decisions
            ],
            "latest_evidence_at": (
                evidence[-1].observed_at if evidence else None
            ),
            "known_failure_modes": sorted(known_failures),
            "blind_spots": sorted(blind_spots),
        }
        return ModelPassport(
            digest=sha256_id("model_passport_v1", canonical),
            subject_id=subject.subject_id,
            identity_status=identity_status,
            first_seen_snapshot_id=subject.first_seen_snapshot_id,
            as_of=as_of,
            route_ids=referenced_route_ids,
            observation_ids=tuple(item.observation_id for item in observations),
            evidence_ids=tuple(item.evidence_id for item in evidence),
            decision_ids=tuple(item.decision_id for item in decisions),
            invalidation_ids=tuple(
                item.invalidation_id for item in invalidations
            ),
            market_observations=MarketObservations(
                prices=tuple(prices),
                benchmark_digests=tuple(sorted(benchmark_digests)),
            ),
            route_privacy_observations=tuple(privacy),
            qualification_states=tuple(
                QualificationProjection(
                    decision_id=item.decision_id,
                    qualification_key=item.qualification_key,
                    state=item.state,
                    evidence_set_digest=item.evidence_set_digest,
                    decided_at=item.decided_at,
                )
                for item in decisions
            ),
            latest_evidence_at=evidence[-1].observed_at if evidence else None,
            known_failure_modes=tuple(sorted(known_failures)),
            blind_spots=tuple(sorted(blind_spots)),
        )


__all__ = [
    "MarketObservations",
    "ModelPassport",
    "ModelPassportProjector",
    "PriceObservation",
    "QualificationProjection",
    "RoutePrivacyObservation",
]
