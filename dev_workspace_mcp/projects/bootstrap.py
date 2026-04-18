from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path, PurePath
from urllib.parse import urlparse

from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.models.project_bootstrap import (
    BootstrapProjectRequest,
    BootstrapProjectResponse,
)
from dev_workspace_mcp.models.projects import ProjectManifest
from dev_workspace_mcp.projects.manifest import (
    load_manifest,
    manifest_path_for,
    write_manifest,
)
from dev_workspace_mcp.projects.registry import ProjectRegistry
from dev_workspace_mcp.shared.env_files import ensure_agent_env_gitignore, write_text_atomic

_DEFAULT_STATE_DOCS: dict[str, str] = {
    ".devworkspace/memory.md": "# Memory\n",
    ".devworkspace/tasks.md": "# Tasks\n\n## Active\n",
    ".devworkspace/roadmap.md": "# Roadmap\n",
    ".devworkspace/policy.yaml": "version: 1\n",
}
_URL_CREDENTIAL_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)([^/\s@]+@)")
_DEFAULT_RECOMMENDED_NEXT_TOOLS = ["list_projects", "project_snapshot"]


class ProjectBootstrapService:
    def __init__(self, project_registry: ProjectRegistry) -> None:
        self.project_registry = project_registry

    def bootstrap_project(self, request: BootstrapProjectRequest) -> BootstrapProjectResponse:
        self.project_registry.refresh()

        if request.mode == "create":
            result = self._bootstrap_create(request)
        elif request.mode == "clone":
            result = self._bootstrap_clone(request)
        else:
            result = self._bootstrap_import(request)

        self.project_registry.refresh()
        record = self.project_registry.require(result["project_id"])
        return BootstrapProjectResponse(
            project_id=record.project_id,
            root_path=record.root_path,
            manifest_path=str(manifest_path_for(Path(record.root_path))),
            created_files=result["created_files"],
            git_initialized=result["git_initialized"],
            git_cloned=result["git_cloned"],
            warnings=result["warnings"],
            recommended_next_tools=list(_DEFAULT_RECOMMENDED_NEXT_TOOLS),
        )

    def _bootstrap_create(self, request: BootstrapProjectRequest) -> dict[str, object]:
        workspace_root = self._default_workspace_root()
        folder_name = self._validate_folder_name(request.folder_name or "")
        project_root = workspace_root / folder_name
        project_id = self._resolve_requested_project_id(request.project_id, folder_name)

        self._ensure_project_id_available(project_id, project_root)
        if project_root.exists():
            raise DomainError(
                code=ErrorCode.BOOTSTRAP_FAILED,
                message=f"Target project folder already exists: {project_root}",
                hint="Choose a new folder name or import the existing path instead.",
            )

        try:
            project_root.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise DomainError(
                code=ErrorCode.BOOTSTRAP_FAILED,
                message=f"Failed to create project folder: {project_root}",
                hint="Check filesystem permissions and workspace root settings, then try again.",
                details={"root_path": str(project_root), "error": str(exc)},
            ) from exc

        git_initialized = False
        if request.git_init:
            self._run_git(["init", str(project_root)], root_path=project_root)
            git_initialized = True

        created_files: list[str] = []
        warnings: list[str] = []
        final_project_id = self._scaffold_project(
            project_root,
            project_id=project_id,
            display_name=request.display_name,
            created_files=created_files,
            warnings=warnings,
        )
        return {
            "project_id": final_project_id,
            "created_files": created_files,
            "git_initialized": git_initialized,
            "git_cloned": False,
            "warnings": warnings,
        }

    def _bootstrap_clone(self, request: BootstrapProjectRequest) -> dict[str, object]:
        workspace_root = self._default_workspace_root()
        repo_url = self._validate_clone_repo_url(request.repo_url or "")
        folder_name = self._clone_folder_name(repo_url)
        project_root = workspace_root / folder_name
        requested_project_id = self._resolve_requested_project_id(request.project_id, folder_name)

        self._ensure_project_id_available(requested_project_id, project_root)
        if project_root.exists():
            raise DomainError(
                code=ErrorCode.BOOTSTRAP_FAILED,
                message=f"Clone destination already exists: {project_root}",
                hint="Choose a different workspace root entry or import the existing path instead.",
            )

        clone_command = ["clone"]
        if request.branch:
            clone_command.extend(["--branch", request.branch, "--single-branch"])
        clone_command.extend(["--", repo_url, str(project_root)])
        self._run_git(clone_command, root_path=project_root)
        if not (project_root / ".git").exists():
            shutil.rmtree(project_root, ignore_errors=True)
            raise DomainError(
                code=ErrorCode.BOOTSTRAP_FAILED,
                message=f"Git clone did not produce a repository at {project_root}",
                hint="Check the repository URL and git clone behavior, then try again.",
                details={"root_path": str(project_root)},
            )

        try:
            final_candidate_project_id = self._candidate_project_id(
                project_root,
                requested_project_id=requested_project_id,
            )
            self._ensure_project_id_available(final_candidate_project_id, project_root)

            created_files: list[str] = []
            warnings: list[str] = []
            final_project_id = self._scaffold_project(
                project_root,
                project_id=requested_project_id,
                display_name=request.display_name,
                created_files=created_files,
                warnings=warnings,
            )
        except Exception:
            shutil.rmtree(project_root, ignore_errors=True)
            raise
        return {
            "project_id": final_project_id,
            "created_files": created_files,
            "git_initialized": False,
            "git_cloned": True,
            "warnings": warnings,
        }

    def _bootstrap_import(self, request: BootstrapProjectRequest) -> dict[str, object]:
        project_root = Path(request.path or "").expanduser().resolve()
        if not project_root.exists():
            raise DomainError(
                code=ErrorCode.PATH_NOT_FOUND,
                message=f"Import path does not exist: {project_root}",
                hint="Create or clone the project first, then import it.",
            )
        if not project_root.is_dir():
            raise DomainError(
                code=ErrorCode.INVALID_PATH,
                message=f"Import path is not a directory: {project_root}",
                hint="Provide the project root directory path.",
            )
        self._ensure_path_within_workspace_roots(project_root)
        self._ensure_path_is_discoverable(project_root)

        requested_project_id = self._resolve_requested_project_id(
            request.project_id,
            project_root.name,
        )
        final_candidate_project_id = self._candidate_project_id(
            project_root,
            requested_project_id=requested_project_id,
        )
        self._ensure_project_id_available(final_candidate_project_id, project_root)

        created_files: list[str] = []
        warnings: list[str] = []
        final_project_id = self._scaffold_project(
            project_root,
            project_id=requested_project_id,
            display_name=request.display_name,
            created_files=created_files,
            warnings=warnings,
        )
        return {
            "project_id": final_project_id,
            "created_files": created_files,
            "git_initialized": False,
            "git_cloned": False,
            "warnings": warnings,
        }

    def _scaffold_project(
        self,
        project_root: Path,
        *,
        project_id: str,
        display_name: str | None,
        created_files: list[str],
        warnings: list[str],
    ) -> str:
        manifest_path = manifest_path_for(project_root)
        manifest_exists = manifest_path.exists()
        manifest = load_manifest(project_root)
        updated_manifest = self._merged_manifest(
            manifest,
            project_id=project_id,
            display_name=display_name,
            warnings=warnings,
        )
        if not manifest_exists:
            write_manifest(project_root, updated_manifest)
            created_files.append(manifest_path.name)
        elif updated_manifest != manifest:
            write_manifest(project_root, updated_manifest)

        for relative_path, content in _DEFAULT_STATE_DOCS.items():
            path = project_root / relative_path
            if path.exists():
                continue
            write_text_atomic(path, content)
            created_files.append(relative_path)

        gitignore_path = project_root / ".gitignore"
        gitignore_existed = gitignore_path.exists()
        ensure_agent_env_gitignore(project_root)
        if not gitignore_existed:
            created_files.append(gitignore_path.name)

        final_manifest = load_manifest(project_root)
        final_project_id = (final_manifest.project_id or project_root.name).strip()
        if not final_project_id:
            raise DomainError(
                code=ErrorCode.INVALID_PROJECT_ID,
                message=f"Project at {project_root} resolved to an empty project_id.",
                hint="Set a non-empty project_id in .devworkspace.yaml or rename the folder.",
            )
        return final_project_id

    def _merged_manifest(
        self,
        manifest: ProjectManifest,
        *,
        project_id: str,
        display_name: str | None,
        warnings: list[str],
    ) -> ProjectManifest:
        final_manifest = manifest.model_copy(deep=True)

        if final_manifest.project_id:
            if final_manifest.project_id != project_id:
                warnings.append(
                    "Manifest project_id already exists; kept the existing "
                    "value instead of overwriting it."
                )
        else:
            final_manifest.project_id = project_id

        normalized_display_name = (display_name or "").strip() or None
        if final_manifest.name:
            if normalized_display_name and final_manifest.name != normalized_display_name:
                warnings.append(
                    "Manifest name already exists; kept the existing value "
                    "instead of overwriting it."
                )
        elif normalized_display_name:
            final_manifest.name = normalized_display_name

        return final_manifest

    def _default_workspace_root(self) -> Path:
        roots = self.project_registry.settings.expanded_workspace_roots
        if not roots:
            raise DomainError(
                code=ErrorCode.BOOTSTRAP_FAILED,
                message="No workspace roots are configured.",
                hint="Set DEV_WORKSPACE_MCP_WORKSPACE_ROOTS before bootstrapping a project.",
            )
        workspace_root = roots[0]
        try:
            workspace_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DomainError(
                code=ErrorCode.BOOTSTRAP_FAILED,
                message=f"Failed to prepare workspace root: {workspace_root}",
                hint="Check filesystem permissions and workspace root settings, then try again.",
                details={"workspace_root": str(workspace_root), "error": str(exc)},
            ) from exc
        return workspace_root

    def _validate_folder_name(self, folder_name: str) -> str:
        normalized = folder_name.strip()
        candidate = PurePath(normalized)
        if (
            not normalized
            or normalized.startswith(".")
            or normalized in {".", ".."}
            or candidate.name != normalized
            or len(candidate.parts) != 1
        ):
            raise DomainError(
                code=ErrorCode.INVALID_PATH,
                message=f"Invalid project folder name: {folder_name!r}",
                hint="Use a single folder name, not a nested or empty path.",
            )
        return normalized

    def _resolve_requested_project_id(
        self,
        requested_project_id: str | None,
        folder_name: str,
    ) -> str:
        raw_project_id = (
            requested_project_id if requested_project_id is not None else folder_name
        )
        project_id = raw_project_id.strip()
        if not project_id:
            raise DomainError(
                code=ErrorCode.INVALID_PROJECT_ID,
                message="Project bootstrap resolved to an empty project_id.",
                hint="Pass a non-empty project_id or use a non-empty target folder name.",
            )
        return project_id

    def _candidate_project_id(
        self,
        project_root: Path,
        *,
        requested_project_id: str,
    ) -> str:
        manifest = load_manifest(project_root)
        project_id = (manifest.project_id or requested_project_id).strip()
        if not project_id:
            raise DomainError(
                code=ErrorCode.INVALID_PROJECT_ID,
                message=f"Project at {project_root} resolved to an empty project_id.",
                hint="Set a non-empty project_id in .devworkspace.yaml or rename the folder.",
            )
        return project_id

    def _ensure_project_id_available(self, project_id: str, project_root: Path) -> None:
        existing = self.project_registry.get(project_id)
        if existing is None:
            return
        if Path(existing.root_path).resolve() == project_root.resolve():
            return
        raise DomainError(
            code=ErrorCode.PROJECT_CONFLICT,
            message=f"Project_id is already in use: {project_id}",
            hint="Choose a unique project_id or import the existing project instead.",
            details={
                "project_id": project_id,
                "existing_root": existing.root_path,
                "requested_root": str(project_root.resolve()),
            },
        )

    def _ensure_path_within_workspace_roots(self, project_root: Path) -> None:
        for workspace_root in self.project_registry.settings.expanded_workspace_roots:
            if self._is_relative_to(project_root, workspace_root):
                return
        raise DomainError(
            code=ErrorCode.PATH_OUTSIDE_PROJECT,
            message=f"Import path is outside the configured workspace roots: {project_root}",
            hint="Move the project under a configured workspace root before importing it.",
            details={"path": str(project_root)},
        )

    def _ensure_path_is_discoverable(self, project_root: Path) -> None:
        for workspace_root in self.project_registry.settings.expanded_workspace_roots:
            if project_root == workspace_root:
                return
            if project_root.parent == workspace_root and not project_root.name.startswith("."):
                return
        raise DomainError(
            code=ErrorCode.INVALID_PATH,
            message=(
                "Import path is not discoverable under current workspace root rules: "
                f"{project_root}"
            ),
            hint=(
                "Import the workspace root itself or an immediate non-hidden "
                "child directory under it."
            ),
            details={"path": str(project_root)},
        )

    def _clone_folder_name(self, repo_url: str) -> str:
        parsed = urlparse(repo_url)
        raw_path = parsed.path if parsed.scheme else repo_url
        folder_name = PurePath(raw_path).name or PurePath(repo_url.split(":")[-1]).name
        if folder_name.endswith(".git"):
            folder_name = folder_name[:-4]
        return self._validate_folder_name(folder_name)

    def _validate_clone_repo_url(self, repo_url: str) -> str:
        normalized = repo_url.strip()
        if not normalized:
            raise DomainError(
                code=ErrorCode.BOOTSTRAP_FAILED,
                message="Clone mode requires a repository URL.",
                hint="Pass a repository URL or local repository path to clone.",
            )
        if normalized.startswith("-"):
            raise DomainError(
                code=ErrorCode.BOOTSTRAP_FAILED,
                message=f"Invalid clone repository URL: {repo_url!r}",
                hint="Repository URLs or local paths must not start with '-'.",
            )
        return normalized

    def _run_git(self, args: list[str], *, root_path: Path) -> None:
        command = ["git", *args]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            raise DomainError(
                code=ErrorCode.GIT_NOT_AVAILABLE,
                message="Git is not available on PATH.",
                hint="Install git or adjust PATH before using bootstrap create/clone flows.",
            ) from exc
        if result.returncode == 0:
            return
        redacted_command = [self._redact_clone_secrets(part) for part in command]
        redacted_stdout = self._redact_clone_secrets(result.stdout.strip())
        redacted_stderr = self._redact_clone_secrets(result.stderr.strip())
        raise DomainError(
            code=ErrorCode.BOOTSTRAP_FAILED,
            message=f"Git command failed for {root_path.name}: {' '.join(redacted_command)}",
            hint=(
                redacted_stderr
                or redacted_stdout
                or "Check the repository URL and filesystem state, then try again."
            ).strip(),
            details={
                "root_path": str(root_path),
                "command": redacted_command,
                "stdout": redacted_stdout,
                "stderr": redacted_stderr,
                "exit_code": result.returncode,
            },
        )

    @staticmethod
    def _redact_clone_secrets(value: str) -> str:
        return _URL_CREDENTIAL_RE.sub(r"\1[REDACTED]@", value)

    @staticmethod
    def _is_relative_to(path: Path, other: Path) -> bool:
        try:
            path.relative_to(other)
        except ValueError:
            return False
        return True


__all__ = ["ProjectBootstrapService"]
