from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

from .canonical import sha256_id
from .errors import DispatchLeaseError, StoragePolicyError
from .runtime_db import RuntimeDatabase


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


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


def _ttl(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 86400:
        raise ValueError("ttl_seconds must be between 1 and 86400")
    return value


def _aware(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("target lease timestamp must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("target lease timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


class TargetLeaseState(str, Enum):
    ACTIVE = "active"
    RELEASED = "released"
    RECONCILIATION_REQUIRED = "reconciliation_required"


def normalize_repository_relative_path(target_path: str) -> str:
    """Return one Windows-safe repository-relative collision identity."""

    if not isinstance(target_path, str) or not target_path.strip():
        raise ValueError("target path must be a non-empty relative path")
    text = unicodedata.normalize("NFC", target_path)
    if text != text.strip():
        raise ValueError("target path may not have outer whitespace")
    if (
        "\x00" in text
        or text.startswith(("/", "\\"))
        or _WINDOWS_DRIVE.match(text)
        or ":" in text
    ):
        raise ValueError("target path must be repository-relative")
    parts = text.replace("\\", "/").split("/")
    if any(
        not part
        or part in {".", ".."}
        or part.endswith((" ", "."))
        or part.split(".", 1)[0].upper() in _WINDOWS_RESERVED
        for part in parts
    ):
        raise ValueError("target path contains unsafe components")
    return "/".join(part.casefold() for part in parts)


@dataclass(frozen=True)
class NormalizedTarget:
    relative_path: str
    target_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.relative_path, str) or not self.relative_path:
            raise ValueError("normalized target path must be non-empty")
        object.__setattr__(
            self,
            "target_key",
            _digest("target_key", self.target_key),
        )


@dataclass(frozen=True)
class RepositoryIdentity:
    root: Path
    revision_digest: str
    repository_id: str

    def __post_init__(self) -> None:
        root = Path(self.root)
        if not root.is_absolute() or root.drive.upper() != "D:":
            raise StoragePolicyError(
                "repository root must be an absolute path on D:"
            )
        resolved = root.resolve(strict=True)
        if resolved.drive.upper() != "D:":
            raise StoragePolicyError(
                "resolved repository root must remain on D:"
            )
        if not resolved.is_dir():
            raise ValueError("repository root must be a directory")
        revision = _digest("revision_digest", self.revision_digest)
        expected = sha256_id(
            "repository_identity_v1",
            {
                "root_path_digest": sha256_id(
                    "repository_root_path_v1",
                    {
                        "root": str(resolved).replace("\\", "/").casefold(),
                    },
                ),
                "revision_digest": revision,
            },
        )
        if self.repository_id != expected:
            raise ValueError("repository_id does not match exact repository identity")
        object.__setattr__(self, "root", resolved)
        object.__setattr__(self, "revision_digest", revision)

    @classmethod
    def create(cls, root: str | Path, revision_digest: str) -> "RepositoryIdentity":
        candidate = Path(root)
        if not candidate.is_absolute() or candidate.drive.upper() != "D:":
            raise StoragePolicyError(
                "repository root must be an absolute path on D:"
            )
        resolved = candidate.resolve(strict=True)
        if resolved.drive.upper() != "D:":
            raise StoragePolicyError(
                "resolved repository root must remain on D:"
            )
        revision = _digest("revision_digest", revision_digest)
        root_digest = sha256_id(
            "repository_root_path_v1",
            {"root": str(resolved).replace("\\", "/").casefold()},
        )
        return cls(
            root=resolved,
            revision_digest=revision,
            repository_id=sha256_id(
                "repository_identity_v1",
                {
                    "root_path_digest": root_digest,
                    "revision_digest": revision,
                },
            ),
        )

    def normalize_target(self, target_path: str) -> NormalizedTarget:
        normalized = normalize_repository_relative_path(target_path)
        parts = normalized.split("/")
        candidate = self.root.joinpath(*parts).resolve(strict=False)
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("target path escapes repository root") from exc
        return NormalizedTarget(
            relative_path=normalized,
            target_key=sha256_id(
                "repository_target_v1",
                {
                    "repository_id": self.repository_id,
                    "relative_path": normalized,
                },
            ),
        )


@dataclass(frozen=True)
class TargetLease:
    lease_id: str
    repository_id: str
    target_key: str
    plan_digest: str
    member_digest: str
    alternative_group: str | None
    materialize_automatically: bool
    state: TargetLeaseState
    fencing_token: int
    acquired_at: str
    expires_at: str
    released_at: str | None
    reconciliation_evidence_digest: str | None


class TargetLeaseStore:
    def __init__(
        self,
        path: str | Path,
        repository: RepositoryIdentity,
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not isinstance(repository, RepositoryIdentity):
            raise ValueError("repository must be a RepositoryIdentity")
        self.database = RuntimeDatabase(path)
        self.repository = repository
        self._now = now

    def _current_time(self) -> datetime:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("target lease clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def acquire(
        self,
        plan_digest: str,
        member_digest: str,
        target_path: str,
        *,
        alternative_group: str | None = None,
        materialize_automatically: bool = False,
        ttl_seconds: int = 300,
    ) -> TargetLease:
        plan = _digest("plan_digest", plan_digest)
        member = _digest("member_digest", member_digest)
        target = self.repository.normalize_target(target_path)
        if alternative_group is not None:
            alternative_group = _identifier(
                "alternative_group",
                alternative_group,
            )
        if not isinstance(materialize_automatically, bool):
            raise ValueError("materialize_automatically must be boolean")
        ttl = _ttl(ttl_seconds)
        now = self._current_time()
        lease_id = sha256_id(
            "target_path_lease_v1",
            {
                "repository_id": self.repository.repository_id,
                "target_key": target.target_key,
                "plan_digest": plan,
                "member_digest": member,
            },
        )
        connection = self.database.connect()
        post_commit_error: DispatchLeaseError | None = None
        try:
            connection.execute("BEGIN IMMEDIATE")
            exact = connection.execute(
                "SELECT * FROM target_path_leases WHERE lease_id = ?",
                (lease_id,),
            ).fetchone()
            if exact is not None:
                if exact["state"] == TargetLeaseState.ACTIVE.value:
                    if _aware(exact["expires_at"]) <= now:
                        connection.execute(
                            """
                            UPDATE target_path_leases
                            SET state = 'reconciliation_required'
                            WHERE lease_id = ?
                            """,
                            (lease_id,),
                        )
                        connection.commit()
                        post_commit_error = DispatchLeaseError(
                            "expired target lease requires reconciliation"
                        )
                    elif (
                        exact["alternative_group"] == alternative_group
                        and bool(exact["materialize_automatically"])
                        == materialize_automatically
                    ):
                        connection.commit()
                        return self._from_row(exact)
                    else:
                        raise DispatchLeaseError(
                            "target lease parameters conflict with active ownership"
                        )
                elif exact["state"] == TargetLeaseState.RECONCILIATION_REQUIRED.value:
                    raise DispatchLeaseError(
                        "target lease requires reconciliation before reuse"
                    )
                else:
                    raise DispatchLeaseError(
                        "released target lease cannot be reused in the same plan"
                    )
            if post_commit_error is None:
                active = connection.execute(
                    """
                    SELECT * FROM target_path_leases
                    WHERE repository_id = ? AND target_key = ?
                      AND state IN ('active', 'reconciliation_required')
                    ORDER BY fencing_token
                    """,
                    (self.repository.repository_id, target.target_key),
                ).fetchall()
                expired = [
                    row
                    for row in active
                    if row["state"] == TargetLeaseState.ACTIVE.value
                    and _aware(row["expires_at"]) <= now
                ]
                if expired:
                    connection.executemany(
                        """
                        UPDATE target_path_leases
                        SET state = 'reconciliation_required'
                        WHERE lease_id = ?
                        """,
                        ((row["lease_id"],) for row in expired),
                    )
                    connection.commit()
                    post_commit_error = DispatchLeaseError(
                        "expired target ownership requires reconciliation"
                    )
                elif active:
                    if any(
                        row["state"]
                        == TargetLeaseState.RECONCILIATION_REQUIRED.value
                        for row in active
                    ):
                        raise DispatchLeaseError(
                            "target ownership requires reconciliation"
                        )
                    if any(row["plan_digest"] != plan for row in active):
                        raise DispatchLeaseError(
                            "target ownership belongs to another plan"
                        )
                    groups = {row["alternative_group"] for row in active}
                    if (
                        alternative_group is None
                        or None in groups
                        or groups != {alternative_group}
                    ):
                        raise DispatchLeaseError(
                            "target is held without one named alternative group"
                        )
                    automatic = sum(
                        int(row["materialize_automatically"]) for row in active
                    ) + int(materialize_automatically)
                    if automatic > 1:
                        raise DispatchLeaseError(
                            "competing target alternatives cannot both be automatic"
                        )
            if post_commit_error is None:
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
                    INSERT INTO target_path_leases(
                        lease_id, repository_id, target_key, plan_digest,
                        member_digest, alternative_group,
                        materialize_automatically, state, fencing_token,
                        acquired_at, expires_at, released_at,
                        reconciliation_evidence_digest
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, NULL, NULL)
                    """,
                    (
                        lease_id,
                        self.repository.repository_id,
                        target.target_key,
                        plan,
                        member,
                        alternative_group,
                        int(materialize_automatically),
                        token,
                        acquired_at,
                        expires_at,
                    ),
                )
                connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        if post_commit_error is not None:
            raise post_commit_error
        return self.read(lease_id)

    def renew(
        self,
        lease_id: str,
        member_digest: str,
        fencing_token: int,
        *,
        ttl_seconds: int = 300,
    ) -> TargetLease:
        lease = _digest("lease_id", lease_id)
        member = _digest("member_digest", member_digest)
        ttl = _ttl(ttl_seconds)
        now = self._current_time()
        connection = self.database.connect()
        expired = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM target_path_leases WHERE lease_id = ?",
                (lease,),
            ).fetchone()
            self._assert_holder(row, member, fencing_token)
            if _aware(row["expires_at"]) <= now:
                connection.execute(
                    """
                    UPDATE target_path_leases
                    SET state = 'reconciliation_required' WHERE lease_id = ?
                    """,
                    (lease,),
                )
                expired = True
            else:
                connection.execute(
                    "UPDATE target_path_leases SET expires_at = ? WHERE lease_id = ?",
                    ((now + timedelta(seconds=ttl)).isoformat(), lease),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        if expired:
            raise DispatchLeaseError(
                "expired target lease requires reconciliation and cannot renew"
            )
        return self.read(lease)

    def release(
        self,
        lease_id: str,
        member_digest: str,
        fencing_token: int,
    ) -> TargetLease:
        lease = _digest("lease_id", lease_id)
        member = _digest("member_digest", member_digest)
        now = self._current_time()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM target_path_leases WHERE lease_id = ?",
                (lease,),
            ).fetchone()
            self._assert_holder(row, member, fencing_token)
            if _aware(row["expires_at"]) <= now:
                connection.execute(
                    """
                    UPDATE target_path_leases
                    SET state = 'reconciliation_required' WHERE lease_id = ?
                    """,
                    (lease,),
                )
                connection.commit()
                raise DispatchLeaseError(
                    "expired target lease requires reconciliation"
                )
            connection.execute(
                """
                UPDATE target_path_leases
                SET state = 'released', released_at = ? WHERE lease_id = ?
                """,
                (now.isoformat(), lease),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.read(lease)

    def reconcile_release(
        self,
        lease_id: str,
        *,
        evidence_digest: str,
    ) -> TargetLease:
        lease = _digest("lease_id", lease_id)
        evidence = _digest("evidence_digest", evidence_digest)
        now = self._current_time().isoformat()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state FROM target_path_leases WHERE lease_id = ?",
                (lease,),
            ).fetchone()
            if row is None or row["state"] != TargetLeaseState.RECONCILIATION_REQUIRED.value:
                raise DispatchLeaseError(
                    "target lease is not awaiting reconciliation"
                )
            connection.execute(
                """
                UPDATE target_path_leases
                SET state = 'released', released_at = ?,
                    reconciliation_evidence_digest = ?
                WHERE lease_id = ?
                """,
                (now, evidence, lease),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.read(lease)

    @staticmethod
    def _assert_holder(row, member_digest: str, fencing_token: int) -> None:
        if (
            isinstance(fencing_token, bool)
            or not isinstance(fencing_token, int)
            or fencing_token < 1
        ):
            raise ValueError("fencing_token must be positive integer")
        if row is None:
            raise DispatchLeaseError("target lease does not exist")
        if row["state"] != TargetLeaseState.ACTIVE.value:
            raise DispatchLeaseError("target lease is not active")
        if (
            row["member_digest"] != member_digest
            or row["fencing_token"] != fencing_token
        ):
            raise DispatchLeaseError(
                "target lease holder or fencing token is invalid"
            )

    @staticmethod
    def _from_row(row) -> TargetLease:
        return TargetLease(
            lease_id=row["lease_id"],
            repository_id=row["repository_id"],
            target_key=row["target_key"],
            plan_digest=row["plan_digest"],
            member_digest=row["member_digest"],
            alternative_group=row["alternative_group"],
            materialize_automatically=bool(row["materialize_automatically"]),
            state=TargetLeaseState(row["state"]),
            fencing_token=row["fencing_token"],
            acquired_at=row["acquired_at"],
            expires_at=row["expires_at"],
            released_at=row["released_at"],
            reconciliation_evidence_digest=row[
                "reconciliation_evidence_digest"
            ],
        )

    def read(self, lease_id: str) -> TargetLease:
        lease = _digest("lease_id", lease_id)
        connection = self.database.connect()
        try:
            row = connection.execute(
                "SELECT * FROM target_path_leases WHERE lease_id = ?",
                (lease,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise DispatchLeaseError("target lease does not exist")
        return self._from_row(row)


__all__ = [
    "NormalizedTarget",
    "RepositoryIdentity",
    "TargetLease",
    "TargetLeaseState",
    "TargetLeaseStore",
    "normalize_repository_relative_path",
]
