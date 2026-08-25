from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from .config import ConnectionScope, load_provider_configs
from .contracts import ResultStatus, TaskContract
from .ledger import AppendOnlyLedger
from .registry import ProviderRegistry
from .runtime import MacrRuntime
from .storage import StorageLayout


def _default_config(layout: StorageLayout) -> Path:
    return Path(layout.source_root) / "config" / "providers.json"


def _doctor(config_path: str | None, strict: bool) -> int:
    layout = StorageLayout.from_environment()
    path = Path(config_path) if config_path else _default_config(layout)
    configs = load_provider_configs(path)
    registry = ProviderRegistry.from_configs(configs)
    report = {
        "runtime": "macr-runtime",
        "version": "0.1.0",
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
    print(json.dumps(task.to_dict(), ensure_ascii=False, indent=2))
    return 0


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
    task_document = json.loads(Path(task_path).read_text(encoding="utf-8"))
    task = TaskContract.from_dict(task_document)
    result = MacrRuntime(registry, AppendOnlyLedger(layout.ledger_path)).invoke(
        provider_id,
        task,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status is ResultStatus.CANDIDATE_SUCCESS else 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="macr", description="MACR v0.1 control utility")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="run offline storage and provider configuration checks")
    doctor.add_argument("--config", help="provider configuration JSON path")
    doctor.add_argument("--strict", action="store_true", help="fail if any provider is not ready")

    sub.add_parser("init-state", help="create the configured D/R runtime-state directories")

    validate = sub.add_parser("validate-task", help="validate and normalize a TaskContract JSON file")
    validate.add_argument("path")

    invoke = sub.add_parser(
        "invoke",
        help="invoke one configured provider and append candidate metadata to the R-drive ledger",
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
    if args.command == "validate-task":
        return _validate_task(args.path)
    if args.command == "invoke":
        return _invoke(
            args.provider_id,
            args.task_path,
            args.config,
            args.allow_network,
            args.allow_local,
        )
    raise AssertionError(f"unhandled command: {args.command}")
