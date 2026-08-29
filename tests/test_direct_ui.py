from __future__ import annotations

import http.client
import json
import subprocess
import threading
import unittest
from html.parser import HTMLParser
from pathlib import Path

from macr_runtime.direct_server import create_direct_server


ROOT = Path(__file__).resolve().parents[1]


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
        self.assertEqual(self.fetch("/result_logic.js")[0], 200)
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
                "setting-token-model",
                "setting-token-default-output",
                "setting-token-max-output",
                "setting-token-warning",
                "setting-token-hard-context",
                "save-model-token-policy",
                "accounting-panel",
                "delete-conversation",
            }.issubset(ids)
        )
        self.assertIn("MACR 0.6.0a0", " ".join(parser.text))
        self.assertIn("Direct UI 0.1 alpha", " ".join(parser.text))
        resources = [
            attrs.get("src") or attrs.get("href")
            for tag, attrs in parser.tags
            if tag in {"script", "link"}
        ]
        self.assertEqual(
            resources,
            ["/style.css", "/result_logic.js", "/app.js"],
        )
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
        self.assertIn('/model-token-policies', javascript)
        self.assertIn("saveModelTokenPolicy", javascript)

    def test_failed_turn_projection_is_visible_and_preserves_input(self) -> None:
        logic = ROOT / "src" / "macr_runtime" / "direct_ui" / "result_logic.js"
        command = (
            "const fs=require('fs');"
            "eval(fs.readFileSync(process.argv[1],'utf8'));"
            "const value={presentation:globalThis.MacrDirectResult.presentation("
            "JSON.parse(process.argv[2])),defaultProvider:"
            "globalThis.MacrDirectResult.defaultProvider(JSON.parse(process.argv[3])),"
            "deleteLower:globalThis.MacrDirectResult.confirmDelete('delete'),"
            "deleteExact:globalThis.MacrDirectResult.confirmDelete('DELETE')};"
            "process.stdout.write(JSON.stringify(value));"
        )
        result = subprocess.run(
            [
                "node",
                "-e",
                command,
                str(logic),
                json.dumps(
                    {
                        "status": "failed_after_dispatch",
                        "failure_type": "ProviderUnavailableError",
                        "context_warning": False,
                    }
                ),
                json.dumps(
                    [
                        {"provider_id": "grok", "ready": False},
                        {"provider_id": "ollama_qwythos", "ready": True},
                    ]
                ),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "presentation": {
                    "ok": False,
                    "label": "本輪失敗 · ProviderUnavailableError",
                    "preserveInput": True,
                },
                "defaultProvider": "ollama_qwythos",
                "deleteLower": False,
                "deleteExact": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
