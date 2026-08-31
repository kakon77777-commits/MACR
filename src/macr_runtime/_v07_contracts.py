from __future__ import annotations

import math
import re
import uuid
from collections.abc import Mapping, Sequence
from types import MappingProxyType

from .canonical import aware_iso8601, canonical_json_bytes, sha256_id


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def require_non_empty(
    name: str,
    value: object,
    max_bytes: int = 512,
) -> str:
    if (
        isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or max_bytes < 1
    ):
        raise ValueError("max_bytes must be a positive integer")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    normalized = value.strip()
    if len(normalized.encode("utf-8")) > max_bytes:
        raise ValueError(f"{name} is too long")
    return normalized


def require_optional_non_empty(
    name: str,
    value: object | None,
    max_bytes: int = 512,
) -> str | None:
    if value is None:
        return None
    return require_non_empty(name, value, max_bytes)


def require_sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
    return value


def require_uuid4(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a UUIDv4 string")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"{name} must be a UUIDv4 string") from exc
    if parsed.version != 4 or str(parsed) != value:
        raise ValueError(f"{name} must be a UUIDv4 string")
    return value


def require_positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def require_non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def require_non_negative_number(name: str, value: object) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite non-negative number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{name} must be a finite non-negative number")
    if value < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return value


def require_json_value(name: str, value: object) -> object:
    try:
        canonical_json_bytes(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be finite JSON") from exc
    return value


def require_json_object(name: str, value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a JSON object")
    copied = dict(value)
    require_json_value(name, copied)
    return copied


def freeze_json_value(name: str, value: object) -> object:
    require_json_value(name, value)
    return _freeze_json(value)


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def public_json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            key: public_json_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [public_json_value(item) for item in value]
    return value


def require_closed_mapping(
    name: str,
    value: object,
    *,
    required: frozenset[str],
    optional: frozenset[str],
) -> dict[str, object]:
    if required & optional:
        raise ValueError("required and optional fields must not overlap")
    data = require_json_object(name, value)
    fields = frozenset(data)
    missing = sorted(required - fields)
    unknown = sorted(fields - required - optional)
    if missing:
        raise ValueError(f"{name} missing fields: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"{name} unknown fields: {', '.join(unknown)}")
    return data


def require_string_tuple(
    name: str,
    values: object,
    maximum: int = 128,
    unique: bool = True,
) -> tuple[str, ...]:
    if (
        isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or maximum < 0
    ):
        raise ValueError("maximum must be a non-negative integer")
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"{name} must be an array of strings")
    normalized = tuple(
        require_non_empty(f"{name} item", item) for item in values
    )
    if len(normalized) > maximum:
        raise ValueError(f"{name} exceeds its item limit")
    if unique and len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must not contain duplicates")
    return tuple(sorted(normalized))


def canonical_record_digest(namespace: str, payload: object) -> str:
    public_payload = public_json_value(payload)
    return sha256_id(
        namespace,
        require_json_value("canonical payload", public_payload),
    )


def normalize_timestamp(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO timestamp")
    return aware_iso8601(name, value)
