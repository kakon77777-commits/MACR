from __future__ import annotations

import argparse
import hashlib
import time
from pathlib import Path

from macr_runtime.observatory_db import ObservatoryDatabase


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    parser.add_argument("snapshot_root")
    parser.add_argument("start_signal")
    parser.add_argument("ready_signal")
    parser.add_argument("worker_id")
    args = parser.parse_args()

    start_signal = Path(args.start_signal)
    Path(args.ready_signal).touch()
    deadline = time.monotonic() + 30
    while not start_signal.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("observatory start signal was not observed")
        time.sleep(0.001)

    worker_digest = hashlib.sha256(args.worker_id.encode("utf-8")).hexdigest()
    store = ObservatoryDatabase(args.database, args.snapshot_root)
    store.append_evidence(
        {
            "qualification_key": "a" * 64,
            "kind": "bootstrap_control",
            "subject_digest": worker_digest,
            "observed_at": "2026-08-29T00:00:00+00:00",
            "payload": {"worker_digest": worker_digest},
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
