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
from .contracts import SemanticNode, SemanticRelation
from .patch import SemanticPatchProposalRequest
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
                    graph_id, graph_ref, scope_ref, registry_version,
                    registry_digest, created_by_agent_run_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    head.graph_id,
                    head.graph_ref,
                    head.scope_ref,
                    head.registry_version,
                    head.registry_digest,
                    head.created_by_agent_run_id,
                    head.created_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO semantic_graph_heads(
                    graph_id, current_revision, current_graph_digest,
                    updated_at, head_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    head.graph_id,
                    head.graph_revision,
                    head.graph_digest,
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
                """
                SELECT g.graph_id, g.graph_ref, g.scope_ref,
                       g.registry_version, g.registry_digest,
                       g.created_by_agent_run_id, g.created_at,
                       h.current_revision, h.current_graph_digest,
                       h.updated_at, h.head_json
                FROM semantic_graphs AS g
                JOIN semantic_graph_heads AS h ON h.graph_id = g.graph_id
                WHERE g.graph_id = ?
                """,
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

    def rebuild_graph_head(self, graph_id: str) -> SemanticGraphHead:
        selected = require_uuid4("graph_id", graph_id)
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            graph = connection.execute(
                "SELECT * FROM semantic_graphs WHERE graph_id = ?",
                (selected,),
            ).fetchone()
            if graph is None:
                raise SemanticGraphNotFoundError("semantic graph was not found")
            revision_row = connection.execute(
                """
                SELECT graph_revision FROM semantic_graph_revisions
                WHERE graph_id = ?
                ORDER BY graph_revision DESC
                LIMIT 1
                """,
                (selected,),
            ).fetchone()
            if revision_row is None:
                raise SemanticGraphNotFoundError(
                    "semantic graph has no immutable revision"
                )
            revision = self._revision_on_connection(
                connection,
                selected,
                revision_row["graph_revision"],
            )
            head = SemanticGraphHead(
                graph_id=graph["graph_id"],
                scope_ref=graph["scope_ref"],
                graph_revision=revision.graph_revision,
                registry_version=graph["registry_version"],
                registry_digest=graph["registry_digest"],
                active_node_record_digests=revision.active_node_record_digests,
                active_relation_digests=revision.active_relation_digests,
                created_by_agent_run_id=graph["created_by_agent_run_id"],
                created_at=graph["created_at"],
                updated_at=revision.committed_at,
            )
            if head.graph_digest != revision.graph_digest:
                raise SemanticGraphDigestMismatchError(
                    "semantic graph revision cannot rebuild head"
                )
            connection.execute(
                "DELETE FROM semantic_graph_heads WHERE graph_id = ?",
                (selected,),
            )
            connection.execute(
                """
                INSERT INTO semantic_graph_heads(
                    graph_id, current_revision, current_graph_digest,
                    updated_at, head_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    head.graph_id,
                    head.graph_revision,
                    head.graph_digest,
                    head.updated_at,
                    _json_text(head.to_public_dict()),
                ),
            )
            connection.commit()
            return head
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_graph_revision(
        self,
        graph_id: str,
        graph_revision: int,
    ) -> SemanticGraphRevision:
        selected = require_uuid4("graph_id", graph_id)
        revision = require_positive_int("graph_revision", graph_revision)
        connection = self.database.connect()
        try:
            return self._revision_on_connection(connection, selected, revision)
        finally:
            connection.close()

    @staticmethod
    def _revision_on_connection(
        connection,
        graph_id: str,
        graph_revision: int,
    ) -> SemanticGraphRevision:
        row = connection.execute(
            """
            SELECT * FROM semantic_graph_revisions
            WHERE graph_id = ? AND graph_revision = ?
            """,
            (graph_id, graph_revision),
        ).fetchone()
        if row is None:
            raise SemanticGraphNotFoundError(
                "semantic graph revision was not found"
            )
        try:
            node_rows = connection.execute(
                """
                SELECT m.node_id, m.record_digest, n.record_json
                FROM semantic_graph_revision_nodes AS m
                LEFT JOIN semantic_nodes AS n
                  ON n.graph_id = m.graph_id
                 AND n.record_digest = m.record_digest
                WHERE m.graph_id = ? AND m.graph_revision = ?
                ORDER BY m.record_digest
                """,
                (graph_id, graph_revision),
            ).fetchall()
            relation_rows = connection.execute(
                """
                SELECT m.relation_id, m.relation_digest, r.relation_json
                FROM semantic_graph_revision_relations AS m
                LEFT JOIN semantic_relations AS r
                  ON r.graph_id = m.graph_id
                 AND r.relation_digest = m.relation_digest
                WHERE m.graph_id = ? AND m.graph_revision = ?
                ORDER BY m.relation_digest
                """,
                (graph_id, graph_revision),
            ).fetchall()
            observed = SemanticGraphRevision.from_dict(
                json.loads(row["revision_json"])
            )
            for name in (
                "graph_id",
                "graph_revision",
                "graph_digest",
                "parent_revision",
                "parent_graph_digest",
                "patch_digest",
                "registry_version",
                "registry_digest",
                "committed_at",
                "revision_digest",
            ):
                if row[name] != getattr(observed, name):
                    raise ValueError(f"semantic revision column mismatch: {name}")
            node_digests = tuple(item["record_digest"] for item in node_rows)
            relation_digests = tuple(
                item["relation_digest"] for item in relation_rows
            )
            if node_digests != observed.active_node_record_digests:
                raise ValueError("semantic node membership conflicts with revision")
            if relation_digests != observed.active_relation_digests:
                raise ValueError("semantic relation membership conflicts with revision")
            for item in node_rows:
                node = SemanticNode.from_dict(json.loads(item["record_json"]))
                if (
                    node.node_id != item["node_id"]
                    or node.record_digest != item["record_digest"]
                ):
                    raise ValueError("semantic node membership record mismatch")
            for item in relation_rows:
                relation = SemanticRelation.from_dict(
                    json.loads(item["relation_json"])
                )
                if (
                    relation.relation_id != item["relation_id"]
                    or relation.relation_digest != item["relation_digest"]
                ):
                    raise ValueError("semantic relation membership record mismatch")
            return observed
        except Exception as exc:
            raise SemanticGraphDigestMismatchError(
                "semantic graph revision record is invalid"
            ) from exc

    @staticmethod
    def _active_nodes_on_connection(
        connection,
        graph_id: str,
        graph_revision: int,
    ) -> tuple[SemanticNode, ...]:
        rows = connection.execute(
            """
            SELECT n.record_json
            FROM semantic_graph_revision_nodes AS m
            JOIN semantic_nodes AS n
              ON n.graph_id = m.graph_id
             AND n.record_digest = m.record_digest
            WHERE m.graph_id = ? AND m.graph_revision = ?
            ORDER BY m.record_digest
            """,
            (graph_id, graph_revision),
        ).fetchall()
        try:
            return tuple(
                SemanticNode.from_dict(json.loads(row["record_json"]))
                for row in rows
            )
        except Exception as exc:
            raise SemanticGraphDigestMismatchError(
                "semantic node membership is invalid"
            ) from exc

    @staticmethod
    def _active_relations_on_connection(
        connection,
        graph_id: str,
        graph_revision: int,
    ) -> tuple[SemanticRelation, ...]:
        rows = connection.execute(
            """
            SELECT r.relation_json
            FROM semantic_graph_revision_relations AS m
            JOIN semantic_relations AS r
              ON r.graph_id = m.graph_id
             AND r.relation_digest = m.relation_digest
            WHERE m.graph_id = ? AND m.graph_revision = ?
            ORDER BY m.relation_digest
            """,
            (graph_id, graph_revision),
        ).fetchall()
        try:
            return tuple(
                SemanticRelation.from_dict(json.loads(row["relation_json"]))
                for row in rows
            )
        except Exception as exc:
            raise SemanticGraphDigestMismatchError(
                "semantic relation membership is invalid"
            ) from exc

    def _graph_snapshot_on_connection(
        self,
        connection,
        graph_id: str,
        graph_revision: int,
    ) -> tuple[
        SemanticGraphRevision,
        tuple[SemanticNode, ...],
        tuple[SemanticRelation, ...],
    ]:
        revision = self._revision_on_connection(
            connection, graph_id, graph_revision
        )
        nodes = self._active_nodes_on_connection(
            connection, graph_id, graph_revision
        )
        relations = self._active_relations_on_connection(
            connection, graph_id, graph_revision
        )
        if tuple(item.record_digest for item in nodes) != revision.active_node_record_digests:
            raise SemanticGraphDigestMismatchError(
                "semantic node snapshot conflicts with revision"
            )
        if tuple(item.relation_digest for item in relations) != revision.active_relation_digests:
            raise SemanticGraphDigestMismatchError(
                "semantic relation snapshot conflicts with revision"
            )
        return revision, nodes, relations

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

    def get_active_nodes(
        self,
        graph_id: str,
        *,
        graph_revision: int | None = None,
    ) -> tuple[SemanticNode, ...]:
        head = self.get_graph_head(graph_id)
        revision = (
            head.graph_revision
            if graph_revision is None
            else require_positive_int("graph_revision", graph_revision)
        )
        connection = self.database.connect()
        try:
            return self._active_nodes_on_connection(
                connection, head.graph_id, revision
            )
        finally:
            connection.close()

    def get_active_relations(
        self,
        graph_id: str,
        *,
        graph_revision: int | None = None,
    ) -> tuple[SemanticRelation, ...]:
        head = self.get_graph_head(graph_id)
        revision = (
            head.graph_revision
            if graph_revision is None
            else require_positive_int("graph_revision", graph_revision)
        )
        connection = self.database.connect()
        try:
            return self._active_relations_on_connection(
                connection, head.graph_id, revision
            )
        finally:
            connection.close()

    def save_proposal(self, record: "SemanticProposalRecord") -> "SemanticProposalRecord":
        from .service import SemanticProposalRecord

        if not isinstance(record, SemanticProposalRecord):
            raise ValueError("record must be a SemanticProposalRecord")
        proposal = record.proposal
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM semantic_patches WHERE proposal_id = ?",
                (proposal.proposal_id,),
            ).fetchone()
            if existing is not None:
                observed = self._proposal_from_row(existing)
                if observed == record:
                    connection.commit()
                    return observed
                raise SemanticPatchConflictError(
                    "semantic proposal ID conflicts with existing record"
                )
            connection.execute(
                """
                INSERT INTO semantic_patches(
                    proposal_id, proposal_digest, graph_id, agent_run_id,
                    base_graph_revision, base_graph_digest, registry_version,
                    registry_digest, patch_id, patch_digest, proposal_json,
                    compiled_digest, state, failure_code, created_at, terminal_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.proposal_id,
                    proposal.proposal_digest,
                    proposal.graph_id,
                    proposal.agent_run_id,
                    proposal.base_graph_revision,
                    proposal.base_graph_digest,
                    proposal.registry_version,
                    proposal.registry_digest,
                    proposal.patch.patch_id,
                    proposal.patch.patch_digest,
                    _json_text(proposal.to_public_dict()),
                    record.compiled_digest,
                    record.state,
                    record.failure_code,
                    record.created_at,
                    record.terminal_at,
                ),
            )
            connection.commit()
            return record
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_proposal(self, proposal_id: str) -> "SemanticProposalRecord":
        selected = require_uuid4("proposal_id", proposal_id)
        connection = self.database.connect()
        try:
            row = connection.execute(
                "SELECT * FROM semantic_patches WHERE proposal_id = ?",
                (selected,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise SemanticGraphNotFoundError("semantic proposal was not found")
        return self._proposal_from_row(row)

    @staticmethod
    def _proposal_from_row(row) -> "SemanticProposalRecord":
        from .service import SemanticProposalRecord

        try:
            proposal = SemanticPatchProposalRequest.from_dict(
                json.loads(row["proposal_json"])
            )
            return SemanticProposalRecord(
                proposal=proposal,
                state=row["state"],
                compiled_digest=row["compiled_digest"],
                failure_code=row["failure_code"],
                created_at=row["created_at"],
                terminal_at=row["terminal_at"],
            )
        except Exception as exc:
            raise SemanticPatchConflictError(
                "stored semantic proposal is invalid"
            ) from exc
