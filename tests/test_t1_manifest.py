from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from macr_runtime.canonical import sha256_id
from macr_runtime.errors import (
    LegacyFixedWorkerTopologyIncompatibleError,
    LegacyOutputPolicyIncompatibleError,
    LegacyPreTierIncompatibleError,
)
from macr_runtime.provider_capability import glm_standard_policy
from macr_runtime.contracts import (
    DelegationClass,
    PrivacyLevel,
    TaskConstraints,
    TaskContract,
)
from macr_runtime.route_resolution import ExecutionRouteProposal
from macr_runtime.scheduler import TargetClaim
from macr_runtime.t1_manifest import (
    T1ExecutionManifest,
    T1ExecutionMember,
    inspect_t1_manifest,
    load_t1_manifest,
)
from macr_runtime.token_policy import t1_glm_live_policy
from tests.support import d_drive_tempdir


def proposal(seed: int = 1) -> ExecutionRouteProposal:
    canonical = {
        "route_id": format(seed, "x") * 64,
        "route_snapshot_id": "2" * 64,
        "policy_snapshot_id": "3" * 64,
        "provider_id": "glm_flash_worker",
        "provider_kind": "zai_glm_worker",
        "provider_model_id": "glm-5.3-flash",
        "connection_scope": "external_https",
        "endpoint_identity": "https://api.z.ai/api/paas/v4",
        "parameter_profile_digest": "4" * 64,
        "prompt_compiler_version": "worker-v1",
        "data_policy_snapshot_id": "5" * 64,
        "resolution_state": "proposal_only",
        "authority_issued": False,
        "network_activity": False,
    }
    return ExecutionRouteProposal(
        proposal_digest=sha256_id("execution_route_proposal_v1", canonical),
        **canonical,
    )


def task(ordinal: int) -> TaskContract:
    return TaskContract(
        task_id=f"t1-member-{ordinal}",
        goal=f"Return exactly: T1_MEMBER_{ordinal}",
        task_type="delegated_routine",
        delegable=True,
        delegation_class=DelegationClass.NON_SENSITIVE_ROUTINE,
        delegation_approval_sha256=sha256_id(
            "test_t1_approval_v1",
            {"ordinal": ordinal},
        ),
        constraints=TaskConstraints(
            max_cost_usd=0.050,
            max_latency_s=180,
            max_output_tokens=65_536,
            max_context_tokens=128_000,
            internet=True,
            privacy=PrivacyLevel.PUBLIC,
        ),
        required_capabilities=("text_generation",),
    )


def member(ordinal: int, *, route_seed: int = 1) -> T1ExecutionMember:
    return T1ExecutionMember.create(
        plan_digest="a" * 64,
        ordinal=ordinal,
        task=task(ordinal),
        route=proposal(route_seed),
        token_policy_digest=t1_glm_live_policy().policy_digest,
        provider_tier_binding_digest=(
            glm_standard_policy().binding().binding_digest
        ),
        role_digest=sha256_id("test_t1_role_v1", {"ordinal": ordinal}),
        privacy="public",
        context_class="non_sensitive_routine",
        cost_ceiling_usd=0.050,
        target_claims=(TargetClaim.for_path(f"src/t1-{ordinal}.txt"),),
    )


def manifest(
    *,
    member_count: int = 3,
    worker_count: int = 3,
    campaign_cost_ceiling_usd: float | None = None,
) -> T1ExecutionManifest:
    aggregate = 0.050 * member_count
    return T1ExecutionManifest.create(
        plan_digest="a" * 64,
        members=tuple(member(ordinal) for ordinal in range(member_count)),
        worker_count=worker_count,
        aggregate_cost_ceiling_usd=aggregate,
        campaign_cost_ceiling_usd=(
            aggregate
            if campaign_cost_ceiling_usd is None
            else campaign_cost_ceiling_usd
        ),
        expires_at="2099-01-01T00:00:00+00:00",
        authorized_dispatchers=tuple(
            f"worker-{ordinal + 1}" for ordinal in range(worker_count)
        ),
    )


class T1ManifestTests(unittest.TestCase):
    def test_t1_real_work_requires_quality_first_output(self) -> None:
        base = member(0)
        quality_task = replace(
            base.task,
            constraints=replace(
                base.task.constraints,
                max_cost_usd=0.050,
                max_output_tokens=65_536,
            ),
        )
        try:
            accepted = T1ExecutionMember.create(
                plan_digest=base.plan_digest,
                ordinal=base.ordinal,
                task=quality_task,
                route=base.route,
                token_policy_digest=t1_glm_live_policy().policy_digest,
                provider_tier_binding_digest=(
                    base.provider_tier_binding_digest
                ),
                role_digest=base.role_digest,
                privacy=base.privacy,
                context_class=base.context_class,
                cost_ceiling_usd=0.050,
                target_claims=base.target_claims,
            )
        except ValueError as exc:
            self.fail(f"T1 quality-first member was rejected: {exc}")

        task_32k = replace(
            quality_task,
            constraints=replace(
                quality_task.constraints,
                max_output_tokens=32_768,
            ),
        )
        with self.assertRaisesRegex(ValueError, "output budget"):
            T1ExecutionMember.create(
                plan_digest=accepted.plan_digest,
                ordinal=accepted.ordinal,
                task=task_32k,
                route=accepted.route,
                token_policy_digest=t1_glm_live_policy().policy_digest,
                provider_tier_binding_digest=(
                    accepted.provider_tier_binding_digest
                ),
                role_digest=accepted.role_digest,
                privacy=accepted.privacy,
                context_class=accepted.context_class,
                cost_ceiling_usd=0.050,
                target_claims=accepted.target_claims,
            )

        self.assertEqual(accepted.task.constraints.max_output_tokens, 65_536)

    def test_worker_count_is_explicit_and_independent_of_member_count(self) -> None:
        members = (member(0), member(1), member(2))
        two_workers = T1ExecutionManifest.create(
            plan_digest="a" * 64,
            members=members,
            worker_count=2,
            aggregate_cost_ceiling_usd=0.150,
            campaign_cost_ceiling_usd=0.200,
            expires_at="2099-01-01T00:00:00+00:00",
            authorized_dispatchers=("worker-1", "worker-2"),
        )
        three_workers = T1ExecutionManifest.create(
            plan_digest="a" * 64,
            members=members,
            worker_count=3,
            aggregate_cost_ceiling_usd=0.150,
            campaign_cost_ceiling_usd=0.200,
            expires_at="2099-01-01T00:00:00+00:00",
            authorized_dispatchers=("worker-1", "worker-2", "worker-3"),
        )

        self.assertEqual(two_workers.schema_version, 4)
        self.assertEqual(two_workers.worker_count, 2)
        self.assertEqual(len(two_workers.members), 3)
        self.assertNotEqual(two_workers.manifest_digest, three_workers.manifest_digest)

    def test_member_and_worker_counts_are_not_capped_at_three(self) -> None:
        members = tuple(member(ordinal) for ordinal in range(5))

        subject = T1ExecutionManifest.create(
            plan_digest="a" * 64,
            members=members,
            worker_count=5,
            aggregate_cost_ceiling_usd=0.250,
            campaign_cost_ceiling_usd=1.000,
            expires_at="2099-01-01T00:00:00+00:00",
            authorized_dispatchers=tuple(
                f"worker-{ordinal + 1}" for ordinal in range(5)
            ),
        )

        self.assertEqual(tuple(item.ordinal for item in subject.members), tuple(range(5)))
        self.assertEqual(len(subject.authorized_dispatchers), 5)
        self.assertEqual(
            subject.members[4].member_digest,
            sha256_id(
                "t1_execution_member_v4",
                subject.members[4].canonical_member(),
            ),
        )
        self.assertEqual(
            subject.manifest_digest,
            sha256_id("t1_execution_manifest_v4", subject.canonical_manifest()),
        )

    def test_member_and_manifest_cost_envelopes_are_dynamic(self) -> None:
        base_task = task(0)
        expensive_task = replace(
            base_task,
            constraints=replace(base_task.constraints, max_cost_usd=0.025),
        )
        expensive_member = T1ExecutionMember.create(
            plan_digest="a" * 64,
            ordinal=0,
            task=expensive_task,
            route=proposal(),
            token_policy_digest=t1_glm_live_policy().policy_digest,
            provider_tier_binding_digest=(
                glm_standard_policy().binding().binding_digest
            ),
            role_digest="9" * 64,
            privacy="public",
            context_class="non_sensitive_routine",
            cost_ceiling_usd=0.025,
            target_claims=(TargetClaim.for_path("src/dynamic-cost.txt"),),
        )

        subject = T1ExecutionManifest.create(
            plan_digest="a" * 64,
            members=(expensive_member,),
            worker_count=1,
            aggregate_cost_ceiling_usd=0.025,
            campaign_cost_ceiling_usd=10.000,
            expires_at="2099-01-01T00:00:00+00:00",
            authorized_dispatchers=("worker-1",),
        )

        self.assertEqual(subject.aggregate_cost_ceiling_usd, 0.025)
        self.assertEqual(subject.campaign_cost_ceiling_usd, 10.000)

    def test_dynamic_worker_and_cost_relations_fail_closed(self) -> None:
        members = (member(0), member(1), member(2))
        cases = (
            {
                "members": members,
                "worker_count": 0,
                "aggregate_cost_ceiling_usd": 0.150,
                "campaign_cost_ceiling_usd": 0.150,
                "authorized_dispatchers": (),
            },
            {
                "members": members,
                "worker_count": 4,
                "aggregate_cost_ceiling_usd": 0.150,
                "campaign_cost_ceiling_usd": 0.150,
                "authorized_dispatchers": (
                    "worker-1",
                    "worker-2",
                    "worker-3",
                    "worker-4",
                ),
            },
            {
                "members": members,
                "worker_count": 2,
                "aggregate_cost_ceiling_usd": 0.150,
                "campaign_cost_ceiling_usd": 0.150,
                "authorized_dispatchers": (
                    "worker-1",
                    "worker-2",
                    "worker-3",
                ),
            },
            {
                "members": members,
                "worker_count": 3,
                "aggregate_cost_ceiling_usd": 0.200,
                "campaign_cost_ceiling_usd": 0.200,
                "authorized_dispatchers": (
                    "worker-1",
                    "worker-2",
                    "worker-3",
                ),
            },
            {
                "members": members,
                "worker_count": 3,
                "aggregate_cost_ceiling_usd": 0.150,
                "campaign_cost_ceiling_usd": 0.100,
                "authorized_dispatchers": (
                    "worker-1",
                    "worker-2",
                    "worker-3",
                ),
            },
            {
                "members": (),
                "worker_count": 1,
                "aggregate_cost_ceiling_usd": 0.0,
                "campaign_cost_ceiling_usd": 0.0,
                "authorized_dispatchers": ("worker-1",),
            },
        )
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                T1ExecutionManifest.create(
                    plan_digest="a" * 64,
                    expires_at="2099-01-01T00:00:00+00:00",
                    **case,
                )

    def test_schema_four_and_member_digest_bind_provider_tier(self) -> None:
        first = manifest()
        original = first.members[0]
        changed = T1ExecutionMember.create(
            plan_digest=original.plan_digest,
            ordinal=original.ordinal,
            task=original.task,
            route=original.route,
            token_policy_digest=original.token_policy_digest,
            provider_tier_binding_digest="b" * 64,
            role_digest=original.role_digest,
            privacy=original.privacy,
            context_class=original.context_class,
            cost_ceiling_usd=original.cost_ceiling_usd,
            target_claims=original.target_claims,
        )

        self.assertEqual(first.schema_version, 4)
        self.assertEqual(
            original.member_digest,
            sha256_id("t1_execution_member_v4", original.canonical_member()),
        )
        self.assertNotEqual(original.member_digest, changed.member_digest)

    def test_schema_one_is_audit_visible_but_dispatch_incompatible(self) -> None:
        current = manifest()
        legacy_members = []
        legacy_member_digests = []
        for member_value in current.members:
            document = member_value.to_dict()
            document.pop("provider_tier_binding_digest")
            canonical = member_value.canonical_member()
            canonical.pop("provider_tier_binding_digest")
            document["member_digest"] = sha256_id(
                "t1_execution_member_v1",
                canonical,
            )
            legacy_member_digests.append(document["member_digest"])
            legacy_members.append(document)
        legacy_manifest = current.to_dict()
        legacy_manifest["schema_version"] = 1
        legacy_manifest.pop("worker_count")
        legacy_manifest["members"] = legacy_members
        canonical_manifest = current.canonical_manifest()
        canonical_manifest["schema_version"] = 1
        canonical_manifest.pop("worker_count")
        canonical_manifest["ordered_member_digests"] = legacy_member_digests
        legacy_manifest["manifest_digest"] = sha256_id(
            "t1_execution_manifest_v1",
            canonical_manifest,
        )

        with d_drive_tempdir() as temp:
            path = temp / "legacy-t1.json"
            raw = json.dumps(legacy_manifest, sort_keys=True).encode("utf-8")
            path.write_bytes(raw)
            inspection = inspect_t1_manifest(path)
            with self.assertRaisesRegex(
                LegacyPreTierIncompatibleError,
                "legacy_pre_tier_incompatible",
            ):
                load_t1_manifest(path)
            after = path.read_bytes()

        self.assertEqual(inspection.status, "legacy_pre_tier")
        self.assertEqual(inspection.schema_version, 1)
        self.assertEqual(inspection.member_count, 3)
        self.assertEqual(inspection.manifest_digest, legacy_manifest["manifest_digest"])
        self.assertEqual(after, raw)

    def test_schema_two_is_audit_visible_but_quality_floor_incompatible(self) -> None:
        current = manifest()
        legacy_manifest = current.to_dict()
        legacy_manifest["schema_version"] = 2
        legacy_manifest.pop("worker_count")
        canonical_manifest = current.canonical_manifest()
        canonical_manifest["schema_version"] = 2
        canonical_manifest.pop("worker_count")
        legacy_manifest["manifest_digest"] = sha256_id(
            "t1_execution_manifest_v2",
            canonical_manifest,
        )

        with d_drive_tempdir() as temp:
            path = temp / "legacy-quality-floor-t1.json"
            raw = json.dumps(legacy_manifest, sort_keys=True).encode("utf-8")
            path.write_bytes(raw)
            inspection = inspect_t1_manifest(path)
            with self.assertRaisesRegex(
                LegacyOutputPolicyIncompatibleError,
                "legacy_output_policy_incompatible",
            ):
                load_t1_manifest(path)
            after = path.read_bytes()

        self.assertEqual(inspection.status, "legacy_pre_quality_floor")
        self.assertEqual(inspection.schema_version, 2)
        self.assertEqual(inspection.member_count, 3)
        self.assertEqual(inspection.manifest_digest, legacy_manifest["manifest_digest"])
        self.assertEqual(after, raw)

    def test_schema_three_is_audit_visible_but_fixed_worker_incompatible(self) -> None:
        current = manifest()
        legacy_members = []
        legacy_member_digests = []
        for member_value in current.members:
            document = member_value.to_dict()
            document["member_digest"] = sha256_id(
                "t1_execution_member_v3",
                member_value.canonical_member(),
            )
            legacy_member_digests.append(document["member_digest"])
            legacy_members.append(document)
        legacy_manifest = current.to_dict()
        legacy_manifest["schema_version"] = 3
        legacy_manifest.pop("worker_count")
        legacy_manifest["members"] = legacy_members
        canonical_manifest = current.canonical_manifest()
        canonical_manifest["schema_version"] = 3
        canonical_manifest.pop("worker_count")
        canonical_manifest["ordered_member_digests"] = legacy_member_digests
        legacy_manifest["manifest_digest"] = sha256_id(
            "t1_execution_manifest_v3",
            canonical_manifest,
        )

        with d_drive_tempdir() as temp:
            path = temp / "legacy-fixed-three-t1.json"
            raw = json.dumps(legacy_manifest, sort_keys=True).encode("utf-8")
            path.write_bytes(raw)
            inspection = inspect_t1_manifest(path)
            with self.assertRaisesRegex(
                LegacyFixedWorkerTopologyIncompatibleError,
                "legacy_fixed_worker_topology",
            ):
                load_t1_manifest(path)
            after = path.read_bytes()

        self.assertEqual(inspection.status, "legacy_fixed_three_workers")
        self.assertEqual(inspection.schema_version, 3)
        self.assertEqual(inspection.member_count, 3)
        self.assertEqual(after, raw)

    def test_stale_schema_four_t1_policy_fails_without_rewriting_manifest(self) -> None:
        old_policy_digest = (
            "ecfafac42410cc8f6b21db637989eb33ac92c347cc513720bfe204678bab3490"
        )
        current = manifest()
        document = current.to_dict()
        member_digests = []
        for index, current_member in enumerate(current.members):
            member_document = document["members"][index]
            member_document["token_policy_digest"] = old_policy_digest
            canonical_member = current_member.canonical_member()
            canonical_member["token_policy_digest"] = old_policy_digest
            member_document["member_digest"] = sha256_id(
                "t1_execution_member_v4",
                canonical_member,
            )
            member_digests.append(member_document["member_digest"])
        canonical_manifest = current.canonical_manifest()
        canonical_manifest["ordered_member_digests"] = member_digests
        document["manifest_digest"] = sha256_id(
            "t1_execution_manifest_v4",
            canonical_manifest,
        )

        with d_drive_tempdir() as temp:
            path = temp / "stale-policy-schema-four.json"
            raw = json.dumps(document, sort_keys=True).encode("utf-8")
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, "token policy"):
                load_t1_manifest(path)
            after = path.read_bytes()

        self.assertEqual(after, raw)

    def test_member_and_manifest_digest_bind_order_task_route_policy_cost_and_targets(
        self,
    ) -> None:
        first = manifest()
        reordered = {
            key: first.to_dict()[key]
            for key in reversed(tuple(first.to_dict()))
        }
        parsed = T1ExecutionManifest.from_dict(reordered)
        with self.assertRaisesRegex(ValueError, "ordinals"):
            T1ExecutionManifest.create(
                plan_digest=first.plan_digest,
                members=tuple(reversed(first.members)),
                worker_count=first.worker_count,
                aggregate_cost_ceiling_usd=first.aggregate_cost_ceiling_usd,
                campaign_cost_ceiling_usd=first.campaign_cost_ceiling_usd,
                expires_at=first.expires_at,
                authorized_dispatchers=first.authorized_dispatchers,
            )
        reordered_members = tuple(
            T1ExecutionMember.create(
                plan_digest=first.plan_digest,
                ordinal=ordinal,
                task=source.task,
                route=source.route,
                token_policy_digest=source.token_policy_digest,
                provider_tier_binding_digest=(
                    source.provider_tier_binding_digest
                ),
                role_digest=source.role_digest,
                privacy=source.privacy,
                context_class=source.context_class,
                cost_ceiling_usd=source.cost_ceiling_usd,
                target_claims=source.target_claims,
            )
            for ordinal, source in enumerate(reversed(first.members))
        )
        reversed_manifest = T1ExecutionManifest.create(
            plan_digest=first.plan_digest,
            members=reordered_members,
            worker_count=first.worker_count,
            aggregate_cost_ceiling_usd=first.aggregate_cost_ceiling_usd,
            campaign_cost_ceiling_usd=first.campaign_cost_ceiling_usd,
            expires_at=first.expires_at,
            authorized_dispatchers=first.authorized_dispatchers,
        )
        changed_route = member(0, route_seed=6)

        self.assertEqual(parsed, first)
        self.assertNotEqual(first.manifest_digest, reversed_manifest.manifest_digest)
        self.assertNotEqual(first.members[0].member_digest, changed_route.member_digest)

    def test_strict_t1_limits_and_digest_only_targets_fail_closed(self) -> None:
        document = manifest().to_dict()
        attacks = []
        unknown = json.loads(json.dumps(document))
        unknown["members"][0]["unexpected"] = True
        attacks.append(unknown)
        raw_path = json.loads(json.dumps(document))
        raw_path["members"][0]["target_claims"][0]["path"] = r"D:\private.txt"
        attacks.append(raw_path)
        too_costly = json.loads(json.dumps(document))
        too_costly["members"][0]["cost_ceiling_usd"] = 0.006
        attacks.append(too_costly)
        wrong_topology = json.loads(json.dumps(document))
        wrong_topology["topology_id"] = "T0_DIRECT_VERIFIED"
        attacks.append(wrong_topology)
        for attacked in attacks:
            with self.subTest(keys=tuple(attacked)), self.assertRaises(ValueError):
                T1ExecutionManifest.from_dict(attacked)

    def test_load_rejects_duplicate_json_keys_and_absolute_task_paths(self) -> None:
        with d_drive_tempdir() as temp:
            duplicate = temp / "duplicate.json"
            duplicate.write_text(
                '{"schema_version":1,"schema_version":1}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate"):
                load_t1_manifest(duplicate)

        first = manifest()
        unsafe_task = replace(first.members[0].task, goal=r"Read D:\private.txt")
        with self.assertRaisesRegex(ValueError, "sensitive|absolute|path"):
            T1ExecutionMember.create(
                plan_digest=first.plan_digest,
                ordinal=0,
                task=unsafe_task,
                route=first.members[0].route,
                token_policy_digest=first.members[0].token_policy_digest,
                provider_tier_binding_digest=(
                    first.members[0].provider_tier_binding_digest
                ),
                role_digest=first.members[0].role_digest,
                privacy=first.members[0].privacy,
                context_class=first.members[0].context_class,
                cost_ceiling_usd=first.members[0].cost_ceiling_usd,
                target_claims=first.members[0].target_claims,
            )

    def test_latex_drive_ambiguities_remain_valid_non_sensitive_text(self) -> None:
        first = manifest().members[0]
        latex_task = replace(
            first.task,
            goal=r"Classify $\forall B:\neg C(B)$ and $\{x\in D:\neg C_k(x)\}$.",
        )
        accepted = T1ExecutionMember.create(
            plan_digest=first.plan_digest,
            ordinal=first.ordinal,
            task=latex_task,
            route=first.route,
            token_policy_digest=first.token_policy_digest,
            provider_tier_binding_digest=first.provider_tier_binding_digest,
            role_digest=first.role_digest,
            privacy=first.privacy,
            context_class=first.context_class,
            cost_ceiling_usd=first.cost_ceiling_usd,
            target_claims=first.target_claims,
        )

        self.assertEqual(accepted.task.goal, latex_task.goal)


if __name__ == "__main__":
    unittest.main()
