from __future__ import annotations

import unittest

from macr_runtime.canonical import sha256_id
from macr_runtime.crossfile_verifier import (
    CrossFileCandidate,
    CrossFileVerificationRequest,
    CrossFileVerifier,
    VerifierStageObservation,
)
from macr_runtime.execution import AcceptanceState, MaterializationState, VerificationState
from macr_runtime.verification_graph import (
    CrossFileVerifierComposition,
    VerifierGraph,
    VerifierNode,
)


CONTRACT = "a" * 64
REPOSITORY = "b" * 64
PLAN = "c" * 64
INPUT = "d" * 64
CONFIG = "e" * 64


def composition() -> CrossFileVerifierComposition:
    individual = VerifierGraph.build(
        (
            VerifierNode(
                "individual-compile",
                "typed_compile",
                "1.0.0",
                (INPUT,),
                config_digest=CONFIG,
            ),
        )
    )
    compile_together = VerifierNode(
        "compile-together",
        "typed_compile",
        "1.0.0",
        (INPUT, CONTRACT),
        config_digest=CONFIG,
    )
    vectors = VerifierNode(
        "cross-file-vectors",
        "vector_suite",
        "1.0.0",
        (INPUT, CONTRACT),
        depends_on=("compile-together",),
        config_digest=CONFIG,
    )
    exact_diff = VerifierNode(
        "exact-diff-scope",
        "exact_diff",
        "1.0.0",
        (INPUT,),
        depends_on=("compile-together",),
        config_digest=CONFIG,
    )
    integration = VerifierGraph.build((vectors, exact_diff, compile_together))
    return CrossFileVerifierComposition(
        individual_graph=individual,
        integration_graph=integration,
        compiler_node_id="compile-together",
        vector_node_id="cross-file-vectors",
        diff_node_id="exact-diff-scope",
    )


def candidates() -> tuple[CrossFileCandidate, ...]:
    return (
        CrossFileCandidate(
            member_digest="1" * 64,
            target_key="2" * 64,
            candidate_sha256="3" * 64,
            shared_contract_digest=CONTRACT,
        ),
        CrossFileCandidate(
            member_digest="4" * 64,
            target_key="5" * 64,
            candidate_sha256="6" * 64,
            shared_contract_digest=CONTRACT,
        ),
    )


class FakeBackend:
    def __init__(
        self,
        *,
        individual_state: VerificationState = VerificationState.PASSED,
        integration_state: VerificationState = VerificationState.PASSED,
    ) -> None:
        self.individual_state = individual_state
        self.integration_state = integration_state
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def verify(
        self,
        graph,
        *,
        candidate_sha256s,
        shared_contract_digest,
        repository_id,
    ) -> VerifierStageObservation:
        candidate_sha256s = tuple(candidate_sha256s)
        self.calls.append((graph.graph_digest, candidate_sha256s))
        state = (
            self.individual_state
            if len(candidate_sha256s) == 1
            else self.integration_state
        )
        evidence = sha256_id(
            "fake_crossfile_evidence_v1",
            {
                "graph": graph.graph_digest,
                "candidates": list(candidate_sha256s),
                "contract": shared_contract_digest,
                "repository": repository_id,
                "state": state.value,
            },
        )
        return VerifierStageObservation(
            graph_digest=graph.graph_digest,
            state=state,
            evidence_digest=evidence,
        )


def request(items=None) -> CrossFileVerificationRequest:
    return CrossFileVerificationRequest(
        plan_digest=PLAN,
        repository_id=REPOSITORY,
        shared_contract_digest=CONTRACT,
        candidates=candidates() if items is None else items,
        verifier=composition(),
    )


class CrossFileVerifierTests(unittest.TestCase):
    def test_individual_green_does_not_equal_pair_green(self) -> None:
        backend = FakeBackend(integration_state=VerificationState.FAILED)
        result = CrossFileVerifier(backend).verify(request())

        self.assertEqual(result.individual_states, ("passed", "passed"))
        self.assertEqual(result.integration_state, "failed")
        self.assertIs(result.acceptance_state, AcceptanceState.PENDING)
        self.assertIs(result.materialization_state, MaterializationState.NONE)
        self.assertFalse(result.automatic_materialization)
        self.assertEqual(len(backend.calls), 3)

    def test_individual_failure_skips_integration_but_keeps_acceptance_pending(self) -> None:
        backend = FakeBackend(individual_state=VerificationState.FAILED)
        result = CrossFileVerifier(backend).verify(request())

        self.assertEqual(result.individual_states, ("failed", "failed"))
        self.assertEqual(result.integration_state, "not_run")
        self.assertIs(result.acceptance_state, AcceptanceState.PENDING)
        self.assertEqual(len(backend.calls), 2)

    def test_shared_contract_mismatch_fails_before_backend(self) -> None:
        backend = FakeBackend()
        mismatched = (
            candidates()[0],
            CrossFileCandidate(
                member_digest="4" * 64,
                target_key="5" * 64,
                candidate_sha256="6" * 64,
                shared_contract_digest="9" * 64,
            ),
        )
        with self.assertRaisesRegex(ValueError, "shared contract"):
            CrossFileVerifier(backend).verify(request(mismatched))
        self.assertEqual(backend.calls, [])

    def test_composition_requires_compiler_vectors_diff_and_dependencies(self) -> None:
        valid = composition()
        self.assertRegex(valid.composition_digest, r"^[0-9a-f]{64}$")
        with self.assertRaisesRegex(ValueError, "diff"):
            CrossFileVerifierComposition(
                individual_graph=valid.individual_graph,
                integration_graph=valid.integration_graph,
                compiler_node_id="compile-together",
                vector_node_id="cross-file-vectors",
                diff_node_id="missing-diff",
            )
        unrelated = VerifierGraph.build(
            (
                VerifierNode(
                    "compile-together",
                    "typed_compile",
                    "1.0.0",
                    (INPUT,),
                ),
                VerifierNode(
                    "cross-file-vectors",
                    "vector_suite",
                    "1.0.0",
                    (INPUT,),
                ),
                VerifierNode(
                    "exact-diff-scope",
                    "exact_diff",
                    "1.0.0",
                    (INPUT,),
                ),
            )
        )
        with self.assertRaisesRegex(ValueError, "depend"):
            CrossFileVerifierComposition(
                individual_graph=valid.individual_graph,
                integration_graph=unrelated,
                compiler_node_id="compile-together",
                vector_node_id="cross-file-vectors",
                diff_node_id="exact-diff-scope",
            )


if __name__ == "__main__":
    unittest.main()
