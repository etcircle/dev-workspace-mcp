from __future__ import annotations

from fnmatch import fnmatch
from urllib.parse import urlparse

import httpx

from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.models.http_tools import HttpRequestResponse
from dev_workspace_mcp.policy.models import NetworkPolicy

_ALLOWED_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class LocalHttpClient:
    """Bounded local-first HTTP client for runtime verification."""

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: str | bytes | None = None,
        timeout_sec: int = 15,
        network_policy: NetworkPolicy | None = None,
    ) -> HttpRequestResponse:
        normalized_method = method.upper().strip()
        effective_policy = network_policy or NetworkPolicy()
        self._validate_url(url, effective_policy)
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
                message=f"HTTP request failed: {exc}",
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

    def _validate_url(self, url: str, network_policy: NetworkPolicy) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise DomainError(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"Unsupported URL scheme for HTTP request: {parsed.scheme or '<missing>'}",
                hint="Use an http:// or https:// URL.",
            )
        if not parsed.hostname:
            raise DomainError(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"HTTP request is missing a hostname: {url}",
            )
        if self._is_allowed_host(parsed.hostname, network_policy):
            return
        raise DomainError(
            code=ErrorCode.NETWORK_DENIED,
            message=f"Refusing HTTP destination outside project policy: {url}",
            hint=(
                "Allow localhost or add the hostname to "
                ".devworkspace/policy.yaml network.allowed_hosts."
            ),
            details={"url": url, "hostname": parsed.hostname},
        )

    def _is_allowed_host(self, hostname: str, network_policy: NetworkPolicy) -> bool:
        normalized = hostname.lower()
        if normalized in _ALLOWED_LOCAL_HOSTS and network_policy.allow_localhost:
            return True
        if any(fnmatch(normalized, pattern.lower()) for pattern in network_policy.allowed_hosts):
            return True
        return network_policy.default == "allow"



__all__ = ["LocalHttpClient"]
