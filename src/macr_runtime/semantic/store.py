from __future__ import annotations

import json
import re
from pathlib import PureWindowsPath

from .._v07_contracts import require_positive_int, require_uuid4
from ..agent.database import AgentDatabase
from ..canonical import canonical_json_bytes
from .database import SemanticSchema
from .errors import (
    SemanticGraphAlreadyExistsError,
    SemanticGraphDigestMismatchError,
    SemanticGraphNotFoundError,
)
from .graph import SemanticGraphHead, SemanticGraphRevision
from .registry import SemanticRegistry


_LOCAL_PATH_MARKER = re.compile(
    r"(?i)(?<![a-z0-9])(?:[a-z]:[\\/]|\\\\[^\\/\s]+[\\/])"
)


def _contains_local_path(value: str) -> bool:
    try:
        if PureWindowsPath(value.strip()).drive:
            return True
    except (OSError, ValueError):
        pass
    return bool(_LOCAL_PATH_MARKER.search(value))


def _json_text(value: object) -> str:
    return canonical_json_bytes(value).decode("utf-8")


class SemanticStore:
    def __init__(
        self,
        database: AgentDatabase,
        *,
        registry: SemanticRegistry | None = None,
    ) -> None:
        self.schema = SemanticSchema(database, registry=registry)
        self.database = database
        self.registry = self.schema.registry

    def create_graph(
        self,
        *,
        graph_id: str,
        scope_ref: str,
        created_by_agent_run_id: str,
        created_at: str,
    ) -> SemanticGraphHead:
        if not isinstance(scope_ref, str) or _contains_local_path(scope_ref):
            raise ValueError("semantic graph scope contains a path-like value")
        head = SemanticGraphHead.create_empty(
            graph_id=graph_id,
            scope_ref=scope_ref,
            registry=self.registry,
            created_by_agent_run_id=created_by_agent_run_id,
            created_at=created_at,
        )
        revision = SemanticGraphRevision.from_initial_head(head)
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            creator = connection.execute(
                "SELECT 1 FROM agent_runs WHERE agent_run_id = ?",
                (head.created_by_agent_run_id,),
            ).fetchone()
            if creator is None:
                raise SemanticGraphNotFoundError(
                    "semantic graph creator AgentRun was not found"
                )
            existing = connection.execute(
                "SELECT 1 FROM semantic_graphs WHERE graph_id = ?",
                (head.graph_id,),
            ).fetchone()
            if existing is not None:
                raise SemanticGraphAlreadyExistsError(
                    "semantic graph already exists"
                )
            connection.execute(
                """
                INSERT INTO semantic_graphs(
                    graph_id, graph_ref, scope_ref, current_revision,
                    current_graph_digest, registry_version, registry_digest,
                    created_by_agent_run_id, created_at, updated_at, head_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    head.graph_id,
                    head.graph_ref,
                    head.scope_ref,
                    head.graph_revision,
                    head.graph_digest,
                    head.registry_version,
                    head.registry_digest,
                    head.created_by_agent_run_id,
                    head.created_at,
                    head.updated_at,
                    _json_text(head.to_public_dict()),
                ),
            )
            connection.execute(
                """
                INSERT INTO semantic_graph_revisions(
                    graph_id, graph_revision, graph_digest, parent_revision,
                    parent_graph_digest, patch_digest, registry_version,
                    registry_digest, committed_at, revision_digest,
                    revision_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision.graph_id,
                    revision.graph_revision,
                    revision.graph_digest,
                    revision.parent_revision,
                    revision.parent_graph_digest,
                    revision.patch_digest,
                    revision.registry_version,
                    revision.registry_digest,
                    revision.committed_at,
                    revision.revision_digest,
                    _json_text(revision.to_public_dict()),
                ),
            )
            connection.commit()
            return head
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_graph_head(self, graph_id: str) -> SemanticGraphHead:
        selected = require_uuid4("graph_id", graph_id)
        connection = self.database.connect()
        try:
            row = connection.execute(
                "SELECT * FROM semantic_graphs WHERE graph_id = ?",
                (selected,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise SemanticGraphNotFoundError("semantic graph was not found")
        try:
            head = SemanticGraphHead.from_dict(json.loads(row["head_json"]))
        except Exception as exc:
            raise SemanticGraphDigestMismatchError(
                "semantic graph head record is invalid"
            ) from exc
        if (
            head.graph_id != row["graph_id"]
            or head.graph_revision != row["current_revision"]
            or head.graph_digest != row["current_graph_digest"]
            or head.registry_version != row["registry_version"]
            or head.registry_digest != row["registry_digest"]
        ):
            raise SemanticGraphDigestMismatchError(
                "semantic graph head projection conflicts"
            )
        return head

    def get_graph_revision(
        self,
        graph_id: str,
        graph_revision: int,
    ) -> SemanticGraphRevision:
        selected = require_uuid4("graph_id", graph_id)
        revision = require_positive_int("graph_revision", graph_revision)
        connection = self.database.connect()
        try:
            row = connection.execute(
                """
                SELECT revision_json FROM semantic_graph_revisions
                WHERE graph_id = ? AND graph_revision = ?
                """,
                (selected, revision),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise SemanticGraphNotFoundError(
                "semantic graph revision was not found"
            )
        try:
            return SemanticGraphRevision.from_dict(json.loads(row["revision_json"]))
        except Exception as exc:
            raise SemanticGraphDigestMismatchError(
                "semantic graph revision record is invalid"
            ) from exc

    def list_graphs(
        self,
        *,
        limit: int,
        after_graph_id: str | None = None,
    ) -> tuple[SemanticGraphHead, ...]:
        selected_limit = require_positive_int("limit", limit)
        if selected_limit > 128:
            raise ValueError("limit must not exceed 128")
        cursor = (
            None
            if after_graph_id is None
            else require_uuid4("after_graph_id", after_graph_id)
        )
        connection = self.database.connect()
        try:
            rows = connection.execute(
                """
                SELECT graph_id FROM semantic_graphs
                WHERE (? IS NULL OR graph_id > ?)
                ORDER BY graph_id
                LIMIT ?
                """,
                (cursor, cursor, selected_limit),
            ).fetchall()
        finally:
            connection.close()
        return tuple(self.get_graph_head(row["graph_id"]) for row in rows)
