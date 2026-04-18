from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.policy.models import ProjectPolicy

POLICY_PATH = Path(".devworkspace/policy.yaml")


def policy_path_for(project_root: Path) -> Path:
    return Path(project_root) / POLICY_PATH


def load_project_policy(project_root: Path) -> ProjectPolicy:
    path = policy_path_for(project_root)
    if not path.exists():
        return ProjectPolicy()

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return ProjectPolicy.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise DomainError(
            code=ErrorCode.POLICY_INVALID,
            message=f"Failed to parse policy for {Path(project_root).name}.",
            hint="Fix .devworkspace/policy.yaml so project policy can load cleanly.",
            details={"policy_path": str(path), "error": str(exc)},
        ) from exc


__all__ = ["POLICY_PATH", "load_project_policy", "policy_path_for"]
