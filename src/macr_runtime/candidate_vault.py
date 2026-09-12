from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import CandidateConflict, StoragePolicyError
from .execution import DispatchOrigin
from .runtime_db import RuntimeDatabase


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_d_path(name: str, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute() or path.drive.upper() != "D:":
        raise StoragePolicyError(f"{name} must be absolute on D:")
    return path.absolute()


def _is_reparse(path: Path) -> bool:
    return path.is_symlink() or (
        hasattr(os.path, "isjunction") and os.path.isjunction(path)
    )


def _check_existing_ancestry(path: Path) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current = current / component
        if _is_reparse(current):
            raise StoragePolicyError(
                "candidate path ancestry may not contain a reparse point"
            )
        if not current.exists():
            return


def _ensure_directory(path: Path) -> None:
    _check_existing_ancestry(path)
    current = Path(path.anchor)
    for component in path.parts[1:]:
        candidate = current / component
        if _is_reparse(candidate):
            raise StoragePolicyError(
                "candidate path ancestry may not contain a reparse point"
            )
        if not candidate.exists():
            try:
                candidate.mkdir()
            except FileExistsError:
                # Another process may have created the same provider/root
                # directory after the existence check. Validate the winner
                # below instead of treating a safe concurrent mkdir as a
                # capture failure.
                pass
        if _is_reparse(candidate):
            raise StoragePolicyError(
                "candidate path ancestry may not contain a reparse point"
            )
        if not candidate.is_dir():
            raise StoragePolicyError(
                "candidate path ancestry must contain only directories"
            )
        current = candidate
        _check_existing_ancestry(current)


def _digest(name: str, value: str) -> str:
    normalized = value.lower() if isinstance(value, str) else ""
    if not _SHA256.fullmatch(normalized):
        raise ValueError(f"{name} must be a SHA-256 hex digest")
    return normalized


def _uuid4(name: str, value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a UUIDv4 string") from exc
    if parsed.version != 4 or str(parsed) != value.lower():
        raise ValueError(f"{name} must be a UUIDv4 string")
    return str(parsed)


def _safe_component(name: str, value: str) -> str:
    if not isinstance(value, str) or not _SAFE_COMPONENT.fullmatch(value):
        raise ValueError(f"{name} must be a safe identifier")
    return value


def _origin_json(origin: DispatchOrigin) -> str:
    if not isinstance(origin, DispatchOrigin):
        raise ValueError("builder_origin must be a DispatchOrigin")
    return json.dumps(
        {
            "host": origin.host,
            "identifier_kind": origin.identifier_kind,
            "native_id": origin.native_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True)
class CandidateCapture:
    capture_id: str
    run_id: str
    provider_id: str
    sha256: str
    byte_count: int
    relative_path: str
    task_digest: str
    approval_digest: str | None
    captured_at: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "capture_id": self.capture_id,
            "run_id": self.run_id,
            "provider_id": self.provider_id,
            "answer_sha256": self.sha256,
            "answer_bytes": self.byte_count,
            "task_digest": self.task_digest,
            "approval_digest": self.approval_digest,
            "captured_at": self.captured_at,
        }


@dataclass(frozen=True)
class MaterializationRecord:
    materialization_id: str
    capture_id: str
    state: str
    output_sha256: str
    output_bytes: int
    transformer_version: str | None
    created_at: str


class CandidateVault:
    def __init__(
        self,
        root: str | Path,
        database_path: str | Path,
    ) -> None:
        self.root = _validate_d_path("candidate root", root)
        _check_existing_ancestry(self.root)
        _ensure_directory(self.root)
        self.database = RuntimeDatabase(database_path)

    def capture(
        self,
        provider_id: str,
        run_id: str,
        answer_bytes: bytes,
        *,
        task_digest: str,
        approval_digest: str | None,
    ) -> CandidateCapture:
        provider = _safe_component("provider_id", provider_id)
        run = _uuid4("run_id", run_id)
        if not isinstance(answer_bytes, bytes):
            raise ValueError("answer_bytes must be bytes")
        task_hash = _digest("task_digest", task_digest)
        approval_hash = (
            _digest("approval_digest", approval_digest)
            if approval_digest is not None
            else None
        )
        answer_sha256 = hashlib.sha256(answer_bytes).hexdigest()
        relative_path = (Path(provider) / run / "answer.bin").as_posix()
        target = self.root / Path(relative_path)
        _ensure_directory(target.parent)
        self._write_once(target, answer_bytes)
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM candidate_captures WHERE run_id = ?",
                (run,),
            ).fetchone()
            if existing is not None:
                expected = (
                    provider,
                    answer_sha256,
                    len(answer_bytes),
                    relative_path,
                    task_hash,
                    approval_hash,
                )
                actual = (
                    existing["provider_id"],
                    existing["answer_sha256"],
                    existing["answer_bytes"],
                    existing["relative_path"],
                    existing["task_digest"],
                    existing["approval_digest"],
                )
                if actual != expected:
                    raise CandidateConflict(
                        "candidate run already contains different bytes or provenance"
                    )
                connection.commit()
                return self._capture_from_row(existing)
            capture_id = str(uuid.uuid4())
            captured_at = _utc_now()
            connection.execute(
                """
                INSERT INTO candidate_captures(
                    capture_id, run_id, provider_id, answer_sha256,
                    answer_bytes, relative_path, task_digest,
                    approval_digest, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    capture_id,
                    run,
                    provider,
                    answer_sha256,
                    len(answer_bytes),
                    relative_path,
                    task_hash,
                    approval_hash,
                    captured_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM candidate_captures WHERE capture_id = ?",
                (capture_id,),
            ).fetchone()
            connection.commit()
            return self._capture_from_row(row)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def read(self, capture_id: str) -> bytes:
        capture = self._get_capture(capture_id=capture_id)
        target = self.root / Path(capture.relative_path)
        _check_existing_ancestry(target)
        if (
            not target.is_file()
            or _is_reparse(target)
            or target.stat().st_size != capture.byte_count
        ):
            raise CandidateConflict("candidate capture file is missing or invalid")
        data = target.read_bytes()
        if hashlib.sha256(data).hexdigest() != capture.sha256:
            raise CandidateConflict("candidate capture hash mismatch")
        return data

    def read_by_run(self, run_id: str) -> CandidateCapture | None:
        run = _uuid4("run_id", run_id)
        connection = self.database.connect()
        try:
            row = connection.execute(
                "SELECT * FROM candidate_captures WHERE run_id = ?",
                (run,),
            ).fetchone()
        finally:
            connection.close()
        return self._capture_from_row(row) if row is not None else None

    def purge_direct_run(
        self,
        provider_id: str,
        run_id: str,
        *,
        confirmation: str,
    ) -> bool:
        provider = _safe_component("provider_id", provider_id)
        run = _uuid4("run_id", run_id)
        if confirmation != "DELETE":
            raise ValueError("candidate purge requires exact DELETE confirmation")
        capture = self.read_by_run(run)
        if capture is None:
            return False
        if capture.provider_id != provider:
            raise CandidateConflict(
                "candidate purge provider does not match capture"
            )
        connection = self.database.connect()
        try:
            materialization = connection.execute(
                """SELECT 1 FROM materializations
                WHERE capture_id = ? LIMIT 1""",
                (capture.capture_id,),
            ).fetchone()
        finally:
            connection.close()
        if materialization is not None:
            raise CandidateConflict(
                "candidate purge refuses a materialized capture"
            )
        target = self.root / Path(capture.relative_path)
        _check_existing_ancestry(target)
        if not target.exists():
            return False
        if not target.is_file() or _is_reparse(target):
            raise CandidateConflict("candidate purge target is not a regular file")
        with target.open("r+b") as handle:
            remaining = capture.byte_count
            zeroes = b"\0" * min(1024 * 1024, max(1, remaining))
            while remaining > 0:
                chunk = zeroes[: min(len(zeroes), remaining)]
                handle.write(chunk)
                remaining -= len(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        target.unlink()
        run_directory = target.parent
        provider_directory = run_directory.parent
        for directory in (run_directory, provider_directory):
            try:
                if directory != self.root and not any(directory.iterdir()):
                    directory.rmdir()
            except OSError:
                # Candidate bytes are already gone. Empty-directory cleanup is
                # cosmetic and may be delayed by Windows scanners/handles.
                pass
        return True

    def materialize_verbatim(
        self,
        capture_id: str,
        target_path: str | Path,
        *,
        builder_origin: DispatchOrigin,
    ) -> MaterializationRecord:
        capture = self._get_capture(capture_id=capture_id)
        data = self.read(capture.capture_id)
        target = _validate_d_path("materialization target", target_path)
        _ensure_directory(target.parent)
        self._write_once(target, data)
        return self._record_materialization(
            capture=capture,
            state="verbatim",
            output_bytes=data,
            relative_path=None,
            target_path_sha256=hashlib.sha256(
                str(target).lower().encode("utf-8")
            ).hexdigest(),
            transformer_version=None,
            builder_origin=builder_origin,
        )

    def record_transformation(
        self,
        capture_id: str,
        transformed_bytes: bytes,
        *,
        transformer_version: str,
        builder_origin: DispatchOrigin,
    ) -> MaterializationRecord:
        capture = self._get_capture(capture_id=capture_id)
        if not isinstance(transformed_bytes, bytes):
            raise ValueError("transformed_bytes must be bytes")
        transformer = _safe_component(
            "transformer_version",
            transformer_version,
        )
        output_sha256 = hashlib.sha256(transformed_bytes).hexdigest()
        relative_path = (
            Path(capture.provider_id)
            / capture.run_id
            / "transforms"
            / f"{output_sha256}.bin"
        ).as_posix()
        target = self.root / Path(relative_path)
        _ensure_directory(target.parent)
        self._write_once(target, transformed_bytes)
        return self._record_materialization(
            capture=capture,
            state="transformed",
            output_bytes=transformed_bytes,
            relative_path=relative_path,
            target_path_sha256=None,
            transformer_version=transformer,
            builder_origin=builder_origin,
        )

    def _get_capture(self, *, capture_id: str) -> CandidateCapture:
        normalized_id = _uuid4("capture_id", capture_id)
        connection = self.database.connect()
        try:
            row = connection.execute(
                "SELECT * FROM candidate_captures WHERE capture_id = ?",
                (normalized_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise CandidateConflict("candidate capture is missing")
        return self._capture_from_row(row)

    def _record_materialization(
        self,
        *,
        capture: CandidateCapture,
        state: str,
        output_bytes: bytes,
        relative_path: str | None,
        target_path_sha256: str | None,
        transformer_version: str | None,
        builder_origin: DispatchOrigin,
    ) -> MaterializationRecord:
        output_sha256 = hashlib.sha256(output_bytes).hexdigest()
        origin_json = _origin_json(builder_origin)
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM materializations
                WHERE capture_id = ? AND state = ? AND output_sha256 = ?
                  AND COALESCE(relative_path, '') = COALESCE(?, '')
                  AND COALESCE(target_path_sha256, '') = COALESCE(?, '')
                  AND COALESCE(transformer_version, '') = COALESCE(?, '')
                  AND builder_origin_json = ?
                """,
                (
                    capture.capture_id,
                    state,
                    output_sha256,
                    relative_path,
                    target_path_sha256,
                    transformer_version,
                    origin_json,
                ),
            ).fetchone()
            if row is None:
                materialization_id = str(uuid.uuid4())
                created_at = _utc_now()
                connection.execute(
                    """
                    INSERT INTO materializations(
                        materialization_id, capture_id, state,
                        output_sha256, output_bytes, relative_path,
                        target_path_sha256, transformer_version,
                        builder_origin_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        materialization_id,
                        capture.capture_id,
                        state,
                        output_sha256,
                        len(output_bytes),
                        relative_path,
                        target_path_sha256,
                        transformer_version,
                        origin_json,
                        created_at,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM materializations WHERE materialization_id = ?",
                    (materialization_id,),
                ).fetchone()
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self._materialization_from_row(row)

    @staticmethod
    def _capture_from_row(row: Any) -> CandidateCapture:
        return CandidateCapture(
            capture_id=row["capture_id"],
            run_id=row["run_id"],
            provider_id=row["provider_id"],
            sha256=row["answer_sha256"],
            byte_count=row["answer_bytes"],
            relative_path=row["relative_path"],
            task_digest=row["task_digest"],
            approval_digest=row["approval_digest"],
            captured_at=row["captured_at"],
        )

    @staticmethod
    def _materialization_from_row(row: Any) -> MaterializationRecord:
        return MaterializationRecord(
            materialization_id=row["materialization_id"],
            capture_id=row["capture_id"],
            state=row["state"],
            output_sha256=row["output_sha256"],
            output_bytes=row["output_bytes"],
            transformer_version=row["transformer_version"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _write_once(target: Path, data: bytes) -> None:
        _check_existing_ancestry(target)
        if target.exists():
            if not target.is_file() or _is_reparse(target):
                raise CandidateConflict("candidate target is not a regular file")
            if target.read_bytes() != data:
                raise CandidateConflict("candidate target contains different bytes")
            return
        temporary = target.with_name(f".{target.name}.{uuid.uuid4()}.tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                if (
                    not target.is_file()
                    or _is_reparse(target)
                    or target.read_bytes() != data
                ):
                    raise CandidateConflict(
                        "candidate target contains different bytes"
                    )
            if (
                not target.is_file()
                or _is_reparse(target)
                or target.read_bytes() != data
            ):
                raise CandidateConflict("candidate target readback mismatch")
        finally:
            temporary.unlink(missing_ok=True)
