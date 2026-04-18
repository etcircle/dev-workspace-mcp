from __future__ import annotations

from pathlib import Path, PurePosixPath


def ensure_relative_path(path: str) -> PurePosixPath:
    """Validate and normalize a project-relative path."""

    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Path must stay relative to the project root: {path}")
    return candidate


def resolve_relative_path(root: Path, relative_path: str) -> Path:
    """Resolve a safe relative path against a filesystem root."""

    return Path(root).joinpath(ensure_relative_path(relative_path))


def to_relative_display(path: Path, root: Path) -> str:
    """Render a path relative to the given root when possible."""

    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(path)


__all__ = ["ensure_relative_path", "resolve_relative_path", "to_relative_display"]