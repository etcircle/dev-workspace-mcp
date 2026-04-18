from __future__ import annotations

import sys
import time
from pathlib import Path

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.tool_registry import build_tool_registry
from dev_workspace_mcp.projects.registry import ProjectRegistry


def _build_tools(workspace_root: Path):
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    return build_tool_registry(registry)



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
    tools = _build_tools(workspace_root)

    first = tools.run("start_service", project_id="manifest-id", service_name="backend")
    assert first["ok"] is True
    assert first["data"]["service"]["runtime"]["restart_count"] == 0

    restarted = tools.run("restart_service", project_id="manifest-id", service_name="backend")
    assert restarted["ok"] is True
    assert restarted["data"]["service"]["runtime"]["restart_count"] == 1
    assert restarted["data"]["service"]["runtime"]["status"] == "running"

    tools.run("stop_service", project_id="manifest-id", service_name="backend")
