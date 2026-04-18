from __future__ import annotations

from functools import cached_property
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEV_WORKSPACE_MCP_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8081
    workspace_roots: list[str] = Field(default_factory=lambda: ["~/dev-workspaces"])
    command_policy: str = "policy"
    codegraph_max_matches: int = 200
    codegraph_max_source_chars: int = 20_000
    default_log_tail_lines: int = 120
    max_read_bytes: int = 200_000
    max_log_bytes: int = 200_000

    @cached_property
    def expanded_workspace_roots(self) -> list[Path]:
        return [Path(root).expanduser().resolve() for root in self.workspace_roots]


def get_settings() -> Settings:
    return Settings()
