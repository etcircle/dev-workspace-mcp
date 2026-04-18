from __future__ import annotations

import asyncio

from fastmcp import FastMCP

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server import server as server_module
from dev_workspace_mcp.mcp_server import transport_stdio as stdio_module


def test_run_stdio_transport_async_builds_real_fastmcp_server(
    monkeypatch,
    workspace_root,
    make_manifest_project,
) -> None:
    make_manifest_project()
    settings = Settings(workspace_roots=[str(workspace_root)])
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    server = server_module.create_server()
    calls: dict[str, object] = {}

    async def fake_run_stdio_async(self, *, show_banner: bool) -> None:
        tools = await self.list_tools(run_middleware=False)
        calls["name"] = self.name
        calls["show_banner"] = show_banner
        calls["tool_names"] = sorted(tool.name for tool in tools)

    monkeypatch.setattr(FastMCP, "run_stdio_async", fake_run_stdio_async)

    asyncio.run(stdio_module.run_stdio_transport_async(server))

    assert calls["name"] == "dev-workspace-mcp"
    assert calls["show_banner"] is False
    assert "project_snapshot" in calls["tool_names"]
    assert "read_file" in calls["tool_names"]
