from __future__ import annotations

from dev_workspace_mcp.config import Settings


def test_settings_can_be_instantiated(tmp_path) -> None:
    settings = Settings(workspace_roots=[str(tmp_path)])

    assert settings.host == "127.0.0.1"
    assert settings.port == 8081
    assert settings.expanded_workspace_roots == [tmp_path.resolve()]
