from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from ..errors import StoragePolicyError
from .errors import AgentProjectionConflictError


class AgentDatabase:
    """Connection policy and schema owner for Phase B AgentRun state."""

    SCHEMA_VERSION = 1
    _BOOTSTRAP_TIMEOUT_S = 30.0
    _BOOTSTRAP_RETRY_INTERVAL_S = 0.01

    def __init__(self, path: str | Path) -> None:
        candidate = Path(path)
        if not candidate.is_absolute() or candidate.drive.upper() != "D:":
            raise StoragePolicyError(
                "Agent database path must be absolute on D:"
            )
        self.path = candidate.absolute()
        self.path.parent.mkdir(parents=True, exist_ok=True)
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
                        raise AgentProjectionConflictError(
                            "Agent database could not enable WAL journal mode"
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
                raise AgentProjectionConflictError(
                    "Agent database is not configured for WAL journal mode"
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
            for statement in _SCHEMA_STATEMENTS:
                connection.execute(statement)
            row = connection.execute(
                "SELECT version FROM schema_meta WHERE component = ?",
                ("agent_runtime",),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_meta(component, version) VALUES (?, ?)",
                    ("agent_runtime", self.SCHEMA_VERSION),
                )
            elif row["version"] != self.SCHEMA_VERSION:
                raise AgentProjectionConflictError(
                    "Agent database schema version is unsupported"
                )
            connection.execute(
                """
                INSERT OR IGNORE INTO agent_fencing_counter(singleton, value)
                VALUES (1, 0)
                """
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


_SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS schema_meta (
        component TEXT PRIMARY KEY,
        version INTEGER NOT NULL CHECK(version >= 1)
    )""",
    """CREATE TABLE IF NOT EXISTS agent_runs (
        agent_run_id TEXT PRIMARY KEY,
        subject_digest TEXT NOT NULL,
        agent_ref TEXT NOT NULL,
        initial_header_json TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN (
            'created', 'admitted', 'active', 'waiting', 'suspended',
            'waking', 'blocked', 'reconciliation_required', 'completed',
            'failed', 'cancelled'
        )),
        state_revision INTEGER NOT NULL CHECK(state_revision >= 1),
        epoch INTEGER NOT NULL CHECK(epoch >= 0),
        goal_ref TEXT NOT NULL,
        authority_ref TEXT NOT NULL,
        budget_ref TEXT NOT NULL,
        semantic_state_ref TEXT,
        active_plan_ref TEXT,
        latest_checkpoint_ref TEXT,
        parent_agent_run_id TEXT,
        delegation_ref TEXT,
        state_digest TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK(
            (parent_agent_run_id IS NULL AND delegation_ref IS NULL)
            OR
            (parent_agent_run_id IS NOT NULL AND delegation_ref IS NOT NULL)
        )
    )""",
    """CREATE INDEX IF NOT EXISTS agent_runs_by_state
    ON agent_runs(state, agent_run_id)""",
    """CREATE TABLE IF NOT EXISTS agent_events (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        agent_run_id TEXT NOT NULL,
        epoch INTEGER NOT NULL CHECK(epoch >= 0),
        before_revision INTEGER NOT NULL CHECK(before_revision >= 0),
        after_revision INTEGER NOT NULL CHECK(after_revision >= 1),
        event_type TEXT NOT NULL CHECK(event_type IN (
            'agent.run_created', 'agent.run_admitted',
            'agent.owner_acquired', 'agent.run_activated', 'agent.blocked',
            'agent.completed', 'agent.failed', 'agent.cancelled'
        )),
        payload_json TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        state_digest_after TEXT NOT NULL,
        created_at TEXT NOT NULL,
        CHECK(after_revision = before_revision + 1),
        UNIQUE(agent_run_id, after_revision)
    )""",
    """CREATE INDEX IF NOT EXISTS agent_events_by_run
    ON agent_events(agent_run_id, sequence)""",
    """CREATE TABLE IF NOT EXISTS agent_goals (
        agent_run_id TEXT NOT NULL REFERENCES agent_runs(agent_run_id)
            ON DELETE CASCADE,
        goal_ref TEXT NOT NULL,
        goal_digest TEXT NOT NULL,
        goal_revision INTEGER NOT NULL CHECK(goal_revision >= 1),
        binding_digest TEXT NOT NULL,
        PRIMARY KEY(agent_run_id, binding_digest)
    )""",
    """CREATE TABLE IF NOT EXISTS agent_world_bindings (
        agent_run_id TEXT NOT NULL REFERENCES agent_runs(agent_run_id)
            ON DELETE CASCADE,
        world_ref TEXT NOT NULL,
        world_digest TEXT NOT NULL,
        world_revision INTEGER NOT NULL CHECK(world_revision >= 1),
        binding_digest TEXT NOT NULL,
        PRIMARY KEY(agent_run_id, binding_digest)
    )""",
    """CREATE TABLE IF NOT EXISTS agent_memory_bindings (
        agent_run_id TEXT NOT NULL REFERENCES agent_runs(agent_run_id)
            ON DELETE CASCADE,
        memory_system_id TEXT NOT NULL,
        profile_id TEXT NOT NULL,
        subject_ref TEXT NOT NULL,
        head_ref TEXT,
        head_digest TEXT,
        access_policy_ref TEXT NOT NULL,
        projection_policy_ref TEXT NOT NULL,
        binding_digest TEXT NOT NULL,
        CHECK(
            (head_ref IS NULL AND head_digest IS NULL)
            OR
            (head_ref IS NOT NULL AND head_digest IS NOT NULL)
        ),
        PRIMARY KEY(agent_run_id, binding_digest)
    )""",
    """CREATE TABLE IF NOT EXISTS agent_plan_bindings (
        agent_run_id TEXT NOT NULL REFERENCES agent_runs(agent_run_id)
            ON DELETE CASCADE,
        plan_ref TEXT NOT NULL,
        plan_digest TEXT NOT NULL,
        plan_revision INTEGER NOT NULL CHECK(plan_revision >= 1),
        binding_digest TEXT NOT NULL,
        PRIMARY KEY(agent_run_id, binding_digest)
    )""",
    """CREATE TABLE IF NOT EXISTS agent_children (
        parent_agent_run_id TEXT NOT NULL REFERENCES agent_runs(agent_run_id)
            ON DELETE CASCADE,
        child_agent_run_id TEXT NOT NULL REFERENCES agent_runs(agent_run_id)
            ON DELETE CASCADE,
        delegation_ref TEXT NOT NULL,
        PRIMARY KEY(parent_agent_run_id, child_agent_run_id)
    )""",
    """CREATE TABLE IF NOT EXISTS agent_ownership (
        agent_run_id TEXT PRIMARY KEY REFERENCES agent_runs(agent_run_id)
            ON DELETE CASCADE,
        owner_id TEXT NOT NULL,
        lease_id TEXT NOT NULL UNIQUE,
        fencing_token INTEGER NOT NULL CHECK(fencing_token >= 1),
        epoch INTEGER NOT NULL CHECK(epoch >= 1),
        acquired_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS agent_ownership_by_expiry
    ON agent_ownership(expires_at, agent_run_id)""",
    """CREATE TABLE IF NOT EXISTS agent_fencing_counter (
        singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
        value INTEGER NOT NULL CHECK(value >= 0)
    )""",
)
