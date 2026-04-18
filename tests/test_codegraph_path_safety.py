from __future__ import annotations

from pathlib import Path

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.tool_registry import build_tool_registry
from dev_workspace_mcp.projects.registry import ProjectRegistry


def _build_tools(workspace_root: Path):
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    return build_tool_registry(registry)


def test_module_overview_denies_symlink_to_file_outside_project(workspace_root) -> None:
    project_root = workspace_root / "manifest-project"
    project_root.mkdir()
    (project_root / ".devworkspace.yaml").write_text(
        "name: Manifest Project\n"
        "project_id: manifest-id\n"
        "aliases:\n"
        "  - manifest-id-alias\n"
        "codegraph:\n"
        "  watch_paths:\n"
        "    - src\n",
        encoding="utf-8",
    )
    outside_file = workspace_root / "outside.py"
    outside_file.write_text("def secret():\n    return 1\n", encoding="utf-8")
    (project_root / "escape.py").symlink_to(outside_file)
    tools = _build_tools(workspace_root)

    result = tools.run("module_overview", project_id="manifest-id", path="escape.py")

    assert result["ok"] is False
    assert result["error"]["code"] == "PATH_OUTSIDE_PROJECT"


def test_watcher_health_denies_symlink_escape_in_watched_paths(workspace_root) -> None:
    project_root = workspace_root / "manifest-project"
    project_root.mkdir()
    (project_root / ".devworkspace.yaml").write_text(
        "name: Manifest Project\n"
        "project_id: manifest-id\n"
        "aliases:\n"
        "  - manifest-id-alias\n"
        "codegraph:\n"
        "  watch_paths:\n"
        "    - linked\n",
        encoding="utf-8",
    )
    outside_dir = workspace_root / "outside-codegraph"
    outside_dir.mkdir()
    (outside_dir / "escape.py").write_text("def leaked():\n    return 1\n", encoding="utf-8")
    (project_root / "linked").symlink_to(outside_dir, target_is_directory=True)
    tools = _build_tools(workspace_root)

    result = tools.run("watcher_health", project_id="manifest-id")

    assert result["ok"] is False
    assert result["error"]["code"] == "PATH_OUTSIDE_PROJECT"
