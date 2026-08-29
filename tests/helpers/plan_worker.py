from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from macr_runtime.scheduler import PlanQueue


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    parser.add_argument("start_signal")
    parser.add_argument("ready_signal")
    parser.add_argument("dispatcher_id")
    args = parser.parse_args()

    database = Path(args.database)
    start_signal = Path(args.start_signal)
    ready_signal = Path(args.ready_signal)
    queue = PlanQueue(database)
    ready_signal.touch()
    deadline = time.monotonic() + 30
    while not start_signal.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("plan worker start signal was not observed")
        time.sleep(0.001)

    claim = queue.claim(args.dispatcher_id, lease_seconds=60)
    if claim is None:
        print(json.dumps({"member_id": None}, sort_keys=True))
        return 0
    queue.complete(
        claim.member_id,
        args.dispatcher_id,
        claim.fencing_token,
        terminal_evidence_digest=claim.member_digest,
        observed_cost_usd=0,
    )
    print(
        json.dumps(
            {
                "member_id": claim.member_id,
                "fencing_token": claim.fencing_token,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
