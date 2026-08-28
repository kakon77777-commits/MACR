from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .errors import DirectStoreConflict, StoragePolicyError


class DirectDatabase:
    _BOOTSTRAP_TIMEOUT_S = 30.0
    _BOOTSTRAP_RETRY_INTERVAL_S = 0.01

    def __init__(self, path: str | Path) -> None:
        candidate = Path(path)
        if not candidate.is_absolute() or candidate.drive.upper() != "D:":
            raise StoragePolicyError(
                "Direct database path must be absolute on D:"
            )
        self.path = candidate.absolute()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._bootstrap_connection()
        connection.close()

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
                mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
                if mode.lower() != "wal":
                    selected = connection.execute(
                        "PRAGMA journal_mode = WAL"
                    ).fetchone()[0]
                    if selected.lower() != "wal":
                        raise DirectStoreConflict(
                            "Direct database could not enable WAL mode"
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
            if mode.lower() != "wal":
                raise DirectStoreConflict(
                    "Direct database is not configured for WAL mode"
                )
            connection.execute("PRAGMA synchronous = FULL")
        except Exception:
            connection.close()
            raise
        return connection
