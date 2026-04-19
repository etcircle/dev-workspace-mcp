from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from dev_workspace_mcp.shared.paths import resolve_project_path

_FIXED_CANONICAL_PATHS = (
    ("AGENTS.md", "agents"),
    (".devworkspace/memory.md", "memory"),
    (".devworkspace/roadmap.md", "roadmap"),
)
_DIRECTORY_CANONICAL_PATHS = (
    ("docs/decisions", "decision"),
    ("docs/standards", "standard"),
)
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


@dataclass(frozen=True)
class IndexedChunk:
    chunk_index: int
    heading: str | None
    content: str


@dataclass(frozen=True)
class IndexedDocument:
    path: str
    kind: str
    content_hash: str
    chunks: list[IndexedChunk]


class CanonicalDocumentIndexer:
    def __init__(
        self,
        project_root: Path,
        *,
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def collect_documents(self) -> list[IndexedDocument]:
        documents: list[IndexedDocument] = []
        for relative_path, kind, path in self._iter_canonical_files():
            try:
                raw_content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise ValueError(
                    f"Canonical document is not readable as UTF-8: {relative_path}"
                ) from exc
            normalized_content = _normalize_content(raw_content)
            documents.append(
                IndexedDocument(
                    path=relative_path,
                    kind=kind,
                    content_hash=_content_hash(normalized_content),
                    chunks=self._chunk_document(normalized_content),
                )
            )
        return documents

    def _iter_canonical_files(self) -> list[tuple[str, str, Path]]:
        discovered: list[tuple[str, str, Path]] = []
        for relative_path, kind in _FIXED_CANONICAL_PATHS:
            path = resolve_project_path(
                self.project_root,
                relative_path,
                allow_missing_leaf=True,
                forbid_symlinks=True,
            )
            if path.is_file():
                discovered.append((relative_path, kind, path))

        for relative_dir, kind in _DIRECTORY_CANONICAL_PATHS:
            directory = resolve_project_path(
                self.project_root,
                relative_dir,
                allow_missing_leaf=True,
                forbid_symlinks=True,
            )
            if not directory.is_dir():
                continue
            for candidate in sorted(directory.rglob("*.md")):
                if not candidate.is_file() or candidate.is_symlink():
                    continue
                resolved = candidate.resolve()
                try:
                    relative_path = resolved.relative_to(self.project_root).as_posix()
                except ValueError:
                    continue
                discovered.append((relative_path, kind, resolved))

        return sorted(discovered, key=lambda item: item[0])

    def _chunk_document(self, content: str) -> list[IndexedChunk]:
        if not content:
            return []

        chunks: list[IndexedChunk] = []
        for heading, section_content in _split_sections(content):
            if not section_content and heading:
                section_content = heading
            for piece in _window_text(
                section_content,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
            ):
                chunks.append(
                    IndexedChunk(
                        chunk_index=len(chunks),
                        heading=heading,
                        content=piece,
                    )
                )

        return chunks


def _split_sections(content: str) -> list[tuple[str | None, str]]:
    sections: list[tuple[str | None, str]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in content.split("\n"):
        heading_match = _HEADING_PATTERN.match(line)
        if heading_match:
            if current_heading is not None or current_lines:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = heading_match.group(2).strip()
            current_lines = []
            continue
        current_lines.append(line)

    if current_heading is not None or current_lines:
        sections.append((current_heading, "\n".join(current_lines).strip()))

    return sections or [(None, content)]


def _window_text(text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []
    if len(normalized) <= chunk_size:
        return [normalized]

    windows: list[str] = []
    step = max(chunk_size - chunk_overlap, 1)
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        piece = normalized[start:end].strip()
        if piece:
            windows.append(piece)
        if end >= len(normalized):
            break
        start += step
    return windows


def _normalize_content(content: str) -> str:
    return content.replace("\r\n", "\n").replace("\r", "\n").strip()


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


__all__ = ["CanonicalDocumentIndexer", "IndexedChunk", "IndexedDocument"]
