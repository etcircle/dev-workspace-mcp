from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DecisionStatus = Literal["proposed", "active", "superseded", "rejected"]
MemoryIndexStatusValue = Literal["missing", "empty", "ready", "stale"]
MemorySearchResultKind = Literal["doc", "session", "decision"]
MemorySearchScope = Literal["all", "docs", "sessions", "decisions"]
SourceRefKind = Literal[
    "github",
    "github_issue",
    "github_pr",
    "github_discussion",
    "chat_thread",
    "doc",
    "commit",
]

_GITHUB_REF_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#\d+$")
_COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SIMPLE_REF_PATTERN = re.compile(r"^\S+$")
_GITHUB_SOURCE_REF_KINDS = {
    "github",
    "github_issue",
    "github_pr",
    "github_discussion",
}


class StrictMemoryIndexModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceRef(StrictMemoryIndexModel):
    kind: SourceRefKind
    value: str = Field(min_length=1)

    @field_validator("value")
    @classmethod
    def _normalize_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Source ref value must not be blank.")
        return normalized

    @model_validator(mode="after")
    def _validate_kind_specific_value(self) -> SourceRef:
        if self.kind == "doc":
            self.value = _normalize_relative_path(self.value)
        elif self.kind in _GITHUB_SOURCE_REF_KINDS:
            self.value = _normalize_github_ref(self.value)
        elif self.kind == "commit":
            self.value = _normalize_commit_sha(self.value)
        elif self.kind == "chat_thread":
            self.value = _normalize_simple_ref(self.value, field_name="chat_thread")
        return self

    def encoded(self) -> str:
        return f"{self.kind}:{self.value}"


class DecisionRecord(StrictMemoryIndexModel):
    title: str = Field(min_length=1)
    status: DecisionStatus
    rationale: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    github_ref: str | None = None
    doc_path: str | None = None

    @field_validator("title", "rationale", mode="before")
    @classmethod
    def _strip_required_text(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("Value must not be blank.")
            return normalized
        return value

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, tags: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for tag in tags:
            cleaned = tag.strip()
            if not cleaned or cleaned in seen:
                continue
            normalized.append(cleaned)
            seen.add(cleaned)
        return normalized

    @field_validator("github_ref")
    @classmethod
    def _normalize_github_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return _normalize_github_ref(normalized)

    @field_validator("doc_path")
    @classmethod
    def _normalize_doc_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_relative_path(value)


class SearchWorkspaceMemoryRequest(StrictMemoryIndexModel):
    project_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    scope: MemorySearchScope = "all"
    limit: int = Field(default=10, ge=1, le=50)

    @field_validator("project_id", "query")
    @classmethod
    def _strip_non_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value must not be blank.")
        return normalized


class MemorySearchResult(StrictMemoryIndexModel):
    kind: MemorySearchResultKind
    title: str
    snippet: str
    source_path: str | None = None
    source_ref: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    score: float = 0.0


class MemoryIndexStatusRequest(StrictMemoryIndexModel):
    project_id: str = Field(min_length=1)

    @field_validator("project_id")
    @classmethod
    def _strip_project_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value must not be blank.")
        return normalized


class MemoryIndexStatus(StrictMemoryIndexModel):
    project_id: str
    status: MemoryIndexStatusValue
    last_indexed_at: datetime | None = None
    documents_indexed: int = 0
    document_chunk_count: int = 0
    session_summary_count: int = 0
    decision_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class SearchWorkspaceMemoryResponse(StrictMemoryIndexModel):
    results: list[MemorySearchResult] = Field(default_factory=list)
    index_status: MemoryIndexStatus
    warnings: list[str] = Field(default_factory=list)


class RecordSessionSummaryRequest(StrictMemoryIndexModel):
    project_id: str = Field(min_length=1)
    source_platform: str = Field(min_length=1)
    source_session_ref: str = Field(min_length=1)
    source_thread_ref: str | None = None
    agent_name: str = Field(min_length=1)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    summary: str = Field(min_length=1)
    outcome: str | None = None
    decisions: list[DecisionRecord] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)

    @field_validator("project_id", "source_session_ref", "agent_name", "summary", mode="before")
    @classmethod
    def _strip_required_fields(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("Value must not be blank.")
            return normalized
        return value

    @field_validator("source_platform")
    @classmethod
    def _normalize_source_platform(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("source_platform must not be blank.")
        if normalized.lower() != normalized:
            raise ValueError("source_platform must be lowercase.")
        if not normalized.replace("_", "").isalnum():
            raise ValueError("source_platform must match [a-z0-9_]+.")
        return normalized

    @field_validator("source_thread_ref", "outcome")
    @classmethod
    def _strip_optional_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def _validate_time_range(self) -> RecordSessionSummaryRequest:
        if self.started_at and self.ended_at and self.ended_at < self.started_at:
            raise ValueError("ended_at must be greater than or equal to started_at.")
        return self


class RecordSessionSummaryResponse(StrictMemoryIndexModel):
    project_id: str
    session_summary_id: int
    decision_count: int = 0
    source_ref_count: int = 0


class ReindexWorkspaceMemoryRequest(StrictMemoryIndexModel):
    project_id: str = Field(min_length=1)
    reason: str = Field(default="manual", min_length=1)

    @field_validator("project_id", "reason")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value must not be blank.")
        return normalized


class ReindexWorkspaceMemoryResponse(StrictMemoryIndexModel):
    project_id: str
    documents_indexed: int = 0
    documents_changed: int = 0
    documents_removed: int = 0
    index_status: MemoryIndexStatus


def _normalize_relative_path(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Document path must not be blank.")
    candidate = PurePosixPath(normalized)
    normalized_path = candidate.as_posix()
    if normalized_path == ".":
        raise ValueError("Document path must not be '.'.")
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("doc_path must stay relative to the project root.")
    return normalized_path


def _normalize_github_ref(value: str) -> str:
    normalized = value.strip()
    if not _GITHUB_REF_PATTERN.fullmatch(normalized):
        raise ValueError("GitHub refs must use compact owner/repo#123 form.")
    return normalized


def _normalize_commit_sha(value: str) -> str:
    normalized = value.strip().lower()
    if not _COMMIT_SHA_PATTERN.fullmatch(normalized):
        raise ValueError("Commit refs must be full 40-character SHAs.")
    return normalized


def _normalize_simple_ref(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not _SIMPLE_REF_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} refs must be simple nonblank tokens.")
    return normalized


__all__ = [
    "DecisionRecord",
    "DecisionStatus",
    "MemoryIndexStatus",
    "MemoryIndexStatusRequest",
    "MemoryIndexStatusValue",
    "MemorySearchResult",
    "MemorySearchResultKind",
    "MemorySearchScope",
    "RecordSessionSummaryRequest",
    "RecordSessionSummaryResponse",
    "ReindexWorkspaceMemoryRequest",
    "ReindexWorkspaceMemoryResponse",
    "SearchWorkspaceMemoryRequest",
    "SearchWorkspaceMemoryResponse",
    "SourceRef",
    "SourceRefKind",
]
