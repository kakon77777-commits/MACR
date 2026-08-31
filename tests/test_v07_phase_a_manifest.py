from __future__ import annotations

import importlib
import json
import unittest
from importlib.resources import files
from pathlib import Path


class V07PhaseAManifestTests(unittest.TestCase):
    def load_manifest(self) -> dict[str, object]:
        path = Path(__file__).parent / "gates/v07_phase_a_contract_manifest.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_manifest_has_exact_required_id_families(self) -> None:
        manifest = self.load_manifest()
        observed = {item["id"] for item in manifest["required"]}
        expected = (
            {f"AR-C{i:02d}" for i in range(1, 9)}
            | {f"ASE-C{i:02d}" for i in range(1, 11)}
            | {f"OBS-C{i:02d}" for i in range(1, 9)}
            | {f"ACT-C{i:02d}" for i in range(1, 13)}
            | {f"TMP-C{i:02d}" for i in range(1, 12)}
            | {f"NC-A{i:02d}" for i in range(1, 11)}
            | {f"SEM-X{i:02d}" for i in range(1, 7)}
            | {f"MEM-X{i:02d}" for i in range(1, 4)}
        )

        self.assertEqual(manifest["schema"], "macr-v07-phase-a-test-manifest/v1")
        self.assertEqual(manifest["phase"], "A")
        self.assertEqual(observed, expected)
        self.assertEqual(len(observed), 68)

    def test_manifest_ids_and_test_bindings_are_unique(self) -> None:
        required = self.load_manifest()["required"]
        ids = [item["id"] for item in required]
        tests = [item["test"] for item in required]

        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(tests), len(set(tests)))
        self.assertTrue(all(item["severity"] in {"S0", "S1"} for item in required))

    def test_every_manifest_test_exists_and_is_not_skipped(self) -> None:
        for entry in self.load_manifest()["required"]:
            module_name, class_name, method_name = entry["test"].rsplit(".", 2)
            module = importlib.import_module(module_name)
            case_type = getattr(module, class_name)
            method = getattr(case_type, method_name)
            with self.subTest(test_id=entry["id"], test=entry["test"]):
                self.assertTrue(callable(method))
                self.assertFalse(getattr(case_type, "__unittest_skip__", False))
                self.assertFalse(getattr(method, "__unittest_skip__", False))

    def test_all_phase_a_schemas_have_resolved_internal_refs_and_closed_objects(self) -> None:
        schema_resources = (
            ("macr_runtime.agent", "schemas/agent-contracts-v1.schema.json"),
            ("macr_runtime.semantic", "schemas/semantic-contracts-v1.schema.json"),
            ("macr_runtime.observation", "schemas/observation-contracts-v1.schema.json"),
            ("macr_runtime.action", "schemas/action-contracts-v1.schema.json"),
            ("macr_runtime.temporal", "schemas/temporal-contracts-v1.schema.json"),
        )
        schema_ids: set[str] = set()

        for package, resource in schema_resources:
            schema = json.loads(
                files(package).joinpath(resource).read_text(encoding="utf-8")
            )
            defs = schema["$defs"]
            refs = self.collect_internal_refs(schema)
            with self.subTest(schema=schema["$id"]):
                self.assertEqual(
                    schema["$schema"],
                    "https://json-schema.org/draft/2020-12/schema",
                )
                self.assertNotIn(schema["$id"], schema_ids)
                self.assertEqual(refs - set(defs), set())
                for name, definition in defs.items():
                    if definition.get("type") == "object":
                        self.assertIs(
                            definition.get("additionalProperties"),
                            False,
                            msg=f"{schema['$id']} {name} is not closed",
                        )
            schema_ids.add(schema["$id"])

    @classmethod
    def collect_internal_refs(cls, value: object) -> set[str]:
        if isinstance(value, dict):
            refs = set()
            ref = value.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                refs.add(ref.removeprefix("#/$defs/"))
            for item in value.values():
                refs.update(cls.collect_internal_refs(item))
            return refs
        if isinstance(value, list):
            refs = set()
            for item in value:
                refs.update(cls.collect_internal_refs(item))
            return refs
        return set()


if __name__ == "__main__":
    unittest.main()
