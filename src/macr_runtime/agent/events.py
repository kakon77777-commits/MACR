from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import PureWindowsPath
from typing import Any

from .._v07_contracts import (
    canonical_record_digest,
    freeze_json_value,
    normalize_timestamp,
    public_json_value,
    require_closed_mapping,
    require_non_empty,
    require_non_negative_int,
    require_positive_int,
    require_sha256,
    require_uuid4,
)
from .contracts import AgentRunHeader, AgentRunState
from .errors import AgentEventIntegrityError
from .lifecycle import require_phase_b_transition
from .state import AgentRunProjection


AGENT_EVENT_SCHEMA_VERSION = "macr-agent-event/v1"


class AgentEventType(str, Enum):
    RUN_CREATED = "agent.run_created"
    RUN_ADMITTED = "agent.run_admitted"
    OWNER_ACQUIRED = "agent.owner_acquired"
    RUN_ACTIVATED = "agent.run_activated"
    BLOCKED = "agent.blocked"
    COMPLETED = "agent.completed"
    FAILED = "agent.failed"
    CANCELLED = "agent.cancelled"


_REASON_EVENTS = frozenset(
    {
        AgentEventType.RUN_ADMITTED,
        AgentEventType.RUN_ACTIVATED,
        AgentEventType.BLOCKED,
        AgentEventType.FAILED,
        AgentEventType.CANCELLED,
    }
)
_PAYLOAD_FIELDS = {
    AgentEventType.RUN_CREATED: frozenset({"initial_header"}),
    **{
        event_type: frozenset({"reason_code", "reason_digest"})
        for event_type in _REASON_EVENTS
    },
    AgentEventType.OWNER_ACQUIRED: frozenset(
        {"owner_id", "lease_id", "fencing_token", "expires_at"}
    ),
    AgentEventType.COMPLETED: frozenset({"evidence_ref", "evidence_digest"}),
}
_FORBIDDEN_KEYS = frozenset(
    {
        "answer",
        "api_key",
        "authorization_header",
        "bearer_token",
        "body",
        "content",
        "credential",
        "path",
        "paths",
        "private_key",
        "prompt",
        "raw_response",
    }
)
_FORBIDDEN_SUFFIXES = ("_body", "_content", "_path", "_paths")
_LOCAL_PATH_MARKER = re.compile(
    r"(?i)(?<![a-z0-9])(?:[a-z]:[\\/]|\\\\[^\\/\s]+[\\/])"
)
_CREDENTIAL_VALUE_MARKER = re.compile(
    r"(?i)(?:\b(?:sk|xai)-[a-z0-9_-]{8,}|-----BEGIN\s+PRIVATE\s+KEY-----)"
)


def _normalize_key(key: str) -> str:
    separated_acronyms = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", key.strip())
    separated_words = re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])",
        "_",
        separated_acronyms,
    )
    return separated_words.lower().replace("-", "_")


def _contains_local_path(value: str) -> bool:
    stripped = value.strip()
    try:
        if PureWindowsPath(stripped).drive:
            return True
    except (OSError, ValueError):
        pass
    return bool(_LOCAL_PATH_MARKER.search(value))


def _validate_content_free(value: object) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("Agent event payload keys must be strings")
            normalized = _normalize_key(key)
            if normalized in _FORBIDDEN_KEYS or normalized.endswith(_FORBIDDEN_SUFFIXES):
                raise ValueError(f"forbidden Agent event payload key: {key}")
            _validate_content_free(child)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            _validate_content_free(child)
        return
    if isinstance(value, bytes):
        raise ValueError("Agent event payload may not contain bytes")
    if isinstance(value, str):
        if _contains_local_path(value):
            raise ValueError("Agent event payload contains a path-like value")
        if _CREDENTIAL_VALUE_MARKER.search(value):
            raise ValueError("Agent event payload contains a credential-like value")


def _validated_payload(
    event_type: AgentEventType,
    payload: object,
) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        raise ValueError("Agent event payload must be an object")
    data = dict(payload)
    expected = _PAYLOAD_FIELDS[event_type]
    unknown = sorted(set(data) - expected)
    missing = sorted(expected - set(data))
    if unknown:
        raise ValueError(f"Agent event payload unknown fields: {', '.join(unknown)}")
    if missing:
        raise ValueError(f"Agent event payload missing fields: {', '.join(missing)}")

    if event_type is AgentEventType.RUN_CREATED:
        header = AgentRunHeader.from_dict(data["initial_header"])
        AgentRunProjection.from_creation_header(header)
        normalized: dict[str, object] = {
            "initial_header": header.to_public_dict(),
        }
    elif event_type in _REASON_EVENTS:
        normalized = {
            "reason_code": require_non_empty(
                "reason_code",
                data["reason_code"],
                max_bytes=128,
            ),
            "reason_digest": require_sha256(
                "reason_digest",
                data["reason_digest"],
            ),
        }
    elif event_type is AgentEventType.OWNER_ACQUIRED:
        normalized = {
            "owner_id": require_non_empty(
                "owner_id",
                data["owner_id"],
                max_bytes=256,
            ),
            "lease_id": require_uuid4("lease_id", data["lease_id"]),
            "fencing_token": require_positive_int(
                "fencing_token",
                data["fencing_token"],
            ),
            "expires_at": normalize_timestamp("expires_at", data["expires_at"]),
        }
    elif event_type is AgentEventType.COMPLETED:
        normalized = {
            "evidence_ref": require_non_empty(
                "evidence_ref",
                data["evidence_ref"],
            ),
            "evidence_digest": require_sha256(
                "evidence_digest",
                data["evidence_digest"],
            ),
        }
    else:  # pragma: no cover - closed enum and mapping make this unreachable
        raise AssertionError("unknown Agent event type")

    _validate_content_free(normalized)
    freeze_json_value("Agent event payload", normalized)
    return normalized


@dataclass(frozen=True)
class AgentStateEvent:
    event_id: str
    agent_run_id: str
    epoch: int
    before_revision: int
    after_revision: int
    event_type: AgentEventType
    payload: Mapping[str, object]
    state_digest_after: str
    created_at: str
    schema_version: str = field(init=False, default=AGENT_EVENT_SCHEMA_VERSION)
    payload_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", require_uuid4("event_id", self.event_id))
        object.__setattr__(
            self,
            "agent_run_id",
            require_uuid4("agent_run_id", self.agent_run_id),
        )
        object.__setattr__(self, "epoch", require_non_negative_int("epoch", self.epoch))
        object.__setattr__(
            self,
            "before_revision",
            require_non_negative_int("before_revision", self.before_revision),
        )
        object.__setattr__(
            self,
            "after_revision",
            require_positive_int("after_revision", self.after_revision),
        )
        if self.after_revision != self.before_revision + 1:
            raise ValueError("after_revision must equal before_revision + 1")
        if not isinstance(self.event_type, AgentEventType):
            raise ValueError("event_type must be an AgentEventType")
        normalized_payload = _validated_payload(self.event_type, self.payload)
        object.__setattr__(
            self,
            "payload",
            freeze_json_value("Agent event payload", normalized_payload),
        )
        object.__setattr__(
            self,
            "state_digest_after",
            require_sha256("state_digest_after", self.state_digest_after),
        )
        object.__setattr__(
            self,
            "created_at",
            normalize_timestamp("created_at", self.created_at),
        )
        if self.event_type is AgentEventType.RUN_CREATED:
            header = AgentRunHeader.from_dict(
                public_json_value(self.payload["initial_header"])
            )
            if self.created_at != header.created_at:
                raise ValueError("creation event timestamp must match initial header")
        if self.event_type is AgentEventType.OWNER_ACQUIRED:
            expiry = datetime.fromisoformat(str(self.payload["expires_at"]))
            created = datetime.fromisoformat(self.created_at)
            if expiry <= created:
                raise ValueError("ownership expiry must be after event timestamp")
        object.__setattr__(
            self,
            "payload_digest",
            canonical_record_digest(
                "macr.agent.event-payload.v1",
                {
                    "event_type": self.event_type.value,
                    "payload": public_json_value(self.payload),
                },
            ),
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "agent_run_id": self.agent_run_id,
            "epoch": self.epoch,
            "before_revision": self.before_revision,
            "after_revision": self.after_revision,
            "event_type": self.event_type.value,
            "payload": public_json_value(self.payload),
            "payload_digest": self.payload_digest,
            "state_digest_after": self.state_digest_after,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentStateEvent":
        parsed = require_closed_mapping(
            "AgentStateEvent",
            data,
            required=frozenset(
                {
                    "schema_version",
                    "event_id",
                    "agent_run_id",
                    "epoch",
                    "before_revision",
                    "after_revision",
                    "event_type",
                    "payload",
                    "payload_digest",
                    "state_digest_after",
                    "created_at",
                }
            ),
            optional=frozenset(),
        )
        if parsed["schema_version"] != AGENT_EVENT_SCHEMA_VERSION:
            raise ValueError("schema_version must be macr-agent-event/v1")
        result = cls(
            event_id=parsed["event_id"],
            agent_run_id=parsed["agent_run_id"],
            epoch=parsed["epoch"],
            before_revision=parsed["before_revision"],
            after_revision=parsed["after_revision"],
            event_type=AgentEventType(parsed["event_type"]),
            payload=parsed["payload"],
            state_digest_after=parsed["state_digest_after"],
            created_at=parsed["created_at"],
        )
        if result.payload_digest != require_sha256(
            "payload_digest",
            parsed["payload_digest"],
        ):
            raise ValueError("payload_digest does not match Agent event")
        return result


_TARGET_STATE = {
    AgentEventType.RUN_ADMITTED: AgentRunState.ADMITTED,
    AgentEventType.RUN_ACTIVATED: AgentRunState.ACTIVE,
    AgentEventType.BLOCKED: AgentRunState.BLOCKED,
    AgentEventType.COMPLETED: AgentRunState.COMPLETED,
    AgentEventType.FAILED: AgentRunState.FAILED,
    AgentEventType.CANCELLED: AgentRunState.CANCELLED,
}


def apply_agent_event(
    current: AgentRunProjection | None,
    event: AgentStateEvent,
) -> AgentRunProjection:
    if not isinstance(event, AgentStateEvent):
        raise ValueError("event must be an AgentStateEvent")
    if current is None:
        if (
            event.event_type is not AgentEventType.RUN_CREATED
            or event.before_revision != 0
            or event.after_revision != 1
            or event.epoch != 0
        ):
            raise AgentEventIntegrityError("Agent event chain must begin with creation")
        header = AgentRunHeader.from_dict(
            public_json_value(event.payload["initial_header"])
        )
        projection = AgentRunProjection.from_creation_header(
            header,
            updated_at=event.created_at,
        )
    else:
        if event.event_type is AgentEventType.RUN_CREATED:
            raise AgentEventIntegrityError("AgentRun cannot contain two creation events")
        if event.agent_run_id != current.agent_run_id:
            raise AgentEventIntegrityError("Agent event run identity does not match")
        if (
            event.before_revision != current.state_revision
            or event.after_revision != current.state_revision + 1
        ):
            raise AgentEventIntegrityError("Agent event revision does not continue chain")
        if event.event_type is AgentEventType.OWNER_ACQUIRED:
            if current.state not in {
                AgentRunState.ADMITTED,
                AgentRunState.ACTIVE,
                AgentRunState.BLOCKED,
            }:
                raise AgentEventIntegrityError(
                    "Agent owner acquisition is invalid for current state"
                )
            if event.epoch != current.epoch + 1:
                raise AgentEventIntegrityError("owner acquisition must advance epoch")
            target = current.state
        else:
            if event.epoch != current.epoch:
                raise AgentEventIntegrityError("Agent event epoch does not match current epoch")
            target = _TARGET_STATE[event.event_type]
            try:
                require_phase_b_transition(current.state, target)
            except Exception as exc:
                raise AgentEventIntegrityError(
                    "Agent event lifecycle transition is invalid"
                ) from exc
        projection = AgentRunProjection(
            initial_header=current.initial_header,
            state=target,
            state_revision=event.after_revision,
            epoch=event.epoch,
            updated_at=event.created_at,
        )
    if projection.agent_run_id != event.agent_run_id:
        raise AgentEventIntegrityError("Agent creation identity does not match event")
    if projection.state_digest != event.state_digest_after:
        raise AgentEventIntegrityError("Agent event state digest does not match projection")
    return projection


def replay_agent_events(events: Iterable[AgentStateEvent]) -> AgentRunProjection:
    current: AgentRunProjection | None = None
    event_ids: set[str] = set()
    observed = False
    for event in events:
        if not isinstance(event, AgentStateEvent):
            raise ValueError("events must contain AgentStateEvent values")
        observed = True
        if event.event_id in event_ids:
            raise AgentEventIntegrityError("Agent event chain contains duplicate event ID")
        event_ids.add(event.event_id)
        current = apply_agent_event(current, event)
    if not observed or current is None:
        raise AgentEventIntegrityError("Agent event chain is empty")
    return current
