from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from dev_workspace_mcp.files.validation import validate_relative_path
from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.models.git import (
    GitCheckoutResponse,
    GitCommitResponse,
    GitDiffResponse,
    GitFileChange,
    GitStatusResponse,
)

_BRANCH_PATTERN = re.compile(
    r"^(?P<branch>[^.]+?)(?:\.\.\.(?P<upstream>[^\[]+?))?(?: \[(?P<tracking>.+)\])?$"
)


class GitService:
    """Structured git operations scoped to one project root."""

    def __init__(self, project_root: Path, *, max_diff_bytes: int = 200_000) -> None:
        self.project_root = Path(project_root).resolve()
        self.max_diff_bytes = max_diff_bytes

    def git_status(self, *, include_untracked: bool = True) -> GitStatusResponse:
        self._require_git()
        status = self._run_git(
            [
                "status",
                "--short",
                "--branch",
                "--untracked-files=all" if include_untracked else "--untracked-files=no",
            ]
        )
        return self._parse_status(status.stdout)

    def git_diff(
        self,
        *,
        path: str | None = None,
        ref: str | None = None,
        staged: bool = False,
        context_lines: int = 3,
    ) -> GitDiffResponse:
        self._require_git()
        args = ["diff", f"--unified={context_lines}"]
        if staged:
            args.append("--staged")
        if ref:
            args.append(ref)
        if path is not None:
            args.extend(["--", validate_relative_path(path)])

        result = self._run_git(args)
        raw = result.stdout
        encoded = raw.encode("utf-8")
        truncated = len(encoded) > self.max_diff_bytes
        if truncated:
            raw = encoded[: self.max_diff_bytes].decode("utf-8", errors="replace")
        return GitDiffResponse(diff=raw, truncated=truncated)

    def git_checkout(
        self,
        *,
        ref: str,
        create: bool = False,
        force: bool = False,
    ) -> GitCheckoutResponse:
        self._require_git()
        args = ["checkout"]
        if force:
            args.append("--force")
        if create:
            args.extend(["-b", ref])
        else:
            args.append(ref)
        self._run_git(args)
        return self._current_checkout()

    def git_commit(
        self,
        *,
        message: str,
        paths: list[str] | None = None,
        all: bool = False,
    ) -> GitCommitResponse:
        self._require_git()
        message = message.strip()
        if not message:
            raise DomainError(
                code=ErrorCode.VALIDATION_ERROR,
                message="Commit message cannot be empty.",
            )
        if all and paths:
            raise DomainError(
                code=ErrorCode.VALIDATION_ERROR,
                message="Use either paths or all=true, not both.",
                hint=(
                    "Pass explicit project-relative paths, or commit tracked "
                    "changes with all=true."
                ),
            )

        normalized_paths = [validate_relative_path(path) for path in (paths or [])]
        if normalized_paths:
            self._run_git(["add", "--", *normalized_paths])

        commit_args = ["commit"]
        if all:
            commit_args.append("-a")
        commit_args.extend(["-m", message])
        self._run_git(commit_args)

        head_sha = self._run_git(["rev-parse", "HEAD"]).stdout.strip() or None
        summary = self._run_git(["show", "-s", "--format=%s", "HEAD"]).stdout.strip() or None
        changed_paths = normalized_paths or self._head_changed_paths()
        return GitCommitResponse(
            commit_sha=head_sha,
            summary=summary,
            changed_paths=changed_paths,
        )

    def status_summary(self) -> dict[str, str | bool | int | list[str] | None]:
        status = self.git_status()
        changed_paths = [change.path for change in status.changes]
        staged_count = sum(
            change.change_type in {"added", "deleted", "renamed", "copied"}
            for change in status.changes
        )
        unstaged_count = sum(change.change_type == "modified" for change in status.changes)
        untracked_count = sum(change.change_type == "untracked" for change in status.changes)
        return {
            "project_root": str(self.project_root),
            "is_repository": True,
            "branch": status.branch,
            "clean": status.clean,
            "changed_paths": changed_paths,
            "staged_count": int(staged_count),
            "unstaged_count": int(unstaged_count),
            "untracked_count": int(untracked_count),
        }

    def is_repository(self) -> bool:
        if shutil.which("git") is None:
            return False
        result = subprocess.run(
            ["git", "-C", str(self.project_root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

    def _current_checkout(self) -> GitCheckoutResponse:
        branch = self._run_git(["branch", "--show-current"]).stdout.strip() or None
        head_sha = self._run_git(["rev-parse", "HEAD"]).stdout.strip() or None
        return GitCheckoutResponse(branch=branch, detached=branch is None, head_sha=head_sha)

    def _head_changed_paths(self) -> list[str]:
        result = self._run_git(["show", "--pretty=format:", "--name-only", "HEAD"])
        return [line for line in result.stdout.splitlines() if line.strip()]

    def _require_git(self) -> None:
        if shutil.which("git") is None:
            raise DomainError(
                code=ErrorCode.GIT_NOT_AVAILABLE,
                message="git is not available on this machine.",
            )
        if not self.is_repository():
            raise DomainError(
                code=ErrorCode.GIT_OPERATION_FAILED,
                message=f"Project at {self.project_root} is not a readable git repository.",
                hint="Use a project discovered from a real git work tree.",
            )

    def _run_git(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", "-C", str(self.project_root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise DomainError(
                code=ErrorCode.GIT_OPERATION_FAILED,
                message=(
                    result.stderr.strip()
                    or result.stdout.strip()
                    or f"git {' '.join(args)} failed"
                ),
                details={"argv": ["git", "-C", str(self.project_root), *args]},
            )
        return result

    def _parse_status(self, text: str) -> GitStatusResponse:
        lines = text.splitlines()
        branch = None
        upstream = None
        ahead = 0
        behind = 0
        changes: list[GitFileChange] = []

        if lines and lines[0].startswith("## "):
            branch, upstream, ahead, behind = self._parse_branch_header(lines[0][3:])
            lines = lines[1:]

        for line in lines:
            if not line.strip():
                continue
            status_code = line[:2]
            payload = line[3:]
            old_path = None
            path = payload
            if " -> " in payload:
                old_path, path = payload.split(" -> ", maxsplit=1)
            changes.append(
                GitFileChange(
                    path=path,
                    old_path=old_path,
                    change_type=self._map_change_type(status_code),
                )
            )

        return GitStatusResponse(
            branch=branch,
            upstream=upstream,
            ahead=ahead,
            behind=behind,
            clean=not changes,
            changes=changes,
        )

    def _parse_branch_header(self, header: str) -> tuple[str | None, str | None, int, int]:
        if header.startswith("HEAD"):
            return None, None, 0, 0

        match = _BRANCH_PATTERN.match(header)
        if not match:
            return header.strip() or None, None, 0, 0

        branch = (match.group("branch") or "").strip() or None
        upstream = (match.group("upstream") or "").strip() or None
        ahead = 0
        behind = 0
        tracking = (match.group("tracking") or "").strip()
        if tracking:
            for part in tracking.split(","):
                item = part.strip()
                if item.startswith("ahead "):
                    ahead = int(item.removeprefix("ahead ").strip())
                elif item.startswith("behind "):
                    behind = int(item.removeprefix("behind ").strip())
        return branch, upstream, ahead, behind

    @staticmethod
    def _map_change_type(status_code: str) -> str:
        if status_code == "??":
            return "untracked"
        significant = [char for char in status_code if char not in {" ", "?"}]
        if not significant:
            return "unknown"
        if any(char == "R" for char in significant):
            return "renamed"
        if any(char == "C" for char in significant):
            return "copied"
        if any(char == "A" for char in significant):
            return "added"
        if any(char == "D" for char in significant):
            return "deleted"
        if any(char == "M" for char in significant):
            return "modified"
        return "unknown"


__all__ = ["GitService"]
