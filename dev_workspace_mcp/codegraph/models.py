from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CodegraphNode(BaseModel):
    """Represents a single indexed symbol or file."""

    identifier: str
    name: str | None = None
    kind: str = "unknown"
    path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    signature: str | None = None
    source: str | None = None


class CodegraphEdge(BaseModel):
    """Represents a lightweight relationship between indexed nodes."""

    source: str
    target: str
    relation: str = "references"
    path: str | None = None
    line_number: int | None = None
    line_text: str | None = None


class CodegraphIndexSnapshot(BaseModel):
    """Stores the current in-memory index state for a project."""

    project_id: str
    revision: str | None = None
    state_token: str | None = None
    indexed_at: datetime | None = None
    file_count: int = 0
    symbol_count: int = 0
    nodes: list[CodegraphNode] = Field(default_factory=list)
    edges: list[CodegraphEdge] = Field(default_factory=list)


class CodegraphWatchState(BaseModel):
    """Captures watcher metadata for a project."""

    project_id: str
    active: bool = False
    status: Literal["not_configured", "configured", "indexed", "inactive"] = "not_configured"
    watched_paths: list[str] = Field(default_factory=list)
    revision: str | None = None
    indexed_at: datetime | None = None
    file_count: int = 0
    symbol_count: int = 0


__all__ = [
    "CodegraphEdge",
    "CodegraphIndexSnapshot",
    "CodegraphNode",
    "CodegraphWatchState",
]