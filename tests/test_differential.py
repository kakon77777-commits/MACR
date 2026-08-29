from __future__ import annotations

import contextlib
import copy
import dataclasses
import io
import json
import unittest
from pathlib import Path

from macr_runtime.canonical import sha256_id
from macr_runtime.cli import _probe_plan, _probe_replay, build_parser
from macr_runtime.differential import (
    DifferentialCandidateResult,
    DifferentialCostPolicy,
    DifferentialProbePack,
    DifferentialRouteCandidate,
    DifferentialRunManifest,
    compare_differential_results,
)
from macr_runtime.execution import AcceptanceState, VerificationState
from macr_runtime.verification_graph import VerifierGraph, VerifierNode

from tests.support import d_drive_tempdir


ROOT_INPUT = "a" * 64
CONFIG = "b" * 64
ROOT = Path(__file__).resolve().parents[1]


def graph() -> VerifierGraph:
    return VerifierGraph.build(
        (
            VerifierNode(
                "exact-output",
                "sha256_exact",
                "1.0.0",
                (ROOT_INPUT,),
                config_digest=CONFIG,
            ),
        )
    )


def pack() -> DifferentialProbePack:
    verifier = graph()
    return DifferentialProbePack.from_dict(
        {
            "schema_version": 1,
            "pack_id": "v06-test-pack",
            "version": "1.0.0",
            "cases": [
                {
                    "case_id": "exact-a",
                    "task_digest": "1" * 64,
                    "verifier_graph_digest": verifier.graph_digest,
                    "context_class": "public_text",
                    "cost_ceiling_usd": 0.01,
                },
                {
                    "case_id": "exact-b",
                    "task_digest": "2" * 64,
                    "verifier_graph_digest": verifier.graph_digest,
                    "context_class": "public_text",
                    "cost_ceiling_usd": 0.01,
                },
            ],
        }
    )


def routes() -> tuple[DifferentialRouteCandidate, ...]:
    return tuple(
        DifferentialRouteCandidate(
            qualification_key=format(index + 3, "x") * 64,
            route_proposal_digest=format(index + 6, "x") * 64,
            route_id=format(index + 9, "x") * 64,
            cost_ceiling_usd=0.005,
        )
        for index in range(3)
    )


def policy() -> DifferentialCostPolicy:
    return DifferentialCostPolicy(
        per_candidate_cost_ceiling_usd=0.01,
        aggregate_cost_ceiling_usd=0.05,
        minimum_candidate_routes=3,
    )


def manifest(route_items=None) -> DifferentialRunManifest:
    return DifferentialRunManifest.build(
        pack(),
        routes() if route_items is None else route_items,
        graph(),
        policy(),
    )


def results(run: DifferentialRunManifest) -> tuple[DifferentialCandidateResult, ...]:
    return tuple(
        DifferentialCandidateResult(
            manifest_digest=run.manifest_digest,
            case_id=member.case_id,
            candidate_id=member.candidate_id,
            candidate_sha256=sha256_id(
                "differential_test_candidate_v1",
                {"member_digest": member.member_digest},
            ),
            verifier_state=VerificationState.PASSED,
            verifier_evidence_digest=sha256_id(
                "differential_test_evidence_v1",
                {"member_digest": member.member_digest},
            ),
            observed_cost_usd=0.001,
        )
        for member in run.members
    )


class DifferentialTests(unittest.TestCase):
    def test_manifest_is_deterministic_and_requires_three_exact_routes(self) -> None:
        first = manifest(routes())
        second = manifest(tuple(reversed(routes())))

        self.assertEqual(first, second)
        self.assertFalse(first.authority_issued)
        self.assertFalse(first.network_activity)
        self.assertFalse(first.execution_performed)
        self.assertEqual(len(first.members), len(pack().cases) * 3)
        with self.assertRaisesRegex(ValueError, "candidate route"):
            manifest(routes()[:2])

    def test_comparison_uses_candidate_ids_not_model_labels_and_replays_stably(self) -> None:
        run = manifest()
        observations = results(run)
        first = compare_differential_results(run, observations)
        second = compare_differential_results(run, tuple(reversed(observations)))

        self.assertEqual(first.replay_digest, second.replay_digest)
        self.assertEqual(first.public_rows, second.public_rows)
        self.assertTrue(first.public_rows)
        self.assertIsNone(first.public_rows[0].model_label)
        self.assertTrue(
            all(row.candidate_id for row in first.public_rows)
        )
        self.assertIs(first.acceptance_state, AcceptanceState.PENDING)
        self.assertFalse(first.execution_performed)

    def test_missing_duplicate_extra_and_over_cost_results_fail_closed(self) -> None:
        run = manifest()
        observations = results(run)
        cases = (
            ("exact", observations[:-1]),
            ("duplicate", observations + (observations[0],)),
        )
        for message, values in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    compare_differential_results(run, values)
        over = dataclasses_replace(
            observations[0],
            observed_cost_usd=0.006,
        )
        with self.assertRaisesRegex(ValueError, "cost"):
            compare_differential_results(
                run,
                (over,) + observations[1:],
            )

    def test_probe_pack_and_route_cost_policy_are_exact(self) -> None:
        run = manifest()
        tampered = copy.deepcopy(pack().to_dict())
        tampered["cases"][0]["task_digest"] = "f" * 64
        changed = DifferentialProbePack.from_dict(tampered)
        self.assertNotEqual(changed.pack_digest, pack().pack_digest)

        costly = (dataclasses_replace(routes()[0], cost_ceiling_usd=0.02),) + routes()[1:]
        with self.assertRaisesRegex(ValueError, "cost"):
            manifest(costly)
        self.assertEqual(
            run.verifier_graph_digest,
            graph().graph_digest,
        )
        example = DifferentialProbePack.from_dict(
            json.loads(
                (ROOT / "examples" / "probes" / "v06-canonical-probe-pack.json")
                .read_text(encoding="utf-8")
            )
        )
        self.assertEqual(len(example.cases), 3)

    def test_manifest_rejects_rehashed_internal_policy_mismatch(self) -> None:
        run = manifest()
        tampered = run.to_dict()
        tampered["aggregate_cost_ceiling_usd"] = 0.06
        canonical = {
            key: value for key, value in tampered.items()
            if key != "manifest_digest"
        }
        tampered["manifest_digest"] = sha256_id(
            "differential_run_manifest_v1",
            canonical,
        )
        with self.assertRaisesRegex(ValueError, "cost policy"):
            DifferentialRunManifest.from_dict(tampered)

        comparison = compare_differential_results(run, results(run))
        with self.assertRaisesRegex(ValueError, "model label"):
            dataclasses.replace(
                comparison.public_rows[0],
                model_label="revealed-model",
            )

    def test_cli_plan_and_replay_are_manifest_only_and_offline(self) -> None:
        run = manifest()
        plan_input = {
            "probe_pack": pack().to_dict(),
            "route_candidates": [item.to_dict() for item in routes()],
            "verifier_graph": graph().to_dict(),
            "cost_policy": policy().to_dict(),
        }
        with d_drive_tempdir() as temp:
            plan_path = temp / "probe-plan.json"
            plan_path.write_text(json.dumps(plan_input), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = _probe_plan(str(plan_path))
            planned = json.loads(output.getvalue())
            self.assertEqual(status, 0)
            self.assertEqual(planned["status"], "differential_manifest_ready")
            self.assertFalse(planned["network_activity"])
            self.assertFalse(planned["dispatch_performed"])

            manifest_path = temp / "manifest.json"
            manifest_path.write_text(
                json.dumps(run.to_dict()),
                encoding="utf-8",
            )
            result_path = temp / "results.json"
            result_path.write_text(
                json.dumps([item.to_dict() for item in results(run)]),
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                replay_status = _probe_replay(
                    str(manifest_path),
                    str(result_path),
                )
            replayed = json.loads(output.getvalue())

        self.assertEqual(replay_status, 0)
        self.assertEqual(replayed["status"], "differential_replay_complete")
        self.assertFalse(replayed["network_activity"])
        self.assertFalse(replayed["dispatch_performed"])
        self.assertIn("probe-plan", build_parser()._subparsers._group_actions[0].choices)
        self.assertIn("probe-replay", build_parser()._subparsers._group_actions[0].choices)


def dataclasses_replace(value, **changes):
    return dataclasses.replace(value, **changes)


if __name__ == "__main__":
    unittest.main()
