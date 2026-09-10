from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .authority import DispatchAuthorityStore
from .errors import DispatchAuthorizationError, DispatchLeaseError
from .execution import DispatchContext
from .runtime_db import RuntimeDatabase


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _non_empty(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _uuid4(name: str, value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a UUIDv4 string") from exc
    if parsed.version != 4 or str(parsed) != value.lower():
        raise ValueError(f"{name} must be a UUIDv4 string")
    return str(parsed)


def _ttl(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 86400:
        raise ValueError("ttl_seconds must be between 1 and 86400")
    return value


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("lease timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class DispatchPermit:
    resource_key: str
    run_id: str
    fencing_token: int
    acquired_at: str
    expires_at: str


class DispatcherLeaseStore:
    def __init__(
        self,
        path: str | Path,
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.database = RuntimeDatabase(path)
        self._now = now

    def _current_time(self) -> datetime:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("lease clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def acquire(
        self,
        resource_key: str,
        run_id: str,
        *,
        ttl_seconds: int,
    ) -> DispatchPermit:
        resource = _non_empty("resource_key", resource_key)
        run = _uuid4("run_id", run_id)
        ttl = _ttl(ttl_seconds)
        now = self._current_time()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM dispatch_leases WHERE resource_key = ?",
                (resource,),
            ).fetchone()
            if row is not None and _aware(row["expires_at"]) <= now:
                connection.execute(
                    "DELETE FROM dispatch_leases WHERE resource_key = ?",
                    (resource,),
                )
                row = None
            if row is not None:
                if row["run_id"] == run:
                    connection.commit()
                    return DispatchPermit(
                        resource,
                        run,
                        row["fencing_token"],
                        row["acquired_at"],
                        row["expires_at"],
                    )
                raise DispatchLeaseError(
                    "dispatch resource is held by another run"
                )
            connection.execute(
                "UPDATE fencing_counter SET value = value + 1 WHERE singleton = 1"
            )
            token = connection.execute(
                "SELECT value FROM fencing_counter WHERE singleton = 1"
            ).fetchone()[0]
            acquired_at = now.isoformat()
            expires_at = (now + timedelta(seconds=ttl)).isoformat()
            connection.execute(
                """
                INSERT INTO dispatch_leases(
                    resource_key, run_id, fencing_token, acquired_at, expires_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (resource, run, token, acquired_at, expires_at),
            )
            connection.commit()
            return DispatchPermit(
                resource,
                run,
                token,
                acquired_at,
                expires_at,
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def renew(
        self,
        resource_key: str,
        run_id: str,
        fencing_token: int,
        *,
        ttl_seconds: int,
    ) -> DispatchPermit:
        resource = _non_empty("resource_key", resource_key)
        run = _uuid4("run_id", run_id)
        ttl = _ttl(ttl_seconds)
        now = self._current_time()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM dispatch_leases WHERE resource_key = ?",
                (resource,),
            ).fetchone()
            if (
                row is None
                or row["run_id"] != run
                or row["fencing_token"] != fencing_token
                or _aware(row["expires_at"]) <= now
            ):
                raise DispatchLeaseError(
                    "dispatch lease holder or fencing token is invalid"
                )
            expires_at = (now + timedelta(seconds=ttl)).isoformat()
            connection.execute(
                "UPDATE dispatch_leases SET expires_at = ? WHERE resource_key = ?",
                (expires_at, resource),
            )
            connection.commit()
            return DispatchPermit(
                resource,
                run,
                fencing_token,
                row["acquired_at"],
                expires_at,
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def release(
        self,
        resource_key: str,
        run_id: str,
        fencing_token: int,
    ) -> bool:
        resource = _non_empty("resource_key", resource_key)
        run = _uuid4("run_id", run_id)
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT run_id, fencing_token FROM dispatch_leases WHERE resource_key = ?",
                (resource,),
            ).fetchone()
            if (
                row is None
                or row["run_id"] != run
                or row["fencing_token"] != fencing_token
            ):
                raise DispatchLeaseError(
                    "dispatch lease holder or fencing token is invalid"
                )
            connection.execute(
                "DELETE FROM dispatch_leases WHERE resource_key = ?",
                (resource,),
            )
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def read(self, resource_key: str) -> DispatchPermit | None:
        resource = _non_empty("resource_key", resource_key)
        connection = self.database.connect()
        try:
            row = connection.execute(
                "SELECT * FROM dispatch_leases WHERE resource_key = ?",
                (resource,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return DispatchPermit(
            row["resource_key"],
            row["run_id"],
            row["fencing_token"],
            row["acquired_at"],
            row["expires_at"],
        )


class AdmissionGate:
    def __init__(
        self,
        authorities: DispatchAuthorityStore,
        leases: DispatcherLeaseStore,
    ) -> None:
        self.authorities = authorities
        self.leases = leases

    def admit(
        self,
        context: DispatchContext,
        *,
        resource_key: str,
        provider_id: str,
        task_type: str,
        ttl_seconds: int = 300,
    ) -> DispatchPermit:
        verification = {
            "provider_id": provider_id,
            "plane": context.plane.value,
            "task_type": task_type,
            "batch_id": context.batch_id,
            "member_digest": context.member_digest,
            "provider_tier_binding_digest": (
                context.provider_tier_binding_digest
            ),
            "project_binding_digest": context.project_binding_digest,
            "admission_lane": context.admission_lane,
            "provider_admission_policy_digest": (
                context.provider_admission_policy_digest
            ),
        }
        self.authorities.verify(context.authorization, **verification)
        permit = self.leases.acquire(
            resource_key,
            context.run_id,
            ttl_seconds=ttl_seconds,
        )
        try:
            self.authorities.verify(context.authorization, **verification)
        except DispatchAuthorizationError:
            self.leases.release(
                permit.resource_key,
                permit.run_id,
                permit.fencing_token,
            )
            raise
        return permit
