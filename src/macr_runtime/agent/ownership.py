from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .._v07_contracts import (
    normalize_timestamp,
    require_non_empty,
    require_positive_int,
    require_uuid4,
)
from .store import AgentStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ttl(value: object) -> int:
    selected = require_positive_int("ttl_seconds", value)
    if selected > 86400:
        raise ValueError("ttl_seconds must not exceed 86400")
    return selected


@dataclass(frozen=True)
class AgentOwnershipPermit:
    agent_run_id: str
    owner_id: str
    lease_id: str
    fencing_token: int
    epoch: int
    revision: int
    acquired_at: str
    expires_at: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "agent_run_id",
            require_uuid4("agent_run_id", self.agent_run_id),
        )
        object.__setattr__(
            self,
            "owner_id",
            require_non_empty("owner_id", self.owner_id, max_bytes=256),
        )
        object.__setattr__(self, "lease_id", require_uuid4("lease_id", self.lease_id))
        object.__setattr__(
            self,
            "fencing_token",
            require_positive_int("fencing_token", self.fencing_token),
        )
        object.__setattr__(self, "epoch", require_positive_int("epoch", self.epoch))
        object.__setattr__(
            self,
            "revision",
            require_positive_int("revision", self.revision),
        )
        object.__setattr__(
            self,
            "acquired_at",
            normalize_timestamp("acquired_at", self.acquired_at),
        )
        object.__setattr__(
            self,
            "expires_at",
            normalize_timestamp("expires_at", self.expires_at),
        )
        if datetime.fromisoformat(self.expires_at) <= datetime.fromisoformat(
            self.acquired_at
        ):
            raise ValueError("ownership expiry must be after acquisition")


class AgentOwnershipStore:
    def __init__(
        self,
        store: AgentStore,
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not isinstance(store, AgentStore):
            raise ValueError("store must be an AgentStore")
        self.store = store
        self._now = now

    def _time(self) -> datetime:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("Agent ownership clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def acquire(
        self,
        agent_run_id: str,
        owner_id: str,
        *,
        expected_revision: int,
        expected_epoch: int,
        ttl_seconds: int,
        event_id: str | None = None,
        lease_id: str | None = None,
    ) -> AgentOwnershipPermit:
        ttl = _ttl(ttl_seconds)
        now = self._time()
        return self.store._acquire_ownership(
            agent_run_id,
            owner_id=owner_id,
            expected_revision=expected_revision,
            expected_epoch=expected_epoch,
            observed_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=ttl)).isoformat(),
            lease_id=str(uuid.uuid4()) if lease_id is None else lease_id,
            event_id=event_id,
        )

    def renew(
        self,
        permit: AgentOwnershipPermit,
        *,
        ttl_seconds: int,
    ) -> AgentOwnershipPermit:
        ttl = _ttl(ttl_seconds)
        now = self._time()
        return self.store._renew_ownership(
            permit,
            observed_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=ttl)).isoformat(),
        )

    def release(self, permit: AgentOwnershipPermit) -> bool:
        return self.store._release_ownership(permit)

    def read(self, agent_run_id: str) -> AgentOwnershipPermit | None:
        return self.store._read_ownership(agent_run_id)
