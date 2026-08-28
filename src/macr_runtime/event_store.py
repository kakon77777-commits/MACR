from __future__ import annotations

import json
import re
import sqlite3
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import EventStoreConflict
from .runtime_db import RuntimeDatabase


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "answer",
        "api_key",
        "authorization",
        "authorization_header",
        "bearer_token",
        "body",
        "content",
        "credential",
        "path",
        "paths",
        "private_key",
        "prompt",
        "raw_response",
    }
)
_FORBIDDEN_PAYLOAD_KEY_SUFFIXES = (
    "_body",
    "_content",
    "_path",
    "_paths",
)
_LOCAL_PATH_MARKER = re.compile(
    r"(?i)(?<![a-z0-9])(?:[a-z]:[\\/]|\\\\[^\\/\s]+[\\/])"
)
_OPERATIONAL_PAYLOAD_KEYS = {
    "provider.dispatch_requested": frozenset(
        {
            "provider_id",
            "task_id",
            "task_type",
            "interaction_plane",
            "origin_host",
            "origin_identifier_kind",
            "origin_native_id",
            "authority_source_kind",
            "authority_source_id",
            "authority_digest",
            "authority_revision",
            "authority_epoch",
            "authority_scope_sha256",
            "policy_snapshot_sha256",
            "batch_id",
            "member_digest",
            "relay_is_authorship",
            "fencing_token",
        }
    ),
    "provider.candidate_completed": frozenset(
        {
            "provider_id",
            "task_id",
            "dispatch_event_id",
            "status",
            "model",
            "response_id",
            "finish_reason",
            "provider_state",
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "cached_tokens",
            "currency_cost_usd",
            "cost_kind",
            "pricing_basis_version",
            "duration_ms",
            "input_media_count",
            "input_media_bytes",
            "output_artifact_count",
            "output_artifact_bytes",
            "billing_state",
            "capture_state",
            "candidate_capture",
            "return_contract_state",
            "return_contract_reason",
            "failure_type",
            "authority_digest",
            "authority_revision",
            "authority_epoch",
        }
    ),
}
_CANDIDATE_CAPTURE_KEYS = frozenset(
    {
        "capture_id",
        "run_id",
        "provider_id",
        "answer_sha256",
        "answer_bytes",
        "task_digest",
        "approval_digest",
        "captured_at",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _non_empty(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _uuid4(name: str, value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a UUIDv4 string") from exc
    if parsed.version != 4 or str(parsed) != value.lower():
        raise ValueError(f"{name} must be a UUIDv4 string")
    return str(parsed)


def _validate_payload(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("event payload keys must be strings")
            normalized_key = re.sub(
                r"(?<=[a-z0-9])(?=[A-Z])",
                "_",
                key.strip(),
            ).lower().replace("-", "_")
            if (
                normalized_key in _FORBIDDEN_PAYLOAD_KEYS
                or normalized_key.endswith(_FORBIDDEN_PAYLOAD_KEY_SUFFIXES)
            ):
                raise ValueError(f"forbidden payload key: {key}")
            _validate_payload(child)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            _validate_payload(child)
        return
    if isinstance(value, bytes):
        raise ValueError("event payload may not contain bytes")
    if isinstance(value, str) and _LOCAL_PATH_MARKER.search(value):
        raise ValueError("event payload contains a path-like value")


def _validate_operational_payload(
    event_type: str,
    payload: Mapping[str, Any],
) -> None:
    allowed = _OPERATIONAL_PAYLOAD_KEYS[event_type]
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(
            f"event payload key is not allowed for {event_type}: {unknown[0]}"
        )
    if event_type == "provider.candidate_completed":
        capture = payload.get("candidate_capture")
        if isinstance(capture, Mapping):
            unknown_capture = sorted(set(capture) - _CANDIDATE_CAPTURE_KEYS)
            if unknown_capture:
                raise ValueError(
                    "candidate capture payload key is not allowed: "
                    f"{unknown_capture[0]}"
                )
    _validate_payload(payload)


def _canonical_json(payload: Mapping[str, Any]) -> str:
    _validate_payload(payload)
    try:
        return json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("event payload must be canonical JSON data") from exc


def _canonical_operational_json(
    event_type: str,
    payload: Mapping[str, Any],
) -> str:
    _validate_operational_payload(event_type, payload)
    return _canonical_json(payload)


class SqliteEventStore:
    def __init__(self, path: str | Path) -> None:
        self.database = RuntimeDatabase(path)

    @property
    def path(self) -> Path:
        return self.database.path

    def _insert_event(
        self,
        connection: sqlite3.Connection,
        *,
        event_id: str,
        run_id: str | None,
        event_type: str,
        observed_at: str,
        payload_json: str,
        source_sha256: str | None = None,
        source_line: int | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO events(
                event_id, run_id, event_type, observed_at, payload_json,
                source_sha256, source_line
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                run_id,
                event_type,
                observed_at,
                payload_json,
                source_sha256,
                source_line,
            ),
        )

    def start_run(
        self,
        *,
        run_id: str,
        dispatch_event_id: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        normalized_run = _uuid4("run_id", run_id)
        normalized_event = _uuid4("dispatch_event_id", dispatch_event_id)
        payload_json = _canonical_operational_json(
            "provider.dispatch_requested",
            payload,
        )
        observed_at = _utc_now()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO runs(
                    run_id, dispatch_event_id, state, started_at
                ) VALUES (?, ?, ?, ?)
                """,
                (normalized_run, normalized_event, "dispatched", observed_at),
            )
            self._insert_event(
                connection,
                event_id=normalized_event,
                run_id=normalized_run,
                event_type="provider.dispatch_requested",
                observed_at=observed_at,
                payload_json=payload_json,
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise EventStoreConflict("run dispatch already exists") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return {
            "event_id": normalized_event,
            "run_id": normalized_run,
            "event_type": "provider.dispatch_requested",
            "observed_at": observed_at,
            "payload": json.loads(payload_json),
        }

    def finish_run(
        self,
        *,
        run_id: str,
        terminal_event_id: str,
        state: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        normalized_run = _uuid4("run_id", run_id)
        normalized_event = _uuid4("terminal_event_id", terminal_event_id)
        normalized_state = _non_empty("terminal state", state)
        payload_json = _canonical_operational_json(
            "provider.candidate_completed",
            payload,
        )
        observed_at = _utc_now()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT terminal_event_id FROM runs WHERE run_id = ?",
                (normalized_run,),
            ).fetchone()
            if row is None:
                raise EventStoreConflict("terminal event has no dispatch run")
            if row["terminal_event_id"] is not None:
                raise EventStoreConflict("terminal event already exists for run")
            self._insert_event(
                connection,
                event_id=normalized_event,
                run_id=normalized_run,
                event_type="provider.candidate_completed",
                observed_at=observed_at,
                payload_json=payload_json,
            )
            connection.execute(
                """
                UPDATE runs
                SET terminal_event_id = ?, state = ?, terminal_at = ?
                WHERE run_id = ?
                """,
                (
                    normalized_event,
                    normalized_state,
                    observed_at,
                    normalized_run,
                ),
            )
            connection.commit()
        except EventStoreConflict:
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise EventStoreConflict("terminal event conflicts with ledger") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return {
            "event_id": normalized_event,
            "run_id": normalized_run,
            "event_type": "provider.candidate_completed",
            "observed_at": observed_at,
            "payload": json.loads(payload_json),
        }

    def append_standalone(
        self,
        event_type: str,
        event_id: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        normalized_type = _non_empty("event_type", event_type)
        normalized_id = _uuid4("event_id", event_id)
        payload_json = _canonical_json(payload)
        observed_at = _utc_now()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._insert_event(
                connection,
                event_id=normalized_id,
                run_id=None,
                event_type=normalized_type,
                observed_at=observed_at,
                payload_json=payload_json,
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise EventStoreConflict("event_id already exists") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return {
            "event_id": normalized_id,
            "run_id": None,
            "event_type": normalized_type,
            "observed_at": observed_at,
            "payload": json.loads(payload_json),
        }

    def append_imported(
        self,
        *,
        event_id: str,
        event_type: str,
        observed_at: str,
        payload: Mapping[str, Any],
        source_sha256: str,
        source_line: int,
    ) -> bool:
        normalized_id = _non_empty("event_id", event_id)
        normalized_type = _non_empty("event_type", event_type)
        normalized_observed = _non_empty("observed_at", observed_at)
        normalized_source = source_sha256.lower()
        if not _SHA256.fullmatch(normalized_source):
            raise ValueError("source_sha256 must be a SHA-256 hex digest")
        if (
            isinstance(source_line, bool)
            or not isinstance(source_line, int)
            or source_line < 1
        ):
            raise ValueError("source_line must be a positive integer")
        payload_json = _canonical_json(payload)
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT event_type, observed_at, payload_json, source_sha256,
                       source_line
                FROM events WHERE event_id = ?
                """,
                (normalized_id,),
            ).fetchone()
            if existing is not None:
                expected = (
                    normalized_type,
                    normalized_observed,
                    payload_json,
                    normalized_source,
                    source_line,
                )
                actual = (
                    existing["event_type"],
                    existing["observed_at"],
                    existing["payload_json"],
                    existing["source_sha256"],
                    existing["source_line"],
                )
                if actual != expected:
                    raise EventStoreConflict(
                        "event_id exists with different imported evidence"
                    )
                connection.commit()
                return False
            self._insert_event(
                connection,
                event_id=normalized_id,
                run_id=None,
                event_type=normalized_type,
                observed_at=normalized_observed,
                payload_json=payload_json,
                source_sha256=normalized_source,
                source_line=source_line,
            )
            connection.commit()
            return True
        except EventStoreConflict:
            connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise EventStoreConflict("event_id conflicts with imported evidence") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def read_run(self, run_id: str) -> dict[str, Any] | None:
        normalized_run = _uuid4("run_id", run_id)
        connection = self.database.connect()
        try:
            row = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?",
                (normalized_run,),
            ).fetchone()
        finally:
            connection.close()
        return dict(row) if row is not None else None

    def read_events(
        self,
        *,
        run_id: str | None = None,
        event_type: str | None = None,
    ) -> tuple[dict[str, Any], ...]:
        clauses: list[str] = []
        parameters: list[str] = []
        if run_id is not None:
            clauses.append("run_id = ?")
            parameters.append(_uuid4("run_id", run_id))
        if event_type is not None:
            clauses.append("event_type = ?")
            parameters.append(_non_empty("event_type", event_type))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        connection = self.database.connect()
        try:
            rows = connection.execute(
                """
                SELECT event_id, run_id, event_type, observed_at, payload_json,
                       source_sha256, source_line
                FROM events
                """
                + where
                + " ORDER BY sequence",
                tuple(parameters),
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            {
                "event_id": row["event_id"],
                "run_id": row["run_id"],
                "event_type": row["event_type"],
                "observed_at": row["observed_at"],
                "payload": json.loads(row["payload_json"]),
                "source_sha256": row["source_sha256"],
                "source_line": row["source_line"],
            }
            for row in rows
        )
