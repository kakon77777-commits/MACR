from __future__ import annotations

import unittest
from dataclasses import replace

from macr_runtime.provider_capability import (
    ProviderCapabilityPolicy,
    ProviderCapabilityResolver,
    ProviderTierBinding,
    builtin_provider_capability_policies,
    glm_extended_text_policy,
    glm_standard_policy,
)


class ProviderCapabilityPolicyTests(unittest.TestCase):
    def test_capability_contracts_are_lazy_root_exports(self) -> None:
        import macr_runtime

        self.assertIs(
            macr_runtime.ProviderTierBinding,
            ProviderTierBinding,
        )
        self.assertIs(
            macr_runtime.ProviderCapabilityPolicy,
            ProviderCapabilityPolicy,
        )

    def test_glm_standard_and_extended_text_boundaries_are_exact(self) -> None:
        standard = glm_standard_policy()
        extended = glm_extended_text_policy()

        self.assertEqual(standard.tier_id, "standard")
        self.assertEqual(standard.max_latency_s, 300)
        self.assertEqual(
            standard.allowed_task_types,
            ("delegated_routine", "provider_conformance"),
        )
        self.assertEqual(extended.tier_id, "extended_text_candidate")
        self.assertEqual(extended.max_latency_s, 900)
        self.assertEqual(
            extended.allowed_task_types,
            (
                "delegated_analysis",
                "delegated_code",
                "delegated_review",
                "delegated_routine",
                "provider_conformance",
            ),
        )
        for policy in (standard, extended):
            self.assertFalse(policy.patch_allowed)
            self.assertFalse(policy.write_scope_allowed)
            self.assertFalse(policy.tools_allowed)
            self.assertTrue(policy.verification_required)
            self.assertEqual(policy.delegation_class, "non_sensitive_routine")
            self.assertEqual(
                policy.approved_privacy,
                ("internal_approved", "public"),
            )
            self.assertEqual(policy.required_capabilities, ("text_generation",))

    def test_binding_digest_changes_for_each_outer_identity_field(self) -> None:
        baseline = ProviderTierBinding(
            provider_id="glm_flash_worker",
            model_id="glm-5.3-flash",
            tier_id="standard",
            revision=1,
            complete_policy_digest="a" * 64,
            max_latency_s=300,
        )
        variants = (
            replace(baseline, provider_id="other_provider"),
            replace(baseline, model_id="other-model"),
            replace(baseline, tier_id="extended_text_candidate"),
            replace(baseline, revision=2),
            replace(baseline, max_latency_s=301),
        )

        self.assertEqual(len({baseline.binding_digest, *(item.binding_digest for item in variants)}), 6)

    def test_policy_round_trip_is_exact_and_binding_matches_policy(self) -> None:
        policy = glm_extended_text_policy()

        self.assertEqual(ProviderCapabilityPolicy.from_dict(policy.to_dict()), policy)
        binding = policy.binding()
        self.assertEqual(binding.complete_policy_digest, policy.complete_policy_digest)
        self.assertEqual(binding.max_latency_s, policy.max_latency_s)

    def test_resolver_defaults_only_exact_glm_model_to_standard(self) -> None:
        resolver = ProviderCapabilityResolver(builtin_provider_capability_policies())

        self.assertEqual(
            resolver.default_binding("glm_flash_worker", "glm-5.3-flash"),
            glm_standard_policy().binding(),
        )
        with self.assertRaisesRegex(ValueError, "default provider capability"):
            resolver.default_binding("other_provider", "glm-5.3-flash")


if __name__ == "__main__":
    unittest.main()
