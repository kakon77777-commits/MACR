import tomllib
import unittest
from pathlib import Path

import macr_runtime


ROOT = Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def test_package_versions_are_0_5_0a1(self) -> None:
        project = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(project["project"]["version"], "0.5.0a1")
        self.assertEqual(macr_runtime.__version__, "0.5.0a1")


if __name__ == "__main__":
    unittest.main()
