import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from macr_runtime.errors import ProviderProtocolError, ProviderUnavailableError
from macr_runtime.providers.http_json import UrllibJsonTransport


class FakeResponse:
    def __init__(self, document):
        self.raw = json.dumps(document).encode("utf-8")
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, limit):
        return self.raw[:limit]


class FakeOpener:
    def __init__(self, document):
        self.document = document
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return FakeResponse(self.document)


class RaisingOpener:
    def __init__(self, error):
        self.error = error

    def open(self, request, timeout):
        del request, timeout
        raise self.error


class RawResponse(FakeResponse):
    def __init__(self, raw: bytes, *, status: int = 200):
        self.raw = raw
        self.status = status


class HttpJsonTransportTests(unittest.TestCase):
    def test_get_json_uses_get_without_authorization_by_default(self):
        opener = FakeOpener({"models": []})
        with patch("urllib.request.build_opener", return_value=opener):
            document = UrllibJsonTransport().get_json(
                "http://127.0.0.1:11434/api/tags",
                headers={},
                timeout_s=2,
            )
        self.assertEqual(document, {"models": []})
        self.assertEqual(opener.requests[0][0].method, "GET")
        self.assertIsNone(opener.requests[0][0].data)
        self.assertNotIn("Authorization", opener.requests[0][0].headers)

    def test_post_json_rejects_oversized_request_before_open(self):
        transport = UrllibJsonTransport(max_request_bytes=10)
        with self.assertRaisesRegex(
            ProviderProtocolError,
            "request exceeded",
        ) as raised:
            transport.post_json(
                "https://example.invalid/v1/responses",
                headers={},
                payload={"input": "larger than ten bytes"},
                timeout_s=2,
            )

        self.assertEqual(
            getattr(raised.exception, "safe_diagnostic", lambda: None)(),
            {
                "network_attempted": False,
                "response_received": False,
                "provider_http_status": None,
                "provider_error_code": None,
                "transport_stage": "request_validation",
            },
        )

    def test_http_error_keeps_only_status_and_bounded_business_code(self):
        remote_message = "PRIVATE REMOTE ERROR BODY"
        error = urllib.error.HTTPError(
            "https://example.invalid/v1/responses",
            429,
            "Too Many Requests",
            {},
            io.BytesIO(
                json.dumps(
                    {"error": {"code": 1303, "message": remote_message}}
                ).encode("utf-8")
            ),
        )
        with patch(
            "urllib.request.build_opener",
            return_value=RaisingOpener(error),
        ):
            with self.assertRaises(ProviderProtocolError) as raised:
                UrllibJsonTransport().post_json(
                    "https://example.invalid/v1/responses",
                    headers={"Authorization": "Bearer PRIVATE"},
                    payload={"input": "safe"},
                    timeout_s=2,
                )

        diagnostic = getattr(
            raised.exception,
            "safe_diagnostic",
            lambda: None,
        )()
        self.assertEqual(
            diagnostic,
            {
                "network_attempted": True,
                "response_received": True,
                "provider_http_status": 429,
                "provider_error_code": "1303",
                "transport_stage": "http_response",
            },
        )
        self.assertNotIn(remote_message, str(raised.exception))
        self.assertNotIn("PRIVATE", str(diagnostic))
        self.assertTrue(error.fp.closed)

    def test_connection_error_records_attempt_without_remote_reason(self):
        remote_reason = "PRIVATE DNS OR TLS DETAIL"
        error = urllib.error.URLError(remote_reason)
        with patch(
            "urllib.request.build_opener",
            return_value=RaisingOpener(error),
        ):
            with self.assertRaises(ProviderUnavailableError) as raised:
                UrllibJsonTransport().get_json(
                    "https://example.invalid/v1/models",
                    headers={},
                    timeout_s=2,
                )

        self.assertEqual(
            getattr(raised.exception, "safe_diagnostic", lambda: None)(),
            {
                "network_attempted": True,
                "response_received": False,
                "provider_http_status": None,
                "provider_error_code": None,
                "transport_stage": "connection",
            },
        )
        self.assertNotIn(remote_reason, str(raised.exception))

    def test_malformed_success_response_records_response_boundary(self):
        opener = FakeOpener({})
        with patch("urllib.request.build_opener", return_value=opener):
            opener.open = lambda request, timeout: RawResponse(
                b"not-json",
                status=200,
            )
            with self.assertRaises(ProviderProtocolError) as raised:
                UrllibJsonTransport().get_json(
                    "https://example.invalid/v1/models",
                    headers={},
                    timeout_s=2,
                )

        self.assertEqual(
            getattr(raised.exception, "safe_diagnostic", lambda: None)(),
            {
                "network_attempted": True,
                "response_received": True,
                "provider_http_status": 200,
                "provider_error_code": None,
                "transport_stage": "response_decode",
            },
        )


if __name__ == "__main__":
    unittest.main()
