from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .direct_contracts import DirectRunSettings
from .direct_ui import read_asset
from .errors import DirectStoreConflict, MacrError


_API_PREFIX = "/api/v0.1"
_MAX_REQUEST_BYTES = 1024 * 1024
_CONVERSATION_ROUTE = re.compile(
    r"^/api/v0\.1/conversations/"
    r"([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$"
)
_MESSAGE_ROUTE = re.compile(
    r"^/api/v0\.1/conversations/"
    r"([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})/messages$"
)
_ARCHIVE_ROUTE = re.compile(
    r"^/api/v0\.1/conversations/"
    r"([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})/(archive|restore)$"
)


class _HttpFailure(Exception):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


@dataclass(frozen=True)
class DirectServerAddress:
    host: str
    port: int


class _DirectServerState:
    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self.bootstrap_token = secrets.token_urlsafe(32)
        self._bootstrap_digest: str | None = self._digest(self.bootstrap_token)
        self._sessions: dict[str, str] = {}

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def exchange_bootstrap(self, token: str) -> str | None:
        candidate = self._digest(token) if isinstance(token, str) else ""
        expected = self._bootstrap_digest
        if expected is None or not hmac.compare_digest(candidate, expected):
            return None
        self._bootstrap_digest = None
        session_token = secrets.token_urlsafe(32)
        session_digest = self._digest(session_token)
        self._sessions[session_digest] = f"session-{session_digest[:24]}"
        return session_token

    def authenticate(self, raw_cookie: str | None) -> str | None:
        if not raw_cookie:
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(raw_cookie)
        except Exception:
            return None
        morsel = cookie.get("macr_direct_session")
        if morsel is None:
            return None
        digest = self._digest(morsel.value)
        for expected, native_id in self._sessions.items():
            if hmac.compare_digest(digest, expected):
                return native_id
        return None


class DirectChatServer:
    def __init__(
        self,
        httpd: ThreadingHTTPServer,
        state: _DirectServerState,
    ) -> None:
        self._httpd = httpd
        self._state = state

    @property
    def address(self) -> DirectServerAddress:
        host, port = self._httpd.server_address[:2]
        return DirectServerAddress(str(host), int(port))

    @property
    def base_url(self) -> str:
        address = self.address
        return f"http://{address.host}:{address.port}"

    @property
    def bootstrap_token(self) -> str:
        return self._state.bootstrap_token

    @property
    def bootstrap_url(self) -> str:
        return f"{self.base_url}/#{self.bootstrap_token}"

    def serve_forever(self) -> None:
        self._httpd.serve_forever(poll_interval=0.1)

    def shutdown(self) -> None:
        self._httpd.shutdown()

    def server_close(self) -> None:
        self._httpd.server_close()


def _handler_class(state: _DirectServerState):
    class DirectRequestHandler(BaseHTTPRequestHandler):
        server_version = "MACRDirect/0.1"
        sys_version = ""

        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def _send_json(
            self,
            status: int,
            document: Any,
            *,
            headers: dict[str, str] | None = None,
        ) -> None:
            raw = json.dumps(
                document,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if headers:
                for key, value in headers.items():
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(raw)

        def _send_asset(self, name: str, content_type: str) -> None:
            raw = read_asset(name)
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
                "style-src 'self'; script-src 'self'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
            )
            self.end_headers()
            self.wfile.write(raw)

        def _reject(self, status: int, code: str) -> None:
            self._send_json(
                status,
                {
                    "error": code,
                    "detail": "The Direct Chat request was rejected.",
                },
            )

        def _validate_host_origin(self) -> None:
            host_value = self.headers.get("Host", "")
            try:
                host = urlsplit(f"//{host_value}")
                bound_port = int(self.server.server_address[1])
            except (TypeError, ValueError) as exc:
                raise _HttpFailure(403, "loopback_required") from exc
            if host.hostname != "127.0.0.1" or host.port not in {None, bound_port}:
                raise _HttpFailure(403, "loopback_required")
            origin_value = self.headers.get("Origin")
            if origin_value is not None:
                try:
                    origin = urlsplit(origin_value)
                except ValueError as exc:
                    raise _HttpFailure(403, "same_origin_required") from exc
                if (
                    origin.scheme != "http"
                    or origin.hostname != "127.0.0.1"
                    or origin.port != bound_port
                    or origin.path not in {"", "/"}
                    or origin.query
                    or origin.fragment
                ):
                    raise _HttpFailure(403, "same_origin_required")
            elif self.command in {"POST", "PUT", "PATCH", "DELETE"}:
                raise _HttpFailure(403, "same_origin_required")

        def _json_body(self) -> dict[str, Any]:
            content_type = self.headers.get("Content-Type", "")
            if not content_type.lower().startswith("application/json"):
                raise _HttpFailure(415, "json_required")
            length_value = self.headers.get("Content-Length")
            try:
                length = int(length_value) if length_value is not None else -1
            except ValueError as exc:
                raise _HttpFailure(400, "invalid_content_length") from exc
            if length < 0:
                raise _HttpFailure(411, "content_length_required")
            if length > _MAX_REQUEST_BYTES:
                raise _HttpFailure(413, "request_too_large")
            raw = self.rfile.read(length)
            try:
                document = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise _HttpFailure(400, "invalid_json") from exc
            if not isinstance(document, dict):
                raise _HttpFailure(400, "json_object_required")
            return document

        @staticmethod
        def _exact_keys(
            document: dict[str, Any],
            *,
            required: set[str],
            optional: set[str] | None = None,
        ) -> None:
            allowed = required | (optional or set())
            if set(document) - allowed or not required.issubset(document):
                raise _HttpFailure(400, "invalid_request_fields")

        def _session(self) -> str:
            native_id = state.authenticate(self.headers.get("Cookie"))
            if native_id is None:
                raise _HttpFailure(401, "authentication_required")
            return native_id

        @staticmethod
        def _boolean_query(
            query: dict[str, list[str]],
            name: str,
            *,
            default: bool,
        ) -> bool:
            values = query.get(name)
            if values is None:
                return default
            if values == ["true"]:
                return True
            if values == ["false"]:
                return False
            raise _HttpFailure(400, "invalid_query")

        def _dispatch(self) -> None:
            self._validate_host_origin()
            target = urlsplit(self.path)
            path = target.path
            query = parse_qs(target.query, keep_blank_values=True)

            assets = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/style.css": ("style.css", "text/css; charset=utf-8"),
            }
            if path in assets:
                if self.command != "GET":
                    raise _HttpFailure(405, "method_not_allowed")
                if query:
                    raise _HttpFailure(400, "invalid_query")
                name, content_type = assets[path]
                self._send_asset(name, content_type)
                return

            if path == f"{_API_PREFIX}/bootstrap":
                if self.command != "POST":
                    raise _HttpFailure(405, "method_not_allowed")
                document = self._json_body()
                self._exact_keys(document, required={"token"})
                token = document.get("token")
                if not isinstance(token, str):
                    raise _HttpFailure(400, "invalid_bootstrap")
                session_token = state.exchange_bootstrap(token)
                if session_token is None:
                    raise _HttpFailure(401, "invalid_bootstrap")
                self._send_json(
                    200,
                    {"status": "authenticated", "api_version": "0.1"},
                    headers={
                        "Set-Cookie": (
                            "macr_direct_session="
                            f"{session_token}; HttpOnly; SameSite=Strict; Path=/"
                        )
                    },
                )
                return

            if not path.startswith(_API_PREFIX):
                raise _HttpFailure(404, "route_not_found")

            native_id = self._session()
            runtime = state.runtime

            if path == f"{_API_PREFIX}/providers":
                if self.command != "GET":
                    raise _HttpFailure(405, "method_not_allowed")
                if query:
                    raise _HttpFailure(400, "invalid_query")
                self._send_json(200, {"providers": list(runtime.provider_health())})
                return

            if path == f"{_API_PREFIX}/conversations":
                if self.command == "GET":
                    if set(query) - {"include_archived"}:
                        raise _HttpFailure(400, "invalid_query")
                    include_archived = self._boolean_query(
                        query,
                        "include_archived",
                        default=False,
                    )
                    self._send_json(
                        200,
                        {
                            "conversations": list(
                                runtime.conversations.list(
                                    include_archived=include_archived
                                )
                            )
                        },
                    )
                    return
                if self.command == "POST":
                    document = self._json_body()
                    self._exact_keys(
                        document,
                        required={"provider_id", "title", "system_prompt"},
                    )
                    conversation = runtime.create_conversation(
                        document["provider_id"],
                        title=document["title"],
                        system_prompt=document["system_prompt"],
                    )
                    self._send_json(201, {"conversation": conversation})
                    return
                raise _HttpFailure(405, "method_not_allowed")

            match = _CONVERSATION_ROUTE.fullmatch(path)
            if match:
                if self.command != "GET":
                    raise _HttpFailure(405, "method_not_allowed")
                if query:
                    raise _HttpFailure(400, "invalid_query")
                conversation_id = match.group(1)
                self._send_json(
                    200,
                    {
                        "conversation": runtime.conversations.get(
                            conversation_id
                        ),
                        "messages": list(
                            runtime.conversations.messages(conversation_id)
                        ),
                    },
                )
                return

            match = _MESSAGE_ROUTE.fullmatch(path)
            if match:
                if self.command != "POST":
                    raise _HttpFailure(405, "method_not_allowed")
                document = self._json_body()
                self._exact_keys(document, required={"content"})
                result = runtime.send_message(
                    match.group(1),
                    document["content"],
                    origin_native_id=native_id,
                )
                self._send_json(200, {"result": result.to_dict()})
                return

            match = _ARCHIVE_ROUTE.fullmatch(path)
            if match:
                if self.command != "POST":
                    raise _HttpFailure(405, "method_not_allowed")
                document = self._json_body()
                self._exact_keys(document, required=set())
                conversation_id, action = match.groups()
                getattr(runtime.conversations, action)(conversation_id)
                self._send_json(200, {"status": action + "d"})
                return

            if path == f"{_API_PREFIX}/search":
                if self.command != "GET":
                    raise _HttpFailure(405, "method_not_allowed")
                if set(query) - {"q", "include_archived"} or len(query.get("q", [])) != 1:
                    raise _HttpFailure(400, "invalid_query")
                include_archived = self._boolean_query(
                    query,
                    "include_archived",
                    default=False,
                )
                self._send_json(
                    200,
                    {
                        "conversations": list(
                            runtime.conversations.search(
                                query["q"][0],
                                include_archived=include_archived,
                            )
                        )
                    },
                )
                return

            if path == f"{_API_PREFIX}/settings":
                if self.command == "GET":
                    if query:
                        raise _HttpFailure(400, "invalid_query")
                    self._send_json(
                        200,
                        {
                            "active": runtime.settings.active_profile().to_dict(),
                            "profiles": [
                                item.to_dict()
                                for item in runtime.settings.profiles()
                            ],
                        },
                    )
                    return
                if self.command == "PUT":
                    document = self._json_body()
                    self._exact_keys(
                        document,
                        required={"settings", "activate"},
                    )
                    if not isinstance(document["activate"], bool):
                        raise _HttpFailure(400, "invalid_request_fields")
                    settings = DirectRunSettings.from_dict(document["settings"])
                    runtime.settings.save_profile(
                        settings,
                        activate=document["activate"],
                    )
                    self._send_json(200, {"settings": settings.to_dict()})
                    return
                raise _HttpFailure(405, "method_not_allowed")

            if path == f"{_API_PREFIX}/accounting":
                if self.command != "GET":
                    raise _HttpFailure(405, "method_not_allowed")
                if query:
                    raise _HttpFailure(400, "invalid_query")
                self._send_json(200, {"summary": runtime.accounting_summary()})
                return

            if path.startswith(_API_PREFIX):
                raise _HttpFailure(404, "route_not_found")
            raise _HttpFailure(404, "route_not_found")

        def _handle(self) -> None:
            try:
                self._dispatch()
            except _HttpFailure as exc:
                self._reject(exc.status, exc.code)
            except KeyError:
                self._reject(404, "not_found")
            except DirectStoreConflict:
                self._reject(409, "state_conflict")
            except (ValueError, TypeError):
                self._reject(400, "invalid_request")
            except MacrError:
                self._reject(409, "direct_failure")
            except Exception:
                self._reject(500, "internal_error")

        def do_GET(self) -> None:
            self._handle()

        def do_POST(self) -> None:
            self._handle()

        def do_PUT(self) -> None:
            self._handle()

        def do_DELETE(self) -> None:
            self._handle()

        def do_PATCH(self) -> None:
            self._handle()

        def do_OPTIONS(self) -> None:
            self._handle()

    return DirectRequestHandler


def create_direct_server(
    runtime: Any,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
) -> DirectChatServer:
    if host != "127.0.0.1":
        raise ValueError("Direct Chat server must bind exactly to 127.0.0.1")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("Direct Chat port is invalid")
    state = _DirectServerState(runtime)
    httpd = ThreadingHTTPServer((host, port), _handler_class(state))
    httpd.daemon_threads = True
    return DirectChatServer(httpd, state)
