from __future__ import annotations

import io
import unittest
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from macr_runtime.artifacts import ImageArtifactStore
from macr_runtime.errors import ProviderProtocolError, StoragePolicyError
from tests.support import d_drive_tempdir


def image_bytes(image_format: str = "JPEG") -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (64, 48), "green").save(stream, format=image_format)
    return stream.getvalue()


class ArtifactStoreTests(unittest.TestCase):
    def test_saves_exact_bytes_and_returns_relative_metadata(self) -> None:
        with d_drive_tempdir() as state_root:
            store = ImageArtifactStore(state_root)
            data = image_bytes()
            record = store.save_image(
                task_id="image-artifact-001",
                model="gemini-3.1-flash-image",
                data=data,
                declared_mime="image/jpeg",
                created_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
            )
            saved = state_root / record.relative_path
            self.assertEqual(saved.read_bytes(), data)
            self.assertEqual((record.width, record.height), (64, 48))
            self.assertEqual(record.mime_type, "image/jpeg")
            self.assertEqual(record.byte_length, len(data))
            self.assertNotIn(str(state_root), str(record.to_dict()))

    def test_png_uses_detected_mime_and_suffix(self) -> None:
        with d_drive_tempdir() as state_root:
            record = ImageArtifactStore(state_root).save_image(
                "png-artifact",
                "gemini-3.1-flash-image",
                image_bytes("PNG"),
                "image/png",
            )
            self.assertTrue(record.relative_path.endswith(".png"))
            self.assertEqual(record.mime_type, "image/png")

    def test_refuses_overwrite_mime_mismatch_and_invalid_bytes(self) -> None:
        with d_drive_tempdir() as state_root:
            store = ImageArtifactStore(state_root)
            data = image_bytes()
            store.save_image(
                "same-task",
                "gemini-3.1-flash-image",
                data,
                "image/jpeg",
            )
            with self.assertRaises(FileExistsError):
                store.save_image(
                    "same-task",
                    "gemini-3.1-flash-image",
                    data,
                    "image/jpeg",
                )
            with self.assertRaises(ProviderProtocolError):
                store.save_image(
                    "mime-bad",
                    "gemini-3.1-flash-image",
                    data,
                    "image/png",
                )
            with self.assertRaises(ProviderProtocolError):
                store.save_image(
                    "bytes-bad",
                    "gemini-3.1-flash-image",
                    b"bad",
                    "image/jpeg",
                )

    def test_store_root_must_be_on_d(self) -> None:
        with self.assertRaisesRegex(StoragePolicyError, "must be on D"):
            ImageArtifactStore(Path(r"C:\temp\macr-state"))


if __name__ == "__main__":
    unittest.main()
