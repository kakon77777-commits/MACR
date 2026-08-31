from __future__ import annotations

import unittest

from macr_runtime._v07_contracts import (
    canonical_record_digest,
    freeze_json_value,
    normalize_timestamp,
    public_json_value,
    require_closed_mapping,
    require_json_object,
    require_json_value,
    require_non_empty,
    require_non_negative_int,
    require_non_negative_number,
    require_optional_non_empty,
    require_positive_int,
    require_sha256,
    require_string_tuple,
    require_uuid4,
)


class V07ContractSupportTests(unittest.TestCase):
    def test_digest_is_namespaced_and_key_order_independent(self) -> None:
        left = canonical_record_digest("macr.v07.test.v1", {"b": 2, "a": 1})
        right = canonical_record_digest("macr.v07.test.v1", {"a": 1, "b": 2})

        self.assertEqual(left, right)
        self.assertNotEqual(
            left,
            canonical_record_digest("macr.v07.other.v1", {"a": 1, "b": 2}),
        )

    def test_json_validation_rejects_nonfinite_and_arbitrary_objects(self) -> None:
        for value in ({"x": float("nan")}, {"x": float("inf")}, object()):
            with self.subTest(value=type(value).__name__):
                with self.assertRaisesRegex(ValueError, "finite JSON"):
                    require_json_value("payload", value)

    def test_json_object_rejects_lists_and_copies_mappings(self) -> None:
        source = {"key": [1, 2]}

        result = require_json_object("payload", source)

        self.assertEqual(result, source)
        self.assertIsNot(result, source)
        with self.assertRaisesRegex(ValueError, "JSON object"):
            require_json_object("payload", ["not", "an", "object"])

    def test_frozen_json_cannot_drift_after_identity_is_created(self) -> None:
        source = {"nested": {"values": [1, 2]}}
        frozen = freeze_json_value("payload", source)
        before = canonical_record_digest("macr.v07.frozen.v1", frozen)

        source["nested"]["values"].append(3)
        public = public_json_value(frozen)
        public["nested"]["values"].append(4)

        self.assertEqual(public_json_value(frozen), {"nested": {"values": [1, 2]}})
        self.assertEqual(
            canonical_record_digest("macr.v07.frozen.v1", frozen),
            before,
        )
        with self.assertRaises(TypeError):
            frozen["nested"]["new"] = "forbidden"
        with self.assertRaises(AttributeError):
            frozen["nested"]["values"].append(5)

    def test_integer_and_number_validators_reject_boolean(self) -> None:
        for validator, value in (
            (require_positive_int, True),
            (require_non_negative_int, False),
            (require_non_negative_number, True),
        ):
            with self.subTest(validator=validator.__name__):
                with self.assertRaises(ValueError):
                    validator("value", value)

    def test_integer_and_number_bounds_fail_closed(self) -> None:
        self.assertEqual(require_positive_int("revision", 1), 1)
        self.assertEqual(require_non_negative_int("epoch", 0), 0)
        self.assertEqual(require_non_negative_number("cost", 1.25), 1.25)

        with self.assertRaises(ValueError):
            require_positive_int("revision", 0)
        with self.assertRaises(ValueError):
            require_non_negative_int("epoch", -1)
        for value in (-0.1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                require_non_negative_number("cost", value)

    def test_closed_mapping_rejects_unknown_and_missing_fields(self) -> None:
        required = frozenset({"id"})
        optional = frozenset({"note"})

        self.assertEqual(
            require_closed_mapping(
                "record",
                {"id": "x", "note": "ok"},
                required=required,
                optional=optional,
            ),
            {"id": "x", "note": "ok"},
        )
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            require_closed_mapping(
                "record",
                {"id": "x", "surprise": 1},
                required=required,
                optional=optional,
            )
        with self.assertRaisesRegex(ValueError, "missing fields"):
            require_closed_mapping(
                "record",
                {},
                required=required,
                optional=optional,
            )

    def test_text_validators_are_bounded_and_optional_is_explicit(self) -> None:
        self.assertEqual(require_non_empty("name", " value "), "value")
        self.assertIsNone(require_optional_non_empty("name", None))
        self.assertEqual(require_optional_non_empty("name", "x"), "x")

        with self.assertRaises(ValueError):
            require_non_empty("name", "   ")
        with self.assertRaises(ValueError):
            require_non_empty("name", "é", max_bytes=1)
        with self.assertRaises(ValueError):
            require_optional_non_empty("name", "")

    def test_sha_and_uuid_require_canonical_forms(self) -> None:
        digest = "a" * 64
        run_id = "11111111-1111-4111-8111-111111111111"

        self.assertEqual(require_sha256("digest", digest), digest)
        self.assertEqual(require_uuid4("run_id", run_id), run_id)

        with self.assertRaises(ValueError):
            require_sha256("digest", "A" * 64)
        with self.assertRaises(ValueError):
            require_sha256("digest", "a" * 63)
        with self.assertRaises(ValueError):
            require_uuid4("run_id", "11111111-1111-1111-8111-111111111111")

    def test_string_tuple_is_bounded_unique_and_canonical(self) -> None:
        self.assertEqual(
            require_string_tuple("refs", ["b", "a"]),
            ("a", "b"),
        )
        with self.assertRaisesRegex(ValueError, "duplicates"):
            require_string_tuple("refs", ["a", "a"])
        with self.assertRaises(ValueError):
            require_string_tuple("refs", "not-a-sequence")
        with self.assertRaises(ValueError):
            require_string_tuple("refs", ["a", "b"], maximum=1)

    def test_timestamp_requires_timezone_and_normalizes_utc(self) -> None:
        self.assertEqual(
            normalize_timestamp("created_at", "2026-08-31T08:00:00+08:00"),
            "2026-08-31T00:00:00+00:00",
        )
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            normalize_timestamp("created_at", "2026-08-31T00:00:00")


if __name__ == "__main__":
    unittest.main()
