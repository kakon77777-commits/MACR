from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import io
import json
import os
import shutil
import sqlite3
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from macr_runtime.cli import (
    _doctor,
    _evidence_import,
    _evidence_inspect,
    _glm_approve,
    _glm_preflight,
    _invoke,
    _migrate_ledger,
    _model_observe,
    _model_passport,
    _plan_diff,
    _plan_shadow,
    _plan_show,
    _queue_status,
    _t1_stage,
    _t1_worker,
)
from macr_runtime.contracts import (
    DelegationClass,
    ImportMode,
    PrivacyLevel,
    RequiredImport,
    TaskConstraints,
    TaskContract,
    TaskPolicyClauses,
)
from macr_runtime.config import load_provider_configs
from macr_runtime.providers.glm import GlmFlashWorkerProvider
from macr_runtime.glm_approval import GlmApprovalStore
from macr_runtime.model_token_store import ModelTokenPolicyStore
from macr_runtime.registry import ProviderRegistry
from macr_runtime.runtime import RuntimeServices
from macr_runtime.scheduler import PlanQueue, QueueMemberState
from macr_runtime.storage import StorageLayout
from macr_runtime.t1_manifest import T1ExecutionManifest
from macr_runtime.token_policy import ModelTokenOverride, t1_glm_live_policy
from tests.support import d_drive_tempdir, write_fake_google_credential
from tests.test_coordination import make_plan
from tests.test_glm_provider import FakeTransport, success_document
from tests.test_scheduler import Clock, _authorize, _member
from tests.test_t1_dispatcher import approved_manifest


ROOT = Path(__file__).resolve().parents[1]


def write_legacy_events(path: Path, *, count: int) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = "".join(
        json.dumps(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "provider.candidate_completed",
                "observed_at": f"2026-08-27T00:00:{index:02d}+00:00",
                "payload": {
                    "provider_id": "legacy",
                    "task_id": f"legacy-{index}",
                    "status": "candidate_success",
                },
            },
            sort_keys=True,
        )
        + "\n"
        for index in range(count)
    ).encode("utf-8")
    path.write_bytes(raw)
    return raw


class StaticKeySource:
    def load(self):
        return "test-id." + "test-secret"

    def check_metadata(self):
        return None


class ExplodingKeySource:
    def load(self):
        raise AssertionError("contradiction must fail before key load")

    def check_metadata(self):
        raise AssertionError("contradiction must fail before key metadata")


class DoctorTests(unittest.TestCase):
    def test_t1_worker_requires_network_opt_in_before_manifest_or_state(self) -> None:
        with d_drive_tempdir() as root:
            state_root = root / "must-not-exist"
            output = io.StringIO()
            environment = {**os.environ, "MACR_STATE_ROOT": str(state_root)}
            with patch.dict(os.environ, environment, clear=True):
                with contextlib.redirect_stdout(output):
                    status = _t1_worker(
                        "missing-private-manifest.json",
                        str(ROOT / "config" / "providers.json"),
                        dispatcher_id="worker-1",
                        allow_network=False,
                        allow_local=False,
                    )

            self.assertEqual(status, 3)
            self.assertIn("network_opt_in_required", output.getvalue())
            self.assertFalse(state_root.exists())

    def test_t1_stage_cli_is_content_free_and_performs_no_provider_call(self) -> None:
        with d_drive_tempdir() as state_root:
            transport = FakeTransport(success_document())
            provider = GlmFlashWorkerProvider(
                next(
                    item
                    for item in load_provider_configs(
                        ROOT / "config" / "providers.json"
                    )
                    if item.id == "glm_flash_worker"
                ),
                transport=transport,
                environ={"MACR_STATE_ROOT": str(state_root)},
                key_source=StaticKeySource(),
                token_policy=t1_glm_live_policy(),
            )
            source = approved_manifest(provider)
            subject = T1ExecutionManifest.create(
                plan_digest=source.plan_digest,
                members=source.members,
                aggregate_cost_ceiling_usd=source.aggregate_cost_ceiling_usd,
                campaign_cost_ceiling_usd=source.campaign_cost_ceiling_usd,
                expires_at=(
                    datetime.now(timezone.utc) + timedelta(minutes=10)
                ).isoformat(),
                authorized_dispatchers=source.authorized_dispatchers,
            )
            approval_store = GlmApprovalStore(state_root)
            for item in subject.members:
                approval_store.create(
                    item.task.delegation_approval_sha256,
                    signing_key="test-id.test-secret",
                    expires_in_days=1,
                )
            manifest_path = state_root / "t1-private-manifest.json"
            manifest_path.write_text(
                json.dumps(subject.to_dict()),
                encoding="utf-8",
            )
            output = io.StringIO()
            environment = {**os.environ, "MACR_STATE_ROOT": str(state_root)}
            with patch.dict(os.environ, environment, clear=True):
                with contextlib.redirect_stdout(output):
                    status = _t1_stage(
                        str(manifest_path),
                        str(ROOT / "config" / "providers.json"),
                        dispatcher_ids=subject.authorized_dispatchers,
                        expires_in_minutes=30,
                    )
                posts_after_stage = len(transport.posts)
                worker_output = io.StringIO()
                services = RuntimeServices.from_layout(
                    StorageLayout.from_environment()
                )
                with contextlib.redirect_stdout(worker_output):
                    worker_status = _t1_worker(
                        str(manifest_path),
                        str(ROOT / "config" / "providers.json"),
                        dispatcher_id="worker-1",
                        allow_network=True,
                        allow_local=False,
                        registry_override=ProviderRegistry((provider,)),
                        services_override=services,
                    )
            queue = PlanQueue(state_root / "runtime" / "dispatch.sqlite3")
            counts = queue.state_counts()

        document = json.loads(output.getvalue())
        worker_document = json.loads(worker_output.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(worker_status, 0)
        self.assertEqual(document["status"], "t1_staged")
        self.assertEqual(worker_document["status"], "t1_worker_completed")
        self.assertEqual(counts["queued"], 2)
        self.assertEqual(counts["completed"], 1)
        self.assertFalse(document["network_activity"])
        self.assertNotIn("T1_MEMBER_", output.getvalue())
        self.assertNotIn("T1_MEMBER_", worker_output.getvalue())
        self.assertNotIn(str(state_root), output.getvalue())
        self.assertEqual(posts_after_stage, 0)
        self.assertEqual(len(transport.posts), 1)

    def test_queue_status_lists_global_reconciliation_content_free(self) -> None:
        now = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
        clock = Clock(now)
        with d_drive_tempdir() as state_root:
            queue = PlanQueue(
                state_root / "runtime" / "dispatch.sqlite3",
                now=clock,
            )
            plan = _authorize(
                queue.database.path,
                clock,
                (_member(0),),
                plan_digest="e" * 64,
            )
            queue.enqueue(plan)
            claim = queue.claim("dispatcher-a", lease_seconds=60)
            assert claim is not None
            queue.require_reconciliation(
                claim.member_id,
                claim.dispatcher_id,
                claim.fencing_token,
                terminal_evidence_digest="c" * 64,
                observed_cost_usd=0.001,
            )
            output = io.StringIO()
            environment = {**os.environ, "MACR_STATE_ROOT": str(state_root)}
            with patch.dict(os.environ, environment, clear=True):
                with contextlib.redirect_stdout(output):
                    status = _queue_status(
                        QueueMemberState.RECONCILIATION_REQUIRED.value,
                        limit=100,
                        after_member_id=None,
                    )

        document = json.loads(output.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(document["counts"]["reconciliation_required"], 1)
        self.assertEqual(len(document["members"]), 1)
        self.assertEqual(
            set(document["members"][0]),
            {
                "member_id",
                "plan_digest",
                "ordinal",
                "member_digest",
                "state",
                "lease_holder",
                "fencing_token",
                "lease_expires_at",
                "attempts",
                "terminal_at",
                "terminal_evidence_digest",
                "observed_cost_usd",
            },
        )
        self.assertFalse(document["network_activity"])
        self.assertNotIn(str(state_root), output.getvalue())

    def test_model_observe_and_passport_use_operator_snapshot_without_network(self) -> None:
        source = (
            ROOT
            / "tests"
            / "fixtures"
            / "openrouter-models-2026-08-28.json"
        )
        expected = hashlib.sha256(source.read_bytes()).hexdigest()
        observe_output = io.StringIO()
        passport_output = io.StringIO()
        with d_drive_tempdir() as state_root:
            environment = {
                **os.environ,
                "MACR_STATE_ROOT": str(state_root),
                "MACR_ROOT": str(ROOT),
                "CODEX_HOME_TARGET": (
                    r"D:\AI_RESIDENCE\AI_Runtime\codex-home"
                ),
            }
            with patch.dict(os.environ, environment, clear=True):
                with contextlib.redirect_stdout(observe_output):
                    observe_status = _model_observe(
                        str(source),
                        expected,
                        "2026-08-29T00:00:00+00:00",
                    )
                observed = json.loads(observe_output.getvalue())
                with contextlib.redirect_stdout(passport_output):
                    passport_status = _model_passport(
                        observed["subject_ids"][0],
                        "2026-08-29T00:00:00+00:00",
                    )
            runtime_exists = (
                state_root / "runtime" / "dispatch.sqlite3"
            ).exists()

        passport = json.loads(passport_output.getvalue())
        self.assertEqual(observe_status, 0)
        self.assertEqual(passport_status, 0)
        self.assertEqual(observed["status"], "model_observation_complete")
        self.assertFalse(observed["network_activity"])
        self.assertFalse(observed["execution_provider_created"])
        self.assertEqual(passport["status"], "model_passport_complete")
        self.assertFalse(passport["network_activity"])
        self.assertFalse(runtime_exists)
        self.assertNotIn("description", passport_output.getvalue().lower())

    def test_plan_shadow_show_and_diff_persist_only_observatory_records(self) -> None:
        first = make_plan()
        second = dataclasses.replace(
            first,
            plan_revision=2,
            planned_at="2026-08-30T00:00:00+00:00",
        )
        with d_drive_tempdir() as state_root:
            first_path = state_root / "plan-one.json"
            second_path = state_root / "plan-two.json"
            first_path.write_text(json.dumps(first.to_dict()), encoding="utf-8")
            second_path.write_text(json.dumps(second.to_dict()), encoding="utf-8")
            outputs = [io.StringIO() for _ in range(5)]
            environment = {
                **os.environ,
                "MACR_STATE_ROOT": str(state_root),
                "MACR_ROOT": str(ROOT),
                "CODEX_HOME_TARGET": (
                    r"D:\AI_RESIDENCE\AI_Runtime\codex-home"
                ),
            }
            with patch.dict(os.environ, environment, clear=True):
                with contextlib.redirect_stdout(outputs[0]):
                    first_status = _plan_shadow(
                        str(first_path),
                        "d" * 64,
                        "2026-08-29T01:00:00+00:00",
                    )
                with contextlib.redirect_stdout(outputs[1]):
                    second_status = _plan_shadow(
                        str(second_path),
                        "d" * 64,
                        "2026-08-30T01:00:00+00:00",
                    )
                with contextlib.redirect_stdout(outputs[2]):
                    show_status = _plan_show(first.plan_digest)
                with contextlib.redirect_stdout(outputs[3]):
                    diff_status = _plan_diff(
                        first.plan_digest,
                        second.plan_digest,
                    )
                with contextlib.redirect_stdout(outputs[4]):
                    same_status = _plan_diff(
                        first.plan_digest,
                        first.plan_digest,
                    )
            connection = sqlite3.connect(
                state_root / "observatory" / "observatory.sqlite3"
            )
            plan_count = connection.execute(
                "SELECT COUNT(*) FROM coordination_plans"
            ).fetchone()[0]
            comparison_count = connection.execute(
                "SELECT COUNT(*) FROM shadow_comparisons"
            ).fetchone()[0]
            connection.close()
            runtime_exists = (
                state_root / "runtime" / "dispatch.sqlite3"
            ).exists()

        statuses = (
            first_status,
            second_status,
            show_status,
            diff_status,
            same_status,
        )
        documents = [json.loads(item.getvalue()) for item in outputs]
        self.assertEqual(statuses, (0, 0, 0, 0, 0))
        self.assertEqual(plan_count, 2)
        self.assertEqual(comparison_count, 2)
        self.assertFalse(runtime_exists)
        self.assertFalse(documents[0]["dispatch_performed"])
        self.assertFalse(documents[1]["network_activity"])
        self.assertEqual(documents[2]["plan_digest"], first.plan_digest)
        self.assertIn("plan_revision", documents[3]["changed_fields"])
        self.assertFalse(documents[3]["identical"])
        self.assertTrue(documents[4]["identical"])
        self.assertNotIn(str(state_root), "".join(item.getvalue() for item in outputs))

    def test_plan_shadow_invalid_comparison_rolls_back_plan_record(self) -> None:
        plan = make_plan()
        with d_drive_tempdir() as state_root:
            plan_path = state_root / "plan.json"
            plan_path.write_text(json.dumps(plan.to_dict()), encoding="utf-8")
            output = io.StringIO()
            environment = {
                **os.environ,
                "MACR_STATE_ROOT": str(state_root),
                "MACR_ROOT": str(ROOT),
                "CODEX_HOME_TARGET": (
                    r"D:\AI_RESIDENCE\AI_Runtime\codex-home"
                ),
            }
            with patch.dict(os.environ, environment, clear=True):
                with contextlib.redirect_stdout(output):
                    status = _plan_shadow(
                        str(plan_path),
                        "not-a-digest",
                        "2026-08-29T01:00:00+00:00",
                    )
            connection = sqlite3.connect(
                state_root / "observatory" / "observatory.sqlite3"
            )
            counts = tuple(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("coordination_plans", "shadow_comparisons")
            )
            connection.close()

        self.assertEqual(status, 4)
        self.assertEqual(counts, (0, 0))
        self.assertEqual(json.loads(output.getvalue())["status"], "shadow_plan_failed")

    def test_evidence_inspect_and_import_are_offline_content_free(self) -> None:
        source_manifest = (
            ROOT / "tests" / "fixtures" / "glm-a3-evidence-manifest.json"
        )
        source_evidence = ROOT / "tests" / "fixtures" / "glm-a3-evidence"
        with d_drive_tempdir() as state_root:
            manifest = state_root / source_manifest.name
            shutil.copy2(source_manifest, manifest)
            shutil.copytree(source_evidence, state_root / source_evidence.name)
            expected = hashlib.sha256(manifest.read_bytes()).hexdigest()
            inspect_output = io.StringIO()
            import_output = io.StringIO()
            environment = {
                **os.environ,
                "MACR_STATE_ROOT": str(state_root),
                "MACR_ROOT": str(ROOT),
                "CODEX_HOME_TARGET": (
                    r"D:\AI_RESIDENCE\AI_Runtime\codex-home"
                ),
            }
            with patch.dict(os.environ, environment, clear=True):
                with contextlib.redirect_stdout(inspect_output):
                    inspect_status = _evidence_inspect(str(manifest))
                self.assertFalse(
                    (state_root / "observatory" / "observatory.sqlite3").exists()
                )
                with contextlib.redirect_stdout(import_output):
                    import_status = _evidence_import(
                        str(manifest),
                        expected,
                    )
            connection = sqlite3.connect(
                state_root / "observatory" / "observatory.sqlite3"
            )
            evidence_count = connection.execute(
                "SELECT COUNT(*) FROM evidence_items"
            ).fetchone()[0]
            decision_count = connection.execute(
                "SELECT COUNT(*) FROM qualification_decisions"
            ).fetchone()[0]
            connection.close()

        inspected = json.loads(inspect_output.getvalue())
        imported = json.loads(import_output.getvalue())
        self.assertEqual(inspect_status, 0)
        self.assertEqual(import_status, 0)
        self.assertEqual(inspected["status"], "evidence_inspection_complete")
        self.assertEqual(imported["status"], "evidence_import_complete")
        self.assertFalse(inspected["network_activity"])
        self.assertFalse(imported["network_activity"])
        self.assertEqual(evidence_count, 3)
        self.assertEqual(decision_count, 0)
        self.assertNotIn(str(state_root), inspect_output.getvalue())
        self.assertNotIn(str(state_root), import_output.getvalue())
    def test_migrate_ledger_dry_run_writes_nothing(self) -> None:
        with d_drive_tempdir() as state_root:
            source = state_root / "ledger" / "events.jsonl"
            before = write_legacy_events(source, count=2)
            output = io.StringIO()
            environment = {
                **os.environ,
                "MACR_STATE_ROOT": str(state_root),
                "MACR_ROOT": str(ROOT),
                "CODEX_HOME_TARGET": r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
            }
            with patch.dict(os.environ, environment, clear=True):
                with contextlib.redirect_stdout(output):
                    status = _migrate_ledger(dry_run=True, expected_count=2)

            self.assertEqual(source.read_bytes(), before)
            self.assertFalse((state_root / "runtime" / "dispatch.sqlite3").exists())
            self.assertFalse((state_root / "quarantine").exists())

        document = json.loads(output.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(document["status"], "legacy_migration_dry_run_complete")
        self.assertEqual(document["valid_count"], 2)

    def test_migrate_ledger_exact_import_and_second_run_are_idempotent(self) -> None:
        with d_drive_tempdir() as state_root:
            source = state_root / "ledger" / "events.jsonl"
            before = write_legacy_events(source, count=2)
            environment = {
                **os.environ,
                "MACR_STATE_ROOT": str(state_root),
                "MACR_ROOT": str(ROOT),
                "CODEX_HOME_TARGET": r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
            }
            first_output = io.StringIO()
            second_output = io.StringIO()
            with patch.dict(os.environ, environment, clear=True):
                with contextlib.redirect_stdout(first_output):
                    first_status = _migrate_ledger(
                        dry_run=False,
                        expected_count=2,
                    )
                with contextlib.redirect_stdout(second_output):
                    second_status = _migrate_ledger(
                        dry_run=False,
                        expected_count=2,
                    )

            connection = sqlite3.connect(state_root / "runtime" / "dispatch.sqlite3")
            event_count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            source_count = connection.execute(
                "SELECT COUNT(*) FROM legacy_sources WHERE complete = 1"
            ).fetchone()[0]
            connection.close()
            self.assertEqual(source.read_bytes(), before)

        first = json.loads(first_output.getvalue())
        second = json.loads(second_output.getvalue())
        self.assertEqual(first_status, 0)
        self.assertEqual(second_status, 0)
        self.assertEqual(first["imported_count"], 2)
        self.assertEqual(second["imported_count"], 0)
        self.assertEqual(second["already_imported_count"], 2)
        self.assertEqual(event_count, 2)
        self.assertEqual(source_count, 1)

    def test_migrate_ledger_corruption_is_quarantined_and_incomplete(self) -> None:
        with d_drive_tempdir() as state_root:
            source = state_root / "ledger" / "events.jsonl"
            source.parent.mkdir(parents=True)
            corrupt = b'{"event_id":"cut" trailing\n'
            source.write_bytes(corrupt)
            output = io.StringIO()
            environment = {
                **os.environ,
                "MACR_STATE_ROOT": str(state_root),
                "MACR_ROOT": str(ROOT),
                "CODEX_HOME_TARGET": r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
            }
            with patch.dict(os.environ, environment, clear=True):
                with contextlib.redirect_stdout(output):
                    status = _migrate_ledger(dry_run=False, expected_count=1)

            quarantine_files = tuple((state_root / "quarantine").rglob("*.bin"))
            self.assertEqual(source.read_bytes(), corrupt)
            self.assertEqual(quarantine_files[0].read_bytes(), corrupt.rstrip(b"\n"))

        document = json.loads(output.getvalue())
        self.assertEqual(status, 5)
        self.assertEqual(document["status"], "legacy_migration_incomplete")
        self.assertEqual(document["corrupt_count"], 1)

    def test_invoke_refuses_unmigrated_legacy_before_task_or_authority(self) -> None:
        with d_drive_tempdir() as state_root:
            source = state_root / "ledger" / "events.jsonl"
            write_legacy_events(source, count=1)
            output = io.StringIO()
            environment = {
                **os.environ,
                "MACR_STATE_ROOT": str(state_root),
                "MACR_ROOT": str(ROOT),
                "CODEX_HOME_TARGET": r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
            }
            with patch.dict(os.environ, environment, clear=True):
                with contextlib.redirect_stdout(output):
                    status = _invoke(
                        "minimax",
                        "this-file-must-not-be-read.json",
                        str(ROOT / "config" / "providers.json"),
                        allow_network=True,
                        allow_local=False,
                    )

            connection = sqlite3.connect(state_root / "runtime" / "dispatch.sqlite3")
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("dispatch_authorities", "dispatch_leases", "events")
            }
            connection.close()

        document = json.loads(output.getvalue())
        self.assertEqual(status, 5)
        self.assertEqual(document["status"], "legacy_migration_required")
        self.assertEqual(counts, {"dispatch_authorities": 0, "dispatch_leases": 0, "events": 0})

    def test_glm_approve_rejects_contradiction_before_key_access(self) -> None:
        with d_drive_tempdir() as temp:
            task = TaskContract(
                task_id="contradictory-glm-task",
                goal="Use structured policy only.",
                task_type="delegated_routine",
                delegable=True,
                delegation_class=DelegationClass.NON_SENSITIVE_ROUTINE,
                delegation_approval_sha256="0" * 64,
                constraints=TaskConstraints(
                    max_cost_usd=0.01,
                    max_latency_s=30,
                    max_output_tokens=256,
                    internet=True,
                    privacy=PrivacyLevel.PUBLIC,
                ),
                required_capabilities=("text_generation",),
                policy_clauses=TaskPolicyClauses(
                    import_mode=ImportMode.NONE,
                    required_imports=(
                        RequiredImport("required-module", "type_only"),
                    ),
                ),
            )
            task_path = temp / "task.json"
            task_path.write_text(json.dumps(task.to_dict()), encoding="utf-8")
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                status = _glm_approve(
                    str(task_path),
                    str(ROOT / "config" / "providers.json"),
                    expires_in_days=1,
                    key_source=ExplodingKeySource(),
                )

        self.assertEqual(status, 4)
        self.assertIn("TaskContradictionError", output.getvalue())
    def test_strict_ignores_intentionally_disabled_providers(self) -> None:
        with d_drive_tempdir() as temp:
            credential = write_fake_google_credential(temp / "credential.json")
            environment = {
                "MINIMAX_API_KEY": "test-key",
                "MINIMAX_BASE_URL": "https://api.minimax.io/v1",
                "MINIMAX_MODEL": "test-model",
                "XAI_API_KEY": "test-key",
                "GOOGLE_APPLICATION_CREDENTIALS": str(credential),
                "GOOGLE_CLOUD_PROJECT": "test-project",
            }
            output = io.StringIO()
            with patch.dict(os.environ, environment, clear=False):
                with contextlib.redirect_stdout(output):
                    status = _doctor(
                        str(ROOT / "config" / "providers.json"),
                        strict=True,
                        key_sources={"glm_flash_worker": StaticKeySource()},
                    )
        self.assertEqual(status, 0)
        self.assertNotIn("test-key", output.getvalue())

    def test_strict_fails_when_enabled_provider_is_not_ready(self) -> None:
        without_minimax = {
            key: value
            for key, value in os.environ.items()
            if key not in {"MINIMAX_API_KEY", "MINIMAX_BASE_URL", "MINIMAX_MODEL"}
        }
        with patch.dict(os.environ, without_minimax, clear=True):
            with contextlib.redirect_stdout(io.StringIO()):
                status = _doctor(str(ROOT / "config" / "providers.json"), strict=True)
        self.assertEqual(status, 2)

    def test_invoke_requires_explicit_network_opt_in_before_reading_task(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = _invoke(
                "minimax",
                "this-file-must-not-be-read.json",
                str(ROOT / "config" / "providers.json"),
                allow_network=False,
                allow_local=False,
            )
        self.assertEqual(status, 3)
        self.assertIn("network_opt_in_required", output.getvalue())

    def test_local_provider_requires_local_opt_in_before_reading_task(self) -> None:
        output = io.StringIO()
        state_root = ROOT / "state-must-not-be-created"
        environment = {
            "MACR_ROOT": str(ROOT),
            "MACR_STATE_ROOT": str(state_root),
            "CODEX_HOME_TARGET": r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
        }
        with patch.dict(os.environ, environment, clear=False):
            with contextlib.redirect_stdout(output):
                status = _invoke(
                    "ollama_qwythos",
                    "this-file-must-not-be-read.json",
                    str(ROOT / "config" / "providers.json"),
                    allow_network=True,
                    allow_local=False,
                )
        self.assertEqual(status, 3)
        self.assertIn("local_opt_in_required", output.getvalue())
        self.assertFalse(state_root.exists())

    def test_external_provider_rejects_local_only_opt_in_before_reading_task(self) -> None:
        output = io.StringIO()
        state_root = ROOT / "state-must-not-be-created"
        environment = {
            "MACR_ROOT": str(ROOT),
            "MACR_STATE_ROOT": str(state_root),
            "CODEX_HOME_TARGET": r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
        }
        with patch.dict(os.environ, environment, clear=False):
            with contextlib.redirect_stdout(output):
                status = _invoke(
                    "grok",
                    "this-file-must-not-be-read.json",
                    str(ROOT / "config" / "providers.json"),
                    allow_network=False,
                    allow_local=True,
                )
        self.assertEqual(status, 3)
        self.assertIn("network_opt_in_required", output.getvalue())
        self.assertFalse(state_root.exists())

    def test_glm_preflight_emits_digest_without_key_or_task_content(self) -> None:
        with d_drive_tempdir() as temp:
            task = TaskContract(
                task_id="glm-preflight-digest",
                goal="PUBLIC PREFLIGHT BODY",
                task_type="delegated_routine",
                delegable=True,
                delegation_class=DelegationClass.NON_SENSITIVE_ROUTINE,
                constraints=TaskConstraints(
                    max_cost_usd=0.01,
                    max_latency_s=30,
                    max_output_tokens=256,
                    internet=True,
                    privacy=PrivacyLevel.PUBLIC,
                ),
                required_capabilities=("text_generation",),
            )
            task_path = temp / "task.json"
            task_path.write_text(
                json.dumps(task.to_dict()),
                encoding="utf-8",
            )
            output = io.StringIO()
            without_key = {
                key: value for key, value in os.environ.items() if key != "ZAI_API_KEY"
            }
            without_key["MACR_STATE_ROOT"] = str(temp)
            with patch.dict(os.environ, without_key, clear=True):
                with contextlib.redirect_stdout(output):
                    status = _glm_preflight(
                        str(task_path),
                        str(ROOT / "config" / "providers.json"),
                        show_required_digest=True,
                    )

        document = json.loads(output.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(document["status"], "approval_required")
        self.assertEqual(len(document["required_approval_sha256"]), 64)
        self.assertNotIn("PUBLIC PREFLIGHT BODY", output.getvalue())

    def test_glm_preflight_rejects_stale_digest_without_key(self) -> None:
        with d_drive_tempdir() as temp:
            task = TaskContract(
                task_id="glm-preflight-stale",
                goal="PUBLIC STALE BODY",
                task_type="delegated_routine",
                delegable=True,
                delegation_class=DelegationClass.NON_SENSITIVE_ROUTINE,
                delegation_approval_sha256="0" * 64,
                constraints=TaskConstraints(
                    max_cost_usd=0.01,
                    max_latency_s=30,
                    max_output_tokens=256,
                    internet=True,
                    privacy=PrivacyLevel.PUBLIC,
                ),
                required_capabilities=("text_generation",),
            )
            task_path = temp / "task.json"
            task_path.write_text(
                json.dumps(task.to_dict()),
                encoding="utf-8",
            )
            output = io.StringIO()
            environment = {**os.environ, "MACR_STATE_ROOT": str(temp)}
            with patch.dict(os.environ, environment, clear=True):
                with contextlib.redirect_stdout(output):
                    status = _glm_preflight(
                        str(task_path),
                        str(ROOT / "config" / "providers.json"),
                        show_required_digest=False,
                    )

        document = json.loads(output.getvalue())
        self.assertEqual(status, 4)
        self.assertEqual(document["status"], "approval_invalid")
        self.assertNotIn("PUBLIC STALE BODY", output.getvalue())

    def test_glm_preflight_applies_active_exact_model_override(self) -> None:
        with d_drive_tempdir() as temp:
            store = ModelTokenPolicyStore(temp / "settings" / "model-token-policies.sqlite3")
            base = store.effective_policy("glm_flash_worker", "glm-5.3-flash")
            store.save_override(
                ModelTokenOverride(
                    provider_id=base.provider_id,
                    model_id=base.model_id,
                    revision=1,
                    context_warning_tokens=100_000,
                    hard_context_tokens=128_000,
                    default_output_tokens=8_192,
                    max_output_tokens=8_192,
                    base_policy_digest=base.policy_digest,
                ),
                activate=True,
            )
            task = TaskContract(
                task_id="glm-preflight-model-policy",
                goal="PUBLIC POLICY BODY",
                task_type="delegated_routine",
                delegable=True,
                delegation_class=DelegationClass.NON_SENSITIVE_ROUTINE,
                constraints=TaskConstraints(
                    max_cost_usd=0.02,
                    max_latency_s=30,
                    max_output_tokens=16_384,
                    max_context_tokens=128_000,
                    internet=True,
                    privacy=PrivacyLevel.PUBLIC,
                ),
                required_capabilities=("text_generation",),
            )
            task_path = temp / "task.json"
            task_path.write_text(json.dumps(task.to_dict()), encoding="utf-8")
            output = io.StringIO()
            environment = {**os.environ, "MACR_STATE_ROOT": str(temp)}
            with patch.dict(os.environ, environment, clear=True):
                with contextlib.redirect_stdout(output):
                    status = _glm_preflight(
                        str(task_path),
                        str(ROOT / "config" / "providers.json"),
                        show_required_digest=True,
                    )

        document = json.loads(output.getvalue())
        self.assertEqual(status, 4)
        self.assertEqual(document["failure_type"], "ProviderPolicyError")
        self.assertNotIn("PUBLIC POLICY BODY", output.getvalue())

    def test_glm_approved_preflight_output_remains_content_free(self) -> None:
        with d_drive_tempdir() as temp:
            task = TaskContract(
                task_id="glm-preflight-approved",
                goal="PUBLIC APPROVED BODY",
                task_type="delegated_routine",
                delegable=True,
                delegation_class=DelegationClass.NON_SENSITIVE_ROUTINE,
                constraints=TaskConstraints(
                    max_cost_usd=0.01,
                    max_latency_s=30,
                    max_output_tokens=256,
                    internet=True,
                    privacy=PrivacyLevel.PUBLIC,
                ),
                required_capabilities=("text_generation",),
            )
            config = next(
                item
                for item in load_provider_configs(ROOT / "config" / "providers.json")
                if item.id == "glm_flash_worker"
            )
            digest = GlmFlashWorkerProvider(config, environ={}).approval_metadata(task)[
                "required_approval_sha256"
            ]
            task = TaskContract.from_dict(
                {
                    **task.to_dict(),
                    "delegation_approval_sha256": digest,
                }
            )
            task_path = temp / "task.json"
            task_path.write_text(json.dumps(task.to_dict()), encoding="utf-8")
            GlmApprovalStore(temp).create(
                digest,
                signing_key="test-id." + "test-secret",
                expires_in_days=30,
            )
            output = io.StringIO()
            environment = {**os.environ, "MACR_STATE_ROOT": str(temp)}
            with patch.dict(os.environ, environment, clear=True):
                with contextlib.redirect_stdout(output):
                    status = _glm_preflight(
                        str(task_path),
                        str(ROOT / "config" / "providers.json"),
                        show_required_digest=False,
                    )

        document = json.loads(output.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(document["status"], "preflight_structurally_valid")
        self.assertEqual(document["required_approval_sha256"], digest)
        self.assertNotIn("system_text", document)
        self.assertNotIn("user_text", document)
        self.assertNotIn("PUBLIC APPROVED BODY", output.getvalue())

    def test_glm_approve_creates_external_host_record_without_key_or_content(self) -> None:
        with d_drive_tempdir() as state_root:
            task = TaskContract(
                task_id="glm-host-approve",
                goal="PUBLIC HOST APPROVAL BODY",
                task_type="delegated_routine",
                delegable=True,
                delegation_class=DelegationClass.NON_SENSITIVE_ROUTINE,
                constraints=TaskConstraints(
                    max_cost_usd=0.01,
                    max_latency_s=30,
                    max_output_tokens=256,
                    internet=True,
                    privacy=PrivacyLevel.PUBLIC,
                ),
                required_capabilities=("text_generation",),
            )
            config_path = ROOT / "config" / "providers.json"
            config = next(
                item
                for item in load_provider_configs(config_path)
                if item.id == "glm_flash_worker"
            )
            digest = GlmFlashWorkerProvider(config, environ={}).approval_metadata(task)[
                "required_approval_sha256"
            ]
            task = TaskContract.from_dict(
                {
                    **task.to_dict(),
                    "delegation_approval_sha256": digest,
                }
            )
            task_path = state_root / "task.json"
            task_path.write_text(json.dumps(task.to_dict()), encoding="utf-8")
            output = io.StringIO()
            environment = {
                **os.environ,
                "MACR_STATE_ROOT": str(state_root),
            }
            environment.pop("ZAI_API_KEY", None)
            with patch.dict(os.environ, environment, clear=True):
                with contextlib.redirect_stdout(output):
                    status = _glm_approve(
                        str(task_path),
                        str(config_path),
                        expires_in_days=30,
                        key_source=StaticKeySource(),
                        replace_existing=True,
                    )

        document = json.loads(output.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(document["status"], "host_approval_created")
        self.assertEqual(document["approval_sha256"], digest)
        self.assertEqual(document["approved_by"], "host_operator")
        self.assertNotIn("PUBLIC HOST APPROVAL BODY", output.getvalue())


if __name__ == "__main__":
    unittest.main()
