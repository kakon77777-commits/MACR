from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


DEFAULT_TEST_ROOT = Path(r"R:\AI_Runtime\macr-state\test-tmp")


@contextmanager
def r_drive_tempdir() -> Iterator[Path]:
    root = Path(os.environ.get("MACR_TEST_TMP", str(DEFAULT_TEST_ROOT)))
    if root.drive.upper() not in {"D:", "R:"}:
        raise RuntimeError("MACR tests may create persistent or temporary state only on D: or R:")
    root.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="macr-test-", dir=root))
    try:
        yield path
    finally:
        resolved = path.resolve()
        if resolved.parent.resolve() != root.resolve():
            raise RuntimeError("refusing to clean an unexpected test directory")
        shutil.rmtree(resolved)
