from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from .canonical import aware_iso8601
from .errors import MacrError, StoragePolicyError
from .observatory_db import ObservatoryDatabase


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_MANIFEST_BYTES = 1024 * 1024
_MAX_EVIDENCE_BYTES = 1024 * 1024
_MAX_TOTAL_EVIDENCE_BYTES = 16 * 1024 * 1024
DEFAULT_BOUNDED_ROLES = (
    "bounded_exact_worker",
    "structured_output_worker",
    "verified_code_worker",
)
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "manifest_id",
        "subject_id",
        "route_id",
        "operator_review_digest",
        "authorized_bounded_roles",
        "explicit_blind_spots",
        "entries",
    }
)
_ENTRY_KEYS = frozenset(
    {
        "role_id",
        "role_digest",
        "context_class",
        "verifier_suite_digest",
        "probe_digest",
        "qualification_key",
        "observed_at",
        "relative_path",
        "file_bytes",
        "file_sha256",
        "import_disposition",
    }
)
_EVIDENCE_KEYS = frozenset(
    {
        "evidence_schema",
        "role_id",
        "outcome",
        "terminal_state",
        "verifier_state",
        "tests_passed",
        "tests_failed",
        "blind_spots",
        "known_failures",
    }
)


class EvidenceImportError(MacrError):
    """Reviewed external evidence does not satisfy its exact import manifest."""


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise EvidenceImportError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise EvidenceImportError(f"{name} must be a bounded identifier")
    return value


def _object(name: str, value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvidenceImportError(f"{name} must be an object")
    return value


def _exact_keys(name: str, value: Mapping[str, Any], expected: frozenset[str]) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        raise EvidenceImportError(f"{name} is missing key: {missing[0]}")
    if unknown:
        raise EvidenceImportError(f"{name} has unknown key: {unknown[0]}")


def _string_array(name: str, value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise EvidenceImportError(f"{name} must be an array of strings")
    if len(set(value)) != len(value):
        raise EvidenceImportError(f"{name} contains duplicate values")
    return tuple(value)


def _strict_json(name: str, raw_bytes: bytes) -> Mapping[str, Any]:
    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise EvidenceImportError(f"{name} has duplicate key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise EvidenceImportError(f"{name} has non-finite value: {value}")

    try:
        document = json.loads(
            raw_bytes.decode("utf-8"),
            object_pairs_hook=reject_duplicate,
            parse_constant=reject_constant,
        )
    except EvidenceImportError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise EvidenceImportError(f"{name} must be valid UTF-8 JSON") from exc
    if not isinstance(document, Mapping):
        raise EvidenceImportError(f"{name} root must be an object")
    return document


def _validate_d_file(name: str, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute() or path.drive.upper() != "D:":
        raise StoragePolicyError(f"{name} must be absolute on D:")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise EvidenceImportError(f"{name} is unavailable") from exc
    if not resolved.is_file() or _is_reparse(resolved):
        raise EvidenceImportError(f"{name} must be a regular non-reparse file")
    return resolved


def _is_reparse(path: Path) -> bool:
    return path.is_symlink() or (
        hasattr(os.path, "isjunction") and os.path.isjunction(path)
    )


def _bounded_read(name: str, path: Path, maximum: int) -> bytes:
    size = path.stat().st_size
    if size > maximum:
        raise EvidenceImportError(f"{name} exceeds its size limit")
    raw = path.read_bytes()
    if len(raw) != size:
        raise EvidenceImportError(f"{name} changed while being read")
    return raw


def _relative_evidence_file(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise EvidenceImportError("relative_path must be a relative POSIX path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise EvidenceImportError("relative_path escapes the manifest directory")
    candidate = root.joinpath(*relative.parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise EvidenceImportError(
            "relative_path escapes or is unavailable"
        ) from exc
    if resolved.drive.upper() != "D:":
        raise EvidenceImportError("relative_path must resolve on D:")
    if not resolved.is_file() or _is_reparse(resolved):
        raise EvidenceImportError(
            "relative_path must resolve to a regular non-reparse file"
        )
    return resolved


@dataclass(frozen=True)
class ImportReport:
    manifest_id: str
    manifest_digest: str
    entry_count: int
    importable_count: int
    imported_count: int
    already_imported_count: int
    imported_evidence_ids: tuple[str, ...]
    imported_roles: tuple[str, ...]
    rejected_or_unqualified_roles: tuple[str, ...]
    explicit_blind_spots: tuple[str, ...]
    wrote: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_id": self.manifest_id,
            "manifest_digest": self.manifest_digest,
            "entry_count": self.entry_count,
            "importable_count": self.importable_count,
            "imported_count": self.imported_count,
            "already_imported_count": self.already_imported_count,
            "imported_evidence_ids": list(self.imported_evidence_ids),
            "imported_roles": list(self.imported_roles),
            "rejected_or_unqualified_roles": list(
                self.rejected_or_unqualified_roles
            ),
            "explicit_blind_spots": list(self.explicit_blind_spots),
            "wrote": self.wrote,
        }


@dataclass(frozen=True)
class _InspectedEntry:
    role_id: str
    role_digest: str
    context_class: str
    verifier_suite_digest: str
    probe_digest: str
    qualification_key: str
    observed_at: str
    file_bytes: int
    file_sha256: str
    import_disposition: str
    outcome: str
    terminal_state: str
    verifier_state: str
    tests_passed: int
    tests_failed: int
    blind_spots: tuple[str, ...]
    known_failures: tuple[str, ...]


@dataclass(frozen=True)
class _InspectionBundle:
    manifest_id: str
    manifest_digest: str
    subject_id: str
    route_id: str
    operator_review_digest: str
    authorized_roles: tuple[str, ...]
    explicit_blind_spots: tuple[str, ...]
    entries: tuple[_InspectedEntry, ...]


class EvidenceImporter:
    def __init__(
        self,
        store: ObservatoryDatabase | None,
        *,
        allowed_roles: Iterable[str] = DEFAULT_BOUNDED_ROLES,
    ) -> None:
        if store is not None and not isinstance(store, ObservatoryDatabase):
            raise ValueError("store must be an ObservatoryDatabase or None")
        if isinstance(allowed_roles, (str, bytes)):
            raise ValueError("allowed_roles must be identifiers")
        normalized = tuple(_identifier("allowed role", item) for item in allowed_roles)
        if not normalized or len(set(normalized)) != len(normalized):
            raise ValueError("allowed_roles must be unique and non-empty")
        self.store = store
        self.allowed_roles = tuple(sorted(normalized))

    def inspect(self, manifest: str | Path) -> ImportReport:
        bundle = self._inspect_bundle(manifest)
        return self._report(bundle, (), imported_count=0, already=0, wrote=False)

    def import_manifest(
        self,
        manifest: str | Path,
        expected_digest: str,
    ) -> ImportReport:
        if self.store is None:
            raise EvidenceImportError("evidence import requires an observatory store")
        expected_digest = _digest("expected manifest digest", expected_digest)
        bundle = self._inspect_bundle(manifest)
        if bundle.manifest_digest != expected_digest:
            raise EvidenceImportError("manifest digest does not match expected digest")

        metadata = tuple(
            self._evidence_metadata(bundle, entry)
            for entry in bundle.entries
            if self._is_importable(bundle, entry)
        )
        persisted, inserted = self.store.append_evidence_batch_with_status(
            metadata
        )
        imported_count = sum(inserted)
        already = len(inserted) - imported_count
        return self._report(
            bundle,
            tuple(item.evidence_id for item in persisted),
            imported_count=imported_count,
            already=already,
            wrote=True,
        )

    def _inspect_bundle(self, manifest: str | Path) -> _InspectionBundle:
        manifest_path = _validate_d_file("evidence manifest", manifest)
        root = manifest_path.parent.resolve(strict=True)
        raw_manifest = _bounded_read(
            "evidence manifest",
            manifest_path,
            _MAX_MANIFEST_BYTES,
        )
        manifest_digest = hashlib.sha256(raw_manifest).hexdigest()
        document = _strict_json("evidence manifest", raw_manifest)
        _exact_keys("evidence manifest", document, _MANIFEST_KEYS)
        if document.get("schema_version") != 1:
            raise EvidenceImportError("evidence manifest schema_version must be 1")
        manifest_id = _identifier("manifest_id", document.get("manifest_id"))
        subject_id = _digest("subject_id", document.get("subject_id"))
        route_id = _digest("route_id", document.get("route_id"))
        operator_review_digest = _digest(
            "operator_review_digest",
            document.get("operator_review_digest"),
        )
        authorized_roles = tuple(
            sorted(
                _identifier("authorized role", item)
                for item in _string_array(
                    "authorized_bounded_roles",
                    document.get("authorized_bounded_roles"),
                )
            )
        )
        explicit_blind_spots = tuple(
            sorted(
                _string_array(
                    "explicit_blind_spots",
                    document.get("explicit_blind_spots"),
                )
            )
        )
        raw_entries = document.get("entries")
        if not isinstance(raw_entries, list) or not raw_entries:
            raise EvidenceImportError("evidence manifest entries must be non-empty")

        total_bytes = 0
        entries: list[_InspectedEntry] = []
        roles: set[str] = set()
        paths: set[str] = set()
        qualifications: set[str] = set()
        for index, raw_entry in enumerate(raw_entries):
            entry = _object(f"entries[{index}]", raw_entry)
            _exact_keys(f"entries[{index}]", entry, _ENTRY_KEYS)
            role_id = _identifier("role_id", entry.get("role_id"))
            relative_path = entry.get("relative_path")
            if not isinstance(relative_path, str):
                raise EvidenceImportError(
                    "relative_path must be a relative POSIX path"
                )
            if role_id in roles:
                raise EvidenceImportError("entries contain duplicate role_id")
            if relative_path in paths:
                raise EvidenceImportError("entries contain duplicate relative_path")
            roles.add(role_id)
            paths.add(relative_path)
            qualification_key = _digest(
                "qualification_key",
                entry.get("qualification_key"),
            )
            if qualification_key in qualifications:
                raise EvidenceImportError(
                    "entries contain duplicate qualification_key"
                )
            qualifications.add(qualification_key)
            file_bytes = entry.get("file_bytes")
            if (
                isinstance(file_bytes, bool)
                or not isinstance(file_bytes, int)
                or not 0 <= file_bytes <= _MAX_EVIDENCE_BYTES
            ):
                raise EvidenceImportError("file_bytes is invalid")
            file_sha256 = _digest("file_sha256", entry.get("file_sha256"))
            target = _relative_evidence_file(root, relative_path)
            raw_evidence = _bounded_read(
                f"evidence file {index}",
                target,
                _MAX_EVIDENCE_BYTES,
            )
            total_bytes += len(raw_evidence)
            if total_bytes > _MAX_TOTAL_EVIDENCE_BYTES:
                raise EvidenceImportError("evidence files exceed aggregate limit")
            if len(raw_evidence) != file_bytes:
                raise EvidenceImportError(
                    "evidence file hash mismatch (byte count changed)"
                )
            if hashlib.sha256(raw_evidence).hexdigest() != file_sha256:
                raise EvidenceImportError("evidence file hash mismatch")
            evidence = _strict_json(f"evidence file {index}", raw_evidence)
            _exact_keys(f"evidence file {index}", evidence, _EVIDENCE_KEYS)
            if evidence.get("evidence_schema") != "macr-glm-a3-reviewed-v1":
                raise EvidenceImportError("evidence file schema is unsupported")
            if evidence.get("role_id") != role_id:
                raise EvidenceImportError("evidence file role_id mismatch")
            tests_passed = evidence.get("tests_passed")
            tests_failed = evidence.get("tests_failed")
            for name, value in (
                ("tests_passed", tests_passed),
                ("tests_failed", tests_failed),
            ):
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise EvidenceImportError(f"{name} must be non-negative integer")
            disposition = entry.get("import_disposition")
            if disposition not in {"bounded_evidence", "unqualified_observation"}:
                raise EvidenceImportError("import_disposition is invalid")
            entries.append(
                _InspectedEntry(
                    role_id=role_id,
                    role_digest=_digest("role_digest", entry.get("role_digest")),
                    context_class=_identifier(
                        "context_class",
                        entry.get("context_class"),
                    ),
                    verifier_suite_digest=_digest(
                        "verifier_suite_digest",
                        entry.get("verifier_suite_digest"),
                    ),
                    probe_digest=_digest(
                        "probe_digest",
                        entry.get("probe_digest"),
                    ),
                    qualification_key=qualification_key,
                    observed_at=aware_iso8601(
                        "observed_at",
                        entry.get("observed_at"),
                    ),
                    file_bytes=file_bytes,
                    file_sha256=file_sha256,
                    import_disposition=disposition,
                    outcome=_identifier("outcome", evidence.get("outcome")),
                    terminal_state=_identifier(
                        "terminal_state",
                        evidence.get("terminal_state"),
                    ),
                    verifier_state=_identifier(
                        "verifier_state",
                        evidence.get("verifier_state"),
                    ),
                    tests_passed=tests_passed,
                    tests_failed=tests_failed,
                    blind_spots=tuple(
                        sorted(
                            _string_array(
                                "evidence blind_spots",
                                evidence.get("blind_spots"),
                            )
                        )
                    ),
                    known_failures=tuple(
                        sorted(
                            _string_array(
                                "known_failures",
                                evidence.get("known_failures"),
                            )
                        )
                    ),
                )
            )
        return _InspectionBundle(
            manifest_id=manifest_id,
            manifest_digest=manifest_digest,
            subject_id=subject_id,
            route_id=route_id,
            operator_review_digest=operator_review_digest,
            authorized_roles=authorized_roles,
            explicit_blind_spots=explicit_blind_spots,
            entries=tuple(entries),
        )

    def _is_importable(
        self,
        bundle: _InspectionBundle,
        entry: _InspectedEntry,
    ) -> bool:
        return (
            entry.import_disposition == "bounded_evidence"
            and entry.role_id in bundle.authorized_roles
            and entry.role_id in self.allowed_roles
        )

    def _evidence_metadata(
        self,
        bundle: _InspectionBundle,
        entry: _InspectedEntry,
    ) -> dict[str, object]:
        return {
            "qualification_key": entry.qualification_key,
            "kind": "reviewed_external_evidence",
            "subject_digest": bundle.subject_id,
            "observed_at": entry.observed_at,
            "payload": {
                "manifest_digest": bundle.manifest_digest,
                "operator_review_digest": bundle.operator_review_digest,
                "source_evidence_sha256": entry.file_sha256,
                "source_evidence_bytes": entry.file_bytes,
                "route_id": bundle.route_id,
                "role_id": entry.role_id,
                "role_digest": entry.role_digest,
                "context_class": entry.context_class,
                "verifier_suite_digest": entry.verifier_suite_digest,
                "probe_digest": entry.probe_digest,
                "outcome": entry.outcome,
                "terminal_state": entry.terminal_state,
                "verifier_state": entry.verifier_state,
                "tests_passed": entry.tests_passed,
                "tests_failed": entry.tests_failed,
                "blind_spots": list(entry.blind_spots),
                "known_failures": list(entry.known_failures),
                "promotion_authority": "none",
            },
        }

    def _report(
        self,
        bundle: _InspectionBundle,
        evidence_ids: tuple[str, ...],
        *,
        imported_count: int,
        already: int,
        wrote: bool,
    ) -> ImportReport:
        imported_roles = tuple(
            sorted(
                entry.role_id
                for entry in bundle.entries
                if self._is_importable(bundle, entry)
            )
        )
        rejected = tuple(
            sorted(
                entry.role_id
                for entry in bundle.entries
                if not self._is_importable(bundle, entry)
            )
        )
        blind_spots = set(bundle.explicit_blind_spots)
        for entry in bundle.entries:
            blind_spots.update(entry.blind_spots)
        return ImportReport(
            manifest_id=bundle.manifest_id,
            manifest_digest=bundle.manifest_digest,
            entry_count=len(bundle.entries),
            importable_count=len(imported_roles),
            imported_count=imported_count,
            already_imported_count=already,
            imported_evidence_ids=evidence_ids,
            imported_roles=imported_roles,
            rejected_or_unqualified_roles=rejected,
            explicit_blind_spots=tuple(sorted(blind_spots)),
            wrote=wrote,
        )


__all__ = [
    "DEFAULT_BOUNDED_ROLES",
    "EvidenceImportError",
    "EvidenceImporter",
    "ImportReport",
]
