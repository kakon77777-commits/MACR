from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import AccountingConflict, StoragePolicyError
from .execution import DispatchContext, RawProviderObservation


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_BILLING_STATES = frozenset(
    {
        "dispatched",
        "provider_reported",
        "estimated",
        "zero_local",
        "unknown_after_dispatch",
    }
)
_CANDIDATE_STATES = frozenset({"candidate_success", "candidate_failure"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _non_empty(name: str, value: str, *, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.strip()) > maximum
    ):
        raise ValueError(f"{name} must be a bounded non-empty string")
    return value.strip()


def _uuid4(name: str, value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a UUIDv4 string") from exc
    if parsed.version != 4 or str(parsed) != value.lower():
        raise ValueError(f"{name} must be a UUIDv4 string")
    return str(parsed)


def _uuid_any(name: str, value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a canonical UUID string") from exc
    if str(parsed) != value.lower():
        raise ValueError(f"{name} must be a canonical UUID string")
    return str(parsed)


def _digest(name: str, value: str) -> str:
    normalized = value.lower() if isinstance(value, str) else ""
    if not _SHA256.fullmatch(normalized):
        raise ValueError(f"{name} must be a SHA-256 hex digest")
    return normalized


def _money(name: str, value: float, *, signed: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized) or (not signed and normalized < 0):
        raise ValueError(f"{name} must be a finite number")
    return normalized


def _optional_money(name: str, value: float | None) -> float | None:
    return None if value is None else _money(name, value)


def _aware_time(name: str, value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat()


def _safe_finish_reason(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if re.fullmatch(r"[a-z0-9._-]{1,64}", normalized):
        return normalized
    return "other"


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


class AccountingStore:
    SCHEMA_VERSION = 1

    def __init__(
        self,
        path: str | Path,
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        candidate = Path(path)
        if not candidate.is_absolute() or candidate.drive.upper() != "D:":
            raise StoragePolicyError(
                "accounting database path must be absolute on D:"
            )
        self.path = candidate.absolute()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._now = now
        self._initialize()

    def _current_time(self) -> str:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("accounting clock must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            statements = (
                """CREATE TABLE IF NOT EXISTS accounting_schema_meta (
                    component TEXT PRIMARY KEY,
                    version INTEGER NOT NULL
                )""",
                """CREATE TABLE IF NOT EXISTS invocations (
                    run_id TEXT PRIMARY KEY,
                    origin_host TEXT NOT NULL,
                    origin_identifier_kind TEXT NOT NULL,
                    origin_native_id TEXT NOT NULL,
                    interaction_plane TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    model TEXT,
                    returned_model TEXT,
                    dispatched_at TEXT NOT NULL,
                    terminal_at TEXT,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    reasoning_tokens INTEGER,
                    cached_tokens INTEGER,
                    duration_ms INTEGER,
                    estimate_usd REAL,
                    currency_cost_usd REAL,
                    cost_kind TEXT,
                    pricing_basis_version TEXT,
                    finish_reason TEXT,
                    billing_state TEXT NOT NULL,
                    candidate_status TEXT,
                    soft_warning INTEGER NOT NULL DEFAULT 0,
                    policy_snapshot_sha256 TEXT NOT NULL
                )""",
                """CREATE TABLE IF NOT EXISTS provider_accounts (
                    account_id TEXT PRIMARY KEY,
                    provider_id TEXT NOT NULL,
                    funding_kind TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    UNIQUE(provider_id, funding_kind, currency)
                )""",
                """CREATE TABLE IF NOT EXISTS accounting_entries (
                    entry_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL
                        REFERENCES provider_accounts(account_id),
                    run_id TEXT REFERENCES invocations(run_id),
                    entry_kind TEXT NOT NULL,
                    amount REAL NOT NULL,
                    source_kind TEXT NOT NULL,
                    source_digest TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    UNIQUE(account_id, entry_kind, source_kind, source_digest)
                )""",
                """CREATE TABLE IF NOT EXISTS accounting_outbox (
                    outbox_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE REFERENCES invocations(run_id),
                    schema_version INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    synced_at TEXT
                )""",
                """CREATE TABLE IF NOT EXISTS billing_reconciliations (
                    reconciliation_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES invocations(run_id),
                    authority_source TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL,
                    tax REAL,
                    exchange_rate REAL,
                    credit REAL,
                    refund REAL,
                    payment_status TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    observed_at TEXT NOT NULL
                )""",
            )
            for statement in statements:
                connection.execute(statement)
            row = connection.execute(
                """
                SELECT version FROM accounting_schema_meta
                WHERE component = 'accounting'
                """
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO accounting_schema_meta(component, version)
                    VALUES ('accounting', ?)
                    """,
                    (self.SCHEMA_VERSION,),
                )
            elif row["version"] != self.SCHEMA_VERSION:
                raise AccountingConflict(
                    "accounting database schema version is unsupported"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def record_dispatch(
        self,
        run_id: str,
        context: DispatchContext,
        *,
        provider_id: str,
        model: str | None,
        estimate_usd: float | None,
        soft_warning: bool = False,
    ) -> bool:
        run = _uuid4("run_id", run_id)
        if not isinstance(context, DispatchContext) or context.run_id != run:
            raise ValueError("dispatch context must match run_id")
        provider = _non_empty("provider_id", provider_id)
        requested_model = (
            _non_empty("model", model, maximum=512)
            if model is not None
            else None
        )
        estimate = _optional_money("estimate_usd", estimate_usd)
        if not isinstance(soft_warning, bool):
            raise ValueError("soft_warning must be boolean")
        dispatched_at = self._current_time()
        values = (
            context.origin.host,
            context.origin.identifier_kind,
            context.origin.native_id,
            context.plane.value,
            provider,
            requested_model,
            estimate,
            int(soft_warning),
            context.policy_snapshot_sha256,
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM invocations WHERE run_id = ?",
                (run,),
            ).fetchone()
            if existing is not None:
                actual = (
                    existing["origin_host"],
                    existing["origin_identifier_kind"],
                    existing["origin_native_id"],
                    existing["interaction_plane"],
                    existing["provider_id"],
                    existing["model"],
                    existing["estimate_usd"],
                    existing["soft_warning"],
                    existing["policy_snapshot_sha256"],
                )
                if actual != values:
                    raise AccountingConflict(
                        "accounting dispatch conflicts with existing run"
                    )
                connection.commit()
                return False
            connection.execute(
                """
                INSERT INTO invocations(
                    run_id, origin_host, origin_identifier_kind,
                    origin_native_id, interaction_plane, provider_id,
                    model, dispatched_at, estimate_usd, billing_state,
                    soft_warning, policy_snapshot_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'dispatched', ?, ?)
                """,
                (run, *values[:6], dispatched_at, values[6], values[7], values[8]),
            )
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def record_observation(
        self,
        run_id: str,
        observation: RawProviderObservation,
    ) -> None:
        run = _uuid4("run_id", run_id)
        if not isinstance(observation, RawProviderObservation):
            raise ValueError("observation must be a RawProviderObservation")
        billing_state = self._observation_billing_state(observation)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM invocations WHERE run_id = ?",
                (run,),
            ).fetchone()
            if row is None:
                raise AccountingConflict("accounting observation has no dispatch")
            if row["terminal_at"] is not None:
                raise AccountingConflict(
                    "accounting observation cannot follow terminal state"
                )
            if row["provider_id"] != observation.provider_id:
                raise AccountingConflict(
                    "accounting observation provider does not match dispatch"
                )
            observed_values = (
                observation.model,
                observation.usage.input_tokens,
                observation.usage.output_tokens,
                observation.usage.reasoning_tokens,
                observation.usage.cached_tokens,
                observation.duration_ms,
                observation.currency_cost_usd,
                observation.cost_kind,
                observation.pricing_basis_version,
                _safe_finish_reason(observation.finish_reason),
                billing_state,
            )
            if row["billing_state"] != "dispatched":
                existing_values = (
                    row["returned_model"],
                    row["input_tokens"],
                    row["output_tokens"],
                    row["reasoning_tokens"],
                    row["cached_tokens"],
                    row["duration_ms"],
                    row["currency_cost_usd"],
                    row["cost_kind"],
                    row["pricing_basis_version"],
                    row["finish_reason"],
                    row["billing_state"],
                )
                if existing_values == observed_values:
                    connection.commit()
                    return
                raise AccountingConflict(
                    "accounting observation conflicts with existing evidence"
                )
            connection.execute(
                """
                UPDATE invocations
                SET returned_model = ?, input_tokens = ?, output_tokens = ?,
                    reasoning_tokens = ?, cached_tokens = ?, duration_ms = ?,
                    currency_cost_usd = ?, cost_kind = ?,
                    pricing_basis_version = ?, finish_reason = ?,
                    billing_state = ?
                WHERE run_id = ?
                """,
                (*observed_values, run),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def record_terminal(
        self,
        run_id: str,
        *,
        candidate_status: str,
        billing_state: str,
    ) -> None:
        run = _uuid4("run_id", run_id)
        if candidate_status not in _CANDIDATE_STATES:
            raise ValueError("candidate_status is invalid")
        if billing_state not in _BILLING_STATES - {"dispatched"}:
            raise ValueError("billing_state is invalid for terminal state")
        terminal_at = self._current_time()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM invocations WHERE run_id = ?",
                (run,),
            ).fetchone()
            if row is None:
                raise AccountingConflict("accounting terminal has no dispatch")
            if row["terminal_at"] is not None:
                if (
                    row["candidate_status"] == candidate_status
                    and row["billing_state"] == billing_state
                ):
                    connection.commit()
                    return
                raise AccountingConflict(
                    "accounting terminal conflicts with existing state"
                )
            if billing_state != "unknown_after_dispatch" and row["currency_cost_usd"] is None:
                raise AccountingConflict(
                    "known billing state requires an observed cost"
                )
            connection.execute(
                """
                UPDATE invocations
                SET terminal_at = ?, candidate_status = ?, billing_state = ?
                WHERE run_id = ?
                """,
                (terminal_at, candidate_status, billing_state, run),
            )
            updated = connection.execute(
                "SELECT * FROM invocations WHERE run_id = ?",
                (run,),
            ).fetchone()
            payload = self._outbox_payload(updated)
            payload_json = _canonical_json(payload)
            payload_sha256 = hashlib.sha256(
                payload_json.encode("utf-8")
            ).hexdigest()
            connection.execute(
                """
                INSERT INTO accounting_outbox(
                    outbox_id, run_id, schema_version, payload_json,
                    payload_sha256, state, created_at, synced_at
                ) VALUES (?, ?, 1, ?, ?, 'pending', ?, NULL)
                """,
                (
                    str(uuid.uuid4()),
                    run,
                    payload_json,
                    payload_sha256,
                    terminal_at,
                ),
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise AccountingConflict(
                "accounting terminal outbox conflicts with existing state"
            ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def read_invocation(self, run_id: str) -> dict[str, Any] | None:
        run = _uuid4("run_id", run_id)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM invocations WHERE run_id = ?",
                (run,),
            ).fetchone()
        finally:
            connection.close()
        return dict(row) if row is not None else None

    def pending_outbox(self) -> tuple[dict[str, Any], ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT outbox_id, run_id, schema_version, payload_json,
                       payload_sha256, state, created_at
                FROM accounting_outbox
                WHERE state = 'pending'
                ORDER BY created_at, outbox_id
                """
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            {
                **{key: row[key] for key in row.keys() if key != "payload_json"},
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        )

    def upsert_provider_account(
        self,
        *,
        provider_id: str,
        funding_kind: str,
        currency: str,
        display_name: str,
    ) -> str:
        provider = _non_empty("provider_id", provider_id)
        funding = _non_empty("funding_kind", funding_kind)
        normalized_currency = _non_empty("currency", currency, maximum=16).upper()
        display = _non_empty("display_name", display_name)
        stable = f"{provider}\x1f{funding}\x1f{normalized_currency}"
        account_id = str(uuid.uuid5(uuid.NAMESPACE_URL, stable))
        opened_at = self._current_time()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM provider_accounts WHERE account_id = ?",
                (account_id,),
            ).fetchone()
            if row is not None and (
                row["provider_id"] != provider
                or row["funding_kind"] != funding
                or row["currency"] != normalized_currency
                or row["display_name"] != display
            ):
                raise AccountingConflict(
                    "provider account conflicts with existing definition"
                )
            if row is None:
                connection.execute(
                    """
                    INSERT INTO provider_accounts(
                        account_id, provider_id, funding_kind,
                        currency, display_name, opened_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        account_id,
                        provider,
                        funding,
                        normalized_currency,
                        display,
                        opened_at,
                    ),
                )
            connection.commit()
            return account_id
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def append_accounting_entry(
        self,
        account_id: str,
        *,
        run_id: str | None,
        entry_kind: str,
        amount: float,
        source_kind: str,
        source_digest: str,
    ) -> str:
        account = _uuid_any("account_id", account_id)
        run = _uuid4("run_id", run_id) if run_id is not None else None
        kind = _non_empty("entry_kind", entry_kind)
        normalized_amount = _money("amount", amount, signed=True)
        source = _non_empty("source_kind", source_kind)
        digest = _digest("source_digest", source_digest)
        if kind == "credit" and normalized_amount < 0:
            raise ValueError("credit amount must be non-negative")
        if kind == "debit" and normalized_amount > 0:
            raise ValueError("debit amount must be non-positive")
        entry_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{account}\x1f{kind}\x1f{source}\x1f{digest}",
            )
        )
        observed_at = self._current_time()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM accounting_entries WHERE entry_id = ?",
                (entry_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["run_id"] != run
                    or existing["amount"] != normalized_amount
                ):
                    raise AccountingConflict(
                        "accounting entry conflicts with existing evidence"
                    )
                connection.commit()
                return entry_id
            connection.execute(
                """
                INSERT INTO accounting_entries(
                    entry_id, account_id, run_id, entry_kind,
                    amount, source_kind, source_digest, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    account,
                    run,
                    kind,
                    normalized_amount,
                    source,
                    digest,
                    observed_at,
                ),
            )
            connection.commit()
            return entry_id
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise AccountingConflict(
                "accounting entry references a missing account or run"
            ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def account_summary(self) -> dict[str, dict[str, float]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT accounts.currency, accounts.account_id,
                       COALESCE(SUM(entries.amount), 0.0) AS balance
                FROM provider_accounts AS accounts
                LEFT JOIN accounting_entries AS entries
                  ON entries.account_id = accounts.account_id
                GROUP BY accounts.currency, accounts.account_id
                ORDER BY accounts.currency, accounts.account_id
                """
            ).fetchall()
        finally:
            connection.close()
        summary: dict[str, dict[str, float]] = {}
        for row in rows:
            summary.setdefault(row["currency"], {})[row["account_id"]] = row[
                "balance"
            ]
        return summary

    def append_reconciliation(
        self,
        *,
        reconciliation_id: str,
        run_id: str,
        authority_source: str,
        amount: float,
        currency: str,
        payment_status: str,
        payload_sha256: str,
        observed_at: str,
        tax: float | None = None,
        exchange_rate: float | None = None,
        credit: float | None = None,
        refund: float | None = None,
    ) -> bool:
        reconciliation = _uuid4("reconciliation_id", reconciliation_id)
        run = _uuid4("run_id", run_id)
        authority = _non_empty("authority_source", authority_source)
        normalized_amount = _money("amount", amount, signed=True)
        normalized_currency = _non_empty("currency", currency, maximum=16).upper()
        status = _non_empty("payment_status", payment_status)
        digest = _digest("payload_sha256", payload_sha256)
        observed = _aware_time("observed_at", observed_at)
        optional_values = (
            _optional_money("tax", tax),
            _optional_money("exchange_rate", exchange_rate),
            _optional_money("credit", credit),
            _optional_money("refund", refund),
        )
        expected = (
            run,
            authority,
            normalized_amount,
            normalized_currency,
            *optional_values,
            status,
            digest,
            observed,
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT run_id, authority_source, amount, currency,
                       tax, exchange_rate, credit, refund, payment_status,
                       payload_sha256, observed_at
                FROM billing_reconciliations
                WHERE reconciliation_id = ?
                """,
                (reconciliation,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) != expected:
                    raise AccountingConflict(
                        "reconciliation conflicts with existing evidence"
                    )
                connection.commit()
                return False
            connection.execute(
                """
                INSERT INTO billing_reconciliations(
                    reconciliation_id, run_id, authority_source,
                    amount, currency, tax, exchange_rate, credit,
                    refund, payment_status, payload_sha256, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (reconciliation, *expected),
            )
            connection.commit()
            return True
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise AccountingConflict(
                "reconciliation references a missing invocation"
            ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _observation_billing_state(
        observation: RawProviderObservation,
    ) -> str:
        if observation.currency_cost_usd is None:
            return "unknown_after_dispatch"
        if observation.cost_kind in {"provider_reported", "actual"}:
            return "provider_reported"
        if observation.cost_kind == "zero_local":
            return "zero_local"
        return "estimated"

    @staticmethod
    def _outbox_payload(row: sqlite3.Row) -> dict[str, Any]:
        keys = (
            "run_id",
            "origin_host",
            "interaction_plane",
            "provider_id",
            "model",
            "returned_model",
            "dispatched_at",
            "terminal_at",
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "cached_tokens",
            "duration_ms",
            "estimate_usd",
            "currency_cost_usd",
            "cost_kind",
            "pricing_basis_version",
            "finish_reason",
            "billing_state",
            "candidate_status",
            "soft_warning",
            "policy_snapshot_sha256",
        )
        return {key: row[key] for key in keys}
