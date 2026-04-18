from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ManagedService(BaseModel):
    """Represents a named long-running service inside a project."""

    service_name: str
    command: list[str] = Field(default_factory=list)
    cwd: str | None = None
    status: Literal["stopped", "starting", "running", "failed"] = "stopped"
    pid: int | None = None


class ServiceLogChunk(BaseModel):
    """Carries a small slice of service log output."""

    service_name: str
    lines: list[str] = Field(default_factory=list)


__all__ = ["ManagedService", "ServiceLogChunk"]