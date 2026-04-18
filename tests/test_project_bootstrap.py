from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.models.project_bootstrap import (
    BootstrapProjectRequest,
    BootstrapProjectResponse,
)
from dev_workspace_mcp.projects.bootstrap import ProjectBootstrapService
from dev_workspace_mcp.projects.manifest import load_manifest
from dev_workspace_mcp.projects.registry import ProjectRegistry
from dev_workspace_mcp.shared.env_files import ensure_agent_env_gitignore


@pytest.mark.parametrize(
    ("payload", "missing_field"),
    [
        ({"mode": "create"}, "folder_name"),
        ({"mode": "clone"}, "repo_url"),
        ({"mode": "import"}, "path"),
    ],
)
def test_bootstrap_request_requires_mode_specific_fields(
    payload: dict[str, object],
    missing_field: str,
) -> None:
    with pytest.raises(ValidationError) as exc:
        BootstrapProjectRequest.model_validate(payload)

    assert missing_field in str(exc.value)


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "create", "folder_name": "demo", "repo_url": "https://example.com/repo.git"},
        {"mode": "clone", "repo_url": "https://example.com/repo.git", "path": "/tmp/demo"},
        {"mode": "import", "path": "/tmp/demo", "git_init": True},
    ],
)
def test_bootstrap_request_rejects_mixed_mode_fields(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        BootstrapProjectRequest.model_validate(payload)


def test_bootstrap_request_rejects_unimplemented_template() -> None:
    with pytest.raises(ValidationError):
        BootstrapProjectRequest.model_validate(
            {"mode": "create", "folder_name": "demo-project", "template": "python"}
        )


def test_bootstrap_response_exposes_stable_wave_one_fields() -> None:
    response = BootstrapProjectResponse(
        project_id="demo-id",
        root_path="/tmp/demo-project",
        manifest_path="/tmp/demo-project/.devworkspace.yaml",
        created_files=[".devworkspace.yaml", ".devworkspace/memory.md"],
        git_initialized=True,
        git_cloned=False,
        warnings=["manifest already existed"],
        recommended_next_tools=["list_projects", "project_snapshot"],
    )

    assert response.project_id == "demo-id"
    assert response.git_initialized is True
    assert response.git_cloned is False
    assert response.recommended_next_tools == ["list_projects", "project_snapshot"]


def test_ensure_agent_env_gitignore_is_idempotent(tmp_path: Path) -> None:
    project_root = tmp_path / "demo-project"
    project_root.mkdir()
    gitignore_path = project_root / ".gitignore"
    gitignore_path.write_text(".venv/\n.devworkspace/agent.env\n", encoding="utf-8")

    returned_path = ensure_agent_env_gitignore(project_root)
    ensure_agent_env_gitignore(project_root)

    assert returned_path == gitignore_path
    assert gitignore_path.read_text(encoding="utf-8").splitlines() == [
        ".venv/",
        ".devworkspace/agent.env",
        ".devworkspace/.agent.env.*.tmp",
    ]


def test_ensure_agent_env_gitignore_preserves_existing_position_and_comments(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "demo-project"
    project_root.mkdir()
    gitignore_path = project_root / ".gitignore"
    gitignore_path.write_text(
        "# local secrets\n"
        ".devworkspace/agent.env\n"
        ".devworkspace/.agent.env.*.tmp\n"
        ".venv/\n"
        ".devworkspace/agent.env\n",
        encoding="utf-8",
    )

    ensure_agent_env_gitignore(project_root)

    assert gitignore_path.read_text(encoding="utf-8").splitlines() == [
        "# local secrets",
        ".devworkspace/agent.env",
        ".devworkspace/.agent.env.*.tmp",
        ".venv/",
    ]


def test_bootstrap_create_mode_creates_discoverable_project(workspace_root: Path) -> None:
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    service = ProjectBootstrapService(registry)

    response = service.bootstrap_project(
        BootstrapProjectRequest(
            mode="create",
            folder_name="demo-project",
            display_name="Demo Project",
            git_init=True,
        )
    )

    project_root = workspace_root / "demo-project"

    assert response.project_id == "demo-project"
    assert response.root_path == str(project_root.resolve())
    assert response.git_initialized is True
    assert response.git_cloned is False
    assert set(response.created_files) >= {
        ".devworkspace.yaml",
        ".devworkspace/memory.md",
        ".devworkspace/tasks.md",
        ".devworkspace/roadmap.md",
        ".devworkspace/policy.yaml",
        ".gitignore",
    }

    manifest = load_manifest(project_root)
    assert manifest.project_id == "demo-project"
    assert manifest.name == "Demo Project"
    assert registry.require("demo-project").root_path == str(project_root.resolve())
    assert (project_root / ".git").exists()
    assert (project_root / ".gitignore").read_text(encoding="utf-8").splitlines() == [
        ".devworkspace/agent.env",
        ".devworkspace/.agent.env.*.tmp",
    ]



def test_bootstrap_import_leaves_existing_files_alone_and_scaffolds_missing_files(
    workspace_root: Path,
) -> None:
    project_root = workspace_root / "import-me"
    project_root.mkdir()
    (project_root / ".devworkspace").mkdir()
    (project_root / ".devworkspace.yaml").write_text(
        "name: Existing Name\nproject_id: existing-id\naliases:\n  - existing\n",
        encoding="utf-8",
    )
    memory_path = project_root / ".devworkspace" / "memory.md"
    memory_path.write_text("keep this memory\n", encoding="utf-8")

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    service = ProjectBootstrapService(registry)

    response = service.bootstrap_project(
        BootstrapProjectRequest(
            mode="import",
            path=str(project_root),
            project_id="ignored-id",
            display_name="Ignored Display Name",
        )
    )

    assert response.project_id == "existing-id"
    assert memory_path.read_text(encoding="utf-8") == "keep this memory\n"
    assert set(response.created_files) >= {
        ".devworkspace/tasks.md",
        ".devworkspace/roadmap.md",
        ".devworkspace/policy.yaml",
        ".gitignore",
    }
    assert not any(path == ".devworkspace/memory.md" for path in response.created_files)
    assert any("project_id" in warning for warning in response.warnings)
    assert any("name" in warning for warning in response.warnings)

    manifest = load_manifest(project_root)
    assert manifest.project_id == "existing-id"
    assert manifest.name == "Existing Name"
    assert registry.require("existing-id").root_path == str(project_root.resolve())
    assert (project_root / ".devworkspace" / "tasks.md").exists()
    assert (project_root / ".devworkspace" / "roadmap.md").exists()
    assert (project_root / ".devworkspace" / "policy.yaml").exists()



def test_bootstrap_clone_mode_clones_local_repo_and_checks_out_branch(
    tmp_path: Path,
    workspace_root: Path,
) -> None:
    source_repo = tmp_path / "source-repo"
    source_repo.mkdir()
    subprocess.run(["git", "init", str(source_repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(source_repo), "config", "user.name", "Test User"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    (source_repo / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(source_repo), "add", "README.md"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "checkout", "-b", "feature/demo"],
        check=True,
        capture_output=True,
    )
    (source_repo / "feature.txt").write_text("feature branch\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(source_repo), "add", "feature.txt"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "commit", "-m", "feature"],
        check=True,
        capture_output=True,
    )

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    service = ProjectBootstrapService(registry)

    response = service.bootstrap_project(
        BootstrapProjectRequest(
            mode="clone",
            repo_url=str(source_repo),
            branch="feature/demo",
            display_name="Cloned Project",
        )
    )

    project_root = workspace_root / "source-repo"
    branch_name = subprocess.run(
        ["git", "-C", str(project_root), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert response.project_id == "source-repo"
    assert response.root_path == str(project_root.resolve())
    assert response.git_cloned is True
    assert response.git_initialized is False
    assert branch_name == "feature/demo"
    assert (project_root / "feature.txt").read_text(encoding="utf-8") == "feature branch\n"
    assert (project_root / ".devworkspace.yaml").exists()
    assert (project_root / ".devworkspace" / "memory.md").exists()
    assert registry.require("source-repo").root_path == str(project_root.resolve())


def test_bootstrap_rejects_blank_project_id_cleanly(workspace_root: Path) -> None:
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    service = ProjectBootstrapService(registry)

    with pytest.raises(DomainError) as exc:
        service.bootstrap_project(
            BootstrapProjectRequest(
                mode="create",
                folder_name="invalid-project",
                project_id="   ",
            )
        )

    assert exc.value.code == ErrorCode.INVALID_PROJECT_ID



def test_bootstrap_import_rejects_conflicting_manifest_project_id_before_mutation(
    workspace_root: Path,
    make_manifest_project,
) -> None:
    make_manifest_project(name="taken-project", project_id="taken-id")
    project_root = workspace_root / "import-me"
    project_root.mkdir()
    (project_root / ".devworkspace").mkdir()
    (project_root / ".devworkspace.yaml").write_text(
        "project_id: taken-id\n",
        encoding="utf-8",
    )

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    service = ProjectBootstrapService(registry)

    with pytest.raises(DomainError) as exc:
        service.bootstrap_project(BootstrapProjectRequest(mode="import", path=str(project_root)))

    assert exc.value.code == ErrorCode.PROJECT_CONFLICT
    assert not (project_root / ".gitignore").exists()
    assert not (project_root / ".devworkspace" / "tasks.md").exists()


def test_bootstrap_clone_rejects_conflicting_manifest_project_id_without_leaving_clone(
    tmp_path: Path,
    workspace_root: Path,
    make_manifest_project,
) -> None:
    make_manifest_project(name="taken-project", project_id="taken-id")
    source_repo = tmp_path / "source-repo"
    source_repo.mkdir()
    subprocess.run(["git", "init", str(source_repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(source_repo), "config", "user.name", "Test User"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    (source_repo / ".devworkspace.yaml").write_text("project_id: taken-id\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(source_repo), "add", ".devworkspace.yaml"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "commit", "-m", "manifest"],
        check=True,
        capture_output=True,
    )

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    service = ProjectBootstrapService(registry)

    with pytest.raises(DomainError) as exc:
        service.bootstrap_project(
            BootstrapProjectRequest(mode="clone", repo_url=str(source_repo))
        )

    assert exc.value.code == ErrorCode.PROJECT_CONFLICT
    assert not (workspace_root / "source-repo").exists()


def test_bootstrap_import_rejects_paths_outside_workspace_roots(
    tmp_path: Path,
    workspace_root: Path,
) -> None:
    outside_root = tmp_path / "outside-root"
    outside_root.mkdir()

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    service = ProjectBootstrapService(registry)

    with pytest.raises(DomainError) as exc:
        service.bootstrap_project(
            BootstrapProjectRequest(mode="import", path=str(outside_root))
        )

    assert exc.value.code == ErrorCode.PATH_OUTSIDE_PROJECT


def test_bootstrap_import_rejects_nested_undiscoverable_path(
    workspace_root: Path,
) -> None:
    nested_root = workspace_root / "parent" / "child"
    nested_root.mkdir(parents=True)

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    service = ProjectBootstrapService(registry)

    with pytest.raises(DomainError) as exc:
        service.bootstrap_project(
            BootstrapProjectRequest(mode="import", path=str(nested_root))
        )

    assert exc.value.code == ErrorCode.INVALID_PATH



def test_bootstrap_rejects_duplicate_project_id_before_mutation(
    workspace_root: Path,
    make_manifest_project,
) -> None:
    make_manifest_project(project_id="taken-id")
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    service = ProjectBootstrapService(registry)

    with pytest.raises(DomainError) as exc:
        service.bootstrap_project(
            BootstrapProjectRequest(
                mode="create",
                folder_name="new-project",
                project_id="taken-id",
            )
        )

    assert exc.value.code == ErrorCode.PROJECT_CONFLICT
    assert not (workspace_root / "new-project").exists()


def test_bootstrap_redacts_credentials_from_git_clone_failures(
    monkeypatch: pytest.MonkeyPatch,
    workspace_root: Path,
) -> None:
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    service = ProjectBootstrapService(registry)
    repo_url = "https://user:super-secret-token@example.com/private/repo.git"

    def _fake_run(command, capture_output, text, check):
        return SimpleNamespace(
            returncode=1,
            stdout="cloning from https://user:super-secret-token@example.com/private/repo.git",
            stderr="fatal: could not read from https://user:super-secret-token@example.com/private/repo.git",
        )

    monkeypatch.setattr("dev_workspace_mcp.projects.bootstrap.subprocess.run", _fake_run)

    with pytest.raises(DomainError) as exc:
        service.bootstrap_project(
            BootstrapProjectRequest(mode="clone", repo_url=repo_url)
        )

    assert exc.value.code == ErrorCode.BOOTSTRAP_FAILED
    assert "super-secret-token" not in exc.value.message
    assert "super-secret-token" not in (exc.value.hint or "")
    assert "super-secret-token" not in str(exc.value.details)


def test_bootstrap_clone_rejects_repo_url_that_looks_like_git_option(
    workspace_root: Path,
) -> None:
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    service = ProjectBootstrapService(registry)

    with pytest.raises(DomainError) as exc:
        service.bootstrap_project(
            BootstrapProjectRequest(mode="clone", repo_url="--help")
        )

    assert exc.value.code == ErrorCode.BOOTSTRAP_FAILED
    assert not (workspace_root / "--help").exists()


def test_bootstrap_create_rejects_hidden_folder_name(
    workspace_root: Path,
) -> None:
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    service = ProjectBootstrapService(registry)

    with pytest.raises(DomainError) as exc:
        service.bootstrap_project(
            BootstrapProjectRequest(mode="create", folder_name=".hidden")
        )

    assert exc.value.code == ErrorCode.INVALID_PATH
    assert not (workspace_root / ".hidden").exists()
