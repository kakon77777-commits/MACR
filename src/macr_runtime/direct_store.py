from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .direct_contracts import DirectConversationSpec, DirectMessage
from .direct_database import DirectDatabase
from .errors import DirectStoreConflict


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid4(name: str, value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a UUIDv4 string") from exc
    if parsed.version != 4 or str(parsed) != value.lower():
        raise ValueError(f"{name} must be a UUIDv4 string")
    return str(parsed)


def _bounded_text(
    name: str,
    value: str,
    *,
    maximum: int,
    preserve: bool = False,
) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be a bounded non-empty string")
    return value if preserve else value.strip()


class DirectConversationStore:
    SCHEMA_VERSION = 1

    def __init__(
        self,
        path: str | Path,
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.database = DirectDatabase(path)
        self._now = now
        self._initialize()

    @property
    def path(self) -> Path:
        return self.database.path

    def _current_time(self) -> str:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("Direct store clock must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()

    def _initialize(self) -> None:
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            statements = (
                """CREATE TABLE IF NOT EXISTS direct_schema_meta (
                    component TEXT PRIMARY KEY,
                    version INTEGER NOT NULL
                )""",
                """CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    model_digest TEXT,
                    created_at TEXT NOT NULL,
                    last_active_at TEXT NOT NULL,
                    system_prompt TEXT NOT NULL,
                    system_prompt_sha256 TEXT NOT NULL,
                    settings_profile_name TEXT NOT NULL,
                    settings_profile_version INTEGER NOT NULL,
                    policy_snapshot_sha256 TEXT NOT NULL,
                    encryption TEXT NOT NULL,
                    dataset_role TEXT NOT NULL,
                    training_eligible INTEGER NOT NULL,
                    provider_improvement_preference TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0,
                    last_context_estimate INTEGER,
                    context_warning INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(conversation_id, provider_id, model)
                )""",
                """CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL
                        REFERENCES conversations(conversation_id),
                    ordinal INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    observation_id TEXT,
                    display_state TEXT NOT NULL,
                    UNIQUE(conversation_id, ordinal)
                )""",
                """CREATE TABLE IF NOT EXISTS direct_runs (
                    run_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL
                        REFERENCES conversations(conversation_id),
                    provider_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    user_ordinal INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    terminal_at TEXT,
                    failure_type TEXT,
                    context_estimate INTEGER,
                    context_warning INTEGER NOT NULL DEFAULT 0
                )""",
                """CREATE INDEX IF NOT EXISTS messages_search_index
                ON messages(conversation_id, ordinal)""",
                """CREATE INDEX IF NOT EXISTS conversations_active_index
                ON conversations(archived, last_active_at DESC)""",
            )
            for statement in statements:
                connection.execute(statement)
            row = connection.execute(
                "SELECT version FROM direct_schema_meta WHERE component = 'direct_conversations'"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO direct_schema_meta(component, version) VALUES ('direct_conversations', ?)",
                    (self.SCHEMA_VERSION,),
                )
            elif row["version"] != self.SCHEMA_VERSION:
                raise DirectStoreConflict(
                    "Direct conversation schema version is unsupported"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _conversation_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "conversation_id": row["conversation_id"],
            "title": row["title"],
            "provider_id": row["provider_id"],
            "model": row["model"],
            "model_digest": row["model_digest"],
            "created_at": row["created_at"],
            "last_active_at": row["last_active_at"],
            "system_prompt": row["system_prompt"],
            "system_prompt_sha256": row["system_prompt_sha256"],
            "settings_profile_name": row["settings_profile_name"],
            "settings_profile_version": row["settings_profile_version"],
            "policy_snapshot_sha256": row["policy_snapshot_sha256"],
            "encryption": row["encryption"],
            "dataset_role": row["dataset_role"],
            "training_eligible": bool(row["training_eligible"]),
            "provider_improvement_preference": row[
                "provider_improvement_preference"
            ],
            "archived": bool(row["archived"]),
            "last_context_estimate": row["last_context_estimate"],
            "context_warning": bool(row["context_warning"]),
        }

    @staticmethod
    def _message_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "message_id": row["message_id"],
            "conversation_id": row["conversation_id"],
            "ordinal": row["ordinal"],
            "role": row["role"],
            "content": row["content"],
            "created_at": row["created_at"],
            "run_id": row["run_id"],
            "observation_id": row["observation_id"],
            "display_state": row["display_state"],
        }

    @staticmethod
    def _run_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "run_id": row["run_id"],
            "conversation_id": row["conversation_id"],
            "provider_id": row["provider_id"],
            "model": row["model"],
            "user_ordinal": row["user_ordinal"],
            "state": row["state"],
            "created_at": row["created_at"],
            "terminal_at": row["terminal_at"],
            "failure_type": row["failure_type"],
            "context_estimate": row["context_estimate"],
            "context_warning": bool(row["context_warning"]),
        }

    def create(
        self,
        spec: DirectConversationSpec,
        *,
        title: str = "New conversation",
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(spec, DirectConversationSpec):
            raise ValueError("spec must be DirectConversationSpec")
        identity = _uuid4(
            "conversation_id",
            conversation_id or str(uuid.uuid4()),
        )
        normalized_title = _bounded_text("title", title, maximum=256)
        now = self._current_time()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO conversations(
                    conversation_id, title, provider_id, model, model_digest,
                    created_at, last_active_at, system_prompt,
                    system_prompt_sha256, settings_profile_name,
                    settings_profile_version, policy_snapshot_sha256,
                    encryption, dataset_role, training_eligible,
                    provider_improvement_preference, archived,
                    last_context_estimate, context_warning
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, 0)""",
                (
                    identity,
                    normalized_title,
                    spec.provider_id.value,
                    spec.model,
                    spec.model_digest,
                    now,
                    now,
                    spec.system_prompt,
                    spec.system_prompt_sha256,
                    spec.settings_profile_name,
                    spec.settings_profile_version,
                    spec.policy_snapshot_sha256,
                    spec.encryption,
                    spec.dataset_role,
                    int(spec.training_eligible),
                    spec.provider_improvement_preference,
                ),
            )
            row = connection.execute(
                "SELECT * FROM conversations WHERE conversation_id = ?",
                (identity,),
            ).fetchone()
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise DirectStoreConflict(
                "Direct conversation identity already exists"
            ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        if row is None:
            raise DirectStoreConflict("Direct conversation creation failed")
        return self._conversation_dict(row)

    def get(self, conversation_id: str) -> dict[str, Any]:
        identity = _uuid4("conversation_id", conversation_id)
        connection = self.database.connect()
        try:
            row = connection.execute(
                "SELECT * FROM conversations WHERE conversation_id = ?",
                (identity,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise DirectStoreConflict("Direct conversation is missing")
        return self._conversation_dict(row)

    def assert_identity(
        self,
        conversation_id: str,
        *,
        provider_id: str,
        model: str,
    ) -> None:
        conversation = self.get(conversation_id)
        if (
            conversation["provider_id"] != provider_id
            or conversation["model"] != model
        ):
            raise DirectStoreConflict(
                "Direct conversation provider/model identity is immutable"
            )

    def list(self, *, include_archived: bool = False) -> tuple[dict[str, Any], ...]:
        if not isinstance(include_archived, bool):
            raise ValueError("include_archived must be boolean")
        where = "" if include_archived else " WHERE archived = 0"
        connection = self.database.connect()
        try:
            rows = connection.execute(
                "SELECT * FROM conversations"
                + where
                + " ORDER BY last_active_at DESC, conversation_id"
            ).fetchall()
        finally:
            connection.close()
        return tuple(self._conversation_dict(row) for row in rows)

    @staticmethod
    def _literal_like(query: str) -> str:
        return (
            query.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )

    def search(
        self,
        query: str,
        *,
        include_archived: bool = False,
    ) -> tuple[dict[str, Any], ...]:
        normalized = _bounded_text("query", query, maximum=512)
        archived_clause = "" if include_archived else "AND c.archived = 0"
        pattern = f"%{self._literal_like(normalized.lower())}%"
        connection = self.database.connect()
        try:
            rows = connection.execute(
                f"""SELECT DISTINCT c.* FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.conversation_id
                WHERE (
                    LOWER(c.title) LIKE ? ESCAPE '\\'
                    OR LOWER(m.content) LIKE ? ESCAPE '\\'
                ) {archived_clause}
                ORDER BY c.last_active_at DESC, c.conversation_id""",
                (pattern, pattern),
            ).fetchall()
        finally:
            connection.close()
        return tuple(self._conversation_dict(row) for row in rows)

    def _set_archive(self, conversation_id: str, archived: bool) -> None:
        identity = _uuid4("conversation_id", conversation_id)
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """UPDATE conversations
                SET archived = ?, last_active_at = ?
                WHERE conversation_id = ?""",
                (int(archived), self._current_time(), identity),
            )
            if cursor.rowcount != 1:
                raise DirectStoreConflict("Direct conversation is missing")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def archive(self, conversation_id: str) -> None:
        self._set_archive(conversation_id, True)

    def restore(self, conversation_id: str) -> None:
        self._set_archive(conversation_id, False)

    def _next_ordinal(
        self,
        connection: sqlite3.Connection,
        conversation_id: str,
    ) -> int:
        row = connection.execute(
            "SELECT COALESCE(MAX(ordinal), 0) AS ordinal FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        return int(row["ordinal"]) + 1

    def append_user(
        self,
        conversation_id: str,
        content: str,
        *,
        run_id: str,
    ) -> dict[str, Any]:
        identity = _uuid4("conversation_id", conversation_id)
        run = _uuid4("run_id", run_id)
        message = DirectMessage("user", content)
        message_id = str(uuid.uuid4())
        now = self._current_time()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            conversation = connection.execute(
                "SELECT archived FROM conversations WHERE conversation_id = ?",
                (identity,),
            ).fetchone()
            if conversation is None:
                raise DirectStoreConflict("Direct conversation is missing")
            if conversation["archived"]:
                raise DirectStoreConflict("Archived conversation is read-only")
            ordinal = self._next_ordinal(connection, identity)
            connection.execute(
                """INSERT INTO messages(
                    message_id, conversation_id, ordinal, role, content,
                    created_at, run_id, observation_id, display_state
                ) VALUES (?, ?, ?, 'user', ?, ?, ?, NULL, 'complete')""",
                (message_id, identity, ordinal, message.content, now, run),
            )
            connection.execute(
                "UPDATE conversations SET last_active_at = ? WHERE conversation_id = ?",
                (now, identity),
            )
            row = connection.execute(
                "SELECT * FROM messages WHERE message_id = ?",
                (message_id,),
            ).fetchone()
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise DirectStoreConflict("Direct message conflicts with history") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        if row is None:
            raise DirectStoreConflict("Direct message creation failed")
        return self._message_dict(row)

    def start_run(
        self,
        *,
        run_id: str,
        conversation_id: str,
        user_ordinal: int,
    ) -> dict[str, Any]:
        run = _uuid4("run_id", run_id)
        identity = _uuid4("conversation_id", conversation_id)
        if (
            isinstance(user_ordinal, bool)
            or not isinstance(user_ordinal, int)
            or user_ordinal < 1
        ):
            raise ValueError("user_ordinal must be positive")
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            conversation = connection.execute(
                "SELECT provider_id, model FROM conversations WHERE conversation_id = ?",
                (identity,),
            ).fetchone()
            message = connection.execute(
                """SELECT role, run_id FROM messages
                WHERE conversation_id = ? AND ordinal = ?""",
                (identity, user_ordinal),
            ).fetchone()
            if conversation is None or message is None:
                raise DirectStoreConflict("Direct run input is missing")
            if message["role"] != "user" or message["run_id"] != run:
                raise DirectStoreConflict("Direct run input does not match history")
            connection.execute(
                """INSERT INTO direct_runs(
                    run_id, conversation_id, provider_id, model,
                    user_ordinal, state, created_at, terminal_at,
                    failure_type, context_estimate, context_warning
                ) VALUES (?, ?, ?, ?, ?, 'created', ?, NULL, NULL, NULL, 0)""",
                (
                    run,
                    identity,
                    conversation["provider_id"],
                    conversation["model"],
                    user_ordinal,
                    self._current_time(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM direct_runs WHERE run_id = ?",
                (run,),
            ).fetchone()
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise DirectStoreConflict("Direct run identity already exists") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        if row is None:
            raise DirectStoreConflict("Direct run creation failed")
        return self._run_dict(row)

    def append_assistant_atomic(
        self,
        *,
        conversation_id: str,
        run_id: str,
        content: str,
        observation_id: str | None,
        context_estimate: int,
        context_warning: bool,
    ) -> dict[str, Any]:
        identity = _uuid4("conversation_id", conversation_id)
        run = _uuid4("run_id", run_id)
        message = DirectMessage("assistant", content)
        if observation_id is not None:
            observation_id = _bounded_text(
                "observation_id",
                observation_id,
                maximum=512,
            )
        if (
            isinstance(context_estimate, bool)
            or not isinstance(context_estimate, int)
            or context_estimate < 0
        ):
            raise ValueError("context_estimate must be non-negative")
        if not isinstance(context_warning, bool):
            raise ValueError("context_warning must be boolean")
        message_id = str(uuid.uuid4())
        now = self._current_time()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM direct_runs WHERE run_id = ?",
                (run,),
            ).fetchone()
            if row is None or row["conversation_id"] != identity:
                raise DirectStoreConflict("Direct run is missing")
            if row["state"] != "created" or row["terminal_at"] is not None:
                raise DirectStoreConflict("Direct run is already terminal")
            ordinal = self._next_ordinal(connection, identity)
            connection.execute(
                """INSERT INTO messages(
                    message_id, conversation_id, ordinal, role, content,
                    created_at, run_id, observation_id, display_state
                ) VALUES (?, ?, ?, 'assistant', ?, ?, ?, ?, 'complete')""",
                (
                    message_id,
                    identity,
                    ordinal,
                    message.content,
                    now,
                    run,
                    observation_id,
                ),
            )
            connection.execute(
                """UPDATE direct_runs
                SET state = 'completed', terminal_at = ?,
                    context_estimate = ?, context_warning = ?
                WHERE run_id = ?""",
                (now, context_estimate, int(context_warning), run),
            )
            connection.execute(
                """UPDATE conversations
                SET last_active_at = ?, last_context_estimate = ?, context_warning = ?
                WHERE conversation_id = ?""",
                (now, context_estimate, int(context_warning), identity),
            )
            inserted = connection.execute(
                "SELECT * FROM messages WHERE message_id = ?",
                (message_id,),
            ).fetchone()
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise DirectStoreConflict("Direct assistant message conflicts") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        if inserted is None:
            raise DirectStoreConflict("Direct assistant message creation failed")
        return self._message_dict(inserted)

    def fail_run(
        self,
        run_id: str,
        *,
        state: str,
        failure_type: str,
    ) -> None:
        run = _uuid4("run_id", run_id)
        if state not in {
            "refused_before_network",
            "failed_after_dispatch",
            "unsettled",
        }:
            raise ValueError("Direct failure state is invalid")
        failure = _bounded_text("failure_type", failure_type, maximum=128)
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state, terminal_at FROM direct_runs WHERE run_id = ?",
                (run,),
            ).fetchone()
            if row is None:
                raise DirectStoreConflict("Direct run is missing")
            if row["state"] != "created" or row["terminal_at"] is not None:
                raise DirectStoreConflict("Direct run is already terminal")
            connection.execute(
                """UPDATE direct_runs
                SET state = ?, terminal_at = ?, failure_type = ?
                WHERE run_id = ?""",
                (state, self._current_time(), failure, run),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def messages(self, conversation_id: str) -> tuple[dict[str, Any], ...]:
        identity = _uuid4("conversation_id", conversation_id)
        self.get(identity)
        connection = self.database.connect()
        try:
            rows = connection.execute(
                """SELECT * FROM messages
                WHERE conversation_id = ? ORDER BY ordinal""",
                (identity,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(self._message_dict(row) for row in rows)

    def read_run(self, run_id: str) -> dict[str, Any]:
        run = _uuid4("run_id", run_id)
        connection = self.database.connect()
        try:
            row = connection.execute(
                "SELECT * FROM direct_runs WHERE run_id = ?",
                (run,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise DirectStoreConflict("Direct run is missing")
        return self._run_dict(row)
