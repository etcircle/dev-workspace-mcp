from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class StateDocKind(StrEnum):
    memory = "memory"
    roadmap = "roadmap"
    tasks = "tasks"


class StateDocRef(BaseModel):
    kind: StateDocKind
    path: str
    char_limit: int | None = Field(default=None, ge=1)


class StateDocument(BaseModel):
    kind: StateDocKind
    path: str
    raw_markdown: str
    char_count: int = Field(default=0, ge=0)
    last_updated_at: datetime | None = None
    within_limit: bool = True


class ReadStateDocRequest(BaseModel):
    project_id: str
    kind: StateDocKind


class ReadStateDocResponse(BaseModel):
    document: StateDocument
    parsed_sections: dict[str, str] = Field(default_factory=dict)


class WriteStateDocRequest(BaseModel):
    project_id: str
    kind: StateDocKind
    raw_markdown: str
    create_if_missing: bool = True


class WriteStateDocResponse(BaseModel):
    document: StateDocument
    written: bool = True


class PatchStateDocRequest(BaseModel):
    project_id: str
    kind: StateDocKind
    section_updates: dict[str, str] = Field(default_factory=dict)
    create_missing_sections: bool = True


class PatchStateDocResponse(BaseModel):
    document: StateDocument
    updated_headings: list[str] = Field(default_factory=list)


__all__ = [
    "PatchStateDocRequest",
    "PatchStateDocResponse",
    "ReadStateDocRequest",
    "ReadStateDocResponse",
    "StateDocument",
    "StateDocKind",
    "StateDocRef",
    "WriteStateDocRequest",
    "WriteStateDocResponse",
]
