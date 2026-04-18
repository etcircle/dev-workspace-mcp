from __future__ import annotations

from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.models.projects import ProjectRecord
from dev_workspace_mcp.projects.registry import ProjectRegistry


class ProjectResolver:
    def __init__(self, registry: ProjectRegistry):
        self.registry = registry

    def resolve(self, project_id: str) -> ProjectRecord:
        record = self.registry.get(project_id)
        if record is None:
            raise DomainError(
                code=ErrorCode.PROJECT_NOT_FOUND,
                message=f"Unknown project_id: {project_id}",
                hint="Call list_projects first to find a valid project_id.",
            )
        return record
