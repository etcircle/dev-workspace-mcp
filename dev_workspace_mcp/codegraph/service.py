from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dev_workspace_mcp.codegraph.index_manager import CodegraphIndexManager
from dev_workspace_mcp.codegraph.models import CodegraphIndexSnapshot, CodegraphNode
from dev_workspace_mcp.codegraph.providers import CodegraphProvider
from dev_workspace_mcp.codegraph.watcher_manager import CodegraphWatcherManager
from dev_workspace_mcp.gittools.service import GitService
from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.codegraph import (
    CallPathNode,
    CallPathResponse,
    CodeMatch,
    FunctionContextResponse,
    GrepResponse,
    SymbolContextMatch,
    WatcherHealthResponse,
)
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.projects.registry import ProjectRegistry
from dev_workspace_mcp.shared.paths import resolve_project_path


@dataclass(slots=True)
class CodegraphService:
    project_registry: ProjectRegistry
    watcher_manager: CodegraphWatcherManager
    index_manager: CodegraphIndexManager
    provider: CodegraphProvider

    def module_overview(self, project_id: str, path: str):
        project = self.project_registry.require(project_id)
        return self.provider.module_overview(Path(project.root_path), path)

    def function_context(self, project_id: str, symbol: str, path: str | None = None):
        project = self.project_registry.require(project_id)
        project_root = Path(project.root_path)
        watched_paths = list(project.manifest.codegraph.watch_paths)
        snapshot = self._ensure_snapshot(project_id, project_root, watched_paths)
        cached = self._function_context_from_snapshot(snapshot, symbol, path=path)
        if cached is not None:
            return cached
        return self.provider.function_context(
            project_root,
            symbol,
            path=path,
            watched_paths=watched_paths,
        )

    def grep(
        self,
        project_id: str,
        pattern: str,
        *,
        path: str | None = None,
        ignore_case: bool = False,
    ):
        project = self.project_registry.require(project_id)
        return self.provider.grep(
            Path(project.root_path),
            pattern,
            path=path,
            watched_paths=list(project.manifest.codegraph.watch_paths),
            ignore_case=ignore_case,
        )

    def find_references(self, project_id: str, symbol: str, *, path: str | None = None):
        project = self.project_registry.require(project_id)
        project_root = Path(project.root_path)
        watched_paths = list(project.manifest.codegraph.watch_paths)
        snapshot = self._ensure_snapshot(project_id, project_root, watched_paths)
        cached = self._find_references_from_snapshot(snapshot, symbol, path=path)
        if cached is not None:
            return cached
        return self.provider.find_references(
            project_root,
            symbol,
            path=path,
            watched_paths=watched_paths,
        )

    def call_path(self, project_id: str, symbol: str, *, path: str | None = None):
        project = self.project_registry.require(project_id)
        project_root = Path(project.root_path)
        watched_paths = list(project.manifest.codegraph.watch_paths)
        snapshot = self._ensure_snapshot(project_id, project_root, watched_paths)
        cached = self._call_path_from_snapshot(snapshot, symbol, path=path)
        if cached is not None:
            return cached
        return self.provider.call_path(
            project_root,
            symbol,
            path=path,
            watched_paths=watched_paths,
        )

    def read_source(
        self,
        project_id: str,
        path: str,
        *,
        start_line: int = 1,
        end_line: int | None = None,
    ):
        project = self.project_registry.require(project_id)
        return self.provider.read_source(
            Path(project.root_path),
            path,
            start_line=start_line,
            end_line=end_line,
        )

    def recent_changes(
        self,
        project_id: str,
        *,
        path: str | None = None,
        ref: str | None = None,
        staged: bool = False,
        context_lines: int = 3,
    ):
        project = self.project_registry.require(project_id)
        git_service = self._git_service(project.root_path)
        return git_service.git_diff(
            path=path,
            ref=ref,
            staged=staged,
            context_lines=context_lines,
        )

    def watcher_health(self, project_id: str) -> WatcherHealthResponse:
        project = self.project_registry.require(project_id)
        project_root = Path(project.root_path)
        watched_paths = list(project.manifest.codegraph.watch_paths)
        for watched_path in watched_paths:
            resolve_project_path(project_root, watched_path)
        state = self.watcher_manager.get_state(project_id)
        if not watched_paths:
            return WatcherHealthResponse(
                project_id=project_id,
                configured=False,
                active=False,
                watched_paths=[],
                status="not_configured",
                revision=None,
                indexed_at=None,
                file_count=0,
                symbol_count=0,
            )

        snapshot = self.index_manager.get_snapshot(project_id)
        if self._snapshot_is_indexed_for_watch_paths(snapshot, project_root, watched_paths):
            return WatcherHealthResponse(
                project_id=project_id,
                configured=True,
                active=False,
                watched_paths=list(state.watched_paths or watched_paths),
                status="indexed",
                revision=snapshot.revision,
                indexed_at=snapshot.indexed_at,
                file_count=snapshot.file_count,
                symbol_count=snapshot.symbol_count,
            )

        return WatcherHealthResponse(
            project_id=project_id,
            configured=True,
            active=False,
            watched_paths=list(state.watched_paths or watched_paths),
            status="inactive" if state.status == "inactive" else "configured",
            revision=None,
            indexed_at=None,
            file_count=0,
            symbol_count=0,
        )

    def _ensure_snapshot(
        self,
        project_id: str,
        project_root: Path,
        watched_paths: list[str],
    ) -> CodegraphIndexSnapshot:
        snapshot = self.index_manager.get_snapshot(project_id)
        if not watched_paths:
            return snapshot
        current_state_token = self.index_manager.compute_state_token(project_root, watched_paths)
        if snapshot.state_token == current_state_token and self._snapshot_has_index(snapshot):
            self.watcher_manager.start(project_id, watched_paths, snapshot=snapshot)
            return snapshot
        snapshot = self.provider.build_index_snapshot(
            project_id,
            project_root,
            watched_paths=watched_paths,
        )
        snapshot.state_token = current_state_token
        self.index_manager.record_snapshot(snapshot)
        self.watcher_manager.start(project_id, watched_paths, snapshot=snapshot)
        return snapshot

    def _snapshot_is_indexed_for_watch_paths(
        self,
        snapshot: CodegraphIndexSnapshot,
        project_root: Path,
        watched_paths: list[str],
    ) -> bool:
        if (
            not watched_paths
            or not self._snapshot_has_index(snapshot)
            or snapshot.state_token is None
        ):
            return False
        current_state_token = self.index_manager.compute_state_token(project_root, watched_paths)
        return snapshot.state_token == current_state_token

    @staticmethod
    def _snapshot_has_index(snapshot: CodegraphIndexSnapshot) -> bool:
        return bool(
            snapshot.nodes
            or snapshot.edges
            or snapshot.revision
            or snapshot.indexed_at
            or snapshot.file_count
            or snapshot.symbol_count
        )

    def _function_context_from_snapshot(
        self,
        snapshot: CodegraphIndexSnapshot,
        symbol: str,
        *,
        path: str | None = None,
    ) -> FunctionContextResponse | None:
        matches = [
            node
            for node in snapshot.nodes
            if node.kind != "file"
            and node.name == symbol
            and (path is None or node.path == path)
            and node.path is not None
            and node.line_start is not None
            and node.line_end is not None
            and node.signature is not None
            and node.source is not None
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: (item.path or "", item.line_start or 0))
        return FunctionContextResponse(
            symbol=symbol,
            matches=[
                SymbolContextMatch(
                    name=symbol,
                    kind=node.kind,
                    path=node.path or "",
                    line_start=node.line_start or 1,
                    line_end=node.line_end or 1,
                    signature=node.signature or symbol,
                    source=node.source or "",
                )
                for node in matches
            ],
        )

    def _find_references_from_snapshot(
        self,
        snapshot: CodegraphIndexSnapshot,
        symbol: str,
        *,
        path: str | None = None,
    ) -> GrepResponse | None:
        targets = self._symbol_targets(snapshot, symbol, path=path)
        matches = [
            CodeMatch(
                path=edge.path or "",
                line_number=edge.line_number or 1,
                line_text=edge.line_text or "",
            )
            for edge in snapshot.edges
            if edge.relation == "calls"
            and (path is None or edge.path == path)
            and edge.path is not None
            and edge.line_number is not None
            and edge.line_text is not None
            and edge.target in targets
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: (item.path, item.line_number, item.line_text))
        return GrepResponse(pattern=symbol, matches=matches, truncated=False)

    def _call_path_from_snapshot(
        self,
        snapshot: CodegraphIndexSnapshot,
        symbol: str,
        *,
        path: str | None = None,
    ) -> CallPathResponse | None:
        definitions = [
            node
            for node in snapshot.nodes
            if node.kind != "file"
            and node.name == symbol
            and (path is None or node.path == path)
            and node.path is not None
            and node.line_start is not None
            and node.line_end is not None
        ]
        if not definitions:
            return None
        definitions.sort(key=lambda item: (item.path or "", item.line_start or 0))
        definition = definitions[0]
        targets = self._symbol_targets(snapshot, symbol, path=path)
        incoming: list[CallPathNode] = []
        for edge in snapshot.edges:
            if edge.relation != "calls" or edge.target not in targets:
                continue
            source_node = self._node_by_identifier(snapshot, edge.source)
            if source_node is None or source_node.kind == "file":
                continue
            if path is not None and source_node.path != path:
                continue
            incoming.append(self._as_call_path_node(source_node))

        outgoing: list[CallPathNode] = []
        for edge in snapshot.edges:
            if edge.relation != "calls" or edge.source != definition.identifier:
                continue
            target_node = self._resolve_edge_target(snapshot, edge.target)
            if target_node is None or target_node.kind == "file":
                continue
            outgoing.append(self._as_call_path_node(target_node))

        incoming.sort(key=lambda item: (item.path, item.line_start, item.symbol))
        outgoing.sort(key=lambda item: (item.path, item.line_start, item.symbol))
        return CallPathResponse(
            symbol=symbol,
            definition=self._as_call_path_node(definition),
            incoming=incoming,
            outgoing=outgoing,
        )

    @staticmethod
    def _node_by_identifier(
        snapshot: CodegraphIndexSnapshot,
        identifier: str,
    ) -> CodegraphNode | None:
        for node in snapshot.nodes:
            if node.identifier == identifier:
                return node
        return None

    @staticmethod
    def _resolve_edge_target(snapshot: CodegraphIndexSnapshot, target: str) -> CodegraphNode | None:
        for node in snapshot.nodes:
            if node.identifier == target and node.kind != "file":
                return node
        for node in snapshot.nodes:
            if node.name == target and node.kind != "file":
                return node
        return None

    @staticmethod
    def _symbol_targets(
        snapshot: CodegraphIndexSnapshot,
        symbol: str,
        *,
        path: str | None = None,
    ) -> set[str]:
        targets = {symbol}
        for node in snapshot.nodes:
            if node.kind == "file" or node.name != symbol:
                continue
            if path is not None and node.path != path:
                continue
            targets.add(node.identifier)
        return targets

    @staticmethod
    def _as_call_path_node(node: CodegraphNode) -> CallPathNode:
        if node.path is None or node.line_start is None or node.line_end is None:
            raise DomainError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Index snapshot is missing call-path metadata.",
            )
        return CallPathNode(
            symbol=node.name or node.identifier,
            kind=node.kind,
            path=node.path,
            line_start=node.line_start,
            line_end=node.line_end,
        )

    def _git_service(self, root_path: str) -> GitService:
        max_diff_bytes = getattr(self.project_registry.settings, "max_read_bytes", 200_000)
        return GitService(Path(root_path), max_diff_bytes=max_diff_bytes)


__all__ = ["CodegraphService"]
