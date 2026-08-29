from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .canonical import aware_iso8601, canonical_json_bytes
from .errors import DispatchAuthorizationError
from .runtime_db import RuntimeDatabase


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded identifier")
    return value


def _cost(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite non-negative")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError(f"{name} must be finite non-negative")
    return normalized


def _identifier_set(name: str, values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"{name} must be an ordered array")
    normalized = tuple(_identifier(f"{name} item", item) for item in values)
    if not normalized or len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must be non-empty and unique")
    return tuple(sorted(normalized))


def _aware(name: str, value: str) -> datetime:
    normalized = aware_iso8601(name, value)
    return datetime.fromisoformat(normalized).astimezone(timezone.utc)


@dataclass(frozen=True)
class BatchMemberScope:
    member_digest: str
    provider_id: str
    route_id: str
    role_digest: str
    privacy: str
    context_class: str
    cost_ceiling_usd: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "member_digest",
            _digest("member_digest", self.member_digest),
        )
        object.__setattr__(
            self,
            "provider_id",
            _identifier("provider_id", self.provider_id),
        )
        object.__setattr__(self, "route_id", _digest("route_id", self.route_id))
        object.__setattr__(
            self,
            "role_digest",
            _digest("role_digest", self.role_digest),
        )
        object.__setattr__(self, "privacy", _identifier("privacy", self.privacy))
        object.__setattr__(
            self,
            "context_class",
            _identifier("context_class", self.context_class),
        )
        object.__setattr__(
            self,
            "cost_ceiling_usd",
            _cost("cost_ceiling_usd", self.cost_ceiling_usd),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "member_digest": self.member_digest,
            "provider_id": self.provider_id,
            "route_id": self.route_id,
            "role_digest": self.role_digest,
            "privacy": self.privacy,
            "context_class": self.context_class,
            "cost_ceiling_usd": self.cost_ceiling_usd,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BatchMemberScope":
        if not isinstance(value, Mapping):
            raise ValueError("batch member scope must be an object")
        return cls(
            member_digest=value.get("member_digest"),
            provider_id=value.get("provider_id"),
            route_id=value.get("route_id"),
            role_digest=value.get("role_digest"),
            privacy=value.get("privacy"),
            context_class=value.get("context_class"),
            cost_ceiling_usd=value.get("cost_ceiling_usd"),
        )


@dataclass(frozen=True)
class BatchScope:
    plan_digest: str
    ordered_members: tuple[BatchMemberScope, ...]
    aggregate_cost_ceiling_usd: float
    expires_at: str
    authorized_dispatchers: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "plan_digest",
            _digest("plan_digest", self.plan_digest),
        )
        if isinstance(self.ordered_members, (str, bytes)):
            raise ValueError("ordered_members must be an ordered array")
        members = tuple(self.ordered_members)
        if not members or any(
            not isinstance(item, BatchMemberScope) for item in members
        ):
            raise ValueError("ordered_members must contain batch member scopes")
        member_digests = tuple(item.member_digest for item in members)
        if len(member_digests) != len(set(member_digests)):
            raise ValueError("ordered_members must not contain duplicate members")
        object.__setattr__(self, "ordered_members", members)
        object.__setattr__(
            self,
            "aggregate_cost_ceiling_usd",
            _cost(
                "aggregate_cost_ceiling_usd",
                self.aggregate_cost_ceiling_usd,
            ),
        )
        object.__setattr__(
            self,
            "expires_at",
            aware_iso8601("expires_at", self.expires_at),
        )
        object.__setattr__(
            self,
            "authorized_dispatchers",
            _identifier_set(
                "authorized_dispatchers",
                self.authorized_dispatchers,
            ),
        )

    @property
    def member_digests(self) -> tuple[str, ...]:
        return tuple(item.member_digest for item in self.ordered_members)

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_digest": self.plan_digest,
            "ordered_members": [item.to_dict() for item in self.ordered_members],
            "aggregate_cost_ceiling_usd": self.aggregate_cost_ceiling_usd,
            "expires_at": self.expires_at,
            "authorized_dispatchers": list(self.authorized_dispatchers),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BatchScope":
        if not isinstance(value, Mapping):
            raise ValueError("batch scope must be an object")
        members = value.get("ordered_members")
        if not isinstance(members, list):
            raise ValueError("ordered_members must be an ordered array")
        return cls(
            plan_digest=value.get("plan_digest"),
            ordered_members=tuple(BatchMemberScope.from_dict(item) for item in members),
            aggregate_cost_ceiling_usd=value.get("aggregate_cost_ceiling_usd"),
            expires_at=value.get("expires_at"),
            authorized_dispatchers=tuple(value.get("authorized_dispatchers", ())),
        )

    def canonical_json(self) -> str:
        return canonical_json_bytes(self.to_dict()).decode("utf-8")


@dataclass(frozen=True)
class BatchAuthorityReference:
    authority_id: str
    digest: str
    revision: int
    plan_digest: str

    def __post_init__(self) -> None:
        try:
            parsed = uuid.UUID(self.authority_id)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("authority_id must be a UUIDv4 string") from exc
        if parsed.version != 4 or str(parsed) != self.authority_id.lower():
            raise ValueError("authority_id must be a UUIDv4 string")
        object.__setattr__(self, "authority_id", str(parsed))
        object.__setattr__(self, "digest", _digest("authority digest", self.digest))
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision < 1
        ):
            raise ValueError("authority revision must be positive integer")
        object.__setattr__(
            self,
            "plan_digest",
            _digest("authority plan_digest", self.plan_digest),
        )


class BatchAuthorityStore:
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
            raise ValueError("batch authority clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def issue(self, scope: BatchScope) -> BatchAuthorityReference:
        if not isinstance(scope, BatchScope):
            raise ValueError("scope must be a BatchScope")
        now = self._current_time()
        expiry = _aware("expires_at", scope.expires_at)
        if expiry <= now:
            raise ValueError("batch authority expires_at must be in the future")
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            revision = connection.execute(
                """
                SELECT COALESCE(MAX(revision), 0) + 1
                FROM batch_authorities WHERE plan_digest = ?
                """,
                (scope.plan_digest,),
            ).fetchone()[0]
            authority_id = str(uuid.uuid4())
            issued_at = now.isoformat()
            scope_json = scope.canonical_json()
            scope_digest = hashlib.sha256(scope_json.encode("utf-8")).hexdigest()
            body = {
                "authority_id": authority_id,
                "revision": revision,
                "issued_at": issued_at,
                "scope": scope.to_dict(),
            }
            body_json = canonical_json_bytes(body).decode("utf-8")
            digest = hashlib.sha256(body_json.encode("utf-8")).hexdigest()
            connection.execute(
                """
                INSERT INTO batch_authorities(
                    authority_id, body_json, body_sha256, scope_json,
                    scope_sha256, plan_digest, revision, issued_at,
                    expires_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    authority_id,
                    body_json,
                    digest,
                    scope_json,
                    scope_digest,
                    scope.plan_digest,
                    revision,
                    issued_at,
                    scope.expires_at,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return BatchAuthorityReference(
            authority_id=authority_id,
            digest=digest,
            revision=revision,
            plan_digest=scope.plan_digest,
        )

    def _load_scope(self, reference: BatchAuthorityReference) -> BatchScope:
        if not isinstance(reference, BatchAuthorityReference):
            raise DispatchAuthorizationError(
                "batch authorization reference is invalid"
            )
        connection = self.database.connect()
        try:
            row = connection.execute(
                "SELECT * FROM batch_authorities WHERE authority_id = ?",
                (reference.authority_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise DispatchAuthorizationError("batch authorization record is missing")
        try:
            body = json.loads(row["body_json"])
            raw_scope = json.loads(row["scope_json"])
            scope = BatchScope.from_dict(raw_scope)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DispatchAuthorizationError(
                "batch authorization digest is invalid"
            ) from exc
        body_digest = hashlib.sha256(row["body_json"].encode("utf-8")).hexdigest()
        scope_digest = hashlib.sha256(row["scope_json"].encode("utf-8")).hexdigest()
        if (
            body_digest != row["body_sha256"]
            or body_digest != reference.digest
            or scope_digest != row["scope_sha256"]
            or body.get("scope") != scope.to_dict()
            or row["plan_digest"] != reference.plan_digest
            or row["revision"] != reference.revision
            or scope.plan_digest != reference.plan_digest
        ):
            raise DispatchAuthorizationError(
                "batch authorization digest is invalid"
            )
        if row["revoked_at"] is not None:
            raise DispatchAuthorizationError("batch authorization is revoked")
        if self._current_time() >= _aware("expires_at", row["expires_at"]):
            raise DispatchAuthorizationError("batch authorization is expired")
        return scope

    def scope(
        self,
        reference: BatchAuthorityReference,
        *,
        dispatcher_id: str | None = None,
    ) -> BatchScope:
        scope = self._load_scope(reference)
        if dispatcher_id is not None:
            dispatcher = _identifier("dispatcher_id", dispatcher_id)
            if dispatcher not in scope.authorized_dispatchers:
                raise DispatchAuthorizationError(
                    "batch authorization does not permit dispatcher"
                )
        return scope

    def verify(
        self,
        reference: BatchAuthorityReference,
        expected_scope: BatchScope,
        *,
        dispatcher_id: str | None = None,
    ) -> BatchAuthorityReference:
        if not isinstance(expected_scope, BatchScope):
            raise DispatchAuthorizationError("expected batch scope is invalid")
        actual = self.scope(reference, dispatcher_id=dispatcher_id)
        if actual.plan_digest != expected_scope.plan_digest:
            raise DispatchAuthorizationError("batch authorization plan digest mismatch")
        if actual.ordered_members != expected_scope.ordered_members:
            raise DispatchAuthorizationError("batch authorization member scope mismatch")
        if (
            actual.aggregate_cost_ceiling_usd
            != expected_scope.aggregate_cost_ceiling_usd
        ):
            raise DispatchAuthorizationError(
                "batch authorization aggregate cost mismatch"
            )
        if actual.expires_at != expected_scope.expires_at:
            raise DispatchAuthorizationError("batch authorization expiry mismatch")
        if actual.authorized_dispatchers != expected_scope.authorized_dispatchers:
            raise DispatchAuthorizationError(
                "batch authorization dispatcher set mismatch"
            )
        return reference

    def revoke(self, reference: BatchAuthorityReference) -> bool:
        if not isinstance(reference, BatchAuthorityReference):
            raise DispatchAuthorizationError(
                "batch authorization reference is invalid"
            )
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM batch_authorities WHERE authority_id = ?",
                (reference.authority_id,),
            ).fetchone()
            if row is None:
                raise DispatchAuthorizationError(
                    "batch authorization record is missing"
                )
            if (
                row["body_sha256"] != reference.digest
                or row["revision"] != reference.revision
                or row["plan_digest"] != reference.plan_digest
            ):
                raise DispatchAuthorizationError(
                    "batch authorization digest is invalid"
                )
            changed = 0
            if row["revoked_at"] is None:
                changed = connection.execute(
                    """
                    UPDATE batch_authorities SET revoked_at = ?
                    WHERE authority_id = ? AND revoked_at IS NULL
                    """,
                    (self._current_time().isoformat(), reference.authority_id),
                ).rowcount
            connection.commit()
            return changed == 1
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


__all__ = [
    "BatchAuthorityReference",
    "BatchAuthorityStore",
    "BatchMemberScope",
    "BatchScope",
]
