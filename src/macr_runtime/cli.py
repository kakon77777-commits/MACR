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
from .config import ConnectionScope, load_provider_configs
from .contracts import ResultStatus, TaskContract
from .errors import MacrError
from .execution import DispatchContext, DispatchOrigin, InteractionPlane
from .legacy_ledger import LegacyLedgerImporter
from .registry import ProviderRegistry
from .providers.glm import GlmFlashWorkerProvider
from .runtime import MacrRuntime, RuntimeServices
from .storage import StorageLayout
from .task_preflight import validate_task_consistency


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
    registry = ProviderRegistry.from_configs(configs, key_sources=key_sources)
    report = {
        "runtime": "macr-runtime",
        "version": "0.5.0a2",
        "network_activity": False,
        "storage": layout.describe(),
        "providers": list(registry.health()),
        "provider_environment": [item.public_summary(os.environ) for item in configs],
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


def _validate_task(path: str) -> int:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    task = TaskContract.from_dict(document)
    validate_task_consistency(task)
    print(json.dumps(task.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _glm_preflight(
    task_path: str,
    config_path: str | None,
    *,
    show_required_digest: bool,
) -> int:
    layout = StorageLayout.from_environment()
    path = Path(config_path) if config_path else _default_config(layout)
    try:
        config = next(
            item
            for item in load_provider_configs(path)
            if item.id == "glm_flash_worker"
        )
        task_document = json.loads(Path(task_path).read_text(encoding="utf-8"))
        task = TaskContract.from_dict(task_document)
        validate_task_consistency(task)
        provider = GlmFlashWorkerProvider(config, environ=os.environ)
        metadata = (
            provider.approval_metadata(task)
            if show_required_digest
            else provider.validate_approval(task)
        )
    except StopIteration:
        failure_type = "ConfigurationError"
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
    print(
        json.dumps(
            {
                "status": "approval_invalid",
                "failure_type": failure_type,
                "detail": "GLM task approval preflight failed; task content omitted.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
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
    try:
        config = next(
            item
            for item in load_provider_configs(path)
            if item.id == "glm_flash_worker"
        )
        task_document = json.loads(Path(task_path).read_text(encoding="utf-8"))
        task = TaskContract.from_dict(task_document)
        validate_task_consistency(task)
        provider = GlmFlashWorkerProvider(
            config,
            environ=os.environ,
            key_source=key_source,
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
            )
        finally:
            signing_key = None
    except StopIteration:
        failure_type = "ConfigurationError"
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
    print(
        json.dumps(
            {
                "status": "host_approval_failed",
                "failure_type": failure_type,
                "detail": "GLM host approval failed; task content omitted.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
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


def _cli_policy_snapshot_sha256(
    provider_id: str,
    provider_scope: ConnectionScope,
    task: TaskContract,
    *,
    allow_network: bool,
    allow_local: bool,
) -> str:
    document = {
        "schema": "macr_cli_one_shot_v1",
        "provider_id": provider_id,
        "connection_scope": provider_scope.value,
        "interaction_plane": InteractionPlane.DELEGATION.value,
        "task_type": task.task_type,
        "privacy": task.constraints.privacy.value,
        "max_cost_usd": task.constraints.max_cost_usd,
        "max_latency_s": task.constraints.max_latency_s,
        "max_output_tokens": task.constraints.max_output_tokens,
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
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    member_digest = task.delegation_approval_sha256
    reference = services.authorities.issue(
        source_kind="cli_opt_in",
        source_id=f"{provider_id}:{task.task_id}:{run_id}",
        scope=AuthorityScope(
            providers=(provider_id,),
            planes=(InteractionPlane.DELEGATION.value,),
            task_types=(task.task_type,),
            member_digests=(member_digest,) if member_digest else (),
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
        ),
        member_digest=member_digest,
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
        description="MACR v0.5.0a2 shared-core control utility",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="run offline storage and provider configuration checks")
    doctor.add_argument("--config", help="provider configuration JSON path")
    doctor.add_argument("--strict", action="store_true", help="fail if any provider is not ready")

    sub.add_parser("init-state", help="create the configured D runtime-state directories")

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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return _doctor(args.config, args.strict)
    if args.command == "init-state":
        return _init_state()
    if args.command == "migrate-ledger":
        return _migrate_ledger(
            dry_run=args.dry_run,
            expected_count=args.expected_count,
        )
    if args.command == "validate-task":
        return _validate_task(args.path)
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
    raise AssertionError(f"unhandled command: {args.command}")
