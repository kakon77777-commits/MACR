from __future__ import annotations

import json
import unittest
from importlib.resources import files

from macr_runtime.observation.contracts import (
    FreshnessMode,
    FreshnessPolicy,
    ObservationBinding,
    ObservationIntent,
    ObservationScope,
    ObservationVerificationRequirement,
    RawObservationRef,
    ReObservationRequest,
    VerifiedObservationRef,
)


RUN_ID = "11111111-1111-4111-8111-111111111111"


class ObservationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scope = ObservationScope(
            scope_ref="scope:repo",
            resource_refs=("repo:file:b", "repo:file:a"),
            region_refs=("region:tests",),
        )
        self.revision_policy = FreshnessPolicy(
            policy_id="freshness:revision",
            mode=FreshnessMode.SOURCE_REVISION,
            source_revision="git:abc123",
            max_age_seconds=None,
            invalidation_event_refs=(),
        )

    def make_intent(self, **overrides: object) -> ObservationIntent:
        values: dict[str, object] = {
            "observation_intent_id": "obs-intent:1",
            "agent_run_id": RUN_ID,
            "goal_ref": "goal:1",
            "plan_ref": "plan:1",
            "task_ref": "task:1",
            "world_binding_ref": "world:repo",
            "observation_purpose": "establish repository basis",
            "requested_scope": self.scope,
            "preferred_representation": "structured_manifest",
            "freshness_policy": self.revision_policy,
            "verification_requirement": ObservationVerificationRequirement.VERIFIED,
        }
        values.update(overrides)
        return ObservationIntent(**values)

    def make_verified(self, **overrides: object) -> VerifiedObservationRef:
        values: dict[str, object] = {
            "observation_ref_id": "verified-observation:1",
            "agent_run_id": RUN_ID,
            "observation_intent_ref": "obs-intent:1",
            "projection_request_ref": "projection-request:1",
            "projection_result_ref": "projection-result:1",
            "manifest_digest": "a" * 64,
            "verification_digest": "b" * 64,
            "visibility_commit_ref": "visibility:1",
            "source_identity": "repo:fixture",
            "source_revision": "git:abc123",
            "scope_digest": self.scope.scope_digest,
            "projection_profile_digest": "c" * 64,
            "visible_at": "2026-08-31T08:00:00+08:00",
        }
        values.update(overrides)
        return VerifiedObservationRef(**values)

    def test_raw_observation_cannot_construct_verified_reference(self) -> None:
        raw = RawObservationRef(
            raw_ref="raw:1",
            source_ref="source:fixture",
            captured_at="2026-08-31T00:00:00+00:00",
            raw_digest="d" * 64,
        )

        self.assertNotIsInstance(raw, VerifiedObservationRef)
        with self.assertRaises(ValueError):
            VerifiedObservationRef.from_dict(raw.to_public_dict())

    def test_verified_reference_requires_verification_and_visibility(self) -> None:
        for field_name, value in (
            ("verification_digest", None),
            ("visibility_commit_ref", None),
            ("manifest_digest", None),
        ):
            with self.subTest(field=field_name):
                with self.assertRaises(ValueError):
                    self.make_verified(**{field_name: value})

    def test_verified_reference_round_trip_has_no_raw_or_boolean_shortcut(self) -> None:
        verified = self.make_verified()

        public = verified.to_public_dict()
        rebuilt = VerifiedObservationRef.from_dict(public)

        self.assertEqual(rebuilt, verified)
        encoded = json.dumps(public)
        self.assertNotIn("raw", encoded)
        self.assertNotIn("\"verified\"", encoded)
        self.assertEqual(public["visible_at"], "2026-08-31T00:00:00+00:00")

    def test_scope_is_canonical_and_requires_a_bounded_target(self) -> None:
        reverse = ObservationScope(
            scope_ref="scope:repo",
            resource_refs=("repo:file:a", "repo:file:b"),
            region_refs=("region:tests",),
        )

        self.assertEqual(reverse, self.scope)
        self.assertEqual(reverse.scope_digest, self.scope.scope_digest)
        self.assertEqual(self.scope.resource_refs, ("repo:file:a", "repo:file:b"))
        with self.assertRaisesRegex(ValueError, "resource or region"):
            ObservationScope("scope:empty", (), ())

    def test_freshness_modes_require_only_their_mode_specific_fields(self) -> None:
        valid = (
            FreshnessPolicy("fresh:immutable", FreshnessMode.IMMUTABLE, None, None, ()),
            self.revision_policy,
            FreshnessPolicy("fresh:age", FreshnessMode.MAX_AGE, None, 30.0, ()),
            FreshnessPolicy(
                "fresh:event",
                FreshnessMode.EVENT_INVALIDATED,
                None,
                None,
                ("event:1",),
            ),
            FreshnessPolicy(
                "fresh:always",
                FreshnessMode.ALWAYS_RECHECK_BEFORE_MUTATION,
                None,
                None,
                (),
            ),
        )
        self.assertEqual(len({item.policy_digest for item in valid}), len(valid))

        invalid = (
            (FreshnessMode.SOURCE_REVISION, None, None, ()),
            (FreshnessMode.MAX_AGE, None, 0, ()),
            (FreshnessMode.EVENT_INVALIDATED, None, None, ()),
            (FreshnessMode.IMMUTABLE, "rev", None, ()),
            (FreshnessMode.MAX_AGE, None, 5, ("event:unexpected",)),
        )
        for mode, revision, age, events in invalid:
            with self.subTest(mode=mode.value):
                with self.assertRaises(ValueError):
                    FreshnessPolicy("fresh:invalid", mode, revision, age, events)

    def test_intent_round_trip_binds_scope_and_freshness_digests(self) -> None:
        intent = self.make_intent()

        public = intent.to_public_dict()
        rebuilt = ObservationIntent.from_dict(public)

        self.assertEqual(rebuilt, intent)
        self.assertEqual(public["requested_scope"]["scope_digest"], self.scope.scope_digest)
        self.assertEqual(
            public["freshness_policy"]["policy_digest"],
            self.revision_policy.policy_digest,
        )

    def test_intent_digest_changes_with_scope_or_freshness(self) -> None:
        baseline = self.make_intent()
        changed_scope = self.make_intent(
            requested_scope=ObservationScope(
                "scope:repo",
                ("repo:file:other",),
                (),
            )
        )
        changed_freshness = self.make_intent(
            freshness_policy=FreshnessPolicy(
                "fresh:always",
                FreshnessMode.ALWAYS_RECHECK_BEFORE_MUTATION,
                None,
                None,
                (),
            )
        )

        self.assertNotEqual(baseline.intent_digest, changed_scope.intent_digest)
        self.assertNotEqual(baseline.intent_digest, changed_freshness.intent_digest)

    def test_intent_from_dict_rejects_verified_flag_and_unknown_mode(self) -> None:
        public = self.make_intent().to_public_dict()
        public["verified"] = True
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            ObservationIntent.from_dict(public)

        public = self.make_intent().to_public_dict()
        public["freshness_policy"]["mode"] = "cache_is_fine"
        with self.assertRaises(ValueError):
            ObservationIntent.from_dict(public)

    def test_binding_keeps_verified_identity_and_basis_separate(self) -> None:
        verified = self.make_verified()
        binding = ObservationBinding(
            observation_binding_id="observation-binding:1",
            agent_run_id=RUN_ID,
            observation_ref_id=verified.observation_ref_id,
            observation_digest=verified.observation_digest,
            semantic_node_ref="sem:observation:1",
            world_binding_ref="world:repo",
            basis_digest="e" * 64,
            bound_at="2026-08-31T08:05:00+08:00",
        )

        self.assertEqual(ObservationBinding.from_dict(binding.to_public_dict()), binding)
        self.assertNotEqual(binding.observation_digest, binding.basis_digest)

    def test_reobservation_request_round_trip_preserves_prior_and_action_refs(self) -> None:
        request = ReObservationRequest(
            reobservation_request_id="reobserve:1",
            agent_run_id=RUN_ID,
            prior_observation_ref="verified-observation:1",
            action_ref="action:1",
            requested_scope=self.scope,
            freshness_policy=FreshnessPolicy(
                "fresh:always",
                FreshnessMode.ALWAYS_RECHECK_BEFORE_MUTATION,
                None,
                None,
                (),
            ),
            reason="verify external effect",
        )

        self.assertEqual(
            ReObservationRequest.from_dict(request.to_public_dict()),
            request,
        )

    def test_observation_schema_is_packaged_closed_and_versioned(self) -> None:
        schema_path = files("macr_runtime.observation").joinpath(
            "schemas/observation-contracts-v1.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(
            schema["$id"],
            "urn:evemisslab:macr:observation-contracts:v1",
        )
        self.assertFalse(
            schema["$defs"]["VerifiedObservationRef"]["additionalProperties"]
        )
        self.assertNotIn(
            "verified",
            schema["$defs"]["VerifiedObservationRef"]["properties"],
        )
        self.assertEqual(
            schema["$defs"]["ObservationVerificationRequirement"]["enum"],
            ["verified"],
        )
        self.assertEqual(len(schema["$defs"]["ObservationScope"]["anyOf"]), 2)
        self.assertEqual(len(schema["$defs"]["FreshnessPolicy"]["allOf"]), 5)


if __name__ == "__main__":
    unittest.main()
