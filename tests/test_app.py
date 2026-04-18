from __future__ import annotations

from dev_workspace_mcp import app as app_module
from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server import server as server_module


def test_describe_command_prints_server_summary(
    monkeypatch,
    capsys,
    workspace_root,
    make_manifest_project,
) -> None:
    make_manifest_project()
    settings = Settings(workspace_roots=[str(workspace_root)], host="127.0.0.1", port=8081)
    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    monkeypatch.setattr(app_module, "create_server", server_module.create_server)

    app_module.main(["describe"])

    output = capsys.readouterr().out
    assert "Dev Workspace MCP ready: dev-workspace-mcp" in output
    assert "HTTP: http://127.0.0.1:8081/mcp" in output
    assert "- project_snapshot" in output
