from __future__ import annotations

from dev_workspace_mcp.mcp_server.server import DevWorkspaceServer
from dev_workspace_mcp.mcp_server.transport_http import build_fastmcp_server


async def run_stdio_transport_async(server: DevWorkspaceServer) -> None:
    mcp = build_fastmcp_server(server)
    await mcp.run_stdio_async(show_banner=False)


__all__ = ["run_stdio_transport_async"]
