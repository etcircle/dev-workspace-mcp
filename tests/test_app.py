from __future__ import annotations

from types import SimpleNamespace

import pytest

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


def test_serve_http_command_preserves_existing_transport_dispatch(monkeypatch, capsys) -> None:
    calls: dict[str, object] = {}
    server = SimpleNamespace(
        name="dev-workspace-mcp",
        project_registry=SimpleNamespace(
            settings=SimpleNamespace(host="127.0.0.1", port=8081)
        ),
    )

    async def fake_run_http_transport_async(*args, **kwargs) -> None:
        calls["args"] = args
        calls["kwargs"] = kwargs

    monkeypatch.setattr(app_module, "create_server", lambda: server)
    monkeypatch.setattr(app_module, "run_http_transport_async", fake_run_http_transport_async)

    app_module.main(["serve-http", "--path", "/custom", "--log-level", "debug"])

    assert calls == {
        "args": (server,),
        "kwargs": {
            "host": "127.0.0.1",
            "port": 8081,
            "path": "/custom",
            "log_level": "debug",
        },
    }
    captured = capsys.readouterr()
    assert "Serving dev-workspace-mcp on http://127.0.0.1:8081/custom" in captured.out
    assert captured.err == ""


def test_serve_http_command_rejects_public_bind_without_override(monkeypatch, capsys) -> None:
    server = SimpleNamespace(
        name="dev-workspace-mcp",
        project_registry=SimpleNamespace(
            settings=SimpleNamespace(host="127.0.0.1", port=8081)
        ),
    )

    async def fake_run_http_transport_async(*args, **kwargs) -> None:
        raise AssertionError("run_http_transport_async should not be called")

    monkeypatch.setattr(app_module, "create_server", lambda: server)
    monkeypatch.setattr(app_module, "run_http_transport_async", fake_run_http_transport_async)

    with pytest.raises(SystemExit, match="Refusing non-local HTTP bind"):
        app_module.main(["serve-http", "--host", "0.0.0.0"])

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_serve_http_command_allows_public_bind_with_explicit_warning(monkeypatch, capsys) -> None:
    calls: dict[str, object] = {}
    server = SimpleNamespace(
        name="dev-workspace-mcp",
        project_registry=SimpleNamespace(
            settings=SimpleNamespace(host="127.0.0.1", port=8081)
        ),
    )

    async def fake_run_http_transport_async(*args, **kwargs) -> None:
        calls["args"] = args
        calls["kwargs"] = kwargs

    monkeypatch.setattr(app_module, "create_server", lambda: server)
    monkeypatch.setattr(app_module, "run_http_transport_async", fake_run_http_transport_async)

    app_module.main(["serve-http", "--host", "0.0.0.0", "--allow-public-bind"])

    assert calls == {
        "args": (server,),
        "kwargs": {
            "host": "0.0.0.0",
            "port": 8081,
            "path": "/mcp",
            "log_level": "info",
        },
    }
    captured = capsys.readouterr()
    assert "Serving dev-workspace-mcp on http://0.0.0.0:8081/mcp" in captured.out
    assert "WARNING: --allow-public-bind is enabled." in captured.err
    assert "http://0.0.0.0:8081/mcp" in captured.err


def test_stdio_command_runs_stdio_transport(monkeypatch) -> None:
    calls: dict[str, object] = {}
    server = SimpleNamespace(name="dev-workspace-mcp")

    async def fake_run_stdio_transport_async(*args, **kwargs) -> None:
        calls["args"] = args
        calls["kwargs"] = kwargs

    monkeypatch.setattr(app_module, "create_server", lambda: server)
    monkeypatch.setattr(app_module, "run_stdio_transport_async", fake_run_stdio_transport_async)

    app_module.main(["stdio"])

    assert calls == {"args": (server,), "kwargs": {}}


def test_cli_command_delegates_without_building_server(monkeypatch) -> None:
    calls: dict[str, object] = {}

    def fake_cli_main(argv) -> int:
        calls["argv"] = list(argv)
        return 0

    monkeypatch.setattr(
        app_module,
        "create_server",
        lambda: (_ for _ in ()).throw(AssertionError("create_server should not run for cli")),
    )
    monkeypatch.setattr(app_module, "cli_main", fake_cli_main, raising=False)

    app_module.main(["cli", "--json", "projects"])

    assert calls == {"argv": ["--json", "projects"]}
