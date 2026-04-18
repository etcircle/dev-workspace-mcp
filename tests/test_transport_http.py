from __future__ import annotations

import asyncio

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server import server as server_module
from dev_workspace_mcp.mcp_server.transport_http import mount_http_transport

EXPECTED_TOOL_NAMES = [
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
    "test_connection",
    "watcher_health",
    "write_file",
    "write_state_doc",
]


def test_mount_http_transport_exposes_all_registered_tools(
    monkeypatch,
    workspace_root,
    make_manifest_project,
) -> None:
    make_manifest_project()
    settings = Settings(workspace_roots=[str(workspace_root)])
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    server = server_module.create_server()

    transport = mount_http_transport(server)
    tools = asyncio.run(transport.mcp.list_tools())
    tool_names = [tool.name for tool in tools]
    route_paths = {route.path for route in transport.app.routes}

    assert tool_names == EXPECTED_TOOL_NAMES
    assert "/mcp" in route_paths


def test_fastmcp_call_tool_returns_same_envelope_as_registry(
    monkeypatch,
    workspace_root,
    make_manifest_project,
) -> None:
    make_manifest_project()
    settings = Settings(workspace_roots=[str(workspace_root)])
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    server = server_module.create_server()
    transport = mount_http_transport(server)

    result = asyncio.run(
        transport.mcp.call_tool("list_projects", {"include_paths": True})
    )

    payload = result.structured_content
    assert payload["ok"] is True
    assert payload["data"]["projects"][0]["project_id"] == "manifest-id"
    assert payload["data"]["projects"][0]["root_path"] is not None


def test_fastmcp_preserves_domain_error_envelope(
    monkeypatch,
    workspace_root,
    make_manifest_project,
) -> None:
    make_manifest_project()
    settings = Settings(workspace_roots=[str(workspace_root)])
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    server = server_module.create_server()
    transport = mount_http_transport(server)

    result = asyncio.run(
        transport.mcp.call_tool("project_snapshot", {"project_id": "missing-project"})
    )

    payload = result.structured_content
    assert payload["ok"] is False
    assert payload["error"]["code"] == "PROJECT_NOT_FOUND"
