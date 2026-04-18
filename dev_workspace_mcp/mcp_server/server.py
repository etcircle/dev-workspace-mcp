from __future__ import annotations

from dataclasses import dataclass

from dev_workspace_mcp.config import get_settings
from dev_workspace_mcp.mcp_server.tool_registry import ToolRegistry, build_tool_registry
from dev_workspace_mcp.runtime import DevWorkspaceRuntime, create_runtime


@dataclass(slots=True)
class DevWorkspaceServer:
    name: str
    runtime: DevWorkspaceRuntime
    tools: ToolRegistry

    @property
    def project_registry(self):
        return self.runtime.project_registry



def create_server() -> DevWorkspaceServer:
    runtime = create_runtime(get_settings())
    tools = build_tool_registry(runtime.project_registry, services=runtime.services)
    return DevWorkspaceServer(
        name=runtime.name,
        runtime=runtime,
        tools=tools,
    )
