from __future__ import annotations

from urllib.parse import urlparse

import httpx

from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.models.http_tools import HttpRequestResponse

_ALLOWED_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class LocalHttpClient:
    """Bounded local-only HTTP client for runtime verification."""

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: str | bytes | None = None,
        timeout_sec: int = 15,
    ) -> HttpRequestResponse:
        normalized_method = method.upper().strip()
        self._validate_local_url(url)
        try:
            response = httpx.request(
                normalized_method,
                url,
                headers=headers or {},
                content=body,
                timeout=timeout_sec,
            )
        except httpx.HTTPError as exc:
            raise DomainError(
                code=ErrorCode.HTTP_REQUEST_FAILED,
                message=f"Local HTTP request failed: {exc}",
                details={"method": normalized_method, "url": url},
            ) from exc

        json_body = None
        try:
            json_body = response.json()
        except ValueError:
            json_body = None

        return HttpRequestResponse(
            method=normalized_method,
            url=str(response.request.url),
            status_code=response.status_code,
            headers={key: value for key, value in response.headers.items()},
            text_body=response.text,
            json_body=json_body,
        )

    def _validate_local_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise DomainError(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"Unsupported URL scheme for local request: {parsed.scheme or '<missing>'}",
                hint="Use an http:// or https:// URL pointing at localhost or 127.0.0.1.",
            )
        if not parsed.hostname or parsed.hostname not in _ALLOWED_LOCAL_HOSTS:
            raise DomainError(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"Refusing non-local HTTP destination: {url}",
                hint="http_request only allows localhost, 127.0.0.1, or ::1.",
            )


__all__ = ["LocalHttpClient"]
