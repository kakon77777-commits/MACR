from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from .authority import AuthorityScope, DispatchAuthorityStore
from .batch_authority import (
    BatchAuthorityReference,
    BatchMemberScope,
    BatchScope,
)
from .canonical import aware_iso8601
from .errors import MacrError
from .execution import AuthorizationReference, InteractionPlane
from .registry import ProviderRegistry
from .runtime import RuntimeServices
from .scheduler import PlanQueue, QueueMember, T1QueuePlan
from .t1_manifest import (
    T1AuthorityBundle,
    T1ExecutionManifest,
    T1ExecutionMember,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class T1DispatchError(MacrError):
    """A T1 manifest cannot be staged or dispatched safely."""


class T1Dispatcher:
    def __init__(
        self,
        registry: ProviderRegistry,
        services: RuntimeServices,
        *,
        queue: PlanQueue | None = None,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not isinstance(registry, ProviderRegistry):
            raise ValueError("registry must be a ProviderRegistry")
        if not isinstance(services, RuntimeServices):
            raise ValueError("services must be RuntimeServices")
        self.registry = registry
        self.services = services
        self._now = now
        self.queue = queue or PlanQueue(services.events.path, now=now)
        self.dispatch_authorities = DispatchAuthorityStore(
            services.events.path,
            now=now,
        )

    def _current_time(self) -> datetime:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("T1 dispatcher clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _queue_member(member: T1ExecutionMember) -> QueueMember:
        return QueueMember(
            member_digest=member.member_digest,
            provider_id=member.route.provider_id,
            route_id=member.route.route_id,
            role_digest=member.role_digest,
            privacy=member.privacy,
            context_class=member.context_class,
            cost_ceiling_usd=member.cost_ceiling_usd,
            target_claims=member.target_claims,
        )

    @staticmethod
    def _batch_scope(
        manifest: T1ExecutionManifest,
        expires_at: str,
    ) -> BatchScope:
        return BatchScope(
            plan_digest=manifest.plan_digest,
            ordered_members=tuple(
                BatchMemberScope(
                    member_digest=item.member_digest,
                    provider_id=item.route.provider_id,
                    route_id=item.route.route_id,
                    role_digest=item.role_digest,
                    privacy=item.privacy,
                    context_class=item.context_class,
                    cost_ceiling_usd=item.cost_ceiling_usd,
                )
                for item in manifest.members
            ),
            aggregate_cost_ceiling_usd=manifest.aggregate_cost_ceiling_usd,
            expires_at=expires_at,
            authorized_dispatchers=manifest.authorized_dispatchers,
        )

    def _queue_plan(
        self,
        manifest: T1ExecutionManifest,
        batch_authority: BatchAuthorityReference,
    ) -> T1QueuePlan:
        return T1QueuePlan(
            plan_digest=manifest.plan_digest,
            members=tuple(self._queue_member(item) for item in manifest.members),
            aggregate_cost_ceiling_usd=manifest.aggregate_cost_ceiling_usd,
            authority=batch_authority,
        )

    def _validate_manifest_routes(self, manifest: T1ExecutionManifest) -> None:
        for member in manifest.members:
            profile = self.registry.execution_profile(member.route.provider_id)
            if (
                profile["enabled"] is not True
                or profile["api_usage_allowed"] is not True
                or profile["kind"] != member.route.provider_kind
                or profile["model"] != member.route.provider_model_id
                or profile["connection_scope"] != member.route.connection_scope
                or profile["base_url"] != member.route.endpoint_identity
            ):
                raise T1DispatchError(
                    "T1 route proposal does not match the execution provider"
                )
            policy = self.registry.token_policy(
                member.route.provider_id,
                store=self.services.token_policies,
            )
            if policy.policy_digest != member.token_policy_digest:
                raise T1DispatchError(
                    "T1 route does not use the exact manifest token policy"
                )
            provider = self.registry.get(member.route.provider_id)
            approval_metadata = getattr(provider, "approval_metadata", None)
            if not callable(approval_metadata):
                raise T1DispatchError(
                    "T1 provider cannot validate exact task approval metadata"
                )
            metadata = approval_metadata(member.task)
            if (
                metadata.get("required_approval_sha256")
                != member.task.delegation_approval_sha256
                or metadata.get("model_token_policy_digest")
                != member.token_policy_digest
            ):
                raise T1DispatchError(
                    "T1 task approval digest or token policy is stale"
                )

    @staticmethod
    def _dispatch_scope(manifest: T1ExecutionManifest) -> AuthorityScope:
        return AuthorityScope(
            providers=tuple(
                sorted({item.route.provider_id for item in manifest.members})
            ),
            planes=(InteractionPlane.DELEGATION.value,),
            task_types=tuple(
                sorted({item.task.task_type for item in manifest.members})
            ),
            batch_ids=(manifest.manifest_digest,),
            member_digests=tuple(item.member_digest for item in manifest.members),
        )

    def _verify_dispatch_authority(
        self,
        manifest: T1ExecutionManifest,
        reference: AuthorizationReference,
    ) -> None:
        for member in manifest.members:
            self.dispatch_authorities.verify(
                reference,
                provider_id=member.route.provider_id,
                plane=InteractionPlane.DELEGATION.value,
                task_type=member.task.task_type,
                batch_id=manifest.manifest_digest,
                member_digest=member.member_digest,
            )

    def _existing_bundle(
        self,
        manifest: T1ExecutionManifest,
    ) -> T1AuthorityBundle | None:
        connection = self.services.events.database.connect()
        try:
            batch = connection.execute(
                "SELECT * FROM plan_queue_batches WHERE plan_digest = ?",
                (manifest.plan_digest,),
            ).fetchone()
            if batch is None:
                return None
            dispatch = connection.execute(
                """
                SELECT * FROM dispatch_authorities
                WHERE source_kind = 't1_manifest' AND source_id = ?
                  AND revoked_at IS NULL
                ORDER BY revision DESC LIMIT 1
                """,
                (manifest.manifest_digest,),
            ).fetchone()
        finally:
            connection.close()
        if dispatch is None:
            raise T1DispatchError(
                "existing T1 queue has no exact dispatch authority"
            )
        batch_reference = BatchAuthorityReference(
            authority_id=batch["authority_id"],
            digest=batch["authority_digest"],
            revision=batch["authority_revision"],
            plan_digest=batch["plan_digest"],
        )
        dispatch_reference = AuthorizationReference(
            source_kind=dispatch["source_kind"],
            source_id=dispatch["source_id"],
            digest=dispatch["body_sha256"],
            revision=dispatch["revision"],
            epoch=dispatch["epoch"],
            scope=dispatch["scope_json"],
        )
        member_ids = self.queue.enqueue(
            self._queue_plan(manifest, batch_reference)
        )
        self._verify_dispatch_authority(manifest, dispatch_reference)
        return T1AuthorityBundle(
            manifest_digest=manifest.manifest_digest,
            batch_authority=batch_reference,
            dispatch_authority=dispatch_reference,
            member_ids=member_ids,
            expires_at=batch["expires_at"],
        )

    def _record_staging_failure(
        self,
        manifest: T1ExecutionManifest,
        failure_type: str,
        batch: BatchAuthorityReference | None,
        dispatch: AuthorizationReference | None,
    ) -> None:
        try:
            self.services.events.append_standalone(
                "t1.staging_failed",
                str(uuid.uuid4()),
                {
                    "manifest_digest": manifest.manifest_digest,
                    "plan_digest": manifest.plan_digest,
                    "failure_type": failure_type,
                    "batch_authority_digest": (
                        batch.digest if batch is not None else None
                    ),
                    "dispatch_authority_digest": (
                        dispatch.digest if dispatch is not None else None
                    ),
                },
            )
        except Exception:
            pass

    def stage(
        self,
        manifest: T1ExecutionManifest,
        dispatcher_ids: Sequence[str],
        expires_at: str,
    ) -> T1AuthorityBundle:
        if not isinstance(manifest, T1ExecutionManifest):
            raise ValueError("manifest must be a T1ExecutionManifest")
        normalized_dispatchers = tuple(sorted(dispatcher_ids))
        if normalized_dispatchers != manifest.authorized_dispatchers:
            raise T1DispatchError(
                "dispatcher IDs do not match the exact T1 manifest"
            )
        normalized_expiry = aware_iso8601("expires_at", expires_at)
        if normalized_expiry != manifest.expires_at:
            raise T1DispatchError("T1 authority expiry must match the manifest")
        if datetime.fromisoformat(normalized_expiry) <= self._current_time():
            raise T1DispatchError("T1 manifest is expired")
        if self.queue.state_counts()["reconciliation_required"] != 0:
            raise T1DispatchError(
                "global reconciliation must be empty before T1 staging"
            )
        self._validate_manifest_routes(manifest)
        existing = self._existing_bundle(manifest)
        if existing is not None:
            return existing
        batch_reference: BatchAuthorityReference | None = None
        dispatch_reference: AuthorizationReference | None = None
        try:
            batch_scope = self._batch_scope(manifest, normalized_expiry)
            batch_reference = self.queue.authorities.issue(batch_scope)
            dispatch_reference = self.dispatch_authorities.issue(
                source_kind="t1_manifest",
                source_id=manifest.manifest_digest,
                scope=self._dispatch_scope(manifest),
                expires_at=normalized_expiry,
            )
            member_ids = self.queue.enqueue(
                self._queue_plan(manifest, batch_reference)
            )
        except Exception as exc:
            if dispatch_reference is not None:
                try:
                    self.dispatch_authorities.revoke(dispatch_reference)
                except Exception:
                    pass
            if batch_reference is not None:
                try:
                    self.queue.authorities.revoke(batch_reference)
                except Exception:
                    pass
            self._record_staging_failure(
                manifest,
                type(exc).__name__,
                batch_reference,
                dispatch_reference,
            )
            raise
        return T1AuthorityBundle(
            manifest_digest=manifest.manifest_digest,
            batch_authority=batch_reference,
            dispatch_authority=dispatch_reference,
            member_ids=member_ids,
            expires_at=normalized_expiry,
        )


__all__ = ["T1DispatchError", "T1Dispatcher"]
