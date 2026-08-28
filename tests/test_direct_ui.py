from __future__ import annotations

import http.client
import threading
import unittest
from html.parser import HTMLParser

from macr_runtime.direct_server import create_direct_server


class MinimalRuntime:
    def provider_health(self):
        return ()


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        if data.strip():
            self.text.append(data.strip())


class DirectUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = create_direct_server(MinimalRuntime())
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def fetch(self, path):
        address = self.server.address
        connection = http.client.HTTPConnection(
            address.host,
            address.port,
            timeout=5,
        )
        connection.request("GET", path)
        response = connection.getresponse()
        raw = response.read()
        headers = dict(response.getheaders())
        status = response.status
        connection.close()
        return status, headers, raw

    def test_packaged_assets_serve_without_auth_and_with_strict_csp(self) -> None:
        status, headers, html = self.fetch("/")
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/html"))
        self.assertEqual(headers["Cache-Control"], "no-store")
        csp = headers["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)

        self.assertEqual(self.fetch("/app.js")[0], 200)
        self.assertTrue(
            self.fetch("/app.js")[1]["Content-Type"].startswith(
                "text/javascript"
            )
        )
        self.assertEqual(self.fetch("/style.css")[0], 200)
        self.assertTrue(
            self.fetch("/style.css")[1]["Content-Type"].startswith(
                "text/css"
            )
        )
        self.assertEqual(self.fetch("/missing.js")[0], 404)

    def test_html_exposes_accessible_direct_chat_regions_and_only_local_assets(self) -> None:
        html = self.fetch("/")[2].decode("utf-8")
        parser = AssetParser()
        parser.feed(html)
        ids = {
            attrs["id"]
            for _, attrs in parser.tags
            if attrs.get("id") is not None
        }
        self.assertTrue(
            {
                "provider-cards",
                "conversation-list",
                "message-list",
                "system-prompt",
                "message-input",
                "generation-state",
                "settings-panel",
                "accounting-panel",
            }.issubset(ids)
        )
        self.assertIn("MACR 0.5.0a4", " ".join(parser.text))
        self.assertIn("Direct UI 0.1 alpha", " ".join(parser.text))
        resources = [
            attrs.get("src") or attrs.get("href")
            for tag, attrs in parser.tags
            if tag in {"script", "link"}
        ]
        self.assertEqual(resources, ["/style.css", "/app.js"])
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)

    def test_assets_are_offline_safe_and_model_output_uses_text_projection(self) -> None:
        javascript = self.fetch("/app.js")[2].decode("utf-8")
        stylesheet = self.fetch("/style.css")[2].decode("utf-8")
        for asset in (javascript, stylesheet):
            self.assertNotIn("https://", asset)
            self.assertNotIn("http://", asset)
            self.assertNotIn("XAI_API_KEY", asset)
            self.assertNotIn("D:\\", asset)
        self.assertNotIn("innerHTML", javascript)
        self.assertIn("textContent", javascript)
        self.assertNotIn("EventSource", javascript)
        self.assertNotIn("WebSocket", javascript)


if __name__ == "__main__":
    unittest.main()
