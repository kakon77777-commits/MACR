from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class AppendOnlyLedger:
    """Process-local serialized JSONL append ledger.

    Cross-process locking is intentionally deferred and documented as a v0.2
    requirement. Each event carries a unique identity so consumers can reject
    stale or duplicate candidates before acceptance.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "payload": dict(payload),
        }
        encoded = json.dumps(event, ensure_ascii=False, sort_keys=True, default=str)
        with self._lock:
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(encoded)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
        return event

    def read_all(self) -> tuple[dict[str, Any], ...]:
        if not self.path.exists():
            return ()
        events: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid ledger JSON at line {line_number}") from exc
                if not isinstance(value, dict):
                    raise ValueError(f"invalid ledger event at line {line_number}")
                events.append(value)
        return tuple(events)
