from __future__ import annotations

import pytest

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.projects.registry import ProjectRegistry


def _write_policy(project_root, lines: list[str]) -> None:
    policy_dir = project_root / ".devworkspace"
    policy_dir.mkdir(exist_ok=True)
    (policy_dir / "policy.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_settings_can_be_instantiated(tmp_path) -> None:
    settings = Settings(workspace_roots=[str(tmp_path)])

    assert settings.host == "127.0.0.1"
    assert settings.port == 8081
    assert settings.command_policy == "policy"
    assert settings.expanded_workspace_roots == [tmp_path.resolve()]


def test_project_registry_loads_safe_default_policy_when_policy_file_is_missing(
    workspace_root,
    make_manifest_project,
) -> None:
    make_manifest_project()
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))

    registry.refresh()

    policy = registry.require("manifest-id").policy
    assert policy.env.inherit is False
    assert policy.command_policy.default == "deny"
    assert policy.command_policy.commands == {}
    assert policy.network.default == "deny"
    assert policy.network.allow_localhost is True


def test_project_registry_refresh_raises_structured_policy_invalid_error(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    _write_policy(
        project_root,
        [
            "command_policy:",
            "  commands:",
            "    echo:",
            "      max_seconds: nope",
        ],
    )
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))

    with pytest.raises(DomainError) as exc_info:
        registry.refresh()

    assert exc_info.value.code == ErrorCode.POLICY_INVALID
    assert exc_info.value.details["policy_path"].endswith(".devworkspace/policy.yaml")
