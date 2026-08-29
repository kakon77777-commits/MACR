from __future__ import annotations

import json
import unittest

from macr_runtime.canonical import canonical_json_bytes
from macr_runtime.discovery.base import DiscoverySnapshot, ModelObservation
from macr_runtime.model_identity import IdentityStatus, ModelSubject
from macr_runtime.observatory import ModelObservatory
from macr_runtime.observatory_db import ObservatoryConflict, ObservatoryDatabase

from tests.support import d_drive_tempdir
from tests.test_discovery_contracts import (
    FixtureNormalizer,
    OBSERVED_AT,
    RAW,
    query,
    snapshot,
)


class FixtureProvider:
    provider_id = "fixture_provider"

    def snapshot(self, requested) -> DiscoverySnapshot:
        del requested
        return snapshot()


class CaptureCheckingNormalizer(FixtureNormalizer):
    def __init__(self, store: ObservatoryDatabase) -> None:
        self.store = store
        self.capture_was_visible = False

    def normalize(
        self,
        captured: DiscoverySnapshot,
    ) -> tuple[ModelObservation, ...]:
        record = self.store.read_snapshot(captured.snapshot_id)
        self.capture_was_visible = (
            record is not None
            and self.store.read_snapshot_bytes(captured.snapshot_id) == RAW
        )
        return super().normalize(captured)


class ConflictingNormalizer(FixtureNormalizer):
    def normalize(
        self,
        captured: DiscoverySnapshot,
    ) -> tuple[ModelObservation, ...]:
        first = super().normalize(captured)[0]
        conflicting_subject = ModelSubject.create(
            first.model_subject.vendor,
            first.model_subject.vendor_model_id,
            first.model_subject.concrete_revision,
            IdentityStatus.RESOLVED,
            captured.snapshot_id,
        )
        second = ModelObservation.create(
            model_subject=conflicting_subject,
            execution_route=first.execution_route,
            snapshot_id=captured.snapshot_id,
            kind="catalog_record",
            observed_at=captured.observed_at,
            payload={"context_tokens": 131072, "variant": 2},
        )
        return (first, second)


class FailingNormalizer(FixtureNormalizer):
    def normalize(self, captured: DiscoverySnapshot):
        del captured
        raise ValueError("injected parser failure")


class ModelObservatoryTests(unittest.TestCase):
    def test_ingest_captures_raw_before_normalization_and_returns_content_free_report(self) -> None:
        with d_drive_tempdir() as temp:
            database = temp / "observatory.sqlite3"
            store = ObservatoryDatabase(database, temp / "snapshots")
            normalizer = CaptureCheckingNormalizer(store)
            report = ModelObservatory(store, normalizer).ingest(
                FixtureProvider(),
                query(),
            )
            db_bytes = database.read_bytes()

            self.assertTrue(normalizer.capture_was_visible)
            self.assertEqual(report.observation_count, 1)
            self.assertEqual(len(report.subject_ids), 1)
            self.assertEqual(len(report.route_ids), 1)
            self.assertEqual(len(report.observation_ids), 1)
            self.assertNotIn(b"ignore previous", db_bytes)
            self.assertIn(b"ignore previous", store.read_snapshot_bytes(report.snapshot_id))
            self.assertNotIn("raw", report.to_dict())

    def test_normalizer_failure_retains_raw_snapshot_but_no_normalized_rows(self) -> None:
        with d_drive_tempdir() as temp:
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            with self.assertRaisesRegex(ValueError, "parser failure"):
                ModelObservatory(store, FailingNormalizer()).ingest(
                    FixtureProvider(),
                    query(),
                )
            captured = snapshot()
            connection = store.connect()
            try:
                counts = tuple(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in (
                        "model_subjects",
                        "execution_routes",
                        "model_observations",
                    )
                )
            finally:
                connection.close()
            snapshot_retained = store.read_snapshot(captured.snapshot_id) is not None

        self.assertTrue(snapshot_retained)
        self.assertEqual(counts, (0, 0, 0))

    def test_normalized_batch_conflict_rolls_back_all_subjects_routes_observations(self) -> None:
        with d_drive_tempdir() as temp:
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            with self.assertRaisesRegex(ObservatoryConflict, "subject_id"):
                ModelObservatory(store, ConflictingNormalizer()).ingest(
                    FixtureProvider(),
                    query(),
                )
            connection = store.connect()
            try:
                counts = tuple(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in (
                        "model_subjects",
                        "execution_routes",
                        "model_observations",
                    )
                )
            finally:
                connection.close()

        self.assertEqual(counts, (0, 0, 0))

    def test_ingest_rejects_snapshot_that_does_not_match_query_before_capture(self) -> None:
        class WrongProvider(FixtureProvider):
            def snapshot(self, requested) -> DiscoverySnapshot:
                del requested
                return DiscoverySnapshot.from_bytes(
                    "other_source",
                    OBSERVED_AT,
                    {"different": True},
                    canonical_json_bytes(json.loads(RAW)),
                    "fixture-v1",
                )

        with d_drive_tempdir() as temp:
            store = ObservatoryDatabase(
                temp / "observatory.sqlite3",
                temp / "snapshots",
            )
            with self.assertRaisesRegex(ValueError, "query"):
                ModelObservatory(store, FixtureNormalizer()).ingest(
                    WrongProvider(),
                    query(),
                )
            connection = store.connect()
            try:
                snapshot_count = connection.execute(
                    "SELECT COUNT(*) FROM source_snapshots"
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(snapshot_count, 0)


if __name__ == "__main__":
    unittest.main()
