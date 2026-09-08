from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .authority import AuthorityScope
from .accounting import read_accounting_status
from .coordination import CoordinationPlan, PlanExecutionMode
from .config import (
    ConnectionScope,
    load_discovery_configs,
    load_provider_configs,
)
from .contracts import ResultStatus, TaskContract
from .differential import (
    DifferentialCandidateResult,
    DifferentialRunManifest,
    build_differential_manifest,
    compare_differential_results,
    strict_json_bytes,
)
from .errors import (
    MacrError,
    ProviderOutputBudgetTooSmallError,
    ProviderTaskTypeError,
)
from .evidence_import import EvidenceImporter
from .execution import DispatchContext, DispatchOrigin, InteractionPlane
from .legacy_ledger import LegacyLedgerImporter
from .model_passport import ModelPassportProjector
from .model_token_store import (
    ModelTokenPolicyStore,
    read_model_token_override_status,
)
from .provider_capability_store import read_effective_policy
from .observatory import ModelObservatory
from .observatory_db import ObservatoryDatabase
from .discovery.openrouter import (
    OpenRouterModelNormalizer,
    OpenRouterWebDiscoveryProvider,
)
from .registry import ProviderRegistry
from .providers.glm import GlmFlashWorkerProvider
from .glm_approval import GlmApprovalStore
from .runtime import MacrRuntime, RuntimeServices
from .scheduler import (
    PlanQueue,
    QueueMemberRecord,
    QueueMemberState,
    read_queue_tier_status,
)
from .storage import StorageLayout
from .t1_dispatcher import T1Dispatcher
from .t1_manifest import load_t1_manifest
from .task_preflight import validate_task_consistency
from .token_policy import t1_glm_live_policy


def _default_config(layout: StorageLayout) -> Path:
    return Path(layout.source_root) / "config" / "providers.json"


def _doctor(
    config_path: str | None,
    strict: bool,
    *,
    key_sources: Mapping[str, Any] | None = None,
) -> int:
    layout = StorageLayout.from_environment()
    path = Path(config_path) if config_path else _default_config(layout)
    configs = load_provider_configs(path)
    discovery_configs = load_discovery_configs(path)
    registry = ProviderRegistry.from_configs(configs, key_sources=key_sources)
    report = {
        "runtime": "macr-runtime",
        "version": "0.7.0a0",
        "network_activity": False,
        "storage": layout.describe(),
        "providers": list(registry.health()),
        "provider_environment": [item.public_summary(os.environ) for item in configs],
        "discovery_environment": [
            item.public_summary() for item in discovery_configs
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    enabled_provider_ids = {item.id for item in configs if item.enabled}
    if strict and any(
        not item["ready"] and item["provider_id"] in enabled_provider_ids
        for item in report["providers"]
    ):
        return 2
    return 0


def _init_state() -> int:
    layout = StorageLayout.from_environment()
    paths = layout.ensure_state_tree()
    print(json.dumps({"created_or_verified": [str(item) for item in paths]}, ensure_ascii=False, indent=2))
    return 0


def _capability_status(
    provider_id: str | None,
    config_path: str | None,
) -> int:
    layout = StorageLayout.from_environment()
    path = Path(config_path) if config_path else _default_config(layout)
    try:
        configs = load_provider_configs(path)
        selected = tuple(
            item
            for item in configs
            if item.kind == "zai_glm_worker"
            and (provider_id is None or item.id == provider_id)
        )
        if not selected:
            raise ValueError("no provider capability policy matches selection")
        providers = []
        for config in selected:
            policy = read_effective_policy(
                layout.provider_capability_policy_db_path,
                config.id,
                config.model or "",
            )
            binding = policy.binding()
            providers.append(
                {
                    "provider_id": policy.provider_id,
                    "model_id": policy.model_id,
                    "tier_id": policy.tier_id,
                    "revision": policy.revision,
                    "binding_digest": binding.binding_digest,
                    "complete_policy_digest": policy.complete_policy_digest,
                    "max_latency_s": policy.max_latency_s,
                    "allowed_task_types": list(policy.allowed_task_types),
                    "patch_allowed": policy.patch_allowed,
                    "write_scope_allowed": policy.write_scope_allowed,
                    "tools_allowed": policy.tools_allowed,
                }
            )
        report = {
            "status": "provider_capability_status",
            "providers": providers,
            "approval_records": GlmApprovalStore(
                layout.state_root
            ).status_snapshot(),
            "model_token_overrides": read_model_token_override_status(
                layout.model_token_policy_db_path
            ),
            "t1_queue": read_queue_tier_status(layout.runtime_db_path),
            "network_activity": False,
            "provider_generation": False,
        }
    except (OSError, ValueError, MacrError) as exc:
        print(
            json.dumps(
                {
                    "status": "provider_capability_status_failed",
                    "failure_type": type(exc).__name__,
                    "network_activity": False,
                    "provider_generation": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 4
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _accounting_status(
    provider_id: str | None = None,
    since: str | None = None,
) -> int:
    layout = StorageLayout.from_environment()
    try:
        snapshot = read_accounting_status(
            layout.accounting_db_path,
            provider_id=provider_id,
            since=since,
        )
    except (OSError, ValueError, MacrError) as exc:
        print(
            json.dumps(
                {
                    "status": "accounting_status_failed",
                    "failure_type": type(exc).__name__,
                    "network_activity": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 4
    print(
        json.dumps(
            {
                "status": "accounting_status",
                "accounting": snapshot.to_dict(),
                "network_activity": False,
                "provider_generation": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _validate_task(path: str) -> int:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    task = TaskContract.from_dict(document)
    validate_task_consistency(task)
    print(json.dumps(task.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _public_queue_member(record: QueueMemberRecord) -> dict[str, object]:
    return {
        "member_id": record.member_id,
        "plan_digest": record.plan_digest,
        "ordinal": record.ordinal,
        "member_digest": record.member_digest,
        "state": record.state.value,
        "lease_holder": record.lease_holder,
        "fencing_token": record.fencing_token,
        "lease_expires_at": record.lease_expires_at,
        "attempts": record.attempts,
        "terminal_at": record.terminal_at,
        "terminal_evidence_digest": record.terminal_evidence_digest,
        "observed_cost_usd": record.observed_cost_usd,
        "provider_tier_binding_digest": (
            record.provider_tier_binding_digest
        ),
    }


def _queue_status(
    state: str,
    *,
    limit: int,
    after_member_id: str | None,
) -> int:
    layout = StorageLayout.from_environment()
    selected_state = QueueMemberState(state)
    queue = PlanQueue(layout.runtime_db_path)
    members = queue.list_by_state(
        selected_state,
        limit=limit,
        after_member_id=after_member_id,
    )
    print(
        json.dumps(
            {
                "status": "queue_status",
                "network_activity": False,
                "selected_state": selected_state.value,
                "counts": queue.state_counts(),
                "members": [_public_queue_member(item) for item in members],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _t1_stage(
    manifest_path: str,
    config_path: str | None,
    *,
    dispatcher_ids: Sequence[str],
    expires_in_minutes: int,
) -> int:
    if (
        isinstance(expires_in_minutes, bool)
        or not isinstance(expires_in_minutes, int)
        or not 1 <= expires_in_minutes <= 1_440
    ):
        raise ValueError("expires-in-minutes must be between 1 and 1440")
    layout = StorageLayout.from_environment()
    layout.ensure_state_tree()
    services = RuntimeServices.from_layout(layout)
    if not _legacy_migration_complete(layout, services):
        raise ValueError("T1 staging requires complete legacy migration")
    path = Path(config_path) if config_path else _default_config(layout)
    config = next(
        item
        for item in load_provider_configs(path)
        if item.id == "glm_flash_worker"
    )
    provider = GlmFlashWorkerProvider(
        config,
        environ=os.environ,
        token_policy=t1_glm_live_policy(),
        capability_policy=(
            services.capability_policies.effective_policy(
                config.id,
                config.model or "",
            )
            if services.capability_policies is not None
            else read_effective_policy(
                layout.provider_capability_policy_db_path,
                config.id,
                config.model or "",
            )
        ),
    )
    manifest = load_t1_manifest(manifest_path)
    now = datetime.now(timezone.utc)
    manifest_expiry = datetime.fromisoformat(manifest.expires_at).astimezone(
        timezone.utc
    )
    if manifest_expiry > now + timedelta(minutes=expires_in_minutes):
        raise ValueError("T1 manifest expiry exceeds the operator staging window")
    bundle = T1Dispatcher(
        ProviderRegistry((provider,)),
        services,
    ).stage(
        manifest,
        tuple(dispatcher_ids),
        manifest.expires_at,
    )
    print(
        json.dumps(
            {
                "status": "t1_staged",
                "network_activity": False,
                "provider_call_performed": False,
                "worker_count": manifest.worker_count,
                "member_count": len(manifest.members),
                "authority_bundle": bundle.to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _t1_worker(
    manifest_path: str,
    config_path: str | None,
    *,
    dispatcher_id: str,
    allow_network: bool,
    allow_local: bool,
    registry_override: ProviderRegistry | None = None,
    services_override: RuntimeServices | None = None,
) -> int:
    if not allow_network:
        return _print_opt_in_error(
            "network_opt_in_required",
            "--allow-network",
        )
    layout = StorageLayout.from_environment()
    if services_override is None:
        layout.ensure_state_tree()
        services = RuntimeServices.from_layout(layout)
    else:
        services = services_override
    if not _legacy_migration_complete(layout, services):
        raise ValueError("T1 worker requires complete legacy migration")
    if registry_override is None:
        path = Path(config_path) if config_path else _default_config(layout)
        config = next(
            item
            for item in load_provider_configs(path)
            if item.id == "glm_flash_worker"
        )
        provider = GlmFlashWorkerProvider(
            config,
            environ=os.environ,
            token_policy=t1_glm_live_policy(),
            capability_policy=(
                services.capability_policies.effective_policy(
                    config.id,
                    config.model or "",
                )
                if services.capability_policies is not None
                else read_effective_policy(
                    layout.provider_capability_policy_db_path,
                    config.id,
                    config.model or "",
                )
            ),
        )
        registry = ProviderRegistry((provider,))
    else:
        registry = registry_override
    manifest = load_t1_manifest(manifest_path)
    dispatcher = T1Dispatcher(registry, services)
    result = dispatcher.run_one(
        manifest,
        dispatcher.load_bundle(manifest),
        dispatcher_id,
        DispatchOrigin("cli", "process_id", str(os.getpid())),
        allow_network=allow_network,
        allow_local=allow_local,
    )
    status = (
        "t1_worker_completed"
        if result.queue_state == QueueMemberState.COMPLETED.value
        else "t1_worker_terminal"
    )
    print(
        json.dumps(
            {
                "status": status,
                "network_activity": result.provider_attempted,
                "worker_count": manifest.worker_count,
                "member_count": len(manifest.members),
                "result": result.to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.queue_state == QueueMemberState.COMPLETED.value else 4


def _glm_preflight(
    task_path: str,
    config_path: str | None,
    *,
    show_required_digest: bool,
) -> int:
    layout = StorageLayout.from_environment()
    path = Path(config_path) if config_path else _default_config(layout)
    policy_violation: dict[str, object] | None = None
    try:
        config = next(
            item
            for item in load_provider_configs(path)
            if item.id == "glm_flash_worker"
        )
        task_document = json.loads(Path(task_path).read_text(encoding="utf-8"))
        task = TaskContract.from_dict(task_document)
        validate_task_consistency(task)
        token_store = ModelTokenPolicyStore(layout.model_token_policy_db_path)
        provider = GlmFlashWorkerProvider(
            config,
            environ=os.environ,
            token_policy=token_store.effective_policy(
                config.id,
                config.model or "",
            ),
            capability_policy=read_effective_policy(
                layout.provider_capability_policy_db_path,
                config.id,
                config.model or "",
            ),
        )
        metadata = (
            provider.approval_metadata(task)
            if show_required_digest
            else provider.validate_approval(task)
        )
    except StopIteration:
        failure_type = "ConfigurationError"
    except (ProviderOutputBudgetTooSmallError, ProviderTaskTypeError) as exc:
        failure_type = type(exc).__name__
        policy_violation = exc.safe_diagnostic()
    except (OSError, json.JSONDecodeError, ValueError, MacrError) as exc:
        failure_type = type(exc).__name__
    else:
        print(
            json.dumps(
                {
                    "status": (
                        "approval_required"
                        if show_required_digest
                        else "preflight_structurally_valid"
                    ),
                    **metadata,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    failure = {
        "status": "approval_invalid",
        "failure_type": failure_type,
        "detail": "GLM task approval preflight failed; task content omitted.",
    }
    if policy_violation is not None:
        failure["policy_violation"] = policy_violation
    print(json.dumps(failure, ensure_ascii=False, indent=2))
    return 4


def _glm_approve(
    task_path: str,
    config_path: str | None,
    *,
    expires_in_days: int,
    key_source: Any | None = None,
    replace_existing: bool = False,
) -> int:
    layout = StorageLayout.from_environment()
    path = Path(config_path) if config_path else _default_config(layout)
    policy_violation: dict[str, object] | None = None
    try:
        config = next(
            item
            for item in load_provider_configs(path)
            if item.id == "glm_flash_worker"
        )
        task_document = json.loads(Path(task_path).read_text(encoding="utf-8"))
        task = TaskContract.from_dict(task_document)
        validate_task_consistency(task)
        token_store = ModelTokenPolicyStore(layout.model_token_policy_db_path)
        provider = GlmFlashWorkerProvider(
            config,
            environ=os.environ,
            key_source=key_source,
            token_policy=token_store.effective_policy(
                config.id,
                config.model or "",
            ),
            capability_policy=read_effective_policy(
                layout.provider_capability_policy_db_path,
                config.id,
                config.model or "",
            ),
        )
        metadata = provider.approval_metadata(task)
        if task.delegation_approval_sha256 != metadata["required_approval_sha256"]:
            raise ValueError("task digest is missing or stale")
        signing_key = provider.key_source.load()
        try:
            record = provider.approval_store.create(
                metadata["required_approval_sha256"],
                signing_key=signing_key,
                expires_in_days=expires_in_days,
                replace_existing=replace_existing,
                approval_contract_schema=metadata["approval_schema"],
                provider_tier_binding_digest=metadata[
                    "provider_tier_binding_digest"
                ],
            )
        finally:
            signing_key = None
    except StopIteration:
        failure_type = "ConfigurationError"
    except (ProviderOutputBudgetTooSmallError, ProviderTaskTypeError) as exc:
        failure_type = type(exc).__name__
        policy_violation = exc.safe_diagnostic()
    except (OSError, json.JSONDecodeError, ValueError, MacrError) as exc:
        failure_type = type(exc).__name__
    else:
        print(
            json.dumps(
                {
                    "status": "host_approval_created",
                    "approval_sha256": record["approval_sha256"],
                    "approved_by": record["approved_by"],
                    "approved_at": record["approved_at"],
                    "expires_at": record["expires_at"],
                    "nonce": record["nonce"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    failure = {
        "status": "host_approval_failed",
        "failure_type": failure_type,
        "detail": "GLM host approval failed; task content omitted.",
    }
    if policy_violation is not None:
        failure["policy_violation"] = policy_violation
    print(json.dumps(failure, ensure_ascii=False, indent=2))
    return 4


def _print_opt_in_error(status: str, flag: str) -> int:
    print(
        json.dumps(
            {
                "status": status,
                "detail": (
                    f"Re-run with {flag} only after reviewing provider policy."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 3


def _legacy_source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _legacy_migration_complete(
    layout: StorageLayout,
    services: RuntimeServices,
) -> bool:
    source = layout.ledger_path
    if not source.is_file() or source.stat().st_size == 0:
        return True
    source_sha256 = _legacy_source_sha256(source)
    source_bytes = source.stat().st_size
    connection = services.events.database.connect()
    try:
        row = connection.execute(
            """
            SELECT source_bytes, complete
            FROM legacy_sources
            WHERE source_sha256 = ?
            """,
            (source_sha256,),
        ).fetchone()
    finally:
        connection.close()
    return bool(
        row is not None
        and row["source_bytes"] == source_bytes
        and row["complete"] == 1
    )


def _migrate_ledger(*, dry_run: bool, expected_count: int | None) -> int:
    layout = StorageLayout.from_environment()
    source = layout.ledger_path
    if expected_count is not None and expected_count < 0:
        raise ValueError("expected_count must be non-negative")
    if not source.is_file() or source.stat().st_size == 0:
        print(
            json.dumps(
                {
                    "status": "legacy_ledger_absent",
                    "source_bytes": 0,
                    "network_activity": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    importer = LegacyLedgerImporter(
        layout.runtime_db_path,
        layout.quarantine_root,
    )
    report = (
        importer.inspect(source, expected_count=expected_count)
        if dry_run
        else importer.import_file(source, expected_count=expected_count)
    )
    status = (
        "legacy_migration_dry_run_complete"
        if dry_run and report.complete
        else (
            "legacy_migration_complete"
            if report.complete
            else "legacy_migration_incomplete"
        )
    )
    print(
        json.dumps(
            {
                "status": status,
                **asdict(report),
                "network_activity": False,
                "source_preserved": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report.complete else 5


def _evidence_inspect(manifest_path: str) -> int:
    try:
        report = EvidenceImporter(None).inspect(manifest_path)
    except (OSError, ValueError, MacrError) as exc:
        print(
            json.dumps(
                {
                    "status": "evidence_inspection_failed",
                    "failure_type": type(exc).__name__,
                    "detail": (
                        "Reviewed evidence inspection failed; paths and "
                        "external content omitted."
                    ),
                    "network_activity": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 4
    print(
        json.dumps(
            {
                "status": "evidence_inspection_complete",
                **report.to_dict(),
                "network_activity": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _evidence_import(manifest_path: str, expected_digest: str) -> int:
    try:
        layout = StorageLayout.from_environment()
        store = ObservatoryDatabase(
            layout.observatory_db_path,
            layout.observatory_snapshot_root,
        )
        report = EvidenceImporter(store).import_manifest(
            manifest_path,
            expected_digest,
        )
    except (OSError, ValueError, MacrError) as exc:
        print(
            json.dumps(
                {
                    "status": "evidence_import_failed",
                    "failure_type": type(exc).__name__,
                    "detail": (
                        "Reviewed evidence import failed; paths and external "
                        "content omitted."
                    ),
                    "network_activity": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 4
    print(
        json.dumps(
            {
                "status": "evidence_import_complete",
                **report.to_dict(),
                "network_activity": False,
                "promotion_performed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _model_observe(
    snapshot_path: str,
    expected_digest: str,
    observed_at: str,
) -> int:
    try:
        source = Path(snapshot_path)
        if source.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("model snapshot exceeds 64 MiB")
        raw = source.read_bytes()
        provider = OpenRouterWebDiscoveryProvider(
            raw,
            observed_at=observed_at,
            expected_sha256=expected_digest,
        )
        layout = StorageLayout.from_environment()
        store = ObservatoryDatabase(
            layout.observatory_db_path,
            layout.observatory_snapshot_root,
        )
        report = ModelObservatory(
            store,
            OpenRouterModelNormalizer(),
        ).ingest(provider, provider.default_query())
    except (OSError, ValueError, MacrError) as exc:
        print(
            json.dumps(
                {
                    "status": "model_observation_failed",
                    "failure_type": type(exc).__name__,
                    "detail": (
                        "Model observation failed; source path and raw catalog "
                        "content omitted."
                    ),
                    "network_activity": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 4
    print(
        json.dumps(
            {
                "status": "model_observation_complete",
                **report.to_dict(),
                "network_activity": False,
                "execution_provider_created": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _model_passport(subject_id: str, as_of: str) -> int:
    try:
        layout = StorageLayout.from_environment()
        store = ObservatoryDatabase(
            layout.observatory_db_path,
            layout.observatory_snapshot_root,
        )
        passport = ModelPassportProjector(store).build(subject_id, as_of)
    except (OSError, ValueError, MacrError) as exc:
        print(
            json.dumps(
                {
                    "status": "model_passport_failed",
                    "failure_type": type(exc).__name__,
                    "network_activity": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 4
    print(
        json.dumps(
            {
                "status": "model_passport_complete",
                "passport": passport.to_dict(),
                "network_activity": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _plan_shadow(
    plan_path: str,
    baseline_route_id: str,
    persisted_at: str,
) -> int:
    try:
        document = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        plan = CoordinationPlan.from_dict(document)
        if plan.execution_mode is not PlanExecutionMode.SHADOW_ONLY:
            raise ValueError("plan-shadow accepts only shadow_only plans")
        layout = StorageLayout.from_environment()
        store = ObservatoryDatabase(
            layout.observatory_db_path,
            layout.observatory_snapshot_root,
        )
        record, comparison = store.append_shadow_plan(
            plan,
            baseline_route_id=baseline_route_id,
            persisted_at=persisted_at,
            metadata={
                "comparison_kind": "shadow_route_proposal",
                "plan_revision": plan.plan_revision,
                "execution_mode": plan.execution_mode.value,
            },
        )
    except (
        OSError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
        ValueError,
        MacrError,
    ) as exc:
        print(
            json.dumps(
                {
                    "status": "shadow_plan_failed",
                    "failure_type": type(exc).__name__,
                    "network_activity": False,
                    "dispatch_performed": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 4
    print(
        json.dumps(
            {
                "status": "shadow_plan_persisted",
                "plan_digest": record.plan_digest,
                "plan_revision": record.plan_revision,
                "comparison_id": comparison.comparison_id,
                "baseline_route_id": comparison.baseline_route_id,
                "proposed_route_id": comparison.proposed_route_id,
                "network_activity": False,
                "dispatch_performed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _plan_show(plan_digest: str) -> int:
    try:
        layout = StorageLayout.from_environment()
        store = ObservatoryDatabase(
            layout.observatory_db_path,
            layout.observatory_snapshot_root,
        )
        record = store.read_coordination_plan(plan_digest)
        if record is None:
            raise ValueError("plan does not exist")
        canonical = json.loads(record.canonical_json)
    except (OSError, json.JSONDecodeError, ValueError, MacrError) as exc:
        print(
            json.dumps(
                {
                    "status": "plan_show_failed",
                    "failure_type": type(exc).__name__,
                    "network_activity": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 4
    print(
        json.dumps(
            {
                "status": "plan_show_complete",
                "plan_id": record.plan_id,
                "plan_digest": record.plan_digest,
                "canonical_plan": canonical,
                "network_activity": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _plan_diff(left_digest: str, right_digest: str) -> int:
    try:
        layout = StorageLayout.from_environment()
        store = ObservatoryDatabase(
            layout.observatory_db_path,
            layout.observatory_snapshot_root,
        )
        left = store.read_coordination_plan(left_digest)
        right = store.read_coordination_plan(right_digest)
        if left is None or right is None:
            raise ValueError("both plans must exist")
        left_value = json.loads(left.canonical_json)
        right_value = json.loads(right.canonical_json)
        changed_fields = sorted(
            key
            for key in set(left_value) | set(right_value)
            if left_value.get(key) != right_value.get(key)
        )
    except (OSError, json.JSONDecodeError, ValueError, MacrError) as exc:
        print(
            json.dumps(
                {
                    "status": "plan_diff_failed",
                    "failure_type": type(exc).__name__,
                    "network_activity": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 4
    print(
        json.dumps(
            {
                "status": "plan_diff_complete",
                "left_plan_digest": left.plan_digest,
                "right_plan_digest": right.plan_digest,
                "identical": not changed_fields,
                "changed_fields": changed_fields,
                "network_activity": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _probe_plan(plan_path: str) -> int:
    try:
        document = strict_json_bytes(Path(plan_path).read_bytes())
        manifest = build_differential_manifest(document)
    except (OSError, TypeError, ValueError, MacrError) as exc:
        print(
            json.dumps(
                {
                    "status": "differential_manifest_failed",
                    "failure_type": type(exc).__name__,
                    "network_activity": False,
                    "dispatch_performed": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 4
    print(
        json.dumps(
            {
                "status": "differential_manifest_ready",
                "manifest": manifest.to_dict(),
                "network_activity": False,
                "dispatch_performed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _probe_replay(
    manifest_path: str,
    result_path: str,
    probe_pack_path: str,
) -> int:
    try:
        manifest_document = strict_json_bytes(Path(manifest_path).read_bytes())
        result_document = strict_json_bytes(Path(result_path).read_bytes())
        probe_pack_document = strict_json_bytes(
            Path(probe_pack_path).read_bytes()
        )
        if not isinstance(result_document, list):
            raise ValueError("differential replay results must be an array")
        manifest = DifferentialRunManifest.from_dict(manifest_document)
        from .differential import DifferentialProbePack

        probe_pack = DifferentialProbePack.from_dict(probe_pack_document)
        comparison = compare_differential_results(
            manifest,
            tuple(
                DifferentialCandidateResult.from_dict(item)
                for item in result_document
            ),
            probe_pack,
        )
    except (OSError, TypeError, ValueError, MacrError) as exc:
        print(
            json.dumps(
                {
                    "status": "differential_replay_failed",
                    "failure_type": type(exc).__name__,
                    "network_activity": False,
                    "dispatch_performed": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 4
    print(
        json.dumps(
            {
                "status": "differential_replay_complete",
                "comparison": comparison.to_dict(),
                "network_activity": False,
                "dispatch_performed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _cli_policy_snapshot_sha256(
    provider_id: str,
    provider_scope: ConnectionScope,
    task: TaskContract,
    *,
    allow_network: bool,
    allow_local: bool,
    model_token_policy_digest: str | None,
    provider_tier_binding_digest: str | None,
) -> str:
    document = {
        "schema": "macr_cli_one_shot_v2",
        "provider_id": provider_id,
        "connection_scope": provider_scope.value,
        "interaction_plane": InteractionPlane.DELEGATION.value,
        "task_type": task.task_type,
        "privacy": task.constraints.privacy.value,
        "max_cost_usd": task.constraints.max_cost_usd,
        "max_latency_s": task.constraints.max_latency_s,
        "max_output_tokens": task.constraints.max_output_tokens,
        "max_context_tokens": task.constraints.max_context_tokens,
        "model_token_policy_digest": model_token_policy_digest,
        "provider_tier_binding_digest": provider_tier_binding_digest,
        "allow_network": allow_network,
        "allow_local": allow_local,
    }
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _invoke(
    provider_id: str,
    task_path: str,
    config_path: str | None,
    allow_network: bool,
    allow_local: bool,
) -> int:
    layout = StorageLayout.from_environment()
    path = Path(config_path) if config_path else _default_config(layout)
    configs = load_provider_configs(path)
    registry = ProviderRegistry.from_configs(configs)
    provider = registry.get(provider_id)
    if (
        provider.connection_scope is ConnectionScope.EXTERNAL_HTTPS
        and not allow_network
    ):
        return _print_opt_in_error(
            "network_opt_in_required",
            "--allow-network",
        )
    if (
        provider.connection_scope is ConnectionScope.LOOPBACK_HTTP
        and not allow_local
    ):
        return _print_opt_in_error(
            "local_opt_in_required",
            "--allow-local",
        )
    layout.ensure_state_tree()
    services = RuntimeServices.from_layout(layout)
    registry = ProviderRegistry.from_configs(
        configs,
        token_policy_store=services.token_policies,
        capability_policy_store=services.capability_policies,
    )
    provider = registry.get(provider_id)
    if not _legacy_migration_complete(layout, services):
        print(
            json.dumps(
                {
                    "status": "legacy_migration_required",
                    "detail": (
                        "Run macr migrate-ledger and resolve any incomplete "
                        "legacy evidence before invoking a provider."
                    ),
                    "network_activity": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 5
    task_document = json.loads(Path(task_path).read_text(encoding="utf-8"))
    task = TaskContract.from_dict(task_document)
    validate_task_consistency(task)
    model_token_policy = (
        registry.token_policy(provider_id, store=services.token_policies)
        if registry.requires_model_token_policy(provider_id)
        else None
    )
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    member_digest = task.delegation_approval_sha256
    capability_binding = getattr(provider, "capability_binding", None)
    provider_tier_binding_digest = (
        capability_binding.binding_digest
        if capability_binding is not None
        else None
    )
    reference = services.authorities.issue(
        source_kind="cli_opt_in",
        source_id=f"{provider_id}:{task.task_id}:{run_id}",
        scope=AuthorityScope(
            providers=(provider_id,),
            planes=(InteractionPlane.DELEGATION.value,),
            task_types=(task.task_type,),
            member_digests=(member_digest,) if member_digest else (),
            provider_tier_binding_digests=(
                (provider_tier_binding_digest,)
                if provider_tier_binding_digest is not None
                else ()
            ),
        ),
        expires_at=(now + timedelta(minutes=10)).isoformat(),
    )
    context = DispatchContext(
        run_id=run_id,
        plane=InteractionPlane.DELEGATION,
        origin=DispatchOrigin("cli", "process_id", str(os.getpid())),
        authorization=reference,
        policy_snapshot_sha256=_cli_policy_snapshot_sha256(
            provider_id,
            provider.connection_scope,
            task,
            allow_network=allow_network,
            allow_local=allow_local,
            model_token_policy_digest=(
                model_token_policy.policy_digest
                if model_token_policy is not None
                else None
            ),
            provider_tier_binding_digest=provider_tier_binding_digest,
        ),
        model_token_policy_digest=(
            model_token_policy.policy_digest
            if model_token_policy is not None
            else None
        ),
        member_digest=member_digest,
        provider_tier_binding_digest=provider_tier_binding_digest,
    )
    result = MacrRuntime(registry, services).invoke(
        provider_id,
        task,
        context,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status is ResultStatus.CANDIDATE_SUCCESS else 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="macr",
        description="MACR v0.7.0a0 Phase-C semantic kernel and Direct Chat utility",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="run offline storage and provider configuration checks")
    doctor.add_argument("--config", help="provider configuration JSON path")
    doctor.add_argument("--strict", action="store_true", help="fail if any provider is not ready")

    sub.add_parser("init-state", help="create the configured D runtime-state directories")

    capability_status = sub.add_parser(
        "capability-status",
        help="read current provider capability and legacy state without writes",
    )
    capability_status.add_argument("--provider")
    capability_status.add_argument(
        "--config",
        help="provider configuration JSON path",
    )

    accounting_status = sub.add_parser(
        "accounting-status",
        help="read bounded aggregate accounting state without writes",
    )
    accounting_status.add_argument(
        "--provider",
        help="restrict invocation accounting to one exact provider ID",
    )
    accounting_status.add_argument(
        "--since",
        help="restrict invocation accounting to an aware ISO timestamp",
    )

    migrate = sub.add_parser(
        "migrate-ledger",
        help="copy-import the preserved legacy JSONL ledger into SQLite",
    )
    migrate.add_argument(
        "--dry-run",
        action="store_true",
        help="inspect counts and hashes without writing migration state",
    )
    migrate.add_argument(
        "--expected-count",
        type=int,
        help="require an exact number of nonblank legacy records",
    )

    validate = sub.add_parser("validate-task", help="validate and normalize a TaskContract JSON file")
    validate.add_argument("path")

    queue_status = sub.add_parser(
        "queue-status",
        help="list bounded content-free global queue state",
    )
    queue_status.add_argument(
        "--state",
        choices=tuple(item.value for item in QueueMemberState),
        default=QueueMemberState.RECONCILIATION_REQUIRED.value,
    )
    queue_status.add_argument("--limit", type=int, default=100)
    queue_status.add_argument("--after-member-id")

    t1_stage = sub.add_parser(
        "t1-stage",
        help="stage one exact dynamic T1 manifest without provider calls",
    )
    t1_stage.add_argument("manifest")
    t1_stage.add_argument("--config", help="provider configuration JSON path")
    t1_stage.add_argument(
        "--dispatcher-id",
        action="append",
        required=True,
        dest="dispatcher_ids",
    )
    t1_stage.add_argument(
        "--expires-in-minutes",
        type=int,
        default=30,
    )

    t1_worker = sub.add_parser(
        "t1-worker",
        help="claim and execute at most one exact staged T1 member",
    )
    t1_worker.add_argument("manifest")
    t1_worker.add_argument("--config", help="provider configuration JSON path")
    t1_worker.add_argument("--dispatcher-id", required=True)
    t1_worker.add_argument("--allow-network", action="store_true")
    t1_worker.add_argument("--allow-local", action="store_true")

    evidence_inspect = sub.add_parser(
        "evidence-inspect",
        help="inspect a reviewed external evidence manifest without writing state",
    )
    evidence_inspect.add_argument("manifest")

    evidence_import = sub.add_parser(
        "evidence-import",
        help="append a reviewed exact-digest evidence manifest without promotion",
    )
    evidence_import.add_argument("manifest")
    evidence_import.add_argument(
        "--expected-digest",
        required=True,
        help="required SHA-256 of the exact manifest bytes",
    )

    model_observe = sub.add_parser(
        "model-observe",
        help="ingest one operator-supplied exact-hash OpenRouter snapshot offline",
    )
    model_observe.add_argument("snapshot")
    model_observe.add_argument("--expected-digest", required=True)
    model_observe.add_argument("--observed-at", required=True)

    model_passport = sub.add_parser(
        "model-passport",
        help="rebuild one content-free Model Passport projection",
    )
    model_passport.add_argument("subject_id")
    model_passport.add_argument("--as-of", required=True)

    plan_shadow = sub.add_parser(
        "plan-shadow",
        help="validate and persist one canonical shadow-only plan",
    )
    plan_shadow.add_argument("plan")
    plan_shadow.add_argument("--baseline-route-id", required=True)
    plan_shadow.add_argument("--persisted-at", required=True)

    plan_show = sub.add_parser("plan-show", help="show one persisted canonical plan")
    plan_show.add_argument("plan_digest")

    plan_diff = sub.add_parser("plan-diff", help="diff two persisted plan revisions")
    plan_diff.add_argument("left_plan_digest")
    plan_diff.add_argument("right_plan_digest")

    probe_plan = sub.add_parser(
        "probe-plan",
        help="compile one exact offline differential-run manifest",
    )
    probe_plan.add_argument("input")

    probe_replay = sub.add_parser(
        "probe-replay",
        help="replay one complete blinded differential result set offline",
    )
    probe_replay.add_argument("manifest")
    probe_replay.add_argument("results")
    probe_replay.add_argument("probe_pack")

    glm_preflight = sub.add_parser(
        "glm-preflight",
        help="validate GLM delegation policy and exact-envelope approval without loading a key",
    )
    glm_preflight.add_argument("task_path")
    glm_preflight.add_argument("--config", help="provider configuration JSON path")
    glm_preflight.add_argument(
        "--show-required-digest",
        action="store_true",
        help="print the required exact-envelope approval digest instead of requiring it",
    )

    glm_approve = sub.add_parser(
        "glm-approve",
        help="create a host-authorized, expiring approval record for an exact GLM task digest",
    )
    glm_approve.add_argument("task_path")
    glm_approve.add_argument("--config", help="provider configuration JSON path")
    glm_approve.add_argument(
        "--expires-in-days",
        type=int,
        default=30,
        help="approval lifetime from 1 to 365 days",
    )
    glm_approve.add_argument(
        "--replace-existing",
        action="store_true",
        help="archive and replace an existing approval record for this digest",
    )

    invoke = sub.add_parser(
        "invoke",
        help="invoke one provider through the authorized SQLite shared-core pipeline",
    )
    invoke.add_argument("provider_id")
    invoke.add_argument("task_path")
    invoke.add_argument("--config", help="provider configuration JSON path")
    invoke.add_argument(
        "--allow-network",
        action="store_true",
        help="explicitly authorize this command to perform a provider network request",
    )
    invoke.add_argument(
        "--allow-local",
        action="store_true",
        help="explicitly authorize this command to load and call a loopback provider",
    )

    direct = sub.add_parser(
        "direct-chat",
        help="start the on-demand loopback Direct Chat UI",
    )
    direct.add_argument(
        "--smoke",
        action="store_true",
        help="start, bootstrap, and stop locally without provider generation",
    )
    direct.add_argument(
        "--no-browser",
        action="store_true",
        help="serve without opening the default browser",
    )
    direct.add_argument(
        "--idle-minutes",
        type=int,
        default=30,
        help="idle shutdown window from 1 to 1440 minutes",
    )
    direct.add_argument("--config", help="provider configuration JSON path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return _doctor(args.config, args.strict)
    if args.command == "init-state":
        return _init_state()
    if args.command == "capability-status":
        return _capability_status(args.provider, args.config)
    if args.command == "accounting-status":
        return _accounting_status(args.provider, args.since)
    if args.command == "migrate-ledger":
        return _migrate_ledger(
            dry_run=args.dry_run,
            expected_count=args.expected_count,
        )
    if args.command == "validate-task":
        return _validate_task(args.path)
    if args.command == "queue-status":
        return _queue_status(
            args.state,
            limit=args.limit,
            after_member_id=args.after_member_id,
        )
    if args.command == "t1-stage":
        return _t1_stage(
            args.manifest,
            args.config,
            dispatcher_ids=args.dispatcher_ids,
            expires_in_minutes=args.expires_in_minutes,
        )
    if args.command == "t1-worker":
        return _t1_worker(
            args.manifest,
            args.config,
            dispatcher_id=args.dispatcher_id,
            allow_network=args.allow_network,
            allow_local=args.allow_local,
        )
    if args.command == "evidence-inspect":
        return _evidence_inspect(args.manifest)
    if args.command == "evidence-import":
        return _evidence_import(args.manifest, args.expected_digest)
    if args.command == "model-observe":
        return _model_observe(
            args.snapshot,
            args.expected_digest,
            args.observed_at,
        )
    if args.command == "model-passport":
        return _model_passport(args.subject_id, args.as_of)
    if args.command == "plan-shadow":
        return _plan_shadow(
            args.plan,
            args.baseline_route_id,
            args.persisted_at,
        )
    if args.command == "plan-show":
        return _plan_show(args.plan_digest)
    if args.command == "plan-diff":
        return _plan_diff(
            args.left_plan_digest,
            args.right_plan_digest,
        )
    if args.command == "probe-plan":
        return _probe_plan(args.input)
    if args.command == "probe-replay":
        return _probe_replay(
            args.manifest,
            args.results,
            args.probe_pack,
        )
    if args.command == "glm-preflight":
        return _glm_preflight(
            args.task_path,
            args.config,
            show_required_digest=args.show_required_digest,
        )
    if args.command == "glm-approve":
        return _glm_approve(
            args.task_path,
            args.config,
            expires_in_days=args.expires_in_days,
            replace_existing=args.replace_existing,
        )
    if args.command == "invoke":
        return _invoke(
            args.provider_id,
            args.task_path,
            args.config,
            args.allow_network,
            args.allow_local,
        )
    if args.command == "direct-chat":
        from .direct_launcher import run_direct_chat, smoke_direct_chat

        layout = StorageLayout.from_environment()
        if args.smoke:
            print(
                json.dumps(
                    smoke_direct_chat(
                        layout,
                        config_path=args.config,
                        environ=os.environ,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if not 1 <= args.idle_minutes <= 1440:
            raise ValueError("idle-minutes must be between 1 and 1440")
        return run_direct_chat(
            layout,
            config_path=args.config,
            idle_timeout_seconds=args.idle_minutes * 60,
            open_browser=not args.no_browser,
            environ=os.environ,
        )
    raise AssertionError(f"unhandled command: {args.command}")
