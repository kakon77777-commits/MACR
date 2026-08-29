from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import DispatchAuthorizationError
from .execution import AuthorizationReference
from .runtime_db import RuntimeDatabase


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_AUTHORITY_STATES = frozenset({"open", "hold", "suspended", "revoked"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _non_empty(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _string_tuple(name: str, value: Sequence[str], *, required: bool) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be an array")
    normalized = tuple(_non_empty(name, item) for item in value)
    if required and not normalized:
        raise ValueError(f"{name} must not be empty")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} must not contain duplicates")
    return normalized


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _aware_time(name: str, value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class AuthorityScope:
    providers: tuple[str, ...]
    planes: tuple[str, ...]
    task_types: tuple[str, ...] = ()
    batch_ids: tuple[str, ...] = ()
    member_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "providers",
            _string_tuple("authority providers", self.providers, required=True),
        )
        object.__setattr__(
            self,
            "planes",
            _string_tuple("authority planes", self.planes, required=True),
        )
        object.__setattr__(
            self,
            "task_types",
            _string_tuple("authority task_types", self.task_types, required=False),
        )
        object.__setattr__(
            self,
            "batch_ids",
            _string_tuple("authority batch_ids", self.batch_ids, required=False),
        )
        digests = _string_tuple(
            "authority member_digests",
            self.member_digests,
            required=False,
        )
        if any(not _SHA256.fullmatch(item.lower()) for item in digests):
            raise ValueError("authority member_digests must be SHA-256 hex")
        object.__setattr__(
            self,
            "member_digests",
            tuple(item.lower() for item in digests),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AuthorityScope":
        return cls(
            providers=data.get("providers", ()),
            planes=data.get("planes", ()),
            task_types=data.get("task_types", ()),
            batch_ids=data.get("batch_ids", ()),
            member_digests=data.get("member_digests", ()),
        )

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "providers": list(self.providers),
            "planes": list(self.planes),
            "task_types": list(self.task_types),
            "batch_ids": list(self.batch_ids),
            "member_digests": list(self.member_digests),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())

    def permits(
        self,
        *,
        provider_id: str,
        plane: str,
        task_type: str,
        batch_id: str | None,
        member_digest: str | None,
    ) -> bool:
        return (
            provider_id in self.providers
            and plane in self.planes
            and (not self.task_types or task_type in self.task_types)
            and (not self.batch_ids or batch_id in self.batch_ids)
            and (
                not self.member_digests
                or (
                    isinstance(member_digest, str)
                    and member_digest.lower() in self.member_digests
                )
            )
        )


class DispatchAuthorityStore:
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
            raise ValueError("authority clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def issue(
        self,
        *,
        source_kind: str,
        source_id: str,
        scope: AuthorityScope,
        expires_at: str,
    ) -> AuthorizationReference:
        normalized_kind = _non_empty("authority source_kind", source_kind)
        normalized_id = _non_empty("authority source_id", source_id)
        if not isinstance(scope, AuthorityScope):
            raise ValueError("authority scope must be an AuthorityScope")
        now = self._current_time()
        expiry = _aware_time("authority expires_at", expires_at)
        if expiry <= now:
            raise ValueError("authority expires_at must be in the future")
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            epoch_row = connection.execute(
                "SELECT epoch, state FROM authority_epoch WHERE singleton = 1"
            ).fetchone()
            if epoch_row["state"] != "open":
                raise DispatchAuthorizationError(
                    "dispatch authority state is not open"
                )
            revision = connection.execute(
                """
                SELECT COALESCE(MAX(revision), 0) + 1
                FROM dispatch_authorities
                WHERE source_kind = ? AND source_id = ?
                """,
                (normalized_kind, normalized_id),
            ).fetchone()[0]
            authority_id = str(uuid.uuid4())
            issued_at = now.isoformat()
            scope_json = scope.canonical_json()
            body = {
                "authority_id": authority_id,
                "source_kind": normalized_kind,
                "source_id": normalized_id,
                "revision": revision,
                "epoch": epoch_row["epoch"],
                "scope": scope.to_dict(),
                "issued_at": issued_at,
                "expires_at": expiry.isoformat(),
            }
            body_json = _canonical_json(body)
            digest = hashlib.sha256(body_json.encode("utf-8")).hexdigest()
            connection.execute(
                """
                INSERT INTO dispatch_authorities(
                    authority_id, source_kind, source_id, body_json,
                    body_sha256, revision, epoch, scope_json,
                    issued_at, expires_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    authority_id,
                    normalized_kind,
                    normalized_id,
                    body_json,
                    digest,
                    revision,
                    epoch_row["epoch"],
                    scope_json,
                    issued_at,
                    expiry.isoformat(),
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return AuthorizationReference(
            source_kind=normalized_kind,
            source_id=normalized_id,
            digest=digest,
            revision=revision,
            epoch=epoch_row["epoch"],
            scope=scope_json,
        )

    def advance_epoch(self, *, reason_digest: str, state: str) -> int:
        normalized_digest = reason_digest.lower()
        if not _SHA256.fullmatch(normalized_digest):
            raise ValueError("authority reason_digest must be SHA-256 hex")
        normalized_state = _non_empty("authority state", state)
        if normalized_state not in _AUTHORITY_STATES:
            raise ValueError("authority state is invalid")
        observed_at = self._current_time().isoformat()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT epoch FROM authority_epoch WHERE singleton = 1"
            ).fetchone()
            epoch = row["epoch"] + 1
            connection.execute(
                """
                UPDATE authority_epoch
                SET epoch = ?, state = ?, reason_digest = ?, updated_at = ?
                WHERE singleton = 1
                """,
                (epoch, normalized_state, normalized_digest, observed_at),
            )
            connection.commit()
            return epoch
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def revoke(self, reference: AuthorizationReference) -> bool:
        if not isinstance(reference, AuthorizationReference):
            raise DispatchAuthorizationError(
                "dispatch authorization reference is invalid"
            )
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM dispatch_authorities
                WHERE source_kind = ? AND source_id = ?
                  AND revision = ? AND epoch = ?
                """,
                (
                    reference.source_kind,
                    reference.source_id,
                    reference.revision,
                    reference.epoch,
                ),
            ).fetchone()
            if row is None or row["body_sha256"] != reference.digest:
                raise DispatchAuthorizationError(
                    "dispatch authorization digest is invalid"
                )
            changed = 0
            if row["revoked_at"] is None:
                changed = connection.execute(
                    """
                    UPDATE dispatch_authorities SET revoked_at = ?
                    WHERE authority_id = ? AND revoked_at IS NULL
                    """,
                    (self._current_time().isoformat(), row["authority_id"]),
                ).rowcount
            connection.commit()
            return changed == 1
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def verify(
        self,
        reference: AuthorizationReference,
        *,
        provider_id: str,
        plane: str,
        task_type: str,
        batch_id: str | None = None,
        member_digest: str | None = None,
    ) -> AuthorizationReference:
        if not isinstance(reference, AuthorizationReference):
            raise DispatchAuthorizationError(
                "dispatch authorization reference is invalid"
            )
        connection = self.database.connect()
        try:
            epoch_row = connection.execute(
                "SELECT epoch, state FROM authority_epoch WHERE singleton = 1"
            ).fetchone()
            row = connection.execute(
                """
                SELECT * FROM dispatch_authorities
                WHERE source_kind = ? AND source_id = ? AND revision = ?
                """,
                (
                    reference.source_kind,
                    reference.source_id,
                    reference.revision,
                ),
            ).fetchone()
        finally:
            connection.close()
        if reference.epoch != epoch_row["epoch"]:
            raise DispatchAuthorizationError(
                "dispatch authorization has a stale epoch"
            )
        if epoch_row["state"] != "open":
            raise DispatchAuthorizationError(
                "dispatch authorization state is not open"
            )
        if row is None:
            raise DispatchAuthorizationError(
                "dispatch authorization record is missing"
            )
        try:
            body = json.loads(row["body_json"])
            scope = AuthorityScope.from_dict(json.loads(row["scope_json"]))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DispatchAuthorizationError(
                "dispatch authorization digest is invalid"
            ) from exc
        expected_digest = hashlib.sha256(
            row["body_json"].encode("utf-8")
        ).hexdigest()
        if (
            expected_digest != row["body_sha256"]
            or expected_digest != reference.digest
            or row["epoch"] != reference.epoch
            or row["scope_json"] != reference.scope
            or body.get("scope") != scope.to_dict()
        ):
            raise DispatchAuthorizationError(
                "dispatch authorization digest is invalid"
            )
        if row["revoked_at"] is not None:
            raise DispatchAuthorizationError(
                "dispatch authorization is revoked"
            )
        if self._current_time() >= _aware_time(
            "authority expires_at",
            row["expires_at"],
        ):
            raise DispatchAuthorizationError(
                "dispatch authorization is expired"
            )
        if not scope.permits(
            provider_id=_non_empty("provider_id", provider_id),
            plane=_non_empty("plane", plane),
            task_type=_non_empty("task_type", task_type),
            batch_id=batch_id,
            member_digest=member_digest,
        ):
            raise DispatchAuthorizationError(
                "dispatch authorization scope does not permit request"
            )
        return reference
