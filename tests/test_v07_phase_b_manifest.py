from __future__ import annotations

import ast
import importlib
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

import macr_runtime.agent as agent_package


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_MANIFEST = ROOT / "tests/gates/v07_phase_b_contract_manifest.json"
ARCHITECTURE_MANIFEST = ROOT / "tests/gates/v07_phase_b_architecture_manifest.json"


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_import(module_name: str, node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""
    package = module_name.split(".")[:-1]
    keep = len(package) - (node.level - 1)
    base = package[:keep]
    if node.module:
        base.extend(node.module.split("."))
    return ".".join(base)


class V07PhaseBManifestTests(unittest.TestCase):
    def test_contract_manifest_families_ids_and_bindings_are_unique(self) -> None:
        manifest = load_json(CONTRACT_MANIFEST)
        required = manifest["required"]
        ids = [entry["id"] for entry in required]
        tests = [entry["test"] for entry in required]
        families = {identifier.rsplit("-", 1)[0] for identifier in ids}

        self.assertEqual(manifest["schema"], "macr-v07-phase-b-test-manifest/v1")
        self.assertEqual(manifest["phase"], "B")
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(tests), len(set(tests)))
        self.assertEqual(
            families,
            {
                "PB-INIT",
                "PB-STATE",
                "PB-DB",
                "PB-EVT",
                "PB-STORE",
                "PB-SVC",
                "PB-OWN",
                "PB-RBLD",
                "PB-MP",
                "PB-ARCH",
            },
        )
        self.assertTrue(all(entry["severity"] in {"S0", "S1"} for entry in required))

    def test_initial_state_mismatch_witnesses_are_independently_bound(self) -> None:
        required = load_json(CONTRACT_MANIFEST)["required"]
        bindings = {
            entry["id"]: entry["test"]
            for entry in required
            if entry["id"] in {"PB-INIT-02", "PB-INIT-03", "PB-INIT-04"}
        }

        self.assertEqual(len(bindings), 3)
        self.assertEqual(len(set(bindings.values())), 3)

    def test_every_required_test_exists_and_is_not_skipped(self) -> None:
        for entry in load_json(CONTRACT_MANIFEST)["required"]:
            module_name, class_name, method_name = entry["test"].rsplit(".", 2)
            module = importlib.import_module(module_name)
            test_case = getattr(module, class_name)
            method = getattr(test_case, method_name)
            self.assertTrue(callable(method), entry["id"])
            self.assertFalse(getattr(method, "__unittest_skip__", False), entry["id"])

    def test_architecture_manifest_matches_exact_modules_and_imports(self) -> None:
        manifest = load_json(ARCHITECTURE_MANIFEST)
        declared = manifest["declared_modules"]
        allowed = set(manifest["allowed_internal_imports"])
        forbidden = tuple(manifest["forbidden_import_prefixes"])

        self.assertEqual(
            manifest["schema"],
            "macr-v07-phase-b-architecture-manifest/v1",
        )
        self.assertEqual(manifest["phase"], "B")
        self.assertFalse(manifest["network_activity"])
        self.assertFalse(manifest["provider_generation"])
        self.assertFalse(manifest["phase_c_started"])
        self.assertEqual(len(declared), len(set(declared)))

        for module_name in declared:
            relative = Path(*module_name.split(".")).with_suffix(".py")
            source_path = ROOT / "src" / relative
            self.assertTrue(source_path.is_file(), module_name)
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            internal: set[str] = set()
            external_roots: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("macr_runtime"):
                            internal.add(alias.name)
                        else:
                            external_roots.add(alias.name.split(".", 1)[0])
                elif isinstance(node, ast.ImportFrom):
                    imported = resolve_import(module_name, node)
                    if imported.startswith("macr_runtime"):
                        internal.add(imported)
                    elif imported and node.level == 0:
                        external_roots.add(imported.split(".", 1)[0])
            self.assertTrue(internal <= allowed, (module_name, sorted(internal - allowed)))
            self.assertFalse(
                any(item.startswith(prefix) for item in internal for prefix in forbidden),
                (module_name, sorted(internal)),
            )
            self.assertTrue(
                external_roots <= sys.stdlib_module_names,
                (module_name, sorted(external_roots - sys.stdlib_module_names)),
            )

    def test_phase_b_public_exports_are_exact(self) -> None:
        required = {
            "AgentDatabase",
            "AgentEventType",
            "AgentStateEvent",
            "AgentRunProjection",
            "ProjectionInspection",
            "ProjectionInspectionStatus",
            "AgentEventRecord",
            "AgentStore",
            "AgentOwnershipPermit",
            "AgentOwnershipStore",
            "AgentStateService",
            "PHASE_B_TRANSITIONS",
            "apply_agent_event",
            "replay_agent_events",
            "require_phase_b_transition",
        }
        forbidden = {
            "AgentRunner",
            "AgentPlanner",
            "AgentScheduler",
            "AgentCheckpointStore",
            "WakeEvaluator",
        }

        self.assertTrue(required <= set(agent_package.__all__))
        self.assertFalse(forbidden & set(agent_package.__all__))
        for name in required:
            self.assertTrue(hasattr(agent_package, name), name)

    def test_structural_smoke_script_is_offline_and_source_independent(self) -> None:
        manifest = load_json(ARCHITECTURE_MANIFEST)
        script = ROOT / manifest["fresh_replay_script"]
        self.assertTrue(script.is_file())
        source = script.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )

        self.assertIn("macr_runtime.agent", imported)
        self.assertNotIn("tests", imported)
        self.assertNotIn("macr_runtime.providers", imported)
        self.assertNotIn("macr_runtime.direct_runtime", imported)
        self.assertNotIn("macr_runtime.runtime", imported)
        self.assertIn("--database", source)
        self.assertIn('"network_activity": False', source)
        self.assertIn('"provider_generation": False', source)
        self.assertNotIn("docs/macr-v0.7/future", source)

    def test_root_package_is_lazy_for_agent_but_legacy_exports_remain_compatible(self) -> None:
        command = (
            "import sys; import macr_runtime.agent; "
            "assert 'macr_runtime.runtime' not in sys.modules; "
            "assert not any(name.startswith('macr_runtime.providers') "
            "for name in sys.modules)"
        )
        environment = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        completed = subprocess.run(
            [sys.executable, "-S", "-c", command],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"stdout={completed.stdout!r} stderr={completed.stderr!r}",
        )

        import macr_runtime
        from macr_runtime.contracts import TaskContract

        self.assertIs(macr_runtime.TaskContract, TaskContract)
        self.assertEqual(macr_runtime.__version__, "0.7.0a0")
        for name in macr_runtime.__all__:
            self.assertIsNotNone(getattr(macr_runtime, name), name)

    def test_phase_b_wrapper_reports_exact_offline_subject(self) -> None:
        script = ROOT / "scripts/verify-v07-phase-b.ps1"
        source = script.read_text(encoding="utf-8")
        self.assertIn("SOURCE_DATE_EPOCH", source)
        self.assertIn("source_date_epoch", source)
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        self.assertIsNotNone(powershell)
        completed = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-File",
                str(script),
                "-ManifestOnly",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        lines = [line for line in completed.stdout.splitlines() if line]
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("PHASE_B_MANIFEST="))
        payload = json.loads(lines[0].removeprefix("PHASE_B_MANIFEST="))
        self.assertEqual(
            payload["focused_modules"],
            [
                "tests.test_agent_state",
                "tests.test_agent_lifecycle",
                "tests.test_agent_database",
                "tests.test_agent_events",
                "tests.test_agent_store",
                "tests.test_agent_service",
                "tests.test_agent_ownership",
                "tests.test_agent_rebuild",
                "tests.test_agent_multiprocess",
                "tests.test_v07_phase_b_manifest",
            ],
        )
        self.assertEqual(
            payload["contract_manifest"],
            "tests/gates/v07_phase_b_contract_manifest.json",
        )
        self.assertEqual(
            payload["architecture_manifest"],
            "tests/gates/v07_phase_b_architecture_manifest.json",
        )
        self.assertEqual(
            payload["phase_a_gate"],
            "scripts/verify-v07-phase-a.ps1",
        )
        self.assertEqual(
            payload["fresh_replay_script"],
            "scripts/agent-kernel-replay-smoke.py",
        )
        self.assertFalse(payload["network_activity"])
        self.assertFalse(payload["provider_generation"])
        self.assertTrue(payload["phase_c_started"])

    def test_phase_a_wrapper_detects_phase_b_instead_of_hardcoding_false(self) -> None:
        source = (ROOT / "scripts/verify-v07-phase-a.ps1").read_text(encoding="utf-8")

        self.assertNotIn("phase_b_started = $false", source)
        self.assertIn("v07_phase_b_contract_manifest.json", source)


if __name__ == "__main__":
    unittest.main()
