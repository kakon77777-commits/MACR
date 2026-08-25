import json
import unittest
from unittest.mock import patch

from macr_runtime.errors import ProviderProtocolError
from macr_runtime.providers.http_json import UrllibJsonTransport


class FakeResponse:
    def __init__(self, document):
        self.raw = json.dumps(document).encode("utf-8")

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
        with self.assertRaisesRegex(ProviderProtocolError, "request exceeded"):
            transport.post_json(
                "https://example.invalid/v1/responses",
                headers={},
                payload={"input": "larger than ten bytes"},
                timeout_s=2,
            )


if __name__ == "__main__":
    unittest.main()
