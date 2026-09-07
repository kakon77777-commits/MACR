import unittest

from macr_runtime.contracts import (
    DelegationClass,
    PrivacyLevel,
    ReturnContract,
    ReturnFormat,
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

    def test_delegable_defaults_false_and_round_trips_true(self) -> None:
        default_task = TaskContract(
            task_id="delegable-default",
            goal="remain local by default",
            task_type="testing",
        )
        delegated_task = TaskContract.from_dict(
            {
                "task_id": "delegable-enabled",
                "goal": "allow explicit external delegation",
                "task_type": "delegated_routine",
                "delegable": True,
            }
        )

        self.assertFalse(default_task.delegable)
        self.assertFalse(default_task.to_dict()["delegable"])
        self.assertTrue(delegated_task.delegable)
        self.assertTrue(delegated_task.to_dict()["delegable"])

    def test_rejects_string_delegable_flag(self) -> None:
        with self.assertRaisesRegex(ValueError, "delegable must be boolean"):
            TaskContract.from_dict(
                {
                    "task_id": "delegable-string",
                    "goal": "reject ambiguous delegation",
                    "task_type": "delegated_routine",
                    "delegable": "true",
                }
            )

    def test_existing_positional_workspace_argument_remains_compatible(self) -> None:
        workspace = WorkspaceSpec(repo="current", write_scope=("src/**",))

        task = TaskContract(
            "positional-compatible",
            "preserve the v0.3 constructor order",
            "testing",
            workspace,
        )

        self.assertEqual(task.workspace, workspace)
        self.assertFalse(task.delegable)

    def test_delegation_class_and_approval_digest_default_closed_and_round_trip(self) -> None:
        digest = "a" * 64
        default_task = TaskContract(
            task_id="delegation-defaults",
            goal="remain closed",
            task_type="testing",
        )
        approved_task = TaskContract.from_dict(
            {
                "task_id": "delegation-approved",
                "goal": "approved routine bytes",
                "task_type": "delegated_routine",
                "delegable": True,
                "delegation_class": "non_sensitive_routine",
                "delegation_approval_sha256": digest,
            }
        )

        self.assertEqual(default_task.delegation_class, DelegationClass.NONE)
        self.assertIsNone(default_task.delegation_approval_sha256)
        self.assertEqual(
            approved_task.delegation_class,
            DelegationClass.NON_SENSITIVE_ROUTINE,
        )
        self.assertEqual(approved_task.delegation_approval_sha256, digest)
        self.assertEqual(
            TaskContract.from_dict(approved_task.to_dict()),
            approved_task,
        )

    def test_invalid_delegation_approval_digest_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "delegation_approval_sha256"):
            TaskContract.from_dict(
                {
                    "task_id": "delegation-invalid-digest",
                    "goal": "reject malformed approval",
                    "task_type": "delegated_routine",
                    "delegation_approval_sha256": "not-a-sha256",
                }
            )

    def test_rejects_string_return_flag(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be boolean"):
            ReturnContract.from_dict({"patch": "false"})

    def test_structured_return_contract_round_trips(self) -> None:
        contract = ReturnContract(
            summary=False,
            patch=False,
            evidence=False,
            format=ReturnFormat.PLAIN_SOURCE,
            language="typescript",
        )

        self.assertEqual(
            ReturnContract.from_dict(contract.to_dict()),
            contract,
        )

    def test_return_format_fields_fail_closed(self) -> None:
        invalid = (
            {"format": "exact_text"},
            {"format": "exact_text", "exact_text": "x"},
            {"format": "free_text", "exact_text": "unexpected"},
            {"format": "plain_source"},
            {"format": "plain_source", "language": "typescript"},
            {"format": "json_object", "language": "json"},
        )
        for document in invalid:
            with self.subTest(document=document):
                with self.assertRaises(ValueError):
                    ReturnContract.from_dict(document)

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

    def test_external_token_defaults_context_and_ceiling_round_trip(self) -> None:
        defaults = TaskConstraints()
        self.assertEqual(defaults.max_output_tokens, 16_384)
        self.assertIsNone(defaults.max_context_tokens)
        expanded = TaskConstraints(
            max_output_tokens=65_536,
            max_context_tokens=512_000,
        )
        self.assertEqual(expanded.max_output_tokens, 65_536)
        self.assertEqual(expanded.max_context_tokens, 512_000)
        self.assertEqual(
            TaskConstraints.from_dict(expanded.to_dict()),
            expanded,
        )
        for value in (True, 0, -1, 1_048_577):
            with self.subTest(context=value), self.assertRaisesRegex(
                ValueError,
                "max_context_tokens",
            ):
                TaskConstraints(max_context_tokens=value)

    def test_rejects_invalid_output_token_bounds(self) -> None:
        for value in (True, "64", 0, 65_537):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "max_output_tokens"):
                    TaskConstraints(max_output_tokens=value)


if __name__ == "__main__":
    unittest.main()
