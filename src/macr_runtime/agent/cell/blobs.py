from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from ...errors import StoragePolicyError
from .contracts import HostedBlobRef, HostedBlobRole


def _is_reparse(path: Path) -> bool:
    return path.is_symlink() or (
        hasattr(os.path, "isjunction") and os.path.isjunction(path)
    )


def _ensure_safe_directory(path: Path) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        candidate = current / component
        if _is_reparse(candidate):
            raise StoragePolicyError(
                "hosted Agent blob ancestry may not contain a reparse point"
            )
        if not candidate.exists():
            try:
                candidate.mkdir()
            except FileExistsError:
                pass
        if _is_reparse(candidate) or not candidate.is_dir():
            raise StoragePolicyError(
                "hosted Agent blob ancestry must contain ordinary directories"
            )
        current = candidate


def _require_safe_existing_directory(path: Path) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        candidate = current / component
        if not candidate.exists() or _is_reparse(candidate) or not candidate.is_dir():
            raise StoragePolicyError("hosted Agent blob ancestry is missing or unsafe")
        current = candidate


class HostedAgentBlobStore:
    def __init__(self, root: str | Path) -> None:
        candidate = Path(root)
        if not candidate.is_absolute() or candidate.drive.upper() != "D:":
            raise StoragePolicyError("hosted Agent blob root must be absolute on D:")
        self.root = candidate.absolute()
        _ensure_safe_directory(self.root)

    def _target(
        self,
        agent_run_id: str,
        role: HostedBlobRole,
        digest: str,
    ) -> Path:
        reference = HostedBlobRef(agent_run_id, role, digest, 0)
        return self.root / reference.agent_run_id / role.value / f"{digest}.bin"

    def write(
        self,
        agent_run_id: str,
        role: HostedBlobRole,
        data: bytes,
    ) -> HostedBlobRef:
        if not isinstance(role, HostedBlobRole):
            raise ValueError("role must be a HostedBlobRole")
        if not isinstance(data, bytes):
            raise ValueError("hosted Agent blob data must be bytes")
        digest = hashlib.sha256(data).hexdigest()
        reference = HostedBlobRef(agent_run_id, role, digest, len(data))
        target = self._target(reference.agent_run_id, role, digest)
        _ensure_safe_directory(target.parent)
        if _is_reparse(target):
            raise StoragePolicyError("hosted Agent blob may not be a reparse point")
        if target.exists():
            self._read_verified_target(target, reference)
            return reference

        temporary = target.parent / f".{uuid.uuid4()}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                pass
            self._read_verified_target(target, reference)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        return reference

    @staticmethod
    def _read_verified_target(target: Path, reference: HostedBlobRef) -> bytes:
        if _is_reparse(target) or not target.is_file():
            raise StoragePolicyError(
                "hosted Agent blob must be an ordinary immutable file"
            )
        data = target.read_bytes()
        if (
            len(data) != reference.byte_count
            or hashlib.sha256(data).hexdigest() != reference.sha256
        ):
            raise StoragePolicyError(
                "hosted Agent blob bytes conflict with their digest"
            )
        return data

    def read(self, reference: HostedBlobRef) -> bytes:
        if not isinstance(reference, HostedBlobRef):
            raise ValueError("reference must be a HostedBlobRef")
        target = self._target(
            reference.agent_run_id,
            reference.role,
            reference.sha256,
        )
        _require_safe_existing_directory(target.parent)
        return self._read_verified_target(target, reference)

    def delete_projection_cache(self, reference: HostedBlobRef) -> bool:
        if not isinstance(reference, HostedBlobRef):
            raise ValueError("reference must be a HostedBlobRef")
        if reference.role is not HostedBlobRole.PROJECTION:
            raise StoragePolicyError(
                "only derived hosted projection blobs are deletable"
            )
        target = self._target(
            reference.agent_run_id,
            reference.role,
            reference.sha256,
        )
        _require_safe_existing_directory(target.parent)
        if _is_reparse(target):
            raise StoragePolicyError("hosted projection cache is a reparse point")
        try:
            target.unlink()
        except FileNotFoundError:
            return False
        return True

    def exists(self, reference: HostedBlobRef) -> bool:
        if not isinstance(reference, HostedBlobRef):
            raise ValueError("reference must be a HostedBlobRef")
        target = self._target(
            reference.agent_run_id,
            reference.role,
            reference.sha256,
        )
        try:
            _require_safe_existing_directory(target.parent)
        except StoragePolicyError:
            return False
        if _is_reparse(target):
            raise StoragePolicyError("hosted Agent blob is a reparse point")
        return target.is_file()
