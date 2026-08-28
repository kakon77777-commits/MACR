from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .direct_contracts import DirectRunSettings
from .direct_database import DirectDatabase
from .errors import DirectStoreConflict


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def guarded_settings() -> DirectRunSettings:
    return DirectRunSettings(
        profile_name="guarded",
        profile_version=1,
        max_output_tokens=2048,
        timeout_s=120.0,
        temperature=0.4,
        top_p=0.9,
        context_warning_tokens=7000,
        hard_context_tokens=8192,
        budget_behavior="hard_cap",
        soft_budget_usd=0.05,
        provider_improvement_preference="disabled",
    )


def operator_managed_settings() -> DirectRunSettings:
    return DirectRunSettings(
        profile_name="operator_managed",
        profile_version=1,
        max_output_tokens=4096,
        timeout_s=300.0,
        temperature=0.6,
        top_p=0.95,
        context_warning_tokens=7000,
        hard_context_tokens=8192,
        budget_behavior="warn_only",
        soft_budget_usd=None,
        provider_improvement_preference="allowed",
    )


def _canonical_settings(settings: DirectRunSettings) -> tuple[str, str]:
    encoded = json.dumps(
        settings.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class DirectSettingsStore:
    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path) -> None:
        self.database = DirectDatabase(path)
        self._initialize()

    @property
    def path(self) -> Path:
        return self.database.path

    def _initialize(self) -> None:
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS settings_schema_meta (
                    component TEXT PRIMARY KEY,
                    version INTEGER NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS settings_profiles (
                    profile_name TEXT NOT NULL,
                    profile_version INTEGER NOT NULL,
                    settings_json TEXT NOT NULL,
                    settings_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(profile_name, profile_version)
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS settings_state (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    active_profile_name TEXT NOT NULL,
                    active_profile_version INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(active_profile_name, active_profile_version)
                        REFERENCES settings_profiles(profile_name, profile_version)
                )"""
            )
            row = connection.execute(
                "SELECT version FROM settings_schema_meta WHERE component = 'direct_settings'"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO settings_schema_meta(component, version) VALUES ('direct_settings', ?)",
                    (self.SCHEMA_VERSION,),
                )
            elif row["version"] != self.SCHEMA_VERSION:
                raise DirectStoreConflict(
                    "Direct settings schema version is unsupported"
                )
            guarded = guarded_settings()
            encoded, digest = _canonical_settings(guarded)
            connection.execute(
                """INSERT OR IGNORE INTO settings_profiles(
                    profile_name, profile_version, settings_json,
                    settings_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?)""",
                (
                    guarded.profile_name,
                    guarded.profile_version,
                    encoded,
                    digest,
                    _utc_now(),
                ),
            )
            connection.execute(
                """INSERT OR IGNORE INTO settings_state(
                    singleton, active_profile_name, active_profile_version, updated_at
                ) VALUES (1, ?, ?, ?)""",
                (
                    guarded.profile_name,
                    guarded.profile_version,
                    _utc_now(),
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save_profile(
        self,
        settings: DirectRunSettings,
        *,
        activate: bool,
    ) -> bool:
        if not isinstance(settings, DirectRunSettings):
            raise ValueError("settings must be DirectRunSettings")
        if not isinstance(activate, bool):
            raise ValueError("activate must be boolean")
        encoded, digest = _canonical_settings(settings)
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT settings_json, settings_sha256
                FROM settings_profiles
                WHERE profile_name = ? AND profile_version = ?""",
                (settings.profile_name, settings.profile_version),
            ).fetchone()
            inserted = row is None
            if row is None:
                connection.execute(
                    """INSERT INTO settings_profiles(
                        profile_name, profile_version, settings_json,
                        settings_sha256, created_at
                    ) VALUES (?, ?, ?, ?, ?)""",
                    (
                        settings.profile_name,
                        settings.profile_version,
                        encoded,
                        digest,
                        _utc_now(),
                    ),
                )
            elif row["settings_json"] != encoded or row["settings_sha256"] != digest:
                raise DirectStoreConflict(
                    "Direct settings profile conflicts with an existing version"
                )
            if activate:
                connection.execute(
                    """UPDATE settings_state
                    SET active_profile_name = ?, active_profile_version = ?, updated_at = ?
                    WHERE singleton = 1""",
                    (
                        settings.profile_name,
                        settings.profile_version,
                        _utc_now(),
                    ),
                )
            connection.commit()
            return inserted
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def ensure_operator_managed(self) -> DirectRunSettings:
        settings = operator_managed_settings()
        self.save_profile(settings, activate=True)
        return settings

    def activate(self, profile_name: str, profile_version: int) -> None:
        if not isinstance(profile_name, str) or not profile_name.strip():
            raise ValueError("profile_name must be non-empty")
        if (
            isinstance(profile_version, bool)
            or not isinstance(profile_version, int)
            or profile_version < 1
        ):
            raise ValueError("profile_version must be positive")
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT 1 FROM settings_profiles
                WHERE profile_name = ? AND profile_version = ?""",
                (profile_name.strip(), profile_version),
            ).fetchone()
            if row is None:
                raise DirectStoreConflict("Direct settings profile is missing")
            connection.execute(
                """UPDATE settings_state
                SET active_profile_name = ?, active_profile_version = ?, updated_at = ?
                WHERE singleton = 1""",
                (profile_name.strip(), profile_version, _utc_now()),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _decode(row: sqlite3.Row) -> DirectRunSettings:
        try:
            document = json.loads(row["settings_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise DirectStoreConflict("Direct settings record is malformed") from exc
        settings = DirectRunSettings.from_dict(document)
        encoded, digest = _canonical_settings(settings)
        if encoded != row["settings_json"] or digest != row["settings_sha256"]:
            raise DirectStoreConflict("Direct settings record digest is invalid")
        return settings

    def active_profile(self) -> DirectRunSettings:
        connection = self.database.connect()
        try:
            row = connection.execute(
                """SELECT p.settings_json, p.settings_sha256
                FROM settings_state s
                JOIN settings_profiles p
                  ON p.profile_name = s.active_profile_name
                 AND p.profile_version = s.active_profile_version
                WHERE s.singleton = 1"""
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise DirectStoreConflict("Direct active settings profile is missing")
        return self._decode(row)

    def get_profile(
        self,
        profile_name: str,
        profile_version: int,
    ) -> DirectRunSettings:
        if not isinstance(profile_name, str) or not profile_name.strip():
            raise ValueError("profile_name must be non-empty")
        if (
            isinstance(profile_version, bool)
            or not isinstance(profile_version, int)
            or profile_version < 1
        ):
            raise ValueError("profile_version must be positive")
        connection = self.database.connect()
        try:
            row = connection.execute(
                """SELECT settings_json, settings_sha256
                FROM settings_profiles
                WHERE profile_name = ? AND profile_version = ?""",
                (profile_name.strip(), profile_version),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise DirectStoreConflict("Direct settings profile is missing")
        return self._decode(row)

    def profiles(self) -> tuple[DirectRunSettings, ...]:
        connection = self.database.connect()
        try:
            rows = connection.execute(
                """SELECT settings_json, settings_sha256
                FROM settings_profiles
                ORDER BY rowid"""
            ).fetchall()
        finally:
            connection.close()
        return tuple(self._decode(row) for row in rows)
