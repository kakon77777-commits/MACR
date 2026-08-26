from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath
from typing import Sequence

from .errors import StoragePolicyError


_MAX_CREDENTIAL_BYTES = 64 * 1024
_REQUIRED_FIELDS = frozenset(
    {
        "type",
        "project_id",
        "private_key_id",
        "private_key",
        "client_email",
        "token_uri",
    }
)
_TOKEN_URI = "https://oauth2.googleapis.com/token"


@dataclass(frozen=True)
class CredentialInspection:
    byte_length: int
    sha256: str
    shape_valid: bool


@dataclass(frozen=True)
class CredentialStageResult:
    copied: bool
    byte_length: int
    sha256_equal: bool
    shape_valid: bool


def _read_and_inspect(path: Path) -> tuple[bytes, CredentialInspection]:
    if not path.is_file() or path.is_symlink():
        raise StoragePolicyError("Google credential source must be a regular file")
    raw = path.read_bytes()
    if not 1 <= len(raw) <= _MAX_CREDENTIAL_BYTES:
        raise StoragePolicyError("Google credential file has an invalid size")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StoragePolicyError(
            "Google credential file is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(document, dict) or not _REQUIRED_FIELDS.issubset(document):
        raise StoragePolicyError(
            "Google credential file has an invalid service-account shape"
        )
    if document.get("type") != "service_account":
        raise StoragePolicyError("Google credential type must be service_account")
    if document.get("token_uri") != _TOKEN_URI:
        raise StoragePolicyError("Google credential token URI is not approved")
    for key in ("project_id", "private_key", "client_email"):
        if not isinstance(document.get(key), str) or not document[key].strip():
            raise StoragePolicyError(
                "Google credential required string is invalid"
            )
    return raw, CredentialInspection(
        byte_length=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        shape_valid=True,
    )


def inspect_service_account(path: str | Path) -> CredentialInspection:
    return _read_and_inspect(Path(path))[1]


def _validate_d_target(target: Path) -> None:
    windows_path = PureWindowsPath(str(target))
    if not windows_path.is_absolute() or windows_path.drive.upper() != "D:":
        raise StoragePolicyError("Google credential target must be on D:")


def stage_service_account(
    source: str | Path,
    target: str | Path,
) -> CredentialStageResult:
    source_path = Path(source)
    target_path = Path(target)
    _validate_d_target(target_path)
    source_raw, source_inspection = _read_and_inspect(source_path)

    if target_path.exists():
        if not target_path.is_file() or target_path.is_symlink():
            raise FileExistsError("Google credential target is not a regular file")
        target_raw = target_path.read_bytes()
        if target_raw != source_raw:
            raise FileExistsError(
                "Google credential target exists with different bytes"
            )
        target_inspection = inspect_service_account(target_path)
        return CredentialStageResult(
            copied=False,
            byte_length=target_inspection.byte_length,
            sha256_equal=(
                target_inspection.sha256 == source_inspection.sha256
            ),
            shape_valid=target_inspection.shape_valid,
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = target_path.with_name(
        f".{target_path.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with temporary.open("xb") as handle:
            handle.write(source_raw)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_inspection = inspect_service_account(temporary)
        if temporary_inspection.sha256 != source_inspection.sha256:
            raise StoragePolicyError("Google credential temporary copy hash mismatch")
        if inspect_service_account(source_path).sha256 != source_inspection.sha256:
            raise StoragePolicyError("Google credential source changed during copy")
        temporary.rename(target_path)
    finally:
        if temporary.exists():
            temporary.unlink()

    final_inspection = inspect_service_account(target_path)
    return CredentialStageResult(
        copied=True,
        byte_length=final_inspection.byte_length,
        sha256_equal=(final_inspection.sha256 == source_inspection.sha256),
        shape_valid=final_inspection.shape_valid,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="macr-google-credential",
        description="Stage a Google service-account credential on D: without disclosure.",
    )
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = stage_service_account(args.source, args.target)
    payload = {"status": "staged", **asdict(result)}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
