from __future__ import annotations

import json
import multiprocessing
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from macr_runtime.authority import AuthorityScope, DispatchAuthorityStore
from macr_runtime.batch_authority import (
    BatchAuthorityStore,
    BatchMemberScope,
    BatchScope,
)
from macr_runtime.dispatch import AdmissionGate, DispatcherLeaseStore
from macr_runtime.errors import DispatchLeaseError
from macr_runtime.event_store import SqliteEventStore
from macr_runtime.execution import DispatchContext, DispatchOrigin, InteractionPlane
from macr_runtime.ledger import AppendOnlyLedger
from macr_runtime.legacy_ledger import LegacyLedgerImporter
from macr_runtime.glm_approval import GlmApprovalStore
from macr_runtime.providers.glm import GlmFlashWorkerProvider
from macr_runtime.registry import ProviderRegistry
from macr_runtime.runtime import RuntimeServices
from macr_runtime.scheduler import PlanQueue, QueueMember, T1QueuePlan
from macr_runtime.t1_dispatcher import T1Dispatcher
from macr_runtime.token_policy import t1_glm_live_policy

from tests.support import build_test_services, d_drive_tempdir
from tests.test_glm_provider import FakeTransport, StaticKeySource, glm_config, success_document
from tests.test_t1_dispatcher import approved_manifest


ROOT = Path(__file__).resolve().parents[1]
WRITER = ROOT / "tests" / "helpers" / "sqlite_event_writer.py"
BOOTSTRAP_WORKER = ROOT / "tests" / "helpers" / "sqlite_bootstrap_worker.py"
PLAN_WORKER = ROOT / "tests" / "helpers" / "plan_worker.py"
T1_RUNTIME_WORKER = ROOT / "tests" / "helpers" / "t1_runtime_worker.py"
CENSUS = ROOT / "scripts" / "Test-MacrInvokerProcesses.ps1"


def _admission_worker(
    database: str,
    reference,
    run_id: str,
    start_event,
    release_event,
    results,
) -> None:
    authorities = DispatchAuthorityStore(database)
    leases = DispatcherLeaseStore(database)
    gate = AdmissionGate(authorities, leases)
    context = DispatchContext(
        run_id=run_id,
        plane=InteractionPlane.DELEGATION,
        origin=DispatchOrigin("test-process", "process_id", str(os.getpid())),
        authorization=reference,
        policy_snapshot_sha256="a" * 64,
    )
    if not start_event.wait(20):
        results.put(("error", "StartTimeout"))
        return
    try:
        permit = gate.admit(
            context,
            resource_key="provider:glm_flash_worker:shared-test-slot",
            provider_id="glm_flash_worker",
            task_type="delegated_routine",
            ttl_seconds=60,
        )
    except DispatchLeaseError as exc:
        results.put(("refused", type(exc).__name__))
        return
    except Exception as exc:
        results.put(("error", type(exc).__name__))
        return
    try:
        SqliteEventStore(database).append_standalone(
            "mock.transport_called",
            str(uuid.uuid4()),
            {"process_id": os.getpid()},
        )
        results.put(("admitted", permit.fencing_token))
        if not release_event.wait(20):
            results.put(("error", "ReleaseTimeout"))
    finally:
        leases.release(
            permit.resource_key,
            permit.run_id,
            permit.fencing_token,
        )


class _BarrierBackedFile:
    def __init__(self, writes, barrier) -> None:
        self.writes = writes
        self.barrier = barrier

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        del exc_type, exc_value, traceback
        return False

    def write(self, value: str) -> int:
        self.writes.append(value)
        self.barrier.wait(20)
        return len(value)

    def flush(self) -> None:
        return None

    def fileno(self) -> int:
        return 0


def _legacy_mutation_worker(
    target: str,
    writes,
    barrier,
    worker: int,
) -> None:
    target_path = Path(target)
    original_open = Path.open

    def patched_open(path, mode="r", *args, **kwargs):
        if path == target_path and mode == "a":
            return _BarrierBackedFile(writes, barrier)
        return original_open(path, mode, *args, **kwargs)

    with patch.object(Path, "open", patched_open), patch(
        "macr_runtime.ledger.os.fsync",
        return_value=None,
    ):
        AppendOnlyLedger(target_path).append(
            "legacy.mutation",
            {"worker": worker},
        )


def _powershell() -> str:
    executable = shutil.which("powershell.exe") or shutil.which("powershell")
    if executable is None:
        raise unittest.SkipTest("Windows PowerShell is unavailable")
    return executable


def _run_census(expected_count: int | None = None) -> subprocess.CompletedProcess:
    command = [_powershell(), "-NoProfile", "-NonInteractive", "-File", str(CENSUS)]
    if expected_count is not None:
        command.extend(("-ExpectedCount", str(expected_count)))
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


class MultiprocessRuntimeTests(unittest.TestCase):
    def test_three_t1_workers_produce_exact_complete_path_evidence(self) -> None:
        with d_drive_tempdir() as temp:
            provider = GlmFlashWorkerProvider(
                glm_config(),
                transport=FakeTransport(success_document()),
                environ={"MACR_STATE_ROOT": str(temp)},
                key_source=StaticKeySource(),
                token_policy=t1_glm_live_policy(),
            )
            subject = approved_manifest(provider)
            approval_store = GlmApprovalStore(temp)
            for item in subject.members:
                approval_store.create(
                    item.task.delegation_approval_sha256,
                    signing_key="test-id.test-secret",
                    expires_in_days=1,
                )
            services = build_test_services(temp)
            dispatcher = T1Dispatcher(
                ProviderRegistry((provider,)),
                services,
            )
            dispatcher.stage(
                subject,
                subject.authorized_dispatchers,
                subject.expires_at,
            )
            manifest_path = temp / "private-t1-manifest.json"
            manifest_path.write_text(
                json.dumps(subject.to_dict()),
                encoding="utf-8",
            )
            start_signal = temp / "t1-start.signal"
            processes = [
                subprocess.Popen(
                    [
                        sys.executable,
                        str(T1_RUNTIME_WORKER),
                        str(temp),
                        str(manifest_path),
                        str(start_signal),
                        str(temp / f"t1-ready-{index}"),
                        dispatcher_id,
                    ],
                    env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                for index, dispatcher_id in enumerate(subject.authorized_dispatchers)
            ]
            completed: list[tuple[str, str]] = []
            try:
                deadline = time.monotonic() + 30
                while (
                    len(tuple(temp.glob("t1-ready-*"))) < 3
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.005)
                self.assertEqual(len(tuple(temp.glob("t1-ready-*"))), 3)
                start_signal.touch()
                completed = [
                    process.communicate(timeout=60) for process in processes
                ]
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=15)

            results = []
            for process, (stdout, stderr) in zip(processes, completed):
                self.assertEqual(
                    process.returncode,
                    0,
                    msg=f"stdout={stdout!r} stderr={stderr!r}",
                )
                results.append(json.loads(stdout))
            events = services.events.read_events()
            queue_records = dispatcher.queue.list_members(subject.plan_digest)
            runtime_connection = services.events.database.connect()
            try:
                capture_count = runtime_connection.execute(
                    "SELECT COUNT(*) FROM candidate_captures"
                ).fetchone()[0]
            finally:
                runtime_connection.close()
            accounting_connection = sqlite3.connect(services.accounting.path)
            try:
                invocation_count = accounting_connection.execute(
                    "SELECT COUNT(*) FROM invocations WHERE terminal_at IS NOT NULL"
                ).fetchone()[0]
                plan_cost_count = accounting_connection.execute(
                    "SELECT COUNT(*) FROM plan_costs"
                ).fetchone()[0]
            finally:
                accounting_connection.close()
            public_databases = (
                services.events.path.read_bytes()
                + services.accounting.path.read_bytes()
            )
            unsettled_count = services.accounting.unsettled_count()
            reconciliation_count = dispatcher.queue.state_counts()[
                "reconciliation_required"
            ]

        self.assertEqual(len({item["member_id"] for item in results}), 3)
        self.assertEqual(
            [item.state.value for item in queue_records],
            ["completed", "completed", "completed"],
        )
        self.assertEqual(
            len([item for item in events if item["event_type"] == "mock.t1_transport_called"]),
            3,
        )
        self.assertEqual(
            len([item for item in events if item["event_type"] == "provider.dispatch_requested"]),
            3,
        )
        self.assertEqual(
            len([item for item in events if item["event_type"] == "provider.candidate_completed"]),
            3,
        )
        self.assertEqual((capture_count, invocation_count, plan_cost_count), (3, 3, 3))
        self.assertEqual(unsettled_count, 0)
        self.assertEqual(reconciliation_count, 0)
        for item in subject.members:
            self.assertNotIn(item.task.goal.encode(), public_databases)
        self.assertNotIn(b"multiprocess candidate", public_databases)
        self.assertNotIn(b"test-secret", public_databases)
        self.assertNotIn(b"private-t1-manifest.json", public_databases)
    def test_fresh_sqlite_bootstrap_is_safe_for_synchronized_processes(self) -> None:
        with d_drive_tempdir() as temp:
            database = temp / "dispatch.sqlite3"
            start_signal = temp / "start.signal"
            process_count = 32
            processes = [
                subprocess.Popen(
                    [
                        sys.executable,
                        str(BOOTSTRAP_WORKER),
                        str(database),
                        str(start_signal),
                        str(temp / f"ready-{index}"),
                    ],
                    env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                for index in range(process_count)
            ]
            completed: list[tuple[str, str]] = []
            try:
                deadline = time.monotonic() + 30
                while (
                    len(tuple(temp.glob("ready-*"))) < process_count
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.005)
                self.assertEqual(
                    len(tuple(temp.glob("ready-*"))),
                    process_count,
                    "all bootstrap workers must reach the synchronized start gate",
                )
                start_signal.touch()
                completed = [
                    process.communicate(timeout=45) for process in processes
                ]
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=15)

            failures = [
                (index, process.returncode, stdout, stderr)
                for index, (process, (stdout, stderr)) in enumerate(
                    zip(processes, completed)
                )
                if process.returncode != 0
            ]
            self.assertEqual(failures, [])

            connection = SqliteEventStore(database).database.connect()
            try:
                version = connection.execute(
                    "SELECT version FROM schema_meta WHERE component = 'runtime'"
                ).fetchone()[0]
                journal_mode = connection.execute(
                    "PRAGMA journal_mode"
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(version, 6)
        self.assertEqual(journal_mode.lower(), "wal")

    def test_plan_workers_claim_exact_members_once(self) -> None:
        for worker_count in (1, 2, 3, 4, 8):
            with self.subTest(worker_count=worker_count), d_drive_tempdir() as temp:
                database = temp / "dispatch.sqlite3"
                members = tuple(
                    QueueMember(
                        member_digest=format(index + 1, "x") * 64,
                        provider_id="glm_flash_worker",
                        route_id="a" * 64,
                        role_digest="b" * 64,
                        privacy="public_text",
                        context_class="non_sensitive_routine",
                        cost_ceiling_usd=0.01,
                    )
                    for index in range(worker_count)
                )
                scope = BatchScope(
                    plan_digest="f" * 64,
                    ordered_members=tuple(
                        BatchMemberScope(
                            member_digest=item.member_digest,
                            provider_id=item.provider_id,
                            route_id=item.route_id,
                            role_digest=item.role_digest,
                            privacy=item.privacy,
                            context_class=item.context_class,
                            cost_ceiling_usd=item.cost_ceiling_usd,
                        )
                        for item in members
                    ),
                    aggregate_cost_ceiling_usd=worker_count * 0.01,
                    expires_at="2099-01-01T00:00:00+00:00",
                    authorized_dispatchers=tuple(
                        f"plan-worker-{index}" for index in range(worker_count)
                    ),
                )
                authority = BatchAuthorityStore(database).issue(scope)
                queue = PlanQueue(database)
                expected_ids = queue.enqueue(
                    T1QueuePlan(
                        plan_digest=scope.plan_digest,
                        members=members,
                        aggregate_cost_ceiling_usd=scope.aggregate_cost_ceiling_usd,
                        authority=authority,
                    )
                )
                start_signal = temp / "plan-start.signal"
                processes = [
                    subprocess.Popen(
                        [
                            sys.executable,
                            str(PLAN_WORKER),
                            str(database),
                            str(start_signal),
                            str(temp / f"plan-ready-{index}"),
                            f"plan-worker-{index}",
                        ],
                        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    for index in range(worker_count)
                ]
                completed: list[tuple[str, str]] = []
                try:
                    deadline = time.monotonic() + 30
                    while (
                        len(tuple(temp.glob("plan-ready-*"))) < worker_count
                        and time.monotonic() < deadline
                    ):
                        time.sleep(0.005)
                    self.assertEqual(
                        len(tuple(temp.glob("plan-ready-*"))),
                        worker_count,
                    )
                    start_signal.touch()
                    completed = [
                        process.communicate(timeout=45) for process in processes
                    ]
                finally:
                    for process in processes:
                        if process.poll() is None:
                            process.terminate()
                            process.wait(timeout=15)

                observations = []
                for process, (stdout, stderr) in zip(processes, completed):
                    self.assertEqual(
                        process.returncode,
                        0,
                        msg=f"stdout={stdout!r} stderr={stderr!r}",
                    )
                    observations.append(json.loads(stdout))
                claimed = tuple(
                    sorted(item["member_id"] for item in observations)
                )
                terminal = queue.list_members(scope.plan_digest)

                self.assertEqual(claimed, tuple(sorted(expected_ids)))
                self.assertEqual(len(set(claimed)), worker_count)
                self.assertEqual(
                    tuple(item.state.value for item in terminal),
                    ("completed",) * worker_count,
                )

    def test_sqlite_event_store_exact_counts_across_processes(self) -> None:
        for workers in (1, 2, 3, 4, 8):
            with self.subTest(workers=workers), d_drive_tempdir() as temp:
                database = temp / "dispatch.sqlite3"
                count = 60
                processes = [
                    subprocess.Popen(
                        [
                            sys.executable,
                            str(WRITER),
                            str(database),
                            f"w{index}",
                            str(count),
                        ],
                        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    for index in range(workers)
                ]
                completed = [process.communicate(timeout=60) for process in processes]
                for process, (stdout, stderr) in zip(processes, completed):
                    self.assertEqual(
                        process.returncode,
                        0,
                        msg=f"stdout={stdout!r} stderr={stderr!r}",
                    )
                events = SqliteEventStore(database).read_events(
                    event_type="concurrency.probe"
                )
                expected = workers * count
                self.assertEqual(len(events), expected)
                self.assertEqual(
                    len({event["event_id"] for event in events}),
                    expected,
                )

    def test_two_process_admission_allows_one_mock_transport_call(self) -> None:
        context = multiprocessing.get_context("spawn")
        with d_drive_tempdir() as temp:
            database = temp / "dispatch.sqlite3"
            authorities = DispatchAuthorityStore(database)
            reference = authorities.issue(
                source_kind="test",
                source_id="two-process-admission",
                scope=AuthorityScope(
                    providers=("glm_flash_worker",),
                    planes=(InteractionPlane.DELEGATION.value,),
                    task_types=("delegated_routine",),
                ),
                expires_at="2099-01-01T00:00:00+00:00",
            )
            start_event = context.Event()
            release_event = context.Event()
            results = context.Queue()
            processes = [
                context.Process(
                    target=_admission_worker,
                    args=(
                        str(database),
                        reference,
                        str(uuid.uuid4()),
                        start_event,
                        release_event,
                        results,
                    ),
                )
                for _ in range(2)
            ]
            for process in processes:
                process.start()
            start_event.set()
            observations = [results.get(timeout=30) for _ in range(2)]
            release_event.set()
            for process in processes:
                process.join(timeout=30)
                self.assertEqual(process.exitcode, 0)
            results.close()
            transport_events = SqliteEventStore(database).read_events(
                event_type="mock.transport_called"
            )

        self.assertEqual([item[0] for item in observations].count("admitted"), 1)
        self.assertEqual([item[0] for item in observations].count("refused"), 1)
        refusal = next(item for item in observations if item[0] == "refused")
        self.assertEqual(refusal[1], "DispatchLeaseError")
        self.assertEqual(len(transport_events), 1)

    def test_census_excludes_itself_even_when_own_command_has_invoker_text(self) -> None:
        escaped = str(CENSUS).replace("'", "''")
        command = (
            f"& '{escaped}' -ExpectedCount 0 "
            "# invoke-glm.ps1 -TaskPath"
        )
        completed = subprocess.run(
            [_powershell(), "-NoProfile", "-NonInteractive", "-Command", command],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["count"], 0)
        self.assertEqual(report["excluded_pid"], report["census_pid"])

    def test_census_detects_and_then_excludes_exact_harmless_process(self) -> None:
        harmless = subprocess.Popen(
            [
                _powershell(),
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$null = 'invoke-glm.ps1 -TaskPath'; Wait-Event -Timeout 60 | Out-Null",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            deadline = time.monotonic() + 15
            report = None
            while time.monotonic() < deadline:
                completed = _run_census()
                self.assertEqual(completed.returncode, 0, msg=completed.stderr)
                report = json.loads(completed.stdout)
                if report["count"] == 1 and harmless.pid in report["matching_pids"]:
                    break
                time.sleep(0.1)
            else:
                self.fail(f"harmless invoker was not observed: {report}")

            exact = _run_census(expected_count=1)
            self.assertEqual(exact.returncode, 0, msg=exact.stderr)
        finally:
            harmless.terminate()
            harmless.wait(timeout=15)

        deadline = time.monotonic() + 15
        report = None
        while time.monotonic() < deadline:
            completed = _run_census()
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            report = json.loads(completed.stdout)
            if report["count"] == 0:
                break
            time.sleep(0.1)
        else:
            self.fail(f"terminated invoker remained visible: {report}")
        self.assertEqual(_run_census(expected_count=0).returncode, 0)

    def test_legacy_two_process_forced_interleaving_is_incomplete(self) -> None:
        context = multiprocessing.get_context("spawn")
        with d_drive_tempdir() as temp, context.Manager() as manager:
            target = temp / "forced-interleave.jsonl"
            writes = manager.list()
            barrier = context.Barrier(2)
            processes = [
                context.Process(
                    target=_legacy_mutation_worker,
                    args=(str(target), writes, barrier, worker),
                )
                for worker in range(2)
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=30)
                self.assertEqual(process.exitcode, 0)
            target.write_text("".join(writes), encoding="utf-8")

            report = LegacyLedgerImporter(
                temp / "dispatch.sqlite3",
                temp / "quarantine",
            ).inspect(target, expected_count=2)

        self.assertFalse(report.complete)
        self.assertGreater(report.corrupt_count, 0)


if __name__ == "__main__":
    unittest.main()
