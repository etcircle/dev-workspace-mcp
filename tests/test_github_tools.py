from __future__ import annotations

import subprocess
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.github_tools.service import GitHubService
from dev_workspace_mcp.mcp_server import tool_registry as tool_registry_module
from dev_workspace_mcp.mcp_server.tool_registry import build_tool_registry
from dev_workspace_mcp.models.github import (
    GitHubIssueDetail,
    GitHubIssueSearchResponse,
    GitHubIssueSummary,
    GitHubPrDetail,
    GitHubPrFile,
    GitHubPrFilesResponse,
    GitHubRepoDetail,
)
from dev_workspace_mcp.projects.registry import ProjectRegistry


def _build_tools(workspace_root: Path):
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    return build_tool_registry(registry)


def _init_git_history(project_root: Path) -> None:
    subprocess.run(
        ["git", "-C", str(project_root), "config", "user.name", "Test User"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(project_root), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(["git", "-C", str(project_root), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(project_root), "commit", "-m", "initial"], check=True)


class _FakeGitHubService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int | str | None]] = []

    def get_repo(self) -> GitHubRepoDetail:
        self.calls.append(("repo", None))
        return GitHubRepoDetail(
            owner="example-org",
            repo="demo-repo",
            full_name="example-org/demo-repo",
            description="Demo repository",
            default_branch="main",
            private=False,
            html_url="https://github.com/example-org/demo-repo",
        )

    def read_issue(self, issue_number: int) -> GitHubIssueDetail:
        self.calls.append(("issue", issue_number))
        return GitHubIssueDetail(
            number=issue_number,
            title="Fix bug",
            state="open",
            author="alice",
            labels=["bug"],
            html_url=f"https://github.com/example-org/demo-repo/issues/{issue_number}",
            body="Issue body",
        )

    def search_issues(
        self,
        query: str,
        *,
        state: str = "open",
        limit: int = 10,
    ) -> GitHubIssueSearchResponse:
        self.calls.append(("issue_search", query))
        return GitHubIssueSearchResponse(
            query=query,
            state=state,
            total_count=1,
            incomplete_results=False,
            issues=[
                GitHubIssueSummary(
                    number=11,
                    title="Fix bug",
                    state="open",
                    author="alice",
                    labels=["bug"],
                    html_url="https://github.com/example-org/demo-repo/issues/11",
                )
            ],
        )

    def read_pr(self, pr_number: int) -> GitHubPrDetail:
        self.calls.append(("pr", pr_number))
        return GitHubPrDetail(
            number=pr_number,
            title="Add feature",
            state="open",
            author="bob",
            draft=False,
            merged=False,
            html_url=f"https://github.com/example-org/demo-repo/pull/{pr_number}",
            base_ref="main",
            head_ref="feature/demo",
            body="PR body",
        )

    def list_pr_files(self, pr_number: int) -> GitHubPrFilesResponse:
        self.calls.append(("pr_files", pr_number))
        return GitHubPrFilesResponse(
            pr_number=pr_number,
            files=[
                GitHubPrFile(
                    filename="src/app.py",
                    status="modified",
                    additions=10,
                    deletions=2,
                    changes=12,
                    patch="@@ -1 +1 @@",
                )
            ],
        )


def test_github_service_reads_repo_issue_search_and_pr_data(make_git_project) -> None:
    project_root = make_git_project(real_git=True)
    (project_root / "README.md").write_text("hello\n", encoding="utf-8")
    _init_git_history(project_root)
    subprocess.run(
        [
            "git",
            "-C",
            str(project_root),
            "remote",
            "add",
            "origin",
            "https://github.com/example-org/demo-repo.git",
        ],
        check=True,
    )
    seen: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path == "/repos/example-org/demo-repo":
            return httpx.Response(
                200,
                request=request,
                json={
                    "full_name": "example-org/demo-repo",
                    "owner": {"login": "example-org"},
                    "name": "demo-repo",
                    "description": "Demo repository",
                    "default_branch": "main",
                    "private": False,
                    "html_url": "https://github.com/example-org/demo-repo",
                },
            )
        if request.url.path == "/repos/example-org/demo-repo/issues/42":
            return httpx.Response(
                200,
                request=request,
                json={
                    "number": 42,
                    "title": "Fix bug",
                    "state": "open",
                    "user": {"login": "alice"},
                    "labels": [{"name": "bug"}],
                    "html_url": "https://github.com/example-org/demo-repo/issues/42",
                    "body": "Issue body",
                    "created_at": "2026-04-19T12:00:00Z",
                    "updated_at": "2026-04-19T12:30:00Z",
                },
            )
        if request.url.path == "/search/issues":
            params = parse_qs(request.url.query.decode())
            assert params["q"][0] == "repo:example-org/demo-repo is:issue is:all flaky test"
            assert params["per_page"][0] == "5"
            return httpx.Response(
                200,
                request=request,
                json={
                    "total_count": 1,
                    "incomplete_results": False,
                    "items": [
                        {
                            "number": 42,
                            "title": "Fix bug",
                            "state": "open",
                            "user": {"login": "alice"},
                            "labels": [{"name": "bug"}],
                            "html_url": "https://github.com/example-org/demo-repo/issues/42",
                            "created_at": "2026-04-19T12:00:00Z",
                            "updated_at": "2026-04-19T12:30:00Z",
                        }
                    ],
                },
            )
        if request.url.path == "/repos/example-org/demo-repo/pulls/7":
            return httpx.Response(
                200,
                request=request,
                json={
                    "number": 7,
                    "title": "Add feature",
                    "state": "open",
                    "user": {"login": "bob"},
                    "draft": False,
                    "merged": False,
                    "html_url": "https://github.com/example-org/demo-repo/pull/7",
                    "body": "PR body",
                    "base": {"ref": "main"},
                    "head": {"ref": "feature/demo"},
                    "created_at": "2026-04-19T12:00:00Z",
                    "updated_at": "2026-04-19T12:30:00Z",
                },
            )
        if request.url.path == "/repos/example-org/demo-repo/pulls/7/files":
            return httpx.Response(
                200,
                request=request,
                json=[
                    {
                        "filename": "src/app.py",
                        "status": "modified",
                        "additions": 10,
                        "deletions": 2,
                        "changes": 12,
                        "patch": "@@ -1 +1 @@",
                    }
                ],
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    service = GitHubService(project_root, transport=httpx.MockTransport(_handler))

    repo = service.get_repo()
    issue = service.read_issue(42)
    search = service.search_issues("flaky test", state="all", limit=5)
    pr = service.read_pr(7)
    files = service.list_pr_files(7)

    assert repo.full_name == "example-org/demo-repo"
    assert issue.number == 42
    assert search.issues[0].number == 42
    assert pr.head_ref == "feature/demo"
    assert files.files[0].filename == "src/app.py"
    assert seen == [
        "https://api.github.com/repos/example-org/demo-repo",
        "https://api.github.com/repos/example-org/demo-repo/issues/42",
        "https://api.github.com/search/issues?q=repo%3Aexample-org%2Fdemo-repo+is%3Aissue+is%3Aall+flaky+test&per_page=5",
        "https://api.github.com/repos/example-org/demo-repo/pulls/7",
        "https://api.github.com/repos/example-org/demo-repo/pulls/7/files?per_page=100&page=1",
    ]


def test_github_service_rejects_pull_request_payload_from_issue_read(make_git_project) -> None:
    project_root = make_git_project(real_git=True)
    (project_root / "README.md").write_text("hello\n", encoding="utf-8")
    _init_git_history(project_root)
    subprocess.run(
        [
            "git",
            "-C",
            str(project_root),
            "remote",
            "add",
            "origin",
            "https://github.com/example-org/demo-repo.git",
        ],
        check=True,
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "number": 42,
                "title": "Actually a PR",
                "state": "open",
                "pull_request": {"url": "https://api.github.com/repos/example-org/demo-repo/pulls/42"},
            },
        )

    service = GitHubService(project_root, transport=httpx.MockTransport(_handler))

    try:
        service.read_issue(42)
    except Exception as exc:  # pragma: no branch
        error = exc
    else:  # pragma: no cover
        raise AssertionError("Expected GitHubService.read_issue() to fail for pull request payload")

    assert getattr(error, "code", None) == "GITHUB_REQUEST_FAILED"
    assert "github_pr_read" in getattr(error, "hint", "")


def test_github_service_paginates_pr_files(make_git_project) -> None:
    project_root = make_git_project(real_git=True)
    (project_root / "README.md").write_text("hello\n", encoding="utf-8")
    _init_git_history(project_root)
    subprocess.run(
        [
            "git",
            "-C",
            str(project_root),
            "remote",
            "add",
            "origin",
            "https://github.com/example-org/demo-repo.git",
        ],
        check=True,
    )
    seen: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        params = parse_qs(request.url.query.decode())
        page = params["page"][0]
        headers = {}
        if page == "1":
            headers["Link"] = (
                "<https://api.github.com/repos/example-org/demo-repo/pulls/7/files"
                '?per_page=100&page=2>; rel="next"'
            )
            payload = [
                {
                    "filename": "src/app.py",
                    "status": "modified",
                    "additions": 10,
                    "deletions": 2,
                    "changes": 12,
                }
            ]
        elif page == "2":
            payload = [
                {
                    "filename": "src/lib.py",
                    "status": "added",
                    "additions": 5,
                    "deletions": 0,
                    "changes": 5,
                }
            ]
        else:  # pragma: no cover
            raise AssertionError(f"Unexpected page: {page}")
        return httpx.Response(200, request=request, json=payload, headers=headers)

    service = GitHubService(project_root, transport=httpx.MockTransport(_handler))
    files = service.list_pr_files(7)

    assert [item.filename for item in files.files] == ["src/app.py", "src/lib.py"]
    assert seen == [
        "https://api.github.com/repos/example-org/demo-repo/pulls/7/files?per_page=100&page=1",
        "https://api.github.com/repos/example-org/demo-repo/pulls/7/files?per_page=100&page=2",
    ]


def test_github_service_maps_403_without_token_to_auth_required(make_git_project) -> None:
    project_root = make_git_project(real_git=True)
    (project_root / "README.md").write_text("hello\n", encoding="utf-8")
    _init_git_history(project_root)
    subprocess.run(
        [
            "git",
            "-C",
            str(project_root),
            "remote",
            "add",
            "origin",
            "git@github.com:example-org/private-repo.git",
        ],
        check=True,
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            request=request,
            json={"message": "API rate limit exceeded for 127.0.0.1."},
        )

    service = GitHubService(project_root, transport=httpx.MockTransport(_handler), token=None)

    try:
        service.get_repo()
    except Exception as exc:  # pragma: no branch
        error = exc
    else:  # pragma: no cover
        raise AssertionError("Expected GitHubService.get_repo() to fail")

    assert getattr(error, "code", None) == "GITHUB_AUTH_REQUIRED"
    assert "GITHUB_TOKEN" in getattr(error, "hint", "")


def test_github_tools_validate_inputs_and_return_structured_payloads(
    workspace_root,
    make_git_project,
    monkeypatch,
) -> None:
    make_git_project()
    fake_service = _FakeGitHubService()
    monkeypatch.setattr(
        tool_registry_module,
        "_github_service",
        lambda *args, **kwargs: fake_service,
    )
    tools = _build_tools(workspace_root)

    invalid = tools.run("github_issue_read", project_id="git-project", issue_number=0)
    repo = tools.run("github_repo", project_id="git-project")
    issue = tools.run("github_issue_read", project_id="git-project", issue_number=42)
    search = tools.run(
        "github_issue_search",
        project_id="git-project",
        query="flaky test",
        state="all",
        limit=5,
    )
    pr = tools.run("github_pr_read", project_id="git-project", pr_number=7)
    files = tools.run("github_pr_files", project_id="git-project", pr_number=7)

    assert invalid["ok"] is False
    assert invalid["error"]["code"] == "VALIDATION_ERROR"
    assert invalid["error"]["details"]["issues"][0]["field"] == "issue_number"

    assert repo["ok"] is True
    assert repo["data"]["full_name"] == "example-org/demo-repo"
    assert issue["data"]["number"] == 42
    assert search["data"]["issues"][0]["title"] == "Fix bug"
    assert pr["data"]["base_ref"] == "main"
    assert files["data"]["files"][0]["filename"] == "src/app.py"
    assert fake_service.calls == [
        ("repo", None),
        ("issue", 42),
        ("issue_search", "flaky test"),
        ("pr", 7),
        ("pr_files", 7),
    ]


def test_github_repo_returns_structured_error_when_origin_is_missing(
    workspace_root,
    make_git_project,
) -> None:
    project_root = make_git_project(real_git=True)
    (project_root / "README.md").write_text("hello\n", encoding="utf-8")
    _init_git_history(project_root)
    tools = _build_tools(workspace_root)

    result = tools.run("github_repo", project_id="git-project")

    assert result["ok"] is False
    assert result["error"]["code"] == "GITHUB_REMOTE_NOT_CONFIGURED"


def test_github_repo_returns_structured_error_when_origin_is_not_github(
    workspace_root,
    make_git_project,
) -> None:
    project_root = make_git_project(real_git=True)
    (project_root / "README.md").write_text("hello\n", encoding="utf-8")
    _init_git_history(project_root)
    subprocess.run(
        [
            "git",
            "-C",
            str(project_root),
            "remote",
            "add",
            "origin",
            "https://gitlab.com/example-org/demo-repo.git",
        ],
        check=True,
    )
    tools = _build_tools(workspace_root)

    result = tools.run("github_repo", project_id="git-project")

    assert result["ok"] is False
    assert result["error"]["code"] == "GITHUB_REMOTE_NOT_CONFIGURED"
