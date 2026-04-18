from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.models.projects import ProjectManifest
from dev_workspace_mcp.shared.env_files import write_text_atomic

MANIFEST_NAME = ".devworkspace.yaml"


def manifest_path_for(project_root: Path) -> Path:
    return project_root / MANIFEST_NAME


def load_manifest(project_root: Path) -> ProjectManifest:
    manifest_path = manifest_path_for(project_root)
    if not manifest_path.exists():
        return ProjectManifest()

    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        return ProjectManifest.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise DomainError(
            code=ErrorCode.MANIFEST_INVALID,
            message=f"Failed to parse manifest for {project_root.name}.",
            hint="Fix .devworkspace.yaml so project discovery can continue cleanly.",
            details={"manifest_path": str(manifest_path), "error": str(exc)},
        ) from exc


def write_manifest(project_root: Path, manifest: ProjectManifest) -> Path:
    manifest_path = manifest_path_for(project_root)
    payload = manifest.model_dump(mode="python", exclude_none=True)

    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        rendered = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
        write_text_atomic(manifest_path, rendered)
    except (OSError, yaml.YAMLError) as exc:
        raise DomainError(
            code=ErrorCode.MANIFEST_INVALID,
            message=f"Failed to write manifest for {project_root.name}.",
            hint="Check filesystem permissions and manifest contents, then try again.",
            details={"manifest_path": str(manifest_path), "error": str(exc)},
        ) from exc

    return manifest_path


def update_manifest(
    project_root: Path,
    updater: Callable[[ProjectManifest], ProjectManifest | dict[str, Any] | None],
) -> ProjectManifest:
    current = load_manifest(project_root)

    try:
        updated = updater(current)
        if updated is None:
            manifest = current
        elif isinstance(updated, ProjectManifest):
            manifest = updated
        else:
            manifest = ProjectManifest.model_validate(updated)
    except (TypeError, ValidationError) as exc:
        raise DomainError(
            code=ErrorCode.MANIFEST_INVALID,
            message=f"Failed to update manifest for {project_root.name}.",
            hint="Return a valid ProjectManifest payload from the manifest updater.",
            details={"manifest_path": str(manifest_path_for(project_root)), "error": str(exc)},
        ) from exc

    write_manifest(project_root, manifest)
    return manifest


__all__ = [
    "MANIFEST_NAME",
    "load_manifest",
    "manifest_path_for",
    "update_manifest",
    "write_manifest",
]
