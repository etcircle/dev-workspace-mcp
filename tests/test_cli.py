from __future__ import annotations

import json
import socket
import subprocess
import threading
from copy import deepcopy
from pathlib import Path

import pytest

from dev_workspace_mcp.cli import main as cli_module
from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.tool_registry import build_tool_registry
from dev_workspace_mcp.projects.registry import ProjectRegistry

_VALID_CONNECTION_PROFILE = {
    "kind": "postgres",
    "transport": "direct",
    "host_env": "PGHOST",
    "port_env": "PGPORT",
    "database_env": "PGDATABASE",
    "user_env": "PGUSER",
    "password_env": "PGPASSWORD",
}


def _build_tools(workspace_root: Path):
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    return build_tool_registry(registry)


def _invoke_cli(
    monkeypatch,
    capsys,
    workspace_root: Path,
    argv: list[str],
) -> tuple[int, dict[str, object]]:
    settings = Settings(workspace_roots=[str(workspace_root)])
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    exit_code = cli_module.main(argv)
    output = capsys.readouterr().out
    return exit_code, json.loads(output)


def _init_git_history(project_root: Path) -> None:
    subprocess.run(
        ["git", "-C", str(project_root), "init"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(project_root), "config", "user.name", "Test User"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(project_root), "config", "user.email", "test@example.com"],
        check=True,
    )
    (project_root / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project_root), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(project_root), "commit", "-m", "initial"], check=True)


def _normalize_job_payload(payload: dict[str, object]) -> dict[str, object]:
    normalized = deepcopy(payload)
    job = normalized["data"]["job"]
    job["job_id"] = "JOB_ID"
    job["timing"] = {"started_at": None, "finished_at": None, "duration_ms": None}
    return normalized


def _normalize_bootstrap_payload(payload: dict[str, object]) -> dict[str, object]:
    normalized = deepcopy(payload)
    normalized["data"]["root_path"] = "ROOT_PATH"
    normalized["data"]["manifest_path"] = "MANIFEST_PATH"
    return normalized


@pytest.fixture
def tcp_server() -> tuple[str, int]:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen()
    server.settimeout(0.2)
    stop_event = threading.Event()

    def _serve() -> None:
        while not stop_event.is_set():
            try:
                client, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            with client:
                pass

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()

    host, port = server.getsockname()
    yield host, port

    stop_event.set()
    server.close()
    thread.join(timeout=1)


def test_cli_projects_json_matches_tool_registry(
    monkeypatch,
    capsys,
    workspace_root,
    make_manifest_project,
) -> None:
    make_manifest_project()
    tools = _build_tools(workspace_root)

    exit_code, payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        ["--json", "projects", "--include-paths"],
    )

    assert exit_code == 0
    assert payload == tools.run("list_projects", include_paths=True)


def _normalize_snapshot_payload(payload: dict[str, object]) -> dict[str, object]:
    normalized = deepcopy(payload)
    normalized["data"]["watcher"]["indexed_at"] = None
    return normalized


def test_cli_snapshot_and_read_json_match_tool_registry(
    monkeypatch,
    capsys,
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    (project_root / "src").mkdir()
    (project_root / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    tools = _build_tools(workspace_root)

    snapshot_exit_code, snapshot_payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        ["--json", "snapshot", "manifest-id"],
    )
    read_exit_code, read_payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        ["--json", "read", "manifest-id", "src/app.py"],
    )

    assert snapshot_exit_code == 0
    assert _normalize_snapshot_payload(snapshot_payload) == _normalize_snapshot_payload(
        tools.run("project_snapshot", project_id="manifest-id")
    )
    assert read_exit_code == 0
    assert read_payload == tools.run("read_file", project_id="manifest-id", path="src/app.py")


def test_cli_run_json_matches_tool_registry_after_normalizing_job_metadata(
    monkeypatch,
    capsys,
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    (project_root / ".devworkspace").mkdir()
    (project_root / ".devworkspace" / "policy.yaml").write_text(
        "command_policy:\n  default: allow\n",
        encoding="utf-8",
    )

    exit_code, payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        ["--json", "run", "manifest-id", "python3", "-c", "print('wave3')"],
    )
    expected = _build_tools(workspace_root).run(
        "run_command",
        project_id="manifest-id",
        argv=["python3", "-c", "print('wave3')"],
    )

    assert exit_code == 0
    assert _normalize_job_payload(payload) == _normalize_job_payload(expected)
    assert payload["data"]["job"]["output"] == [{"stream": "stdout", "text": "wave3\n"}]


def test_cli_run_parses_flags_after_project_id(
    monkeypatch,
    capsys,
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    (project_root / ".devworkspace").mkdir()
    (project_root / ".devworkspace" / "policy.yaml").write_text(
        "command_policy:\n  default: allow\n",
        encoding="utf-8",
    )

    exit_code, payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        [
            "--json",
            "run",
            "manifest-id",
            "--timeout-sec",
            "5",
            "python3",
            "-c",
            "print('wave3')",
        ],
    )
    expected = _build_tools(workspace_root).run(
        "run_command",
        project_id="manifest-id",
        argv=["python3", "-c", "print('wave3')"],
        timeout_sec=5,
    )

    assert exit_code == 0
    assert _normalize_job_payload(payload) == _normalize_job_payload(expected)


def test_cli_run_preserves_command_args_that_look_like_cli_flags(
    monkeypatch,
    capsys,
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    (project_root / ".devworkspace").mkdir()
    (project_root / ".devworkspace" / "policy.yaml").write_text(
        "command_policy:\n  default: allow\n",
        encoding="utf-8",
    )

    exit_code, payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        [
            "--json",
            "run",
            "manifest-id",
            "python3",
            "-c",
            "import json, sys; print(json.dumps(sys.argv[1:]))",
            "--timeout-sec",
            "5",
        ],
    )

    assert exit_code == 0
    assert payload["data"]["job"]["output"] == [
        {"stream": "stdout", "text": '["--timeout-sec", "5"]\n'}
    ]


def test_cli_git_status_json_matches_tool_registry(
    monkeypatch,
    capsys,
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project(project_id="git-project")
    _init_git_history(project_root)
    (project_root / "README.md").write_text("hello\nchanged\n", encoding="utf-8")
    (project_root / "notes.txt").write_text("draft\n", encoding="utf-8")
    tools = _build_tools(workspace_root)

    exit_code, payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        ["--json", "git", "status", "git-project"],
    )

    assert exit_code == 0
    assert payload == tools.run("git_status", project_id="git-project", include_untracked=True)


def test_cli_memory_patch_and_read_use_state_doc_tools(
    monkeypatch,
    capsys,
    workspace_root,
    make_manifest_project,
) -> None:
    make_manifest_project()
    tools = _build_tools(workspace_root)

    patch_exit_code, patch_payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        [
            "--json",
            "memory",
            "patch",
            "manifest-id",
            "--section",
            "Current Truth",
            "Beta",
            "--section",
            "Next Step",
            "Ship it",
        ],
    )
    read_exit_code, read_payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        ["--json", "memory", "read", "manifest-id"],
    )

    assert patch_exit_code == 0
    assert patch_payload["ok"] is True
    assert patch_payload["data"]["updated_headings"] == ["Current Truth", "Next Step"]
    assert read_exit_code == 0
    assert read_payload == tools.run("read_state_doc", project_id="manifest-id", kind="memory")


def test_cli_bootstrap_json_matches_tool_registry(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    tool_workspace_root = tmp_path / "tool-workspace"
    tool_workspace_root.mkdir()
    cli_workspace_root = tmp_path / "cli-workspace"
    cli_workspace_root.mkdir()

    expected = _build_tools(tool_workspace_root).run(
        "bootstrap_project",
        mode="create",
        folder_name="demo-project",
        project_id="demo-id",
        display_name="Demo Project",
        git_init=True,
    )
    exit_code, payload = _invoke_cli(
        monkeypatch,
        capsys,
        cli_workspace_root,
        [
            "--json",
            "bootstrap",
            "create",
            "demo-project",
            "--project-id",
            "demo-id",
            "--display-name",
            "Demo Project",
            "--git-init",
        ],
    )

    assert exit_code == 0
    assert _normalize_bootstrap_payload(payload) == _normalize_bootstrap_payload(expected)
    assert (cli_workspace_root / "demo-project" / ".git").exists()


def test_cli_bootstrap_clone_and_import_json_match_tool_registry(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    source_repo = tmp_path / "source-repo"
    source_repo.mkdir()
    subprocess.run(["git", "init", str(source_repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(source_repo), "config", "user.name", "Test User"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    (source_repo / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(source_repo), "add", "README.md"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )

    tool_clone_root = tmp_path / "tool-clone-workspace"
    tool_clone_root.mkdir()
    cli_clone_root = tmp_path / "cli-clone-workspace"
    cli_clone_root.mkdir()

    expected_clone = _build_tools(tool_clone_root).run(
        "bootstrap_project",
        mode="clone",
        repo_url=str(source_repo),
        display_name="Cloned Project",
    )
    clone_exit_code, clone_payload = _invoke_cli(
        monkeypatch,
        capsys,
        cli_clone_root,
        [
            "--json",
            "bootstrap",
            "clone",
            str(source_repo),
            "--display-name",
            "Cloned Project",
        ],
    )

    assert clone_exit_code == 0
    assert _normalize_bootstrap_payload(
        clone_payload
    ) == _normalize_bootstrap_payload(expected_clone)

    tool_import_root = tmp_path / "tool-import-workspace"
    tool_import_root.mkdir()
    cli_import_root = tmp_path / "cli-import-workspace"
    cli_import_root.mkdir()
    (tool_import_root / "import-me").mkdir()
    (cli_import_root / "import-me").mkdir()

    expected_import = _build_tools(tool_import_root).run(
        "bootstrap_project",
        mode="import",
        path=str(tool_import_root / "import-me"),
        display_name="Imported Project",
    )
    import_exit_code, import_payload = _invoke_cli(
        monkeypatch,
        capsys,
        cli_import_root,
        [
            "--json",
            "bootstrap",
            "import",
            str(cli_import_root / "import-me"),
            "--display-name",
            "Imported Project",
        ],
    )

    assert import_exit_code == 0
    assert _normalize_bootstrap_payload(
        import_payload
    ) == _normalize_bootstrap_payload(expected_import)


def test_cli_connections_json_matches_tool_registry(
    monkeypatch,
    capsys,
    workspace_root,
    make_manifest_project,
    tcp_server: tuple[str, int],
) -> None:
    host, port = tcp_server
    make_manifest_project(name="demo-project", project_id="demo-id")
    tools = _build_tools(workspace_root)

    expected_configure = tools.run(
        "configure_connection",
        project_id="demo-id",
        connection_name="primary",
        profile=_VALID_CONNECTION_PROFILE,
        env_updates={"PGHOST": host, "PGPORT": str(port)},
    )
    configure_exit_code, configure_payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        [
            "--json",
            "connections",
            "configure",
            "demo-id",
            "primary",
            "--kind",
            "postgres",
            "--host-env",
            "PGHOST",
            "--port-env",
            "PGPORT",
            "--database-env",
            "PGDATABASE",
            "--user-env",
            "PGUSER",
            "--password-env",
            "PGPASSWORD",
            "--env",
            f"PGHOST={host}",
            "--env",
            f"PGPORT={port}",
        ],
    )
    list_exit_code, list_payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        ["--json", "connections", "list", "demo-id"],
    )
    expected_test = tools.run(
        "test_connection",
        project_id="demo-id",
        connection_name="primary",
    )
    test_exit_code, test_payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        ["--json", "connections", "test", "demo-id", "primary"],
    )

    assert configure_exit_code == 0
    assert configure_payload == expected_configure
    assert list_exit_code == 0
    assert list_payload == tools.run("list_connections", project_id="demo-id")
    assert test_exit_code == 0
    assert test_payload == expected_test


def test_cli_bootstrap_flow_becomes_discoverable_via_projects(
    monkeypatch,
    capsys,
    workspace_root,
) -> None:
    bootstrap_exit_code, bootstrap_payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        [
            "--json",
            "bootstrap",
            "create",
            "discoverable-project",
            "--display-name",
            "Discoverable Project",
        ],
    )
    projects_exit_code, projects_payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        ["--json", "projects", "--include-paths"],
    )

    assert bootstrap_exit_code == 0
    assert bootstrap_payload["data"]["project_id"] == "discoverable-project"
    assert projects_exit_code == 0
    assert projects_payload == _build_tools(workspace_root).run("list_projects", include_paths=True)

    project = projects_payload["data"]["projects"][0]
    assert project["project_id"] == "discoverable-project"
    assert project["display_name"] == "Discoverable Project"
    assert project["root_path"] == str((workspace_root / "discoverable-project").resolve())
    assert project["manifest_present"] is True


def test_cli_json_flag_pretty_prints_output(
    monkeypatch,
    capsys,
    workspace_root,
    make_manifest_project,
) -> None:
    make_manifest_project()
    settings = Settings(workspace_roots=[str(workspace_root)])
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)

    compact_exit_code = cli_module.main(["projects"])
    compact_output = capsys.readouterr().out
    pretty_exit_code = cli_module.main(["--json", "projects"])
    pretty_output = capsys.readouterr().out

    assert compact_exit_code == 0
    assert pretty_exit_code == 0
    assert compact_output.count("\n") == 1
    assert pretty_output.startswith("{\n")
    assert json.loads(compact_output) == json.loads(pretty_output)
