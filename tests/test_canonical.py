from __future__ import annotations

import unittest

from macr_runtime.canonical import (
    aware_iso8601,
    canonical_json_bytes,
    sha256_id,
)


class CanonicalTests(unittest.TestCase):
    def test_canonical_json_is_byte_stable_and_rejects_non_finite_values(self) -> None:
        self.assertEqual(
            canonical_json_bytes({"b": 2, "a": 1, "text": "澄序"}),
            '{"a":1,"b":2,"text":"澄序"}'.encode("utf-8"),
        )
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError,
                "finite JSON",
            ):
                canonical_json_bytes({"value": value})

    def test_canonical_json_rejects_non_string_keys_and_non_json_values(self) -> None:
        for value in ({1: "integer key"}, {"raw": b"bytes"}):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError,
                "finite JSON",
            ):
                canonical_json_bytes(value)

    def test_namespaced_digest_is_stable_and_separates_subjects(self) -> None:
        model = sha256_id("model_subject_v1", {"id": "x"})
        route = sha256_id("route_v1", {"id": "x"})
        self.assertEqual(
            model,
            "a655d322cc7d12c23e303795b4e1219d0f87d16ebdc50f35de898e898876864b",
        )
        self.assertNotEqual(model, route)
        self.assertEqual(model, sha256_id("model_subject_v1", {"id": "x"}))
        for namespace in ("", "模型", "white space"):
            with self.subTest(namespace=namespace), self.assertRaisesRegex(
                ValueError,
                "namespace",
            ):
                sha256_id(namespace, {"id": "x"})

    def test_aware_iso8601_requires_timezone_and_normalizes_utc(self) -> None:
        self.assertEqual(
            aware_iso8601("observed_at", "2026-08-29T10:00:00+08:00"),
            "2026-08-29T02:00:00+00:00",
        )
        self.assertEqual(
            aware_iso8601("observed_at", "2026-08-29T02:00:00Z"),
            "2026-08-29T02:00:00+00:00",
        )
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            aware_iso8601("observed_at", "2026-08-29T02:00:00")
        with self.assertRaisesRegex(ValueError, "ISO timestamp"):
            aware_iso8601("observed_at", "not-a-time")


if __name__ == "__main__":
    unittest.main()
