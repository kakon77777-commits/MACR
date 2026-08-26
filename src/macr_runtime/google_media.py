from __future__ import annotations

import hashlib
import io
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath

from PIL import Image, UnidentifiedImageError

from .contracts import TaskContract
from .errors import ProviderPolicyError


ALLOWED_INPUT_MIME = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/webp",
        "video/mp4",
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "application/pdf",
    }
)
MIME_ALIASES = {"audio/mp3": "audio/mpeg"}
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ValidatedMediaInput:
    relative_path: str
    mime_type: str
    sha256: str
    data: bytes = field(repr=False)


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & flag)


def _workspace_root(task: TaskContract, cwd: Path) -> Path:
    raw = task.workspace.repo
    root = cwd if raw == "current" else Path(raw)
    windows = PureWindowsPath(str(root))
    if not windows.is_absolute() or windows.drive.upper() != "D:":
        raise ProviderPolicyError("Google media workspace must be an absolute D: path")
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise ProviderPolicyError("Google media workspace is unavailable") from exc
    if not resolved.is_dir():
        raise ProviderPolicyError("Google media workspace must be a directory")
    return resolved


def _relative_path(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ProviderPolicyError("Google media path must be a relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ProviderPolicyError("Google media path escapes the workspace")
    return path


def _detected_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video/mp4"
    if data.startswith(b"ID3") or (
        len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0
    ):
        return "audio/mpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def _verify_image(data: bytes) -> None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
    except (OSError, UnidentifiedImageError) as exc:
        raise ProviderPolicyError("Google image input could not be decoded") from exc


def validate_google_media_inputs(
    task: TaskContract,
    *,
    cwd: str | Path | None = None,
) -> tuple[ValidatedMediaInput, ...]:
    root = _workspace_root(task, Path.cwd() if cwd is None else Path(cwd))
    validated: list[ValidatedMediaInput] = []
    total_bytes = 0
    for entry in task.inputs:
        if entry.get("type") != "file":
            raise ProviderPolicyError("Google media inputs must use type=file")
        relative = _relative_path(entry.get("path"))
        try:
            candidate = root.joinpath(*relative.parts).resolve(strict=True)
            candidate.relative_to(root)
        except (OSError, ValueError) as exc:
            raise ProviderPolicyError(
                "Google media path escapes the workspace or is unavailable"
            ) from exc
        if (
            not candidate.is_file()
            or candidate.is_symlink()
            or _is_reparse_point(candidate)
        ):
            raise ProviderPolicyError(
                "Google media input must be a regular non-reparse file"
            )
        declared = entry.get("mime_type")
        if not isinstance(declared, str) or declared not in ALLOWED_INPUT_MIME:
            raise ProviderPolicyError("Google media MIME type is not allowed")
        canonical_mime = MIME_ALIASES.get(declared, declared)
        digest = entry.get("sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ProviderPolicyError("Google media SHA-256 must be lowercase hex")
        data = candidate.read_bytes()
        if len(data) > MAX_FILE_BYTES:
            raise ProviderPolicyError("Google media file exceeds the 20 MiB limit")
        total_bytes += len(data)
        if total_bytes > MAX_TOTAL_BYTES:
            raise ProviderPolicyError("Google media inputs exceed the 32 MiB limit")
        if hashlib.sha256(data).hexdigest() != digest:
            raise ProviderPolicyError("Google media SHA-256 does not match")
        detected = _detected_mime(data)
        if detected != canonical_mime:
            raise ProviderPolicyError("Google media MIME does not match file bytes")
        if detected.startswith("image/"):
            _verify_image(data)
        validated.append(
            ValidatedMediaInput(
                relative_path=relative.as_posix(),
                mime_type=canonical_mime,
                sha256=digest,
                data=data,
            )
        )
    return tuple(validated)
