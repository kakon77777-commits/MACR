from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from macr_runtime.event_store import SqliteEventStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    parser.add_argument("worker")
    parser.add_argument("count", type=int)
    args = parser.parse_args()
    if args.count < 0:
        raise ValueError("count must be non-negative")
    store = SqliteEventStore(Path(args.database))
    for index in range(args.count):
        store.append_standalone(
            "concurrency.probe",
            str(uuid.uuid4()),
            {"worker": args.worker, "index": index},
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
