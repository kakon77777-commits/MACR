from __future__ import annotations

import unittest
from dataclasses import replace

from macr_runtime.contracts import (
    EolNormalization,
    EolScope,
    ImportMode,
    RequiredImport,
    TaskContract,
    TaskPolicyClauses,
)
from macr_runtime.errors import TaskContradictionError
from macr_runtime.task_preflight import validate_task_consistency


def base_task() -> TaskContract:
    return TaskContract(
        task_id="preflight-test",
        goal="Use only the structured clauses in this test.",
        task_type="testing",
    )


class TaskPreflightTests(unittest.TestCase):
    def test_import_none_conflicts_with_required_type_import(self) -> None:
        task = replace(
            base_task(),
            policy_clauses=TaskPolicyClauses(
                import_mode=ImportMode.NONE,
                required_imports=(
                    RequiredImport("document-format-contract", "type_only"),
                ),
            ),
        )

        with self.assertRaisesRegex(
            TaskContradictionError,
            "imports_none_but_required",
        ):
            validate_task_consistency(task)

    def test_type_only_mode_conflicts_with_runtime_import(self) -> None:
        task = replace(
            base_task(),
            policy_clauses=TaskPolicyClauses(
                import_mode=ImportMode.TYPE_ONLY,
                required_imports=(RequiredImport("runtime-module", "runtime"),),
            ),
        )

        with self.assertRaisesRegex(
            TaskContradictionError,
            "type_only_mode_but_runtime_required",
        ):
            validate_task_consistency(task)

    def test_eol_out_of_scope_conflicts_with_normalization(self) -> None:
        task = replace(
            base_task(),
            policy_clauses=TaskPolicyClauses(
                eol_scope=EolScope.OUT_OF_SCOPE,
                eol_normalization=EolNormalization.LF,
            ),
        )

        with self.assertRaisesRegex(
            TaskContradictionError,
            "eol_out_of_scope_but_normalized",
        ):
            validate_task_consistency(task)

    def test_corrected_structured_control_passes_and_round_trips(self) -> None:
        task = replace(
            base_task(),
            policy_clauses=TaskPolicyClauses(
                import_mode=ImportMode.TYPE_ONLY,
                required_imports=(
                    RequiredImport("document-format-contract", "type_only"),
                ),
                eol_scope=EolScope.IN_SCOPE,
                eol_normalization=EolNormalization.LF,
            ),
        )

        self.assertEqual(validate_task_consistency(task), ())
        self.assertEqual(TaskContract.from_dict(task.to_dict()), task)

    def test_goal_prose_is_not_treated_as_a_proven_contradiction(self) -> None:
        task = TaskContract(
            task_id="prose-not-proof",
            goal="Import nothing but also import one module.",
            task_type="testing",
        )

        self.assertEqual(validate_task_consistency(task), ())

    def test_required_import_shape_fails_closed(self) -> None:
        for module, kind in (("", "type_only"), ("module", "other")):
            with self.subTest(module=module, kind=kind):
                with self.assertRaises(ValueError):
                    RequiredImport(module, kind)


if __name__ == "__main__":
    unittest.main()
