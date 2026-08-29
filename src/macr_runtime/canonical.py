from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any


_NAMESPACE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical data must be finite JSON")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("canonical data must be finite JSON")
            _validate_json_value(item)
        return
    raise ValueError("canonical data must be finite JSON")


def canonical_json_bytes(value: object) -> bytes:
    _validate_json_value(value)
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("canonical data must be finite JSON") from exc
    return text.encode("utf-8")


def sha256_id(namespace: str, value: object) -> str:
    if not isinstance(namespace, str) or not _NAMESPACE.fullmatch(namespace):
        raise ValueError(
            "namespace must be bounded non-empty ASCII without whitespace"
        )
    return hashlib.sha256(
        namespace.encode("ascii") + b"\0" + canonical_json_bytes(value)
    ).hexdigest()


def aware_iso8601(name: str, value: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("timestamp name must be non-empty")
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat()
