from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from macr_runtime.canonical import sha256_id
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
        delegation_approval_sha256=format(ordinal + 6, "x") * 64,
        constraints=TaskConstraints(
            max_cost_usd=0.005,
            max_latency_s=180,
            max_output_tokens=8_192,
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
        role_digest=format(ordinal + 9, "x") * 64,
        privacy="public",
        context_class="non_sensitive_routine",
        cost_ceiling_usd=0.005,
        target_claims=(TargetClaim.for_path(f"src/t1-{ordinal}.txt"),),
    )


def manifest() -> T1ExecutionManifest:
    return T1ExecutionManifest.create(
        plan_digest="a" * 64,
        members=(member(0), member(1), member(2)),
        aggregate_cost_ceiling_usd=0.015,
        campaign_cost_ceiling_usd=0.020,
        expires_at="2099-01-01T00:00:00+00:00",
        authorized_dispatchers=("worker-1", "worker-2", "worker-3"),
    )


class T1ManifestTests(unittest.TestCase):
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
            role_digest=first.role_digest,
            privacy=first.privacy,
            context_class=first.context_class,
            cost_ceiling_usd=first.cost_ceiling_usd,
            target_claims=first.target_claims,
        )

        self.assertEqual(accepted.task.goal, latex_task.goal)


if __name__ == "__main__":
    unittest.main()
