from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dev_workspace_mcp.codegraph.adapters import InProcessCodegraphProvider
from dev_workspace_mcp.codegraph.index_manager import CodegraphIndexManager
from dev_workspace_mcp.codegraph.models import CodegraphEdge, CodegraphIndexSnapshot, CodegraphNode
from dev_workspace_mcp.codegraph.providers import build_codegraph_provider
from dev_workspace_mcp.codegraph.service import CodegraphService
from dev_workspace_mcp.codegraph.watcher_manager import CodegraphWatcherManager
from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.models.codegraph import (
    CallPathNode,
    CallPathResponse,
    FunctionContextResponse,
    GrepResponse,
    SymbolContextMatch,
)
from dev_workspace_mcp.projects.registry import ProjectRegistry


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.find_reference_calls: list[dict[str, object]] = []
        self.call_path_calls: list[dict[str, object]] = []
        self.build_snapshot_calls: list[dict[str, object]] = []

    def function_context(
        self,
        project_root: Path,
        symbol: str,
        *,
        path: str | None = None,
        watched_paths: list[str] | None = None,
    ) -> FunctionContextResponse:
        self.calls.append(
            {
                "project_root": project_root,
                "symbol": symbol,
                "path": path,
                "watched_paths": list(watched_paths or []),
            }
        )
        return FunctionContextResponse(
            symbol=symbol,
            matches=[
                SymbolContextMatch(
                    name=symbol,
                    kind="function",
                    path="src/example.py",
                    line_start=1,
                    line_end=2,
                    signature=f"def {symbol}():",
                    source=f"def {symbol}():\n    return 1",
                )
            ],
        )

    def find_references(
        self,
        project_root: Path,
        symbol: str,
        *,
        path: str | None = None,
        watched_paths: list[str] | None = None,
    ) -> GrepResponse:
        self.find_reference_calls.append(
            {
                "project_root": project_root,
                "symbol": symbol,
                "path": path,
                "watched_paths": list(watched_paths or []),
            }
        )
        return GrepResponse(pattern=symbol)

    def call_path(
        self,
        project_root: Path,
        symbol: str,
        *,
        path: str | None = None,
        watched_paths: list[str] | None = None,
    ) -> CallPathResponse:
        self.call_path_calls.append(
            {
                "project_root": project_root,
                "symbol": symbol,
                "path": path,
                "watched_paths": list(watched_paths or []),
            }
        )
        return CallPathResponse(
            symbol=symbol,
            definition=CallPathNode(
                symbol=symbol,
                kind="function",
                path="src/example.py",
                line_start=1,
                line_end=2,
            ),
        )

    def build_index_snapshot(
        self,
        project_id: str,
        project_root: Path,
        *,
        watched_paths: list[str] | None = None,
    ) -> CodegraphIndexSnapshot:
        build_number = len(self.build_snapshot_calls) + 1
        self.build_snapshot_calls.append(
            {
                "project_id": project_id,
                "project_root": project_root,
                "watched_paths": list(watched_paths or []),
            }
        )
        return CodegraphIndexSnapshot(
            project_id=project_id,
            revision=f"snapshot-rev-{build_number}",
            indexed_at=datetime(2026, 4, 9, 20, build_number, tzinfo=UTC),
            file_count=1,
            symbol_count=2,
            nodes=[
                CodegraphNode(
                    identifier="src/example.py:helper",
                    name="helper",
                    kind="function",
                    path="src/example.py",
                    line_start=4,
                    line_end=5,
                    signature="def helper():",
                    source=f"def helper():\n    return {build_number}",
                ),
                CodegraphNode(
                    identifier="src/example.py:caller",
                    name="caller",
                    kind="function",
                    path="src/example.py",
                    line_start=1,
                    line_end=2,
                    signature="def caller():",
                    source="def caller():\n    return helper()",
                ),
            ],
            edges=[
                CodegraphEdge(
                    source="src/example.py:caller",
                    target="src/example.py:helper",
                    relation="calls",
                    path="src/example.py",
                    line_number=2,
                    line_text="    return helper()",
                )
            ],
        )



def test_build_codegraph_provider_returns_in_process_provider() -> None:
    provider = build_codegraph_provider(max_matches=10, max_source_chars=500)

    assert isinstance(provider, InProcessCodegraphProvider)
    assert provider.max_matches == 10
    assert provider.max_source_chars == 500



def test_settings_do_not_expose_runtime_codegraph_provider_switch() -> None:
    assert "codegraph_provider" not in Settings.model_fields



def test_codegraph_service_falls_back_to_provider_when_snapshot_has_no_symbol_match(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    provider = FakeProvider()
    service = CodegraphService(
        project_registry=registry,
        watcher_manager=CodegraphWatcherManager(),
        index_manager=CodegraphIndexManager(),
        provider=provider,
    )

    result = service.function_context("manifest-id", "missing_symbol")

    assert result.symbol == "missing_symbol"
    assert provider.calls == [
        {
            "project_root": project_root.resolve(),
            "symbol": "missing_symbol",
            "path": None,
            "watched_paths": ["src"],
        }
    ]



def test_codegraph_service_uses_cached_snapshot_for_function_context(
    workspace_root,
    make_manifest_project,
) -> None:
    make_manifest_project()
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    provider = FakeProvider()
    service = CodegraphService(
        project_registry=registry,
        watcher_manager=CodegraphWatcherManager(),
        index_manager=CodegraphIndexManager(),
        provider=provider,
    )

    watcher = service.watcher_health("manifest-id")
    result = service.function_context("manifest-id", "helper")
    indexed = service.watcher_health("manifest-id")

    assert watcher.status == "configured"
    assert watcher.revision is None
    assert result.symbol == "helper"
    assert result.matches[0].path == "src/example.py"
    assert result.matches[0].signature == "def helper():"
    assert indexed.status == "indexed"
    assert indexed.revision == "snapshot-rev-1"
    assert provider.build_snapshot_calls
    assert provider.calls == []



def test_codegraph_service_uses_cached_snapshot_for_reference_queries(
    workspace_root,
    make_manifest_project,
) -> None:
    make_manifest_project()
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    provider = FakeProvider()
    service = CodegraphService(
        project_registry=registry,
        watcher_manager=CodegraphWatcherManager(),
        index_manager=CodegraphIndexManager(),
        provider=provider,
    )

    watcher = service.watcher_health("manifest-id")
    references = service.find_references("manifest-id", "helper")
    call_path = service.call_path("manifest-id", "helper")
    indexed = service.watcher_health("manifest-id")

    assert watcher.status == "configured"
    assert indexed.status == "indexed"
    assert [match.line_text for match in references.matches] == ["    return helper()"]
    assert call_path.definition.path == "src/example.py"
    assert [item.symbol for item in call_path.incoming] == ["caller"]
    assert call_path.outgoing == []
    assert len(provider.build_snapshot_calls) == 1
    assert provider.find_reference_calls == []
    assert provider.call_path_calls == []



def test_codegraph_service_rebuilds_snapshot_when_watched_files_change(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    src = project_root / "src"
    src.mkdir()
    sample = src / "sample.py"
    sample.write_text("def helper():\n    return 1\n", encoding="utf-8")

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    provider = FakeProvider()
    service = CodegraphService(
        project_registry=registry,
        watcher_manager=CodegraphWatcherManager(),
        index_manager=CodegraphIndexManager(),
        provider=provider,
    )

    initial = service.function_context("manifest-id", "helper")
    first = service.watcher_health("manifest-id")
    sample.write_text("def helper():\n    return 2\n", encoding="utf-8")
    stale = service.watcher_health("manifest-id")
    updated = service.function_context("manifest-id", "helper")
    second = service.watcher_health("manifest-id")

    assert initial.matches[0].source.endswith("return 1")
    assert first.status == "indexed"
    assert first.revision == "snapshot-rev-1"
    assert stale.status == "configured"
    assert stale.revision is None
    assert updated.matches[0].source.endswith("return 2")
    assert second.status == "indexed"
    assert second.revision == "snapshot-rev-2"
    assert len(provider.build_snapshot_calls) == 2



def test_codegraph_service_rebuilds_snapshot_before_cached_query_after_file_change(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    src = project_root / "src"
    src.mkdir()
    sample = src / "sample.py"
    sample.write_text("def helper():\n    return 1\n", encoding="utf-8")

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    provider = FakeProvider()
    service = CodegraphService(
        project_registry=registry,
        watcher_manager=CodegraphWatcherManager(),
        index_manager=CodegraphIndexManager(),
        provider=provider,
    )

    first = service.function_context("manifest-id", "helper")
    sample.write_text("def helper():\n    return 2\n", encoding="utf-8")
    result = service.function_context("manifest-id", "helper")

    assert first.matches[0].source.endswith("return 1")
    assert len(provider.build_snapshot_calls) == 2
    assert result.matches[0].source.endswith("return 2")
    assert service.index_manager.get_snapshot("manifest-id").revision == "snapshot-rev-2"
