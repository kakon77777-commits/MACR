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

import macr_runtime.semantic as semantic_package

from tests.support import d_drive_tempdir


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_MANIFEST = ROOT / "tests/gates/v07_phase_c_contract_manifest.json"
ARCHITECTURE_MANIFEST = ROOT / "tests/gates/v07_phase_c_architecture_manifest.json"


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


class V07PhaseCManifestTests(unittest.TestCase):
    def test_phase_c_wrapper_reports_exact_offline_subject(self) -> None:
        script = ROOT / "scripts/verify-v07-phase-c.ps1"
        source = script.read_text(encoding="utf-8")
        for required in (
            "pip wheel",
            "--no-deps",
            "--no-index",
            "MACR_INSTALL_TARGET",
            "installed_import_isolated",
            "python -S",
        ):
            self.assertIn(required, source)
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        self.assertIsNotNone(powershell)
        completed = subprocess.run(
            [powershell, "-NoProfile", "-File", str(script), "-ManifestOnly"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        lines = [line for line in completed.stdout.splitlines() if line]
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("PHASE_C_MANIFEST="))
        payload = json.loads(lines[0].removeprefix("PHASE_C_MANIFEST="))
        self.assertEqual(
            payload["contract_manifest"],
            "tests/gates/v07_phase_c_contract_manifest.json",
        )
        self.assertEqual(
            payload["architecture_manifest"],
            "tests/gates/v07_phase_c_architecture_manifest.json",
        )
        self.assertEqual(payload["phase_b_gate"], "scripts/verify-v07-phase-b.ps1")
        self.assertEqual(
            payload["fresh_replay_script"],
            "scripts/semantic-working-state-replay-smoke.py",
        )
        self.assertIn("tests.test_semantic_projection", payload["focused_modules"])
        self.assertIn("tests.test_v07_phase_c_manifest", payload["focused_modules"])
        self.assertFalse(payload["network_activity"])
        self.assertFalse(payload["provider_generation"])
        self.assertFalse(payload["phase_d_started"])

    def test_phase_b_wrapper_detects_phase_c_manifest_instead_of_rejecting_source(self) -> None:
        source = (ROOT / "scripts/verify-v07-phase-b.ps1").read_text(encoding="utf-8")
        self.assertIn("v07_phase_c_contract_manifest.json", source)
        self.assertNotIn("Phase C source is present in the Phase B verification subject", source)
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        completed = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-File",
                str(ROOT / "scripts/verify-v07-phase-b.ps1"),
                "-ManifestOnly",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        line = next(
            item for item in completed.stdout.splitlines()
            if item.startswith("PHASE_B_MANIFEST=")
        )
        self.assertTrue(json.loads(line.removeprefix("PHASE_B_MANIFEST="))["phase_c_started"])

    def test_contract_manifest_ids_families_and_bindings_are_unique(self) -> None:
        manifest = load_json(CONTRACT_MANIFEST)
        required = manifest["required"]
        ids = [entry["id"] for entry in required]
        tests = [entry["test"] for entry in required]

        self.assertEqual(manifest["schema"], "macr-v07-phase-c-test-manifest/v1")
        self.assertEqual(manifest["phase"], "C")
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(tests), len(set(tests)))
        self.assertEqual(
            {identifier.rsplit("-", 1)[0] for identifier in ids},
            {
                "PC-REG",
                "PC-GRAPH",
                "PC-DB",
                "PC-PATCH",
                "PC-PROP",
                "PC-COMMIT",
                "PC-ATOM",
                "PC-SHARE",
                "PC-RBLD",
                "PC-PROJ",
                "PC-ARCH",
            },
        )
        self.assertTrue(all(entry["severity"] in {"S0", "S1"} for entry in required))

    def test_every_required_test_exists_and_is_not_skipped(self) -> None:
        for entry in load_json(CONTRACT_MANIFEST)["required"]:
            module_name, class_name, method_name = entry["test"].rsplit(".", 2)
            module = importlib.import_module(module_name)
            method = getattr(getattr(module, class_name), method_name)
            self.assertTrue(callable(method), entry["id"])
            self.assertFalse(getattr(method, "__unittest_skip__", False), entry["id"])

    def test_twin_challenge_axes_have_distinct_positive_and_negative_bindings(self) -> None:
        required = {
            entry["id"]: entry["test"]
            for entry in load_json(CONTRACT_MANIFEST)["required"]
        }
        groups = (
            ("PC-COMMIT-01", "PC-COMMIT-02"),
            ("PC-GRAPH-03", "PC-RBLD-02"),
            ("PC-RBLD-01", "PC-RBLD-03"),
            ("PC-PROJ-01", "PC-PROJ-05"),
        )
        for positive, negative in groups:
            self.assertIn(positive, required)
            self.assertIn(negative, required)
            self.assertNotEqual(required[positive], required[negative])

    def test_architecture_manifest_matches_exact_modules_and_imports(self) -> None:
        manifest = load_json(ARCHITECTURE_MANIFEST)
        declared = manifest["declared_modules"]
        allowed = set(manifest["allowed_internal_imports"])
        forbidden = tuple(manifest["forbidden_import_prefixes"])

        self.assertEqual(
            manifest["schema"], "macr-v07-phase-c-architecture-manifest/v1"
        )
        self.assertEqual(manifest["phase"], "C")
        self.assertFalse(manifest["network_activity"])
        self.assertFalse(manifest["provider_generation"])
        self.assertFalse(manifest["phase_d_started"])
        self.assertEqual(len(declared), len(set(declared)))
        for module_name in declared:
            source_path = ROOT / "src" / Path(*module_name.split(".")).with_suffix(".py")
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

    def test_phase_c_public_exports_and_phase_d_absence_are_exact(self) -> None:
        required = {
            "SemanticRegistry",
            "SemanticGraphHead",
            "SemanticGraphRevision",
            "SemanticStore",
            "SemanticProposalService",
            "SemanticCommitService",
            "SemanticAttachReceipt",
            "SemanticCommitReceipt",
            "SemanticProjectionProfile",
            "SemanticContextRequest",
            "SemanticContextProjection",
            "SemanticContextProjector",
        }
        forbidden = {
            "SemanticObservationBridge",
            "SemanticActionExecutor",
            "AgentLoop",
            "AgentRunner",
        }
        self.assertTrue(required <= set(semantic_package.__all__))
        self.assertFalse(forbidden & set(semantic_package.__all__))
        for name in required:
            self.assertTrue(hasattr(semantic_package, name), name)
        for relative in load_json(ARCHITECTURE_MANIFEST)["phase_d_forbidden_paths"]:
            self.assertFalse((ROOT / relative).exists(), relative)

    def test_structural_smoke_contract_is_offline_and_reconstructs_from_source(self) -> None:
        manifest = load_json(ARCHITECTURE_MANIFEST)
        script = ROOT / manifest["fresh_replay_script"]
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
        self.assertNotIn("tests", imported)
        self.assertNotIn("macr_runtime.providers", imported)
        self.assertNotIn("macr_runtime.direct_runtime", imported)
        self.assertNotIn("macr_runtime.observation", imported)
        self.assertIn("--database", source)
        self.assertIn('"network_activity": False', source)
        self.assertIn('"provider_generation": False', source)
        self.assertIn("rebuild_graph_head", source)
        self.assertIn("rebuild_projection", source)

        with d_drive_tempdir() as temp:
            database = temp / "agent.sqlite3"
            environment = {
                **os.environ,
                "PYTHONPATH": str(ROOT / "src"),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            completed = subprocess.run(
                [sys.executable, "-S", str(script), "--database", str(database)],
                cwd=temp,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
            repeated = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    str(script),
                    "--database",
                    str(temp / "agent-repeat.sqlite3"),
                ],
                cwd=temp,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        self.assertEqual(repeated.returncode, 0, repeated.stderr or repeated.stdout)
        replay = json.loads(completed.stdout)
        self.assertEqual(json.loads(repeated.stdout), replay)
        self.assertTrue(replay["reconstruction_equivalent"])
        self.assertEqual(replay["graph_revision"], 2)
        self.assertEqual(replay["agent_state_revision"], 6)
        self.assertEqual(replay["agent_event_count"], 6)
        self.assertEqual(replay["semantic_binding_event_count"], 2)
        self.assertFalse(replay["network_activity"])
        self.assertFalse(replay["provider_generation"])

    def test_semantic_import_is_lazy_for_providers_direct_and_observation(self) -> None:
        command = (
            "import sys; import macr_runtime.semantic; "
            "assert not any(name.startswith('macr_runtime.providers') for name in sys.modules); "
            "assert 'macr_runtime.direct_runtime' not in sys.modules; "
            "assert not any(name.startswith('macr_runtime.observation') for name in sys.modules)"
        )
        completed = subprocess.run(
            [sys.executable, "-S", "-c", command],
            cwd=ROOT,
            env={
                **os.environ,
                "PYTHONPATH": str(ROOT / "src"),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)


if __name__ == "__main__":
    unittest.main()
