from __future__ import annotations

import inspect
from dataclasses import dataclass
from functools import wraps
from typing import Any

from fastmcp import FastMCP

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
    app = mcp.http_app(path=path, transport=transport)
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
    mounted = mount_http_transport(server, path=path)
    await mounted.mcp.run_http_async(
        show_banner=False,
        transport=mounted.transport,
        host=host,
        port=port,
        path=path,
        log_level=log_level,
    )


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
