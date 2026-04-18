from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ServiceHealthCheckDefinition(BaseModel):
    type: Literal["http", "command", "none"] = "none"
    url: str | None = None
    expect_status: int | None = None
    argv: list[str] = Field(default_factory=list)


class CodegraphConfig(BaseModel):
    watch_paths: list[str] = Field(default_factory=list)


class ServiceDefinition(BaseModel):
    cwd: str
    start: list[str] = Field(default_factory=list)
    stop_signal: str | None = None
    ports: list[int] = Field(default_factory=list)
    health: ServiceHealthCheckDefinition | None = None


class ProbeDefinition(BaseModel):
    cwd: str
    argv: list[str] = Field(default_factory=list)
    timeout_sec: int = 30


class ProjectManifest(BaseModel):
    name: str | None = None
    project_id: str | None = None
    aliases: list[str] = Field(default_factory=list)
    codegraph: CodegraphConfig = Field(default_factory=CodegraphConfig)
    services: dict[str, ServiceDefinition] = Field(default_factory=dict)
    probes: dict[str, ProbeDefinition] = Field(default_factory=dict)
    presets: dict[str, list[str]] = Field(default_factory=dict)


class ProjectRecord(BaseModel):
    project_id: str
    display_name: str
    root_path: str
    manifest_path: str | None = None
    aliases: list[str] = Field(default_factory=list)
    manifest: ProjectManifest = Field(default_factory=ProjectManifest)


class ProjectListItem(BaseModel):
    project_id: str
    display_name: str
    aliases: list[str] = Field(default_factory=list)
    manifest_present: bool = False
    root_path: str | None = None
    services: list[str] = Field(default_factory=list)
    codegraph_enabled: bool = False


class ServiceSummary(BaseModel):
    name: str
    cwd: str
    ports: list[int] = Field(default_factory=list)
    has_health_check: bool = False


class GitSummary(BaseModel):
    is_repo: bool = False
    branch: str | None = None
    dirty: bool = False
    staged_count: int = 0
    unstaged_count: int = 0
    untracked_count: int = 0
    changed_paths: list[str] = Field(default_factory=list)


class WatcherSummary(BaseModel):
    configured: bool = False
    active: bool = False
    watched_paths: list[str] = Field(default_factory=list)
    status: Literal["not_configured", "configured", "active", "inactive"] = "not_configured"
    revision: str | None = None
    indexed_at: datetime | None = None
    file_count: int = 0
    symbol_count: int = 0


class StateDocSummary(BaseModel):
    kind: str
    path: str
    exists: bool = False
    char_count: int = 0


class ProjectSnapshot(BaseModel):
    project: ProjectRecord
    git: GitSummary
    services: list[ServiceSummary] = Field(default_factory=list)
    watcher: WatcherSummary = Field(default_factory=WatcherSummary)
    recent_changed_files: list[str] = Field(default_factory=list)
    probes: list[str] = Field(default_factory=list)
    presets: list[str] = Field(default_factory=list)
    state_docs: list[StateDocSummary] = Field(default_factory=list)


__all__ = [
    "CodegraphConfig",
    "GitSummary",
    "ProbeDefinition",
    "ProjectListItem",
    "ProjectManifest",
    "ProjectRecord",
    "ProjectSnapshot",
    "ServiceDefinition",
    "ServiceHealthCheckDefinition",
    "ServiceSummary",
    "StateDocSummary",
    "WatcherSummary",
]
