from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from ..errors import ProviderProtocolError, ProviderUnavailableError


class JsonTransport(Protocol):
    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_s: float,
    ) -> Mapping[str, Any]:
        raise NotImplementedError

    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_s: float,
    ) -> Mapping[str, Any]:
        raise NotImplementedError


class _RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Prevent credentials from being forwarded by urllib redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


@dataclass
class UrllibJsonTransport:
    max_request_bytes: int = 2 * 1024 * 1024
    max_response_bytes: int = 8 * 1024 * 1024

    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_s: float,
    ) -> Mapping[str, Any]:
        return self._request_json(
            "GET",
            url,
            headers=headers,
            payload=None,
            timeout_s=timeout_s,
        )

    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_s: float,
    ) -> Mapping[str, Any]:
        return self._request_json(
            "POST",
            url,
            headers=headers,
            payload=payload,
            timeout_s=timeout_s,
        )

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any] | None,
        timeout_s: float,
    ) -> Mapping[str, Any]:
        body = (
            None
            if payload is None
            else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        )
        if body is not None and len(body) > self.max_request_bytes:
            raise ProviderProtocolError(
                "provider request exceeded the configured size limit"
            )
        request_headers = dict(headers)
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url,
            data=body,
            headers=request_headers,
            method=method,
        )
        return self._open_and_decode(request, timeout_s)

    def _open_and_decode(
        self,
        request: urllib.request.Request,
        timeout_s: float,
    ) -> Mapping[str, Any]:
        opener = urllib.request.build_opener(_RejectRedirectHandler())
        try:
            with opener.open(request, timeout=timeout_s) as response:
                raw = response.read(self.max_response_bytes + 1)
        except urllib.error.HTTPError as exc:
            raise ProviderProtocolError(
                f"provider HTTP {exc.code}; remote response body omitted"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            reason = getattr(exc, "reason", str(exc))
            raise ProviderUnavailableError(
                f"provider connection failed: {reason}"
            ) from exc
        if len(raw) > self.max_response_bytes:
            raise ProviderProtocolError(
                "provider response exceeded the configured size limit"
            )
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderProtocolError(
                "provider response was not valid UTF-8 JSON"
            ) from exc
        if not isinstance(document, dict):
            raise ProviderProtocolError(
                "provider response root must be a JSON object"
            )
        return document
