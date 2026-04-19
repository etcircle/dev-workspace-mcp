from __future__ import annotations

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server import server as server_module
from dev_workspace_mcp.mcp_server.tool_registry import ToolDefinition, ToolRegistry

_VALID_CONNECTION_PROFILE = {
    "kind": "postgres",
    "transport": "direct",
    "host_env": "PGHOST",
    "port_env": "PGPORT",
    "database_env": "PGDATABASE",
    "user_env": "PGUSER",
    "password_env": "PGPASSWORD",
}


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
        "bootstrap_project",
        "call_path",
        "cancel_job",
        "configure_connection",
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
        "list_connections",
        "list_dir",
        "list_probes",
        "list_projects",
        "list_services",
        "memory_index_status",
        "module_overview",
        "move_path",
        "patch_state_doc",
        "project_snapshot",
        "read_file",
        "read_source",
        "read_state_doc",
        "recent_changes",
        "record_session_summary",
        "reindex_workspace_memory",
        "restart_service",
        "run_command",
        "run_probe",
        "search_workspace_memory",
        "service_status",
        "start_service",
        "stop_service",
        "test_connection",
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


def test_bootstrap_and_connection_tools_return_structured_success_and_error_envelopes(
    monkeypatch,
    workspace_root,
) -> None:
    settings = Settings(workspace_roots=[str(workspace_root)])
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)

    server = server_module.create_server()

    invalid_bootstrap = server.tools.run("bootstrap_project", mode="create")
    invalid_bootstrap_extra = server.tools.run(
        "bootstrap_project",
        mode="create",
        folder_name="demo-project",
        bogus="x",
    )

    assert invalid_bootstrap["ok"] is False
    assert invalid_bootstrap["error"]["code"] == "VALIDATION_ERROR"
    assert invalid_bootstrap["error"]["details"]["issues"][0]["field"] == "folder_name"
    assert invalid_bootstrap_extra["ok"] is False
    assert invalid_bootstrap_extra["error"]["code"] == "VALIDATION_ERROR"

    bootstrap_result = server.tools.run(
        "bootstrap_project",
        mode="create",
        folder_name="demo-project",
        display_name="Demo Project",
    )

    assert bootstrap_result["ok"] is True
    assert bootstrap_result["data"]["project_id"] == "demo-project"
    assert bootstrap_result["data"]["root_path"] == str(workspace_root / "demo-project")
    assert bootstrap_result["data"]["manifest_path"] == str(
        workspace_root / "demo-project" / ".devworkspace.yaml"
    )
    assert ".devworkspace.yaml" in bootstrap_result["data"]["created_files"]
    assert bootstrap_result["data"]["recommended_next_tools"] == [
        "list_projects",
        "project_snapshot",
    ]

    configure_result = server.tools.run(
        "configure_connection",
        project_id="demo-project",
        connection_name="primary",
        profile=_VALID_CONNECTION_PROFILE,
    )
    configure_result_extra = server.tools.run(
        "configure_connection",
        project_id="demo-project",
        connection_name="primary",
        profile={**_VALID_CONNECTION_PROFILE, "bogus": "x"},
    )

    assert configure_result["ok"] is True
    assert configure_result["data"]["project_id"] == "demo-project"
    assert configure_result["data"]["connection_name"] == "primary"
    assert configure_result["data"]["profile"]["kind"] == "postgres"
    assert configure_result["data"]["env_keys_updated"] == []
    assert configure_result_extra["ok"] is False
    assert configure_result_extra["error"]["code"] == "VALIDATION_ERROR"

    list_connections_result = server.tools.run(
        "list_connections",
        project_id="demo-project",
    )

    assert list_connections_result["ok"] is True
    assert list_connections_result["data"] == {
        "project_id": "demo-project",
        "connections": {"primary": configure_result["data"]["profile"]},
    }

    test_connection_result = server.tools.run(
        "test_connection",
        project_id="demo-project",
        connection_name="primary",
    )

    assert test_connection_result["ok"] is False
    assert test_connection_result["error"]["code"] == "CONNECTION_TEST_FAILED"
    assert test_connection_result["error"]["details"]["connection_name"] == "primary"
    assert test_connection_result["error"]["details"]["missing_env_keys"] == [
        "PGHOST",
        "PGPORT",
    ]


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


def test_tool_registry_reports_argument_shape_errors_as_validation_errors() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo",
            description="Echo one value.",
            handler=lambda value: {"value": value},
        )
    )

    result = registry.run("echo", bogus=True)

    assert result["ok"] is False
    assert result["error"]["code"] == "VALIDATION_ERROR"
