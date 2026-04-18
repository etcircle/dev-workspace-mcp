from __future__ import annotations

from pathlib import Path

from dev_workspace_mcp.models.state_docs import (
    PatchStateDocResponse,
    ReadStateDocResponse,
    StateDocKind,
    StateDocument,
    WriteStateDocResponse,
)
from dev_workspace_mcp.state_docs.limits import ensure_within_limit, get_char_limit
from dev_workspace_mcp.state_docs.parser import parse_state_document, patch_state_document

_STATE_DOC_PATHS = {
    StateDocKind.memory: ".devworkspace/memory.md",
    StateDocKind.roadmap: ".devworkspace/roadmap.md",
    StateDocKind.tasks: ".devworkspace/tasks.md",
}


class StateDocumentService:
    """Reads, writes, and patches repo-local working state documents."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root).resolve()

    def doc_path(self, kind: StateDocKind) -> Path:
        return self.project_root / _STATE_DOC_PATHS[kind]

    def read(self, kind: StateDocKind) -> ReadStateDocResponse:
        path = self.doc_path(kind)
        raw_markdown = path.read_text(encoding="utf-8") if path.exists() else ""
        document = self._build_document(kind, raw_markdown, path)
        return ReadStateDocResponse(
            document=document,
            parsed_sections=parse_state_document(raw_markdown),
        )

    def write(self, kind: StateDocKind, raw_markdown: str) -> WriteStateDocResponse:
        ensure_within_limit(kind, raw_markdown)
        path = self.doc_path(kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw_markdown, encoding="utf-8")
        return WriteStateDocResponse(document=self._build_document(kind, raw_markdown, path))

    def patch(
        self,
        kind: StateDocKind,
        section_updates: dict[str, str],
        *,
        create_missing_sections: bool = True,
    ) -> PatchStateDocResponse:
        current = self.read(kind).document.raw_markdown
        patched = patch_state_document(
            current,
            section_updates,
            create_missing_sections=create_missing_sections,
        )
        ensure_within_limit(kind, patched)
        path = self.doc_path(kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(patched, encoding="utf-8")
        return PatchStateDocResponse(
            document=self._build_document(kind, patched, path),
            updated_headings=list(section_updates.keys()),
        )

    def _build_document(self, kind: StateDocKind, raw_markdown: str, path: Path) -> StateDocument:
        return StateDocument(
            kind=kind,
            path=_STATE_DOC_PATHS[kind],
            raw_markdown=raw_markdown,
            char_count=len(raw_markdown),
            last_updated_at=None if not path.exists() else _mtime_to_datetime(path),
            within_limit=len(raw_markdown) <= get_char_limit(kind),
        )



def _mtime_to_datetime(path: Path):
    from datetime import UTC, datetime

    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


__all__ = ["StateDocumentService"]
