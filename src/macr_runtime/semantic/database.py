from __future__ import annotations

from ..agent.database import AgentDatabase
from .errors import SemanticRegistryMismatchError, SemanticSchemaUnsupportedError
from .registry import SemanticRegistry


class SemanticSchema:
    """Schema owner for Phase C semantic tables in the Agent database."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        database: AgentDatabase,
        *,
        registry: SemanticRegistry | None = None,
    ) -> None:
        if not isinstance(database, AgentDatabase):
            raise ValueError("database must be an AgentDatabase")
        self.database = database
        self.registry = (
            SemanticRegistry.from_builtin() if registry is None else registry
        )
        if not isinstance(self.registry, SemanticRegistry):
            raise ValueError("registry must be a SemanticRegistry")
        self._initialize()

    def _initialize(self) -> None:
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            for statement in _SEMANTIC_SCHEMA_STATEMENTS:
                connection.execute(statement)
            row = connection.execute(
                "SELECT version FROM schema_meta WHERE component = ?",
                ("agent_semantics",),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_meta(component, version) VALUES (?, ?)",
                    ("agent_semantics", self.SCHEMA_VERSION),
                )
            elif row["version"] != self.SCHEMA_VERSION:
                raise SemanticSchemaUnsupportedError(
                    "semantic database schema version is unsupported"
                )
            registry_json = self.registry.canonical_bytes().decode("utf-8")
            existing = connection.execute(
                "SELECT * FROM semantic_registry_versions "
                "WHERE registry_version = ?",
                (self.registry.registry_version,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO semantic_registry_versions(
                        registry_version, registry_digest, registry_json,
                        registered_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        self.registry.registry_version,
                        self.registry.registry_digest,
                        registry_json,
                        "1970-01-01T00:00:00+00:00",
                    ),
                )
            elif (
                existing["registry_digest"] != self.registry.registry_digest
                or existing["registry_json"] != registry_json
            ):
                raise SemanticRegistryMismatchError(
                    "stored semantic registry conflicts with builtin registry"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


_SEMANTIC_SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS semantic_registry_versions (
        registry_version TEXT PRIMARY KEY,
        registry_digest TEXT NOT NULL UNIQUE,
        registry_json TEXT NOT NULL,
        registered_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS semantic_graphs (
        graph_id TEXT PRIMARY KEY,
        graph_ref TEXT NOT NULL UNIQUE,
        scope_ref TEXT NOT NULL,
        current_revision INTEGER NOT NULL CHECK(current_revision >= 1),
        current_graph_digest TEXT NOT NULL,
        registry_version TEXT NOT NULL
            REFERENCES semantic_registry_versions(registry_version),
        registry_digest TEXT NOT NULL,
        created_by_agent_run_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        head_json TEXT NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS semantic_graphs_by_scope
    ON semantic_graphs(scope_ref, graph_id)""",
    """CREATE TABLE IF NOT EXISTS semantic_graph_revisions (
        graph_id TEXT NOT NULL REFERENCES semantic_graphs(graph_id),
        graph_revision INTEGER NOT NULL CHECK(graph_revision >= 1),
        graph_digest TEXT NOT NULL,
        parent_revision INTEGER,
        parent_graph_digest TEXT,
        patch_digest TEXT,
        registry_version TEXT NOT NULL,
        registry_digest TEXT NOT NULL,
        committed_at TEXT NOT NULL,
        revision_digest TEXT NOT NULL,
        revision_json TEXT NOT NULL,
        PRIMARY KEY(graph_id, graph_revision),
        UNIQUE(graph_id, graph_digest, graph_revision)
    )""",
    """CREATE TABLE IF NOT EXISTS semantic_graph_revision_nodes (
        graph_id TEXT NOT NULL,
        graph_revision INTEGER NOT NULL,
        node_id TEXT NOT NULL,
        record_digest TEXT NOT NULL,
        PRIMARY KEY(graph_id, graph_revision, node_id),
        FOREIGN KEY(graph_id, graph_revision)
            REFERENCES semantic_graph_revisions(graph_id, graph_revision)
            ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS semantic_graph_revision_relations (
        graph_id TEXT NOT NULL,
        graph_revision INTEGER NOT NULL,
        relation_id TEXT NOT NULL,
        relation_digest TEXT NOT NULL,
        PRIMARY KEY(graph_id, graph_revision, relation_id),
        FOREIGN KEY(graph_id, graph_revision)
            REFERENCES semantic_graph_revisions(graph_id, graph_revision)
            ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS semantic_nodes (
        graph_id TEXT NOT NULL REFERENCES semantic_graphs(graph_id),
        record_digest TEXT NOT NULL,
        node_id TEXT NOT NULL,
        content_digest TEXT NOT NULL,
        node_type TEXT NOT NULL,
        status TEXT NOT NULL,
        scope_ref TEXT NOT NULL,
        created_revision INTEGER NOT NULL CHECK(created_revision >= 2),
        record_json TEXT NOT NULL,
        PRIMARY KEY(graph_id, record_digest),
        UNIQUE(graph_id, node_id, record_digest)
    )""",
    """CREATE INDEX IF NOT EXISTS semantic_nodes_by_id
    ON semantic_nodes(graph_id, node_id, created_revision)""",
    """CREATE TABLE IF NOT EXISTS semantic_relations (
        graph_id TEXT NOT NULL REFERENCES semantic_graphs(graph_id),
        relation_digest TEXT NOT NULL,
        relation_id TEXT NOT NULL,
        source_ref TEXT NOT NULL,
        relation_type TEXT NOT NULL,
        target_ref TEXT NOT NULL,
        created_revision INTEGER NOT NULL CHECK(created_revision >= 2),
        relation_json TEXT NOT NULL,
        PRIMARY KEY(graph_id, relation_digest),
        UNIQUE(graph_id, relation_id, relation_digest)
    )""",
    """CREATE INDEX IF NOT EXISTS semantic_relations_by_endpoint
    ON semantic_relations(graph_id, source_ref, target_ref, created_revision)""",
    """CREATE TABLE IF NOT EXISTS semantic_events (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        semantic_event_id TEXT NOT NULL UNIQUE,
        graph_id TEXT NOT NULL REFERENCES semantic_graphs(graph_id),
        agent_run_id TEXT NOT NULL,
        graph_revision INTEGER NOT NULL CHECK(graph_revision >= 1),
        event_type TEXT NOT NULL,
        event_digest TEXT NOT NULL,
        event_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS semantic_events_by_graph
    ON semantic_events(graph_id, sequence)""",
    """CREATE TABLE IF NOT EXISTS semantic_patches (
        proposal_id TEXT PRIMARY KEY,
        proposal_digest TEXT NOT NULL UNIQUE,
        graph_id TEXT NOT NULL,
        agent_run_id TEXT NOT NULL,
        base_graph_revision INTEGER NOT NULL CHECK(base_graph_revision >= 1),
        base_graph_digest TEXT NOT NULL,
        registry_version TEXT NOT NULL,
        registry_digest TEXT NOT NULL,
        patch_id TEXT NOT NULL,
        patch_digest TEXT NOT NULL,
        proposal_json TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN (
            'proposed', 'validation_failed', 'committed'
        )),
        failure_code TEXT,
        created_at TEXT NOT NULL,
        terminal_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS semantic_commit_receipts (
        commit_id TEXT PRIMARY KEY,
        request_digest TEXT NOT NULL UNIQUE,
        proposal_id TEXT NOT NULL REFERENCES semantic_patches(proposal_id),
        proposal_digest TEXT NOT NULL,
        graph_id TEXT NOT NULL,
        graph_revision INTEGER NOT NULL CHECK(graph_revision >= 1),
        graph_digest TEXT NOT NULL,
        agent_run_id TEXT NOT NULL,
        agent_state_revision INTEGER NOT NULL CHECK(agent_state_revision >= 1),
        semantic_event_id TEXT NOT NULL UNIQUE,
        agent_event_id TEXT NOT NULL UNIQUE,
        patch_digest TEXT NOT NULL,
        receipt_digest TEXT NOT NULL,
        receipt_json TEXT NOT NULL,
        committed_at TEXT NOT NULL
    )""",
)
