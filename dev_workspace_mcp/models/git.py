from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

GitChangeType = Literal["added", "modified", "deleted", "renamed", "copied", "untracked", "unknown"]


class GitFileChange(BaseModel):
    path: str
    change_type: GitChangeType = "unknown"
    old_path: str | None = None


class GitStatusRequest(BaseModel):
    project_id: str
    include_untracked: bool = True


class GitStatusResponse(BaseModel):
    branch: str | None = None
    upstream: str | None = None
    ahead: int = Field(default=0, ge=0)
    behind: int = Field(default=0, ge=0)
    clean: bool = True
    changes: list[GitFileChange] = Field(default_factory=list)


class GitDiffRequest(BaseModel):
    project_id: str
    path: str | None = None
    ref: str | None = None
    staged: bool = False
    context_lines: int = Field(default=3, ge=0)


class GitDiffResponse(BaseModel):
    diff: str
    truncated: bool = False


class GitCheckoutRequest(BaseModel):
    project_id: str
    ref: str
    create: bool = False
    force: bool = False


class GitCheckoutResponse(BaseModel):
    branch: str | None = None
    detached: bool = False
    head_sha: str | None = None


class GitCommitRequest(BaseModel):
    project_id: str
    message: str
    paths: list[str] = Field(default_factory=list)
    all: bool = False


class GitCommitResponse(BaseModel):
    commit_sha: str | None = None
    summary: str | None = None
    changed_paths: list[str] = Field(default_factory=list)


__all__ = [
    "GitChangeType",
    "GitCheckoutRequest",
    "GitCheckoutResponse",
    "GitCommitRequest",
    "GitCommitResponse",
    "GitDiffRequest",
    "GitDiffResponse",
    "GitFileChange",
    "GitStatusRequest",
    "GitStatusResponse",
]
