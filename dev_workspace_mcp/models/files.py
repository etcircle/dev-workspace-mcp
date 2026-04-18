from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PathKind = Literal["file", "directory", "symlink", "other"]


class FileSummary(BaseModel):
    path: str
    size_bytes: int | None = Field(default=None, ge=0)
    line_count: int | None = Field(default=None, ge=0)
    encoding: str | None = None
    sha256: str | None = None


class DirEntry(BaseModel):
    path: str
    name: str
    kind: PathKind = "file"
    size_bytes: int | None = Field(default=None, ge=0)
    is_hidden: bool = False


class ListDirRequest(BaseModel):
    project_id: str
    path: str = "."
    recursive: bool = False
    limit: int | None = Field(default=None, ge=1)


class ListDirResponse(BaseModel):
    path: str = "."
    entries: list[DirEntry] = Field(default_factory=list)
    truncated: bool = False


class ReadFileRequest(BaseModel):
    project_id: str
    path: str
    offset: int = Field(default=1, ge=1)
    limit: int | None = Field(default=None, ge=1)


class ReadFileResponse(BaseModel):
    path: str
    content: str
    encoding: str = "utf-8"
    truncated: bool = False
    summary: FileSummary | None = None


class WriteFileRequest(BaseModel):
    project_id: str
    path: str
    content: str
    encoding: str = "utf-8"
    create_parents: bool = True
    overwrite: bool = True


class WriteFileResponse(BaseModel):
    path: str
    bytes_written: int = Field(ge=0)
    summary: FileSummary | None = None


class ApplyPatchRequest(BaseModel):
    project_id: str
    patch: str
    base_path: str | None = None


class ApplyPatchResponse(BaseModel):
    changed_paths: list[str] = Field(default_factory=list)
    diff: str | None = None


class MovePathRequest(BaseModel):
    project_id: str
    source_path: str
    destination_path: str
    overwrite: bool = False


class DeletePathRequest(BaseModel):
    project_id: str
    path: str
    recursive: bool = False
    missing_ok: bool = False


class PathMutationResponse(BaseModel):
    path: str
    existed: bool = True
    changed: bool = True


__all__ = [
    "ApplyPatchRequest",
    "ApplyPatchResponse",
    "DeletePathRequest",
    "DirEntry",
    "FileSummary",
    "ListDirRequest",
    "ListDirResponse",
    "MovePathRequest",
    "PathMutationResponse",
    "ReadFileRequest",
    "ReadFileResponse",
    "WriteFileRequest",
    "WriteFileResponse",
]
