from __future__ import annotations

import inspect
from dataclasses import dataclass
from functools import wraps
from typing import Any
from urllib.parse import urlparse

from fastmcp import FastMCP
from starlette.datastructures import Headers
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse

from dev_workspace_mcp.config import is_local_http_host
from dev_workspace_mcp.mcp_server.server import DevWorkspaceServer
from dev_workspace_mcp.mcp_server.tool_registry import ToolDefinition, ToolRegistry


@dataclass(slots=True)
class HttpTransportMount:
    server: DevWorkspaceServer
    mcp: FastMCP
    app: Any
    path: str = "/mcp"
    transport: str = "streamable-http"


def build_fastmcp_server(server: DevWorkspaceServer) -> FastMCP:
    mcp = FastMCP(
        name=server.name,
        instructions=(
            "Project-aware MCP server for remote coding agents. "
            "Use list_projects first, then project_snapshot, then the narrower tools."
        ),
    )
    for definition in server.tools.list_tools():
        mcp.tool(name=definition.name, description=definition.description)(
            _make_tool_wrapper(server.tools, definition)
        )
    return mcp


def mount_http_transport(
    server: DevWorkspaceServer,
    *,
    path: str = "/mcp",
    transport: str = "streamable-http",
) -> HttpTransportMount:
    mcp = build_fastmcp_server(server)
    app = mcp.http_app(
        path=path,
        transport=transport,
        middleware=_http_transport_middleware(),
    )
    return HttpTransportMount(
        server=server,
        mcp=mcp,
        app=app,
        path=path,
        transport=transport,
    )


async def run_http_transport_async(
    server: DevWorkspaceServer,
    *,
    host: str,
    port: int,
    path: str = "/mcp",
    log_level: str = "info",
) -> None:
    mcp = build_fastmcp_server(server)
    await mcp.run_http_async(
        show_banner=False,
        transport="streamable-http",
        host=host,
        port=port,
        path=path,
        log_level=log_level,
        middleware=_http_transport_middleware(),
    )


def _http_transport_middleware() -> list[Middleware]:
    return [Middleware(LocalOriginFilterMiddleware)]


class LocalOriginFilterMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            origin = Headers(scope=scope).get("origin")
            if origin and not _is_allowed_local_origin(origin):
                response = PlainTextResponse(
                    "Origin not allowed for local MCP HTTP transport.",
                    status_code=403,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _is_allowed_local_origin(origin: str) -> bool:
    parsed = urlparse(origin)
    if not parsed.scheme or parsed.hostname is None:
        return False
    return is_local_http_host(parsed.hostname)


def _make_tool_wrapper(tool_registry: ToolRegistry, definition: ToolDefinition):
    signature = inspect.signature(definition.handler)

    @wraps(definition.handler)
    def _wrapper(*args, **kwargs):
        bound = signature.bind_partial(*args, **kwargs)
        return tool_registry.run(definition.name, **bound.arguments)

    _wrapper.__name__ = definition.name.replace(".", "_").replace("-", "_")
    _wrapper.__qualname__ = _wrapper.__name__
    _wrapper.__signature__ = signature
    _wrapper.__doc__ = definition.description
    return _wrapper


__all__ = [
    "HttpTransportMount",
    "build_fastmcp_server",
    "mount_http_transport",
    "run_http_transport_async",
]
