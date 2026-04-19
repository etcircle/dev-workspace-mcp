from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.tool_registry import build_tool_registry
from dev_workspace_mcp.projects.registry import ProjectRegistry
from dev_workspace_mcp.services.logs import ServiceLogStore


def _build_tools(workspace_root: Path, **settings_overrides):
    settings = Settings(
        workspace_roots=[str(workspace_root)],
        **settings_overrides,
    )
    registry = ProjectRegistry(settings)
    registry.refresh()
    return build_tool_registry(registry)


def _write_policy(project_root: Path, lines: list[str]) -> None:
    policy_dir = project_root / ".devworkspace"
    policy_dir.mkdir(exist_ok=True)
    (policy_dir / "policy.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_start_service_returns_validation_error_when_executable_is_missing(
    workspace_root,
    make_manifest_project,
) -> None:
    missing_python = workspace_root / "missing-python"
    project_root = make_manifest_project(
        services_block=[
            "services:",
            "  backend:",
            "    cwd: .",
            f"    start: ['{missing_python}', '-u', 'service.py']",
        ]
    )
    (project_root / "service.py").write_text("print('ready')\n", encoding="utf-8")
    _write_policy(
        project_root,
        [
            "command_policy:",
            "  commands:",
            f"    {missing_python.name}: {{}}",
        ],
    )
    tools = _build_tools(workspace_root)

    result = tools.run("start_service", project_id="manifest-id", service_name="backend")

    assert result["ok"] is False
    assert result["error"]["code"] == "VALIDATION_ERROR"
    assert "failed to start" in result["error"]["message"]

    status = tools.run("service_status", project_id="manifest-id", service_name="backend")
    assert status["ok"] is True
    assert status["data"]["service"]["runtime"]["status"] == "failed"
    assert status["data"]["service"]["runtime"]["pid"] is None



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


def test_service_status_reports_unhealthy_when_health_command_executable_is_missing(
    workspace_root,
    make_manifest_project,
) -> None:
    missing_python = workspace_root / "missing-health-python"
    project_root = make_manifest_project(
        services_block=[
            "services:",
            "  backend:",
            "    cwd: .",
            f"    start: ['{sys.executable}', '-u', 'service.py']",
            "    health:",
            "      type: command",
            f"      argv: ['{missing_python}', '-c', 'print(1)']",
        ]
    )
    (project_root / "service.py").write_text(
        "import time\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    _write_policy(
        project_root,
        [
            "command_policy:",
            "  commands:",
            f"    {Path(sys.executable).name}: {{}}",
            f"    {missing_python.name}: {{}}",
        ],
    )
    tools = _build_tools(workspace_root)

    started = tools.run("start_service", project_id="manifest-id", service_name="backend")
    assert started["ok"] is True

    result = tools.run("service_status", project_id="manifest-id", service_name="backend")

    assert result["ok"] is True
    assert result["data"]["service"]["runtime"]["health"]["status"] == "unhealthy"
    assert "failed to start" in result["data"]["service"]["runtime"]["health"]["message"]

    tools.run("stop_service", project_id="manifest-id", service_name="backend")



def test_service_status_denies_non_local_http_health_without_policy(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project(
        services_block=[
            "services:",
            "  backend:",
            "    cwd: .",
            f"    start: ['{sys.executable}', '-u', 'service.py']",
            "    health:",
            "      type: http",
            "      url: https://example.com/health",
            "      expect_status: 200",
        ]
    )
    (project_root / "service.py").write_text(
        "import time\n"
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

    result = tools.run("start_service", project_id="manifest-id", service_name="backend")

    assert result["ok"] is False
    assert result["error"]["code"] == "NETWORK_DENIED"

    status = tools.run("service_status", project_id="manifest-id", service_name="backend")
    assert status["ok"] is True
    assert status["data"]["service"]["runtime"]["status"] == "failed"
    assert status["data"]["service"]["runtime"]["pid"] is None



def test_service_status_reports_unhealthy_when_http_health_endpoint_is_unreachable(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project(
        services_block=[
            "services:",
            "  backend:",
            "    cwd: .",
            f"    start: ['{sys.executable}', '-u', 'service.py']",
            "    health:",
            "      type: http",
            "      url: http://127.0.0.1:65534/health",
            "      expect_status: 200",
        ]
    )
    (project_root / "service.py").write_text(
        "import time\n"
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

    started = tools.run("start_service", project_id="manifest-id", service_name="backend")
    assert started["ok"] is True
    assert started["data"]["service"]["runtime"]["health"]["status"] == "unhealthy"

    status = tools.run("service_status", project_id="manifest-id", service_name="backend")
    assert status["ok"] is True
    assert status["data"]["service"]["runtime"]["status"] == "running"
    assert status["data"]["service"]["runtime"]["health"]["status"] == "unhealthy"

    tools.run("stop_service", project_id="manifest-id", service_name="backend")



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
            f"    start: ['{sys.executable}', '-u', 'service.py']",
            "    health:",
            "      type: http",
            "      url: https://example.com/health",
            "      expect_status: 200",
        ]
    )
    (project_root / "service.py").write_text(
        "import time\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    _write_policy(
        project_root,
        [
            "command_policy:",
            "  commands:",
            f"    {Path(sys.executable).name}: {{}}",
            "network:",
            "  allowed_hosts: ['example.com']",
        ],
    )
    tools = _build_tools(workspace_root)

    def _fake_request(method: str, url: str, headers, content, timeout):
        request = httpx.Request(method, url)
        return httpx.Response(200, request=request, text="ok")

    monkeypatch.setattr(httpx, "request", _fake_request)

    started = tools.run("start_service", project_id="manifest-id", service_name="backend")
    assert started["ok"] is True

    result = tools.run("service_status", project_id="manifest-id", service_name="backend")

    assert result["ok"] is True
    assert result["data"]["service"]["runtime"]["health"]["status"] == "healthy"

    tools.run("stop_service", project_id="manifest-id", service_name="backend")

def test_service_log_store_trims_old_lines_and_keeps_offsets_honest() -> None:
    store = ServiceLogStore(max_bytes=25)

    for idx in range(6):
        store.append("manifest-id:backend", "stdout", f"line-{idx}")

    first_page = store.slice("manifest-id:backend", offset=0, limit=2)
    assert [line.message for line in first_page.lines] == ["line-3", "line-4"]
    assert [line.line_number for line in first_page.lines] == [3, 4]
    assert first_page.next_offset == 5
    assert first_page.truncated is True

    second_page = store.slice("manifest-id:backend", offset=first_page.next_offset or 0, limit=2)
    assert [line.message for line in second_page.lines] == ["line-5"]
    assert [line.line_number for line in second_page.lines] == [5]
    assert second_page.next_offset is None
    assert second_page.truncated is False


def test_service_log_store_keeps_truncated_long_line_in_buffer() -> None:
    store = ServiceLogStore(max_bytes=6)

    store.append("manifest-id:backend", "stdout", "abcdef")

    page = store.slice("manifest-id:backend", offset=0, limit=10)
    assert [line.message for line in page.lines] == ["abcde"]
    assert [line.line_number for line in page.lines] == [0]
    assert page.next_offset is None
    assert page.truncated is False


def test_service_log_store_keeps_stream_fragments_separate() -> None:
    store = ServiceLogStore(max_bytes=40)

    store.set_open_fragment("manifest-id:backend", "stdout", "out")
    store.set_open_fragment("manifest-id:backend", "stderr", "err")
    store.close_open_fragment("manifest-id:backend", "stdout", "out-done")
    store.close_open_fragment("manifest-id:backend", "stderr", "err-done")

    page = store.slice("manifest-id:backend", offset=0, limit=10)
    assert [(line.stream, line.message) for line in page.lines] == [
        ("stdout", "out-done"),
        ("stderr", "err-done"),
    ]



def test_service_log_capture_flushes_partial_output_without_newline(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project(
        services_block=[
            "services:",
            "  backend:",
            "    cwd: .",
            f"    start: ['{sys.executable}', '-u', 'service.py']",
        ]
    )
    (project_root / "service.py").write_text(
        "import sys, time\n"
        "sys.stdout.write('partial-without-newline')\n"
        "sys.stdout.flush()\n"
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
    tools = _build_tools(workspace_root, max_log_bytes=80, subprocess_stream_chunk_bytes=8)

    started = tools.run("start_service", project_id="manifest-id", service_name="backend")
    assert started["ok"] is True

    deadline = time.monotonic() + 3
    logs = tools.run("get_logs", project_id="manifest-id", service_name="backend", limit=20)
    while (
        not logs["data"]["lines"]
        and time.monotonic() < deadline
    ):
        time.sleep(0.05)
        logs = tools.run("get_logs", project_id="manifest-id", service_name="backend", limit=20)

    assert logs["ok"] is True
    assert any(line["message"] == "partial-without-newline" for line in logs["data"]["lines"])

    tools.run("stop_service", project_id="manifest-id", service_name="backend")


def test_service_status_clears_service_instance_id_after_natural_exit(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project(
        services_block=[
            "services:",
            "  backend:",
            "    cwd: .",
            f"    start: ['{sys.executable}', '-u', 'service.py']",
        ]
    )
    (project_root / "service.py").write_text(
        "print('done', flush=True)\n",
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

    started = tools.run("start_service", project_id="manifest-id", service_name="backend")
    assert started["ok"] is True
    assert started["data"]["service"]["runtime"]["service_instance_id"] is not None

    deadline = time.monotonic() + 3
    status = tools.run("service_status", project_id="manifest-id", service_name="backend")
    while (
        status["data"]["service"]["runtime"]["status"] == "running"
        and time.monotonic() < deadline
    ):
        time.sleep(0.05)
        status = tools.run("service_status", project_id="manifest-id", service_name="backend")

    assert status["ok"] is True
    assert status["data"]["service"]["runtime"]["status"] == "stopped"
    assert status["data"]["service"]["runtime"]["service_instance_id"] is None


def test_service_log_retention_trims_chatty_service_output(
    workspace_root,
    make_manifest_project,
) -> None:
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
        "for idx in range(20):\n"
        "    print(f'line-{idx:02d}', flush=True)\n"
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
    tools = _build_tools(workspace_root, max_log_bytes=80)

    started = tools.run("start_service", project_id="manifest-id", service_name="backend")
    assert started["ok"] is True

    deadline = time.monotonic() + 3
    logs = tools.run("get_logs", project_id="manifest-id", service_name="backend", limit=20)
    while (
        (not logs["data"]["lines"] or logs["data"]["lines"][-1]["message"] != "line-19")
        and time.monotonic() < deadline
    ):
        time.sleep(0.05)
        logs = tools.run("get_logs", project_id="manifest-id", service_name="backend", limit=20)

    assert logs["ok"] is True
    messages = [line["message"] for line in logs["data"]["lines"]]
    assert "line-00" not in messages
    assert "line-19" in messages
    assert logs["data"]["lines"][0]["line_number"] > 0

    first_page = tools.run(
        "get_logs",
        project_id="manifest-id",
        service_name="backend",
        offset=0,
        limit=3,
    )
    assert first_page["ok"] is True
    next_offset = first_page["data"]["next_offset"]
    assert next_offset is not None

    second_page = tools.run(
        "get_logs",
        project_id="manifest-id",
        service_name="backend",
        offset=next_offset,
        limit=3,
    )
    assert second_page["ok"] is True
    assert (
        second_page["data"]["lines"][0]["line_number"]
        == first_page["data"]["lines"][-1]["line_number"] + 1
    )

    tools.run("stop_service", project_id="manifest-id", service_name="backend")
