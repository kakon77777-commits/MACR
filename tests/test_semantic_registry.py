from __future__ import annotations

import unittest

from macr_runtime.action.contracts import EffectName, VerificationVerdict
from macr_runtime.semantic.contracts import (
    ClaimStatus,
    ResolutionStatus,
    SemanticLifecycleStatus,
    SemanticNodeType,
    SemanticRelationType,
)
from macr_runtime.semantic.errors import (
    SemanticRegistryMismatchError,
    SemanticRegistryUnknownError,
    SemanticStateError,
)
from macr_runtime.semantic.registry import SemanticRegistry


class SemanticRegistryTests(unittest.TestCase):
    def test_builtin_registry_is_packaged_versioned_digest_bound_and_exact(self) -> None:
        registry = SemanticRegistry.from_builtin()

        self.assertEqual(registry.schema_version, "macr-semantic-registry/v1")
        self.assertEqual(registry.registry_version, "1")
        self.assertRegex(registry.registry_digest, r"^[0-9a-f]{64}$")
        self.assertEqual(
            set(registry.node_types),
            {item.value for item in SemanticNodeType},
        )
        self.assertEqual(
            set(registry.relation_types),
            {item.value for item in SemanticRelationType},
        )
        self.assertEqual(
            set(registry.effect_types),
            {item.value for item in EffectName},
        )
        self.assertEqual(
            set(registry.verdict_types),
            {item.value for item in VerificationVerdict},
        )
        expected_statuses = {
            *(item.value for item in SemanticLifecycleStatus),
            *(item.value for item in ClaimStatus),
            *(item.value for item in ResolutionStatus),
        }
        self.assertEqual(set(registry.status_types), expected_statuses)

    def test_builtin_registry_bytes_and_round_trip_are_deterministic(self) -> None:
        first = SemanticRegistry.from_builtin()
        second = SemanticRegistry.from_dict(first.to_public_dict())

        self.assertEqual(second, first)
        self.assertEqual(second.canonical_bytes(), first.canonical_bytes())

        tampered = first.to_public_dict()
        tampered["registry_digest"] = "f" * 64
        with self.assertRaisesRegex(SemanticRegistryMismatchError, "digest"):
            SemanticRegistry.from_dict(tampered)

    def test_unknown_node_relation_effect_status_verdict_and_failure_fail_closed(self) -> None:
        registry = SemanticRegistry.from_builtin()
        calls = (
            lambda: registry.require_node_type("invented"),
            lambda: registry.require_relation_type("invented"),
            lambda: registry.require_effect("invented.effect"),
            lambda: registry.require_status("invented"),
            lambda: registry.require_verdict("invented"),
            lambda: registry.require_failure("invented"),
        )

        for call in calls:
            with self.subTest(call=call):
                with self.assertRaises(SemanticRegistryUnknownError) as caught:
                    call()
                self.assertEqual(caught.exception.code, "SEMANTIC_REGISTRY_UNKNOWN")

    def test_relation_direction_has_goal_to_plan_green_and_reverse_negative(self) -> None:
        registry = SemanticRegistry.from_builtin()

        registry.require_relation(
            SemanticNodeType.GOAL,
            SemanticRelationType.MOTIVATES,
            SemanticNodeType.PLAN,
        )
        with self.assertRaisesRegex(
            SemanticRegistryMismatchError,
            "direction",
        ):
            registry.require_relation(
                SemanticNodeType.PLAN,
                SemanticRelationType.MOTIVATES,
                SemanticNodeType.GOAL,
            )

    def test_registry_data_is_not_commit_authority(self) -> None:
        registry = SemanticRegistry.from_builtin()
        public = registry.to_public_dict()

        self.assertNotIn("authorization_reference", public)
        self.assertNotIn("authorizes", registry.relation_types)

    def test_registry_errors_are_sanitized_macr_errors(self) -> None:
        error = SemanticRegistryUnknownError("unknown semantic type")

        self.assertIsInstance(error, SemanticStateError)
        self.assertEqual(error.code, "SEMANTIC_REGISTRY_UNKNOWN")
        self.assertEqual(str(error), "unknown semantic type")


if __name__ == "__main__":
    unittest.main()
