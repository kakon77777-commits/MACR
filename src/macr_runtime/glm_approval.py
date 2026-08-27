from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .errors import ProviderPolicyError


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = frozenset(
    {
        "schema_version",
        "provider_id",
        "approval_sha256",
        "approved_by",
        "approved_at",
        "expires_at",
        "nonce",
    }
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GlmApprovalStore:
    def __init__(
        self,
        state_root: str | Path,
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.state_root = Path(state_root)
        if not self.state_root.is_absolute() or self.state_root.drive.upper() != "D:":
            raise ValueError("GLM approval state root must be absolute on D:")
        self.root = self.state_root / "approvals" / "glm"
        self._now = now

    @staticmethod
    def _validate_digest(value: str) -> str:
        normalized = value.lower() if isinstance(value, str) else ""
        if not _SHA256.fullmatch(normalized):
            raise ProviderPolicyError("GLM approval digest is invalid")
        return normalized

    def record_path(self, approval_sha256: str) -> Path:
        digest = self._validate_digest(approval_sha256)
        return self.root / f"{digest}.json"

    def create(
        self,
        approval_sha256: str,
        *,
        expires_in_days: int,
    ) -> dict[str, Any]:
        digest = self._validate_digest(approval_sha256)
        if (
            isinstance(expires_in_days, bool)
            or not isinstance(expires_in_days, int)
            or not 1 <= expires_in_days <= 365
        ):
            raise ValueError("expires_in_days must be between 1 and 365")
        now = self._now()
        if now.tzinfo is None:
            raise ValueError("approval clock must be timezone-aware")
        now = now.astimezone(timezone.utc)
        document = {
            "schema_version": 1,
            "provider_id": "glm_flash_worker",
            "approval_sha256": digest,
            "approved_by": "host_operator",
            "approved_at": now.isoformat(),
            "expires_at": (now + timedelta(days=expires_in_days)).isoformat(),
            "nonce": str(uuid.uuid4()),
        }
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.record_path(digest)
        encoded = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        try:
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(encoded)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            return self.verify(digest)
        return document

    def verify(self, approval_sha256: str) -> dict[str, Any]:
        digest = self._validate_digest(approval_sha256)
        path = self.record_path(digest)
        if not path.is_file() or path.is_symlink() or (
            hasattr(os.path, "isjunction") and os.path.isjunction(path)
        ):
            raise ProviderPolicyError("GLM host approval record is missing")
        try:
            if path.stat().st_size > 4096:
                raise ProviderPolicyError("GLM host approval record is invalid")
            document = json.loads(path.read_text(encoding="utf-8"))
        except ProviderPolicyError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProviderPolicyError("GLM host approval record is invalid") from exc
        if not isinstance(document, dict) or set(document) != _FIELDS:
            raise ProviderPolicyError("GLM host approval record is invalid")
        try:
            approved_at = datetime.fromisoformat(document["approved_at"])
            expires_at = datetime.fromisoformat(document["expires_at"])
            nonce = uuid.UUID(document["nonce"])
        except (TypeError, ValueError, KeyError) as exc:
            raise ProviderPolicyError("GLM host approval record is invalid") from exc
        if (
            document["schema_version"] != 1
            or document["provider_id"] != "glm_flash_worker"
            or document["approval_sha256"] != digest
            or document["approved_by"] != "host_operator"
            or nonce.version != 4
            or approved_at.tzinfo is None
            or expires_at.tzinfo is None
            or expires_at <= approved_at
            or expires_at - approved_at > timedelta(days=365)
        ):
            raise ProviderPolicyError("GLM host approval record is invalid")
        now = self._now()
        if now.tzinfo is None:
            raise ProviderPolicyError("GLM host approval clock is invalid")
        if now.astimezone(timezone.utc) >= expires_at.astimezone(timezone.utc):
            raise ProviderPolicyError("GLM host approval record is expired")
        return dict(document)
