from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .._v07_contracts import (
    canonical_record_digest,
    normalize_timestamp,
    require_closed_mapping,
    require_non_negative_int,
    require_positive_int,
    require_sha256,
)
from .contracts import AgentRunHeader, AgentRunState


AGENT_PROJECTION_SCHEMA_VERSION = "macr-agent-projection/v1"


def _require_creation_header(header: AgentRunHeader) -> AgentRunHeader:
    if not isinstance(header, AgentRunHeader):
        raise ValueError("initial_header must be an AgentRunHeader")
    if (
        header.state is not AgentRunState.CREATED
        or header.state_revision != 1
        or header.epoch != 0
    ):
        raise ValueError(
            "AgentRun creation requires exactly CREATED/revision 1/epoch 0"
        )
    return header


@dataclass(frozen=True)
class AgentRunProjection:
    initial_header: AgentRunHeader
    state: AgentRunState
    state_revision: int
    epoch: int
    updated_at: str
    schema_version: str = field(
        init=False,
        default=AGENT_PROJECTION_SCHEMA_VERSION,
    )
    state_digest: str = field(init=False)

    def __post_init__(self) -> None:
        _require_creation_header(self.initial_header)
        if not isinstance(self.state, AgentRunState):
            raise ValueError("state must be an AgentRunState")
        object.__setattr__(
            self,
            "state_revision",
            require_positive_int("state_revision", self.state_revision),
        )
        object.__setattr__(
            self,
            "epoch",
            require_non_negative_int("epoch", self.epoch),
        )
        object.__setattr__(
            self,
            "updated_at",
            normalize_timestamp("updated_at", self.updated_at),
        )
        object.__setattr__(
            self,
            "state_digest",
            canonical_record_digest(
                "macr.agent.projection.v1",
                self._identity_dict(),
            ),
        )

    @property
    def agent_run_id(self) -> str:
        return self.initial_header.identity.agent_run_id

    @property
    def subject_digest(self) -> str:
        return self.initial_header.identity.subject_digest

    @classmethod
    def from_creation_header(
        cls,
        header: AgentRunHeader,
        *,
        updated_at: str | None = None,
    ) -> "AgentRunProjection":
        initial = _require_creation_header(header)
        return cls(
            initial_header=initial,
            state=AgentRunState.CREATED,
            state_revision=1,
            epoch=0,
            updated_at=initial.created_at if updated_at is None else updated_at,
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "agent_run_id": self.agent_run_id,
            "subject_digest": self.subject_digest,
            "initial_header": self.initial_header.to_public_dict(),
            "state": self.state.value,
            "state_revision": self.state_revision,
            "epoch": self.epoch,
        }

    def to_public_dict(self) -> dict[str, object]:
        return {
            **self._identity_dict(),
            "updated_at": self.updated_at,
            "state_digest": self.state_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentRunProjection":
        parsed = require_closed_mapping(
            "AgentRunProjection",
            data,
            required=frozenset(
                {
                    "schema_version",
                    "agent_run_id",
                    "subject_digest",
                    "initial_header",
                    "state",
                    "state_revision",
                    "epoch",
                    "updated_at",
                    "state_digest",
                }
            ),
            optional=frozenset(),
        )
        if parsed["schema_version"] != AGENT_PROJECTION_SCHEMA_VERSION:
            raise ValueError("schema_version must be macr-agent-projection/v1")
        header = AgentRunHeader.from_dict(parsed["initial_header"])
        if parsed["agent_run_id"] != header.identity.agent_run_id:
            raise ValueError("agent_run_id does not match initial_header")
        if require_sha256(
            "subject_digest",
            parsed["subject_digest"],
        ) != header.identity.subject_digest:
            raise ValueError("subject_digest does not match initial_header")
        result = cls(
            initial_header=header,
            state=AgentRunState(parsed["state"]),
            state_revision=parsed["state_revision"],
            epoch=parsed["epoch"],
            updated_at=parsed["updated_at"],
        )
        if result.state_digest != require_sha256(
            "state_digest",
            parsed["state_digest"],
        ):
            raise ValueError("state_digest does not match projection")
        return result
