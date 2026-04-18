from __future__ import annotations

from pathlib import Path

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.projects.manifest import MANIFEST_NAME

_DISCOVERY_MARKERS = (MANIFEST_NAME, ".git")


def is_project_root(path: Path) -> bool:
    return any((path / marker).exists() for marker in _DISCOVERY_MARKERS)



def discover_project_roots(settings: Settings) -> list[Path]:
    discovered: dict[str, Path] = {}
    for workspace_root in settings.expanded_workspace_roots:
        if not workspace_root.exists():
            continue

        candidates = [workspace_root] if is_project_root(workspace_root) else []
        candidates.extend(
            child
            for child in workspace_root.iterdir()
            if child.is_dir() and not child.name.startswith(".") and is_project_root(child)
        )

        for candidate in candidates:
            discovered[str(candidate.resolve())] = candidate.resolve()

    return sorted(discovered.values(), key=lambda path: path.name.lower())
