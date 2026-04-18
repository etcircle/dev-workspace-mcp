from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.tool_registry import build_tool_registry
from dev_workspace_mcp.projects.registry import ProjectRegistry


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = json.dumps({"ok": True, "path": self.path}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A003
        return


def _build_tools(workspace_root: Path):
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    return build_tool_registry(registry)


def _write_policy(project_root: Path, lines: list[str]) -> None:
    policy_dir = project_root / ".devworkspace"
    policy_dir.mkdir(exist_ok=True)
    (policy_dir / "policy.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_http_request_calls_local_endpoint_and_parses_json(
    workspace_root,
    make_manifest_project,
) -> None:
    make_manifest_project()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    tools = _build_tools(workspace_root)

    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/health"
        result = tools.run("http_request", project_id="manifest-id", method="GET", url=url)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result["ok"] is True
    response = result["data"]
    assert response["status_code"] == 200
    assert response["json_body"] == {"ok": True, "path": "/health"}
    assert response["text_body"] == '{"ok": true, "path": "/health"}'


def test_http_request_rejects_non_local_destinations(workspace_root, make_manifest_project) -> None:
    make_manifest_project()
    tools = _build_tools(workspace_root)

    result = tools.run(
        "http_request",
        project_id="manifest-id",
        method="GET",
        url="https://example.com/health",
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "NETWORK_DENIED"


def test_http_request_allows_policy_approved_host(
    workspace_root,
    make_manifest_project,
    monkeypatch,
) -> None:
    project_root = make_manifest_project()
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
        return httpx.Response(
            200,
            request=request,
            json={"ok": True, "url": url},
            headers={"Content-Type": "application/json"},
        )

    monkeypatch.setattr(httpx, "request", _fake_request)

    result = tools.run(
        "http_request",
        project_id="manifest-id",
        method="GET",
        url="https://example.com/health",
    )

    assert result["ok"] is True
    assert result["data"]["json_body"] == {"ok": True, "url": "https://example.com/health"}


def test_list_probes_and_run_probe(workspace_root, make_manifest_project) -> None:
    project_root = make_manifest_project(
        services_block=[
            "probes:",
            "  echo_probe:",
            "    cwd: .",
            "    argv: ['echo', 'probe-ok']",
            "    timeout_sec: 5",
        ]
    )
    _write_policy(
        project_root,
        [
            "command_policy:",
            "  commands:",
            "    echo: {}",
        ],
    )
    tools = _build_tools(workspace_root)

    listed = tools.run("list_probes", project_id="manifest-id")
    assert listed["ok"] is True
    assert listed["data"]["probes"] == [
        {
            "name": "echo_probe",
            "cwd": ".",
            "argv": ["echo", "probe-ok"],
            "timeout_sec": 5,
        }
    ]

    run_result = tools.run("run_probe", project_id="manifest-id", probe_name="echo_probe")
    assert run_result["ok"] is True
    probe = run_result["data"]
    assert probe["probe_name"] == "echo_probe"
    assert probe["ok"] is True
    assert probe["exit_code"] == 0
    assert probe["stdout"] == "probe-ok\n"


def test_run_probe_denies_cwd_symlink_escape(workspace_root, make_manifest_project) -> None:
    project_root = make_manifest_project(
        services_block=[
            "probes:",
            "  echo_probe:",
            "    cwd: linked",
            "    argv: ['echo', 'probe-ok']",
            "    timeout_sec: 5",
        ]
    )
    outside_dir = workspace_root / "outside-probe-cwd"
    outside_dir.mkdir()
    (project_root / "linked").symlink_to(outside_dir, target_is_directory=True)
    _write_policy(
        project_root,
        [
            "command_policy:",
            "  commands:",
            "    echo: {}",
        ],
    )
    tools = _build_tools(workspace_root)

    result = tools.run("run_probe", project_id="manifest-id", probe_name="echo_probe")

    assert result["ok"] is False
    assert result["error"]["code"] == "PATH_OUTSIDE_PROJECT"


def test_run_probe_denies_argv_combinations_blocked_by_project_policy(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project(
        services_block=[
            "probes:",
            "  echo_probe:",
            "    cwd: .",
            "    argv: ['echo', 'blocked']",
            "    timeout_sec: 5",
        ]
    )
    _write_policy(
        project_root,
        [
            "command_policy:",
            "  commands:",
            "    echo:",
            "      deny_args:",
            "        - ['blocked']",
        ],
    )
    tools = _build_tools(workspace_root)

    result = tools.run("run_probe", project_id="manifest-id", probe_name="echo_probe")

    assert result["ok"] is False
    assert result["error"]["code"] == "POLICY_DENIED"
