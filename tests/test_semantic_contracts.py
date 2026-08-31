from __future__ import annotations

import json
import unittest
from importlib.resources import files

from macr_runtime.semantic.contracts import (
    ArtifactRole,
    BindingKind,
    ClaimStatus,
    ExternalSemanticBinding,
    ResolutionStatus,
    SemanticEvent,
    SemanticEventType,
    SemanticLifecycleStatus,
    SemanticNode,
    SemanticNodeType,
    SemanticPatch,
    SemanticProfileRef,
    SemanticProvenance,
    SemanticRelation,
    SemanticRelationType,
)


RUN_ID = "11111111-1111-4111-8111-111111111111"


class SemanticContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provenance_a = SemanticProvenance(
            origin_kind="agent_run",
            origin_ref="worker:a",
            source_refs=("source:1",),
            agent_run_id=RUN_ID,
            created_by_ref="actor:a",
            created_at="2026-08-31T08:00:00+08:00",
        )
        self.provenance_b = SemanticProvenance(
            origin_kind="agent_run",
            origin_ref="worker:b",
            source_refs=("source:1",),
            agent_run_id=RUN_ID,
            created_by_ref="actor:b",
            created_at="2026-08-31T08:00:01+08:00",
        )
        self.emlu_profile = SemanticProfileRef(
            system_id="eml-u",
            profile_id="composite-glyph/0.1",
            profile_version="0.1.0",
            registry_ref="registry:emlu",
            registry_revision=1,
            registry_digest="a" * 64,
            decoder_contract_ref="decoder:emlu-v1",
        )
        self.isql_profile = SemanticProfileRef(
            system_id="isql",
            profile_id="meta-core/0.2",
            profile_version="0.2",
            registry_ref="registry:isql",
            registry_revision=2,
            registry_digest="b" * 64,
            decoder_contract_ref="decoder:isql-meta-v02",
        )
        self.emlu_binding = ExternalSemanticBinding(
            semantic_ref="sem:claim:1",
            profile=self.emlu_profile,
            external_object_ref="emlu:glyph:1",
            external_object_digest="c" * 64,
            binding_kind=BindingKind.PROJECTION,
            artifact_role=ArtifactRole.PROJECTION,
        )
        self.isql_binding = ExternalSemanticBinding(
            semantic_ref="sem:claim:1",
            profile=self.isql_profile,
            external_object_ref="isql:claim:1",
            external_object_digest="d" * 64,
            binding_kind=BindingKind.REFERENCE,
            artifact_role=ArtifactRole.CANONICAL_SOURCE,
        )

    def make_claim(
        self,
        *,
        provenance: SemanticProvenance | None = None,
        status: ClaimStatus = ClaimStatus.PROPOSED,
        bindings: tuple[ExternalSemanticBinding, ...] = (),
        payload: dict[str, object] | None = None,
    ) -> SemanticNode:
        return SemanticNode(
            node_id="sem:claim:1",
            node_type=SemanticNodeType.CLAIM,
            payload=(
                {"statement": "parser rejects empty tuples"}
                if payload is None
                else payload
            ),
            scope_ref="scope:fixture",
            status=status,
            effects=(),
            constraints=("verification:required",),
            policy={"visibility": "task"},
            provenance=provenance or self.provenance_a,
            temporal={"created_step": 1},
            external_bindings=bindings,
        )

    def test_same_content_different_provenance_has_distinct_record_identity(self) -> None:
        first = self.make_claim(provenance=self.provenance_a)
        second = self.make_claim(provenance=self.provenance_b)

        self.assertEqual(first.content_digest, second.content_digest)
        self.assertNotEqual(first.record_digest, second.record_digest)

    def test_epistemic_status_changes_record_not_claim_content(self) -> None:
        proposed = self.make_claim(status=ClaimStatus.PROPOSED)
        verified = self.make_claim(status=ClaimStatus.VERIFIED)

        self.assertEqual(proposed.content_digest, verified.content_digest)
        self.assertNotEqual(proposed.record_digest, verified.record_digest)

    def test_profile_binding_changes_record_not_macr_content_identity(self) -> None:
        emlu = self.make_claim(bindings=(self.emlu_binding,))
        isql = self.make_claim(bindings=(self.isql_binding,))

        self.assertEqual(emlu.content_digest, isql.content_digest)
        self.assertNotEqual(emlu.record_digest, isql.record_digest)

    def test_profile_and_external_binding_round_trip_exactly(self) -> None:
        profile = SemanticProfileRef.from_dict(self.isql_profile.to_public_dict())
        binding = ExternalSemanticBinding.from_dict(
            self.isql_binding.to_public_dict()
        )

        self.assertEqual(profile, self.isql_profile)
        self.assertEqual(binding, self.isql_binding)
        self.assertEqual(
            binding.to_public_dict()["artifact_role"],
            "canonical_source",
        )

    def test_profile_registry_fields_are_all_present_or_all_absent(self) -> None:
        cases = (
            {"registry_ref": "registry:x", "registry_revision": None, "registry_digest": None},
            {"registry_ref": None, "registry_revision": 1, "registry_digest": None},
            {"registry_ref": None, "registry_revision": None, "registry_digest": "a" * 64},
        )
        for fields in cases:
            with self.subTest(fields=fields):
                with self.assertRaisesRegex(ValueError, "registry fields"):
                    SemanticProfileRef(
                        system_id="system",
                        profile_id="profile",
                        profile_version="1",
                        decoder_contract_ref=None,
                        **fields,
                    )

    def test_unresolved_ambiguity_and_obligation_use_resolution_status(self) -> None:
        ambiguity = SemanticNode(
            node_id="sem:ambiguity:1",
            node_type=SemanticNodeType.AMBIGUITY,
            payload={"candidate_refs": ["candidate:a", "candidate:b"]},
            scope_ref="scope:fixture",
            status=ResolutionStatus.UNRESOLVED,
            effects=(),
            constraints=(),
            policy={},
            provenance=self.provenance_a,
            temporal={},
            external_bindings=(),
        )
        obligation = SemanticNode(
            node_id="sem:obligation:1",
            node_type=SemanticNodeType.OBLIGATION,
            payload={"required_evidence": ["verify:test"]},
            scope_ref="scope:fixture",
            status=ResolutionStatus.UNRESOLVED,
            effects=(),
            constraints=(),
            policy={},
            provenance=self.provenance_a,
            temporal={},
            external_bindings=(),
        )

        self.assertEqual(
            SemanticNode.from_dict(ambiguity.to_public_dict()),
            ambiguity,
        )
        self.assertEqual(
            SemanticNode.from_dict(obligation.to_public_dict()),
            obligation,
        )
        self.assertEqual(ambiguity.to_public_dict()["status"], "unresolved")

    def test_status_enum_must_match_node_family(self) -> None:
        with self.assertRaisesRegex(ValueError, "ClaimStatus"):
            self.make_claim(status=SemanticLifecycleStatus.ACTIVE)
        with self.assertRaisesRegex(ValueError, "ResolutionStatus"):
            SemanticNode(
                node_id="sem:ambiguity:1",
                node_type=SemanticNodeType.AMBIGUITY,
                payload={},
                scope_ref="scope:fixture",
                status=ClaimStatus.UNRESOLVED,
                effects=(),
                constraints=(),
                policy={},
                provenance=self.provenance_a,
                temporal={},
                external_bindings=(),
            )

    def test_semantic_payload_is_deeply_immutable(self) -> None:
        source = {"nested": {"values": [1, 2]}}
        node = self.make_claim(payload=source)
        before = node.record_digest

        source["nested"]["values"].append(3)
        public = node.to_public_dict()
        public["payload"]["nested"]["values"].append(4)

        self.assertEqual(
            node.to_public_dict()["payload"],
            {"nested": {"values": [1, 2]}},
        )
        self.assertEqual(node.record_digest, before)

    def test_node_from_dict_rejects_authority_and_unknown_vocabularies(self) -> None:
        public = self.make_claim().to_public_dict()
        public["authorized"] = True
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            SemanticNode.from_dict(public)

        for field_name, value in (
            ("node_type", "unknown"),
            ("status", "certainly_true"),
        ):
            public = self.make_claim().to_public_dict()
            public[field_name] = value
            with self.subTest(field=field_name):
                with self.assertRaises(ValueError):
                    SemanticNode.from_dict(public)

    def test_relation_is_closed_digest_bound_and_round_trips(self) -> None:
        relation = SemanticRelation(
            relation_id="semrel:1",
            source_ref="sem:observation:1",
            relation_type=SemanticRelationType.SUPPORTS,
            target_ref="sem:claim:1",
            qualifiers={"strength": "direct"},
            provenance=self.provenance_a,
        )

        self.assertEqual(
            SemanticRelation.from_dict(relation.to_public_dict()),
            relation,
        )
        public = relation.to_public_dict()
        public["relation_type"] = "authorizes"
        with self.assertRaises(ValueError):
            SemanticRelation.from_dict(public)

    def test_correction_and_resolution_events_require_parent_lineage(self) -> None:
        for event_type in (SemanticEventType.CORRECTION, SemanticEventType.RESOLUTION):
            with self.subTest(event_type=event_type.value):
                with self.assertRaisesRegex(ValueError, "parent_event_refs"):
                    SemanticEvent(
                        event_id=f"event:{event_type.value}:1",
                        event_type=event_type,
                        subject_refs=("sem:claim:1",),
                        parent_event_refs=(),
                        payload={"reason": "new evidence"},
                        provenance=self.provenance_a,
                        created_at="2026-08-31T00:00:00+00:00",
                    )

        event = SemanticEvent(
            event_id="event:correction:1",
            event_type=SemanticEventType.CORRECTION,
            subject_refs=("sem:claim:1",),
            parent_event_refs=("event:proposal:1",),
            payload={"reason": "new evidence"},
            provenance=self.provenance_a,
            created_at="2026-08-31T00:00:00+00:00",
        )
        self.assertEqual(SemanticEvent.from_dict(event.to_public_dict()), event)

    def test_patch_is_proposal_only_and_digest_bound(self) -> None:
        node = self.make_claim()
        relation = SemanticRelation(
            relation_id="semrel:1",
            source_ref="sem:observation:1",
            relation_type=SemanticRelationType.SUPPORTS,
            target_ref=node.node_id,
            qualifiers={},
            provenance=self.provenance_a,
        )
        patch = SemanticPatch(
            patch_id="sempatch:1",
            base_graph_digest="e" * 64,
            add_nodes=(node,),
            add_relations=(relation,),
            status_updates=({"node_ref": node.node_id, "status": "supported"},),
            supersession_refs=(),
            producer_ref="agent:fixture",
        )

        public = patch.to_public_dict()
        self.assertNotIn("authorized", public)
        self.assertNotIn("committed", public)
        self.assertEqual(SemanticPatch.from_dict(public), patch)

    def test_semantic_schema_is_packaged_closed_and_versioned(self) -> None:
        schema_path = files("macr_runtime.semantic").joinpath(
            "schemas/semantic-contracts-v1.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(
            schema["$id"],
            "urn:evemisslab:macr:semantic-contracts:v1",
        )
        self.assertFalse(schema["$defs"]["SemanticNode"]["additionalProperties"])
        self.assertIn("ambiguity", schema["$defs"]["SemanticNodeType"]["enum"])
        self.assertIn("unresolved", schema["$defs"]["ClaimStatus"]["enum"])
        self.assertIn("ExternalSemanticBinding", schema["$defs"])
        self.assertIn("ArtifactRole", schema["$defs"])
        self.assertNotIn(
            "authorizes",
            schema["$defs"]["SemanticRelationType"]["enum"],
        )
        self.assertEqual(len(schema["$defs"]["SemanticNode"]["allOf"]), 3)


if __name__ == "__main__":
    unittest.main()
