from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from ..errors import ProviderProtocolError, ProviderUnavailableError


_MAX_ERROR_BODY_BYTES = 64 * 1024
_SAFE_PROVIDER_ERROR_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _response_status(value: object) -> int | None:
    status = getattr(value, "status", None)
    if (
        isinstance(status, int)
        and not isinstance(status, bool)
        and 100 <= status <= 599
    ):
        return status
    return None


def _provider_error_code(error: urllib.error.HTTPError) -> str | None:
    try:
        raw = error.read(_MAX_ERROR_BODY_BYTES + 1)
    except (OSError, ValueError):
        return None
    if not isinstance(raw, bytes) or len(raw) > _MAX_ERROR_BODY_BYTES:
        return None
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    detail = document.get("error") if isinstance(document, Mapping) else None
    code = detail.get("code") if isinstance(detail, Mapping) else None
    if isinstance(code, bool) or not isinstance(code, (int, str)):
        return None
    normalized = str(code)
    return normalized if _SAFE_PROVIDER_ERROR_CODE.fullmatch(normalized) else None


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
                "provider request exceeded the configured size limit",
                network_attempted=False,
                response_received=False,
                transport_stage="request_validation",
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
                status = _response_status(response) or 200
                try:
                    raw = response.read(self.max_response_bytes + 1)
                except (OSError, TimeoutError) as exc:
                    raise ProviderUnavailableError(
                        "provider response read failed; remote detail omitted",
                        network_attempted=True,
                        response_received=True,
                        provider_http_status=status,
                        transport_stage="response_read",
                    ) from exc
        except urllib.error.HTTPError as exc:
            status = exc.code
            business_code = _provider_error_code(exc)
            try:
                exc.close()
            except OSError:
                pass
            raise ProviderProtocolError(
                f"provider HTTP {status}; remote response body omitted",
                network_attempted=True,
                response_received=True,
                provider_http_status=status,
                provider_error_code=business_code,
                transport_stage="http_response",
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ProviderUnavailableError(
                "provider connection failed; remote detail omitted",
                network_attempted=True,
                response_received=False,
                transport_stage="connection",
            ) from exc
        if len(raw) > self.max_response_bytes:
            raise ProviderProtocolError(
                "provider response exceeded the configured size limit",
                network_attempted=True,
                response_received=True,
                provider_http_status=status,
                transport_stage="response_read",
            )
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderProtocolError(
                "provider response was not valid UTF-8 JSON",
                network_attempted=True,
                response_received=True,
                provider_http_status=status,
                transport_stage="response_decode",
            ) from exc
        if not isinstance(document, dict):
            raise ProviderProtocolError(
                "provider response root must be a JSON object",
                network_attempted=True,
                response_received=True,
                provider_http_status=status,
                transport_stage="response_decode",
            )
        return document
