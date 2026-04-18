from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CodeMatch(BaseModel):
    path: str
    line_number: int = Field(ge=1)
    line_text: str


class GrepResponse(BaseModel):
    pattern: str
    matches: list[CodeMatch] = Field(default_factory=list)
    truncated: bool = False


class SourceReadResponse(BaseModel):
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content: str
    truncated: bool = False


class FunctionOverviewItem(BaseModel):
    name: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)


class ClassOverviewItem(BaseModel):
    name: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    methods: list[str] = Field(default_factory=list)


class ModuleOverviewResponse(BaseModel):
    path: str
    language: str = "text"
    imports: list[str] = Field(default_factory=list)
    classes: list[ClassOverviewItem] = Field(default_factory=list)
    functions: list[FunctionOverviewItem] = Field(default_factory=list)
    line_count: int = Field(default=0, ge=0)


class SymbolContextMatch(BaseModel):
    name: str
    kind: str
    path: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    signature: str
    source: str


class FunctionContextResponse(BaseModel):
    symbol: str
    matches: list[SymbolContextMatch] = Field(default_factory=list)


class CallPathNode(BaseModel):
    symbol: str
    kind: str
    path: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)


class CallPathResponse(BaseModel):
    symbol: str
    definition: CallPathNode
    incoming: list[CallPathNode] = Field(default_factory=list)
    outgoing: list[CallPathNode] = Field(default_factory=list)


class WatcherHealthResponse(BaseModel):
    project_id: str
    configured: bool = False
    active: bool = False
    watched_paths: list[str] = Field(default_factory=list)
    status: str = "not_configured"
    revision: str | None = None
    indexed_at: datetime | None = None
    file_count: int = 0
    symbol_count: int = 0


__all__ = [
    "CallPathNode",
    "CallPathResponse",
    "ClassOverviewItem",
    "CodeMatch",
    "FunctionContextResponse",
    "FunctionOverviewItem",
    "GrepResponse",
    "ModuleOverviewResponse",
    "SourceReadResponse",
    "SymbolContextMatch",
    "WatcherHealthResponse",
]
