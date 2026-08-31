from __future__ import annotations

import unittest

import macr_runtime.agent as agent_package
from macr_runtime.agent.contracts import SemanticStateBinding
from macr_runtime.agent.errors import AgentEventIntegrityError
from macr_runtime.agent.events import AgentEventType, replay_semantic_binding
from macr_runtime.agent.semantic_binding import _AgentSemanticBindingPort
from macr_runtime.agent.store import AgentStore, ProjectionInspectionStatus
from macr_runtime.semantic.graph import SemanticGraphHead
from macr_runtime.semantic.registry import SemanticRegistry
from tests.support import d_drive_tempdir
from tests.test_agent_state import RUN_ID, make_header


GRAPH_ID = "44444444-4444-4444-8444-444444444444"
EVENT_ID = "55555555-5555-4555-8555-555555555555"
OPERATION_ID = "66666666-6666-4666-8666-666666666666"


def graph_binding() -> SemanticStateBinding:
    return SemanticGraphHead.create_empty(
        graph_id=GRAPH_ID,
        scope_ref="project:phase-c",
        registry=SemanticRegistry.from_builtin(),
        created_by_agent_run_id=RUN_ID,
        created_at="2026-09-01T00:00:00+00:00",
    ).to_semantic_state_binding()


class AgentSemanticBindingTests(unittest.TestCase):
    def test_creation_persists_exact_initial_semantic_binding_or_all_null(self) -> None:
        binding = graph_binding()
        for supplied in (None, binding):
            with self.subTest(supplied=supplied), d_drive_tempdir() as temp:
                store = AgentStore(temp / "agent.sqlite3")
                store.create_agent_run(make_header(semantic_state=supplied))

                observed = store.get_agent_semantic_binding(RUN_ID)
                connection = store.database.connect()
                try:
                    row = connection.execute(
                        "SELECT semantic_state_ref, semantic_state_digest, "
                        "semantic_state_revision FROM agent_runs "
                        "WHERE agent_run_id = ?",
                        (RUN_ID,),
                    ).fetchone()
                finally:
                    connection.close()

            self.assertEqual(observed, supplied)
            expected = (
                (None, None, None)
                if supplied is None
                else (supplied.ref, supplied.digest, supplied.revision)
            )
            self.assertEqual(tuple(row), expected)

    def test_attach_event_same_state_epoch_and_revision_plus_one_round_trips(self) -> None:
        binding = graph_binding()
        with d_drive_tempdir() as temp:
            store = AgentStore(temp / "agent.sqlite3")
            current = store.create_agent_run(make_header())
            port = _AgentSemanticBindingPort(store)
            event, next_projection = port._build_event(
                current=current,
                previous_binding=None,
                new_binding=binding,
                operation_kind="attach",
                operation_id=OPERATION_ID,
                proposal_digest=None,
                patch_digest=None,
                registry_digest=SemanticRegistry.from_builtin().registry_digest,
                authorization_digest="a" * 64,
                created_at="2026-09-01T01:00:00+00:00",
                event_id=EVENT_ID,
            )
            connection = store.database.connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                committed = port._commit_on_connection(
                    connection,
                    current=current,
                    event=event,
                    new_binding=binding,
                    expected_revision=1,
                    expected_epoch=0,
                )
                connection.commit()
            finally:
                connection.close()

            observed = store.get_agent_run(RUN_ID)
            observed_binding = store.get_agent_semantic_binding(RUN_ID)
            events = store.list_agent_events(RUN_ID)

        self.assertEqual(event.event_type, AgentEventType.SEMANTIC_STATE_ADVANCED)
        self.assertEqual(next_projection.state, current.state)
        self.assertEqual(next_projection.epoch, current.epoch)
        self.assertEqual(next_projection.state_revision, current.state_revision + 1)
        self.assertEqual(committed, next_projection)
        self.assertEqual(observed, next_projection)
        self.assertEqual(observed_binding, binding)
        self.assertEqual(events[-1].event, event)

    def test_semantic_binding_event_payload_separates_attach_and_commit(self) -> None:
        binding = graph_binding()
        with d_drive_tempdir() as temp:
            store = AgentStore(temp / "agent.sqlite3")
            current = store.create_agent_run(make_header())
            port = _AgentSemanticBindingPort(store)

            attach, _ = port._build_event(
                current=current,
                previous_binding=None,
                new_binding=binding,
                operation_kind="attach",
                operation_id=OPERATION_ID,
                proposal_digest=None,
                patch_digest=None,
                registry_digest="b" * 64,
                authorization_digest="c" * 64,
                created_at="2026-09-01T01:00:00+00:00",
                event_id=EVENT_ID,
            )
            with self.assertRaisesRegex(ValueError, "proposal.*patch"):
                port._build_event(
                    current=current,
                    previous_binding=None,
                    new_binding=binding,
                    operation_kind="commit",
                    operation_id=OPERATION_ID,
                    proposal_digest=None,
                    patch_digest=None,
                    registry_digest="b" * 64,
                    authorization_digest="c" * 64,
                    created_at="2026-09-01T01:00:00+00:00",
                    event_id=EVENT_ID,
                )

        self.assertIsNone(attach.payload["proposal_digest"])
        self.assertIsNone(attach.payload["patch_digest"])

    def test_binding_replay_rejects_wrong_previous_binding_and_tamper(self) -> None:
        binding = graph_binding()
        with d_drive_tempdir() as temp:
            store = AgentStore(temp / "agent.sqlite3")
            current = store.create_agent_run(make_header())
            event, _ = _AgentSemanticBindingPort(store)._build_event(
                current=current,
                previous_binding=None,
                new_binding=binding,
                operation_kind="attach",
                operation_id=OPERATION_ID,
                proposal_digest=None,
                patch_digest=None,
                registry_digest="b" * 64,
                authorization_digest="c" * 64,
                created_at="2026-09-01T01:00:00+00:00",
                event_id=EVENT_ID,
            )

        self.assertEqual(replay_semantic_binding(None, (event,)), binding)
        with self.assertRaisesRegex(AgentEventIntegrityError, "previous"):
            replay_semantic_binding(binding, (event,))

        public = event.to_public_dict()
        public["payload"]["new_binding"]["digest"] = "f" * 64
        with self.assertRaises(ValueError):
            type(event).from_dict(public)

    def test_projection_rebuild_restores_binding_and_detects_column_mismatch(self) -> None:
        binding = graph_binding()
        with d_drive_tempdir() as temp:
            store = AgentStore(temp / "agent.sqlite3")
            current = store.create_agent_run(make_header())
            port = _AgentSemanticBindingPort(store)
            event, _ = port._build_event(
                current=current,
                previous_binding=None,
                new_binding=binding,
                operation_kind="attach",
                operation_id=OPERATION_ID,
                proposal_digest=None,
                patch_digest=None,
                registry_digest="b" * 64,
                authorization_digest="c" * 64,
                created_at="2026-09-01T01:00:00+00:00",
                event_id=EVENT_ID,
            )
            connection = store.database.connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                port._commit_on_connection(
                    connection,
                    current=current,
                    event=event,
                    new_binding=binding,
                    expected_revision=1,
                    expected_epoch=0,
                )
                connection.commit()
                connection.execute(
                    "UPDATE agent_runs SET semantic_state_digest = ? "
                    "WHERE agent_run_id = ?",
                    ("9" * 64, RUN_ID),
                )
            finally:
                connection.close()

            conflict = store.inspect_projection(RUN_ID)
            connection = store.database.connect()
            try:
                connection.execute(
                    "DELETE FROM agent_runs WHERE agent_run_id = ?",
                    (RUN_ID,),
                )
            finally:
                connection.close()
            store.rebuild_projection(RUN_ID)
            exact = store.inspect_projection(RUN_ID)
            restored = store.get_agent_semantic_binding(RUN_ID)

        self.assertEqual(conflict.status, ProjectionInspectionStatus.CONFLICT)
        self.assertEqual(exact.status, ProjectionInspectionStatus.EXACT_MATCH)
        self.assertEqual(restored, binding)

    def test_connection_bound_binding_mutator_is_not_public_api(self) -> None:
        self.assertNotIn("AgentSemanticBindingPort", agent_package.__all__)
        self.assertFalse(hasattr(agent_package, "AgentSemanticBindingPort"))


if __name__ == "__main__":
    unittest.main()
