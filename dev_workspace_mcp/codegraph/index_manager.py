from __future__ import annotations

import hashlib
from pathlib import Path

from dev_workspace_mcp.codegraph.models import CodegraphIndexSnapshot
from dev_workspace_mcp.shared.paths import resolve_project_path, to_relative_display

_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
}


class CodegraphIndexManager:
    """In-memory placeholder for project codegraph indexes."""

    def __init__(self) -> None:
        self._snapshots: dict[str, CodegraphIndexSnapshot] = {}

    def get_snapshot(self, project_id: str) -> CodegraphIndexSnapshot:
        """Return the latest known snapshot for a project."""

        return self._snapshots.get(project_id, CodegraphIndexSnapshot(project_id=project_id))

    def record_snapshot(self, snapshot: CodegraphIndexSnapshot) -> CodegraphIndexSnapshot:
        """Store a snapshot until persistent indexing is implemented."""

        self._snapshots[snapshot.project_id] = snapshot
        return snapshot

    def clear_snapshot(self, project_id: str) -> bool:
        """Remove a cached snapshot if one exists."""

        return self._snapshots.pop(project_id, None) is not None

    def compute_state_token(self, project_root: Path, watched_paths: list[str]) -> str:
        digest = hashlib.sha256()
        normalized_paths = list(watched_paths or ["."])
        for relative_path in normalized_paths:
            resolved = resolve_project_path(project_root, relative_path)
            digest.update(relative_path.encode("utf-8"))
            digest.update(str(resolved.exists()).encode("utf-8"))
            for file_path in self._iter_candidate_files(project_root, relative_path):
                relative_display = to_relative_display(file_path, project_root)
                stat = file_path.stat()
                digest.update(relative_display.encode("utf-8"))
                digest.update(str(stat.st_size).encode("utf-8"))
                digest.update(str(stat.st_mtime_ns).encode("utf-8"))
        return digest.hexdigest()[:16]

    def _iter_candidate_files(self, project_root: Path, relative_path: str):
        root = resolve_project_path(project_root, relative_path)
        if not root.exists():
            return
        if root.is_file():
            yield root
            return
        for file_path in root.rglob("*"):
            if any(part in _IGNORED_DIRS for part in file_path.parts):
                continue
            if not file_path.is_file():
                continue
            yield resolve_project_path(project_root, str(file_path.relative_to(project_root)))


__all__ = ["CodegraphIndexManager"]
