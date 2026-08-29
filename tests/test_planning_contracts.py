from __future__ import annotations

import dataclasses
import re
import unittest
from unittest.mock import patch

from macr_runtime.canonical import sha256_id
from macr_runtime.contracts import PrivacyLevel
from macr_runtime.planning_contracts import (
    ApprovalMode,
    BudgetMode,
    ContextCapsule,
    ContextSourceItem,
    FallbackMode,
    OperatorPolicyProfile,
)


SHA256 = re.compile(r"^[0-9a-f]{64}$")
ROLE_A = sha256_id("role_definition_v1", {"role": "worker"})
ROLE_B = sha256_id("role_definition_v1", {"role": "reviewer"})
ROUTE_A = sha256_id("execution_route_v1", {"route": "direct"})
ROUTE_B = sha256_id("execution_route_v1", {"route": "router"})
AUTHORITY = sha256_id("selection_authority_v1", {"host": "session"})


def source(byte_digest: str = "a" * 64) -> ContextSourceItem:
    return ContextSourceItem(
        source_id="document:public-spec",
        byte_sha256=byte_digest,
        selected_ranges=((0, 100),),
        selection_authority_digest=None,
    )


def capsule(
    item: ContextSourceItem | None = None,
    *,
    roles: tuple[str, ...] = (ROLE_A,),
    routes: tuple[str, ...] = (ROUTE_A,),
) -> ContextCapsule:
    return ContextCapsule.build(
        [item or source()],
        "capsule-v1",
        PrivacyLevel.PUBLIC,
        roles,
        routes,
    )


class PlanningContractTests(unittest.TestCase):
    def test_owner_profile_is_warn_only_manual_and_non_automatic(self) -> None:
        profile = OperatorPolicyProfile.owner_default()

        self.assertEqual(profile.profile_id, "owner-warn-only-v1")
        self.assertIs(profile.budget_mode, BudgetMode.WARN)
        self.assertIs(profile.approval_mode, ApprovalMode.EXACT_MEMBER)
        self.assertFalse(profile.model_watch_enabled)
        self.assertTrue(profile.discovery_only)
        self.assertEqual(profile.auto_probe_max_cost_usd_per_day, 0.0)
        self.assertEqual(profile.production_promotion, "explicit")
        self.assertIs(
            profile.fallback_mode,
            FallbackMode.EXPLICIT_PLAN_REVISION,
        )
        self.assertEqual(profile.max_parallelism, 1)
        self.assertEqual(profile.direct_context_import, "manual")
        self.assertTrue(profile.accounting_required)
        self.assertRegex(profile.snapshot_id, SHA256)

    def test_policy_snapshot_changes_with_behavior_but_not_field_order(self) -> None:
        profile = OperatorPolicyProfile.owner_default()
        rebuilt = OperatorPolicyProfile.from_dict(profile.to_dict())

        self.assertEqual(profile.snapshot_id, rebuilt.snapshot_id)
        self.assertNotEqual(
            profile.snapshot_id,
            dataclasses.replace(profile, max_parallelism=2).snapshot_id,
        )
        with self.assertRaisesRegex(ValueError, "finite non-negative"):
            dataclasses.replace(profile, auto_probe_max_cost_usd_per_day=float("nan"))
        with self.assertRaisesRegex(ValueError, "boolean"):
            dataclasses.replace(profile, model_watch_enabled="false")

    def test_direct_session_source_requires_explicit_selection_authority(self) -> None:
        with self.assertRaisesRegex(ValueError, "selection authority"):
            ContextSourceItem(
                source_id="direct_session:abc",
                byte_sha256="a" * 64,
                selected_ranges=(),
                selection_authority_digest=None,
            )

        selected = ContextSourceItem(
            source_id="direct_session:abc",
            byte_sha256="a" * 64,
            selected_ranges=((4, 9),),
            selection_authority_digest=AUTHORITY,
        )
        self.assertEqual(selected.selection_authority_digest, AUTHORITY)

    def test_source_ranges_are_canonical_non_overlapping_byte_intervals(self) -> None:
        item = ContextSourceItem(
            source_id="document:spec",
            byte_sha256="a" * 64,
            selected_ranges=((20, 30), (0, 10)),
            selection_authority_digest=None,
        )
        self.assertEqual(item.selected_ranges, ((0, 10), (20, 30)))

        for ranges in (((0, 10), (9, 12)), ((3, 3),), ((-1, 2),)):
            with self.subTest(ranges=ranges), self.assertRaisesRegex(
                ValueError,
                "selected_ranges",
            ):
                ContextSourceItem(
                    source_id="document:spec",
                    byte_sha256="a" * 64,
                    selected_ranges=ranges,
                    selection_authority_digest=None,
                )

    def test_capsule_digest_changes_with_source_bytes_role_or_route_scope(self) -> None:
        one = capsule()
        changed_bytes = capsule(source("b" * 64))
        changed_role = capsule(roles=(ROLE_B,))
        changed_route = capsule(routes=(ROUTE_B,))

        self.assertRegex(one.capsule_id, SHA256)
        self.assertRegex(one.compiled_bytes_sha256, SHA256)
        self.assertNotEqual(one.capsule_id, changed_bytes.capsule_id)
        self.assertNotEqual(one.capsule_id, changed_role.capsule_id)
        self.assertNotEqual(one.capsule_id, changed_route.capsule_id)
        with self.assertRaisesRegex(ValueError, "role"):
            one.assert_allowed(ROLE_B, ROUTE_A)
        with self.assertRaisesRegex(ValueError, "route"):
            one.assert_allowed(ROLE_A, ROUTE_B)

    def test_capsule_build_is_metadata_only_and_scope_sets_are_canonical(self) -> None:
        item = ContextSourceItem(
            source_id=r"document:D:\does-not-exist\private.txt",
            byte_sha256="a" * 64,
            selected_ranges=(),
            selection_authority_digest=AUTHORITY,
        )
        with patch("builtins.open", side_effect=AssertionError("must not read files")):
            first = ContextCapsule.build(
                [item],
                "capsule-v1",
                PrivacyLevel.LOCAL_ONLY,
                [ROLE_B, ROLE_A],
                [ROUTE_B, ROUTE_A],
                token_estimate=25,
                redaction_profile="manual-reviewed-v1",
                expires_at="2026-08-30T08:00:00+08:00",
            )
            second = ContextCapsule.build(
                [item],
                "capsule-v1",
                PrivacyLevel.LOCAL_ONLY,
                [ROLE_A, ROLE_B],
                [ROUTE_A, ROUTE_B],
                token_estimate=25,
                redaction_profile="manual-reviewed-v1",
                expires_at="2026-08-30T00:00:00Z",
            )

        self.assertEqual(first, second)
        self.assertEqual(first.allowed_role_ids, tuple(sorted((ROLE_A, ROLE_B))))
        self.assertEqual(first.allowed_route_ids, tuple(sorted((ROUTE_A, ROUTE_B))))
        self.assertEqual(first.expires_at, "2026-08-30T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
