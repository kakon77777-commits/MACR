from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .batch_authority import (
    BatchAuthorityReference,
    BatchAuthorityStore,
    BatchMemberScope,
)
from .canonical import canonical_json_bytes, sha256_id
from .errors import DispatchAuthorizationError, DispatchLeaseError
from .runtime_db import RuntimeDatabase
from .target_leases import normalize_repository_relative_path


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


def _ttl(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 86400:
        raise ValueError("lease_seconds must be between 1 and 86400")
    return value


def _aware(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("queue timestamp must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("queue timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


class QueueMemberState(str, Enum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    FAILED = "failed"
    RECONCILIATION_REQUIRED = "reconciliation_required"


@dataclass(frozen=True)
class TargetClaim:
    target_key: str
    alternative_group: str | None = None
    materialize_automatically: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_key",
            _digest("target_key", self.target_key),
        )
        if self.alternative_group is not None:
            object.__setattr__(
                self,
                "alternative_group",
                _identifier("alternative_group", self.alternative_group),
            )
        if not isinstance(self.materialize_automatically, bool):
            raise ValueError("materialize_automatically must be boolean")

    @classmethod
    def for_path(
        cls,
        path: str,
        *,
        alternative_group: str | None = None,
        materialize_automatically: bool = True,
    ) -> "TargetClaim":
        normalized = normalize_repository_relative_path(path)
        return cls(
            target_key=sha256_id("plan_target_path_v1", {"path": normalized}),
            alternative_group=alternative_group,
            materialize_automatically=materialize_automatically,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "target_key": self.target_key,
            "alternative_group": self.alternative_group,
            "materialize_automatically": self.materialize_automatically,
        }


@dataclass(frozen=True)
class QueueMember:
    member_digest: str
    provider_id: str
    route_id: str
    role_digest: str
    privacy: str
    context_class: str
    cost_ceiling_usd: float
    target_claims: tuple[TargetClaim, ...] = ()

    def __post_init__(self) -> None:
        member = BatchMemberScope(
            member_digest=self.member_digest,
            provider_id=self.provider_id,
            route_id=self.route_id,
            role_digest=self.role_digest,
            privacy=self.privacy,
            context_class=self.context_class,
            cost_ceiling_usd=self.cost_ceiling_usd,
        )
        for name in (
            "member_digest",
            "provider_id",
            "route_id",
            "role_digest",
            "privacy",
            "context_class",
            "cost_ceiling_usd",
        ):
            object.__setattr__(self, name, getattr(member, name))
        if isinstance(self.target_claims, (str, bytes)):
            raise ValueError("target_claims must be an array")
        claims = tuple(self.target_claims)
        if any(not isinstance(item, TargetClaim) for item in claims):
            raise ValueError("target_claims must contain TargetClaim values")
        keys = tuple(item.target_key for item in claims)
        if len(keys) != len(set(keys)):
            raise ValueError("target_claims must not contain duplicate targets")
        object.__setattr__(self, "target_claims", claims)

    def authority_scope(self) -> BatchMemberScope:
        return BatchMemberScope(
            member_digest=self.member_digest,
            provider_id=self.provider_id,
            route_id=self.route_id,
            role_digest=self.role_digest,
            privacy=self.privacy,
            context_class=self.context_class,
            cost_ceiling_usd=self.cost_ceiling_usd,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            **self.authority_scope().to_dict(),
            "target_claims": [item.to_dict() for item in self.target_claims],
        }


@dataclass(frozen=True)
class T1QueuePlan:
    plan_digest: str
    members: tuple[QueueMember, ...]
    aggregate_cost_ceiling_usd: float
    authority: BatchAuthorityReference

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "plan_digest",
            _digest("plan_digest", self.plan_digest),
        )
        if isinstance(self.members, (str, bytes)):
            raise ValueError("members must be an ordered array")
        members = tuple(self.members)
        if not members or any(not isinstance(item, QueueMember) for item in members):
            raise ValueError("members must contain queue members")
        digests = tuple(item.member_digest for item in members)
        if len(digests) != len(set(digests)):
            raise ValueError("members must not contain duplicate digests")
        object.__setattr__(self, "members", members)
        object.__setattr__(
            self,
            "aggregate_cost_ceiling_usd",
            _cost(
                "aggregate_cost_ceiling_usd",
                self.aggregate_cost_ceiling_usd,
            ),
        )
        if not isinstance(self.authority, BatchAuthorityReference):
            raise ValueError("authority must be a BatchAuthorityReference")
        if self.authority.plan_digest != self.plan_digest:
            raise ValueError("authority plan digest does not match queue plan")


@dataclass(frozen=True)
class QueueClaim:
    member_id: str
    plan_digest: str
    ordinal: int
    member_digest: str
    provider_id: str
    route_id: str
    role_digest: str
    privacy: str
    context_class: str
    cost_ceiling_usd: float
    dispatcher_id: str
    fencing_token: int
    lease_expires_at: str
    attempts: int


@dataclass(frozen=True)
class QueueMemberRecord:
    member_id: str
    plan_digest: str
    ordinal: int
    member_digest: str
    state: QueueMemberState
    lease_holder: str | None
    fencing_token: int | None
    lease_expires_at: str | None
    attempts: int
    terminal_at: str | None
    terminal_evidence_digest: str | None
    observed_cost_usd: float | None


class PlanQueue:
    def __init__(
        self,
        path: str | Path,
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.database = RuntimeDatabase(path)
        self._now = now
        self.authorities = BatchAuthorityStore(path, now=now)

    def _current_time(self) -> datetime:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("queue clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _validate_collisions(members: Sequence[QueueMember]) -> None:
        claims: dict[str, list[TargetClaim]] = defaultdict(list)
        for member in members:
            for claim in member.target_claims:
                claims[claim.target_key].append(claim)
        for target_claims in claims.values():
            if len(target_claims) < 2:
                continue
            groups = {item.alternative_group for item in target_claims}
            if None in groups or len(groups) != 1:
                raise DispatchLeaseError(
                    "target collision requires one named competing alternative group"
                )
            automatic = sum(
                1 for item in target_claims if item.materialize_automatically
            )
            if automatic > 1:
                raise DispatchLeaseError(
                    "competing alternatives cannot both use automatic materialization"
                )

    @staticmethod
    def _members_digest(members: Sequence[QueueMember]) -> str:
        return sha256_id(
            "plan_queue_members_v1",
            [item.to_dict() for item in members],
        )

    def enqueue(self, plan: T1QueuePlan) -> tuple[str, ...]:
        if not isinstance(plan, T1QueuePlan):
            raise ValueError("plan must be a T1QueuePlan")
        authority_scope = self.authorities.scope(plan.authority)
        if authority_scope.plan_digest != plan.plan_digest:
            raise DispatchAuthorizationError(
                "batch authorization plan digest mismatch"
            )
        expected_members = tuple(item.authority_scope() for item in plan.members)
        if authority_scope.ordered_members != expected_members:
            raise DispatchAuthorizationError(
                "batch authorization member scope mismatch"
            )
        if (
            authority_scope.aggregate_cost_ceiling_usd
            != plan.aggregate_cost_ceiling_usd
        ):
            raise DispatchAuthorizationError(
                "batch authorization aggregate cost mismatch"
            )
        self._validate_collisions(plan.members)
        members_digest = self._members_digest(plan.members)
        dispatcher_json = canonical_json_bytes(
            list(authority_scope.authorized_dispatchers)
        ).decode("utf-8")
        enqueued_at = self._current_time().isoformat()
        member_ids = tuple(
            sha256_id(
                "plan_queue_member_v1",
                {
                    "plan_digest": plan.plan_digest,
                    "ordinal": ordinal,
                    "member_digest": member.member_digest,
                },
            )
            for ordinal, member in enumerate(plan.members)
        )
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM plan_queue_batches WHERE plan_digest = ?",
                (plan.plan_digest,),
            ).fetchone()
            if existing is not None:
                matches = (
                    existing["authority_id"] == plan.authority.authority_id
                    and existing["authority_digest"] == plan.authority.digest
                    and existing["authority_revision"] == plan.authority.revision
                    and existing["aggregate_cost_ceiling_usd"]
                    == plan.aggregate_cost_ceiling_usd
                    and existing["authorized_dispatchers_json"] == dispatcher_json
                    and existing["expires_at"] == authority_scope.expires_at
                    and existing["members_sha256"] == members_digest
                )
                if not matches:
                    raise DispatchLeaseError(
                        "queued plan digest conflicts with existing batch"
                    )
                rows = connection.execute(
                    """
                    SELECT member_id FROM plan_queue_members
                    WHERE plan_digest = ? ORDER BY ordinal
                    """,
                    (plan.plan_digest,),
                ).fetchall()
                connection.commit()
                return tuple(row["member_id"] for row in rows)
            connection.execute(
                """
                INSERT INTO plan_queue_batches(
                    plan_digest, authority_id, authority_digest,
                    authority_revision, aggregate_cost_ceiling_usd,
                    authorized_dispatchers_json, expires_at,
                    members_sha256, enqueued_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.plan_digest,
                    plan.authority.authority_id,
                    plan.authority.digest,
                    plan.authority.revision,
                    plan.aggregate_cost_ceiling_usd,
                    dispatcher_json,
                    authority_scope.expires_at,
                    members_digest,
                    enqueued_at,
                ),
            )
            for ordinal, (member, member_id) in enumerate(
                zip(plan.members, member_ids)
            ):
                connection.execute(
                    """
                    INSERT INTO plan_queue_members(
                        member_id, plan_digest, ordinal, member_digest,
                        provider_id, route_id, role_digest, privacy,
                        context_class, cost_ceiling_usd, state,
                        lease_holder, fencing_token, lease_expires_at,
                        attempts, terminal_at, terminal_evidence_digest,
                        observed_cost_usd
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued',
                              NULL, NULL, NULL, 0, NULL, NULL, NULL)
                    """,
                    (
                        member_id,
                        plan.plan_digest,
                        ordinal,
                        member.member_digest,
                        member.provider_id,
                        member.route_id,
                        member.role_digest,
                        member.privacy,
                        member.context_class,
                        member.cost_ceiling_usd,
                    ),
                )
                for claim in member.target_claims:
                    connection.execute(
                        """
                        INSERT INTO plan_target_claims(
                            plan_digest, target_key, member_id,
                            alternative_group, materialize_automatically
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            plan.plan_digest,
                            claim.target_key,
                            member_id,
                            claim.alternative_group,
                            int(claim.materialize_automatically),
                        ),
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return member_ids

    @staticmethod
    def _mark_expired_claims(connection, now: datetime) -> None:
        timestamp = now.isoformat()
        connection.execute(
            """
            UPDATE plan_queue_members
            SET state = 'reconciliation_required', terminal_at = ?
            WHERE state = 'claimed' AND lease_expires_at <= ?
            """,
            (timestamp, timestamp),
        )

    @staticmethod
    def _reference_from_row(row) -> BatchAuthorityReference:
        return BatchAuthorityReference(
            authority_id=row["authority_id"],
            digest=row["authority_digest"],
            revision=row["authority_revision"],
            plan_digest=row["plan_digest"],
        )

    @staticmethod
    def _scope_member_from_row(row) -> BatchMemberScope:
        return BatchMemberScope(
            member_digest=row["member_digest"],
            provider_id=row["provider_id"],
            route_id=row["route_id"],
            role_digest=row["role_digest"],
            privacy=row["privacy"],
            context_class=row["context_class"],
            cost_ceiling_usd=row["cost_ceiling_usd"],
        )

    def claim(
        self,
        dispatcher_id: str,
        *,
        lease_seconds: int = 300,
        plan_digest: str | None = None,
    ) -> QueueClaim | None:
        dispatcher = _identifier("dispatcher_id", dispatcher_id)
        ttl = _ttl(lease_seconds)
        plan = (
            _digest("plan_digest", plan_digest)
            if plan_digest is not None
            else None
        )
        now = self._current_time()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._mark_expired_claims(connection, now)
            # Reconciliation evidence must survive any refusal while selecting
            # the next member (for example, an aggregate ceiling refusal).
            connection.commit()
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT m.*, b.authority_id, b.authority_digest,
                       b.authority_revision, b.aggregate_cost_ceiling_usd,
                       b.authorized_dispatchers_json, b.expires_at
                FROM plan_queue_members AS m
                JOIN plan_queue_batches AS b USING(plan_digest)
                WHERE m.state = 'queued' AND (? IS NULL OR m.plan_digest = ?)
                ORDER BY m.plan_digest, m.ordinal
                """,
                (plan, plan),
            ).fetchall()
            if not rows:
                connection.commit()
                return None
            selected = None
            last_authorization_error: DispatchAuthorizationError | None = None
            for row in rows:
                try:
                    scope = self.authorities.scope(
                        self._reference_from_row(row),
                        dispatcher_id=dispatcher,
                    )
                except DispatchAuthorizationError as exc:
                    last_authorization_error = exc
                    continue
                if scope.aggregate_cost_ceiling_usd != row[
                    "aggregate_cost_ceiling_usd"
                ]:
                    raise DispatchAuthorizationError(
                        "batch authorization aggregate cost mismatch"
                    )
                if (
                    row["ordinal"] >= len(scope.ordered_members)
                    or scope.ordered_members[row["ordinal"]]
                    != self._scope_member_from_row(row)
                ):
                    raise DispatchAuthorizationError(
                        "batch authorization member scope mismatch"
                    )
                selected = row
                break
            if selected is None:
                assert last_authorization_error is not None
                raise last_authorization_error
            reserved = connection.execute(
                """
                SELECT COALESCE(SUM(
                    CASE
                        WHEN state IN ('claimed', 'reconciliation_required')
                            THEN cost_ceiling_usd
                        WHEN state IN ('completed', 'failed')
                            THEN COALESCE(observed_cost_usd, cost_ceiling_usd)
                        ELSE 0
                    END
                ), 0)
                FROM plan_queue_members WHERE plan_digest = ?
                """,
                (selected["plan_digest"],),
            ).fetchone()[0]
            projected = float(reserved) + selected["cost_ceiling_usd"]
            if projected > selected["aggregate_cost_ceiling_usd"] + 1e-12:
                raise DispatchLeaseError(
                    "batch aggregate cost ceiling would be exceeded"
                )
            connection.execute(
                "UPDATE fencing_counter SET value = value + 1 WHERE singleton = 1"
            )
            token = connection.execute(
                "SELECT value FROM fencing_counter WHERE singleton = 1"
            ).fetchone()[0]
            expires_at = (now + timedelta(seconds=ttl)).isoformat()
            changed = connection.execute(
                """
                UPDATE plan_queue_members
                SET state = 'claimed', lease_holder = ?, fencing_token = ?,
                    lease_expires_at = ?, attempts = 1
                WHERE member_id = ? AND state = 'queued' AND attempts = 0
                """,
                (dispatcher, token, expires_at, selected["member_id"]),
            ).rowcount
            if changed != 1:
                raise DispatchLeaseError("queue member claim lost atomic admission")
            connection.commit()
            return QueueClaim(
                member_id=selected["member_id"],
                plan_digest=selected["plan_digest"],
                ordinal=selected["ordinal"],
                member_digest=selected["member_digest"],
                provider_id=selected["provider_id"],
                route_id=selected["route_id"],
                role_digest=selected["role_digest"],
                privacy=selected["privacy"],
                context_class=selected["context_class"],
                cost_ceiling_usd=selected["cost_ceiling_usd"],
                dispatcher_id=dispatcher,
                fencing_token=token,
                lease_expires_at=expires_at,
                attempts=1,
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def renew(
        self,
        member_id: str,
        dispatcher_id: str,
        fencing_token: int,
        *,
        lease_seconds: int = 300,
    ) -> QueueClaim:
        member = _digest("member_id", member_id)
        dispatcher = _identifier("dispatcher_id", dispatcher_id)
        ttl = _ttl(lease_seconds)
        if (
            isinstance(fencing_token, bool)
            or not isinstance(fencing_token, int)
            or fencing_token < 1
        ):
            raise ValueError("fencing_token must be positive integer")
        now = self._current_time()
        connection = self.database.connect()
        expired = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM plan_queue_members WHERE member_id = ?",
                (member,),
            ).fetchone()
            if row is None:
                raise DispatchLeaseError("queue member does not exist")
            if row["state"] != QueueMemberState.CLAIMED.value:
                raise DispatchLeaseError("queue member is terminal or not claimed")
            if (
                row["lease_holder"] != dispatcher
                or row["fencing_token"] != fencing_token
            ):
                raise DispatchLeaseError(
                    "queue lease holder or fencing token is invalid"
                )
            if _aware(row["lease_expires_at"]) <= now:
                connection.execute(
                    """
                    UPDATE plan_queue_members
                    SET state = 'reconciliation_required', terminal_at = ?
                    WHERE member_id = ?
                    """,
                    (now.isoformat(), member),
                )
                connection.commit()
                expired = True
            else:
                expires_at = (now + timedelta(seconds=ttl)).isoformat()
                connection.execute(
                    """
                    UPDATE plan_queue_members SET lease_expires_at = ?
                    WHERE member_id = ?
                    """,
                    (expires_at, member),
                )
                connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        if expired:
            raise DispatchLeaseError(
                "expired queue lease requires reconciliation and cannot renew"
            )
        return QueueClaim(
            member_id=row["member_id"],
            plan_digest=row["plan_digest"],
            ordinal=row["ordinal"],
            member_digest=row["member_digest"],
            provider_id=row["provider_id"],
            route_id=row["route_id"],
            role_digest=row["role_digest"],
            privacy=row["privacy"],
            context_class=row["context_class"],
            cost_ceiling_usd=row["cost_ceiling_usd"],
            dispatcher_id=dispatcher,
            fencing_token=fencing_token,
            lease_expires_at=expires_at,
            attempts=row["attempts"],
        )

    def _terminal(
        self,
        state: QueueMemberState,
        member_id: str,
        dispatcher_id: str,
        fencing_token: int,
        *,
        terminal_evidence_digest: str,
        observed_cost_usd: float | None,
    ) -> QueueMemberRecord:
        if state not in {QueueMemberState.COMPLETED, QueueMemberState.FAILED}:
            raise ValueError("terminal state is invalid")
        member = _digest("member_id", member_id)
        dispatcher = _identifier("dispatcher_id", dispatcher_id)
        evidence = _digest(
            "terminal_evidence_digest",
            terminal_evidence_digest,
        )
        cost = (
            _cost("observed_cost_usd", observed_cost_usd)
            if observed_cost_usd is not None
            else None
        )
        if (
            isinstance(fencing_token, bool)
            or not isinstance(fencing_token, int)
            or fencing_token < 1
        ):
            raise ValueError("fencing_token must be positive integer")
        now = self._current_time()
        connection = self.database.connect()
        post_commit_error: DispatchLeaseError | DispatchAuthorizationError | None = None
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM plan_queue_members WHERE member_id = ?",
                (member,),
            ).fetchone()
            if row is None:
                raise DispatchLeaseError("queue member does not exist")
            if row["state"] != QueueMemberState.CLAIMED.value:
                raise DispatchLeaseError("queue member is terminal or not claimed")
            if (
                row["lease_holder"] != dispatcher
                or row["fencing_token"] != fencing_token
            ):
                raise DispatchLeaseError(
                    "queue lease holder or fencing token is invalid"
                )
            if _aware(row["lease_expires_at"]) <= now:
                next_state = QueueMemberState.RECONCILIATION_REQUIRED
                post_commit_error = DispatchLeaseError(
                    "expired queue lease requires reconciliation"
                )
            elif cost > row["cost_ceiling_usd"] + 1e-12:
                next_state = QueueMemberState.RECONCILIATION_REQUIRED
                post_commit_error = DispatchAuthorizationError(
                    "observed cost exceeds member hard ceiling"
                )
            else:
                next_state = state
            connection.execute(
                """
                UPDATE plan_queue_members
                SET state = ?, terminal_at = ?, terminal_evidence_digest = ?,
                    observed_cost_usd = ?
                WHERE member_id = ?
                """,
                (
                    next_state.value,
                    now.isoformat(),
                    evidence,
                    cost,
                    member,
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
        return self.read_member(member)

    def complete(
        self,
        member_id: str,
        dispatcher_id: str,
        fencing_token: int,
        *,
        terminal_evidence_digest: str,
        observed_cost_usd: float,
    ) -> QueueMemberRecord:
        return self._terminal(
            QueueMemberState.COMPLETED,
            member_id,
            dispatcher_id,
            fencing_token,
            terminal_evidence_digest=terminal_evidence_digest,
            observed_cost_usd=observed_cost_usd,
        )

    def fail(
        self,
        member_id: str,
        dispatcher_id: str,
        fencing_token: int,
        *,
        terminal_evidence_digest: str,
        observed_cost_usd: float,
    ) -> QueueMemberRecord:
        return self._terminal(
            QueueMemberState.FAILED,
            member_id,
            dispatcher_id,
            fencing_token,
            terminal_evidence_digest=terminal_evidence_digest,
            observed_cost_usd=observed_cost_usd,
        )

    def require_reconciliation(
        self,
        member_id: str,
        dispatcher_id: str,
        fencing_token: int,
        *,
        terminal_evidence_digest: str,
        observed_cost_usd: float,
    ) -> QueueMemberRecord:
        member = _digest("member_id", member_id)
        dispatcher = _identifier("dispatcher_id", dispatcher_id)
        evidence = _digest(
            "terminal_evidence_digest",
            terminal_evidence_digest,
        )
        cost = _cost("observed_cost_usd", observed_cost_usd)
        if (
            isinstance(fencing_token, bool)
            or not isinstance(fencing_token, int)
            or fencing_token < 1
        ):
            raise ValueError("fencing_token must be positive integer")
        now = self._current_time()
        connection = self.database.connect()
        expired = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM plan_queue_members WHERE member_id = ?",
                (member,),
            ).fetchone()
            if row is None:
                raise DispatchLeaseError("queue member does not exist")
            if row["state"] != QueueMemberState.CLAIMED.value:
                raise DispatchLeaseError("queue member is terminal or not claimed")
            if (
                row["lease_holder"] != dispatcher
                or row["fencing_token"] != fencing_token
            ):
                raise DispatchLeaseError(
                    "queue lease holder or fencing token is invalid"
                )
            expired = _aware(row["lease_expires_at"]) <= now
            connection.execute(
                """
                UPDATE plan_queue_members
                SET state = 'reconciliation_required', terminal_at = ?,
                    terminal_evidence_digest = ?, observed_cost_usd = ?
                WHERE member_id = ?
                """,
                (now.isoformat(), evidence, cost, member),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        if expired:
            raise DispatchLeaseError(
                "expired queue lease requires reconciliation but was not active"
            )
        return self.read_member(member)

    def resolve_reconciliation(
        self,
        member_id: str,
        *,
        terminal_state: QueueMemberState,
        reconciliation_evidence_digest: str,
        observed_cost_usd: float,
    ) -> QueueMemberRecord:
        member = _digest("member_id", member_id)
        if terminal_state not in {
            QueueMemberState.COMPLETED,
            QueueMemberState.FAILED,
        }:
            raise ValueError("reconciliation terminal_state is invalid")
        evidence = _digest(
            "reconciliation_evidence_digest",
            reconciliation_evidence_digest,
        )
        cost = _cost("observed_cost_usd", observed_cost_usd)
        connection = self.database.connect()
        try:
            row = connection.execute(
                """
                SELECT m.*, b.authority_id, b.authority_digest,
                       b.authority_revision
                FROM plan_queue_members AS m
                JOIN plan_queue_batches AS b USING(plan_digest)
                WHERE member_id = ?
                """,
                (member,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise DispatchLeaseError("queue member does not exist")
        if row["state"] != QueueMemberState.RECONCILIATION_REQUIRED.value:
            raise DispatchLeaseError(
                "queue member does not require reconciliation"
            )
        if (
            terminal_state is QueueMemberState.COMPLETED
            and cost > row["cost_ceiling_usd"] + 1e-12
        ):
            raise DispatchAuthorizationError(
                "over-ceiling reconciliation cannot complete successfully"
            )
        batch_reference = BatchAuthorityReference(
            authority_id=row["authority_id"],
            digest=row["authority_digest"],
            revision=row["authority_revision"],
            plan_digest=row["plan_digest"],
        )
        self.authorities.revoke(batch_reference)
        now = self._current_time().isoformat()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute(
                """
                UPDATE plan_queue_members
                SET state = ?, terminal_at = ?, terminal_evidence_digest = ?,
                    observed_cost_usd = ?
                WHERE member_id = ? AND state = 'reconciliation_required'
                """,
                (terminal_state.value, now, evidence, cost, member),
            ).rowcount
            if changed != 1:
                raise DispatchLeaseError(
                    "queue reconciliation lost atomic resolution"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.read_member(member)

    @staticmethod
    def _record(row) -> QueueMemberRecord:
        try:
            state = QueueMemberState(row["state"])
        except ValueError as exc:
            raise DispatchLeaseError("queue member state is invalid") from exc
        return QueueMemberRecord(
            member_id=row["member_id"],
            plan_digest=row["plan_digest"],
            ordinal=row["ordinal"],
            member_digest=row["member_digest"],
            state=state,
            lease_holder=row["lease_holder"],
            fencing_token=row["fencing_token"],
            lease_expires_at=row["lease_expires_at"],
            attempts=row["attempts"],
            terminal_at=row["terminal_at"],
            terminal_evidence_digest=row["terminal_evidence_digest"],
            observed_cost_usd=row["observed_cost_usd"],
        )

    def read_member(self, member_id: str) -> QueueMemberRecord:
        member = _digest("member_id", member_id)
        connection = self.database.connect()
        try:
            row = connection.execute(
                "SELECT * FROM plan_queue_members WHERE member_id = ?",
                (member,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise DispatchLeaseError("queue member does not exist")
        return self._record(row)

    def list_members(self, plan_digest: str) -> tuple[QueueMemberRecord, ...]:
        plan = _digest("plan_digest", plan_digest)
        connection = self.database.connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM plan_queue_members
                WHERE plan_digest = ? ORDER BY ordinal
                """,
                (plan,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(self._record(row) for row in rows)

    def list_by_state(
        self,
        state: QueueMemberState,
        *,
        limit: int = 100,
        after_member_id: str | None = None,
    ) -> tuple[QueueMemberRecord, ...]:
        if not isinstance(state, QueueMemberState):
            raise ValueError("state must be a QueueMemberState")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 1000
        ):
            raise ValueError("limit must be between 1 and 1000")
        cursor = (
            None
            if after_member_id is None
            else _digest("after_member_id", after_member_id)
        )
        now = self._current_time()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._mark_expired_claims(connection, now)
            parameters: list[object] = [state.value]
            cursor_clause = ""
            if cursor is not None:
                cursor_row = connection.execute(
                    "SELECT * FROM plan_queue_members WHERE member_id = ?",
                    (cursor,),
                ).fetchone()
                if cursor_row is None or cursor_row["state"] != state.value:
                    raise DispatchLeaseError(
                        "queue cursor does not resolve to the requested state"
                    )
                cursor_clause = """
                    AND (
                        plan_digest > ?
                        OR (plan_digest = ? AND ordinal > ?)
                        OR (plan_digest = ? AND ordinal = ? AND member_id > ?)
                    )
                """
                parameters.extend(
                    (
                        cursor_row["plan_digest"],
                        cursor_row["plan_digest"],
                        cursor_row["ordinal"],
                        cursor_row["plan_digest"],
                        cursor_row["ordinal"],
                        cursor_row["member_id"],
                    )
                )
            parameters.append(limit)
            rows = connection.execute(
                f"""
                SELECT * FROM plan_queue_members
                WHERE state = ? {cursor_clause}
                ORDER BY plan_digest, ordinal, member_id
                LIMIT ?
                """,
                tuple(parameters),
            ).fetchall()
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return tuple(self._record(row) for row in rows)

    def state_counts(self) -> dict[str, int]:
        now = self._current_time()
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._mark_expired_claims(connection, now)
            rows = connection.execute(
                """
                SELECT state, COUNT(*) AS count
                FROM plan_queue_members GROUP BY state
                """
            ).fetchall()
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        observed = {row["state"]: row["count"] for row in rows}
        return {
            state.value: int(observed.get(state.value, 0))
            for state in QueueMemberState
        }


QueueMemberSpec = QueueMember
QueueTargetClaim = TargetClaim
QueuePlan = T1QueuePlan


__all__ = [
    "PlanQueue",
    "QueueClaim",
    "QueueMember",
    "QueueMemberRecord",
    "QueueMemberSpec",
    "QueueMemberState",
    "QueuePlan",
    "QueueTargetClaim",
    "T1QueuePlan",
    "TargetClaim",
]
