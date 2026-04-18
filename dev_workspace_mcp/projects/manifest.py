from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.models.projects import ProjectManifest

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
