from __future__ import annotations

from pathlib import Path
from typing import Protocol

from dev_workspace_mcp.codegraph.adapters import InProcessCodegraphProvider
from dev_workspace_mcp.codegraph.models import CodegraphIndexSnapshot
from dev_workspace_mcp.models.codegraph import (
    CallPathResponse,
    FunctionContextResponse,
    GrepResponse,
    ModuleOverviewResponse,
    SourceReadResponse,
)


class CodegraphProvider(Protocol):
    def module_overview(self, project_root: Path, path: str) -> ModuleOverviewResponse: ...

    def function_context(
        self,
        project_root: Path,
        symbol: str,
        *,
        path: str | None = None,
        watched_paths: list[str] | None = None,
    ) -> FunctionContextResponse: ...

    def grep(
        self,
        project_root: Path,
        pattern: str,
        *,
        path: str | None = None,
        watched_paths: list[str] | None = None,
        ignore_case: bool = False,
    ) -> GrepResponse: ...

    def find_references(
        self,
        project_root: Path,
        symbol: str,
        *,
        path: str | None = None,
        watched_paths: list[str] | None = None,
    ) -> GrepResponse: ...

    def call_path(
        self,
        project_root: Path,
        symbol: str,
        *,
        path: str | None = None,
        watched_paths: list[str] | None = None,
    ) -> CallPathResponse: ...

    def read_source(
        self,
        project_root: Path,
        path: str,
        *,
        start_line: int = 1,
        end_line: int | None = None,
    ) -> SourceReadResponse: ...

    def build_index_snapshot(
        self,
        project_id: str,
        project_root: Path,
        *,
        watched_paths: list[str] | None = None,
    ) -> CodegraphIndexSnapshot: ...


def build_codegraph_provider(
    *,
    max_matches: int,
    max_source_chars: int,
) -> CodegraphProvider:
    return InProcessCodegraphProvider(
        max_matches=max_matches,
        max_source_chars=max_source_chars,
    )


__all__ = ["CodegraphProvider", "build_codegraph_provider"]
