from __future__ import annotations

import hashlib
import io
import os
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

from PIL import Image, UnidentifiedImageError

from .errors import ProviderProtocolError, StoragePolicyError


_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MIME_BY_FORMAT = {"JPEG": "image/jpeg", "PNG": "image/png"}
_SUFFIX_BY_MIME = {"image/jpeg": ".jpg", "image/png": ".png"}
MAX_IMAGE_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class ArtifactRecord:
    relative_path: str
    mime_type: str
    width: int
    height: int
    byte_length: int
    sha256: str
    model: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _inspect_image(data: bytes, declared_mime: str) -> tuple[str, int, int]:
    if not 1 <= len(data) <= MAX_IMAGE_BYTES:
        raise ProviderProtocolError("Google image artifact has an invalid size")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            image_format = image.format
            width, height = image.size
    except (OSError, UnidentifiedImageError) as exc:
        raise ProviderProtocolError(
            "Google image artifact could not be decoded"
        ) from exc
    actual_mime = _MIME_BY_FORMAT.get(image_format or "")
    if actual_mime is None:
        raise ProviderProtocolError("Google image artifact MIME is unsupported")
    if declared_mime != actual_mime:
        raise ProviderProtocolError(
            "Google image artifact MIME does not match decoded bytes"
        )
    if width <= 0 or height <= 0:
        raise ProviderProtocolError("Google image artifact dimensions are invalid")
    return actual_mime, width, height


class ImageArtifactStore:
    def __init__(self, state_root: str | Path) -> None:
        self.state_root = Path(state_root)
        windows = PureWindowsPath(str(self.state_root))
        if not windows.is_absolute() or windows.drive.upper() != "D:":
            raise StoragePolicyError("Google artifact state root must be on D:")

    def save_image(
        self,
        task_id: str,
        model: str,
        data: bytes,
        declared_mime: str,
        created_at: datetime | None = None,
    ) -> ArtifactRecord:
        if not isinstance(task_id, str) or not _TASK_ID.fullmatch(task_id):
            raise ProviderProtocolError("Google artifact task_id is invalid")
        if not isinstance(model, str) or not model.strip():
            raise ProviderProtocolError("Google artifact model is invalid")
        actual_mime, width, height = _inspect_image(data, declared_mime)
        relative = (
            Path("artifacts")
            / "google"
            / task_id
            / f"image-001{_SUFFIX_BY_MIME[actual_mime]}"
        )
        final_path = self.state_root / relative
        if final_path.exists():
            raise FileExistsError("Google image artifact already exists")
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = final_path.with_name(
            f".{final_path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with temporary.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if temporary.read_bytes() != data:
                raise ProviderProtocolError("Google image temporary bytes changed")
            _inspect_image(temporary.read_bytes(), actual_mime)
            temporary.rename(final_path)
        finally:
            if temporary.exists():
                temporary.unlink()
        observed_at = created_at or datetime.now(timezone.utc)
        return ArtifactRecord(
            relative_path=relative.as_posix(),
            mime_type=actual_mime,
            width=width,
            height=height,
            byte_length=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            model=model.strip(),
            created_at=observed_at.astimezone(timezone.utc).isoformat(),
        )
