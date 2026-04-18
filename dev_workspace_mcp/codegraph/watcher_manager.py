from __future__ import annotations

from dev_workspace_mcp.codegraph.models import CodegraphIndexSnapshot, CodegraphWatchState


class CodegraphWatcherManager:
    """Tracks watcher intent without starting real filesystem observers."""

    def __init__(self) -> None:
        self._states: dict[str, CodegraphWatchState] = {}

    def start(
        self,
        project_id: str,
        watched_paths: list[str] | None = None,
        *,
        snapshot: CodegraphIndexSnapshot | None = None,
    ) -> CodegraphWatchState:
        """Mark a project watcher as active and attach the latest index metadata."""

        state = CodegraphWatchState(
            project_id=project_id,
            active=True,
            watched_paths=list(watched_paths or []),
            revision=snapshot.revision if snapshot else None,
            indexed_at=snapshot.indexed_at if snapshot else None,
            file_count=snapshot.file_count if snapshot else 0,
            symbol_count=snapshot.symbol_count if snapshot else 0,
        )
        # TODO: Replace this stub with a real file watching backend.
        self._states[project_id] = state
        return state

    def stop(self, project_id: str) -> CodegraphWatchState:
        """Mark a project watcher as inactive."""

        state = self._states.get(project_id, CodegraphWatchState(project_id=project_id))
        state.active = False
        self._states[project_id] = state
        return state

    def get_state(self, project_id: str) -> CodegraphWatchState:
        """Return the current watcher state for a project."""

        return self._states.get(project_id, CodegraphWatchState(project_id=project_id))


__all__ = ["CodegraphWatcherManager"]