from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    return root


@pytest.fixture
def make_git_project(workspace_root: Path):
    def _make(name: str = "git-project", *, real_git: bool = False) -> Path:
        project_root = workspace_root / name
        project_root.mkdir()
        if real_git:
            subprocess.run(
                ["git", "-C", str(project_root), "init"],
                check=True,
                capture_output=True,
            )
            (project_root / "README.md").write_text("hello\n", encoding="utf-8")
        else:
            (project_root / ".git").mkdir()
        return project_root

    return _make


@pytest.fixture
def make_manifest_project(workspace_root: Path):
    def _make(
        name: str = "manifest-project",
        *,
        project_id: str = "manifest-id",
        display_name: str = "Manifest Project",
        alias: str | None = None,
        services_block: list[str] | None = None,
    ) -> Path:
        project_root = workspace_root / name
        project_root.mkdir()
        alias = alias or f"{project_id}-alias"
        lines = [
            f"name: {display_name}",
            f"project_id: {project_id}",
            "aliases:",
            f"  - {alias}",
            "codegraph:",
            "  watch_paths:",
            "    - src",
        ]
        if services_block:
            lines.extend(services_block)
        (project_root / ".devworkspace.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return project_root

    return _make
