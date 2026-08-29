from __future__ import annotations

import unittest

from macr_runtime.canonical import sha256_id
from macr_runtime.config import (
    AuthMode,
    ConnectionScope,
    ProviderConfig,
)
from macr_runtime.coordination import ModelBinding
from macr_runtime.event_store import SqliteEventStore
from macr_runtime.model_identity import ExecutionRouteIdentity
from macr_runtime.registry import ProviderRegistry
from macr_runtime.route_resolution import (
    ExecutionProviderResolver,
    ExecutionRouteSnapshot,
    RouteResolutionError,
    RouteResolutionPolicy,
)

from tests.support import d_drive_tempdir


DIGESTS = {
    name: sha256_id("route_resolution_test_v1", {"name": name})
    for name in (
        "subject",
        "params",
        "data-policy",
        "qualification",
        "capsule",
        "policy",
    )
}


class NeverCalledTransport:
    def __init__(self) -> None:
        self.posts = []
        self.gets = []


class StaticProvider:
    def __init__(self, config: ProviderConfig, transport: NeverCalledTransport):
        self.provider_id = config.id
        self.config = config
        self.transport = transport

    def health(self):
        raise AssertionError("route resolution must not call health")


def config() -> ProviderConfig:
    return ProviderConfig(
        id="glm_flash_worker",
        kind="zai_glm_worker",
        enabled=True,
        auth_mode=AuthMode.API_KEY_FILE,
        api_usage_allowed=True,
        connection_scope=ConnectionScope.EXTERNAL_HTTPS,
        api_key_file=r"D:\KEY\GLM.txt",
        base_url="https://api.z.ai/api/paas/v4",
        model="glm-5.3-flash",
        endpoint_path="/chat/completions",
        allowed_hosts=("api.z.ai",),
        capabilities=("text_generation",),
    )


def route(provider_id: str = "glm_flash_worker") -> ExecutionRouteIdentity:
    return ExecutionRouteIdentity.create(
        DIGESTS["subject"],
        provider_id,
        (
            "https://openrouter.ai/api/v1"
            if provider_id == "openrouter_discovery_claim"
            else "https://api.z.ai/api/paas/v4"
        ),
        "glm-5.3-flash",
        DIGESTS["params"],
        "worker-v1",
        DIGESTS["data-policy"],
    )


def binding(route_item: ExecutionRouteIdentity) -> ModelBinding:
    return ModelBinding(
        slot_id="worker",
        model_subject_id=DIGESTS["subject"],
        route_id=route_item.route_id,
        qualification_key=DIGESTS["qualification"],
        parameter_profile_digest=DIGESTS["params"],
        context_capsule_ids=(DIGESTS["capsule"],),
    )


class RouteResolutionTests(unittest.TestCase):
    def test_resolution_is_proposal_only_without_authority_lease_dispatch_or_transport(self) -> None:
        transport = NeverCalledTransport()
        registry = ProviderRegistry((StaticProvider(config(), transport),))
        route_item = route()
        snapshot = ExecutionRouteSnapshot.build(
            (route_item,),
            discovery_only_route_ids=(),
            observed_at="2026-08-29T00:00:00+00:00",
        )
        policy = RouteResolutionPolicy(
            policy_snapshot_id=DIGESTS["policy"],
            allowed_provider_ids=("glm_flash_worker",),
            require_exact_model=True,
        )
        with d_drive_tempdir() as temp:
            store = SqliteEventStore(temp / "dispatch.sqlite3")
            connection = store.database.connect()
            try:
                before = tuple(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in (
                        "dispatch_authorities",
                        "dispatch_leases",
                        "events",
                    )
                )
            finally:
                connection.close()
            proposal = ExecutionProviderResolver(registry, snapshot).resolve(
                binding(route_item),
                policy,
            )
            connection = store.database.connect()
            try:
                after = tuple(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in (
                        "dispatch_authorities",
                        "dispatch_leases",
                        "events",
                    )
                )
            finally:
                connection.close()

        self.assertEqual(proposal.provider_id, "glm_flash_worker")
        self.assertEqual(proposal.provider_model_id, "glm-5.3-flash")
        self.assertEqual(proposal.resolution_state, "proposal_only")
        self.assertFalse(proposal.authority_issued)
        self.assertFalse(proposal.network_activity)
        self.assertEqual(before, (0, 0, 0))
        self.assertEqual(after, (0, 0, 0))
        self.assertEqual(transport.posts, [])
        self.assertEqual(transport.gets, [])

    def test_discovery_route_cannot_resolve_as_execution_provider(self) -> None:
        transport = NeverCalledTransport()
        registry = ProviderRegistry((StaticProvider(config(), transport),))
        discovery = route("openrouter_discovery_claim")
        snapshot = ExecutionRouteSnapshot.build(
            (discovery,),
            discovery_only_route_ids=(discovery.route_id,),
            observed_at="2026-08-29T00:00:00+00:00",
        )
        policy = RouteResolutionPolicy(
            policy_snapshot_id=DIGESTS["policy"],
            allowed_provider_ids=("glm_flash_worker",),
            require_exact_model=True,
        )

        with self.assertRaisesRegex(RouteResolutionError, "discovery-only"):
            ExecutionProviderResolver(registry, snapshot).resolve(
                binding(discovery),
                policy,
            )
        self.assertEqual(transport.posts, [])

    def test_policy_provider_and_exact_model_mismatches_fail_closed(self) -> None:
        transport = NeverCalledTransport()
        registry = ProviderRegistry((StaticProvider(config(), transport),))
        route_item = route()
        snapshot = ExecutionRouteSnapshot.build(
            (route_item,),
            discovery_only_route_ids=(),
            observed_at="2026-08-29T00:00:00+00:00",
        )
        denied = RouteResolutionPolicy(
            policy_snapshot_id=DIGESTS["policy"],
            allowed_provider_ids=("another_provider",),
            require_exact_model=True,
        )
        with self.assertRaisesRegex(RouteResolutionError, "policy"):
            ExecutionProviderResolver(registry, snapshot).resolve(
                binding(route_item),
                denied,
            )

        mismatched = ExecutionRouteIdentity.create(
            DIGESTS["subject"],
            "glm_flash_worker",
            "https://api.z.ai/api/paas/v4",
            "different-model",
            DIGESTS["params"],
            "worker-v1",
            DIGESTS["data-policy"],
        )
        mismatch_snapshot = ExecutionRouteSnapshot.build(
            (mismatched,),
            discovery_only_route_ids=(),
            observed_at="2026-08-29T00:00:00+00:00",
        )
        allowed = RouteResolutionPolicy(
            policy_snapshot_id=DIGESTS["policy"],
            allowed_provider_ids=("glm_flash_worker",),
            require_exact_model=True,
        )
        with self.assertRaisesRegex(RouteResolutionError, "model"):
            ExecutionProviderResolver(registry, mismatch_snapshot).resolve(
                binding(mismatched),
                allowed,
            )

        wrong_endpoint = ExecutionRouteIdentity.create(
            DIGESTS["subject"],
            "glm_flash_worker",
            "https://unexpected.example.invalid/v1",
            "glm-5.3-flash",
            DIGESTS["params"],
            "worker-v1",
            DIGESTS["data-policy"],
        )
        endpoint_snapshot = ExecutionRouteSnapshot.build(
            (wrong_endpoint,),
            discovery_only_route_ids=(),
            observed_at="2026-08-29T00:00:00+00:00",
        )
        with self.assertRaisesRegex(RouteResolutionError, "endpoint"):
            ExecutionProviderResolver(registry, endpoint_snapshot).resolve(
                binding(wrong_endpoint),
                allowed,
            )


if __name__ == "__main__":
    unittest.main()
