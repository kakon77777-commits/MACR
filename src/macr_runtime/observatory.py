from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .canonical import canonical_json_bytes
from .discovery.base import (
    DiscoveryQuery,
    DiscoverySnapshot,
    ModelDiscoveryProvider,
    ModelNormalizer,
    ModelObservation,
)
from .observatory_db import ObservatoryDatabase


@dataclass(frozen=True)
class IngestReport:
    snapshot_id: str
    normalized_bytes_sha256: str
    observation_count: int
    subject_ids: tuple[str, ...]
    route_ids: tuple[str, ...]
    observation_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "normalized_bytes_sha256": self.normalized_bytes_sha256,
            "observation_count": self.observation_count,
            "subject_ids": list(self.subject_ids),
            "route_ids": list(self.route_ids),
            "observation_ids": list(self.observation_ids),
        }


class ModelObservatory:
    """Capture-first ingestion of untrusted discovery data."""

    def __init__(
        self,
        store: ObservatoryDatabase,
        normalizer: ModelNormalizer,
    ) -> None:
        if not isinstance(store, ObservatoryDatabase):
            raise ValueError("store must be an ObservatoryDatabase")
        if not isinstance(getattr(normalizer, "parser_version", None), str):
            raise ValueError("normalizer must declare parser_version")
        self.store = store
        self.normalizer = normalizer

    def ingest(
        self,
        provider: ModelDiscoveryProvider,
        query: DiscoveryQuery,
    ) -> IngestReport:
        if not isinstance(query, DiscoveryQuery):
            raise ValueError("query must be a DiscoveryQuery")
        if not isinstance(getattr(provider, "provider_id", None), str):
            raise ValueError("provider must declare provider_id")
        supplied = provider.snapshot(query)
        if not isinstance(supplied, DiscoverySnapshot):
            raise ValueError("provider must return a DiscoverySnapshot")
        if (
            supplied.source_id != query.source_id
            or supplied.request_shape_sha256 != query.request_shape_sha256
        ):
            raise ValueError("provider snapshot does not match discovery query")
        if supplied.parser_version != self.normalizer.parser_version:
            raise ValueError("snapshot parser version does not match normalizer")
        if len(supplied.raw_bytes) > query.max_response_bytes:
            raise ValueError("provider snapshot exceeds discovery query limit")

        snapshot_record = self.store.append_snapshot(
            supplied.storage_metadata(),
            raw_bytes=supplied.raw_bytes,
        )
        captured_bytes = self.store.read_snapshot_bytes(
            snapshot_record.snapshot_id
        )
        captured = DiscoverySnapshot.from_captured_record(
            snapshot_record,
            captured_bytes,
        )
        observations = tuple(self.normalizer.normalize(captured))
        if any(not isinstance(item, ModelObservation) for item in observations):
            raise ValueError("normalizer must return ModelObservation values")
        if any(item.snapshot_id != captured.snapshot_id for item in observations):
            raise ValueError("normalized observation does not bind captured snapshot")

        normalized_bytes = canonical_json_bytes(
            [item.to_dict() for item in observations]
        )
        normalized_digest = hashlib.sha256(normalized_bytes).hexdigest()
        subjects = tuple(item.model_subject for item in observations)
        routes = tuple(
            item.execution_route
            for item in observations
            if item.execution_route is not None
        )
        self.store.append_discovery_batch(
            subjects,
            routes,
            tuple(item.to_store_metadata() for item in observations),
        )

        return IngestReport(
            snapshot_id=captured.snapshot_id,
            normalized_bytes_sha256=normalized_digest,
            observation_count=len(observations),
            subject_ids=tuple(
                sorted({item.model_subject.subject_id for item in observations})
            ),
            route_ids=tuple(
                sorted(
                    {
                        item.execution_route.route_id
                        for item in observations
                        if item.execution_route is not None
                    }
                )
            ),
            observation_ids=tuple(
                sorted(item.observation_id for item in observations)
            ),
        )


__all__ = ["IngestReport", "ModelObservatory"]
