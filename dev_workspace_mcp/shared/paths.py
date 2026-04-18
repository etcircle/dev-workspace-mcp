from __future__ import annotations

from pathlib import Path, PurePosixPath

from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode


def ensure_relative_path(path: str) -> PurePosixPath:
    """Validate and normalize a project-relative path."""

    candidate = PurePosixPath(path or ".")
    if candidate.is_absolute() or ".." in candidate.parts:
        raise DomainError(
            code=ErrorCode.INVALID_PATH,
            message=f"Path must stay relative to the project root: {path}",
            hint="Use a project-relative path that stays inside the project root.",
        )
    return candidate


def resolve_relative_path(root: Path, relative_path: str) -> Path:
    """Lexically resolve a validated relative path against a filesystem root."""

    return Path(root).joinpath(ensure_relative_path(relative_path))


def resolve_project_path(
    project_root: Path,
    relative_path: str,
    *,
    allow_missing_leaf: bool = False,
    forbid_symlinks: bool = False,
) -> Path:
    """Resolve a project-relative path and enforce post-resolution containment.

    When ``allow_missing_leaf`` is true, the final path component may be absent so long as the
    resolved parent remains inside the project root. When ``forbid_symlinks`` is true, any
    existing symlink encountered along the relative path is rejected.
    """

    root = Path(project_root).resolve()
    candidate = resolve_relative_path(root, relative_path)
    symlink_component = _find_existing_symlink_component(root, relative_path)
    if forbid_symlinks and symlink_component is not None:
        raise DomainError(
            code=ErrorCode.PATH_SYMLINK_DENIED,
            message=f"Symlink traversal is not allowed for path: {relative_path}",
            hint="Use a real in-project path instead of a symlinked target.",
            details={
                "path": relative_path,
                "symlink_path": _relative_or_absolute(symlink_component, root),
            },
        )

    if allow_missing_leaf:
        resolved_parent = candidate.parent.resolve()
        _ensure_inside_project(root, resolved_parent, relative_path)
        return resolved_parent / candidate.name

    resolved = candidate.resolve()
    _ensure_inside_project(root, resolved, relative_path)
    return resolved


def to_relative_display(path: Path, root: Path) -> str:
    """Render a path relative to the given root when possible."""

    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(path)


def _ensure_inside_project(project_root: Path, resolved_path: Path, relative_path: str) -> None:
    try:
        resolved_path.relative_to(project_root)
    except ValueError as exc:
        raise DomainError(
            code=ErrorCode.PATH_OUTSIDE_PROJECT,
            message=f"Path resolves outside the project root: {relative_path}",
            hint="Use a path that resolves inside the selected project.",
            details={"path": relative_path},
        ) from exc


def _find_existing_symlink_component(project_root: Path, relative_path: str) -> Path | None:
    current = project_root
    for part in ensure_relative_path(relative_path).parts:
        current = current / part
        if current.is_symlink():
            return current
        if not current.exists():
            break
    return None


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


__all__ = [
    "ensure_relative_path",
    "resolve_relative_path",
    "resolve_project_path",
    "to_relative_display",
]
