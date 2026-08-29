from __future__ import annotations

import hashlib
import http.client
import json
import msvcrt
import os
import threading
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .config import load_provider_configs
from .direct_providers import DirectProviderRegistry
from .direct_runtime import DirectRuntime, issue_operator_direct_authority
from .direct_server import DirectChatServer, create_direct_server
from .direct_settings import DirectSettingsStore
from .direct_store import DirectConversationStore
from .model_token_store import ModelTokenPolicyStore
from .errors import LegacyLedgerError, StoragePolicyError
from .runtime import RuntimeServices
from .storage import StorageLayout


@dataclass(frozen=True)
class DirectApplication:
    runtime: DirectRuntime
    services: RuntimeServices
    conversations: DirectConversationStore
    settings: DirectSettingsStore
    registry: DirectProviderRegistry
    server: DirectChatServer


class DirectInstanceLease:
    def __init__(self, path: str | Path) -> None:
        candidate = Path(path)
        if not candidate.is_absolute() or candidate.drive.upper() != "D:":
            raise StoragePolicyError(
                "Direct instance lock path must be absolute on D:"
            )
        self.path = candidate.absolute()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle: Any | None = None

    def acquire(self) -> bool:
        if self._handle is not None:
            return True
        handle = self.path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
                os.fsync(handle.fileno())
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            handle.close()
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            handle.close()

    def __enter__(self) -> "DirectInstanceLease":
        if not self.acquire():
            raise RuntimeError("Direct instance lease is already held")
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback
        self.release()


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
            """SELECT source_bytes, complete
            FROM legacy_sources WHERE source_sha256 = ?""",
            (source_sha256,),
        ).fetchone()
    finally:
        connection.close()
    return bool(
        row is not None
        and row["source_bytes"] == source_bytes
        and row["complete"] == 1
    )


def build_direct_application(
    layout: StorageLayout,
    *,
    config_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> DirectApplication:
    if not isinstance(layout, StorageLayout):
        raise ValueError("layout must be StorageLayout")
    layout.ensure_state_tree()
    services = RuntimeServices.from_layout(layout)
    if not _legacy_migration_complete(layout, services):
        raise LegacyLedgerError(
            "Direct Chat requires complete legacy migration before startup"
        )
    source_config = (
        Path(config_path)
        if config_path is not None
        else Path(layout.source_root) / "config" / "providers.json"
    )
    configs = load_provider_configs(source_config)
    registry = DirectProviderRegistry.from_configs(
        configs,
        environ=os.environ if environ is None else environ,
    )
    settings = DirectSettingsStore(layout.settings_db_path)
    settings.ensure_operator_managed()
    conversations = DirectConversationStore(layout.direct_db_path)
    token_policies = ModelTokenPolicyStore(layout.model_token_policy_db_path)
    authority = issue_operator_direct_authority(services)
    runtime = DirectRuntime(
        registry,
        services,
        conversations,
        settings,
        authority,
        token_policies=token_policies,
    )
    server = create_direct_server(runtime)
    return DirectApplication(
        runtime=runtime,
        services=services,
        conversations=conversations,
        settings=settings,
        registry=registry,
        server=server,
    )


def smoke_direct_chat(
    layout: StorageLayout,
    *,
    config_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    application = build_direct_application(
        layout,
        config_path=config_path,
        environ=environ,
    )
    server = application.server
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = server.address
    asset_status = 0
    bootstrap_status = 0
    try:
        connection = http.client.HTTPConnection(
            address.host,
            address.port,
            timeout=5,
        )
        connection.request("GET", "/")
        response = connection.getresponse()
        response.read()
        asset_status = response.status
        connection.close()

        payload = json.dumps(
            {"token": server.bootstrap_token},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        connection = http.client.HTTPConnection(
            address.host,
            address.port,
            timeout=5,
        )
        connection.request(
            "POST",
            "/api/v0.1/bootstrap",
            body=payload,
            headers={
                "Origin": server.base_url,
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        response.read()
        bootstrap_status = response.status
        connection.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    if asset_status != 200 or bootstrap_status != 200:
        raise RuntimeError("Direct Chat local smoke check failed")
    return {
        "status": "direct_chat_smoke_ok",
        "version": "0.6.0a0",
        "ui_version": "0.1",
        "host": "127.0.0.1",
        "asset_status": asset_status,
        "bootstrap_status": bootstrap_status,
        "network_activity": False,
        "provider_generation": False,
    }


def _instance_document(server: DirectChatServer) -> dict[str, object]:
    address = server.address
    return {
        "schema": "macr_direct_instance_v1",
        "version": "0.6.0a0",
        "ui_version": "0.1",
        "pid": os.getpid(),
        "host": address.host,
        "port": address.port,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


def _write_instance(path: Path, document: Mapping[str, object]) -> None:
    encoded = json.dumps(
        dict(document),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    temporary = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    temporary.write_text(encoded, encoding="utf-8")
    os.replace(temporary, path)


def _read_instance(path: Path) -> dict[str, object] | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(document, dict) or set(document) != {
        "schema",
        "version",
        "ui_version",
        "pid",
        "host",
        "port",
        "started_at",
    }:
        return None
    if (
        document["schema"] != "macr_direct_instance_v1"
        or document["version"] != "0.6.0a0"
        or document["ui_version"] != "0.1"
        or document["host"] != "127.0.0.1"
        or isinstance(document["port"], bool)
        or not isinstance(document["port"], int)
        or not 1 <= document["port"] <= 65535
        or isinstance(document["pid"], bool)
        or not isinstance(document["pid"], int)
        or document["pid"] < 1
        or not isinstance(document["started_at"], str)
    ):
        return None
    return document


def _probe_existing(document: Mapping[str, object]) -> str | None:
    host = str(document["host"])
    port = int(document["port"])
    try:
        connection = http.client.HTTPConnection(host, port, timeout=1)
        connection.request("GET", "/")
        response = connection.getresponse()
        response.read()
        server_header = response.getheader("Server", "")
        status = response.status
        connection.close()
    except OSError:
        return None
    if status != 200 or not server_header.startswith("MACRDirect/0.1"):
        return None
    return f"http://{host}:{port}/"


def run_direct_chat(
    layout: StorageLayout,
    *,
    config_path: str | Path | None = None,
    idle_timeout_seconds: int = 1800,
    open_browser: bool = True,
    environ: Mapping[str, str] | None = None,
) -> int:
    if (
        isinstance(idle_timeout_seconds, bool)
        or not isinstance(idle_timeout_seconds, int)
        or not 60 <= idle_timeout_seconds <= 86400
    ):
        raise ValueError("idle_timeout_seconds must be between 60 and 86400")
    layout.ensure_state_tree()
    lease = DirectInstanceLease(layout.direct_root / "instance.lock")
    if not lease.acquire():
        for _ in range(40):
            document = _read_instance(layout.direct_instance_path)
            url = _probe_existing(document) if document is not None else None
            if url is not None:
                if open_browser:
                    webbrowser.open(url, new=2)
                return 0
            time.sleep(0.05)
        raise RuntimeError("Direct Chat instance is locked but not reachable")

    application: DirectApplication | None = None
    monitor_stop = threading.Event()
    try:
        application = build_direct_application(
            layout,
            config_path=config_path,
            environ=environ,
        )
        server = application.server
        descriptor = _instance_document(server)
        _write_instance(layout.direct_instance_path, descriptor)
        if open_browser:
            webbrowser.open(server.bootstrap_url, new=2)

        def monitor_idle() -> None:
            while not monitor_stop.wait(1.0):
                if (
                    server.active_requests == 0
                    and server.idle_seconds >= idle_timeout_seconds
                    and application is not None
                    and application.services.accounting.unsettled_count() == 0
                ):
                    server.shutdown()
                    return

        monitor = threading.Thread(target=monitor_idle, daemon=True)
        monitor.start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.shutdown()
        finally:
            monitor_stop.set()
            monitor.join(timeout=5)
            server.server_close()
        return 0
    finally:
        monitor_stop.set()
        current = _read_instance(layout.direct_instance_path)
        if current is not None and current.get("pid") == os.getpid():
            layout.direct_instance_path.unlink(missing_ok=True)
        lease.release()
