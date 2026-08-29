from __future__ import annotations

import http.client
import json
import threading
import unittest
from urllib.parse import urlsplit

from macr_runtime.direct_contracts import DirectTurnResult
from macr_runtime.direct_server import create_direct_server
from macr_runtime.direct_settings import DirectSettingsStore
from tests.support import d_drive_tempdir


CONVERSATION_ID = "00000000-0000-4000-8000-000000000201"
RUN_ID = "00000000-0000-4000-8000-000000000202"


class FakeConversations:
    def __init__(self) -> None:
        self.items: dict[str, dict] = {}
        self.message_items: dict[str, list[dict]] = {}

    def list(self, *, include_archived=False):
        return tuple(
            value
            for value in self.items.values()
            if include_archived or not value["archived"]
        )

    def get(self, conversation_id):
        return self.items[conversation_id]

    def messages(self, conversation_id):
        return tuple(self.message_items.get(conversation_id, ()))

    def search(self, query, *, include_archived=False):
        lowered = query.lower()
        return tuple(
            value
            for value in self.list(include_archived=include_archived)
            if lowered in value["title"].lower()
        )

    def archive(self, conversation_id):
        self.items[conversation_id]["archived"] = True

    def restore(self, conversation_id):
        self.items[conversation_id]["archived"] = False


class FakeRuntime:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.conversations = FakeConversations()
        self.fail_message = False
        self.send_count = 0

    def provider_health(self):
        return (
            {
                "provider_id": "grok",
                "ready": True,
                "status": "configured_offline",
                "detail": "",
            },
            {
                "provider_id": "ollama_qwythos",
                "ready": True,
                "status": "available_local",
                "detail": "",
            },
        )

    def create_conversation(
        self,
        provider_id,
        *,
        title,
        system_prompt,
        conversation_id=None,
    ):
        del conversation_id
        item = {
            "conversation_id": CONVERSATION_ID,
            "title": title,
            "provider_id": provider_id,
            "model": (
                "grok-4.6"
                if provider_id == "grok"
                else "hf.co/empero-ai/Qwythos-9B-v2-GGUF:Q4_K_M"
            ),
            "system_prompt": system_prompt,
            "archived": False,
        }
        self.conversations.items[CONVERSATION_ID] = item
        return item

    def send_message(
        self,
        conversation_id,
        content,
        *,
        origin_native_id,
        run_id=None,
    ):
        del run_id
        self.send_count += 1
        if self.fail_message:
            raise RuntimeError(
                r"D:\private\prompt.txt XAI credential private marker"
            )
        messages = self.conversations.message_items.setdefault(conversation_id, [])
        messages.extend(
            (
                {"role": "user", "content": content, "ordinal": len(messages) + 1},
                {
                    "role": "assistant",
                    "content": "complete response",
                    "ordinal": len(messages) + 2,
                },
            )
        )
        return DirectTurnResult(
            run_id=RUN_ID,
            conversation_id=conversation_id,
            status="completed",
            assistant_message=messages[-1],
            observation={"model": "grok-4.6", "answer_bytes": 17},
            context_warning=False,
            failure_type=None,
        )

    def accounting_summary(self):
        return {"grok": {"provider_reported": 0.001}}

    def delete_conversation(
        self,
        conversation_id,
        *,
        confirmation,
        origin_native_id,
    ):
        del origin_native_id
        if confirmation != "DELETE":
            raise ValueError("exact DELETE confirmation required")
        self.conversations.items.pop(conversation_id)
        messages = self.conversations.message_items.pop(conversation_id, [])
        return {
            "conversation_id": conversation_id,
            "message_count": len(messages),
            "run_count": 1 if messages else 0,
            "candidate_files_removed": 1 if messages else 0,
            "secure_delete": True,
            "wal_truncated": True,
        }


class DirectServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = d_drive_tempdir()
        self.root = self.temp.__enter__()
        settings = DirectSettingsStore(self.root / "settings.sqlite3")
        settings.ensure_operator_managed()
        self.runtime = FakeRuntime(settings)
        self.server = create_direct_server(self.runtime)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        self.host = self.server.address.host
        self.port = self.server.address.port
        self.origin = f"http://{self.host}:{self.port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.temp.__exit__(None, None, None)

    def request(
        self,
        method,
        path,
        *,
        body=None,
        cookie=None,
        origin=True,
        headers=None,
    ):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        request_headers = {} if headers is None else dict(headers)
        if origin:
            request_headers["Origin"] = self.origin
        if cookie:
            request_headers["Cookie"] = cookie
        raw = None
        if body is not None:
            raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        connection.request(method, path, body=raw, headers=request_headers)
        response = connection.getresponse()
        data = response.read()
        result = (
            json.loads(data.decode("utf-8"))
            if data and response.getheader("Content-Type", "").startswith(
                "application/json"
            )
            else data
        )
        headers_out = dict(response.getheaders())
        connection.close()
        return response.status, headers_out, result

    def authenticate(self):
        status, headers, body = self.request(
            "POST",
            "/api/v0.1/bootstrap",
            body={"token": self.server.bootstrap_token},
        )
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"]
        return cookie.split(";", 1)[0], body

    def test_binds_loopback_on_os_assigned_port(self) -> None:
        self.assertEqual(self.host, "127.0.0.1")
        self.assertGreater(self.port, 0)
        parsed = urlsplit(self.server.base_url)
        self.assertEqual(parsed.hostname, "127.0.0.1")
        self.assertEqual(parsed.port, self.port)

    def test_bootstrap_is_one_time_and_session_cookie_is_hardened(self) -> None:
        token = self.server.bootstrap_token
        cookie, body = self.authenticate()
        self.assertEqual(
            body,
            {"status": "authenticated", "api_version": "0.1"},
        )
        self.assertNotIn(token, json.dumps(body))
        status, headers, _ = self.request(
            "POST",
            "/api/v0.1/bootstrap",
            body={"token": token},
        )
        self.assertEqual(status, 401)
        self.assertNotIn("Set-Cookie", headers)

        status, _, providers = self.request(
            "GET",
            "/api/v0.1/providers",
            cookie=cookie,
            origin=False,
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(providers["providers"]), 2)

        raw_cookie = self.request(
            "POST",
            "/api/v0.1/bootstrap",
            body={"token": "wrong"},
        )[1].get("Set-Cookie", "")
        self.assertEqual(raw_cookie, "")

    def test_cookie_attributes_and_missing_auth(self) -> None:
        status, headers, _ = self.request(
            "POST",
            "/api/v0.1/bootstrap",
            body={"token": self.server.bootstrap_token},
        )
        self.assertEqual(status, 200)
        set_cookie = headers["Set-Cookie"]
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Strict", set_cookie)
        self.assertIn("Path=/", set_cookie)

        status, _, body = self.request(
            "GET",
            "/api/v0.1/providers",
            origin=False,
        )
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "authentication_required")

    def test_rejects_non_loopback_host_and_origin_without_cors(self) -> None:
        status, headers, _ = self.request(
            "GET",
            "/api/v0.1/providers",
            origin=False,
            headers={"Host": "evil.example"},
        )
        self.assertEqual(status, 403)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

        status, headers, _ = self.request(
            "POST",
            "/api/v0.1/bootstrap",
            body={"token": self.server.bootstrap_token},
            origin=False,
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(status, 403)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_exact_routes_cover_conversation_history_and_settings(self) -> None:
        cookie, _ = self.authenticate()
        status, _, created = self.request(
            "POST",
            "/api/v0.1/conversations",
            cookie=cookie,
            body={
                "provider_id": "grok",
                "title": "Alpha thread",
                "system_prompt": "Visible prompt",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(created["conversation"]["provider_id"], "grok")

        status, _, sent = self.request(
            "POST",
            f"/api/v0.1/conversations/{CONVERSATION_ID}/messages",
            cookie=cookie,
            body={"content": "hello"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(sent["result"]["assistant_message"]["content"], "complete response")

        status, _, thread = self.request(
            "GET",
            f"/api/v0.1/conversations/{CONVERSATION_ID}",
            cookie=cookie,
            origin=False,
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(thread["messages"]), 2)

        status, _, found = self.request(
            "GET",
            "/api/v0.1/search?q=alpha",
            cookie=cookie,
            origin=False,
        )
        self.assertEqual(status, 200)
        self.assertEqual(found["conversations"][0]["conversation_id"], CONVERSATION_ID)

        self.assertEqual(
            self.request(
                "POST",
                f"/api/v0.1/conversations/{CONVERSATION_ID}/archive",
                cookie=cookie,
                body={},
            )[0],
            200,
        )
        listed = self.request(
            "GET",
            "/api/v0.1/conversations",
            cookie=cookie,
            origin=False,
        )[2]
        self.assertEqual(listed["conversations"], [])
        self.assertEqual(
            self.request(
                "POST",
                f"/api/v0.1/conversations/{CONVERSATION_ID}/restore",
                cookie=cookie,
                body={},
            )[0],
            200,
        )

        settings = self.request(
            "GET",
            "/api/v0.1/settings",
            cookie=cookie,
            origin=False,
        )[2]
        self.assertEqual(settings["active"]["profile_name"], "operator_managed")
        accounting = self.request(
            "GET",
            "/api/v0.1/accounting",
            cookie=cookie,
            origin=False,
        )[2]
        self.assertEqual(accounting["summary"]["grok"]["provider_reported"], 0.001)

    def test_invalid_bodies_routes_and_methods_fail_before_runtime(self) -> None:
        cookie, _ = self.authenticate()
        before = self.runtime.send_count
        cases = (
            ("POST", "/api/v0.1/conversations", {"provider_id": "grok"}, 400),
            ("POST", "/api/v0.1/conversations", {
                "provider_id": "grok",
                "title": "x",
                "system_prompt": "",
                "unknown": True,
            }, 400),
            ("DELETE", "/api/v0.1/conversations", None, 405),
            ("GET", "/api/v0.1/unknown", None, 404),
        )
        for method, path, body, expected in cases:
            with self.subTest(method=method, path=path):
                status, _, _ = self.request(
                    method,
                    path,
                    body=body,
                    cookie=cookie,
                    origin=method != "GET",
                )
                self.assertEqual(status, expected)
        self.assertEqual(self.runtime.send_count, before)

        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        connection.request(
            "POST",
            "/api/v0.1/conversations",
            body=b"",
            headers={
                "Origin": self.origin,
                "Cookie": cookie,
                "Content-Type": "application/json",
                "Content-Length": str(1_048_577),
            },
        )
        response = connection.getresponse()
        response.read()
        self.assertEqual(response.status, 413)
        connection.close()
        self.assertEqual(self.runtime.send_count, before)

    def test_internal_errors_are_sanitized(self) -> None:
        cookie, _ = self.authenticate()
        self.runtime.create_conversation(
            "grok",
            title="error",
            system_prompt="",
        )
        self.runtime.fail_message = True
        status, _, body = self.request(
            "POST",
            f"/api/v0.1/conversations/{CONVERSATION_ID}/messages",
            cookie=cookie,
            body={"content": "trigger"},
        )
        serialized = json.dumps(body)
        self.assertEqual(status, 500)
        self.assertEqual(body["error"], "internal_error")
        self.assertNotIn("private", serialized)
        self.assertNotIn("XAI", serialized)
        self.assertNotIn("D:", serialized)

    def test_permanent_delete_requires_exact_confirmation_and_removes_thread(self) -> None:
        cookie, _ = self.authenticate()
        self.runtime.create_conversation(
            "grok",
            title="temporary",
            system_prompt="",
        )
        self.runtime.send_message(
            CONVERSATION_ID,
            "temporary content",
            origin_native_id="test-session",
        )

        status, _, body = self.request(
            "DELETE",
            f"/api/v0.1/conversations/{CONVERSATION_ID}",
            cookie=cookie,
            body={"confirmation": "delete"},
        )
        self.assertEqual(status, 400)
        self.assertIn(CONVERSATION_ID, self.runtime.conversations.items)
        self.assertEqual(body["error"], "invalid_request")

        status, _, body = self.request(
            "DELETE",
            f"/api/v0.1/conversations/{CONVERSATION_ID}",
            cookie=cookie,
            body={"confirmation": "DELETE"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            body["deletion"],
            {
                "conversation_id": CONVERSATION_ID,
                "message_count": 2,
                "run_count": 1,
                "candidate_files_removed": 1,
                "secure_delete": True,
                "wal_truncated": True,
            },
        )
        self.assertNotIn(CONVERSATION_ID, self.runtime.conversations.items)


if __name__ == "__main__":
    unittest.main()
