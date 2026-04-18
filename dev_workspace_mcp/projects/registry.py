from __future__ import annotations

from pathlib import Path

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.models.projects import ProjectListItem, ProjectRecord
from dev_workspace_mcp.projects.discovery import discover_project_roots
from dev_workspace_mcp.projects.manifest import load_manifest, manifest_path_for


class ProjectRegistry:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._projects: dict[str, ProjectRecord] = {}
        self._aliases: dict[str, str] = {}

    def refresh(self) -> None:
        projects: dict[str, ProjectRecord] = {}
        aliases: dict[str, str] = {}

        for project_root in discover_project_roots(self.settings):
            record = self._build_record(project_root)
            self._register_project(projects, record)
            self._register_aliases(aliases, projects, record)

        self._projects = projects
        self._aliases = aliases

    def list_projects(self) -> list[ProjectRecord]:
        return [self._projects[key] for key in sorted(self._projects)]

    def list_items(
        self,
        *,
        include_paths: bool = False,
        query: str | None = None,
    ) -> list[ProjectListItem]:
        normalized_query = (query or "").strip().lower()
        items: list[ProjectListItem] = []
        for project in self.list_projects():
            haystack_parts = [project.project_id, project.display_name, *project.aliases]
            haystack = " ".join(haystack_parts).lower()
            if normalized_query and normalized_query not in haystack:
                continue
            items.append(
                ProjectListItem(
                    project_id=project.project_id,
                    display_name=project.display_name,
                    aliases=project.aliases,
                    manifest_present=project.manifest_path is not None,
                    root_path=project.root_path if include_paths else None,
                    services=sorted(project.manifest.services.keys()),
                    codegraph_enabled=bool(project.manifest.codegraph.watch_paths),
                )
            )
        return items

    def get(self, project_id: str) -> ProjectRecord | None:
        resolved = self._aliases.get(project_id, project_id)
        return self._projects.get(resolved)

    def require(self, project_id: str) -> ProjectRecord:
        record = self.get(project_id)
        if record is None:
            raise DomainError(
                code=ErrorCode.PROJECT_NOT_FOUND,
                message=f"Unknown project_id: {project_id}",
                hint="Call list_projects first to find a valid project_id.",
            )
        return record

    def _build_record(self, project_root: Path) -> ProjectRecord:
        manifest = load_manifest(project_root)
        project_id = (manifest.project_id or project_root.name).strip()
        display_name = (manifest.name or project_root.name).strip()
        if not project_id:
            raise DomainError(
                code=ErrorCode.INVALID_PROJECT_ID,
                message=f"Project at {project_root} resolved to an empty project_id.",
                hint="Set a non-empty project_id in .devworkspace.yaml or rename the folder.",
            )

        manifest_path = manifest_path_for(project_root)
        return ProjectRecord(
            project_id=project_id,
            display_name=display_name,
            root_path=str(project_root.resolve()),
            manifest_path=str(manifest_path) if manifest_path.exists() else None,
            aliases=sorted(set(alias.strip() for alias in manifest.aliases if alias.strip())),
            manifest=manifest,
        )

    def _register_project(self, projects: dict[str, ProjectRecord], record: ProjectRecord) -> None:
        if record.project_id in projects:
            raise DomainError(
                code=ErrorCode.PROJECT_CONFLICT,
                message=f"Duplicate project_id discovered: {record.project_id}",
                hint="Make project_id values unique across all workspace roots.",
                details={
                    "project_id": record.project_id,
                    "existing_root": projects[record.project_id].root_path,
                    "conflicting_root": record.root_path,
                },
            )
        projects[record.project_id] = record

    def _register_aliases(
        self,
        aliases: dict[str, str],
        projects: dict[str, ProjectRecord],
        record: ProjectRecord,
    ) -> None:
        for alias in record.aliases:
            if alias == record.project_id:
                continue
            if alias in projects and projects[alias].project_id != record.project_id:
                raise DomainError(
                    code=ErrorCode.PROJECT_CONFLICT,
                    message=f"Alias '{alias}' conflicts with a canonical project_id.",
                    hint="Rename the alias or the conflicting project_id.",
                    details={"alias": alias, "project_id": record.project_id},
                )
            if alias in aliases and aliases[alias] != record.project_id:
                raise DomainError(
                    code=ErrorCode.PROJECT_CONFLICT,
                    message=f"Alias '{alias}' is assigned to multiple projects.",
                    hint="Aliases must be globally unique.",
                    details={"alias": alias, "project_id": record.project_id},
                )
            aliases[alias] = record.project_id
