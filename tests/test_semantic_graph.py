from __future__ import annotations

import unittest

from macr_runtime.semantic.errors import (
    SemanticGraphDigestMismatchError,
    SemanticStateError,
)
from macr_runtime.semantic.graph import (
    SEMANTIC_GRAPH_HEAD_SCHEMA_VERSION,
    SemanticGraphHead,
    SemanticGraphRevision,
    calculate_graph_digest,
)
from macr_runtime.semantic.registry import SemanticRegistry


GRAPH_A = "11111111-1111-4111-8111-111111111111"
GRAPH_B = "22222222-2222-4222-8222-222222222222"
RUN_ID = "33333333-3333-4333-8333-333333333333"


class SemanticGraphTests(unittest.TestCase):
    def test_empty_graph_starts_at_positive_revision_one_and_is_bindable(self) -> None:
        registry = SemanticRegistry.from_builtin()
        head = SemanticGraphHead.create_empty(
            graph_id=GRAPH_A,
            scope_ref="project:phase-c",
            registry=registry,
            created_by_agent_run_id=RUN_ID,
            created_at="2026-09-01T08:00:00+08:00",
        )

        self.assertEqual(head.schema_version, SEMANTIC_GRAPH_HEAD_SCHEMA_VERSION)
        self.assertEqual(head.graph_ref, f"semantic-graph:{GRAPH_A}")
        self.assertEqual(head.graph_revision, 1)
        self.assertEqual(head.active_node_record_digests, ())
        self.assertEqual(head.active_relation_digests, ())
        self.assertEqual(head.created_at, "2026-09-01T00:00:00+00:00")
        binding = head.to_semantic_state_binding()
        self.assertEqual(binding.ref, head.graph_ref)
        self.assertEqual(binding.digest, head.graph_digest)
        self.assertEqual(binding.revision, 1)

    def test_graph_identity_is_distinct_from_content_digest(self) -> None:
        registry = SemanticRegistry.from_builtin()
        first = SemanticGraphHead.create_empty(
            graph_id=GRAPH_A,
            scope_ref="project:phase-c",
            registry=registry,
            created_by_agent_run_id=RUN_ID,
            created_at="2026-09-01T00:00:00+00:00",
        )
        second = SemanticGraphHead.create_empty(
            graph_id=GRAPH_B,
            scope_ref="project:phase-c",
            registry=registry,
            created_by_agent_run_id=RUN_ID,
            created_at="2026-09-01T00:00:00+00:00",
        )

        self.assertNotEqual(first.graph_id, second.graph_id)
        self.assertEqual(first.graph_digest, second.graph_digest)

    def test_graph_digest_is_order_independent_but_membership_sensitive(self) -> None:
        registry = SemanticRegistry.from_builtin()
        forward = calculate_graph_digest(
            registry_version=registry.registry_version,
            registry_digest=registry.registry_digest,
            active_node_record_digests=("a" * 64, "b" * 64),
            active_relation_digests=("c" * 64, "d" * 64),
        )
        reverse = calculate_graph_digest(
            registry_version=registry.registry_version,
            registry_digest=registry.registry_digest,
            active_node_record_digests=("b" * 64, "a" * 64),
            active_relation_digests=("d" * 64, "c" * 64),
        )
        changed = calculate_graph_digest(
            registry_version=registry.registry_version,
            registry_digest=registry.registry_digest,
            active_node_record_digests=("a" * 64,),
            active_relation_digests=("c" * 64, "d" * 64),
        )

        self.assertEqual(forward, reverse)
        self.assertNotEqual(forward, changed)

    def test_head_round_trip_is_closed_and_digest_tamper_fails(self) -> None:
        head = SemanticGraphHead.create_empty(
            graph_id=GRAPH_A,
            scope_ref="project:phase-c",
            registry=SemanticRegistry.from_builtin(),
            created_by_agent_run_id=RUN_ID,
            created_at="2026-09-01T00:00:00+00:00",
        )
        public = head.to_public_dict()

        self.assertEqual(SemanticGraphHead.from_dict(public), head)
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            SemanticGraphHead.from_dict({**public, "extra": "forbidden"})
        tampered = {**public, "graph_digest": "f" * 64}
        with self.assertRaises(SemanticGraphDigestMismatchError):
            SemanticGraphHead.from_dict(tampered)

    def test_initial_revision_round_trips_and_has_no_parent_or_patch(self) -> None:
        head = SemanticGraphHead.create_empty(
            graph_id=GRAPH_A,
            scope_ref="project:phase-c",
            registry=SemanticRegistry.from_builtin(),
            created_by_agent_run_id=RUN_ID,
            created_at="2026-09-01T00:00:00+00:00",
        )
        revision = SemanticGraphRevision.from_initial_head(head)

        self.assertEqual(revision.graph_revision, 1)
        self.assertIsNone(revision.parent_revision)
        self.assertIsNone(revision.parent_graph_digest)
        self.assertIsNone(revision.patch_digest)
        self.assertEqual(SemanticGraphRevision.from_dict(revision.to_public_dict()), revision)

    def test_graph_contract_rejects_invalid_identity_revision_and_digests(self) -> None:
        registry = SemanticRegistry.from_builtin()
        with self.assertRaisesRegex(ValueError, "UUIDv4"):
            SemanticGraphHead.create_empty(
                graph_id="not-a-uuid",
                scope_ref="project:phase-c",
                registry=registry,
                created_by_agent_run_id=RUN_ID,
                created_at="2026-09-01T00:00:00+00:00",
            )
        with self.assertRaisesRegex(ValueError, "positive"):
            SemanticGraphHead(
                graph_id=GRAPH_A,
                scope_ref="project:phase-c",
                graph_revision=0,
                registry_version=registry.registry_version,
                registry_digest=registry.registry_digest,
                active_node_record_digests=(),
                active_relation_digests=(),
                created_by_agent_run_id=RUN_ID,
                created_at="2026-09-01T00:00:00+00:00",
                updated_at="2026-09-01T00:00:00+00:00",
            )

    def test_graph_errors_are_typed(self) -> None:
        error = SemanticGraphDigestMismatchError("graph digest mismatch")

        self.assertIsInstance(error, SemanticStateError)
        self.assertEqual(error.code, "SEMANTIC_GRAPH_DIGEST_MISMATCH")


if __name__ == "__main__":
    unittest.main()
