from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Mapping

from .errors import StoragePolicyError


DEFAULT_SOURCE_ROOT = r"D:\Ai\work together\MACR"
DEFAULT_STATE_ROOT = r"D:\AI_RESIDENCE\AI_Runtime\macr-state"
DEFAULT_CODEX_HOME_TARGET = r"D:\AI_RESIDENCE\AI_Runtime\codex-home"
ALLOWED_PERSISTENT_DRIVES = frozenset({"D:"})


def _validate_persistent_path(name: str, value: str) -> str:
    path = PureWindowsPath(value)
    if not path.is_absolute() or not path.drive:
        raise StoragePolicyError(f"{name} must be an absolute Windows path")
    drive = path.drive.upper()
    if drive not in ALLOWED_PERSISTENT_DRIVES:
        raise StoragePolicyError(
            f"{name} must be on D:; persistent writes to {drive or 'an unknown drive'} are denied"
        )
    return str(path)


@dataclass(frozen=True)
class StorageLayout:
    source_root: str
    state_root: str
    codex_home_target: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_root", _validate_persistent_path("MACR_ROOT", self.source_root))
        object.__setattr__(self, "state_root", _validate_persistent_path("MACR_STATE_ROOT", self.state_root))
        object.__setattr__(
            self,
            "codex_home_target",
            _validate_persistent_path("CODEX_HOME_TARGET", self.codex_home_target),
        )

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "StorageLayout":
        env = os.environ if environ is None else environ
        return cls(
            source_root=env.get("MACR_ROOT", DEFAULT_SOURCE_ROOT),
            state_root=env.get("MACR_STATE_ROOT", DEFAULT_STATE_ROOT),
            codex_home_target=env.get("CODEX_HOME_TARGET", DEFAULT_CODEX_HOME_TARGET),
        )

    @property
    def ledger_path(self) -> Path:
        return Path(self.state_root) / "ledger" / "events.jsonl"

    @property
    def test_tmp_root(self) -> Path:
        return Path(self.state_root) / "test-tmp"

    @property
    def google_artifact_root(self) -> Path:
        return Path(self.state_root) / "artifacts" / "google"

    def ensure_state_tree(self) -> tuple[Path, ...]:
        roots = tuple(
            Path(self.state_root) / name
            for name in ("ledger", "artifacts", "cache", "test-tmp")
        )
        for path in roots:
            path.mkdir(parents=True, exist_ok=True)
        return roots

    def describe(self) -> dict[str, object]:
        return {
            "source_root": self.source_root,
            "state_root": self.state_root,
            "codex_home_target": self.codex_home_target,
            "source_exists": Path(self.source_root).is_dir(),
            "state_exists": Path(self.state_root).is_dir(),
            "codex_home_migrated": False,
        }
