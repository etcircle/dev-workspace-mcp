from __future__ import annotations

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server import server as server_module
from dev_workspace_mcp.mcp_server.tool_registry import ToolDefinition, ToolRegistry


def test_create_server_exposes_bootstrap_tools(
    monkeypatch,
    workspace_root,
    make_manifest_project,
) -> None:
    make_manifest_project()
    settings = Settings(workspace_roots=[str(workspace_root)])
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)

    server = server_module.create_server()
    tool_names = [tool.name for tool in server.tools.list_tools()]

    assert server.name == "dev-workspace-mcp"
    assert server.project_registry.list_projects()
    assert tool_names == [
        "apply_patch",
        "call_path",
        "cancel_job",
        "delete_path",
        "find_references",
        "function_context",
        "get_job",
        "get_logs",
        "git_checkout",
        "git_commit",
        "git_diff",
        "git_status",
        "grep",
        "http_request",
        "list_dir",
        "list_probes",
        "list_projects",
        "list_services",
        "module_overview",
        "move_path",
        "patch_state_doc",
        "project_snapshot",
        "read_file",
        "read_source",
        "read_state_doc",
        "recent_changes",
        "restart_service",
        "run_command",
        "run_probe",
        "service_status",
        "start_service",
        "stop_service",
        "watcher_health",
        "write_file",
        "write_state_doc",
    ]
    list_result = server.tools.run("list_projects", include_paths=True)
    assert list_result["ok"] is True
    assert list_result["data"]["projects"][0]["root_path"] is not None


def test_unknown_tool_returns_error(monkeypatch, workspace_root, make_manifest_project) -> None:
    make_manifest_project()
    settings = Settings(workspace_roots=[str(workspace_root)])
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)

    server = server_module.create_server()
    result = server.tools.run("nope")

    assert result["ok"] is False
    assert result["error"]["code"] == "INTERNAL_ERROR"


def test_tool_registry_wraps_unexpected_exceptions_as_internal_error() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="boom",
            description="Explodes for test coverage.",
            handler=lambda: (_ for _ in ()).throw(RuntimeError("kaboom")),
        )
    )

    result = registry.run("boom")

    assert result["ok"] is False
    assert result["error"]["code"] == "INTERNAL_ERROR"
    assert result["error"]["details"]["error"] == "kaboom"
