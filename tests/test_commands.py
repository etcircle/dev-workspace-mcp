from __future__ import annotations

import shlex
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


def _write_policy(project_root: Path, lines: list[str]) -> None:
    policy_dir = project_root / ".devworkspace"
    policy_dir.mkdir(exist_ok=True)
    (policy_dir / "policy.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _make_allowed_python(project_root: Path) -> str:
    wrapper = project_root / "bin" / "python3"
    wrapper.parent.mkdir(exist_ok=True)
    wrapper.write_text(
        f"#!/bin/sh\nexec {shlex.quote(sys.executable)} \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return str(wrapper)


def _stdout_text(job: dict[str, object]) -> str:
    output = job.get("output", [])
    return "".join(
        chunk["text"]
        for chunk in output
        if isinstance(chunk, dict) and chunk.get("stream") == "stdout"
    )


def test_run_command_foreground_success_and_get_job_returns_completed_record(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    app_dir = project_root / "app"
    app_dir.mkdir()
    (app_dir / "marker.txt").write_text("hello from app\n", encoding="utf-8")
    python_cmd = _make_allowed_python(project_root)
    _write_policy(
        project_root,
        [
            "command_policy:",
            "  commands:",
            f"    {Path(python_cmd).name}: {{}}",
        ],
    )
    tools = _build_tools(workspace_root)

    result = tools.run(
        "run_command",
        project_id="manifest-id",
        argv=[
            python_cmd,
            "-c",
            (
                "from pathlib import Path; "
                "print(Path.cwd().name); "
                "print(Path('marker.txt').read_text().strip())"
            ),
        ],
        cwd="app",
    )

    assert result["ok"] is True
    job = result["data"]["job"]
    assert job["status"] == "succeeded"
    assert job["background"] is False
    assert job["cwd"] == str(app_dir.resolve())
    assert Path(job["argv"][0]).name == "python3"
    assert "app\nhello from app\n" in _stdout_text(job)
    assert job["timing"]["finished_at"] is not None

    get_result = tools.run("get_job", project_id="manifest-id", job_id=job["job_id"])

    assert get_result["ok"] is True
    assert get_result["data"]["job"] == job


def test_run_command_rejects_blocked_command(workspace_root, make_manifest_project) -> None:
    make_manifest_project()
    tools = _build_tools(workspace_root)

    result = tools.run(
        "run_command",
        project_id="manifest-id",
        argv=["/bin/sh", "-c", "echo blocked"],
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "POLICY_DENIED"


def test_run_command_executes_manifest_preset(workspace_root, make_manifest_project) -> None:
    project_root = make_manifest_project(
        services_block=[
            "presets:",
            "  say_hi: ['echo', 'preset-ok']",
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

    result = tools.run("run_command", project_id="manifest-id", preset="say_hi")

    assert result["ok"] is True
    job = result["data"]["job"]
    assert job["status"] == "succeeded"
    assert job["argv"] == ["echo", "preset-ok"]
    assert _stdout_text(job) == "preset-ok\n"


def test_run_command_returns_validation_error_for_unknown_preset(
    workspace_root,
    make_manifest_project,
) -> None:
    make_manifest_project()
    tools = _build_tools(workspace_root)

    result = tools.run("run_command", project_id="manifest-id", preset="missing")

    assert result["ok"] is False
    assert result["error"]["code"] == "VALIDATION_ERROR"
    assert result["error"]["message"] == "Unknown preset: missing"
    assert result["error"]["hint"] == "Use one of the presets exposed by project_snapshot."


def test_background_job_can_be_cancelled_and_get_job_reflects_cancellation(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    python_cmd = _make_allowed_python(project_root)
    _write_policy(
        project_root,
        [
            "command_policy:",
            "  commands:",
            f"    {Path(python_cmd).name}: {{}}",
        ],
    )
    tools = _build_tools(workspace_root)

    run_result = tools.run(
        "run_command",
        project_id="manifest-id",
        argv=[
            python_cmd,
            "-c",
            "import time; print('started', flush=True); time.sleep(30)",
        ],
        background=True,
    )

    assert run_result["ok"] is True
    running_job = run_result["data"]["job"]
    assert running_job["status"] == "running"
    assert running_job["background"] is True
    assert running_job["pid"] is not None

    cancel_result = tools.run(
        "cancel_job",
        project_id="manifest-id",
        job_id=running_job["job_id"],
    )

    assert cancel_result["ok"] is True
    cancelled_job = cancel_result["data"]["job"]
    assert cancelled_job["status"] == "cancelled"
    assert cancelled_job["timing"]["finished_at"] is not None

    fetched = tools.run("get_job", project_id="manifest-id", job_id=running_job["job_id"])
    deadline = time.monotonic() + 3
    while fetched["data"]["job"]["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.05)
        fetched = tools.run("get_job", project_id="manifest-id", job_id=running_job["job_id"])

    assert fetched["ok"] is True
    assert fetched["data"]["job"]["status"] == "cancelled"
    assert fetched["data"]["job"]["exit_code"] is not None


def test_run_command_denies_cwd_symlink_escape(workspace_root, make_manifest_project) -> None:
    project_root = make_manifest_project()
    outside_dir = workspace_root / "outside-command-cwd"
    outside_dir.mkdir()
    (project_root / "linked").symlink_to(outside_dir, target_is_directory=True)
    python_cmd = _make_allowed_python(project_root)
    _write_policy(
        project_root,
        [
            "command_policy:",
            "  commands:",
            f"    {Path(python_cmd).name}: {{}}",
        ],
    )
    tools = _build_tools(workspace_root)

    result = tools.run(
        "run_command",
        project_id="manifest-id",
        argv=[python_cmd, "-c", "print('nope')"],
        cwd="linked",
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "PATH_OUTSIDE_PROJECT"


def test_run_command_does_not_inherit_secret_env_vars_but_keeps_allowed_ones(
    workspace_root,
    make_manifest_project,
    monkeypatch,
) -> None:
    project_root = make_manifest_project()
    python_cmd = _make_allowed_python(project_root)
    _write_policy(
        project_root,
        [
            "env:",
            "  allow: ['PATH', 'HOME', 'LANG', 'LC_ALL', 'APP_MODE']",
            "command_policy:",
            "  commands:",
            f"    {Path(python_cmd).name}: {{}}",
        ],
    )
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "top-secret")
    monkeypatch.setenv("APP_MODE", "dev")
    tools = _build_tools(workspace_root)

    result = tools.run(
        "run_command",
        project_id="manifest-id",
        argv=[
            python_cmd,
            "-c",
            (
                "import os; "
                "print(os.getenv('AWS_SECRET_ACCESS_KEY')); "
                "print(os.getenv('APP_MODE'))"
            ),
        ],
    )

    assert result["ok"] is True
    assert _stdout_text(result["data"]["job"]) == "None\ndev\n"



def test_run_command_filters_explicit_env_overrides_through_policy(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    python_cmd = _make_allowed_python(project_root)
    _write_policy(
        project_root,
        [
            "env:",
            "  allow: ['PATH', 'HOME', 'LANG', 'LC_ALL', 'APP_MODE']",
            "command_policy:",
            "  commands:",
            f"    {Path(python_cmd).name}: {{}}",
        ],
    )
    tools = _build_tools(workspace_root)

    result = tools.run(
        "run_command",
        project_id="manifest-id",
        argv=[
            python_cmd,
            "-c",
            (
                "import os; "
                "print(os.getenv('FOO')); "
                "print(os.getenv('LD_PRELOAD')); "
                "print(os.getenv('APP_MODE'))"
            ),
        ],
        env={"FOO": "bar", "LD_PRELOAD": "/tmp/x.so", "APP_MODE": "prod"},
    )

    assert result["ok"] is True
    assert _stdout_text(result["data"]["job"]) == "None\nNone\nprod\n"


def test_run_command_denies_argv_combinations_blocked_by_project_policy(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
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

    result = tools.run("run_command", project_id="manifest-id", argv=["echo", "blocked"])

    assert result["ok"] is False
    assert result["error"]["code"] == "POLICY_DENIED"
