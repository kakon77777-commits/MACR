from __future__ import annotations

import sys
import unittest

from tests.helpers.process_capture import (
    CapturedProcess,
    assert_canaries_absent,
    render_utf8,
    run_bytes,
)


class ProcessCaptureTests(unittest.TestCase):
    def test_non_utf8_stderr_is_preserved_and_rendered_without_reader_failure(
        self,
    ) -> None:
        capture = run_bytes(
            (
                sys.executable,
                "-c",
                "import os; os.write(2, b'bad\\xa6')",
            )
        )

        self.assertEqual(capture.returncode, 0)
        self.assertEqual(capture.stderr_bytes, b"bad\xa6")
        self.assertEqual(render_utf8(capture.stderr_bytes), "bad\ufffd")

    def test_canary_scan_checks_raw_stdout_before_rendering(self) -> None:
        capture = CapturedProcess(1, b"uuid-token\xa6", b"")

        with self.assertRaisesRegex(AssertionError, "stdout"):
            assert_canaries_absent(capture, (b"uuid-token",))

    def test_canary_scan_checks_raw_stderr_before_rendering(self) -> None:
        capture = CapturedProcess(1, b"", b"secret-token\xa6")

        with self.assertRaisesRegex(AssertionError, "stderr"):
            assert_canaries_absent(capture, (b"secret-token",))

    def test_utf8_rendering_preserves_valid_text_and_strips_bom(self) -> None:
        self.assertEqual(render_utf8(b"\xef\xbb\xbfhello\r\n"), "hello\r\n")

    def test_capture_exposes_replacement_decoded_diagnostics(self) -> None:
        capture = CapturedProcess(1, b"\xef\xbb\xbfhello", b"bad\xa6")

        self.assertEqual(capture.stdout, "hello")
        self.assertEqual(capture.stderr, "bad\ufffd")


if __name__ == "__main__":
    unittest.main()
