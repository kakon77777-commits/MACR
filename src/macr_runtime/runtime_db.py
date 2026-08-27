from __future__ import annotations

import sqlite3
from pathlib import Path

from .errors import EventStoreConflict, StoragePolicyError


class RuntimeDatabase:
    """Connection policy and schema owner for MACR runtime coordination state."""

    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path) -> None:
        candidate = Path(path)
        if not candidate.is_absolute() or candidate.drive.upper() != "D:":
            raise StoragePolicyError(
                "runtime database path must be absolute on D:"
            )
        self.path = candidate.absolute()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
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
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    component TEXT PRIMARY KEY,
                    version INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    dispatch_event_id TEXT NOT NULL UNIQUE,
                    terminal_event_id TEXT UNIQUE,
                    state TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    terminal_at TEXT
                );

                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    run_id TEXT REFERENCES runs(run_id),
                    event_type TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    source_sha256 TEXT,
                    source_line INTEGER
                );

                CREATE UNIQUE INDEX IF NOT EXISTS events_one_dispatch_per_run
                ON events(run_id)
                WHERE event_type = 'provider.dispatch_requested';
                """
            )
            row = connection.execute(
                "SELECT version FROM schema_meta WHERE component = ?",
                ("runtime",),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_meta(component, version) VALUES (?, ?)",
                    ("runtime", self.SCHEMA_VERSION),
                )
            elif row["version"] != self.SCHEMA_VERSION:
                raise EventStoreConflict(
                    "runtime database schema version is unsupported"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
