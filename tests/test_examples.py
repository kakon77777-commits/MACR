import json
import unittest
from pathlib import Path

from macr_runtime.contracts import PrivacyLevel, TaskContract


ROOT = Path(__file__).resolve().parents[1]


def load_example(name: str) -> TaskContract:
    document = json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))
    return TaskContract.from_dict(document)


class ExampleContractTests(unittest.TestCase):
    def test_grok_example_is_public_bounded_cloud_task(self) -> None:
        task = load_example("grok-task.example.json")
        self.assertEqual(task.goal, "Return exactly: MACR_GROK_46_OK")
        self.assertTrue(task.constraints.internet)
        self.assertEqual(task.constraints.privacy, PrivacyLevel.PUBLIC)
        self.assertEqual(task.constraints.max_cost_usd, 0.01)
        self.assertEqual(task.constraints.max_output_tokens, 64)
        self.assertFalse(task.return_contract.summary)
        self.assertFalse(task.return_contract.evidence)

    def test_ollama_example_is_zero_cost_local_only_task(self) -> None:
        task = load_example("ollama-task.example.json")
        self.assertEqual(task.goal, "Return exactly: MACR_OLLAMA_OK")
        self.assertFalse(task.constraints.internet)
        self.assertEqual(task.constraints.privacy, PrivacyLevel.LOCAL_ONLY)
        self.assertEqual(task.constraints.max_cost_usd, 0)
        self.assertEqual(task.constraints.max_output_tokens, 64)
        self.assertFalse(task.return_contract.summary)
        self.assertFalse(task.return_contract.evidence)

    def test_google_gemini_example_is_public_bounded_cloud_task(self) -> None:
        task = load_example("google-gemini-task.example.json")
        self.assertEqual(task.goal, "Return exactly: MACR_GOOGLE_GEMINI_OK")
        self.assertTrue(task.constraints.internet)
        self.assertEqual(task.constraints.privacy, PrivacyLevel.PUBLIC)
        self.assertGreater(task.constraints.max_cost_usd, 0)
        self.assertEqual(task.constraints.max_output_tokens, 256)
        self.assertEqual(task.required_capabilities, ("text_generation",))
        self.assertFalse(task.return_contract.summary)
        self.assertFalse(task.return_contract.evidence)

    def test_google_image_example_requests_one_public_image(self) -> None:
        task = load_example("google-image-task.example.json")
        self.assertTrue(task.constraints.internet)
        self.assertEqual(task.constraints.privacy, PrivacyLevel.PUBLIC)
        self.assertEqual(task.constraints.max_cost_usd, 1.0)
        self.assertEqual(task.constraints.max_output_tokens, 2048)
        self.assertEqual(task.required_capabilities, ("image_generation",))

    def test_glm_example_requires_explicit_public_delegation(self) -> None:
        task = load_example("glm-worker-task.example.json")

        self.assertEqual(task.goal, "Return exactly: MACR_GLM_OK")
        self.assertTrue(task.delegable)
        self.assertTrue(task.constraints.internet)
        self.assertEqual(task.constraints.privacy, PrivacyLevel.PUBLIC)
        self.assertEqual(task.constraints.max_cost_usd, 0.01)
        self.assertEqual(task.constraints.max_output_tokens, 512)
        self.assertEqual(task.workspace.write_scope, ())
        self.assertEqual(task.inputs, ())
        self.assertEqual(task.required_capabilities, ("text_generation",))
        self.assertTrue(task.verification.required)
        self.assertFalse(task.return_contract.patch)


if __name__ == "__main__":
    unittest.main()
