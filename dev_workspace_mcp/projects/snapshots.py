from __future__ import annotations

import subprocess
from pathlib import Path

from dev_workspace_mcp.models.common import WarningMessage
from dev_workspace_mcp.models.projects import (
    GitSummary,
    ProjectSnapshot,
    ServiceSummary,
    StateDocSummary,
    WatcherSummary,
)
from dev_workspace_mcp.projects.registry import ProjectRegistry

_STATE_DOC_PATHS = {
    "agents": "AGENTS.md",
    "memory": ".devworkspace/memory.md",
    "roadmap": ".devworkspace/roadmap.md",
    "tasks": ".devworkspace/tasks.md",
}

def build_project_snapshot(
    registry: ProjectRegistry,
    project_id: str,
) -> tuple[ProjectSnapshot, list[WarningMessage]]:
    record = registry.require(project_id)
    warnings: list[WarningMessage] = []
    project_root = Path(record.root_path)

    if not record.manifest_path:
        warnings.append(
            WarningMessage(
                code="MANIFEST_MISSING",
                message="Project discovered without .devworkspace.yaml; using derived defaults.",
            )
        )

    git_summary = _build_git_summary(project_root, warnings)
    state_docs = _collect_state_docs(project_root, warnings)
    services = [
        ServiceSummary(
            name=name,
            cwd=definition.cwd,
            ports=definition.ports,
            has_health_check=definition.health is not None,
        )
        for name, definition in sorted(record.manifest.services.items())
    ]
    watcher = WatcherSummary(
        configured=bool(record.manifest.codegraph.watch_paths),
        active=False,
        watched_paths=record.manifest.codegraph.watch_paths,
        status="configured" if record.manifest.codegraph.watch_paths else "not_configured",
    )

    snapshot = ProjectSnapshot(
        project=record,
        git=git_summary,
        services=services,
        watcher=watcher,
        recent_changed_files=git_summary.changed_paths[:10],
        probes=sorted(record.manifest.probes.keys()),
        presets=sorted(record.manifest.presets.keys()),
        state_docs=state_docs,
    )
    return snapshot, warnings



def _collect_state_docs(
    project_root: Path,
    warnings: list[WarningMessage],
) -> list[StateDocSummary]:
    summaries: list[StateDocSummary] = []
    for kind, relative_path in _STATE_DOC_PATHS.items():
        path = project_root / relative_path
        exists = path.exists()
        char_count = len(path.read_text(encoding="utf-8")) if exists else 0
        summaries.append(
            StateDocSummary(
                kind=kind,
                path=relative_path,
                exists=exists,
                char_count=char_count,
            )
        )
        if kind == "agents" and not exists:
            warnings.append(
                WarningMessage(
                    code="AGENTS_MISSING",
                    message="Project is missing AGENTS.md, so stable repo guidance is absent.",
                )
            )
    return summaries



def _build_git_summary(project_root: Path, warnings: list[WarningMessage]) -> GitSummary:
    if not (project_root / ".git").exists():
        return GitSummary(is_repo=False)

    branch_result = _run_git(project_root, ["branch", "--show-current"])
    status_result = _run_git(
        project_root,
        ["status", "--short", "--branch", "--untracked-files=all"],
    )
    if branch_result is None or status_result is None:
        warnings.append(
            WarningMessage(
                code="GIT_STATUS_UNAVAILABLE",
                message="Project looks git-backed but git status could not be read cleanly.",
            )
        )
        return GitSummary(is_repo=False)

    lines = status_result.splitlines()
    header = lines[0] if lines else ""
    entries = lines[1:] if header.startswith("##") else lines

    changed_paths: list[str] = []
    staged_count = 0
    unstaged_count = 0
    untracked_count = 0

    for line in entries:
        if not line:
            continue
        if line.startswith("??"):
            untracked_count += 1
            changed_paths.append(line[3:])
            continue
        status = line[:2]
        if len(status) == 2:
            if status[0] not in {" ", "?"}:
                staged_count += 1
            if status[1] != " ":
                unstaged_count += 1
        changed_paths.append(line[3:])

    return GitSummary(
        is_repo=True,
        branch=(branch_result.strip() or None),
        dirty=bool(entries),
        staged_count=staged_count,
        unstaged_count=unstaged_count,
        untracked_count=untracked_count,
        changed_paths=changed_paths,
    )



def _run_git(project_root: Path, args: list[str]) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(project_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()
