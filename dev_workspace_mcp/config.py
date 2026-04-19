from __future__ import annotations

from functools import cached_property
from ipaddress import ip_address
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_HTTP_HOSTNAMES = frozenset({"localhost"})


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
    max_command_output_bytes: int = 200_000
    max_log_bytes: int = 200_000
    subprocess_stream_chunk_bytes: int = 4096

    @cached_property
    def expanded_workspace_roots(self) -> list[Path]:
        return [Path(root).expanduser().resolve() for root in self.workspace_roots]


def normalize_http_host(host: str) -> str:
    normalized = host.strip().lower()
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    return normalized


def is_local_http_host(host: str) -> bool:
    normalized = normalize_http_host(host)
    if normalized in LOCAL_HTTP_HOSTNAMES:
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def build_public_bind_warning(*, host: str, port: int, path: str) -> str:
    return "\n".join(
        (
            "WARNING: --allow-public-bind is enabled.",
            (
                "WARNING: Binding dev-workspace-mcp HTTP on "
                f"http://{host}:{port}{path} exposes it to non-local clients."
            ),
            "WARNING: This transport is only hardened for trusted local use.",
        )
    )


def get_settings() -> Settings:
    return Settings()
