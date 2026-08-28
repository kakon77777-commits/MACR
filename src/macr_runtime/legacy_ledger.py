from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import EventStoreConflict, LegacyLedgerError, StoragePolicyError
from .event_store import SqliteEventStore, _canonical_json


class _DuplicateJsonKey(ValueError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _d_path(name: str, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute() or path.drive.upper() != "D:":
        raise StoragePolicyError(f"{name} must be absolute on D:")
    return path.absolute()


@dataclass(frozen=True)
class LegacyImportReport:
    source_sha256: str
    source_bytes: int
    expected_count: int | None
    observed_count: int
    valid_count: int
    corrupt_count: int
    duplicate_count: int
    imported_count: int
    already_imported_count: int
    complete: bool


@dataclass(frozen=True)
class _ValidLine:
    line_number: int
    event_id: str
    event_type: str
    observed_at: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class _CorruptLine:
    line_number: int
    raw_bytes: bytes
    error_code: str


@dataclass(frozen=True)
class _ExistingLegacyEvent:
    event_id: str
    event_type: str
    observed_at: str
    payload_json: str


class LegacyLedgerImporter:
    def __init__(
        self,
        database_path: str | Path,
        quarantine_root: str | Path,
    ) -> None:
        self.database_path = _d_path("legacy database path", database_path)
        self.quarantine_root = _d_path(
            "legacy quarantine root",
            quarantine_root,
        )

    def inspect(
        self,
        source: str | Path,
        *,
        expected_count: int | None = None,
    ) -> LegacyImportReport:
        source_path = _d_path("legacy source", source)
        raw = source_path.read_bytes()
        valid, corrupt, duplicate_count = self._scan(raw)
        observed_count = len(valid) + len(corrupt)
        complete = (
            not corrupt
            and duplicate_count == 0
            and (
                expected_count is None
                or expected_count == observed_count
            )
        )
        return LegacyImportReport(
            source_sha256=hashlib.sha256(raw).hexdigest(),
            source_bytes=len(raw),
            expected_count=expected_count,
            observed_count=observed_count,
            valid_count=len(valid),
            corrupt_count=len(corrupt),
            duplicate_count=duplicate_count,
            imported_count=0,
            already_imported_count=0,
            complete=complete,
        )

    def import_file(
        self,
        source: str | Path,
        *,
        expected_count: int | None = None,
    ) -> LegacyImportReport:
        source_path = _d_path("legacy source", source)
        raw = source_path.read_bytes()
        source_sha256 = hashlib.sha256(raw).hexdigest()
        valid, corrupt, duplicate_count = self._scan(raw)
        observed_count = len(valid) + len(corrupt)
        complete = (
            not corrupt
            and duplicate_count == 0
            and (
                expected_count is None
                or expected_count == observed_count
            )
        )
        event_store = SqliteEventStore(self.database_path)
        connection = event_store.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM legacy_sources WHERE source_sha256 = ?",
                (source_sha256,),
            ).fetchone()
            if existing is not None:
                if existing["expected_count"] != expected_count:
                    raise LegacyLedgerError(
                        "legacy source expected_count conflicts with prior import"
                    )
                connection.commit()
                return LegacyImportReport(
                    source_sha256=source_sha256,
                    source_bytes=existing["source_bytes"],
                    expected_count=existing["expected_count"],
                    observed_count=existing["observed_count"],
                    valid_count=existing["valid_count"],
                    corrupt_count=existing["corrupt_count"],
                    duplicate_count=existing["duplicate_count"],
                    imported_count=0,
                    already_imported_count=existing["imported_count"],
                    complete=bool(existing["complete"]),
                )
            existing_events = self._existing_legacy_events(connection)
            new_items: list[_ValidLine] = []
            already_imported_count = 0
            for item in valid:
                prior = existing_events.get(item.event_id)
                if prior is None:
                    new_items.append(item)
                    continue
                if (
                    prior.event_type != item.event_type
                    or prior.observed_at != item.observed_at
                    or prior.payload_json != _canonical_json(item.payload)
                ):
                    raise LegacyLedgerError(
                        "legacy event identity conflicts with prior import"
                    )
                already_imported_count += 1
            imported_at = datetime.now(timezone.utc).isoformat()
            connection.execute(
                """
                INSERT INTO legacy_sources(
                    source_sha256, source_bytes, expected_count,
                    observed_count, valid_count, corrupt_count,
                    duplicate_count, imported_count, complete, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_sha256,
                    len(raw),
                    expected_count,
                    observed_count,
                    len(valid),
                    len(corrupt),
                    duplicate_count,
                    len(valid),
                    int(complete),
                    imported_at,
                ),
            )
            for item in new_items:
                imported_id = hashlib.sha256(
                    (
                        f"{source_sha256}:{item.line_number}:"
                        f"{item.event_id}"
                    ).encode("utf-8")
                ).hexdigest()
                payload = {
                    **item.payload,
                    "legacy_event_id": item.event_id,
                    "legacy_source_sha256": source_sha256,
                    "legacy_source_line": item.line_number,
                }
                event_store._insert_event(
                    connection,
                    event_id=imported_id,
                    run_id=None,
                    event_type=item.event_type,
                    observed_at=item.observed_at,
                    payload_json=_canonical_json(payload),
                    source_sha256=source_sha256,
                    source_line=item.line_number,
                )
            for item in corrupt:
                connection.execute(
                    """
                    INSERT INTO legacy_quarantine(
                        source_sha256, line_number, raw_sha256,
                        raw_bytes, error_code
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        source_sha256,
                        item.line_number,
                        hashlib.sha256(item.raw_bytes).hexdigest(),
                        item.raw_bytes,
                        item.error_code,
                    ),
                )
            connection.commit()
        except (LegacyLedgerError, EventStoreConflict):
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise LegacyLedgerError(
                "legacy import conflicts with existing runtime evidence"
            ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        for item in corrupt:
            self._write_quarantine_file(source_sha256, item)
        return LegacyImportReport(
            source_sha256=source_sha256,
            source_bytes=len(raw),
            expected_count=expected_count,
            observed_count=observed_count,
            valid_count=len(valid),
            corrupt_count=len(corrupt),
            duplicate_count=duplicate_count,
            imported_count=len(new_items),
            already_imported_count=already_imported_count,
            complete=complete,
        )

    @staticmethod
    def _existing_legacy_events(
        connection: sqlite3.Connection,
    ) -> dict[str, _ExistingLegacyEvent]:
        rows = connection.execute(
            """
            SELECT event_id, event_type, observed_at, payload_json,
                   source_sha256, source_line
            FROM events
            WHERE source_sha256 IS NOT NULL
            ORDER BY sequence
            """
        ).fetchall()
        result: dict[str, _ExistingLegacyEvent] = {}
        for row in rows:
            try:
                payload = json.loads(
                    row["payload_json"],
                    object_pairs_hook=_strict_object,
                )
            except (_DuplicateJsonKey, json.JSONDecodeError) as exc:
                raise LegacyLedgerError(
                    "existing legacy event payload is invalid"
                ) from exc
            if not isinstance(payload, dict):
                raise LegacyLedgerError(
                    "existing legacy event payload is invalid"
                )
            legacy_event_id = payload.pop("legacy_event_id", None)
            legacy_source_sha256 = payload.pop("legacy_source_sha256", None)
            legacy_source_line = payload.pop("legacy_source_line", None)
            if (
                not isinstance(legacy_event_id, str)
                or not legacy_event_id.strip()
                or legacy_source_sha256 != row["source_sha256"]
                or legacy_source_line != row["source_line"]
            ):
                raise LegacyLedgerError(
                    "existing legacy event provenance is invalid"
                )
            candidate = _ExistingLegacyEvent(
                event_id=row["event_id"],
                event_type=row["event_type"],
                observed_at=row["observed_at"],
                payload_json=_canonical_json(payload),
            )
            if legacy_event_id in result:
                raise LegacyLedgerError(
                    "existing legacy event identity is duplicated"
                )
            result[legacy_event_id] = candidate
        return result

    def read_quarantine(
        self,
        source_sha256: str,
    ) -> tuple[dict[str, Any], ...]:
        event_store = SqliteEventStore(self.database_path)
        connection = event_store.database.connect()
        try:
            rows = connection.execute(
                """
                SELECT line_number, raw_sha256, raw_bytes, error_code
                FROM legacy_quarantine
                WHERE source_sha256 = ?
                ORDER BY line_number
                """,
                (source_sha256,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(dict(row) for row in rows)

    def _scan(
        self,
        raw: bytes,
    ) -> tuple[list[_ValidLine], list[_CorruptLine], int]:
        valid: list[_ValidLine] = []
        corrupt: list[_CorruptLine] = []
        seen: set[str] = set()
        duplicate_count = 0
        for line_number, line in enumerate(raw.split(b"\n"), start=1):
            if not line.strip():
                continue
            try:
                text = line.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                corrupt.append(
                    _CorruptLine(line_number, line, "invalid_utf8")
                )
                continue
            try:
                document = json.loads(text, object_pairs_hook=_strict_object)
            except _DuplicateJsonKey:
                corrupt.append(
                    _CorruptLine(line_number, line, "duplicate_json_key")
                )
                continue
            except json.JSONDecodeError:
                corrupt.append(
                    _CorruptLine(line_number, line, "invalid_json")
                )
                continue
            if not self._valid_shape(document):
                corrupt.append(
                    _CorruptLine(line_number, line, "invalid_shape")
                )
                continue
            try:
                _canonical_json(document["payload"])
            except ValueError:
                corrupt.append(
                    _CorruptLine(line_number, line, "forbidden_payload")
                )
                continue
            event_id = document["event_id"]
            if event_id in seen:
                duplicate_count += 1
            seen.add(event_id)
            valid.append(
                _ValidLine(
                    line_number=line_number,
                    event_id=event_id,
                    event_type=document["event_type"],
                    observed_at=document["observed_at"],
                    payload=dict(document["payload"]),
                )
            )
        return valid, corrupt, duplicate_count

    @staticmethod
    def _valid_shape(document: Any) -> bool:
        if not (
            isinstance(document, dict)
            and isinstance(document.get("event_id"), str)
            and bool(document["event_id"].strip())
            and isinstance(document.get("event_type"), str)
            and bool(document["event_type"].strip())
            and isinstance(document.get("observed_at"), str)
            and bool(document["observed_at"].strip())
            and isinstance(document.get("payload"), dict)
        ):
            return False
        try:
            observed_at = datetime.fromisoformat(document["observed_at"])
        except ValueError:
            return False
        return observed_at.tzinfo is not None

    def _write_quarantine_file(
        self,
        source_sha256: str,
        item: _CorruptLine,
    ) -> None:
        directory = self.quarantine_root / source_sha256
        directory.mkdir(parents=True, exist_ok=True)
        raw_sha256 = hashlib.sha256(item.raw_bytes).hexdigest()
        target = directory / f"{item.line_number:08d}-{raw_sha256}.bin"
        try:
            with target.open("xb") as handle:
                handle.write(item.raw_bytes)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            if target.read_bytes() != item.raw_bytes:
                raise LegacyLedgerError(
                    "legacy quarantine file conflicts with captured bytes"
                )
