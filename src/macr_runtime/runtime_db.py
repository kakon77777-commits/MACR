from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .errors import EventStoreConflict, StoragePolicyError


class RuntimeDatabase:
    """Connection policy and schema owner for MACR runtime coordination state."""

    SCHEMA_VERSION = 8

    def __init__(self, path: str | Path) -> None:
        candidate = Path(path)
        if not candidate.is_absolute() or candidate.drive.upper() != "D:":
            raise StoragePolicyError(
                "runtime database path must be absolute on D:"
            )
        self.path = candidate.absolute()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    _BOOTSTRAP_TIMEOUT_S = 30.0
    _BOOTSTRAP_RETRY_INTERVAL_S = 0.01

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
                        raise EventStoreConflict(
                            "runtime database could not enable WAL journal mode"
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
            current_mode = connection.execute(
                "PRAGMA journal_mode"
            ).fetchone()[0]
            if current_mode.lower() != "wal":
                raise EventStoreConflict(
                    "runtime database is not configured for WAL journal mode"
                )
            connection.execute("PRAGMA synchronous = FULL")
        except Exception:
            connection.close()
            raise
        return connection

    def _initialize(self) -> None:
        connection = self._bootstrap_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            statements = (
                """CREATE TABLE IF NOT EXISTS schema_meta (
                    component TEXT PRIMARY KEY,
                    version INTEGER NOT NULL
                )""",
                """CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    dispatch_event_id TEXT NOT NULL UNIQUE,
                    terminal_event_id TEXT UNIQUE,
                    state TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    terminal_at TEXT
                )""",
                """CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    run_id TEXT REFERENCES runs(run_id),
                    event_type TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    source_sha256 TEXT,
                    source_line INTEGER
                )""",
                """CREATE UNIQUE INDEX IF NOT EXISTS events_one_dispatch_per_run
                ON events(run_id)
                WHERE event_type = 'provider.dispatch_requested'""",
            )
            for statement in statements:
                connection.execute(statement)
            row = connection.execute(
                "SELECT version FROM schema_meta WHERE component = ?",
                ("runtime",),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_meta(component, version) VALUES (?, ?)",
                    ("runtime", 1),
                )
                version = 1
            else:
                version = row["version"]
            if version > self.SCHEMA_VERSION or version < 1:
                raise EventStoreConflict(
                    "runtime database schema version is unsupported"
                )
            if version == 1:
                migration_two = (
                    """CREATE TABLE IF NOT EXISTS legacy_sources (
                        source_sha256 TEXT PRIMARY KEY,
                        source_bytes INTEGER NOT NULL,
                        expected_count INTEGER,
                        observed_count INTEGER NOT NULL,
                        valid_count INTEGER NOT NULL,
                        corrupt_count INTEGER NOT NULL,
                        duplicate_count INTEGER NOT NULL,
                        imported_count INTEGER NOT NULL,
                        complete INTEGER NOT NULL,
                        imported_at TEXT NOT NULL
                    )""",
                    """CREATE TABLE IF NOT EXISTS legacy_quarantine (
                        source_sha256 TEXT NOT NULL
                            REFERENCES legacy_sources(source_sha256),
                        line_number INTEGER NOT NULL,
                        raw_sha256 TEXT NOT NULL,
                        raw_bytes BLOB NOT NULL,
                        error_code TEXT NOT NULL,
                        PRIMARY KEY (source_sha256, line_number)
                    )""",
                )
                for statement in migration_two:
                    connection.execute(statement)
                connection.execute(
                    "UPDATE schema_meta SET version = ? WHERE component = ?",
                    (2, "runtime"),
                )
                version = 2
            if version == 2:
                migration_three = (
                    """CREATE TABLE IF NOT EXISTS authority_epoch (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        epoch INTEGER NOT NULL,
                        state TEXT NOT NULL,
                        reason_digest TEXT,
                        updated_at TEXT NOT NULL
                    )""",
                    """CREATE TABLE IF NOT EXISTS dispatch_authorities (
                        authority_id TEXT PRIMARY KEY,
                        source_kind TEXT NOT NULL,
                        source_id TEXT NOT NULL,
                        body_json TEXT NOT NULL,
                        body_sha256 TEXT NOT NULL,
                        revision INTEGER NOT NULL CHECK(revision >= 1),
                        epoch INTEGER NOT NULL,
                        scope_json TEXT NOT NULL,
                        issued_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        revoked_at TEXT,
                        UNIQUE(source_kind, source_id, revision)
                    )""",
                    """CREATE TABLE IF NOT EXISTS dispatch_leases (
                        resource_key TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL,
                        fencing_token INTEGER NOT NULL,
                        acquired_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL
                    )""",
                    """CREATE TABLE IF NOT EXISTS fencing_counter (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        value INTEGER NOT NULL
                    )""",
                )
                for statement in migration_three:
                    connection.execute(statement)
                now = "1970-01-01T00:00:00+00:00"
                connection.execute(
                    """
                    INSERT OR IGNORE INTO authority_epoch(
                        singleton, epoch, state, reason_digest, updated_at
                    ) VALUES (1, 0, 'open', NULL, ?)
                    """,
                    (now,),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO fencing_counter(singleton, value)
                    VALUES (1, 0)
                    """
                )
                connection.execute(
                    "UPDATE schema_meta SET version = ? WHERE component = ?",
                    (3, "runtime"),
                )
                version = 3
            if version == 3:
                migration_four = (
                    """CREATE TABLE IF NOT EXISTS candidate_captures (
                        capture_id TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL UNIQUE,
                        provider_id TEXT NOT NULL,
                        answer_sha256 TEXT NOT NULL,
                        answer_bytes INTEGER NOT NULL,
                        relative_path TEXT NOT NULL,
                        task_digest TEXT NOT NULL,
                        approval_digest TEXT,
                        captured_at TEXT NOT NULL
                    )""",
                    """CREATE TABLE IF NOT EXISTS materializations (
                        materialization_id TEXT PRIMARY KEY,
                        capture_id TEXT NOT NULL
                            REFERENCES candidate_captures(capture_id),
                        state TEXT NOT NULL,
                        output_sha256 TEXT NOT NULL,
                        output_bytes INTEGER NOT NULL,
                        relative_path TEXT,
                        target_path_sha256 TEXT,
                        transformer_version TEXT,
                        builder_origin_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )""",
                )
                for statement in migration_four:
                    connection.execute(statement)
                connection.execute(
                    "UPDATE schema_meta SET version = ? WHERE component = ?",
                    (4, "runtime"),
                )
                version = 4
            if version == 4:
                migration_five = (
                    """CREATE TABLE IF NOT EXISTS batch_authorities (
                        authority_id TEXT PRIMARY KEY,
                        body_json TEXT NOT NULL,
                        body_sha256 TEXT NOT NULL UNIQUE,
                        scope_json TEXT NOT NULL,
                        scope_sha256 TEXT NOT NULL,
                        plan_digest TEXT NOT NULL,
                        revision INTEGER NOT NULL,
                        issued_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        revoked_at TEXT,
                        UNIQUE(plan_digest, revision)
                    )""",
                    """CREATE TABLE IF NOT EXISTS plan_queue_batches (
                        plan_digest TEXT PRIMARY KEY,
                        authority_id TEXT NOT NULL
                            REFERENCES batch_authorities(authority_id),
                        authority_digest TEXT NOT NULL,
                        authority_revision INTEGER NOT NULL,
                        aggregate_cost_ceiling_usd REAL NOT NULL
                            CHECK(aggregate_cost_ceiling_usd >= 0),
                        authorized_dispatchers_json TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        members_sha256 TEXT NOT NULL,
                        enqueued_at TEXT NOT NULL
                    )""",
                    """CREATE TABLE IF NOT EXISTS plan_queue_members (
                        member_id TEXT PRIMARY KEY,
                        plan_digest TEXT NOT NULL
                            REFERENCES plan_queue_batches(plan_digest),
                        ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
                        member_digest TEXT NOT NULL,
                        provider_id TEXT NOT NULL,
                        route_id TEXT NOT NULL,
                        role_digest TEXT NOT NULL,
                        privacy TEXT NOT NULL,
                        context_class TEXT NOT NULL,
                        cost_ceiling_usd REAL NOT NULL
                            CHECK(cost_ceiling_usd >= 0),
                        state TEXT NOT NULL CHECK(state IN (
                            'queued', 'claimed', 'completed', 'failed',
                            'reconciliation_required'
                        )),
                        lease_holder TEXT,
                        fencing_token INTEGER,
                        lease_expires_at TEXT,
                        attempts INTEGER NOT NULL
                            CHECK(attempts = 0 OR attempts = 1),
                        terminal_at TEXT,
                        terminal_evidence_digest TEXT,
                        observed_cost_usd REAL
                            CHECK(observed_cost_usd IS NULL
                                  OR observed_cost_usd >= 0),
                        UNIQUE(plan_digest, ordinal),
                        UNIQUE(plan_digest, member_digest)
                    )""",
                    """CREATE TABLE IF NOT EXISTS plan_target_claims (
                        plan_digest TEXT NOT NULL,
                        target_key TEXT NOT NULL,
                        member_id TEXT NOT NULL
                            REFERENCES plan_queue_members(member_id),
                        alternative_group TEXT,
                        materialize_automatically INTEGER NOT NULL
                            CHECK(materialize_automatically IN (0, 1)),
                        PRIMARY KEY(plan_digest, target_key, member_id)
                    )""",
                    """CREATE INDEX IF NOT EXISTS plan_queue_claimable
                    ON plan_queue_members(state, plan_digest, ordinal)""",
                    """CREATE INDEX IF NOT EXISTS plan_queue_expiring
                    ON plan_queue_members(state, lease_expires_at)""",
                )
                for statement in migration_five:
                    connection.execute(statement)
                connection.execute(
                    "UPDATE schema_meta SET version = ? WHERE component = ?",
                    (5, "runtime"),
                )
                version = 5
            if version == 5:
                migration_six = (
                    """CREATE TABLE IF NOT EXISTS target_path_leases (
                        lease_id TEXT PRIMARY KEY,
                        repository_id TEXT NOT NULL,
                        target_key TEXT NOT NULL,
                        plan_digest TEXT NOT NULL,
                        member_digest TEXT NOT NULL,
                        alternative_group TEXT,
                        materialize_automatically INTEGER NOT NULL
                            CHECK(materialize_automatically IN (0, 1)),
                        state TEXT NOT NULL CHECK(state IN (
                            'active', 'released', 'reconciliation_required'
                        )),
                        fencing_token INTEGER NOT NULL,
                        acquired_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        released_at TEXT,
                        reconciliation_evidence_digest TEXT,
                        UNIQUE(
                            repository_id, target_key, plan_digest,
                            member_digest
                        )
                    )""",
                    """CREATE INDEX IF NOT EXISTS target_path_active
                    ON target_path_leases(repository_id, target_key, state)""",
                )
                for statement in migration_six:
                    connection.execute(statement)
                connection.execute(
                    "UPDATE schema_meta SET version = ? WHERE component = ?",
                    (6, "runtime"),
                )
                version = 6
            if version == 6:
                columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(plan_queue_members)"
                    ).fetchall()
                }
                if "provider_tier_binding_digest" not in columns:
                    connection.execute(
                        """ALTER TABLE plan_queue_members
                        ADD COLUMN provider_tier_binding_digest TEXT"""
                    )
                connection.execute(
                    "UPDATE schema_meta SET version = ? WHERE component = ?",
                    (7, "runtime"),
                )
                version = 7
            if version == 7:
                migration_eight = (
                    """CREATE TABLE IF NOT EXISTS provider_admission_policies (
                        provider_id TEXT NOT NULL,
                        revision INTEGER NOT NULL CHECK(revision >= 1),
                        body_json TEXT NOT NULL,
                        body_sha256 TEXT NOT NULL,
                        policy_digest TEXT NOT NULL UNIQUE,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY(provider_id, revision)
                    )""",
                    """CREATE TABLE IF NOT EXISTS provider_admission_state (
                        provider_id TEXT PRIMARY KEY,
                        policy_digest TEXT NOT NULL,
                        effective_target INTEGER NOT NULL
                            CHECK(effective_target >= 1),
                        circuit_state TEXT NOT NULL CHECK(circuit_state IN (
                            'closed', 'open', 'half_open'
                        )),
                        grant_sequence INTEGER NOT NULL
                            CHECK(grant_sequence >= 0),
                        last_granted_lane TEXT CHECK(
                            last_granted_lane IS NULL OR
                            last_granted_lane IN (
                                'interactive', 'routine', 'bulk'
                            )
                        ),
                        half_open_probe_request_digest TEXT,
                        control_revision INTEGER NOT NULL
                            CHECK(control_revision >= 1),
                        control_digest TEXT NOT NULL,
                        last_signal TEXT,
                        updated_at TEXT NOT NULL
                    )""",
                    """CREATE TABLE IF NOT EXISTS provider_admission_transitions (
                        transition_id TEXT PRIMARY KEY,
                        provider_id TEXT NOT NULL,
                        control_revision INTEGER NOT NULL
                            CHECK(control_revision >= 1),
                        prior_control_digest TEXT NOT NULL,
                        transition_kind TEXT NOT NULL,
                        authority_digest TEXT,
                        binding_digest TEXT,
                        request_id TEXT,
                        evidence_digest TEXT,
                        body_json TEXT NOT NULL,
                        body_sha256 TEXT NOT NULL UNIQUE,
                        created_at TEXT NOT NULL,
                        UNIQUE(provider_id, control_revision)
                    )""",
                    """CREATE TRIGGER IF NOT EXISTS
                    provider_admission_transitions_no_update
                    BEFORE UPDATE ON provider_admission_transitions
                    BEGIN
                        SELECT RAISE(ABORT,
                            'provider admission transitions are append-only');
                    END""",
                    """CREATE TRIGGER IF NOT EXISTS
                    provider_admission_transitions_no_delete
                    BEFORE DELETE ON provider_admission_transitions
                    BEGIN
                        SELECT RAISE(ABORT,
                            'provider admission transitions are append-only');
                    END""",
                    """CREATE TABLE IF NOT EXISTS provider_admission_projects (
                        provider_id TEXT NOT NULL,
                        project_binding_digest TEXT NOT NULL,
                        active_units INTEGER NOT NULL CHECK(active_units >= 0),
                        last_grant_sequence INTEGER NOT NULL
                            CHECK(last_grant_sequence >= 0),
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(provider_id, project_binding_digest)
                    )""",
                    """CREATE TABLE IF NOT EXISTS provider_admission_requests (
                        request_id TEXT PRIMARY KEY,
                        provider_id TEXT NOT NULL,
                        project_binding_digest TEXT NOT NULL,
                        admission_lane TEXT NOT NULL CHECK(admission_lane IN (
                            'interactive', 'routine', 'bulk'
                        )),
                        run_id TEXT NOT NULL UNIQUE,
                        authority_digest TEXT NOT NULL,
                        authority_epoch INTEGER NOT NULL CHECK(authority_epoch >= 0),
                        task_digest TEXT NOT NULL,
                        member_digest TEXT,
                        provider_tier_binding_digest TEXT,
                        policy_digest TEXT NOT NULL,
                        capacity_unit INTEGER NOT NULL CHECK(capacity_unit = 1),
                        state TEXT NOT NULL CHECK(state IN (
                            'waiting', 'granted', 'dispatched', 'completed',
                            'cancelled', 'reconciliation_required', 'reconciled'
                        )),
                        fencing_token INTEGER,
                        requested_at TEXT NOT NULL,
                        granted_at TEXT,
                        transport_started_at TEXT,
                        terminal_at TEXT,
                        expires_at TEXT NOT NULL,
                        terminal_evidence_digest TEXT,
                        resolution_evidence_digest TEXT,
                        resolved_at TEXT
                    )""",
                    """CREATE INDEX IF NOT EXISTS provider_admission_waiting
                    ON provider_admission_requests(
                        provider_id, state, admission_lane, requested_at
                    )""",
                    """CREATE INDEX IF NOT EXISTS provider_admission_active
                    ON provider_admission_requests(provider_id, state)""",
                )
                for statement in migration_eight:
                    connection.execute(statement)
                batch_exists = connection.execute(
                    """SELECT 1 FROM sqlite_master
                    WHERE type='table' AND name='plan_queue_batches'"""
                ).fetchone()
                if batch_exists is not None:
                    batch_columns = {
                        item[1]
                        for item in connection.execute(
                            "PRAGMA table_info(plan_queue_batches)"
                        ).fetchall()
                    }
                    for name in (
                        "project_binding_digest",
                        "admission_lane",
                        "provider_admission_policy_digest",
                    ):
                        if name not in batch_columns:
                            connection.execute(
                                "ALTER TABLE plan_queue_batches "
                                f"ADD COLUMN {name} TEXT"
                            )
                connection.execute(
                    "UPDATE schema_meta SET version = ? WHERE component = ?",
                    (8, "runtime"),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
