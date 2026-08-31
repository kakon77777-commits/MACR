from __future__ import annotations

import dataclasses
import os
from datetime import datetime

from macr_runtime.agent.ownership import AgentOwnershipPermit
from macr_runtime.agent.service import AgentStateService
from macr_runtime.agent.store import AgentStore
from tests.test_agent_state import make_header


class FixedClock:
    def __init__(self, value: str) -> None:
        self.value = datetime.fromisoformat(value)

    def __call__(self) -> datetime:
        return self.value


def owner_contender(
    database_path: str,
    owner_id: str,
    expected_revision: int,
    expected_epoch: int,
    observed_at: str,
    start_event,
    results,
) -> None:
    service = AgentStateService(
        AgentStore(database_path),
        now=FixedClock(observed_at),
    )
    start_event.wait(timeout=30)
    try:
        permit = service.acquire_agent_run(
            make_header().identity.agent_run_id,
            owner_id,
            expected_revision=expected_revision,
            expected_epoch=expected_epoch,
            ttl_seconds=300,
        )
        results.put(("acquired", dataclasses.asdict(permit)))
    except Exception as exc:
        results.put(("refused", type(exc).__name__, getattr(exc, "code", None)))


def stale_activate(
    database_path: str,
    permit_data: dict[str, object],
    expected_revision: int,
    expected_epoch: int,
    observed_at: str,
    start_event,
    results,
) -> None:
    service = AgentStateService(
        AgentStore(database_path),
        now=FixedClock(observed_at),
    )
    permit = AgentOwnershipPermit(**permit_data)
    start_event.wait(timeout=30)
    try:
        service.activate_agent_run(
            permit,
            expected_revision=expected_revision,
            expected_epoch=expected_epoch,
            reason_code="STALE_OWNER_ATTEMPT",
            reason_digest="a" * 64,
        )
        results.put(("mutated", None))
    except Exception as exc:
        results.put(("refused", type(exc).__name__, getattr(exc, "code", None)))


def hard_exit_after_event_insert(database_path: str) -> None:
    def terminate(marker: str) -> None:
        if marker == "after_event_insert":
            os._exit(73)

    store = AgentStore(database_path, fault_injector=terminate)
    store.create_agent_run(make_header())
