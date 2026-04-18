from __future__ import annotations

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.tool_registry import build_tool_registry
from dev_workspace_mcp.projects.registry import ProjectRegistry


def test_project_snapshot_warns_when_manifest_and_agents_are_missing(
    workspace_root,
    make_git_project,
) -> None:
    make_git_project()
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    tools = build_tool_registry(registry)

    result = tools.run("project_snapshot", project_id="git-project")

    assert result["ok"] is True
    assert result["data"]["project"]["project_id"] == "git-project"
    assert result["data"]["project"]["manifest_path"] is None
    warning_codes = {warning["code"] for warning in result["warnings"]}
    assert {"MANIFEST_MISSING", "AGENTS_MISSING", "GIT_STATUS_UNAVAILABLE"} <= warning_codes
    assert result["data"]["watcher"]["configured"] is False
    assert result["data"]["recent_changed_files"] == []
    assert any(
        doc["kind"] == "agents" and doc["exists"] is False
        for doc in result["data"]["state_docs"]
    )


def test_project_snapshot_includes_manifest_services_state_docs_and_watcher_metrics(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project(
        services_block=[
            "services:",
            "  backend:",
            "    cwd: backend",
            "    start: ['uvicorn', 'app.main:app']",
            "    ports: [8000]",
            "    health:",
            "      type: http",
            "      url: http://127.0.0.1:8000/health",
            "      expect_status: 200",
            "presets:",
            "  test_backend: ['pytest', '-q']",
            "probes:",
            "  backend_db:",
            "    cwd: backend",
            "    argv: ['python', '-m', 'scripts.check_db']",
        ]
    )
    (project_root / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")
    state_dir = project_root / ".devworkspace"
    state_dir.mkdir()
    (state_dir / "memory.md").write_text("known fact\n", encoding="utf-8")
    src = project_root / "src"
    src.mkdir()
    (project_root / "README.md").write_text("outside watcher scope\n", encoding="utf-8")
    (
        src / "sample.py"
    ).write_text(
        "class Service:\n"
        "    def run(self):\n"
        "        return helper()\n\n"
        "def helper():\n"
        "    return 'ok'\n",
        encoding="utf-8",
    )

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    tools = build_tool_registry(registry)

    result = tools.run("project_snapshot", project_id="manifest-id")

    assert result["ok"] is True
    assert result["warnings"] == []
    assert result["data"]["services"] == [
        {"name": "backend", "cwd": "backend", "ports": [8000], "has_health_check": True}
    ]
    assert result["data"]["watcher"]["watched_paths"] == ["src"]
    assert result["data"]["watcher"]["status"] == "active"
    assert result["data"]["watcher"]["file_count"] == 1
    assert result["data"]["watcher"]["symbol_count"] == 3
    assert result["data"]["watcher"]["revision"]
    assert result["data"]["watcher"]["indexed_at"]
    assert result["data"]["probes"] == ["backend_db"]
    assert result["data"]["presets"] == ["test_backend"]
    assert any(
        doc["kind"] == "agents" and doc["exists"] is True
        for doc in result["data"]["state_docs"]
    )
    assert any(
        doc["kind"] == "memory" and doc["char_count"] > 0
        for doc in result["data"]["state_docs"]
    )
