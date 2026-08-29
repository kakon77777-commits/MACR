from __future__ import annotations

import dataclasses
import unittest
from decimal import Decimal

from macr_runtime.canonical import sha256_id
from macr_runtime.model_identity import (
    ExecutionRouteIdentity,
    IdentityStatus,
    ModelSubject,
)
from macr_runtime.model_passport import ModelPassportProjector
from macr_runtime.observatory_db import ObservatoryConflict, ObservatoryDatabase

from tests.support import d_drive_tempdir


T1 = "2026-08-29T00:00:00+00:00"
T2 = "2026-08-30T00:00:00+00:00"
T3 = "2026-08-31T00:00:00+00:00"
REQUEST = sha256_id("request_shape_v1", {"source": "passport-test"})
PARAMS = sha256_id("parameter_profile_v1", {"temperature": 0})
POLICY = sha256_id("data_policy_v1", {"privacy": "unknown"})
QUALIFICATION = "9" * 64


def append_snapshot(
    store: ObservatoryDatabase,
    observed_at: str,
    raw: bytes,
):
    return store.append_snapshot(
        {
            "source_id": "passport_fixture",
            "observed_at": observed_at,
            "request_shape_sha256": REQUEST,
            "normalized_bytes_sha256": None,
            "parser_version": "passport-v1",
        },
        raw_bytes=raw,
    )


def seed_store(store: ObservatoryDatabase) -> tuple[ModelSubject, ExecutionRouteIdentity]:
    first = append_snapshot(store, T1, b'{"price":"0.15"}')
    second = append_snapshot(store, T2, b'{"price":"0.10"}')
    subject = ModelSubject.create(
        "z-ai",
        "glm-5.3-flash",
        "z-ai/glm-5.3-flash-20260826",
        IdentityStatus.CLAIMED,
        first.snapshot_id,
    )
    route = ExecutionRouteIdentity.create(
        subject.subject_id,
        "openrouter_discovery_claim",
        "https://openrouter.ai/api/v1",
        "z-ai/glm-5.3-flash",
        PARAMS,
        "unbound-v1",
        POLICY,
    )
    store.append_model_subject(subject)
    store.append_execution_route(route)
    for snapshot, observed_at, amount in (
        (first, T1, "0.15"),
        (second, T2, "0.10"),
    ):
        store.append_observation(
            {
                "subject_id": subject.subject_id,
                "route_id": route.route_id,
                "snapshot_id": snapshot.snapshot_id,
                "kind": "openrouter_model_catalog",
                "observed_at": observed_at,
                "payload": {
                    "pricing": [
                        {
                            "price_kind": "prompt",
                            "usd_per_unit": amount,
                        }
                    ],
                    "privacy_status": "unknown_conservative",
                    "description_digest": "a" * 64,
                },
            }
        )
    store.append_evidence(
        {
            "qualification_key": QUALIFICATION,
            "kind": "probe_verification",
            "subject_digest": subject.subject_id,
            "observed_at": T2,
            "payload": {
                "passed": True,
                "blind_spots": ["live_not_measured"],
                "failure_mode": "long_context_not_measured",
            },
        }
    )
    store.append_qualification_decision(
        {
            "qualification_key": QUALIFICATION,
            "state": "shadow_only",
            "evidence_set_digest": "b" * 64,
            "decided_at": T2,
            "payload": {"blind_spots": ["minimum_trials_not_met"]},
        }
    )
    store.append_qualification_invalidation(
        {
            "qualification_key": QUALIFICATION,
            "reason_code": "route_policy_changed",
            "source_id": "policy_snapshot",
            "invalidated_at": T3,
        }
    )
    return subject, route


class ModelPassportTests(unittest.TestCase):
    def test_passport_rebuild_is_deterministic_and_keeps_price_history(self) -> None:
        with d_drive_tempdir() as temp:
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            subject, route = seed_store(store)
            projector = ModelPassportProjector(store)
            passport = projector.build(subject.subject_id, T3)
            rebuilt = projector.build(subject.subject_id, T3)
            rebuilt_digest = projector.rebuild_digest(subject.subject_id, T3)

        self.assertEqual(
            [item.amount for item in passport.market_observations.prices],
            [Decimal("0.15"), Decimal("0.10")],
        )
        self.assertEqual(
            [item.route_id for item in passport.market_observations.prices],
            [route.route_id, route.route_id],
        )
        self.assertEqual(passport.digest, rebuilt.digest)
        self.assertEqual(passport.digest, rebuilt_digest)
        self.assertEqual(passport.qualification_states[0].state, "shadow_only")
        self.assertIn("route_policy_changed", passport.known_failure_modes)
        self.assertIn("live_not_measured", passport.blind_spots)

    def test_projection_cache_delete_does_not_delete_evidence(self) -> None:
        with d_drive_tempdir() as temp:
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            subject, _ = seed_store(store)
            projector = ModelPassportProjector(store)
            first = projector.build(subject.subject_id, T3)
            expected_evidence = first.evidence_ids
            projector.clear_cache(subject.subject_id)
            rebuilt = projector.build(subject.subject_id, T3)
            persisted = tuple(
                item.evidence_id
                for item in store.read_evidence_for_subject(subject.subject_id)
            )

        self.assertEqual(rebuilt.evidence_ids, expected_evidence)
        self.assertEqual(persisted, expected_evidence)

    def test_as_of_excludes_future_observations_and_invalidations(self) -> None:
        with d_drive_tempdir() as temp:
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            subject, _ = seed_store(store)
            passport = ModelPassportProjector(store).build(subject.subject_id, T1)

        self.assertEqual(
            [item.amount for item in passport.market_observations.prices],
            [Decimal("0.15")],
        )
        self.assertEqual(passport.evidence_ids, ())
        self.assertNotIn("route_policy_changed", passport.known_failure_modes)
        self.assertIn("no_subject_evidence", passport.blind_spots)

    def test_passport_is_frozen_content_free_projection(self) -> None:
        with d_drive_tempdir() as temp:
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            subject, _ = seed_store(store)
            passport = ModelPassportProjector(store).build(subject.subject_id, T3)
            serialized = str(passport.to_dict())

        self.assertNotIn("description", serialized.lower())
        self.assertNotIn("ignore previous", serialized.lower())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            passport.digest = "0" * 64  # type: ignore[misc]
        with self.assertRaisesRegex(ValueError, "digest"):
            dataclasses.replace(passport, digest="0" * 64)

    def test_missing_subject_and_pre_first_seen_as_of_fail_closed(self) -> None:
        with d_drive_tempdir() as temp:
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            subject, _ = seed_store(store)
            projector = ModelPassportProjector(store)
            with self.assertRaisesRegex(ObservatoryConflict, "subject"):
                projector.build("f" * 64, T3)
            with self.assertRaisesRegex(ValueError, "before first seen"):
                projector.build(
                    subject.subject_id,
                    "2026-08-28T00:00:00+00:00",
                )


if __name__ == "__main__":
    unittest.main()
