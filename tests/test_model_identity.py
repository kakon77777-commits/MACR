from __future__ import annotations

import re
import unittest

from macr_runtime.canonical import sha256_id
from macr_runtime.model_identity import (
    ExecutionRouteIdentity,
    IdentityStatus,
    ModelSubject,
    QualificationKey,
    RoleDefinition,
)


SHA256 = re.compile(r"^[0-9a-f]{64}$")
SNAPSHOT = "a" * 64
PARAMS = sha256_id("parameter_profile_v1", {"temperature": 0})
POLICY = sha256_id("data_policy_v1", {"class": "public"})
VERIFIER = sha256_id("verifier_suite_v1", {"version": "1"})
PROBE = sha256_id("probe_definition_v1", {"version": "1"})


def make_subject(
    *,
    status: IdentityStatus = IdentityStatus.CLAIMED,
) -> ModelSubject:
    return ModelSubject.create(
        "z-ai",
        "glm-5.3-flash",
        "2026-08-28",
        status,
        SNAPSHOT,
    )


def make_route(subject: ModelSubject) -> ExecutionRouteIdentity:
    return ExecutionRouteIdentity.create(
        subject.subject_id,
        "z_ai_direct",
        "https://api.z.ai/api/paas/v4",
        "glm-5.3-flash",
        PARAMS,
        "worker-v1",
        POLICY,
    )


def make_role() -> RoleDefinition:
    return RoleDefinition.create(
        "bounded_exact_worker",
        authority=("candidate_generate",),
        context_classes=("public_text", "internal_approved_text"),
        required_capabilities=("text_generation", "exact_output"),
    )


class ModelIdentityTests(unittest.TestCase):
    def test_model_and_route_ids_are_distinct_stable_lowercase_digests(self) -> None:
        subject = make_subject()
        route = make_route(subject)

        self.assertRegex(subject.subject_id, SHA256)
        self.assertRegex(route.route_id, SHA256)
        self.assertNotEqual(subject.subject_id, route.route_id)
        self.assertEqual(route.model_subject_id, subject.subject_id)
        self.assertEqual(subject, make_subject())
        self.assertEqual(route, make_route(make_subject()))

    def test_route_identity_covers_every_execution_and_policy_field(self) -> None:
        subject = make_subject()
        base = make_route(subject)
        fields = {
            "model_subject_id": base.model_subject_id,
            "provider_id": base.provider_id,
            "endpoint_identity": base.endpoint_identity,
            "provider_model_id": base.provider_model_id,
            "parameter_profile_digest": base.parameter_profile_digest,
            "prompt_compiler_version": base.prompt_compiler_version,
            "data_policy_snapshot_id": base.data_policy_snapshot_id,
        }
        variants = (
            {"provider_id": "another_provider"},
            {"endpoint_identity": "https://router.example/v1"},
            {"provider_model_id": "glm-alias"},
            {"parameter_profile_digest": "b" * 64},
            {"prompt_compiler_version": "worker-v2"},
            {"data_policy_snapshot_id": "c" * 64},
        )

        for changed in variants:
            with self.subTest(changed=changed):
                rebuilt = ExecutionRouteIdentity.create(**(fields | changed))
                self.assertNotEqual(base.route_id, rebuilt.route_id)

    def test_role_digest_is_canonical_and_excludes_presentation_or_resident_data(self) -> None:
        role = make_role()
        reordered = RoleDefinition.create(
            "bounded_exact_worker",
            authority=("candidate_generate",),
            context_classes=("internal_approved_text", "public_text"),
            required_capabilities=("exact_output", "text_generation"),
        )

        self.assertRegex(role.role_digest, SHA256)
        self.assertEqual(role.role_digest, reordered.role_digest)
        self.assertNotIn("display_label", role.canonical_identity())
        self.assertNotIn("resident", role.canonical_identity())
        self.assertFalse(hasattr(make_subject(), "resident_id"))
        self.assertFalse(hasattr(make_subject(), "host_session_id"))

    def test_unresolved_identity_cannot_form_qualification_key(self) -> None:
        subject = make_subject(status=IdentityStatus.UNRESOLVED)
        route = make_route(subject)
        role = make_role()

        with self.assertRaisesRegex(ValueError, "resolved or claimed"):
            QualificationKey.create(
                subject,
                route,
                role,
                "public_text",
                VERIFIER,
                PROBE,
            )

    def test_qualification_key_checks_subject_route_binding_and_all_components(self) -> None:
        subject = make_subject(status=IdentityStatus.RESOLVED)
        route = make_route(subject)
        role = make_role()
        key = QualificationKey.create(
            subject,
            route,
            role,
            "public_text",
            VERIFIER,
            PROBE,
        )

        self.assertRegex(key.digest, SHA256)
        self.assertEqual(key.model_subject_id, subject.subject_id)
        self.assertEqual(key.route_id, route.route_id)
        self.assertEqual(key.role_digest, role.role_digest)

        other = ModelSubject.create(
            "x-ai",
            "grok-4.6",
            "2026-08-29",
            IdentityStatus.CLAIMED,
            "d" * 64,
        )
        with self.assertRaisesRegex(ValueError, "route.*model subject"):
            QualificationKey.create(
                other,
                route,
                role,
                "public_text",
                VERIFIER,
                PROBE,
            )

    def test_external_digest_inputs_must_be_lowercase_sha256(self) -> None:
        subject = make_subject()
        invalid_values = ("A" * 64, "a" * 63, "not-a-digest")
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError,
                "lowercase SHA-256",
            ):
                ExecutionRouteIdentity.create(
                    subject.subject_id,
                    "z_ai_direct",
                    "https://api.z.ai/api/paas/v4",
                    "glm-5.3-flash",
                    value,
                    "worker-v1",
                    POLICY,
                )

        with self.assertRaisesRegex(ValueError, "iterable of identifiers"):
            RoleDefinition.create(
                "worker",
                authority="candidate_generate",
                context_classes=("public_text",),
            )


if __name__ == "__main__":
    unittest.main()
