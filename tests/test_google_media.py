from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from macr_runtime.contracts import TaskContract, WorkspaceSpec
from macr_runtime.errors import ProviderPolicyError
from macr_runtime.google_media import validate_google_media_inputs
from tests.support import d_drive_tempdir


def file_entry(path: Path, root: Path, mime: str) -> dict[str, str]:
    data = path.read_bytes()
    return {
        "type": "file",
        "path": path.relative_to(root).as_posix(),
        "mime_type": mime,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def media_task(
    root: Path,
    entries: tuple[dict[str, str], ...],
    task_id: str,
) -> TaskContract:
    return TaskContract(
        task_id=task_id,
        goal="inspect media",
        task_type="multimodal",
        workspace=WorkspaceSpec(repo=str(root)),
        inputs=entries,
    )


class GoogleMediaTests(unittest.TestCase):
    def test_png_is_read_once_and_normalized(self) -> None:
        with d_drive_tempdir() as root:
            image = root / "blue.png"
            Image.new("RGB", (32, 24), "blue").save(image)
            values = validate_google_media_inputs(
                media_task(
                    root,
                    (file_entry(image, root, "image/png"),),
                    "media-png-001",
                ),
                cwd=root,
            )
            self.assertEqual(values[0].mime_type, "image/png")
            self.assertEqual(values[0].data, image.read_bytes())
            self.assertEqual(values[0].relative_path, "blue.png")

    def test_path_escape_hash_mismatch_and_mime_mismatch_are_rejected(
        self,
    ) -> None:
        with d_drive_tempdir() as root:
            image = root / "blue.png"
            Image.new("RGB", (8, 8), "blue").save(image)
            bad_entries = (
                {
                    "type": "file",
                    "path": "../blue.png",
                    "mime_type": "image/png",
                    "sha256": "0" * 64,
                },
                {**file_entry(image, root, "image/png"), "sha256": "0" * 64},
                file_entry(image, root, "application/pdf"),
            )
            for index, entry in enumerate(bad_entries):
                with self.subTest(index=index):
                    with self.assertRaises(ProviderPolicyError):
                        validate_google_media_inputs(
                            media_task(
                                root,
                                (entry,),
                                f"media-bad-{index}",
                            ),
                            cwd=root,
                        )

    def test_rejects_absolute_path_and_unknown_input_type(self) -> None:
        with d_drive_tempdir() as root:
            image = root / "blue.png"
            Image.new("RGB", (8, 8), "blue").save(image)
            invalid = (
                {**file_entry(image, root, "image/png"), "path": str(image)},
                {"type": "url", "url": "https://example.invalid/a.png"},
            )
            for index, entry in enumerate(invalid):
                with self.subTest(index=index):
                    with self.assertRaises(ProviderPolicyError):
                        validate_google_media_inputs(
                            media_task(
                                root,
                                (entry,),
                                f"media-shape-{index}",
                            ),
                            cwd=root,
                        )

    def test_rejects_per_file_size_limit(self) -> None:
        with d_drive_tempdir() as root:
            too_big = root / "too-big.pdf"
            too_big.write_bytes(b"%PDF-" + b"x" * 64)
            with patch("macr_runtime.google_media.MAX_FILE_BYTES", 64):
                with self.assertRaisesRegex(ProviderPolicyError, "20 MiB"):
                    validate_google_media_inputs(
                        media_task(
                            root,
                            (file_entry(too_big, root, "application/pdf"),),
                            "media-size-one",
                        ),
                        cwd=root,
                    )

    def test_rejects_aggregate_size_limit(self) -> None:
        with d_drive_tempdir() as root:
            first = root / "first.pdf"
            second = root / "second.pdf"
            first.write_bytes(b"%PDF-" + b"a" * 48)
            second.write_bytes(b"%PDF-" + b"b" * 48)
            with (
                patch("macr_runtime.google_media.MAX_FILE_BYTES", 64),
                patch("macr_runtime.google_media.MAX_TOTAL_BYTES", 96),
            ):
                with self.assertRaisesRegex(ProviderPolicyError, "32 MiB"):
                    validate_google_media_inputs(
                        media_task(
                            root,
                            (
                                file_entry(first, root, "application/pdf"),
                                file_entry(second, root, "application/pdf"),
                            ),
                            "media-size-total",
                        ),
                        cwd=root,
                    )

    def test_audio_mp3_is_canonicalized_and_reparse_is_rejected(self) -> None:
        with d_drive_tempdir() as root:
            audio = root / "sample.mp3"
            audio.write_bytes(b"ID3" + b"\x00" * 64)
            task = media_task(
                root,
                (file_entry(audio, root, "audio/mp3"),),
                "media-mp3",
            )
            self.assertEqual(
                validate_google_media_inputs(task, cwd=root)[0].mime_type,
                "audio/mpeg",
            )
            with patch(
                "macr_runtime.google_media._is_reparse_point",
                return_value=True,
            ):
                with self.assertRaisesRegex(ProviderPolicyError, "reparse"):
                    validate_google_media_inputs(task, cwd=root)


if __name__ == "__main__":
    unittest.main()
