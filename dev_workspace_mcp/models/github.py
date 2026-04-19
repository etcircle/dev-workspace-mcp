from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

GitHubIssueState = Literal["open", "closed", "all"]


class GitHubRepoRef(BaseModel):
    owner: str
    repo: str
    origin_url: str


class GitHubRepoRequest(BaseModel):
    project_id: str


class GitHubRepoDetail(BaseModel):
    owner: str
    repo: str
    full_name: str
    description: str | None = None
    default_branch: str | None = None
    private: bool = False
    html_url: str | None = None


class GitHubIssueReadRequest(BaseModel):
    project_id: str
    issue_number: int = Field(gt=0)


class GitHubIssueSummary(BaseModel):
    number: int
    title: str
    state: str
    author: str | None = None
    labels: list[str] = Field(default_factory=list)
    html_url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class GitHubIssueDetail(GitHubIssueSummary):
    body: str | None = None


class GitHubIssueSearchRequest(BaseModel):
    project_id: str
    query: str
    state: GitHubIssueState = "open"
    limit: int = Field(default=10, ge=1, le=100)

    @field_validator("query")
    @classmethod
    def _validate_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must not be empty")
        return normalized


class GitHubIssueSearchResponse(BaseModel):
    query: str
    state: GitHubIssueState = "open"
    total_count: int = 0
    incomplete_results: bool = False
    issues: list[GitHubIssueSummary] = Field(default_factory=list)


class GitHubPrReadRequest(BaseModel):
    project_id: str
    pr_number: int = Field(gt=0)


class GitHubPrDetail(BaseModel):
    number: int
    title: str
    state: str
    author: str | None = None
    draft: bool = False
    merged: bool = False
    html_url: str | None = None
    base_ref: str | None = None
    head_ref: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    body: str | None = None


class GitHubPrFilesRequest(BaseModel):
    project_id: str
    pr_number: int = Field(gt=0)


class GitHubPrFile(BaseModel):
    filename: str
    status: str
    additions: int = 0
    deletions: int = 0
    changes: int = 0
    previous_filename: str | None = None
    patch: str | None = None


class GitHubPrFilesResponse(BaseModel):
    pr_number: int
    files: list[GitHubPrFile] = Field(default_factory=list)


__all__ = [
    "GitHubIssueDetail",
    "GitHubIssueReadRequest",
    "GitHubIssueSearchRequest",
    "GitHubIssueSearchResponse",
    "GitHubIssueState",
    "GitHubIssueSummary",
    "GitHubPrDetail",
    "GitHubPrFile",
    "GitHubPrFilesRequest",
    "GitHubPrFilesResponse",
    "GitHubPrReadRequest",
    "GitHubRepoDetail",
    "GitHubRepoRef",
    "GitHubRepoRequest",
]
