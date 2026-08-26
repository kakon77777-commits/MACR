from __future__ import annotations

import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


DEFAULT_TEST_ROOT = Path(r"D:\AI_RESIDENCE\AI_Runtime\macr-state\test-tmp")


def write_fake_google_credential(path: Path) -> Path:
    document = {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "test-key-id",
        "private_key": (
            "-----BEGIN "
            + "PRIVATE KEY-----\nTEST\n-----END "
            + "PRIVATE KEY-----\n"
        ),
        "client_email": "test@example.invalid",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


@contextmanager
def d_drive_tempdir() -> Iterator[Path]:
    root = Path(os.environ.get("MACR_TEST_TMP", str(DEFAULT_TEST_ROOT)))
    if root.drive.upper() != "D:":
        raise RuntimeError("MACR tests may create state only on D:")
    root.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="macr-test-", dir=root))
    try:
        yield path
    finally:
        resolved = path.resolve()
        if resolved.parent.resolve() != root.resolve():
            raise RuntimeError("refusing to clean an unexpected test directory")
        shutil.rmtree(resolved)
