from __future__ import annotations

from dataclasses import dataclass

from dev_workspace_mcp.config import get_settings
from dev_workspace_mcp.mcp_server.tool_registry import ToolRegistry, build_tool_registry
from dev_workspace_mcp.projects.registry import ProjectRegistry


@dataclass(slots=True)
class DevWorkspaceServer:
    name: str
    project_registry: ProjectRegistry
    tools: ToolRegistry



def create_server() -> DevWorkspaceServer:
    settings = get_settings()
    project_registry = ProjectRegistry(settings)
    project_registry.refresh()
    tools = build_tool_registry(project_registry)
    return DevWorkspaceServer(
        name="dev-workspace-mcp",
        project_registry=project_registry,
        tools=tools,
    )
