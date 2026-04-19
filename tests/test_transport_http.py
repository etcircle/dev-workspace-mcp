from __future__ import annotations

import asyncio

from starlette.testclient import TestClient

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


def test_http_transport_allows_no_origin_and_localhost_origin(
    monkeypatch,
    workspace_root,
    make_manifest_project,
) -> None:
    make_manifest_project()
    settings = Settings(workspace_roots=[str(workspace_root)])
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    server = server_module.create_server()
    transport = mount_http_transport(server)

    with TestClient(transport.app) as client:
        no_origin_response = client.get("/mcp", headers={"accept": "text/event-stream"})
        localhost_origin_response = client.get(
            "/mcp",
            headers={
                "accept": "text/event-stream",
                "origin": "http://localhost:3000",
            },
        )
        ipv4_loopback_origin_response = client.get(
            "/mcp",
            headers={
                "accept": "text/event-stream",
                "origin": "http://127.0.0.1:3000",
            },
        )
        ipv6_loopback_origin_response = client.get(
            "/mcp",
            headers={
                "accept": "text/event-stream",
                "origin": "http://[::1]:3000",
            },
        )

    assert no_origin_response.status_code == 400
    assert localhost_origin_response.status_code == 400
    assert ipv4_loopback_origin_response.status_code == 400
    assert ipv6_loopback_origin_response.status_code == 400


def test_http_transport_rejects_unexpected_origin_before_tool_layer(
    monkeypatch,
    workspace_root,
    make_manifest_project,
) -> None:
    make_manifest_project()
    settings = Settings(workspace_roots=[str(workspace_root)])
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    server = server_module.create_server()
    transport = mount_http_transport(server)

    with TestClient(transport.app) as client:
        response = client.get(
            "/mcp",
            headers={
                "accept": "text/event-stream",
                "origin": "https://evil.example",
            },
        )

    assert response.status_code == 403
    assert response.text == "Origin not allowed for local MCP HTTP transport."


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
