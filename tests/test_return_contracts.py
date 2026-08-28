from __future__ import annotations

import unittest
from dataclasses import replace

from macr_runtime.contracts import (
    ReturnContract,
    ReturnFormat,
    TaskContract,
)
from macr_runtime.execution import ReturnContractState
from macr_runtime.return_contracts import (
    compile_worker_instruction,
    validate_return_contract,
)


def base_task(goal: str = "Return a bounded candidate") -> TaskContract:
    return TaskContract(
        task_id="return-contract-test",
        goal=goal,
        task_type="testing",
        required_capabilities=("text_generation",),
    )


class ReturnContractCompilerTests(unittest.TestCase):
    def test_plain_source_contract_controls_instruction_and_rejects_fences(self) -> None:
        task = replace(
            base_task(),
            return_contract=ReturnContract(
                summary=False,
                patch=False,
                evidence=False,
                format=ReturnFormat.PLAIN_SOURCE,
                language="typescript",
            ),
        )

        instruction = compile_worker_instruction(task)
        invalid = validate_return_contract(
            task,
            "```typescript\nexport {};\n```\nEvidence: compiled",
        )
        prose_wrappers = (
            "Here is the source:\nexport {};",
            "Here's the TypeScript:\nexport {};",
            "Below is the code:\nexport {};",
            "The following source implements it:\nexport {};",
            "Source:\nexport {};",
            "Code:\nexport {};",
        )
        valid = validate_return_contract(task, "export {};\n")
        comment_control = validate_return_contract(
            task,
            "// bounded source\nexport {};\n",
        )

        self.assertIn("Return only plain TypeScript source", instruction)
        self.assertNotIn("evidence and warnings", instruction)
        self.assertEqual(invalid.state, ReturnContractState.INVALID)
        self.assertEqual(
            invalid.reason_code,
            "plain_source_has_fence_or_prose",
        )
        for answer in prose_wrappers:
            with self.subTest(answer=answer):
                validation = validate_return_contract(task, answer)
                self.assertEqual(validation.state, ReturnContractState.INVALID)
                self.assertEqual(
                    validation.reason_code,
                    "plain_source_has_fence_or_prose",
                )
        self.assertEqual(valid.state, ReturnContractState.VALID)
        self.assertEqual(comment_control.state, ReturnContractState.VALID)

    def test_exact_text_no_longer_depends_on_goal_prefix(self) -> None:
        task = replace(
            base_task(goal="Use any wording in this goal."),
            return_contract=ReturnContract(
                summary=False,
                patch=False,
                evidence=False,
                format=ReturnFormat.EXACT_TEXT,
                exact_text="MACR_OK",
            ),
        )

        instruction = compile_worker_instruction(task)

        self.assertIn("MACR_OK", instruction)
        self.assertEqual(
            validate_return_contract(task, "MACR_OK").state,
            ReturnContractState.VALID,
        )
        self.assertEqual(
            validate_return_contract(task, "MACR_OK\n").state,
            ReturnContractState.INVALID,
        )

    def test_plain_source_uses_dynamic_language_heading_without_rejecting_code(self) -> None:
        cases = (
            ("python", "Python:\nprint('ok')"),
            ("rust", "Rust:\nfn main() {}"),
            ("typescript", "TypeScript source:\nexport {};"),
        )
        for language, answer in cases:
            with self.subTest(language=language):
                task = replace(
                    base_task(),
                    return_contract=ReturnContract(
                        summary=False,
                        patch=False,
                        evidence=False,
                        format=ReturnFormat.PLAIN_SOURCE,
                        language=language,
                    ),
                )
                self.assertEqual(
                    validate_return_contract(task, answer).state,
                    ReturnContractState.INVALID,
                )

        python_task = replace(
            base_task(),
            return_contract=ReturnContract(
                summary=False,
                patch=False,
                evidence=False,
                format=ReturnFormat.PLAIN_SOURCE,
                language="python",
            ),
        )
        self.assertEqual(
            validate_return_contract(
                python_task,
                "code: str = 'ok'\nprint(code)\n",
            ).state,
            ReturnContractState.VALID,
        )

    def test_json_object_rejects_duplicate_keys_and_non_objects(self) -> None:
        task = replace(
            base_task(),
            return_contract=ReturnContract(
                summary=False,
                patch=False,
                evidence=False,
                format=ReturnFormat.JSON_OBJECT,
            ),
        )

        valid = validate_return_contract(task, '{"one":1}')
        whitespace_and_order_control = validate_return_contract(
            task,
            '{\n  "two": 2,\n  "one": 1\n}\n',
        )
        duplicate = validate_return_contract(task, '{"one":1,"one":2}')
        array = validate_return_contract(task, "[]")

        self.assertEqual(valid.state, ReturnContractState.VALID)
        self.assertEqual(
            whitespace_and_order_control.state,
            ReturnContractState.VALID,
        )
        self.assertEqual(duplicate.reason_code, "json_duplicate_key")
        self.assertEqual(array.reason_code, "json_not_object")

    def test_default_free_text_preserves_shared_worker_instruction(self) -> None:
        from macr_runtime.providers.common import BOUNDED_WORKER_INSTRUCTION

        self.assertEqual(
            compile_worker_instruction(base_task()),
            BOUNDED_WORKER_INSTRUCTION,
        )
        self.assertEqual(
            validate_return_contract(base_task(), "candidate").state,
            ReturnContractState.VALID,
        )
        self.assertEqual(
            validate_return_contract(base_task(), "  ").reason_code,
            "answer_blank",
        )


if __name__ == "__main__":
    unittest.main()
