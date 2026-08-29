from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .canonical import aware_iso8601, canonical_json_bytes, sha256_id
from .errors import ObservatoryConflict, StoragePolicyError
from .model_identity import ExecutionRouteIdentity, ModelSubject


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SNAPSHOT_NAME = re.compile(r"^[0-9a-f]{64}\.bin$")
_MAX_RAW_BYTES = 64 * 1024 * 1024
_MAX_CANONICAL_BYTES = 64 * 1024
_RAW_CONTENT_KEYS = frozenset(
    {
        "answer",
        "api_key",
        "authorization",
        "content",
        "description",
        "local_path",
        "path",
        "prompt",
        "raw_body",
        "raw_bytes",
        "raw_response",
        "remote_body",
        "source_path",
    }
)
_RAW_CONTENT_KEY_SUFFIXES = ("_body", "_content", "_path", "_paths")
_EXPECTED_COLUMNS = {
    "source_snapshots": (
        "snapshot_id",
        "source_id",
        "observed_at",
        "request_shape_sha256",
        "raw_bytes_sha256",
        "normalized_bytes_sha256",
        "parser_version",
        "raw_relative_name",
    ),
    "model_subjects": (
        "subject_id",
        "canonical_json",
        "first_seen_snapshot_id",
    ),
    "execution_routes": (
        "route_id",
        "model_subject_id",
        "canonical_json",
    ),
    "model_observations": (
        "observation_id",
        "subject_id",
        "route_id",
        "snapshot_id",
        "kind",
        "canonical_json",
        "observed_at",
    ),
    "evidence_items": (
        "evidence_id",
        "qualification_key",
        "kind",
        "subject_digest",
        "canonical_json",
        "observed_at",
    ),
    "qualification_decisions": (
        "decision_id",
        "qualification_key",
        "state",
        "evidence_set_digest",
        "canonical_json",
        "decided_at",
    ),
    "qualification_invalidations": (
        "invalidation_id",
        "qualification_key",
        "reason_code",
        "source_id",
        "invalidated_at",
    ),
}


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a 64-character lowercase SHA-256 digest")
    return value


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded ASCII identifier")
    return value


def _mapping(name: str, value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _validate_no_raw_content(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("canonical payload keys must be strings")
            separated_acronyms = re.sub(
                r"([A-Z]+)([A-Z][a-z])",
                r"\1_\2",
                key.strip(),
            )
            normalized = re.sub(
                r"(?<=[a-z0-9])(?=[A-Z])",
                "_",
                separated_acronyms,
            ).lower().replace("-", "_")
            if (
                normalized in _RAW_CONTENT_KEYS
                or normalized.endswith(_RAW_CONTENT_KEY_SUFFIXES)
            ):
                raise ValueError(f"canonical payload contains raw content key: {key}")
            _validate_no_raw_content(item)
    elif isinstance(value, list):
        for item in value:
            _validate_no_raw_content(item)


def _canonical_payload(value: object) -> str:
    payload = _mapping("payload", value)
    _validate_no_raw_content(payload)
    encoded = canonical_json_bytes(dict(payload))
    if len(encoded) > _MAX_CANONICAL_BYTES:
        raise ValueError("canonical payload exceeds 64 KiB")
    return encoded.decode("utf-8")


def _validate_d_path(name: str, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute() or path.drive.upper() != "D:":
        raise StoragePolicyError(f"{name} must be absolute on D:")
    return path.absolute()


def _is_reparse(path: Path) -> bool:
    return path.is_symlink() or (
        hasattr(os.path, "isjunction") and os.path.isjunction(path)
    )


def _check_existing_ancestry(path: Path) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current = current / component
        if _is_reparse(current):
            raise StoragePolicyError(
                "observatory path ancestry may not contain a reparse point"
            )
        if not current.exists():
            return


def _ensure_directory(path: Path) -> None:
    _check_existing_ancestry(path)
    path.mkdir(parents=True, exist_ok=True)
    _check_existing_ancestry(path)
    if not path.is_dir():
        raise StoragePolicyError("observatory directory is unavailable")


def _write_once(target: Path, data: bytes) -> None:
    _check_existing_ancestry(target)
    if target.exists():
        if (
            not target.is_file()
            or _is_reparse(target)
            or target.read_bytes() != data
        ):
            raise ObservatoryConflict("private snapshot conflicts with existing bytes")
        return
    temporary = target.with_name(f".{target.name}.{uuid.uuid4()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if (
                not target.is_file()
                or _is_reparse(target)
                or target.read_bytes() != data
            ):
                raise ObservatoryConflict(
                    "private snapshot conflicts with existing bytes"
                )
        if (
            not target.is_file()
            or _is_reparse(target)
            or target.read_bytes() != data
        ):
            raise ObservatoryConflict("private snapshot readback mismatch")
    finally:
        temporary.unlink(missing_ok=True)


def _expected_or_conflict(
    data: Mapping[str, Any],
    key: str,
    namespace: str,
    canonical: Mapping[str, Any],
) -> str:
    expected = sha256_id(namespace, dict(canonical))
    supplied = data.get(key)
    if supplied is not None and supplied != expected:
        raise ObservatoryConflict(f"{key} conflicts with canonical record")
    return expected


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: str
    source_id: str
    observed_at: str
    request_shape_sha256: str
    raw_bytes_sha256: str
    normalized_bytes_sha256: str | None
    parser_version: str
    raw_relative_name: str


@dataclass(frozen=True)
class ModelSubjectRecord:
    subject_id: str
    canonical_json: str
    first_seen_snapshot_id: str


@dataclass(frozen=True)
class ExecutionRouteRecord:
    route_id: str
    model_subject_id: str
    canonical_json: str


@dataclass(frozen=True)
class ObservationRecord:
    observation_id: str
    subject_id: str
    route_id: str | None
    snapshot_id: str
    kind: str
    canonical_json: str
    observed_at: str


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    qualification_key: str
    kind: str
    subject_digest: str
    canonical_json: str
    observed_at: str


@dataclass(frozen=True)
class QualificationDecisionRecord:
    decision_id: str
    qualification_key: str
    state: str
    evidence_set_digest: str
    canonical_json: str
    decided_at: str


@dataclass(frozen=True)
class QualificationInvalidationRecord:
    invalidation_id: str
    qualification_key: str
    reason_code: str
    source_id: str
    invalidated_at: str


class ObservatoryDatabase:
    """Append-only evidence store with create-once private source snapshots."""

    SCHEMA_VERSION = 1
    _BOOTSTRAP_TIMEOUT_S = 30.0
    _BOOTSTRAP_RETRY_INTERVAL_S = 0.01

    def __init__(
        self,
        path: str | Path,
        snapshot_root: str | Path | None = None,
    ) -> None:
        self.path = _validate_d_path("observatory database path", path)
        self.snapshot_root = _validate_d_path(
            "observatory snapshot root",
            snapshot_root
            if snapshot_root is not None
            else self.path.parent / "snapshots",
        )
        _ensure_directory(self.path.parent)
        _ensure_directory(self.snapshot_root)
        self._initialize()

    def _open_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @staticmethod
    def _is_transient_lock(exc: sqlite3.OperationalError) -> bool:
        code = getattr(exc, "sqlite_errorcode", None)
        if code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            return True
        detail = str(exc).lower()
        return "locked" in detail or "busy" in detail

    def _bootstrap_connection(self) -> sqlite3.Connection:
        deadline = time.monotonic() + self._BOOTSTRAP_TIMEOUT_S
        while True:
            connection = self._open_connection()
            try:
                current_mode = connection.execute(
                    "PRAGMA journal_mode"
                ).fetchone()[0]
                if current_mode.lower() != "wal":
                    selected_mode = connection.execute(
                        "PRAGMA journal_mode = WAL"
                    ).fetchone()[0]
                    if selected_mode.lower() != "wal":
                        raise ObservatoryConflict(
                            "observatory database could not enable WAL journal mode"
                        )
                connection.execute("PRAGMA synchronous = FULL")
                return connection
            except sqlite3.OperationalError as exc:
                connection.close()
                remaining = deadline - time.monotonic()
                if not self._is_transient_lock(exc) or remaining <= 0:
                    raise
                time.sleep(min(self._BOOTSTRAP_RETRY_INTERVAL_S, remaining))
            except Exception:
                connection.close()
                raise

    def connect(self) -> sqlite3.Connection:
        connection = self._open_connection()
        try:
            mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if mode.lower() != "wal" or version != self.SCHEMA_VERSION:
                raise ObservatoryConflict(
                    "observatory database schema or journal mode is invalid"
                )
            connection.execute("PRAGMA synchronous = FULL")
            return connection
        except Exception:
            connection.close()
            raise

    def _initialize(self) -> None:
        connection = self._bootstrap_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute("PRAGMA user_version").fetchone()[0]
            if current not in {0, self.SCHEMA_VERSION}:
                raise ObservatoryConflict(
                    "observatory database schema version is unsupported"
                )
            statements = (
                """CREATE TABLE IF NOT EXISTS source_snapshots(
                    snapshot_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    request_shape_sha256 TEXT NOT NULL,
                    raw_bytes_sha256 TEXT NOT NULL,
                    normalized_bytes_sha256 TEXT,
                    parser_version TEXT NOT NULL,
                    raw_relative_name TEXT NOT NULL UNIQUE
                )""",
                """CREATE TABLE IF NOT EXISTS model_subjects(
                    subject_id TEXT PRIMARY KEY,
                    canonical_json TEXT NOT NULL UNIQUE,
                    first_seen_snapshot_id TEXT NOT NULL
                        REFERENCES source_snapshots(snapshot_id)
                )""",
                """CREATE TABLE IF NOT EXISTS execution_routes(
                    route_id TEXT PRIMARY KEY,
                    model_subject_id TEXT NOT NULL
                        REFERENCES model_subjects(subject_id),
                    canonical_json TEXT NOT NULL UNIQUE
                )""",
                """CREATE TABLE IF NOT EXISTS model_observations(
                    observation_id TEXT PRIMARY KEY,
                    subject_id TEXT NOT NULL REFERENCES model_subjects(subject_id),
                    route_id TEXT REFERENCES execution_routes(route_id),
                    snapshot_id TEXT NOT NULL REFERENCES source_snapshots(snapshot_id),
                    kind TEXT NOT NULL,
                    canonical_json TEXT NOT NULL,
                    observed_at TEXT NOT NULL
                )""",
                """CREATE TABLE IF NOT EXISTS evidence_items(
                    evidence_id TEXT PRIMARY KEY,
                    qualification_key TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    subject_digest TEXT NOT NULL,
                    canonical_json TEXT NOT NULL,
                    observed_at TEXT NOT NULL
                )""",
                """CREATE TABLE IF NOT EXISTS qualification_decisions(
                    decision_id TEXT PRIMARY KEY,
                    qualification_key TEXT NOT NULL,
                    state TEXT NOT NULL,
                    evidence_set_digest TEXT NOT NULL,
                    canonical_json TEXT NOT NULL,
                    decided_at TEXT NOT NULL
                )""",
                """CREATE TABLE IF NOT EXISTS qualification_invalidations(
                    invalidation_id TEXT PRIMARY KEY,
                    qualification_key TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    invalidated_at TEXT NOT NULL
                )""",
            )
            for statement in statements:
                connection.execute(statement)
            for table, expected_columns in _EXPECTED_COLUMNS.items():
                actual_columns = tuple(
                    row["name"]
                    for row in connection.execute(
                        f"PRAGMA table_info({table})"
                    ).fetchall()
                )
                if actual_columns != expected_columns:
                    raise ObservatoryConflict(
                        f"observatory table schema conflicts: {table}"
                    )
            connection.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def append_snapshot(
        self,
        metadata: Mapping[str, Any],
        *,
        raw_bytes: bytes,
    ) -> SnapshotRecord:
        data = _mapping("snapshot metadata", metadata)
        if not isinstance(raw_bytes, bytes):
            raise ValueError("raw_bytes must be bytes")
        if len(raw_bytes) > _MAX_RAW_BYTES:
            raise ValueError("raw snapshot exceeds 64 MiB")
        source_id = _identifier("source_id", data.get("source_id"))
        observed_at = aware_iso8601("observed_at", data.get("observed_at"))
        request_shape = _digest(
            "request_shape_sha256",
            data.get("request_shape_sha256"),
        )
        raw_digest = hashlib.sha256(raw_bytes).hexdigest()
        supplied_raw_digest = data.get("raw_bytes_sha256")
        if supplied_raw_digest is not None and supplied_raw_digest != raw_digest:
            raise ObservatoryConflict("raw_bytes_sha256 conflicts with raw bytes")
        normalized = data.get("normalized_bytes_sha256")
        if normalized is not None:
            normalized = _digest("normalized_bytes_sha256", normalized)
        parser_version = _identifier("parser_version", data.get("parser_version"))
        identity = {
            "source_id": source_id,
            "observed_at": observed_at,
            "request_shape_sha256": request_shape,
            "raw_bytes_sha256": raw_digest,
            "parser_version": parser_version,
        }
        snapshot_id = _expected_or_conflict(
            data,
            "snapshot_id",
            "source_snapshot_v1",
            identity,
        )
        relative_name = f"{snapshot_id}.bin"
        record = SnapshotRecord(
            snapshot_id=snapshot_id,
            source_id=source_id,
            observed_at=observed_at,
            request_shape_sha256=request_shape,
            raw_bytes_sha256=raw_digest,
            normalized_bytes_sha256=normalized,
            parser_version=parser_version,
            raw_relative_name=relative_name,
        )
        _write_once(self.snapshot_root / relative_name, raw_bytes)
        self._append_row(
            "source_snapshots",
            "snapshot_id",
            snapshot_id,
            record.__dict__,
        )
        return record

    def append_model_subject(self, subject: ModelSubject) -> ModelSubjectRecord:
        record = self._subject_record(subject)
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            persisted = self._append_subject_connection(connection, record)
            connection.commit()
            return persisted
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise ObservatoryConflict(
                "subject_id conflicts with observatory references"
            ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _subject_record(subject: ModelSubject) -> ModelSubjectRecord:
        if not isinstance(subject, ModelSubject):
            raise ValueError("subject must be a ModelSubject")
        canonical = {
            **subject.canonical_identity(),
            "identity_status": subject.identity_status.value,
        }
        record = ModelSubjectRecord(
            subject_id=subject.subject_id,
            canonical_json=canonical_json_bytes(canonical).decode("utf-8"),
            first_seen_snapshot_id=subject.first_seen_snapshot_id,
        )
        return record

    def append_execution_route(
        self,
        route: ExecutionRouteIdentity,
    ) -> ExecutionRouteRecord:
        record = self._route_record(route)
        self._append_row(
            "execution_routes",
            "route_id",
            record.route_id,
            record.__dict__,
        )
        return record

    @staticmethod
    def _route_record(route: ExecutionRouteIdentity) -> ExecutionRouteRecord:
        if not isinstance(route, ExecutionRouteIdentity):
            raise ValueError("route must be an ExecutionRouteIdentity")
        record = ExecutionRouteRecord(
            route_id=route.route_id,
            model_subject_id=route.model_subject_id,
            canonical_json=canonical_json_bytes(
                route.canonical_identity()
            ).decode("utf-8"),
        )
        return record

    def append_observation(
        self,
        metadata: Mapping[str, Any],
    ) -> ObservationRecord:
        record = self._observation_record(metadata)
        if record.route_id is not None:
            route_row = self._read_one(
                "execution_routes",
                "route_id",
                record.route_id,
            )
            if (
                route_row is None
                or route_row["model_subject_id"] != record.subject_id
            ):
                raise ObservatoryConflict(
                    "observation route does not bind the supplied model subject"
                )
        self._append_row(
            "model_observations",
            "observation_id",
            record.observation_id,
            record.__dict__,
        )
        return record

    @staticmethod
    def _observation_record(
        metadata: Mapping[str, Any],
    ) -> ObservationRecord:
        data = _mapping("observation", metadata)
        subject_id = _digest("subject_id", data.get("subject_id"))
        route_id = data.get("route_id")
        if route_id is not None:
            route_id = _digest("route_id", route_id)
        snapshot_id = _digest("snapshot_id", data.get("snapshot_id"))
        kind = _identifier("kind", data.get("kind"))
        observed_at = aware_iso8601("observed_at", data.get("observed_at"))
        canonical_json = _canonical_payload(data.get("payload"))
        identity = {
            "subject_id": subject_id,
            "route_id": route_id,
            "snapshot_id": snapshot_id,
            "kind": kind,
            "canonical_json": canonical_json,
            "observed_at": observed_at,
        }
        observation_id = _expected_or_conflict(
            data,
            "observation_id",
            "model_observation_v1",
            identity,
        )
        record = ObservationRecord(observation_id=observation_id, **identity)
        return record

    def append_discovery_batch(
        self,
        subjects: Iterable[ModelSubject],
        routes: Iterable[ExecutionRouteIdentity],
        observations: Iterable[Mapping[str, Any]],
    ) -> tuple[
        tuple[ModelSubjectRecord, ...],
        tuple[ExecutionRouteRecord, ...],
        tuple[ObservationRecord, ...],
    ]:
        if isinstance(subjects, (str, bytes)):
            raise ValueError("subjects must be ModelSubject values")
        if isinstance(routes, (str, bytes)):
            raise ValueError("routes must be ExecutionRouteIdentity values")
        if isinstance(observations, (str, bytes)):
            raise ValueError("observations must be metadata objects")
        subject_records = tuple(self._subject_record(item) for item in subjects)
        route_records = tuple(self._route_record(item) for item in routes)
        observation_records = tuple(
            self._observation_record(item) for item in observations
        )

        connection = self.connect()
        persisted_subjects: list[ModelSubjectRecord] = []
        try:
            connection.execute("BEGIN IMMEDIATE")
            for record in subject_records:
                persisted_subjects.append(
                    self._append_subject_connection(connection, record)
                )
            for record in route_records:
                self._append_row_connection(
                    connection,
                    "execution_routes",
                    "route_id",
                    record.route_id,
                    record.__dict__,
                )
            for record in observation_records:
                if record.route_id is not None:
                    route_row = connection.execute(
                        "SELECT model_subject_id FROM execution_routes "
                        "WHERE route_id = ?",
                        (record.route_id,),
                    ).fetchone()
                    if (
                        route_row is None
                        or route_row["model_subject_id"] != record.subject_id
                    ):
                        raise ObservatoryConflict(
                            "observation route does not bind the supplied model subject"
                        )
                self._append_row_connection(
                    connection,
                    "model_observations",
                    "observation_id",
                    record.observation_id,
                    record.__dict__,
                )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise ObservatoryConflict(
                "discovery batch conflicts with observatory references"
            ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return tuple(persisted_subjects), route_records, observation_records

    def append_evidence(self, metadata: Mapping[str, Any]) -> EvidenceRecord:
        record = self._evidence_record(metadata)
        self._append_row(
            "evidence_items",
            "evidence_id",
            record.evidence_id,
            record.__dict__,
        )
        return record

    @staticmethod
    def _evidence_record(metadata: Mapping[str, Any]) -> EvidenceRecord:
        data = _mapping("evidence", metadata)
        qualification_key = _digest(
            "qualification_key",
            data.get("qualification_key"),
        )
        kind = _identifier("kind", data.get("kind"))
        subject_digest = _digest(
            "subject_digest",
            data.get("subject_digest"),
        )
        observed_at = aware_iso8601("observed_at", data.get("observed_at"))
        canonical_json = _canonical_payload(data.get("payload"))
        identity = {
            "qualification_key": qualification_key,
            "kind": kind,
            "subject_digest": subject_digest,
            "canonical_json": canonical_json,
            "observed_at": observed_at,
        }
        evidence_id = _expected_or_conflict(
            data,
            "evidence_id",
            "evidence_item_v1",
            identity,
        )
        record = EvidenceRecord(evidence_id=evidence_id, **identity)
        return record

    def prepare_evidence(
        self,
        metadata: Mapping[str, Any],
    ) -> EvidenceRecord:
        return self._evidence_record(metadata)

    def append_evidence_batch(
        self,
        entries: Iterable[Mapping[str, Any]],
    ) -> tuple[EvidenceRecord, ...]:
        records, _ = self.append_evidence_batch_with_status(entries)
        return records

    def append_evidence_batch_with_status(
        self,
        entries: Iterable[Mapping[str, Any]],
    ) -> tuple[tuple[EvidenceRecord, ...], tuple[bool, ...]]:
        if isinstance(entries, (str, bytes)):
            raise ValueError("evidence entries must be metadata objects")
        records = tuple(self._evidence_record(item) for item in entries)
        connection = self.connect()
        inserted: list[bool] = []
        try:
            connection.execute("BEGIN IMMEDIATE")
            for record in records:
                inserted.append(
                    self._append_row_connection(
                        connection,
                        "evidence_items",
                        "evidence_id",
                        record.evidence_id,
                        record.__dict__,
                    )
                )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise ObservatoryConflict(
                "evidence batch conflicts with observatory references"
            ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return records, tuple(inserted)

    def append_qualification_decision(
        self,
        metadata: Mapping[str, Any],
    ) -> QualificationDecisionRecord:
        data = _mapping("qualification decision", metadata)
        qualification_key = _digest(
            "qualification_key",
            data.get("qualification_key"),
        )
        state = _identifier("state", data.get("state"))
        evidence_set_digest = _digest(
            "evidence_set_digest",
            data.get("evidence_set_digest"),
        )
        decided_at = aware_iso8601("decided_at", data.get("decided_at"))
        canonical_json = _canonical_payload(data.get("payload"))
        identity = {
            "qualification_key": qualification_key,
            "state": state,
            "evidence_set_digest": evidence_set_digest,
            "canonical_json": canonical_json,
            "decided_at": decided_at,
        }
        decision_id = _expected_or_conflict(
            data,
            "decision_id",
            "qualification_decision_v1",
            identity,
        )
        record = QualificationDecisionRecord(decision_id=decision_id, **identity)
        self._append_row(
            "qualification_decisions",
            "decision_id",
            decision_id,
            record.__dict__,
        )
        return record

    def append_qualification_invalidation(
        self,
        metadata: Mapping[str, Any],
    ) -> QualificationInvalidationRecord:
        data = _mapping("qualification invalidation", metadata)
        identity = {
            "qualification_key": _digest(
                "qualification_key",
                data.get("qualification_key"),
            ),
            "reason_code": _identifier(
                "reason_code",
                data.get("reason_code"),
            ),
            "source_id": _identifier("source_id", data.get("source_id")),
            "invalidated_at": aware_iso8601(
                "invalidated_at",
                data.get("invalidated_at"),
            ),
        }
        invalidation_id = _expected_or_conflict(
            data,
            "invalidation_id",
            "qualification_invalidation_v1",
            identity,
        )
        record = QualificationInvalidationRecord(
            invalidation_id=invalidation_id,
            **identity,
        )
        self._append_row(
            "qualification_invalidations",
            "invalidation_id",
            invalidation_id,
            record.__dict__,
        )
        return record

    def read_snapshot(self, snapshot_id: str) -> SnapshotRecord | None:
        snapshot_id = _digest("snapshot_id", snapshot_id)
        row = self._read_one("source_snapshots", "snapshot_id", snapshot_id)
        return SnapshotRecord(**dict(row)) if row is not None else None

    def read_snapshot_bytes(self, snapshot_id: str) -> bytes:
        record = self.read_snapshot(snapshot_id)
        if record is None:
            raise ObservatoryConflict("snapshot does not exist")
        if not _SNAPSHOT_NAME.fullmatch(record.raw_relative_name):
            raise ObservatoryConflict("snapshot relative name is invalid")
        target = self.snapshot_root / record.raw_relative_name
        _check_existing_ancestry(target)
        if not target.is_file() or _is_reparse(target):
            raise ObservatoryConflict("private snapshot is missing or invalid")
        data = target.read_bytes()
        if hashlib.sha256(data).hexdigest() != record.raw_bytes_sha256:
            raise ObservatoryConflict("private snapshot hash mismatch")
        return data

    def read_model_subject(self, subject_id: str) -> ModelSubjectRecord | None:
        subject_id = _digest("subject_id", subject_id)
        row = self._read_one("model_subjects", "subject_id", subject_id)
        return ModelSubjectRecord(**dict(row)) if row is not None else None

    def read_execution_route(
        self,
        route_id: str,
    ) -> ExecutionRouteRecord | None:
        route_id = _digest("route_id", route_id)
        row = self._read_one("execution_routes", "route_id", route_id)
        return ExecutionRouteRecord(**dict(row)) if row is not None else None

    def read_routes_for_subject(
        self,
        subject_id: str,
    ) -> tuple[ExecutionRouteRecord, ...]:
        rows = self._read_many(
            "execution_routes",
            "model_subject_id",
            _digest("subject_id", subject_id),
            "route_id",
        )
        return tuple(ExecutionRouteRecord(**dict(row)) for row in rows)

    def read_observations(
        self,
        subject_id: str,
    ) -> tuple[ObservationRecord, ...]:
        rows = self._read_many(
            "model_observations",
            "subject_id",
            _digest("subject_id", subject_id),
            "observed_at, observation_id",
        )
        return tuple(ObservationRecord(**dict(row)) for row in rows)

    def read_evidence(
        self,
        qualification_key: str,
    ) -> tuple[EvidenceRecord, ...]:
        rows = self._read_many(
            "evidence_items",
            "qualification_key",
            _digest("qualification_key", qualification_key),
            "observed_at, evidence_id",
        )
        return tuple(EvidenceRecord(**dict(row)) for row in rows)

    def read_evidence_for_subject(
        self,
        subject_id: str,
    ) -> tuple[EvidenceRecord, ...]:
        rows = self._read_many(
            "evidence_items",
            "subject_digest",
            _digest("subject_id", subject_id),
            "observed_at, evidence_id",
        )
        return tuple(EvidenceRecord(**dict(row)) for row in rows)

    def evidence_exists(self, evidence_id: str) -> bool:
        evidence_id = _digest("evidence_id", evidence_id)
        return (
            self._read_one("evidence_items", "evidence_id", evidence_id)
            is not None
        )

    def evidence_count(self) -> int:
        return self._table_count("evidence_items")

    def qualification_decision_count(self) -> int:
        return self._table_count("qualification_decisions")

    def read_qualification_decisions(
        self,
        qualification_key: str,
    ) -> tuple[QualificationDecisionRecord, ...]:
        rows = self._read_many(
            "qualification_decisions",
            "qualification_key",
            _digest("qualification_key", qualification_key),
            "decided_at, decision_id",
        )
        return tuple(QualificationDecisionRecord(**dict(row)) for row in rows)

    def read_qualification_invalidations(
        self,
        qualification_key: str,
    ) -> tuple[QualificationInvalidationRecord, ...]:
        rows = self._read_many(
            "qualification_invalidations",
            "qualification_key",
            _digest("qualification_key", qualification_key),
            "invalidated_at, invalidation_id",
        )
        return tuple(
            QualificationInvalidationRecord(**dict(row)) for row in rows
        )

    def _append_row(
        self,
        table: str,
        id_column: str,
        record_id: str,
        values: Mapping[str, Any],
    ) -> None:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._append_row_connection(
                connection,
                table,
                id_column,
                record_id,
                values,
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise ObservatoryConflict(
                f"{id_column} conflicts with observatory references"
            ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _append_row_connection(
        connection: sqlite3.Connection,
        table: str,
        id_column: str,
        record_id: str,
        values: Mapping[str, Any],
    ) -> bool:
        columns = tuple(values.keys())
        existing = connection.execute(
            f"SELECT * FROM {table} WHERE {id_column} = ?",
            (record_id,),
        ).fetchone()
        if existing is None:
            placeholders = ", ".join("?" for _ in columns)
            connection.execute(
                f"INSERT INTO {table}({', '.join(columns)}) "
                f"VALUES ({placeholders})",
                tuple(values[column] for column in columns),
            )
            return True
        elif any(existing[column] != values[column] for column in columns):
            raise ObservatoryConflict(
                f"{id_column} conflicts with append-only observatory state"
            )
        return False

    @staticmethod
    def _append_subject_connection(
        connection: sqlite3.Connection,
        record: ModelSubjectRecord,
    ) -> ModelSubjectRecord:
        existing = connection.execute(
            "SELECT * FROM model_subjects WHERE subject_id = ?",
            (record.subject_id,),
        ).fetchone()
        if existing is None:
            connection.execute(
                "INSERT INTO model_subjects("
                "subject_id, canonical_json, first_seen_snapshot_id"
                ") VALUES (?, ?, ?)",
                (
                    record.subject_id,
                    record.canonical_json,
                    record.first_seen_snapshot_id,
                ),
            )
            return record
        if existing["canonical_json"] != record.canonical_json:
            raise ObservatoryConflict(
                "subject_id conflicts with append-only observatory state"
            )
        return ModelSubjectRecord(**dict(existing))

    def _read_one(
        self,
        table: str,
        column: str,
        value: str,
    ) -> sqlite3.Row | None:
        connection = self.connect()
        try:
            return connection.execute(
                f"SELECT * FROM {table} WHERE {column} = ?",
                (value,),
            ).fetchone()
        finally:
            connection.close()

    def _read_many(
        self,
        table: str,
        column: str,
        value: str,
        order_by: str,
    ) -> tuple[sqlite3.Row, ...]:
        connection = self.connect()
        try:
            return tuple(
                connection.execute(
                    f"SELECT * FROM {table} WHERE {column} = ? "
                    f"ORDER BY {order_by}",
                    (value,),
                ).fetchall()
            )
        finally:
            connection.close()

    def _table_count(self, table: str) -> int:
        connection = self.connect()
        try:
            return int(
                connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
            )
        finally:
            connection.close()


__all__ = [
    "EvidenceRecord",
    "ExecutionRouteRecord",
    "ModelSubjectRecord",
    "ObservationRecord",
    "ObservatoryConflict",
    "ObservatoryDatabase",
    "QualificationDecisionRecord",
    "QualificationInvalidationRecord",
    "SnapshotRecord",
]
