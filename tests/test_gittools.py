from __future__ import annotations

import subprocess
from pathlib import Path

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.tool_registry import build_tool_registry
from dev_workspace_mcp.projects.registry import ProjectRegistry


def _build_tools(workspace_root: Path):
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    return build_tool_registry(registry)


def _init_git_history(project_root: Path) -> str:
    subprocess.run(
        ["git", "-C", str(project_root), "config", "user.name", "Test User"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(project_root), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(["git", "-C", str(project_root), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(project_root), "commit", "-m", "initial"], check=True)
    head = subprocess.run(
        ["git", "-C", str(project_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return head.stdout.strip()


def test_git_status_reports_branch_and_file_changes(workspace_root, make_git_project) -> None:
    project_root = make_git_project(real_git=True)
    _init_git_history(project_root)
    (project_root / "README.md").write_text("hello\nchanged\n", encoding="utf-8")
    (project_root / "staged.txt").write_text("staged\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project_root), "add", "staged.txt"], check=True)
    (project_root / "notes.txt").write_text("draft\n", encoding="utf-8")

    tools = _build_tools(workspace_root)
    result = tools.run("git_status", project_id="git-project")

    assert result["ok"] is True
    status = result["data"]
    assert status["branch"]
    assert status["clean"] is False
    changes = {item["path"]: item for item in status["changes"]}
    assert changes["README.md"]["change_type"] == "modified"
    assert changes["staged.txt"]["change_type"] == "added"
    assert changes["notes.txt"]["change_type"] == "untracked"


def test_git_diff_returns_patch_for_project_relative_path(workspace_root, make_git_project) -> None:
    project_root = make_git_project(real_git=True)
    _init_git_history(project_root)
    (project_root / "README.md").write_text("hello\nchanged\n", encoding="utf-8")

    tools = _build_tools(workspace_root)
    result = tools.run("git_diff", project_id="git-project", path="README.md")

    assert result["ok"] is True
    diff = result["data"]["diff"]
    assert "diff --git a/README.md b/README.md" in diff
    assert "+changed" in diff


def test_git_checkout_can_create_branch_and_report_head(workspace_root, make_git_project) -> None:
    project_root = make_git_project(real_git=True)
    initial_head = _init_git_history(project_root)

    tools = _build_tools(workspace_root)
    result = tools.run(
        "git_checkout",
        project_id="git-project",
        ref="feature/demo",
        create=True,
    )

    assert result["ok"] is True
    checkout = result["data"]
    assert checkout["branch"] == "feature/demo"
    assert checkout["detached"] is False
    assert checkout["head_sha"] == initial_head


def test_git_commit_stages_relative_paths_and_returns_commit_metadata(
    workspace_root,
    make_git_project,
) -> None:
    project_root = make_git_project(real_git=True)
    _init_git_history(project_root)
    (project_root / "src").mkdir()
    (project_root / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")

    tools = _build_tools(workspace_root)
    result = tools.run(
        "git_commit",
        project_id="git-project",
        message="Add app",
        paths=["src/app.py"],
    )

    assert result["ok"] is True
    commit = result["data"]
    assert len(commit["commit_sha"]) == 40
    assert commit["changed_paths"] == ["src/app.py"]
    assert "Add app" in (commit["summary"] or "")

    status = tools.run("git_status", project_id="git-project")
    assert status["ok"] is True
    assert status["data"]["clean"] is True
