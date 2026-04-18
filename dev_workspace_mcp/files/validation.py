from __future__ import annotations

from pathlib import PurePosixPath

from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode


def is_safe_relative_path(path: str) -> bool:
    """Return whether a path is relative and stays inside the project root."""

    candidate = PurePosixPath(path or ".")
    return not candidate.is_absolute() and ".." not in candidate.parts



def validate_relative_path(path: str) -> str:
    """Validate a project-relative path and return a normalized display string."""

    candidate = PurePosixPath(path or ".")
    if not is_safe_relative_path(str(candidate)):
        raise DomainError(
            code=ErrorCode.INVALID_PATH,
            message=f"Unsafe relative path: {path}",
            hint="Use a project-relative path that stays inside the project root.",
        )
    normalized = str(candidate)
    return "." if normalized == "" else normalized


__all__ = ["is_safe_relative_path", "validate_relative_path"]
