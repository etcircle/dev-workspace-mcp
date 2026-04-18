from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.tool_registry import build_tool_registry
from dev_workspace_mcp.projects.registry import ProjectRegistry


def _build_tools(workspace_root: Path):
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    return build_tool_registry(registry)


def _write_policy(project_root: Path, lines: list[str]) -> None:
    policy_dir = project_root / ".devworkspace"
    policy_dir.mkdir(exist_ok=True)
    (policy_dir / "policy.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_service_lifecycle_and_logs(workspace_root, make_manifest_project) -> None:
    project_root = make_manifest_project(
        services_block=[
            "services:",
            "  backend:",
            "    cwd: .",
            f"    start: ['{sys.executable}', '-u', 'service.py']",
        ]
    )
    (project_root / "service.py").write_text(
        "import time\n"
        "print('ready', flush=True)\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    _write_policy(
        project_root,
        [
            "command_policy:",
            "  commands:",
            f"    {Path(sys.executable).name}: {{}}",
        ],
    )
    tools = _build_tools(workspace_root)

    listed = tools.run("list_services", project_id="manifest-id")
    assert listed["ok"] is True
    assert listed["data"]["services"][0]["service_name"] == "backend"
    assert listed["data"]["services"][0]["runtime"]["status"] == "stopped"

    started = tools.run("start_service", project_id="manifest-id", service_name="backend")
    assert started["ok"] is True
    assert started["data"]["service"]["runtime"]["status"] == "running"
    assert started["data"]["service"]["runtime"]["pid"] is not None

    deadline = time.monotonic() + 3
    logs = tools.run("get_logs", project_id="manifest-id", service_name="backend")
    while not logs["data"]["lines"] and time.monotonic() < deadline:
        time.sleep(0.05)
        logs = tools.run("get_logs", project_id="manifest-id", service_name="backend")

    assert logs["ok"] is True
    assert any(line["message"] == "ready" for line in logs["data"]["lines"])

    status = tools.run("service_status", project_id="manifest-id", service_name="backend")
    assert status["ok"] is True
    assert status["data"]["service"]["runtime"]["status"] == "running"
    assert status["data"]["service"]["runtime"]["health"]["status"] == "healthy"

    stopped = tools.run("stop_service", project_id="manifest-id", service_name="backend")
    assert stopped["ok"] is True
    assert stopped["data"]["service"]["runtime"]["status"] == "stopped"


def test_restart_service_increments_restart_count(workspace_root, make_manifest_project) -> None:
    project_root = make_manifest_project(
        services_block=[
            "services:",
            "  backend:",
            "    cwd: .",
            f"    start: ['{sys.executable}', '-u', 'service.py']",
        ]
    )
    (project_root / "service.py").write_text(
        "import time\n"
        "print('hello', flush=True)\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    _write_policy(
        project_root,
        [
            "command_policy:",
            "  commands:",
            f"    {Path(sys.executable).name}: {{}}",
        ],
    )
    tools = _build_tools(workspace_root)

    first = tools.run("start_service", project_id="manifest-id", service_name="backend")
    assert first["ok"] is True
    assert first["data"]["service"]["runtime"]["restart_count"] == 0

    restarted = tools.run("restart_service", project_id="manifest-id", service_name="backend")
    assert restarted["ok"] is True
    assert restarted["data"]["service"]["runtime"]["restart_count"] == 1
    assert restarted["data"]["service"]["runtime"]["status"] == "running"

    tools.run("stop_service", project_id="manifest-id", service_name="backend")


def test_start_service_denies_cwd_symlink_escape(workspace_root, make_manifest_project) -> None:
    project_root = make_manifest_project(
        services_block=[
            "services:",
            "  backend:",
            "    cwd: linked",
            f"    start: ['{sys.executable}', '-u', 'service.py']",
        ]
    )
    outside_dir = workspace_root / "outside-service-cwd"
    outside_dir.mkdir()
    (project_root / "linked").symlink_to(outside_dir, target_is_directory=True)
    (project_root / "service.py").write_text("print('ready')\n", encoding="utf-8")
    _write_policy(
        project_root,
        [
            "command_policy:",
            "  commands:",
            f"    {Path(sys.executable).name}: {{}}",
        ],
    )
    tools = _build_tools(workspace_root)

    result = tools.run("start_service", project_id="manifest-id", service_name="backend")

    assert result["ok"] is False
    assert result["error"]["code"] == "PATH_OUTSIDE_PROJECT"


def test_service_status_denies_non_local_http_health_without_policy(
    workspace_root,
    make_manifest_project,
) -> None:
    make_manifest_project(
        services_block=[
            "services:",
            "  backend:",
            "    cwd: .",
            "    health:",
            "      type: http",
            "      url: https://example.com/health",
            "      expect_status: 200",
        ]
    )
    tools = _build_tools(workspace_root)

    result = tools.run("service_status", project_id="manifest-id", service_name="backend")

    assert result["ok"] is False
    assert result["error"]["code"] == "NETWORK_DENIED"


def test_service_status_allows_policy_approved_http_health(
    workspace_root,
    make_manifest_project,
    monkeypatch,
) -> None:
    project_root = make_manifest_project(
        services_block=[
            "services:",
            "  backend:",
            "    cwd: .",
            "    health:",
            "      type: http",
            "      url: https://example.com/health",
            "      expect_status: 200",
        ]
    )
    _write_policy(
        project_root,
        [
            "network:",
            "  allowed_hosts: ['example.com']",
        ],
    )
    tools = _build_tools(workspace_root)

    def _fake_request(method: str, url: str, headers, content, timeout):
        request = httpx.Request(method, url)
        return httpx.Response(200, request=request, text="ok")

    monkeypatch.setattr(httpx, "request", _fake_request)

    result = tools.run("service_status", project_id="manifest-id", service_name="backend")

    assert result["ok"] is True
    assert result["data"]["service"]["runtime"]["health"]["status"] == "healthy"
