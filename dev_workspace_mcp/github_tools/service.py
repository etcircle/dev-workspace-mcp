from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from dev_workspace_mcp.gittools.service import GitService
from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.models.github import (
    GitHubIssueDetail,
    GitHubIssueSearchResponse,
    GitHubIssueState,
    GitHubIssueSummary,
    GitHubPrDetail,
    GitHubPrFile,
    GitHubPrFilesResponse,
    GitHubRepoDetail,
    GitHubRepoRef,
)


class GitHubService:
    """Read-only GitHub API helper scoped to one project repository."""

    def __init__(
        self,
        project_root: Path,
        *,
        token: str | None = None,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
        base_url: str = "https://api.github.com",
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.git_service = GitService(self.project_root)
        self.token = token if token is not None else os.getenv("GITHUB_TOKEN")
        self._repo_ref: GitHubRepoRef | None = None
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            transport=transport,
            timeout=20.0,
            headers=self._headers(),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_repo(self) -> GitHubRepoDetail:
        repo = self._resolve_repo()
        payload = self._get(f"/repos/{repo.owner}/{repo.repo}")
        return GitHubRepoDetail(
            owner=repo.owner,
            repo=repo.repo,
            full_name=str(payload.get("full_name") or f"{repo.owner}/{repo.repo}"),
            description=_as_optional_string(payload.get("description")),
            default_branch=_as_optional_string(payload.get("default_branch")),
            private=bool(payload.get("private", False)),
            html_url=_as_optional_string(payload.get("html_url")),
        )

    def read_issue(self, issue_number: int) -> GitHubIssueDetail:
        repo = self._resolve_repo()
        payload = self._get(f"/repos/{repo.owner}/{repo.repo}/issues/{issue_number}")
        if isinstance(payload, dict) and payload.get("pull_request"):
            raise DomainError(
                code=ErrorCode.GITHUB_REQUEST_FAILED,
                message=f"GitHub issue #{issue_number} is a pull request, not an issue.",
                hint="Use github_pr_read for pull requests.",
                details={"issue_number": issue_number, "repo": f"{repo.owner}/{repo.repo}"},
            )
        return GitHubIssueDetail(
            number=int(payload.get("number") or issue_number),
            title=str(payload.get("title") or ""),
            state=str(payload.get("state") or "unknown"),
            author=_user_login(payload.get("user")),
            labels=_label_names(payload.get("labels")),
            html_url=_as_optional_string(payload.get("html_url")),
            created_at=_as_optional_string(payload.get("created_at")),
            updated_at=_as_optional_string(payload.get("updated_at")),
            body=_as_optional_string(payload.get("body")),
        )

    def search_issues(
        self,
        query: str,
        *,
        state: GitHubIssueState = "open",
        limit: int = 10,
    ) -> GitHubIssueSearchResponse:
        repo = self._resolve_repo()
        payload = self._get(
            "/search/issues",
            params={
                "q": self._issue_query(repo, query, state),
                "per_page": str(limit),
            },
        )
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        return GitHubIssueSearchResponse(
            query=query,
            state=state,
            total_count=int(payload.get("total_count") or 0),
            incomplete_results=bool(payload.get("incomplete_results", False)),
            issues=[self._issue_summary(item) for item in items if isinstance(item, dict)],
        )

    def read_pr(self, pr_number: int) -> GitHubPrDetail:
        repo = self._resolve_repo()
        payload = self._get(f"/repos/{repo.owner}/{repo.repo}/pulls/{pr_number}")
        return GitHubPrDetail(
            number=int(payload.get("number") or pr_number),
            title=str(payload.get("title") or ""),
            state=str(payload.get("state") or "unknown"),
            author=_user_login(payload.get("user")),
            draft=bool(payload.get("draft", False)),
            merged=bool(payload.get("merged", False)),
            html_url=_as_optional_string(payload.get("html_url")),
            base_ref=_nested_ref(payload.get("base")),
            head_ref=_nested_ref(payload.get("head")),
            created_at=_as_optional_string(payload.get("created_at")),
            updated_at=_as_optional_string(payload.get("updated_at")),
            body=_as_optional_string(payload.get("body")),
        )

    def list_pr_files(self, pr_number: int) -> GitHubPrFilesResponse:
        repo = self._resolve_repo()
        files: list[GitHubPrFile] = []
        page = 1
        while True:
            response = self._request(
                f"/repos/{repo.owner}/{repo.repo}/pulls/{pr_number}/files",
                params={"per_page": "100", "page": str(page)},
            )
            payload = self._parse_json(
                response,
                path=f"/repos/{repo.owner}/{repo.repo}/pulls/{pr_number}/files",
            )
            items = payload if isinstance(payload, list) else []
            files.extend(self._pr_file(item) for item in items if isinstance(item, dict))
            if not _has_next_page(response) and len(items) < 100:
                break
            page += 1
        return GitHubPrFilesResponse(pr_number=pr_number, files=files)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "dev-workspace-mcp",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _resolve_repo(self) -> GitHubRepoRef:
        if self._repo_ref is None:
            self._repo_ref = self.git_service.resolve_github_origin()
        return self._repo_ref

    def _get(self, path: str, *, params: dict[str, str] | None = None) -> Any:
        response = self._request(path, params=params)
        return self._parse_json(response, path=path)

    def _request(self, path: str, *, params: dict[str, str] | None = None) -> httpx.Response:
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise DomainError(
                code=ErrorCode.GITHUB_REQUEST_FAILED,
                message="GitHub request failed before a response was received.",
                hint="Check network access and GitHub API availability.",
                details={"path": path, "error": str(exc)},
            ) from exc
        if response.status_code >= 400:
            self._raise_response_error(response)
        return response

    def _parse_json(self, response: httpx.Response, *, path: str) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise DomainError(
                code=ErrorCode.GITHUB_REQUEST_FAILED,
                message="GitHub returned a non-JSON response.",
                details={"path": path, "status_code": response.status_code},
            ) from exc

    def _raise_response_error(self, response: httpx.Response) -> None:
        payload: dict[str, Any] = {}
        try:
            json_payload = response.json()
        except ValueError:
            json_payload = None
        if isinstance(json_payload, dict):
            payload = json_payload
        message = str(payload.get("message") or response.text.strip() or "GitHub request failed.")
        details = {
            "status_code": response.status_code,
            "method": response.request.method,
            "url": str(response.request.url),
            "response": message,
        }
        if response.status_code in {401, 403} and not self.token:
            raise DomainError(
                code=ErrorCode.GITHUB_AUTH_REQUIRED,
                message="GitHub authentication is required for this request.",
                hint="Set GITHUB_TOKEN to allow authenticated GitHub API reads.",
                details=details,
            )
        raise DomainError(
            code=ErrorCode.GITHUB_REQUEST_FAILED,
            message=message,
            hint=(
                "Confirm the repository resource exists and set GITHUB_TOKEN if the repo is "
                "private or GitHub is rate limiting anonymous requests."
            ),
            details=details,
        )

    @staticmethod
    def _issue_query(repo: GitHubRepoRef, query: str, state: GitHubIssueState) -> str:
        qualifiers = [f"repo:{repo.owner}/{repo.repo}", "is:issue"]
        if state == "all":
            qualifiers.append("is:all")
        else:
            qualifiers.append(f"state:{state}")
        qualifiers.append(query)
        return " ".join(qualifiers)

    @staticmethod
    def _issue_summary(payload: dict[str, Any]) -> GitHubIssueSummary:
        return GitHubIssueSummary(
            number=int(payload.get("number") or 0),
            title=str(payload.get("title") or ""),
            state=str(payload.get("state") or "unknown"),
            author=_user_login(payload.get("user")),
            labels=_label_names(payload.get("labels")),
            html_url=_as_optional_string(payload.get("html_url")),
            created_at=_as_optional_string(payload.get("created_at")),
            updated_at=_as_optional_string(payload.get("updated_at")),
        )

    @staticmethod
    def _pr_file(payload: dict[str, Any]) -> GitHubPrFile:
        return GitHubPrFile(
            filename=str(payload.get("filename") or ""),
            status=str(payload.get("status") or "unknown"),
            additions=int(payload.get("additions") or 0),
            deletions=int(payload.get("deletions") or 0),
            changes=int(payload.get("changes") or 0),
            previous_filename=_as_optional_string(payload.get("previous_filename")),
            patch=_as_optional_string(payload.get("patch")),
        )



def _label_names(payload: Any) -> list[str]:
    if not isinstance(payload, list):
        return []
    labels: list[str] = []
    for item in payload:
        if isinstance(item, dict):
            name = item.get("name")
            if name:
                labels.append(str(name))
    return labels



def _user_login(payload: Any) -> str | None:
    if isinstance(payload, dict):
        login = payload.get("login")
        if login:
            return str(login)
    return None



def _nested_ref(payload: Any) -> str | None:
    if isinstance(payload, dict):
        ref = payload.get("ref")
        if ref:
            return str(ref)
    return None



def _as_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value)
    return normalized or None


def _has_next_page(response: httpx.Response) -> bool:
    link_header = response.headers.get("Link", "")
    return 'rel="next"' in link_header


__all__ = ["GitHubService"]
