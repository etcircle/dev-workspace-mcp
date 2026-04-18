from __future__ import annotations

import pytest

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.projects.registry import ProjectRegistry


def test_project_registry_discovers_git_and_manifest_projects(
    workspace_root,
    make_git_project,
    make_manifest_project,
) -> None:
    git_project = make_git_project()
    manifest_project = make_manifest_project(
        display_name="Demo Project",
        project_id="demo-id",
        alias="demo",
    )

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()

    projects = {project.project_id: project for project in registry.list_projects()}

    assert set(projects) == {"git-project", "demo-id"}
    assert projects["git-project"].root_path == str(git_project.resolve())
    assert projects["git-project"].manifest_path is None
    assert projects["demo-id"].display_name == "Demo Project"
    assert projects["demo-id"].manifest_path == str(manifest_project / ".devworkspace.yaml")
    assert registry.require("demo").project_id == "demo-id"


def test_list_items_supports_query_and_include_paths(
    workspace_root,
    make_manifest_project,
) -> None:
    make_manifest_project(
        name="alpha-folder",
        display_name="Alpha Workspace",
        project_id="alpha-id",
    )
    make_manifest_project(
        name="beta-folder",
        display_name="Beta Workspace",
        project_id="beta-id",
    )

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()

    filtered = registry.list_items(query="beta")
    assert [item.project_id for item in filtered] == ["beta-id"]
    assert filtered[0].root_path is None

    with_paths = registry.list_items(query="alpha", include_paths=True)
    assert with_paths[0].root_path == str((workspace_root / "alpha-folder").resolve())
    assert with_paths[0].manifest_present is True
    assert with_paths[0].codegraph_enabled is True


def test_duplicate_alias_raises_conflict(workspace_root, make_manifest_project) -> None:
    make_manifest_project(name="one", project_id="one-id", alias="shared")
    make_manifest_project(name="two", project_id="two-id", alias="shared")

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))

    with pytest.raises(DomainError) as exc:
        registry.refresh()

    assert exc.value.code == ErrorCode.PROJECT_CONFLICT


def test_invalid_manifest_raises_domain_error(workspace_root) -> None:
    broken_project = workspace_root / "broken"
    broken_project.mkdir()
    (broken_project / ".devworkspace.yaml").write_text("services: [oops\n", encoding="utf-8")

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))

    with pytest.raises(DomainError) as exc:
        registry.refresh()

    assert exc.value.code == ErrorCode.MANIFEST_INVALID
