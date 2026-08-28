from __future__ import annotations

import argparse
import time
from pathlib import Path

from macr_runtime.runtime_db import RuntimeDatabase


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    parser.add_argument("start_signal")
    parser.add_argument("ready_signal")
    args = parser.parse_args()

    database = Path(args.database)
    start_signal = Path(args.start_signal)
    ready_signal = Path(args.ready_signal)
    ready_signal.touch()
    deadline = time.monotonic() + 30
    while not start_signal.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("bootstrap start signal was not observed")
        time.sleep(0.001)

    runtime = RuntimeDatabase(database)
    connection = runtime.connect()
    try:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        connection.close()
    if journal_mode.lower() != "wal":
        raise AssertionError(f"expected WAL journal mode, got {journal_mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
