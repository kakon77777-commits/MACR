from __future__ import annotations

import hashlib
import hmac
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
_FIELDS_V1 = frozenset(
    {
        "schema_version",
        "provider_id",
        "approval_sha256",
        "approved_by",
        "approved_at",
        "expires_at",
        "nonce",
        "mac_sha256",
    }
)
_FIELDS_V2 = _FIELDS_V1 | frozenset(
    {
        "approval_contract_schema",
        "provider_tier_binding_digest",
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
        absolute_state = self.state_root.absolute()
        current = Path(absolute_state.anchor)
        for component in absolute_state.parts[1:]:
            current = current / component
            if current.exists() and self._is_reparse(current):
                raise ValueError(
                    "GLM approval state-root ancestry may not contain a reparse point"
                )
        self.state_root = absolute_state.resolve(strict=False)
        self.root = self.state_root / "approvals" / "glm"
        self._now = now

    @staticmethod
    def _is_reparse(path: Path) -> bool:
        return path.is_symlink() or (
            hasattr(os.path, "isjunction") and os.path.isjunction(path)
        )

    @staticmethod
    def _record_mac(document: dict[str, Any], signing_key: str) -> str:
        if not isinstance(signing_key, str) or not signing_key:
            raise ValueError("approval signing key must be non-empty")
        body = {
            key: value
            for key, value in document.items()
            if key != "mac_sha256"
        }
        encoded = json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hmac.new(
            signing_key.encode("utf-8"),
            encoded,
            hashlib.sha256,
        ).hexdigest()

    def _ensure_root(self) -> None:
        self._check_root_ancestry()
        if not self.state_root.is_dir():
            raise ProviderPolicyError(
                "GLM approval state root must already exist as a directory"
            )
        current = self.state_root
        for component in self.root.relative_to(self.state_root).parts:
            candidate = current / component
            if self._is_reparse(candidate):
                raise ProviderPolicyError(
                    "GLM approval-root ancestry contains a reparse point"
                )
            if candidate.exists():
                if not candidate.is_dir():
                    raise ProviderPolicyError(
                        "GLM approval-root ancestry must contain only directories"
                    )
            else:
                candidate.mkdir()
            current = candidate
            self._check_root_ancestry()

    def _check_root_ancestry(self) -> None:
        current = Path(self.state_root.anchor)
        for component in self.state_root.parts[1:]:
            current = current / component
            if self._is_reparse(current):
                raise ProviderPolicyError(
                    "GLM approval state-root ancestry contains a reparse point"
                )
            if not current.exists():
                return
        for component in self.root.relative_to(self.state_root).parts:
            current = current / component
            if self._is_reparse(current):
                raise ProviderPolicyError(
                    "GLM approval-root ancestry contains a reparse point"
                )
            if not current.exists():
                return

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
        signing_key: str,
        expires_in_days: int,
        replace_existing: bool = False,
        approval_contract_schema: int | None = None,
        provider_tier_binding_digest: str | None = None,
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
        typed = (
            approval_contract_schema is not None
            or provider_tier_binding_digest is not None
        )
        if typed and (
            approval_contract_schema != 3
            or not isinstance(provider_tier_binding_digest, str)
            or not _SHA256.fullmatch(provider_tier_binding_digest)
        ):
            raise ValueError(
                "typed GLM approval requires schema 3 and a tier binding digest"
            )
        document = {
            "schema_version": 2 if typed else 1,
            "provider_id": "glm_flash_worker",
            "approval_sha256": digest,
            "approved_by": "host_operator",
            "approved_at": now.isoformat(),
            "expires_at": (now + timedelta(days=expires_in_days)).isoformat(),
            "nonce": str(uuid.uuid4()),
        }
        if typed:
            document["approval_contract_schema"] = approval_contract_schema
            document["provider_tier_binding_digest"] = (
                provider_tier_binding_digest
            )
        document["mac_sha256"] = self._record_mac(document, signing_key)
        self._ensure_root()
        path = self.record_path(digest)
        if path.exists():
            if not replace_existing:
                return self.verify(digest, signing_key=signing_key)
            history_root = self.root / "history"
            history_root.mkdir(exist_ok=True)
            if self._is_reparse(history_root):
                raise ProviderPolicyError(
                    "GLM approval history may not be a reparse point"
                )
            archive_path = history_root / f"{digest}-{uuid.uuid4()}.json"
            os.replace(path, archive_path)
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
            return self.verify(digest, signing_key=signing_key)
        return document

    def _read_document(self, approval_sha256: str) -> tuple[str, dict[str, Any]]:
        digest = self._validate_digest(approval_sha256)
        self._check_root_ancestry()
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
        expected_fields = (
            _FIELDS_V2
            if isinstance(document, dict) and document.get("schema_version") == 2
            else _FIELDS_V1
        )
        if not isinstance(document, dict) or set(document) != expected_fields:
            raise ProviderPolicyError("GLM host approval record is invalid")
        if not isinstance(document.get("mac_sha256"), str) or not _SHA256.fullmatch(
            document["mac_sha256"]
        ):
            raise ProviderPolicyError("GLM host approval record is invalid")
        return digest, document

    def _validate_document(
        self,
        digest: str,
        document: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            approved_at = datetime.fromisoformat(document["approved_at"])
            expires_at = datetime.fromisoformat(document["expires_at"])
            nonce = uuid.UUID(document["nonce"])
        except (TypeError, ValueError, KeyError) as exc:
            raise ProviderPolicyError("GLM host approval record is invalid") from exc
        if (
            document["schema_version"] not in {1, 2}
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
        if document["schema_version"] == 2 and (
            document.get("approval_contract_schema") != 3
            or not isinstance(
                document.get("provider_tier_binding_digest"),
                str,
            )
            or not _SHA256.fullmatch(document["provider_tier_binding_digest"])
        ):
            raise ProviderPolicyError("GLM host approval record is invalid")
        now = self._now()
        if now.tzinfo is None:
            raise ProviderPolicyError("GLM host approval clock is invalid")
        now_utc = now.astimezone(timezone.utc)
        if approved_at.astimezone(timezone.utc) > now_utc + timedelta(minutes=5):
            raise ProviderPolicyError(
                "GLM host approval record is future-dated"
            )
        if now_utc >= expires_at.astimezone(timezone.utc):
            raise ProviderPolicyError("GLM host approval record is expired")
        return dict(document)

    def inspect(self, approval_sha256: str) -> dict[str, Any]:
        digest, document = self._read_document(approval_sha256)
        return self._validate_document(digest, document)

    def verify(
        self,
        approval_sha256: str,
        *,
        signing_key: str,
    ) -> dict[str, Any]:
        digest, document = self._read_document(approval_sha256)
        expected_mac = self._record_mac(document, signing_key)
        if not hmac.compare_digest(document["mac_sha256"], expected_mac):
            raise ProviderPolicyError("GLM host approval record MAC is invalid")
        return self._validate_document(digest, document)

    def status_snapshot(self) -> dict[str, int]:
        counts = {
            "current_typed_count": 0,
            "invalid_count": 0,
            "legacy_pre_tier_count": 0,
            "total_count": 0,
        }
        self._check_root_ancestry()
        if not self.root.is_dir():
            return counts
        for path in self.root.glob("*.json"):
            counts["total_count"] += 1
            try:
                digest = path.stem.lower()
                _, document = self._read_document(digest)
            except ProviderPolicyError:
                counts["invalid_count"] += 1
                continue
            if document["schema_version"] == 2:
                counts["current_typed_count"] += 1
            else:
                counts["legacy_pre_tier_count"] += 1
        return counts
