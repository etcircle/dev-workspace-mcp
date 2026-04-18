from __future__ import annotations

import contextlib
import os
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path
from tempfile import NamedTemporaryFile

from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.shared.text import normalize_newlines

_AGENT_ENV_DIR = ".devworkspace"
_AGENT_ENV_NAME = "agent.env"
_AGENT_ENV_GITIGNORE_ENTRY = ".devworkspace/agent.env"
_AGENT_ENV_TMP_GITIGNORE_ENTRY = ".devworkspace/.agent.env.*.tmp"
_AGENT_ENV_GITIGNORE_ENTRIES = [
    _AGENT_ENV_GITIGNORE_ENTRY,
    _AGENT_ENV_TMP_GITIGNORE_ENTRY,
]
_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")


def agent_env_path_for(project_root: Path) -> Path:
    return project_root / _AGENT_ENV_DIR / _AGENT_ENV_NAME


def load_agent_env(project_root: Path) -> dict[str, str]:
    env_path = agent_env_path_for(project_root)
    if not env_path.exists():
        return {}

    try:
        return _parse_agent_env(env_path.read_text(encoding="utf-8"), env_path)
    except OSError as exc:
        raise DomainError(
            code=ErrorCode.ENV_FILE_INVALID,
            message=f"Failed to read local env file for {project_root.name}.",
            hint="Check .devworkspace/agent.env permissions and contents, then try again.",
            details={"env_path": str(env_path), "error": str(exc)},
        ) from exc


def update_agent_env(project_root: Path, updates: Mapping[str, str]) -> Path:
    env_path = agent_env_path_for(project_root)
    if _is_git_tracked(project_root, env_path):
        raise DomainError(
            code=ErrorCode.ENV_FILE_INVALID,
            message=(
                f"Refusing to write local env values into git-tracked file: {env_path}"
            ),
            hint=(
                "Remove .devworkspace/agent.env from git tracking before "
                "storing local secrets there."
            ),
            details={"env_path": str(env_path)},
        )
    if not _is_effectively_git_ignored(project_root, env_path):
        raise DomainError(
            code=ErrorCode.ENV_FILE_INVALID,
            message=(
                f"Refusing to write local env values into non-ignored file: {env_path}"
            ),
            hint=(
                "Ensure .devworkspace/agent.env is effectively ignored by git before "
                "storing local secrets there."
            ),
            details={"env_path": str(env_path)},
        )
    current = load_agent_env(project_root)
    merged = dict(current)

    for key, value in updates.items():
        _validate_env_key(key, env_path)
        _validate_env_value(value, key, env_path)
        merged[key] = value

    rendered = "\n".join(f"{key}={value}" for key, value in merged.items())
    if rendered:
        rendered = f"{rendered}\n"

    try:
        write_text_atomic(env_path, rendered)
    except OSError as exc:
        raise DomainError(
            code=ErrorCode.ENV_FILE_INVALID,
            message=f"Failed to write local env file for {project_root.name}.",
            hint="Check .devworkspace directory permissions and try again.",
            details={"env_path": str(env_path), "error": str(exc)},
        ) from exc

    return env_path


def ensure_agent_env_gitignore(project_root: Path) -> Path:
    gitignore_path = project_root / ".gitignore"
    lines: list[str] = []
    try:
        if gitignore_path.exists():
            lines = normalize_newlines(gitignore_path.read_text(encoding="utf-8")).splitlines()
    except OSError as exc:
        raise DomainError(
            code=ErrorCode.ENV_FILE_INVALID,
            message=f"Failed to read .gitignore for {project_root.name}.",
            hint="Check .gitignore permissions and try again.",
            details={"gitignore_path": str(gitignore_path), "error": str(exc)},
        ) from exc

    filtered: list[str] = []
    seen_agent_env_entries: set[str] = set()
    for line in lines:
        if line in _AGENT_ENV_GITIGNORE_ENTRIES:
            if line in seen_agent_env_entries:
                continue
            seen_agent_env_entries.add(line)
        filtered.append(line)
    for entry in _AGENT_ENV_GITIGNORE_ENTRIES:
        if entry not in seen_agent_env_entries:
            filtered.append(entry)

    rendered = "\n".join(filtered) + "\n"
    try:
        write_text_atomic(gitignore_path, rendered)
    except OSError as exc:
        raise DomainError(
            code=ErrorCode.ENV_FILE_INVALID,
            message=f"Failed to update .gitignore for {project_root.name}.",
            hint="Check .gitignore permissions and try again.",
            details={"gitignore_path": str(gitignore_path), "error": str(exc)},
        ) from exc
    return gitignore_path


def _parse_agent_env(content: str, env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(normalize_newlines(content).splitlines(), start=1):
        if not raw_line:
            continue
        if "=" not in raw_line:
            _raise_invalid_env_file(env_path, line_number, raw_line, "Expected KEY=VALUE format.")
        key, value = raw_line.split("=", 1)
        _validate_env_key(key, env_path, line_number=line_number, raw_line=raw_line)
        _validate_env_value(value, key, env_path, line_number=line_number, raw_line=raw_line)
        if key in values:
            _raise_invalid_env_file(env_path, line_number, raw_line, f"Duplicate key: {key}")
        values[key] = value
    return values


def _validate_env_key(
    key: str,
    env_path: Path,
    *,
    line_number: int | None = None,
    raw_line: str | None = None,
) -> None:
    if not _ENV_NAME_RE.fullmatch(key):
        _raise_invalid_env_file(
            env_path,
            line_number,
            raw_line,
            "Environment variable names must match [A-Z_][A-Z0-9_]*.",
        )


def _validate_env_value(
    value: str,
    key: str,
    env_path: Path,
    *,
    line_number: int | None = None,
    raw_line: str | None = None,
) -> None:
    if "\n" in value or "\r" in value:
        _raise_invalid_env_file(
            env_path,
            line_number,
            raw_line,
            f"Environment value for {key} must stay on a single line.",
        )


def _raise_invalid_env_file(
    env_path: Path,
    line_number: int | None,
    raw_line: str | None,
    reason: str,
) -> None:
    details = {"env_path": str(env_path), "reason": reason}
    if line_number is not None:
        details["line_number"] = line_number
    raise DomainError(
        code=ErrorCode.ENV_FILE_INVALID,
        message=f"Invalid local env file: {env_path}",
        hint="Use plain KEY=VALUE lines in .devworkspace/agent.env.",
        details=details,
    )


def _is_git_tracked(project_root: Path, env_path: Path) -> bool:
    git_root = _find_git_root(project_root)
    if git_root is None:
        return False
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(git_root),
                "ls-files",
                "--error-unmatch",
                str(env_path.relative_to(git_root)),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except ValueError:
        return False
    except FileNotFoundError as exc:
        raise DomainError(
            code=ErrorCode.ENV_FILE_INVALID,
            message="Cannot verify git tracking state for .devworkspace/agent.env.",
            hint="Ensure git is available on PATH before storing local secrets.",
            details={"env_path": str(env_path)},
        ) from exc
    return result.returncode == 0


def _is_effectively_git_ignored(project_root: Path, env_path: Path) -> bool:
    git_root = _find_git_root(project_root)
    if git_root is None:
        return True
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(git_root),
                "check-ignore",
                str(env_path.relative_to(git_root)),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except ValueError:
        return False
    except FileNotFoundError as exc:
        raise DomainError(
            code=ErrorCode.ENV_FILE_INVALID,
            message="Cannot verify git ignore state for .devworkspace/agent.env.",
            hint="Ensure git is available on PATH before storing local secrets.",
            details={"env_path": str(env_path)},
        ) from exc
    return result.returncode == 0


def _find_git_root(project_root: Path) -> Path | None:
    for candidate in (project_root, *project_root.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: str | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            temp_path = handle.name
        os.replace(temp_path, path)
    except OSError:
        if temp_path is not None:
            with contextlib.suppress(OSError):
                Path(temp_path).unlink()
        raise


__all__ = [
    "agent_env_path_for",
    "ensure_agent_env_gitignore",
    "load_agent_env",
    "update_agent_env",
    "write_text_atomic",
]
