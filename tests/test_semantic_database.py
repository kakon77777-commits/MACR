from __future__ import annotations

import multiprocessing
import unittest

from macr_runtime.agent.database import AgentDatabase
from macr_runtime.semantic.database import SemanticSchema
from macr_runtime.semantic.errors import (
    SemanticRegistryMismatchError,
    SemanticSchemaUnsupportedError,
)
from macr_runtime.semantic.registry import SemanticRegistry
from tests.support import d_drive_tempdir


SEMANTIC_TABLES = {
    "semantic_registry_versions",
    "semantic_graphs",
    "semantic_graph_heads",
    "semantic_graph_revisions",
    "semantic_graph_revision_nodes",
    "semantic_graph_revision_relations",
    "semantic_nodes",
    "semantic_relations",
    "semantic_events",
    "semantic_patches",
    "semantic_attach_receipts",
    "semantic_commit_receipts",
}


def _semantic_bootstrap_worker(path: str, start_event, results) -> None:
    start_event.wait(timeout=30)
    try:
        database = AgentDatabase(path)
        schema = SemanticSchema(database)
        connection = database.connect()
        try:
            versions = tuple(
                tuple(row)
                for row in connection.execute(
                    "SELECT component, version FROM schema_meta ORDER BY component"
                )
            )
        finally:
            connection.close()
        results.put(("ok", schema.SCHEMA_VERSION, versions))
    except Exception as exc:  # pragma: no cover - parent reports exact failure
        results.put((type(exc).__name__, str(exc)))


class SemanticDatabaseTests(unittest.TestCase):
    def test_semantic_schema_shares_agent_database_and_has_exact_component_tables(self) -> None:
        with d_drive_tempdir() as temp:
            path = temp / "agent.sqlite3"
            database = AgentDatabase(path)
            schema = SemanticSchema(database)
            connection = database.connect()
            try:
                versions = {
                    row["component"]: row["version"]
                    for row in connection.execute(
                        "SELECT component, version FROM schema_meta"
                    )
                }
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type = 'table' AND name LIKE 'semantic_%'"
                    )
                }
                journal = connection.execute("PRAGMA journal_mode").fetchone()[0]
            finally:
                connection.close()

        self.assertIs(schema.database, database)
        self.assertEqual(versions, {"agent_runtime": 2, "agent_semantics": 1})
        self.assertEqual(tables, SEMANTIC_TABLES)
        self.assertEqual(journal.lower(), "wal")

    def test_builtin_registry_is_create_once_and_byte_exact(self) -> None:
        registry = SemanticRegistry.from_builtin()
        with d_drive_tempdir() as temp:
            database = AgentDatabase(temp / "agent.sqlite3")
            SemanticSchema(database, registry=registry)
            SemanticSchema(database, registry=registry)
            connection = database.connect()
            try:
                rows = connection.execute(
                    "SELECT registry_version, registry_digest, registry_json "
                    "FROM semantic_registry_versions"
                ).fetchall()
            finally:
                connection.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["registry_version"], registry.registry_version)
        self.assertEqual(rows[0]["registry_digest"], registry.registry_digest)
        self.assertEqual(rows[0]["registry_json"].encode("utf-8"), registry.canonical_bytes())

    def test_tampered_registry_or_newer_semantic_schema_fails_closed(self) -> None:
        with d_drive_tempdir() as temp:
            database = AgentDatabase(temp / "agent.sqlite3")
            SemanticSchema(database)
            connection = database.connect()
            try:
                connection.execute(
                    "UPDATE semantic_registry_versions SET registry_json = '{}'"
                )
            finally:
                connection.close()
            with self.assertRaises(SemanticRegistryMismatchError):
                SemanticSchema(database)

        with d_drive_tempdir() as temp:
            database = AgentDatabase(temp / "agent.sqlite3")
            SemanticSchema(database)
            connection = database.connect()
            try:
                connection.execute(
                    "UPDATE schema_meta SET version = 2 "
                    "WHERE component = 'agent_semantics'"
                )
            finally:
                connection.close()
            with self.assertRaises(SemanticSchemaUnsupportedError):
                SemanticSchema(database)

    def test_fresh_semantic_bootstrap_is_safe_for_32_synchronized_processes(self) -> None:
        context = multiprocessing.get_context("spawn")
        with d_drive_tempdir() as temp:
            path = temp / "agent.sqlite3"
            start_event = context.Event()
            results = context.Queue()
            processes = [
                context.Process(
                    target=_semantic_bootstrap_worker,
                    args=(str(path), start_event, results),
                )
                for _ in range(32)
            ]
            for process in processes:
                process.start()
            start_event.set()
            observations = [results.get(timeout=60) for _ in processes]
            for process in processes:
                process.join(timeout=60)
                self.assertEqual(process.exitcode, 0)
            results.close()

        expected_versions = (("agent_runtime", 2), ("agent_semantics", 1))
        self.assertEqual(observations, [("ok", 1, expected_versions)] * 32)


if __name__ == "__main__":
    unittest.main()
