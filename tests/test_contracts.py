import unittest

from macr_runtime.contracts import (
    PrivacyLevel,
    ReturnContract,
    TaskConstraints,
    TaskContract,
    VerificationSpec,
    WorkspaceSpec,
)


class TaskContractTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        task = TaskContract(
            task_id="task-001",
            goal="repair failing tests",
            task_type="coding",
            workspace=WorkspaceSpec(repo="current", write_scope=("src/**", "tests/**")),
            constraints=TaskConstraints(
                max_cost_usd=1.0,
                max_latency_s=120,
                internet=True,
                privacy=PrivacyLevel.INTERNAL_APPROVED,
            ),
            required_capabilities=("code_read", "test_reasoning"),
            verification=VerificationSpec(required=True, methods=("tests", "diff_review")),
        )
        self.assertEqual(TaskContract.from_dict(task.to_dict()), task)

    def test_rejects_parent_write_scope(self) -> None:
        with self.assertRaisesRegex(ValueError, "may not contain"):
            WorkspaceSpec(write_scope=("../outside",))

    def test_rejects_absolute_write_scope(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be relative"):
            WorkspaceSpec(write_scope=("/absolute",))

    def test_rejects_duplicate_capability(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicates"):
            TaskContract(
                task_id="task-duplicate",
                goal="test",
                task_type="testing",
                required_capabilities=("code_read", "code_read"),
            )

    def test_rejects_negative_budget(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-negative"):
            TaskConstraints(max_cost_usd=-1)

    def test_rejects_string_boolean_in_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be boolean"):
            TaskContract.from_dict(
                {
                    "task_id": "task-string-bool",
                    "goal": "reject ambiguous JSON",
                    "task_type": "validation",
                    "constraints": {"internet": "false"},
                }
            )

    def test_rejects_string_return_flag(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be boolean"):
            ReturnContract.from_dict({"patch": "false"})

    def test_rejects_string_where_array_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be an array"):
            TaskContract.from_dict(
                {
                    "task_id": "task-string-array",
                    "goal": "reject ambiguous JSON",
                    "task_type": "validation",
                    "required_capabilities": "code_read",
                }
            )

    def test_max_output_tokens_round_trip(self) -> None:
        task = TaskContract.from_dict(
            {
                "task_id": "output-bound-001",
                "goal": "bound output",
                "task_type": "testing",
                "constraints": {"max_output_tokens": 64},
            }
        )
        self.assertEqual(task.constraints.max_output_tokens, 64)
        self.assertEqual(task.to_dict()["constraints"]["max_output_tokens"], 64)

    def test_rejects_invalid_output_token_bounds(self) -> None:
        for value in (True, "64", 0, 16385):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "max_output_tokens"):
                    TaskConstraints(max_output_tokens=value)


if __name__ == "__main__":
    unittest.main()
