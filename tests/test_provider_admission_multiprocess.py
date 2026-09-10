from __future__ import annotations

import multiprocessing
import queue
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from macr_runtime.authority import AuthorityScope, DispatchAuthorityStore
from macr_runtime.errors import ProviderAdmissionBusyError
from macr_runtime.execution import AuthorizationReference
from macr_runtime.provider_admission import (
    AdmissionLane,
    ProjectAdmissionBinding,
    ProviderAdmissionKernel,
    ProviderAdmissionRequest,
    ProviderAdmissionTargetBinding,
    glm_provider_admission_policy,
)
from tests.support import d_drive_tempdir


def _try_admission_worker(
    database: str,
    reference_data: dict[str, object],
    project_data: dict[str, object],
    ready,
    start,
    results,
) -> None:
    reference = AuthorizationReference(**reference_data)
    project = ProjectAdmissionBinding.from_dict(project_data)
    request = ProviderAdmissionRequest(
        request_id=str(uuid.uuid4()),
        provider_id="glm_flash_worker",
        project_binding_digest=project.binding_digest,
        lane=AdmissionLane.ROUTINE,
        run_id=str(uuid.uuid4()),
        authorization=reference,
        plane="delegation",
        task_type="delegated_routine",
        task_digest="b" * 64,
        member_digest="c" * 64,
        batch_id=None,
        provider_tier_binding_digest="a" * 64,
    )
    kernel = ProviderAdmissionKernel(database)
    ready.put(project.project_id)
    if not start.wait(20):
        results.put({"status": "start_timeout"})
        return
    try:
        permit = kernel.try_admit(request, ttl_seconds=60)
    except ProviderAdmissionBusyError:
        results.put({"status": "busy"})
    except Exception as exc:
        results.put({"status": "error", "type": type(exc).__name__})
    else:
        results.put(
            {
                "status": "granted",
                "request_id": permit.request_id,
                "fencing_token": permit.fencing_token,
            }
        )


class ProviderAdmissionMultiprocessTests(unittest.TestCase):
    def test_governed_target_two_grants_exactly_two_processes(self) -> None:
        with d_drive_tempdir() as temp:
            database = temp / "runtime" / "dispatch.sqlite3"
            policy = glm_provider_admission_policy()
            kernel = ProviderAdmissionKernel(database)
            authorities = DispatchAuthorityStore(database)
            target = ProviderAdmissionTargetBinding.create(policy, target=2)
            target_reference = authorities.issue(
                source_kind="operator_capacity_authority",
                source_id="multiprocess-target-two",
                scope=AuthorityScope(
                    providers=(policy.provider_id,),
                    planes=("provider_capacity_activation",),
                    task_types=("provider_capacity_target",),
                    provider_admission_target_digests=(
                        target.binding_digest,
                    ),
                    scope_contract_version=3,
                ),
                expires_at=(
                    datetime.now(timezone.utc) + timedelta(minutes=10)
                ).isoformat(),
            )
            kernel.activate_target(target, target_reference)
            projects = tuple(
                ProjectAdmissionBinding(
                    f"target-two-{index}",
                    1,
                    "operator_asserted",
                )
                for index in range(8)
            )
            reference = authorities.issue(
                source_kind="operator_test",
                source_id="multiprocess-two-admission",
                scope=AuthorityScope(
                    providers=(policy.provider_id,),
                    planes=("delegation",),
                    task_types=("delegated_routine",),
                    provider_tier_binding_digests=("a" * 64,),
                    project_binding_digests=tuple(
                        item.binding_digest for item in projects
                    ),
                    admission_lanes=(AdmissionLane.ROUTINE.value,),
                    provider_admission_policy_digests=(policy.policy_digest,),
                    scope_contract_version=3,
                ),
                expires_at=(
                    datetime.now(timezone.utc) + timedelta(minutes=10)
                ).isoformat(),
            )
            reference_data = {
                "source_kind": reference.source_kind,
                "source_id": reference.source_id,
                "digest": reference.digest,
                "revision": reference.revision,
                "epoch": reference.epoch,
                "scope": reference.scope,
            }
            context = multiprocessing.get_context("spawn")
            ready = context.Queue()
            start = context.Event()
            results = context.Queue()
            processes = [
                context.Process(
                    target=_try_admission_worker,
                    args=(
                        str(database),
                        reference_data,
                        project.to_dict(),
                        ready,
                        start,
                        results,
                    ),
                )
                for project in projects
            ]
            try:
                for process in processes:
                    process.start()
                for _ in processes:
                    ready.get(timeout=30)
                start.set()
                for process in processes:
                    process.join(timeout=30)
                self.assertTrue(all(not process.is_alive() for process in processes))
                observed = [results.get(timeout=10) for _ in processes]
            finally:
                for process in processes:
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=10)
            status = ProviderAdmissionKernel(database).status(policy.provider_id)

        self.assertEqual(
            sum(item["status"] == "granted" for item in observed),
            2,
        )
        self.assertEqual(
            sum(item["status"] == "busy" for item in observed),
            6,
        )
        self.assertEqual(status.counts["granted"], 2)
        self.assertEqual(status.effective_target, 2)

    def test_eight_processes_share_one_effective_provider_slot(self) -> None:
        with d_drive_tempdir() as temp:
            database = temp / "runtime" / "dispatch.sqlite3"
            policy = glm_provider_admission_policy()
            ProviderAdmissionKernel(database)
            projects = tuple(
                ProjectAdmissionBinding(
                    f"project-{index}",
                    1,
                    "operator_asserted",
                )
                for index in range(8)
            )
            authorities = DispatchAuthorityStore(database)
            reference = authorities.issue(
                source_kind="operator_test",
                source_id="multiprocess-admission",
                scope=AuthorityScope(
                    providers=(policy.provider_id,),
                    planes=("delegation",),
                    task_types=("delegated_routine",),
                    provider_tier_binding_digests=("a" * 64,),
                    project_binding_digests=tuple(
                        item.binding_digest for item in projects
                    ),
                    admission_lanes=(AdmissionLane.ROUTINE.value,),
                    provider_admission_policy_digests=(policy.policy_digest,),
                    scope_contract_version=3,
                ),
                expires_at=(
                    datetime.now(timezone.utc) + timedelta(minutes=10)
                ).isoformat(),
            )
            reference_data = {
                "source_kind": reference.source_kind,
                "source_id": reference.source_id,
                "digest": reference.digest,
                "revision": reference.revision,
                "epoch": reference.epoch,
                "scope": reference.scope,
            }
            context = multiprocessing.get_context("spawn")
            ready = context.Queue()
            start = context.Event()
            results = context.Queue()
            processes = [
                context.Process(
                    target=_try_admission_worker,
                    args=(
                        str(database),
                        reference_data,
                        project.to_dict(),
                        ready,
                        start,
                        results,
                    ),
                )
                for project in projects
            ]
            try:
                for process in processes:
                    process.start()
                observed_ready = []
                for _ in processes:
                    observed_ready.append(ready.get(timeout=30))
                self.assertEqual(len(observed_ready), len(processes))
                start.set()
                for process in processes:
                    process.join(timeout=30)
                self.assertTrue(all(not process.is_alive() for process in processes))
                self.assertEqual(
                    [process.exitcode for process in processes],
                    [0] * len(processes),
                )
                observed = [results.get(timeout=10) for _ in processes]
            finally:
                for process in processes:
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=10)
            status = ProviderAdmissionKernel(database).status(policy.provider_id)

        outcome_counts = {
            name: sum(item["status"] == name for item in observed)
            for name in ("granted", "busy", "error", "start_timeout")
        }
        self.assertEqual(
            outcome_counts,
            {"granted": 1, "busy": 7, "error": 0, "start_timeout": 0},
        )
        self.assertEqual(status.counts["granted"], 1)
        self.assertEqual(status.counts["waiting"], 7)


if __name__ == "__main__":
    unittest.main()
