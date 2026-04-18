from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

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
    assert result["error"]["code"] == "VALIDATION_ERROR"


def test_list_probes_and_run_probe(workspace_root, make_manifest_project) -> None:
    make_manifest_project(
        services_block=[
            "probes:",
            "  echo_probe:",
            "    cwd: .",
            "    argv: ['echo', 'probe-ok']",
            "    timeout_sec: 5",
        ]
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
