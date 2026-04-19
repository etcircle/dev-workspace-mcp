from __future__ import annotations

from dev_workspace_mcp.codegraph.models import CodegraphIndexSnapshot, CodegraphWatchState


class CodegraphWatcherManager:
    """Tracks watcher intent and index metadata without a live filesystem backend."""

    def __init__(self) -> None:
        self._states: dict[str, CodegraphWatchState] = {}

    def start(
        self,
        project_id: str,
        watched_paths: list[str] | None = None,
        *,
        snapshot: CodegraphIndexSnapshot | None = None,
    ) -> CodegraphWatchState:
        """Record configured/indexed watcher metadata without claiming active watching."""

        normalized_paths = list(watched_paths or [])
        status = (
            "indexed"
            if snapshot is not None
            else "configured"
            if normalized_paths
            else "not_configured"
        )
        state = CodegraphWatchState(
            project_id=project_id,
            active=False,
            status=status,
            watched_paths=normalized_paths,
            revision=snapshot.revision if snapshot else None,
            indexed_at=snapshot.indexed_at if snapshot else None,
            file_count=snapshot.file_count if snapshot else 0,
            symbol_count=snapshot.symbol_count if snapshot else 0,
        )
        self._states[project_id] = state
        return state

    def stop(self, project_id: str) -> CodegraphWatchState:
        """Mark stored watcher metadata as inactive."""

        state = self._states.get(project_id, CodegraphWatchState(project_id=project_id))
        state.active = False
        state.status = "inactive" if state.watched_paths else "not_configured"
        self._states[project_id] = state
        return state

    def get_state(self, project_id: str) -> CodegraphWatchState:
        """Return the current watcher metadata for a project."""

        return self._states.get(project_id, CodegraphWatchState(project_id=project_id))


__all__ = ["CodegraphWatcherManager"]
