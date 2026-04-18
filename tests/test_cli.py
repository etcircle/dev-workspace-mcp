from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from pathlib import Path

from dev_workspace_mcp.cli import main as cli_module
from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.tool_registry import build_tool_registry
from dev_workspace_mcp.projects.registry import ProjectRegistry


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
