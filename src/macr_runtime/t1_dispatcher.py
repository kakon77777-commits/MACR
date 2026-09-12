from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from .accounting import CostClass
from .authority import AuthorityScope, DispatchAuthorityStore
from .batch_authority import (
    BatchAuthorityReference,
    BatchMemberScope,
    BatchScope,
)
from .canonical import aware_iso8601, sha256_id
from .config import ConnectionScope
from .contracts import ResultStatus
from .errors import MacrError, ProviderAdmissionBusyError
from .execution import (
    AcceptanceState,
    AuthorizationReference,
    DispatchContext,
    DispatchOrigin,
    InteractionPlane,
)
from .registry import ProviderRegistry
from .provider_admission import (
    AdmissionLane,
    ProjectAdmissionBinding,
    ProviderAdmissionRequest,
)
from .runtime import MacrRuntime, RuntimeServices, task_contract_digest
from .scheduler import (
    PlanQueue,
    QueueCandidate,
    QueueClaim,
    QueueMember,
    QueueMemberState,
    T1QueuePlan,
)
from .t1_manifest import (
    T1AuthorityBundle,
    T1ExecutionManifest,
    T1ExecutionMember,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class T1DispatchError(MacrError):
    """A T1 manifest cannot be staged or dispatched safely."""


@dataclass(frozen=True)
class T1DispatchResult:
    manifest_digest: str
    plan_digest: str
    member_id: str
    member_digest: str
    run_id: str
    queue_state: str
    provider_status: str
    provider_state: str
    capture_state: str
    return_contract_state: str
    accounting_state: str
    acceptance_state: str
    provider_attempted: bool
    reconciliation_required: bool
    terminal_evidence_digest: str
    observed_cost_usd: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_digest": self.manifest_digest,
            "plan_digest": self.plan_digest,
            "member_id": self.member_id,
            "member_digest": self.member_digest,
            "run_id": self.run_id,
            "queue_state": self.queue_state,
            "provider_status": self.provider_status,
            "provider_state": self.provider_state,
            "capture_state": self.capture_state,
            "return_contract_state": self.return_contract_state,
            "accounting_state": self.accounting_state,
            "acceptance_state": self.acceptance_state,
            "provider_attempted": self.provider_attempted,
            "reconciliation_required": self.reconciliation_required,
            "terminal_evidence_digest": self.terminal_evidence_digest,
            "observed_cost_usd": self.observed_cost_usd,
        }


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
            provider_tier_binding_digest=(
                member.provider_tier_binding_digest
            ),
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
        project_binding_digest: str,
        admission_lane: str,
        provider_admission_policy_digest: str,
    ) -> T1QueuePlan:
        return T1QueuePlan(
            plan_digest=manifest.plan_digest,
            members=tuple(self._queue_member(item) for item in manifest.members),
            aggregate_cost_ceiling_usd=manifest.aggregate_cost_ceiling_usd,
            authority=batch_authority,
            project_binding_digest=project_binding_digest,
            admission_lane=admission_lane,
            provider_admission_policy_digest=(
                provider_admission_policy_digest
            ),
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
            capability_binding = self.registry.capability_binding(
                member.route.provider_id
            )
            if self.services.capability_policies is not None:
                try:
                    active_binding = (
                        self.services.capability_policies.effective_binding(
                            member.route.provider_id,
                            member.route.provider_model_id,
                        )
                    )
                except (MacrError, ValueError) as exc:
                    raise T1DispatchError(
                        "T1 active provider capability binding is unavailable"
                    ) from exc
                if active_binding != capability_binding:
                    raise T1DispatchError(
                        "T1 active provider capability binding changed"
                    )
            if (
                capability_binding.binding_digest
                != member.provider_tier_binding_digest
            ):
                raise T1DispatchError(
                    "T1 route does not use the exact provider capability binding"
                )
            provider = self.registry.get(member.route.provider_id)
            validate_approval = getattr(provider, "validate_approval", None)
            if not callable(validate_approval):
                raise T1DispatchError(
                    "T1 provider cannot validate exact task approval metadata"
                )
            try:
                metadata = validate_approval(member.task)
            except MacrError as exc:
                raise T1DispatchError(
                    "T1 task approval is missing, stale, or invalid"
                ) from exc
            if (
                metadata.get("required_approval_sha256")
                != member.task.delegation_approval_sha256
                or metadata.get("model_token_policy_digest")
                != member.token_policy_digest
                or metadata.get("provider_tier_binding_digest")
                != member.provider_tier_binding_digest
            ):
                raise T1DispatchError(
                    "T1 task approval digest or token policy is stale"
                )

    @staticmethod
    def _dispatch_scope(
        manifest: T1ExecutionManifest,
        project_binding_digest: str,
        admission_lane: str,
        provider_admission_policy_digest: str,
    ) -> AuthorityScope:
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
            provider_tier_binding_digests=tuple(
                sorted(
                    {
                        item.provider_tier_binding_digest
                        for item in manifest.members
                    }
                )
            ),
            project_binding_digests=(project_binding_digest,),
            admission_lanes=(admission_lane,),
            provider_admission_policy_digests=(
                provider_admission_policy_digest,
            ),
            scope_contract_version=3,
        )

    def _verify_dispatch_authority(
        self,
        manifest: T1ExecutionManifest,
        reference: AuthorizationReference,
        *,
        project_binding_digest: str,
        admission_lane: str,
        provider_admission_policy_digest: str,
    ) -> None:
        for member in manifest.members:
            self.dispatch_authorities.verify(
                reference,
                provider_id=member.route.provider_id,
                plane=InteractionPlane.DELEGATION.value,
                task_type=member.task.task_type,
                batch_id=manifest.manifest_digest,
                member_digest=member.member_digest,
                provider_tier_binding_digest=(
                    member.provider_tier_binding_digest
                ),
                project_binding_digest=project_binding_digest,
                admission_lane=admission_lane,
                provider_admission_policy_digest=(
                    provider_admission_policy_digest
                ),
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
        if any(
            batch[name] is None
            for name in (
                "project_binding_digest",
                "admission_lane",
                "provider_admission_policy_digest",
            )
        ):
            raise T1DispatchError(
                "legacy_pre_provider_admission: existing T1 queue lacks "
                "provider admission binding"
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
            self._queue_plan(
                manifest,
                batch_reference,
                batch["project_binding_digest"],
                batch["admission_lane"],
                batch["provider_admission_policy_digest"],
            )
        )
        self._verify_dispatch_authority(
            manifest,
            dispatch_reference,
            project_binding_digest=batch["project_binding_digest"],
            admission_lane=batch["admission_lane"],
            provider_admission_policy_digest=(
                batch["provider_admission_policy_digest"]
            ),
        )
        return T1AuthorityBundle(
            manifest_digest=manifest.manifest_digest,
            batch_authority=batch_reference,
            dispatch_authority=dispatch_reference,
            member_ids=member_ids,
            worker_count=manifest.worker_count,
            expires_at=batch["expires_at"],
            project_binding_digest=batch["project_binding_digest"],
            admission_lane=batch["admission_lane"],
            provider_admission_policy_digest=(
                batch["provider_admission_policy_digest"]
            ),
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

    def load_bundle(self, manifest: T1ExecutionManifest) -> T1AuthorityBundle:
        if not isinstance(manifest, T1ExecutionManifest):
            raise ValueError("manifest must be a T1ExecutionManifest")
        bundle = self._existing_bundle(manifest)
        if bundle is None:
            raise T1DispatchError("T1 manifest has not been staged")
        return bundle

    def _validate_bundle(
        self,
        manifest: T1ExecutionManifest,
        bundle: T1AuthorityBundle,
        dispatcher_id: str,
    ) -> None:
        if not isinstance(bundle, T1AuthorityBundle):
            raise ValueError("bundle must be a T1AuthorityBundle")
        if (
            bundle.manifest_digest != manifest.manifest_digest
            or bundle.batch_authority.plan_digest != manifest.plan_digest
            or bundle.worker_count != manifest.worker_count
            or bundle.expires_at != manifest.expires_at
            or bundle.project_binding_digest is None
            or bundle.admission_lane is None
            or bundle.provider_admission_policy_digest is None
            or self.services.provider_admission is None
            or bundle.provider_admission_policy_digest
            != self.services.provider_admission.policy.policy_digest
        ):
            raise T1DispatchError("T1 authority bundle does not match manifest")
        expected_scope = self._batch_scope(manifest, bundle.expires_at)
        self.queue.authorities.verify(
            bundle.batch_authority,
            expected_scope,
            dispatcher_id=dispatcher_id,
        )
        self._verify_dispatch_authority(
            manifest,
            bundle.dispatch_authority,
            project_binding_digest=bundle.project_binding_digest,
            admission_lane=bundle.admission_lane,
            provider_admission_policy_digest=(
                bundle.provider_admission_policy_digest
            ),
        )
        actual_member_ids = tuple(
            item.member_id for item in self.queue.list_members(manifest.plan_digest)
        )
        if actual_member_ids != bundle.member_ids:
            raise T1DispatchError("T1 authority bundle member IDs are stale")

    @staticmethod
    def _member_for_claim(
        manifest: T1ExecutionManifest,
        bundle: T1AuthorityBundle,
        claim: QueueClaim | QueueCandidate,
    ) -> T1ExecutionMember:
        if (
            claim.plan_digest != manifest.plan_digest
            or not 0 <= claim.ordinal < len(manifest.members)
        ):
            raise T1DispatchError("claimed queue member is outside the exact manifest")
        member = manifest.members[claim.ordinal]
        expected = (
            bundle.member_ids[claim.ordinal],
            member.member_digest,
            member.route.provider_id,
            member.route.route_id,
            member.role_digest,
            member.privacy,
            member.context_class,
            member.cost_ceiling_usd,
            member.provider_tier_binding_digest,
        )
        actual = (
            claim.member_id,
            claim.member_digest,
            claim.provider_id,
            claim.route_id,
            claim.role_digest,
            claim.privacy,
            claim.context_class,
            claim.cost_ceiling_usd,
            claim.provider_tier_binding_digest,
        )
        if actual != expected:
            raise T1DispatchError("claimed queue member does not match manifest")
        return member

    def _runtime_evidence(
        self,
        run_id: str,
        *,
        failure_type: str | None,
    ) -> dict[str, object]:
        try:
            events = self.services.events.read_events(run_id=run_id)
        except Exception:
            events = ()
        dispatches = tuple(
            item for item in events if item["event_type"] == "provider.dispatch_requested"
        )
        terminals = tuple(
            item for item in events if item["event_type"] == "provider.candidate_completed"
        )
        try:
            accounting = self.services.accounting.read_invocation(run_id)
        except Exception:
            accounting = None
        try:
            capture = self.services.vault.read_by_run(run_id)
        except Exception:
            capture = None
        terminal = terminals[0]["payload"] if len(terminals) == 1 else None
        dispatched = len(dispatches) == 1
        accounting_terminal = bool(
            accounting is not None and accounting.get("terminal_at") is not None
        )
        billing_state = accounting.get("billing_state") if accounting is not None else None
        observed_cost = (
            accounting.get("currency_cost_usd") if accounting is not None else None
        )
        complete = bool(
            dispatched
            and len(terminals) == 1
            and accounting_terminal
            and billing_state != "unknown_after_dispatch"
            and observed_cost is not None
        )
        public = {
            "run_id": run_id,
            "dispatch_event_ids": [item["event_id"] for item in dispatches],
            "terminal_event_ids": [item["event_id"] for item in terminals],
            "accounting_terminal": accounting_terminal,
            "billing_state": billing_state,
            "observed_cost_usd": observed_cost,
            "capture_id": capture.capture_id if capture is not None else None,
            "capture_answer_sha256": (
                capture.sha256 if capture is not None else None
            ),
            "provider_status": terminal.get("status") if terminal else None,
            "provider_state": terminal.get("provider_state") if terminal else None,
            "capture_state": terminal.get("capture_state") if terminal else None,
            "return_contract_state": (
                terminal.get("return_contract_state") if terminal else None
            ),
            "failure_type": failure_type,
        }
        return {
            "dispatched": dispatched,
            "complete": complete,
            "accounting": accounting,
            "observed_cost_usd": observed_cost,
            "provider_status": public["provider_status"],
            "provider_state": public["provider_state"],
            "capture_state": public["capture_state"],
            "return_contract_state": public["return_contract_state"],
            "terminal_evidence_digest": sha256_id(
                "t1_terminal_evidence_v1",
                public,
            ),
        }

    def _record_plan_cost(
        self,
        manifest: T1ExecutionManifest,
        member: T1ExecutionMember,
        run_id: str,
        accounting: dict[str, object],
    ) -> None:
        observed_cost = accounting.get("currency_cost_usd")
        if not isinstance(observed_cost, (int, float)) or isinstance(
            observed_cost,
            bool,
        ):
            raise T1DispatchError("T1 observed provider cost is unavailable")
        basis_digest = sha256_id(
            "pricing_basis_reference_v1",
            {
                "pricing_basis_version": accounting.get("pricing_basis_version"),
                "cost_kind": accounting.get("cost_kind"),
            },
        )
        self.services.accounting.record_plan_cost(
            manifest.plan_digest,
            run_id,
            CostClass.PRODUCTION_EXECUTION_COST,
            float(observed_cost),
            str(accounting.get("cost_kind") or "observed"),
            basis_digest,
            role_digest=member.role_digest,
            route_id=member.route.route_id,
            idempotency_key=f"{manifest.manifest_digest}:{member.member_digest}",
        )
        total = sum(self.services.accounting.plan_costs(manifest.plan_digest).values())
        if total > manifest.aggregate_cost_ceiling_usd + 1e-12:
            raise T1DispatchError("T1 aggregate accounting ceiling is exceeded")

    def _reconciliation_result(
        self,
        manifest: T1ExecutionManifest,
        member: T1ExecutionMember,
        claim: QueueClaim,
        run_id: str,
        evidence: dict[str, object],
    ) -> T1DispatchResult:
        observed_cost = evidence.get("observed_cost_usd")
        normalized_cost = (
            float(observed_cost)
            if isinstance(observed_cost, (int, float))
            and not isinstance(observed_cost, bool)
            else None
        )
        digest = str(evidence["terminal_evidence_digest"])
        try:
            self.queue.require_reconciliation(
                claim.member_id,
                claim.dispatcher_id,
                claim.fencing_token,
                terminal_evidence_digest=digest,
                observed_cost_usd=normalized_cost,
            )
        except Exception:
            record = self.queue.read_member(claim.member_id)
            if record.state is not QueueMemberState.RECONCILIATION_REQUIRED:
                raise
        return T1DispatchResult(
            manifest_digest=manifest.manifest_digest,
            plan_digest=manifest.plan_digest,
            member_id=claim.member_id,
            member_digest=member.member_digest,
            run_id=run_id,
            queue_state=QueueMemberState.RECONCILIATION_REQUIRED.value,
            provider_status=str(evidence.get("provider_status") or "unknown_after_dispatch"),
            provider_state="unknown_after_dispatch",
            capture_state=str(evidence.get("capture_state") or "unknown"),
            return_contract_state=str(
                evidence.get("return_contract_state") or "not_evaluated"
            ),
            accounting_state=(
                "complete"
                if isinstance(evidence.get("accounting"), dict)
                and evidence["accounting"].get("terminal_at") is not None
                else "incomplete"
            ),
            acceptance_state=AcceptanceState.PENDING.value,
            provider_attempted=bool(evidence.get("dispatched")),
            reconciliation_required=True,
            terminal_evidence_digest=digest,
            observed_cost_usd=normalized_cost,
        )

    def _plan_has_reconciliation(self, plan_digest: str) -> bool:
        # Materialize expired claims first, then scope the stop decision to the
        # exact plan instead of using the returned global aggregate.
        self.queue.state_counts()
        return any(
            item.state is QueueMemberState.RECONCILIATION_REQUIRED
            for item in self.queue.list_members(plan_digest)
        )

    def run_one(
        self,
        manifest: T1ExecutionManifest,
        bundle: T1AuthorityBundle,
        dispatcher_id: str,
        origin: DispatchOrigin,
        *,
        allow_network: bool,
        allow_local: bool,
    ) -> T1DispatchResult:
        if not isinstance(manifest, T1ExecutionManifest):
            raise ValueError("manifest must be a T1ExecutionManifest")
        if not isinstance(origin, DispatchOrigin):
            raise ValueError("origin must be a DispatchOrigin")
        if not isinstance(allow_network, bool) or not isinstance(allow_local, bool):
            raise ValueError("T1 provider opt-ins must be boolean")
        if self._plan_has_reconciliation(manifest.plan_digest):
            raise T1DispatchError(
                "plan reconciliation must be empty before a T1 claim"
            )
        self._validate_bundle(manifest, bundle, dispatcher_id)
        self._validate_manifest_routes(manifest)
        provider = self.registry.get(manifest.members[0].route.provider_id)
        if (
            provider.connection_scope is ConnectionScope.EXTERNAL_HTTPS
            and not allow_network
        ):
            raise T1DispatchError("T1 worker requires explicit network opt-in")
        if (
            provider.connection_scope is ConnectionScope.LOOPBACK_HTTP
            and not allow_local
        ):
            raise T1DispatchError("T1 worker requires explicit local opt-in")
        lease_seconds = max(
            1,
            min(
                86_400,
                int(max(item.task.constraints.max_latency_s for item in manifest.members))
                + 60,
            ),
        )
        candidate = self.queue.peek_claimable(
            dispatcher_id,
            plan_digest=manifest.plan_digest,
        )
        if candidate is None:
            raise T1DispatchError("T1 manifest has no queued member")
        member = self._member_for_claim(manifest, bundle, candidate)
        run_id = str(uuid.uuid4())
        assert self.services.provider_admission is not None
        assert bundle.project_binding_digest is not None
        assert bundle.admission_lane is not None
        assert bundle.provider_admission_policy_digest is not None
        context = DispatchContext(
            run_id=run_id,
            plane=InteractionPlane.DELEGATION,
            origin=origin,
            authorization=bundle.dispatch_authority,
            policy_snapshot_sha256=member.route.policy_snapshot_id,
            batch_id=manifest.manifest_digest,
            member_digest=member.member_digest,
            plan_digest=manifest.plan_digest,
            plan_revision=manifest.plan_revision,
            role_slot_id=f"t1-member-{member.ordinal}",
            route_id=member.route.route_id,
            model_token_policy_digest=member.token_policy_digest,
            provider_tier_binding_digest=member.provider_tier_binding_digest,
            project_binding_digest=bundle.project_binding_digest,
            admission_lane=bundle.admission_lane,
            provider_admission_policy_digest=(
                bundle.provider_admission_policy_digest
            ),
        )
        admission_request = ProviderAdmissionRequest(
            request_id=str(uuid.uuid4()),
            provider_id=member.route.provider_id,
            project_binding_digest=bundle.project_binding_digest,
            lane=AdmissionLane(bundle.admission_lane),
            run_id=run_id,
            authorization=bundle.dispatch_authority,
            plane=InteractionPlane.DELEGATION.value,
            task_type=member.task.task_type,
            task_digest=task_contract_digest(member.task),
            member_digest=member.member_digest,
            batch_id=manifest.manifest_digest,
            provider_tier_binding_digest=(
                member.provider_tier_binding_digest
            ),
        )
        try:
            admission_permit = self.services.provider_admission.try_admit(
                admission_request,
                ttl_seconds=lease_seconds,
            )
        except ProviderAdmissionBusyError:
            self.services.provider_admission.cancel_waiting(
                admission_request.request_id,
                admission_request.run_id,
            )
            raise
        claim = self.queue.claim(
            dispatcher_id,
            lease_seconds=lease_seconds,
            plan_digest=manifest.plan_digest,
            expected_member_id=candidate.member_id,
        )
        if claim is None:
            self.services.provider_admission.cancel_before_transport(
                admission_permit
            )
            raise T1DispatchError(
                "T1 claim changed after provider admission; retry without attempt"
            )
        try:
            member = self._member_for_claim(manifest, bundle, claim)
            self._validate_bundle(manifest, bundle, dispatcher_id)
        except Exception as exc:
            self.services.provider_admission.cancel_before_transport(
                admission_permit
            )
            evidence = {
                "dispatched": False,
                "complete": False,
                "accounting": None,
                "observed_cost_usd": None,
                "provider_status": "not_dispatched",
                "provider_state": "not_dispatched",
                "capture_state": "absent",
                "return_contract_state": "not_evaluated",
                "terminal_evidence_digest": sha256_id(
                    "t1_claim_mismatch_v1",
                    {
                        "manifest_digest": manifest.manifest_digest,
                        "member_id": claim.member_id,
                        "failure_type": type(exc).__name__,
                    },
                ),
            }
            fallback_member = manifest.members[claim.ordinal]
            return self._reconciliation_result(
                manifest,
                fallback_member,
                claim,
                run_id,
                evidence,
            )
        result = None
        failure_type = None
        try:
            result = MacrRuntime(self.registry, self.services).invoke(
                member.route.provider_id,
                member.task,
                context,
                provider_admission_permit=admission_permit,
                provider_admission_request=admission_request,
            )
        except Exception as exc:
            failure_type = type(exc).__name__
        evidence = self._runtime_evidence(run_id, failure_type=failure_type)
        if not evidence["dispatched"]:
            digest = str(evidence["terminal_evidence_digest"])
            record = self.queue.release_before_dispatch(
                claim.member_id,
                claim.dispatcher_id,
                claim.fencing_token,
            )
            return T1DispatchResult(
                manifest_digest=manifest.manifest_digest,
                plan_digest=manifest.plan_digest,
                member_id=claim.member_id,
                member_digest=member.member_digest,
                run_id=run_id,
                queue_state=record.state.value,
                provider_status=(
                    result.status.value
                    if result is not None
                    else ResultStatus.CANDIDATE_FAILURE.value
                ),
                provider_state="not_dispatched",
                capture_state="absent",
                return_contract_state="not_evaluated",
                accounting_state="not_started",
                acceptance_state=AcceptanceState.PENDING.value,
                provider_attempted=False,
                reconciliation_required=False,
                terminal_evidence_digest=digest,
                observed_cost_usd=0.0,
            )
        if not evidence["complete"] or result is None:
            return self._reconciliation_result(
                manifest,
                member,
                claim,
                run_id,
                evidence,
            )
        try:
            accounting = evidence["accounting"]
            assert isinstance(accounting, dict)
            self._record_plan_cost(manifest, member, run_id, accounting)
            observed_cost = float(evidence["observed_cost_usd"])
            digest = str(evidence["terminal_evidence_digest"])
            terminal_method = (
                self.queue.complete
                if result.status is ResultStatus.CANDIDATE_SUCCESS
                else self.queue.fail
            )
            record = terminal_method(
                claim.member_id,
                claim.dispatcher_id,
                claim.fencing_token,
                terminal_evidence_digest=digest,
                observed_cost_usd=observed_cost,
            )
        except Exception:
            return self._reconciliation_result(
                manifest,
                member,
                claim,
                run_id,
                evidence,
            )
        return T1DispatchResult(
            manifest_digest=manifest.manifest_digest,
            plan_digest=manifest.plan_digest,
            member_id=claim.member_id,
            member_digest=member.member_digest,
            run_id=run_id,
            queue_state=record.state.value,
            provider_status=result.status.value,
            provider_state=str(evidence["provider_state"]),
            capture_state=str(evidence["capture_state"]),
            return_contract_state=str(evidence["return_contract_state"]),
            accounting_state="complete",
            acceptance_state=AcceptanceState.PENDING.value,
            provider_attempted=True,
            reconciliation_required=False,
            terminal_evidence_digest=digest,
            observed_cost_usd=observed_cost,
        )

    def stage(
        self,
        manifest: T1ExecutionManifest,
        dispatcher_ids: Sequence[str],
        expires_at: str,
        project_binding: ProjectAdmissionBinding | None = None,
        admission_lane: AdmissionLane = AdmissionLane.ROUTINE,
    ) -> T1AuthorityBundle:
        if not isinstance(manifest, T1ExecutionManifest):
            raise ValueError("manifest must be a T1ExecutionManifest")
        project = project_binding or ProjectAdmissionBinding(
            "operator-default",
            1,
            "operator_asserted",
        )
        if not isinstance(project, ProjectAdmissionBinding):
            raise ValueError(
                "project_binding must be a ProjectAdmissionBinding"
            )
        if not isinstance(admission_lane, AdmissionLane):
            raise ValueError("admission_lane must be an AdmissionLane")
        if self.services.provider_admission is None:
            raise T1DispatchError("T1 provider admission kernel is unavailable")
        admission_policy_digest = (
            self.services.provider_admission.policy.policy_digest
        )
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
        if self._plan_has_reconciliation(manifest.plan_digest):
            raise T1DispatchError(
                "plan reconciliation must be empty before T1 staging"
            )
        self._validate_manifest_routes(manifest)
        existing = self._existing_bundle(manifest)
        if existing is not None:
            if (
                existing.project_binding_digest != project.binding_digest
                or existing.admission_lane != admission_lane.value
                or existing.provider_admission_policy_digest
                != admission_policy_digest
            ):
                raise T1DispatchError(
                    "existing T1 provider admission binding conflicts"
                )
            return existing
        batch_reference: BatchAuthorityReference | None = None
        dispatch_reference: AuthorizationReference | None = None
        try:
            batch_scope = self._batch_scope(manifest, normalized_expiry)
            batch_reference = self.queue.authorities.issue(batch_scope)
            dispatch_reference = self.dispatch_authorities.issue(
                source_kind="t1_manifest",
                source_id=manifest.manifest_digest,
                scope=self._dispatch_scope(
                    manifest,
                    project.binding_digest,
                    admission_lane.value,
                    admission_policy_digest,
                ),
                expires_at=normalized_expiry,
            )
            member_ids = self.queue.enqueue(
                self._queue_plan(
                    manifest,
                    batch_reference,
                    project.binding_digest,
                    admission_lane.value,
                    admission_policy_digest,
                )
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
            worker_count=manifest.worker_count,
            expires_at=normalized_expiry,
            project_binding_digest=project.binding_digest,
            admission_lane=admission_lane.value,
            provider_admission_policy_digest=admission_policy_digest,
        )


__all__ = ["T1DispatchError", "T1DispatchResult", "T1Dispatcher"]
