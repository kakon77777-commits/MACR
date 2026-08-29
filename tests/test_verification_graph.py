from __future__ import annotations

import re
import unittest

from macr_runtime.canonical import sha256_id
from macr_runtime.verification_graph import VerifierGraph, VerifierNode


SHA256 = re.compile(r"^[0-9a-f]{64}$")
INPUT_A = sha256_id("verifier_input_v1", {"artifact": "candidate"})
INPUT_B = sha256_id("verifier_input_v1", {"artifact": "contract"})
CONFIG = sha256_id("verifier_config_v1", {"strict": True})


def nodes():
    parse = VerifierNode(
        "parse",
        "python_ast",
        "3.14.0",
        (INPUT_A,),
        config_digest=CONFIG,
    )
    tests = VerifierNode(
        "unit-tests",
        "python_unittest",
        "3.14.0",
        (INPUT_A, INPUT_B),
        depends_on=("parse",),
        config_digest=CONFIG,
    )
    exact = VerifierNode(
        "byte-contract",
        "sha256_exact",
        "1.0.0",
        (INPUT_A,),
        depends_on=("unit-tests",),
        config_digest=CONFIG,
    )
    return parse, tests, exact


class VerificationGraphTests(unittest.TestCase):
    def test_graph_is_topologically_canonical_independent_of_input_order(self) -> None:
        parse, tests, exact = nodes()
        first = VerifierGraph.build((exact, parse, tests))
        second = VerifierGraph.build((tests, exact, parse))

        self.assertRegex(first.graph_digest, SHA256)
        self.assertEqual(first, second)
        self.assertEqual(
            [item.node_id for item in first.nodes],
            ["parse", "unit-tests", "byte-contract"],
        )

    def test_graph_rejects_cycles_missing_dependencies_and_duplicate_nodes(self) -> None:
        cyclic = (
            VerifierNode("a", "exact", "1", (INPUT_A,), depends_on=("b",)),
            VerifierNode("b", "exact", "1", (INPUT_A,), depends_on=("a",)),
        )
        with self.assertRaisesRegex(ValueError, "cycle"):
            VerifierGraph.build(cyclic)
        with self.assertRaisesRegex(ValueError, "missing dependency"):
            VerifierGraph.build(
                (
                    VerifierNode(
                        "a",
                        "exact",
                        "1",
                        (INPUT_A,),
                        depends_on=("missing",),
                    ),
                )
            )
        parse, _, _ = nodes()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            VerifierGraph.build((parse, parse))

    def test_node_rejects_unversioned_tools_and_invalid_digests(self) -> None:
        with self.assertRaisesRegex(ValueError, "version"):
            VerifierNode("compile", "python", "", (INPUT_A,))
        with self.assertRaisesRegex(ValueError, "input_digests"):
            VerifierNode("compile", "python", "1", ("A" * 64,))

    def test_graph_digest_changes_with_tool_version_dependency_or_config(self) -> None:
        parse, tests, exact = nodes()
        base = VerifierGraph.build((parse, tests, exact))
        changed = (
            VerifierGraph.build(
                (
                    VerifierNode(
                        "parse",
                        "python_ast",
                        "3.15.0",
                        (INPUT_A,),
                        config_digest=CONFIG,
                    ),
                    tests,
                    exact,
                )
            ),
            VerifierGraph.build(
                (
                    parse,
                    VerifierNode(
                        "unit-tests",
                        "python_unittest",
                        "3.14.0",
                        (INPUT_A, INPUT_B),
                        config_digest=CONFIG,
                    ),
                    exact,
                )
            ),
        )
        for graph in changed:
            self.assertNotEqual(base.graph_digest, graph.graph_digest)


if __name__ == "__main__":
    unittest.main()
