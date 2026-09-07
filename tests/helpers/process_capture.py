from __future__ import annotations

import subprocess
from dataclasses import dataclass
from os import PathLike
from typing import Mapping, Sequence


@dataclass(frozen=True)
class CapturedProcess:
    returncode: int
    stdout_bytes: bytes
    stderr_bytes: bytes

    @property
    def stdout(self) -> str:
        return render_utf8(self.stdout_bytes)

    @property
    def stderr(self) -> str:
        return render_utf8(self.stderr_bytes)


def run_bytes(
    argv: Sequence[str | PathLike[str]],
    *,
    cwd: str | PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> CapturedProcess:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=False,
    )
    return CapturedProcess(
        returncode=completed.returncode,
        stdout_bytes=completed.stdout,
        stderr_bytes=completed.stderr,
    )


def render_utf8(value: bytes) -> str:
    if not isinstance(value, bytes):
        raise TypeError("captured process output must be bytes")
    return value.decode("utf-8-sig", errors="replace")


def assert_canaries_absent(
    capture: CapturedProcess,
    canaries: Sequence[bytes],
) -> None:
    if not isinstance(capture, CapturedProcess):
        raise TypeError("capture must be a CapturedProcess")
    for canary in canaries:
        if not isinstance(canary, bytes) or not canary:
            raise ValueError("canaries must be non-empty bytes")
        if canary in capture.stdout_bytes:
            raise AssertionError("sensitive canary appeared in raw stdout")
        if canary in capture.stderr_bytes:
            raise AssertionError("sensitive canary appeared in raw stderr")


__all__ = [
    "CapturedProcess",
    "assert_canaries_absent",
    "render_utf8",
    "run_bytes",
]
