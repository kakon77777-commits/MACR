from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
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


class CostClass(str, Enum):
    DISCOVERY_COST = "discovery_cost"
    PROBE_COST = "probe_cost"
    PRODUCTION_EXECUTION_COST = "production_execution_cost"
    VERIFICATION_COST = "verification_cost"
    INTEGRATION_COST = "integration_cost"
    HUMAN_CORRECTION_OBSERVATION = "human_correction_observation"


@dataclass(frozen=True)
class PlanCostRecord:
    cost_id: str
    plan_digest: str
    run_id: str | None
    role_digest: str | None
    route_id: str | None
    cost_class: CostClass
    amount_usd: float
    cost_kind: str
    pricing_basis_digest: str
    idempotency_key: str
    observed_at: str


@dataclass(frozen=True)
class BudgetAccountingDecision:
    plan_digest: str
    total_cost_usd: float
    allowed: bool
    warning: str | None


@dataclass(frozen=True)
class AccountingStatusSnapshot:
    known_cost_usd: float
    unknown_after_dispatch_count: int
    unsettled_count: int
    legacy_pre_tier_count: int
    pending_invocation_outbox_count: int
    pending_plan_cost_outbox_count: int
    pending_bill_observation_outbox_count: int
    by_provider_billing_state: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "known_cost_usd": self.known_cost_usd,
            "unknown_after_dispatch_count": self.unknown_after_dispatch_count,
            "unsettled_count": self.unsettled_count,
            "legacy_pre_tier_count": self.legacy_pre_tier_count,
            "pending_invocation_outbox_count": (
                self.pending_invocation_outbox_count
            ),
            "pending_plan_cost_outbox_count": (
                self.pending_plan_cost_outbox_count
            ),
            "pending_bill_observation_outbox_count": (
                self.pending_bill_observation_outbox_count
            ),
            "by_provider_billing_state": [
                dict(item) for item in self.by_provider_billing_state
            ],
        }


def _status_snapshot_from_connection(
    connection: sqlite3.Connection,
    *,
    has_tier_column: bool,
) -> AccountingStatusSnapshot:
    provider_rows = connection.execute(
        """SELECT provider_id, billing_state, COUNT(*) AS run_count,
                  COALESCE(SUM(currency_cost_usd), 0.0) AS known_cost_usd
        FROM invocations
        GROUP BY provider_id, billing_state
        ORDER BY provider_id, billing_state"""
    ).fetchall()
    legacy_expression = (
        "COALESCE(SUM(CASE WHEN provider_tier_binding_digest IS NULL "
        "THEN 1 ELSE 0 END), 0)"
        if has_tier_column
        else "COUNT(*)"
    )
    totals = connection.execute(
        f"""SELECT
            COALESCE(SUM(currency_cost_usd), 0.0) AS known_cost_usd,
            COALESCE(SUM(CASE WHEN billing_state = 'unknown_after_dispatch'
                              THEN 1 ELSE 0 END), 0)
                AS unknown_after_dispatch_count,
            COALESCE(SUM(CASE WHEN terminal_at IS NULL THEN 1 ELSE 0 END), 0)
                AS unsettled_count,
            {legacy_expression} AS legacy_pre_tier_count
        FROM invocations"""
    ).fetchone()
    outboxes = connection.execute(
        """SELECT
            (SELECT COUNT(*) FROM accounting_outbox
             WHERE state = 'pending') AS invocation_count,
            (SELECT COUNT(*) FROM plan_cost_outbox
             WHERE state = 'pending') AS plan_cost_count,
            (SELECT COUNT(*) FROM bill_observation_outbox
             WHERE state = 'pending') AS bill_count"""
    ).fetchone()
    return AccountingStatusSnapshot(
        known_cost_usd=float(totals["known_cost_usd"]),
        unknown_after_dispatch_count=int(
            totals["unknown_after_dispatch_count"]
        ),
        unsettled_count=int(totals["unsettled_count"]),
        legacy_pre_tier_count=int(totals["legacy_pre_tier_count"]),
        pending_invocation_outbox_count=int(outboxes["invocation_count"]),
        pending_plan_cost_outbox_count=int(outboxes["plan_cost_count"]),
        pending_bill_observation_outbox_count=int(outboxes["bill_count"]),
        by_provider_billing_state=tuple(
            {
                "provider_id": row["provider_id"],
                "billing_state": row["billing_state"],
                "run_count": int(row["run_count"]),
                "known_cost_usd": float(row["known_cost_usd"]),
            }
            for row in provider_rows
        ),
    )


def _empty_status_snapshot() -> AccountingStatusSnapshot:
    return AccountingStatusSnapshot(
        known_cost_usd=0.0,
        unknown_after_dispatch_count=0,
        unsettled_count=0,
        legacy_pre_tier_count=0,
        pending_invocation_outbox_count=0,
        pending_plan_cost_outbox_count=0,
        pending_bill_observation_outbox_count=0,
        by_provider_billing_state=(),
    )


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


def _safe_id(name: str, value: str, *, maximum: int = 256) -> str:
    normalized = _non_empty(name, value, maximum=maximum)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", normalized):
        raise ValueError(f"{name} must be a safe identifier")
    return normalized


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
    SCHEMA_VERSION = 3

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
                    policy_snapshot_sha256 TEXT NOT NULL,
                    provider_tier_binding_digest TEXT,
                    failure_code TEXT,
                    failure_stage TEXT
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
                """CREATE TABLE IF NOT EXISTS plan_costs (
                    cost_id TEXT PRIMARY KEY,
                    plan_digest TEXT NOT NULL,
                    run_id TEXT REFERENCES invocations(run_id),
                    role_digest TEXT,
                    route_id TEXT,
                    cost_class TEXT NOT NULL,
                    amount_usd REAL NOT NULL,
                    cost_kind TEXT NOT NULL,
                    pricing_basis_digest TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    UNIQUE(plan_digest, idempotency_key)
                )""",
                """CREATE TABLE IF NOT EXISTS plan_cost_outbox (
                    outbox_id TEXT PRIMARY KEY,
                    cost_id TEXT NOT NULL UNIQUE REFERENCES plan_costs(cost_id),
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )""",
                """CREATE TABLE IF NOT EXISTS bill_observations (
                    observation_id TEXT PRIMARY KEY,
                    provider_id TEXT NOT NULL,
                    provider_account_id TEXT NOT NULL
                        REFERENCES provider_accounts(account_id),
                    funding_source_id TEXT NOT NULL,
                    invoice_item_id TEXT NOT NULL,
                    plan_digest TEXT,
                    run_id TEXT REFERENCES invocations(run_id),
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL,
                    tax REAL,
                    credit REAL,
                    payment_status TEXT NOT NULL,
                    source_digest TEXT NOT NULL UNIQUE,
                    metadata_digest TEXT NOT NULL,
                    observed_at TEXT NOT NULL
                )""",
                """CREATE TABLE IF NOT EXISTS bill_observation_outbox (
                    outbox_id TEXT PRIMARY KEY,
                    observation_id TEXT NOT NULL UNIQUE
                        REFERENCES bill_observations(observation_id),
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL
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
                row = {"version": self.SCHEMA_VERSION}
            elif row["version"] == 1:
                connection.execute(
                    """UPDATE accounting_schema_meta SET version = ?
                    WHERE component = 'accounting'""",
                    (2,),
                )
                row = {"version": 2}
            if row["version"] == 2:
                columns = {
                    item["name"]
                    for item in connection.execute(
                        "PRAGMA table_info(invocations)"
                    ).fetchall()
                }
                additions = (
                    ("provider_tier_binding_digest", "TEXT"),
                    ("failure_code", "TEXT"),
                    ("failure_stage", "TEXT"),
                )
                for name, declaration in additions:
                    if name not in columns:
                        connection.execute(
                            f"ALTER TABLE invocations ADD COLUMN {name} {declaration}"
                        )
                connection.execute(
                    """UPDATE accounting_schema_meta SET version = ?
                    WHERE component = 'accounting'""",
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

    def record_plan_cost(
        self,
        plan_digest: str,
        run_id: str | None,
        cost_class: CostClass | str,
        amount_usd: float,
        cost_kind: str,
        pricing_basis_digest: str,
        *,
        role_digest: str | None = None,
        route_id: str | None = None,
        idempotency_key: str,
    ) -> PlanCostRecord:
        plan = _digest("plan_digest", plan_digest)
        run = _uuid4("run_id", run_id) if run_id is not None else None
        try:
            normalized_class = (
                cost_class
                if isinstance(cost_class, CostClass)
                else CostClass(cost_class)
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("cost_class is invalid") from exc
        amount = _money("amount_usd", amount_usd)
        kind = _safe_id("cost_kind", cost_kind)
        basis = _digest("pricing_basis_digest", pricing_basis_digest)
        role = _digest("role_digest", role_digest) if role_digest is not None else None
        route = _digest("route_id", route_id) if route_id is not None else None
        idempotency = _safe_id(
            "idempotency_key",
            idempotency_key,
            maximum=512,
        )
        identity = {
            "plan_digest": plan,
            "run_id": run,
            "role_digest": role,
            "route_id": route,
            "cost_class": normalized_class.value,
            "amount_usd": amount,
            "cost_kind": kind,
            "pricing_basis_digest": basis,
            "idempotency_key": idempotency,
        }
        cost_id = hashlib.sha256(
            _canonical_json(identity).encode("utf-8")
        ).hexdigest()
        observed_at = self._current_time()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM plan_costs WHERE plan_digest = ? "
                "AND idempotency_key = ?",
                (plan, idempotency),
            ).fetchone()
            if existing is not None:
                expected = (
                    cost_id,
                    run,
                    role,
                    route,
                    normalized_class.value,
                    amount,
                    kind,
                    basis,
                )
                actual = (
                    existing["cost_id"],
                    existing["run_id"],
                    existing["role_digest"],
                    existing["route_id"],
                    existing["cost_class"],
                    existing["amount_usd"],
                    existing["cost_kind"],
                    existing["pricing_basis_digest"],
                )
                if actual != expected:
                    raise AccountingConflict(
                        "plan cost conflicts with existing idempotency key"
                    )
                connection.commit()
                return self._plan_cost_from_row(existing)
            connection.execute(
                """INSERT INTO plan_costs(
                    cost_id, plan_digest, run_id, role_digest, route_id,
                    cost_class, amount_usd, cost_kind,
                    pricing_basis_digest, idempotency_key, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    cost_id,
                    plan,
                    run,
                    role,
                    route,
                    normalized_class.value,
                    amount,
                    kind,
                    basis,
                    idempotency,
                    observed_at,
                ),
            )
            payload = {"cost_id": cost_id, **identity, "observed_at": observed_at}
            payload_json = _canonical_json(payload)
            payload_digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
            connection.execute(
                """INSERT INTO plan_cost_outbox(
                    outbox_id, cost_id, payload_json, payload_sha256,
                    state, created_at
                ) VALUES (?, ?, ?, ?, 'pending', ?)""",
                (
                    str(uuid.uuid4()),
                    cost_id,
                    payload_json,
                    payload_digest,
                    observed_at,
                ),
            )
            connection.commit()
            return PlanCostRecord(
                cost_id=cost_id,
                plan_digest=plan,
                run_id=run,
                role_digest=role,
                route_id=route,
                cost_class=normalized_class,
                amount_usd=amount,
                cost_kind=kind,
                pricing_basis_digest=basis,
                idempotency_key=idempotency,
                observed_at=observed_at,
            )
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise AccountingConflict(
                "plan cost references missing invocation or conflicts"
            ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def plan_costs(self, plan_digest: str) -> dict[str, float]:
        plan = _digest("plan_digest", plan_digest)
        connection = self._connect()
        try:
            rows = connection.execute(
                """SELECT cost_class, SUM(amount_usd) AS amount
                FROM plan_costs WHERE plan_digest = ?
                GROUP BY cost_class ORDER BY cost_class""",
                (plan,),
            ).fetchall()
        finally:
            connection.close()
        return {row["cost_class"]: float(row["amount"]) for row in rows}

    def evaluate_budget(
        self,
        plan_digest: str,
        profile: object,
        *,
        warning_threshold_usd: float | None,
    ) -> BudgetAccountingDecision:
        from .planning_contracts import BudgetMode, OperatorPolicyProfile

        plan = _digest("plan_digest", plan_digest)
        if not isinstance(profile, OperatorPolicyProfile):
            raise ValueError("profile must be an OperatorPolicyProfile")
        threshold = (
            _money("warning_threshold_usd", warning_threshold_usd)
            if warning_threshold_usd is not None
            else None
        )
        total = sum(self.plan_costs(plan).values())
        exceeded = threshold is not None and total > threshold
        allowed = not (
            profile.budget_mode is BudgetMode.ENFORCE and exceeded
        )
        warning = (
            "plan cost exceeds configured warning threshold"
            if exceeded and profile.budget_mode in {BudgetMode.WARN, BudgetMode.ENFORCE}
            else None
        )
        return BudgetAccountingDecision(
            plan_digest=plan,
            total_cost_usd=total,
            allowed=allowed,
            warning=warning,
        )

    def pending_plan_cost_outbox(self) -> tuple[dict[str, Any], ...]:
        return self._pending_generic_outbox("plan_cost_outbox")

    def record_bill_observation(self, observation: object) -> bool:
        from .billing_port import BillObservation

        if not isinstance(observation, BillObservation):
            raise ValueError("observation must be a BillObservation")
        values = (
            observation.provider_id,
            observation.provider_account_id,
            observation.funding_source_id,
            observation.invoice_item_id,
            observation.plan_digest,
            observation.run_id,
            observation.amount,
            observation.currency,
            observation.tax,
            observation.credit,
            observation.payment_status,
            observation.source_digest,
            observation.metadata_digest,
            observation.observed_at,
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM bill_observations WHERE source_digest = ?",
                (observation.source_digest,),
            ).fetchone()
            if existing is not None:
                actual = tuple(existing[key] for key in (
                    "provider_id",
                    "provider_account_id",
                    "funding_source_id",
                    "invoice_item_id",
                    "plan_digest",
                    "run_id",
                    "amount",
                    "currency",
                    "tax",
                    "credit",
                    "payment_status",
                    "source_digest",
                    "metadata_digest",
                    "observed_at",
                ))
                if actual != values or existing["observation_id"] != observation.observation_id:
                    raise AccountingConflict(
                        "bill observation conflicts with existing source digest"
                    )
                connection.commit()
                return False
            connection.execute(
                """INSERT INTO bill_observations(
                    observation_id, provider_id, provider_account_id,
                    funding_source_id, invoice_item_id, plan_digest, run_id,
                    amount, currency, tax, credit, payment_status,
                    source_digest, metadata_digest, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (observation.observation_id, *values),
            )
            payload_json = _canonical_json(observation.to_public_dict())
            payload_digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
            connection.execute(
                """INSERT INTO bill_observation_outbox(
                    outbox_id, observation_id, payload_json, payload_sha256,
                    state, created_at
                ) VALUES (?, ?, ?, ?, 'pending', ?)""",
                (
                    str(uuid.uuid4()),
                    observation.observation_id,
                    payload_json,
                    payload_digest,
                    observation.observed_at,
                ),
            )
            connection.commit()
            return True
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise AccountingConflict(
                "bill observation references missing account or invocation"
            ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def bill_observation_count(self) -> int:
        connection = self._connect()
        try:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM bill_observations"
                ).fetchone()[0]
            )
        finally:
            connection.close()

    def pending_bill_outbox(self) -> tuple[dict[str, Any], ...]:
        return self._pending_generic_outbox("bill_observation_outbox")

    def _pending_generic_outbox(
        self,
        table: str,
    ) -> tuple[dict[str, Any], ...]:
        if table not in {"plan_cost_outbox", "bill_observation_outbox"}:
            raise ValueError("unsupported accounting outbox")
        connection = self._connect()
        try:
            rows = connection.execute(
                f"SELECT * FROM {table} WHERE state = 'pending' "
                "ORDER BY created_at, outbox_id"
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            {
                **{
                    key: row[key]
                    for key in row.keys()
                    if key != "payload_json"
                },
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        )

    @staticmethod
    def _plan_cost_from_row(row: sqlite3.Row) -> PlanCostRecord:
        return PlanCostRecord(
            cost_id=row["cost_id"],
            plan_digest=row["plan_digest"],
            run_id=row["run_id"],
            role_digest=row["role_digest"],
            route_id=row["route_id"],
            cost_class=CostClass(row["cost_class"]),
            amount_usd=row["amount_usd"],
            cost_kind=row["cost_kind"],
            pricing_basis_digest=row["pricing_basis_digest"],
            idempotency_key=row["idempotency_key"],
            observed_at=row["observed_at"],
        )

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
            context.provider_tier_binding_digest,
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
                    existing["provider_tier_binding_digest"],
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
                    soft_warning, policy_snapshot_sha256,
                    provider_tier_binding_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'dispatched', ?, ?, ?)
                """,
                (
                    run,
                    *values[:6],
                    dispatched_at,
                    values[6],
                    values[7],
                    values[8],
                    values[9],
                ),
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
        failure_code: str | None = None,
        failure_stage: str | None = None,
    ) -> None:
        run = _uuid4("run_id", run_id)
        if candidate_status not in _CANDIDATE_STATES:
            raise ValueError("candidate_status is invalid")
        if billing_state not in _BILLING_STATES - {"dispatched"}:
            raise ValueError("billing_state is invalid for terminal state")
        if (failure_code is None) != (failure_stage is None):
            raise ValueError("failure_code and failure_stage must be set together")
        normalized_failure_code = (
            _safe_id("failure_code", failure_code)
            if failure_code is not None
            else None
        )
        normalized_failure_stage = (
            _safe_id("failure_stage", failure_stage)
            if failure_stage is not None
            else None
        )
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
                    and row["failure_code"] == normalized_failure_code
                    and row["failure_stage"] == normalized_failure_stage
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
                SET terminal_at = ?, candidate_status = ?, billing_state = ?,
                    failure_code = ?, failure_stage = ?
                WHERE run_id = ?
                """,
                (
                    terminal_at,
                    candidate_status,
                    billing_state,
                    normalized_failure_code,
                    normalized_failure_stage,
                    run,
                ),
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
                ) VALUES (?, ?, 2, ?, ?, 'pending', ?, NULL)
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

    def mark_soft_warning(self, run_id: str) -> None:
        run = _uuid4("run_id", run_id)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT soft_warning FROM invocations WHERE run_id = ?",
                (run,),
            ).fetchone()
            if row is None:
                raise AccountingConflict(
                    "accounting warning has no dispatch"
                )
            if row["soft_warning"] != 1:
                connection.execute(
                    "UPDATE invocations SET soft_warning = 1 WHERE run_id = ?",
                    (run,),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

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

    def unsettled_count(self) -> int:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM invocations WHERE terminal_at IS NULL"
            ).fetchone()
        finally:
            connection.close()
        return int(row["count"])

    def status_snapshot(self) -> AccountingStatusSnapshot:
        connection = self._connect()
        try:
            return _status_snapshot_from_connection(
                connection,
                has_tier_column=True,
            )
        finally:
            connection.close()

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
            "provider_tier_binding_digest",
            "failure_code",
            "failure_stage",
        )
        return {key: row[key] for key in keys}


def read_accounting_status(path: str | Path) -> AccountingStatusSnapshot:
    candidate = Path(path)
    if not candidate.is_absolute() or candidate.drive.upper() != "D:":
        raise StoragePolicyError(
            "accounting database path must be absolute on D:"
        )
    if not candidate.exists():
        return _empty_status_snapshot()
    uri = candidate.absolute().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """SELECT version FROM accounting_schema_meta
            WHERE component = 'accounting'"""
        ).fetchone()
        if row is None or row["version"] not in {2, 3}:
            raise AccountingConflict(
                "accounting database schema version is unsupported"
            )
        columns = {
            item["name"]
            for item in connection.execute(
                "PRAGMA table_info(invocations)"
            ).fetchall()
        }
        return _status_snapshot_from_connection(
            connection,
            has_tier_column="provider_tier_binding_digest" in columns,
        )
    except sqlite3.Error as exc:
        raise AccountingConflict("accounting database is invalid") from exc
    finally:
        connection.close()
