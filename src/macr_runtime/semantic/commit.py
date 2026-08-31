from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .._v07_contracts import (
    canonical_record_digest,
    normalize_timestamp,
    require_positive_int,
    require_sha256,
    require_uuid4,
)
from ..agent.contracts import AgentRunState
from ..agent.ownership import AgentOwnershipPermit
from ..agent.semantic_binding import _AgentSemanticBindingPort
from ..agent.store import AgentStore
from ..canonical import canonical_json_bytes
from ..execution import AuthorizationReference
from .contracts import SemanticNode, SemanticRelation
from .errors import (
    SemanticAgentBindingConflictError,
    SemanticCommitAuthorityInvalidError,
    SemanticCommitPermitInvalidError,
    SemanticGraphDigestMismatchError,
    SemanticGraphHeadStaleError,
    SemanticPatchConflictError,
    SemanticPatchInvalidError,
)
from .graph import SemanticGraphHead, SemanticGraphRevision
from .patch import CompiledSemanticPatch, SemanticCommitRequest, SemanticPatchCompiler
from .service import SemanticProposalRecord
from .store import SemanticStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_text(value: object) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def ownership_permit_digest(permit: AgentOwnershipPermit) -> str:
    if not isinstance(permit, AgentOwnershipPermit):
        raise ValueError("permit must be an AgentOwnershipPermit")
    return canonical_record_digest(
        "macr.agent.ownership-permit.v1",
        {
            "agent_run_id": permit.agent_run_id,
            "owner_id": permit.owner_id,
            "lease_id": permit.lease_id,
            "fencing_token": permit.fencing_token,
            "epoch": permit.epoch,
            "revision": permit.revision,
            "acquired_at": permit.acquired_at,
            "expires_at": permit.expires_at,
        },
    )


@dataclass(frozen=True)
class SemanticCommitEvent:
    semantic_event_id: str
    graph_id: str
    graph_revision: int
    graph_digest: str
    agent_run_id: str
    proposal_digest: str
    patch_digest: str
    authorization_digest: str
    created_at: str
    event_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "semantic_event_id",
            require_uuid4("semantic_event_id", self.semantic_event_id),
        )
        object.__setattr__(self, "graph_id", require_uuid4("graph_id", self.graph_id))
        object.__setattr__(
            self,
            "graph_revision",
            require_positive_int("graph_revision", self.graph_revision),
        )
        object.__setattr__(
            self,
            "graph_digest",
            require_sha256("graph_digest", self.graph_digest),
        )
        object.__setattr__(
            self,
            "agent_run_id",
            require_uuid4("agent_run_id", self.agent_run_id),
        )
        object.__setattr__(
            self,
            "proposal_digest",
            require_sha256("proposal_digest", self.proposal_digest),
        )
        object.__setattr__(
            self,
            "patch_digest",
            require_sha256("patch_digest", self.patch_digest),
        )
        object.__setattr__(
            self,
            "authorization_digest",
            require_sha256("authorization_digest", self.authorization_digest),
        )
        object.__setattr__(
            self,
            "created_at",
            normalize_timestamp("created_at", self.created_at),
        )
        object.__setattr__(
            self,
            "event_digest",
            canonical_record_digest(
                "macr.semantic.commit-event.v1",
                self._identity_dict(),
            ),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "schema": "macr-semantic-commit-event/v1",
            "semantic_event_id": self.semantic_event_id,
            "event_type": "patch_committed",
            "graph_id": self.graph_id,
            "graph_revision": self.graph_revision,
            "graph_digest": self.graph_digest,
            "agent_run_id": self.agent_run_id,
            "proposal_digest": self.proposal_digest,
            "patch_digest": self.patch_digest,
            "authorization_digest": self.authorization_digest,
            "created_at": self.created_at,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "event_digest": self.event_digest}


@dataclass(frozen=True)
class SemanticCommitReceipt:
    commit_id: str
    request_digest: str
    proposal_id: str
    proposal_digest: str
    graph_id: str
    graph_revision: int
    graph_digest: str
    agent_run_id: str
    agent_state_revision: int
    semantic_event_id: str
    agent_event_id: str
    patch_digest: str
    committed_at: str
    receipt_digest: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "commit_id", "proposal_id", "graph_id", "agent_run_id",
            "semantic_event_id", "agent_event_id",
        ):
            object.__setattr__(self, name, require_uuid4(name, getattr(self, name)))
        for name in (
            "request_digest", "proposal_digest", "graph_digest", "patch_digest",
        ):
            object.__setattr__(self, name, require_sha256(name, getattr(self, name)))
        object.__setattr__(
            self,
            "graph_revision",
            require_positive_int("graph_revision", self.graph_revision),
        )
        object.__setattr__(
            self,
            "agent_state_revision",
            require_positive_int("agent_state_revision", self.agent_state_revision),
        )
        object.__setattr__(
            self,
            "committed_at",
            normalize_timestamp("committed_at", self.committed_at),
        )
        object.__setattr__(
            self,
            "receipt_digest",
            canonical_record_digest(
                "macr.semantic.commit-receipt.v1",
                self._identity_dict(),
            ),
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "schema": "macr-semantic-commit-receipt/v1",
            "commit_id": self.commit_id,
            "request_digest": self.request_digest,
            "proposal_id": self.proposal_id,
            "proposal_digest": self.proposal_digest,
            "graph_id": self.graph_id,
            "graph_revision": self.graph_revision,
            "graph_digest": self.graph_digest,
            "agent_run_id": self.agent_run_id,
            "agent_state_revision": self.agent_state_revision,
            "semantic_event_id": self.semantic_event_id,
            "agent_event_id": self.agent_event_id,
            "patch_digest": self.patch_digest,
            "committed_at": self.committed_at,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "receipt_digest": self.receipt_digest}


class SemanticCommitService:
    """Sole host/runtime owner of cross-component semantic commits."""

    def __init__(
        self,
        agent_store: AgentStore,
        semantic_store: SemanticStore,
        *,
        now: Callable[[], datetime] = _utc_now,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        if not isinstance(agent_store, AgentStore):
            raise ValueError("agent_store must be an AgentStore")
        if not isinstance(semantic_store, SemanticStore):
            raise ValueError("semantic_store must be a SemanticStore")
        if agent_store.database.path != semantic_store.database.path:
            raise ValueError("Agent and semantic stores must share one database")
        self.agent_store = agent_store
        self.semantic_store = semantic_store
        self.database = agent_store.database
        self.registry = semantic_store.registry
        self.compiler = SemanticPatchCompiler(self.registry)
        self._agent_binding = _AgentSemanticBindingPort(agent_store)
        self._now = now
        self._fault_injector = fault_injector

    def _time(self) -> str:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("semantic commit clock must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()

    def _fault(self, marker: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(marker)

    def _validate_agent(
        self,
        connection: sqlite3.Connection,
        *,
        agent_run_id: str,
        expected_revision: int,
        expected_epoch: int,
        permit: AgentOwnershipPermit,
        authorization_reference: AuthorizationReference,
        observed_at: str,
    ):
        row = connection.execute(
            "SELECT * FROM agent_runs WHERE agent_run_id = ?",
            (agent_run_id,),
        ).fetchone()
        if row is None:
            raise SemanticAgentBindingConflictError("AgentRun was not found")
        current = self.agent_store._projection_from_row(row)
        self.agent_store._require_matching_tail(connection, current)
        if current.state is not AgentRunState.ACTIVE:
            raise SemanticCommitPermitInvalidError("AgentRun is not active")
        if current.state_revision != expected_revision or current.epoch != expected_epoch:
            raise SemanticCommitPermitInvalidError(
                "AgentRun revision or epoch is stale"
            )
        ownership = connection.execute(
            "SELECT * FROM agent_ownership WHERE agent_run_id = ?",
            (agent_run_id,),
        ).fetchone()
        try:
            self.agent_store._require_permit_row(
                ownership,
                permit,
                observed_at=observed_at,
            )
        except Exception as exc:
            raise SemanticCommitPermitInvalidError(
                "Agent ownership permit is invalid"
            ) from exc
        if permit.agent_run_id != agent_run_id:
            raise SemanticCommitPermitInvalidError(
                "Agent ownership permit targets another run"
            )
        if authorization_reference != current.initial_header.authority.reference:
            raise SemanticCommitAuthorityInvalidError(
                "external semantic commit authority is invalid"
            )
        return current, self.agent_store._semantic_binding_from_row(row)

    def attach_graph(
        self,
        *,
        agent_run_id: str,
        graph_id: str,
        graph_revision: int,
        graph_digest: str,
        expected_agent_revision: int,
        expected_agent_epoch: int,
        permit: AgentOwnershipPermit,
        authorization_reference: AuthorizationReference,
        operation_id: str,
        agent_event_id: str,
    ):
        timestamp = self._time()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current, binding = self._validate_agent(
                connection,
                agent_run_id=agent_run_id,
                expected_revision=expected_agent_revision,
                expected_epoch=expected_agent_epoch,
                permit=permit,
                authorization_reference=authorization_reference,
                observed_at=timestamp,
            )
            head = self._head_on_connection(connection, graph_id)
            if head.graph_revision != graph_revision or head.graph_digest != graph_digest:
                raise SemanticGraphHeadStaleError(
                    "semantic graph attach head is stale"
                )
            target = head.to_semantic_state_binding()
            if binding == target:
                connection.commit()
                return current
            if binding is not None:
                raise SemanticAgentBindingConflictError(
                    "AgentRun is already bound to another semantic head"
                )
            event, _ = self._agent_binding._build_event(
                current=current,
                previous_binding=None,
                new_binding=target,
                operation_kind="attach",
                operation_id=operation_id,
                proposal_digest=None,
                patch_digest=None,
                registry_digest=head.registry_digest,
                authorization_digest=authorization_reference.digest,
                created_at=timestamp,
                event_id=agent_event_id,
            )
            next_projection = self._agent_binding._commit_on_connection(
                connection,
                current=current,
                event=event,
                new_binding=target,
                expected_revision=expected_agent_revision,
                expected_epoch=expected_agent_epoch,
            )
            connection.commit()
            return next_projection
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def commit_patch(
        self,
        request: SemanticCommitRequest,
        *,
        permit: AgentOwnershipPermit,
        semantic_event_id: str,
        agent_event_id: str,
    ) -> SemanticCommitReceipt:
        if not isinstance(request, SemanticCommitRequest):
            raise ValueError("request must be a SemanticCommitRequest")
        if ownership_permit_digest(permit) != request.ownership_permit_digest:
            raise SemanticCommitPermitInvalidError(
                "semantic commit permit digest does not match"
            )
        timestamp = self._time()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM semantic_commit_receipts WHERE commit_id = ?",
                (request.commit_id,),
            ).fetchone()
            if existing is not None:
                receipt = self._receipt_from_row(existing)
                if receipt.request_digest != request.request_digest:
                    raise SemanticPatchConflictError(
                        "semantic commit ID conflicts with existing receipt"
                    )
                connection.commit()
                return receipt

            current, current_binding = self._validate_agent(
                connection,
                agent_run_id=request.agent_run_id,
                expected_revision=request.expected_agent_revision,
                expected_epoch=request.expected_agent_epoch,
                permit=permit,
                authorization_reference=request.authorization_reference,
                observed_at=timestamp,
            )
            head = self._head_on_connection(connection, request.graph_id)
            if (
                head.graph_revision != request.base_graph_revision
                or head.graph_digest != request.base_graph_digest
                or head.registry_version != request.registry_version
                or head.registry_digest != request.registry_digest
            ):
                raise SemanticGraphHeadStaleError("semantic graph commit head is stale")
            if current_binding != head.to_semantic_state_binding():
                raise SemanticAgentBindingConflictError(
                    "AgentRun is not pinned to semantic commit base"
                )
            proposal_row = connection.execute(
                "SELECT * FROM semantic_patches WHERE proposal_id = ?",
                (request.proposal_id,),
            ).fetchone()
            if proposal_row is None:
                raise SemanticPatchInvalidError("semantic proposal was not found")
            proposal_record = self.semantic_store._proposal_from_row(proposal_row)
            if (
                proposal_record.state != "proposed"
                or proposal_record.proposal.proposal_digest != request.proposal_digest
                or proposal_record.proposal.patch != request.patch
            ):
                raise SemanticPatchInvalidError(
                    "stored semantic proposal does not match commit request"
                )
            active_nodes = self._active_nodes_on_connection(
                connection, head.graph_id, head.graph_revision
            )
            active_relations = self._active_relations_on_connection(
                connection, head.graph_id, head.graph_revision
            )
            compiled = self.compiler.compile(
                head=head,
                proposal=proposal_record.proposal,
                active_nodes=active_nodes,
                active_relations=active_relations,
            )
            if compiled.compiled_digest != proposal_record.compiled_digest:
                raise SemanticPatchInvalidError(
                    "semantic proposal compilation has drifted"
                )
            semantic_event = SemanticCommitEvent(
                semantic_event_id=semantic_event_id,
                graph_id=head.graph_id,
                graph_revision=compiled.next_graph_revision,
                graph_digest=compiled.next_graph_digest,
                agent_run_id=request.agent_run_id,
                proposal_digest=request.proposal_digest,
                patch_digest=request.patch.patch_digest,
                authorization_digest=request.authorization_reference.digest,
                created_at=timestamp,
            )
            next_head, revision = self._write_compiled(
                connection,
                head=head,
                request=request,
                compiled=compiled,
                event=semantic_event,
                committed_at=timestamp,
            )
            self._fault("after_semantic_records")
            cursor = connection.execute(
                """
                UPDATE semantic_graph_heads
                SET current_revision = ?, current_graph_digest = ?,
                    updated_at = ?, head_json = ?
                WHERE graph_id = ? AND current_revision = ?
                  AND current_graph_digest = ?
                """,
                (
                    next_head.graph_revision,
                    next_head.graph_digest,
                    next_head.updated_at,
                    _json_text(next_head.to_public_dict()),
                    head.graph_id,
                    head.graph_revision,
                    head.graph_digest,
                ),
            )
            if cursor.rowcount != 1:
                raise SemanticGraphHeadStaleError(
                    "semantic graph head compare-and-swap failed"
                )
            self._fault("after_graph_head")
            next_binding = next_head.to_semantic_state_binding()
            agent_event, _ = self._agent_binding._build_event(
                current=current,
                previous_binding=current_binding,
                new_binding=next_binding,
                operation_kind="commit",
                operation_id=request.commit_id,
                proposal_digest=request.proposal_digest,
                patch_digest=request.patch.patch_digest,
                registry_digest=request.registry_digest,
                authorization_digest=request.authorization_reference.digest,
                created_at=timestamp,
                event_id=agent_event_id,
            )
            next_agent = self._agent_binding._commit_on_connection(
                connection,
                current=current,
                event=agent_event,
                new_binding=next_binding,
                expected_revision=request.expected_agent_revision,
                expected_epoch=request.expected_agent_epoch,
                fault_injector=self._fault,
            )
            connection.execute(
                """
                UPDATE semantic_patches
                SET state = 'committed', terminal_at = ?
                WHERE proposal_id = ? AND state = 'proposed'
                """,
                (timestamp, request.proposal_id),
            )
            self._fault("before_receipt")
            receipt = SemanticCommitReceipt(
                commit_id=request.commit_id,
                request_digest=request.request_digest,
                proposal_id=request.proposal_id,
                proposal_digest=request.proposal_digest,
                graph_id=next_head.graph_id,
                graph_revision=next_head.graph_revision,
                graph_digest=next_head.graph_digest,
                agent_run_id=request.agent_run_id,
                agent_state_revision=next_agent.state_revision,
                semantic_event_id=semantic_event.semantic_event_id,
                agent_event_id=agent_event.event_id,
                patch_digest=request.patch.patch_digest,
                committed_at=timestamp,
            )
            connection.execute(
                """
                INSERT INTO semantic_commit_receipts(
                    commit_id, request_digest, proposal_id, proposal_digest,
                    graph_id, graph_revision, graph_digest, agent_run_id,
                    agent_state_revision, semantic_event_id, agent_event_id,
                    patch_digest, receipt_digest, receipt_json, committed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt.commit_id,
                    receipt.request_digest,
                    receipt.proposal_id,
                    receipt.proposal_digest,
                    receipt.graph_id,
                    receipt.graph_revision,
                    receipt.graph_digest,
                    receipt.agent_run_id,
                    receipt.agent_state_revision,
                    receipt.semantic_event_id,
                    receipt.agent_event_id,
                    receipt.patch_digest,
                    receipt.receipt_digest,
                    _json_text(receipt.to_public_dict()),
                    receipt.committed_at,
                ),
            )
            self._fault("before_commit")
            connection.commit()
            return receipt
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _head_on_connection(
        self,
        connection: sqlite3.Connection,
        graph_id: str,
    ) -> SemanticGraphHead:
        row = connection.execute(
            """
            SELECT h.head_json FROM semantic_graph_heads AS h
            WHERE h.graph_id = ?
            """,
            (graph_id,),
        ).fetchone()
        if row is None:
            raise SemanticGraphHeadStaleError("semantic graph head is missing")
        try:
            return SemanticGraphHead.from_dict(json.loads(row["head_json"]))
        except Exception as exc:
            raise SemanticGraphDigestMismatchError(
                "semantic graph head is invalid"
            ) from exc

    @staticmethod
    def _active_nodes_on_connection(connection, graph_id, revision):
        rows = connection.execute(
            """
            SELECT n.record_json
            FROM semantic_graph_revision_nodes AS m
            JOIN semantic_nodes AS n
              ON n.graph_id = m.graph_id AND n.record_digest = m.record_digest
            WHERE m.graph_id = ? AND m.graph_revision = ?
            ORDER BY m.record_digest
            """,
            (graph_id, revision),
        ).fetchall()
        return tuple(SemanticNode.from_dict(json.loads(row["record_json"])) for row in rows)

    @staticmethod
    def _active_relations_on_connection(connection, graph_id, revision):
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
            (graph_id, revision),
        ).fetchall()
        return tuple(
            SemanticRelation.from_dict(json.loads(row["relation_json"]))
            for row in rows
        )

    def _write_compiled(
        self,
        connection,
        *,
        head,
        request,
        compiled: CompiledSemanticPatch,
        event: SemanticCommitEvent,
        committed_at: str,
    ):
        for node in compiled.added_nodes:
            text = _json_text(node.to_public_dict())
            existing = connection.execute(
                "SELECT record_json FROM semantic_nodes "
                "WHERE graph_id = ? AND record_digest = ?",
                (head.graph_id, node.record_digest),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO semantic_nodes(
                        graph_id, record_digest, node_id, content_digest,
                        node_type, status, scope_ref, created_revision,
                        record_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        head.graph_id, node.record_digest, node.node_id,
                        node.content_digest, node.node_type.value,
                        node.status.value, node.scope_ref,
                        compiled.next_graph_revision, text,
                    ),
                )
            elif existing["record_json"] != text:
                raise SemanticPatchConflictError(
                    "semantic node digest conflicts with existing record"
                )
        for relation in compiled.added_relations:
            text = _json_text(relation.to_public_dict())
            existing = connection.execute(
                "SELECT relation_json FROM semantic_relations "
                "WHERE graph_id = ? AND relation_digest = ?",
                (head.graph_id, relation.relation_digest),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO semantic_relations(
                        graph_id, relation_digest, relation_id, source_ref,
                        relation_type, target_ref, created_revision,
                        relation_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        head.graph_id, relation.relation_digest,
                        relation.relation_id, relation.source_ref,
                        relation.relation_type.value, relation.target_ref,
                        compiled.next_graph_revision, text,
                    ),
                )
            elif existing["relation_json"] != text:
                raise SemanticPatchConflictError(
                    "semantic relation digest conflicts with existing record"
                )
        next_head = SemanticGraphHead(
            graph_id=head.graph_id,
            scope_ref=head.scope_ref,
            graph_revision=compiled.next_graph_revision,
            registry_version=head.registry_version,
            registry_digest=head.registry_digest,
            active_node_record_digests=tuple(
                item.record_digest for item in compiled.active_nodes
            ),
            active_relation_digests=tuple(
                item.relation_digest for item in compiled.active_relations
            ),
            created_by_agent_run_id=head.created_by_agent_run_id,
            created_at=head.created_at,
            updated_at=committed_at,
        )
        revision = SemanticGraphRevision(
            graph_id=head.graph_id,
            graph_revision=compiled.next_graph_revision,
            graph_digest=compiled.next_graph_digest,
            parent_revision=head.graph_revision,
            parent_graph_digest=head.graph_digest,
            patch_digest=request.patch.patch_digest,
            registry_version=head.registry_version,
            registry_digest=head.registry_digest,
            active_node_record_digests=next_head.active_node_record_digests,
            active_relation_digests=next_head.active_relation_digests,
            committed_at=committed_at,
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
                revision.graph_id, revision.graph_revision,
                revision.graph_digest, revision.parent_revision,
                revision.parent_graph_digest, revision.patch_digest,
                revision.registry_version, revision.registry_digest,
                revision.committed_at, revision.revision_digest,
                _json_text(revision.to_public_dict()),
            ),
        )
        for node in compiled.active_nodes:
            connection.execute(
                """
                INSERT INTO semantic_graph_revision_nodes(
                    graph_id, graph_revision, node_id, record_digest
                ) VALUES (?, ?, ?, ?)
                """,
                (head.graph_id, compiled.next_graph_revision, node.node_id, node.record_digest),
            )
        for relation in compiled.active_relations:
            connection.execute(
                """
                INSERT INTO semantic_graph_revision_relations(
                    graph_id, graph_revision, relation_id, relation_digest
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    head.graph_id, compiled.next_graph_revision,
                    relation.relation_id, relation.relation_digest,
                ),
            )
        connection.execute(
            """
            INSERT INTO semantic_events(
                semantic_event_id, graph_id, agent_run_id, graph_revision,
                event_type, event_digest, event_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.semantic_event_id, event.graph_id, event.agent_run_id,
                event.graph_revision, "patch_committed", event.event_digest,
                _json_text(event.to_public_dict()), event.created_at,
            ),
        )
        return next_head, revision

    @staticmethod
    def _receipt_from_row(row) -> SemanticCommitReceipt:
        try:
            data = json.loads(row["receipt_json"])
            receipt = SemanticCommitReceipt(
                commit_id=data["commit_id"],
                request_digest=data["request_digest"],
                proposal_id=data["proposal_id"],
                proposal_digest=data["proposal_digest"],
                graph_id=data["graph_id"],
                graph_revision=data["graph_revision"],
                graph_digest=data["graph_digest"],
                agent_run_id=data["agent_run_id"],
                agent_state_revision=data["agent_state_revision"],
                semantic_event_id=data["semantic_event_id"],
                agent_event_id=data["agent_event_id"],
                patch_digest=data["patch_digest"],
                committed_at=data["committed_at"],
            )
            if receipt.receipt_digest != data["receipt_digest"]:
                raise ValueError("receipt digest mismatch")
            return receipt
        except Exception as exc:
            raise SemanticPatchConflictError(
                "stored semantic commit receipt is invalid"
            ) from exc
