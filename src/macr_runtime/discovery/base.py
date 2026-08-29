from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

from ..canonical import aware_iso8601, canonical_json_bytes, sha256_id
from ..model_identity import ExecutionRouteIdentity, ModelSubject


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_REQUEST_BYTES = 64 * 1024
_MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
_FORBIDDEN_NORMALIZED_KEYS = frozenset(
    {
        "answer",
        "api_key",
        "authorization",
        "content",
        "description",
        "path",
        "prompt",
        "raw_body",
        "raw_bytes",
        "raw_response",
        "remote_body",
    }
)


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded ASCII identifier")
    return value


def _mapping(name: str, value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _normalize_key(key: str) -> str:
    separated_acronyms = re.sub(
        r"([A-Z]+)([A-Z][a-z])",
        r"\1_\2",
        key.strip(),
    )
    return re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])",
        "_",
        separated_acronyms,
    ).lower().replace("-", "_")


def _validate_normalized_payload(value: object) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("normalized payload keys must be strings")
            normalized = _normalize_key(key)
            if (
                normalized in _FORBIDDEN_NORMALIZED_KEYS
                or normalized.endswith(("_body", "_content", "_path", "_paths"))
            ):
                raise ValueError(f"normalized payload contains raw content key: {key}")
            _validate_normalized_payload(child)
    elif isinstance(value, list):
        for child in value:
            _validate_normalized_payload(child)


def _load_canonical_object(value: str) -> dict[str, Any]:
    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("canonical payload contains duplicate keys")
            result[key] = item
        return result

    try:
        parsed = json.loads(value, object_pairs_hook=reject_duplicate)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("canonical payload must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("canonical payload must be a JSON object")
    if canonical_json_bytes(parsed).decode("utf-8") != value:
        raise ValueError("canonical payload is not canonical JSON")
    _validate_normalized_payload(parsed)
    return parsed


@dataclass(frozen=True)
class DiscoveryQuery:
    source_id: str
    request_shape_sha256: str
    max_response_bytes: int
    _request_json: str = field(repr=False)

    def __post_init__(self) -> None:
        source_id = _identifier("source_id", self.source_id)
        request_shape_sha256 = _digest(
            "request_shape_sha256",
            self.request_shape_sha256,
        )
        if isinstance(self.max_response_bytes, bool) or not isinstance(
            self.max_response_bytes,
            int,
        ):
            raise ValueError("max_response_bytes must be an integer")
        if not 1 <= self.max_response_bytes <= _MAX_SNAPSHOT_BYTES:
            raise ValueError("max_response_bytes is out of range")
        request = _load_canonical_object(self._request_json)
        expected = sha256_id("discovery_request_shape_v1", request)
        if request_shape_sha256 != expected:
            raise ValueError("request_shape_sha256 does not match request shape")
        object.__setattr__(self, "source_id", source_id)

    @classmethod
    def create(
        cls,
        source_id: str,
        request_shape: Mapping[str, Any],
        *,
        max_response_bytes: int,
    ) -> "DiscoveryQuery":
        request = dict(_mapping("request_shape", request_shape))
        encoded = canonical_json_bytes(request)
        if len(encoded) > _MAX_REQUEST_BYTES:
            raise ValueError("request_shape exceeds 64 KiB")
        return cls(
            source_id=source_id,
            request_shape_sha256=sha256_id(
                "discovery_request_shape_v1",
                request,
            ),
            max_response_bytes=max_response_bytes,
            _request_json=encoded.decode("utf-8"),
        )

    def request_shape(self) -> dict[str, Any]:
        return _load_canonical_object(self._request_json)

    def public_metadata(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "request_shape_sha256": self.request_shape_sha256,
            "max_response_bytes": self.max_response_bytes,
        }


@dataclass(frozen=True)
class DiscoverySnapshot:
    snapshot_id: str
    source_id: str
    observed_at: str
    request_shape_sha256: str
    raw_bytes_sha256: str
    parser_version: str
    raw_bytes: bytes = field(repr=False)

    def __post_init__(self) -> None:
        snapshot_id = _digest("snapshot_id", self.snapshot_id)
        source_id = _identifier("source_id", self.source_id)
        observed_at = aware_iso8601("observed_at", self.observed_at)
        request_shape_sha256 = _digest(
            "request_shape_sha256",
            self.request_shape_sha256,
        )
        if not isinstance(self.raw_bytes, bytes):
            raise ValueError("raw_bytes must be bytes")
        if len(self.raw_bytes) > _MAX_SNAPSHOT_BYTES:
            raise ValueError("raw snapshot exceeds 64 MiB")
        raw_bytes_sha256 = _digest("raw_bytes_sha256", self.raw_bytes_sha256)
        if hashlib.sha256(self.raw_bytes).hexdigest() != raw_bytes_sha256:
            raise ValueError("raw_bytes_sha256 does not match raw bytes")
        parser_version = _identifier("parser_version", self.parser_version)
        expected = sha256_id(
            "source_snapshot_v1",
            {
                "source_id": source_id,
                "observed_at": observed_at,
                "request_shape_sha256": request_shape_sha256,
                "raw_bytes_sha256": raw_bytes_sha256,
                "parser_version": parser_version,
            },
        )
        if snapshot_id != expected:
            raise ValueError("snapshot_id does not match captured source identity")
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "parser_version", parser_version)

    @classmethod
    def from_bytes(
        cls,
        source_id: str,
        observed_at: str,
        request: DiscoveryQuery | Mapping[str, Any],
        raw_bytes: bytes,
        parser_version: str,
    ) -> "DiscoverySnapshot":
        if isinstance(request, DiscoveryQuery):
            if request.source_id != source_id:
                raise ValueError("snapshot source does not match query")
            request_digest = request.request_shape_sha256
            if not isinstance(raw_bytes, bytes) or (
                len(raw_bytes) > request.max_response_bytes
            ):
                raise ValueError("raw snapshot exceeds query response limit")
        else:
            request_digest = sha256_id(
                "discovery_request_shape_v1",
                dict(_mapping("request", request)),
            )
        if not isinstance(raw_bytes, bytes):
            raise ValueError("raw_bytes must be bytes")
        normalized_time = aware_iso8601("observed_at", observed_at)
        raw_digest = hashlib.sha256(raw_bytes).hexdigest()
        identity = {
            "source_id": _identifier("source_id", source_id),
            "observed_at": normalized_time,
            "request_shape_sha256": request_digest,
            "raw_bytes_sha256": raw_digest,
            "parser_version": _identifier("parser_version", parser_version),
        }
        return cls(
            snapshot_id=sha256_id("source_snapshot_v1", identity),
            raw_bytes=raw_bytes,
            **identity,
        )

    @classmethod
    def from_captured_record(
        cls,
        record: object,
        raw_bytes: bytes,
    ) -> "DiscoverySnapshot":
        return cls(
            snapshot_id=getattr(record, "snapshot_id"),
            source_id=getattr(record, "source_id"),
            observed_at=getattr(record, "observed_at"),
            request_shape_sha256=getattr(record, "request_shape_sha256"),
            raw_bytes_sha256=getattr(record, "raw_bytes_sha256"),
            parser_version=getattr(record, "parser_version"),
            raw_bytes=raw_bytes,
        )

    def storage_metadata(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "source_id": self.source_id,
            "observed_at": self.observed_at,
            "request_shape_sha256": self.request_shape_sha256,
            "raw_bytes_sha256": self.raw_bytes_sha256,
            "normalized_bytes_sha256": None,
            "parser_version": self.parser_version,
        }

    def public_metadata(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "source_id": self.source_id,
            "observed_at": self.observed_at,
            "request_shape_sha256": self.request_shape_sha256,
            "raw_bytes_sha256": self.raw_bytes_sha256,
            "parser_version": self.parser_version,
        }


@dataclass(frozen=True)
class ModelObservation:
    observation_id: str
    model_subject: ModelSubject
    execution_route: ExecutionRouteIdentity | None
    snapshot_id: str
    kind: str
    observed_at: str
    canonical_payload_json: str = field(repr=False)
    description_digest: str | None = None
    market_signal_kind: str | None = None

    def __post_init__(self) -> None:
        observation_id = _digest("observation_id", self.observation_id)
        if not isinstance(self.model_subject, ModelSubject):
            raise ValueError("model_subject must be a ModelSubject")
        if self.execution_route is not None:
            if not isinstance(self.execution_route, ExecutionRouteIdentity):
                raise ValueError("execution_route must be an ExecutionRouteIdentity")
            if self.execution_route.model_subject_id != self.model_subject.subject_id:
                raise ValueError("route does not bind the supplied model subject")
        snapshot_id = _digest("snapshot_id", self.snapshot_id)
        kind = _identifier("kind", self.kind)
        observed_at = aware_iso8601("observed_at", self.observed_at)
        payload = _load_canonical_object(self.canonical_payload_json)
        description_digest = self.description_digest
        if description_digest is not None:
            description_digest = _digest(
                "description_digest",
                description_digest,
            )
            if payload.get("description_digest") != description_digest:
                raise ValueError("description_digest does not match payload")
        market_signal_kind = self.market_signal_kind
        if market_signal_kind is not None:
            market_signal_kind = _identifier(
                "market_signal_kind",
                market_signal_kind,
            )
            if not market_signal_kind.startswith("external_"):
                raise ValueError("market_signal_kind must start with external_")
            if payload.get("market_signal_kind") != market_signal_kind:
                raise ValueError("market_signal_kind does not match payload")
        identity = {
            "subject_id": self.model_subject.subject_id,
            "route_id": (
                self.execution_route.route_id
                if self.execution_route is not None
                else None
            ),
            "snapshot_id": snapshot_id,
            "kind": kind,
            "canonical_json": self.canonical_payload_json,
            "observed_at": observed_at,
        }
        expected = sha256_id("model_observation_v1", identity)
        if observation_id != expected:
            raise ValueError("observation_id does not match normalized observation")
        object.__setattr__(self, "snapshot_id", snapshot_id)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "description_digest", description_digest)
        object.__setattr__(self, "market_signal_kind", market_signal_kind)

    @classmethod
    def create(
        cls,
        *,
        model_subject: ModelSubject,
        execution_route: ExecutionRouteIdentity | None,
        snapshot_id: str,
        kind: str,
        observed_at: str,
        payload: Mapping[str, Any],
        external_description: str | None = None,
        market_signal_kind: str | None = None,
    ) -> "ModelObservation":
        if not isinstance(model_subject, ModelSubject):
            raise ValueError("model_subject must be a ModelSubject")
        if execution_route is not None and (
            execution_route.model_subject_id != model_subject.subject_id
        ):
            raise ValueError("route does not bind the supplied model subject")
        normalized_payload = dict(_mapping("payload", payload))
        _validate_normalized_payload(normalized_payload)
        description_digest = None
        if external_description is not None:
            if not isinstance(external_description, str):
                raise ValueError("external_description must be text")
            if len(external_description.encode("utf-8")) > 1024 * 1024:
                raise ValueError("external_description is too long")
            description_digest = hashlib.sha256(
                external_description.encode("utf-8")
            ).hexdigest()
            normalized_payload["description_digest"] = description_digest
        if market_signal_kind is not None:
            market_signal_kind = _identifier(
                "market_signal_kind",
                market_signal_kind,
            )
            if not market_signal_kind.startswith("external_"):
                raise ValueError("market_signal_kind must start with external_")
            normalized_payload["market_signal_kind"] = market_signal_kind
        canonical_payload_json = canonical_json_bytes(
            normalized_payload
        ).decode("utf-8")
        normalized_time = aware_iso8601("observed_at", observed_at)
        identity = {
            "subject_id": model_subject.subject_id,
            "route_id": (
                execution_route.route_id if execution_route is not None else None
            ),
            "snapshot_id": _digest("snapshot_id", snapshot_id),
            "kind": _identifier("kind", kind),
            "canonical_json": canonical_payload_json,
            "observed_at": normalized_time,
        }
        return cls(
            observation_id=sha256_id("model_observation_v1", identity),
            model_subject=model_subject,
            execution_route=execution_route,
            snapshot_id=identity["snapshot_id"],
            kind=identity["kind"],
            observed_at=identity["observed_at"],
            canonical_payload_json=canonical_payload_json,
            description_digest=description_digest,
            market_signal_kind=market_signal_kind,
        )

    def canonical_payload(self) -> dict[str, Any]:
        return _load_canonical_object(self.canonical_payload_json)

    def to_store_metadata(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "subject_id": self.model_subject.subject_id,
            "route_id": (
                self.execution_route.route_id
                if self.execution_route is not None
                else None
            ),
            "snapshot_id": self.snapshot_id,
            "kind": self.kind,
            "observed_at": self.observed_at,
            "payload": self.canonical_payload(),
        }

    def public_metadata(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "subject_id": self.model_subject.subject_id,
            "route_id": (
                self.execution_route.route_id
                if self.execution_route is not None
                else None
            ),
            "snapshot_id": self.snapshot_id,
            "kind": self.kind,
            "observed_at": self.observed_at,
            "description_digest": self.description_digest,
            "market_signal_kind": self.market_signal_kind,
            "payload": self.canonical_payload(),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self.public_metadata(),
            "model_subject": {
                "subject_id": self.model_subject.subject_id,
                **self.model_subject.canonical_identity(),
                "identity_status": self.model_subject.identity_status.value,
                "first_seen_snapshot_id": (
                    self.model_subject.first_seen_snapshot_id
                ),
            },
            "execution_route": (
                {
                    "route_id": self.execution_route.route_id,
                    **self.execution_route.canonical_identity(),
                }
                if self.execution_route is not None
                else None
            ),
        }


@runtime_checkable
class ModelDiscoveryProvider(Protocol):
    provider_id: str

    def snapshot(self, query: DiscoveryQuery) -> DiscoverySnapshot: ...


@runtime_checkable
class ModelNormalizer(Protocol):
    parser_version: str

    def normalize(
        self,
        snapshot: DiscoverySnapshot,
    ) -> tuple[ModelObservation, ...]: ...
