from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled", "timed_out"]


class PresetDefinition(BaseModel):
    name: str
    argv: list[str] = Field(default_factory=list)
    cwd: str | None = None
    description: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    timeout_sec: int | None = Field(default=None, ge=1)


class CommandOutputChunk(BaseModel):
    stream: Literal["stdout", "stderr"] = "stdout"
    text: str


class CommandTiming(BaseModel):
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class JobRecord(BaseModel):
    job_id: str
    project_id: str
    argv: list[str] = Field(default_factory=list)
    cwd: str | None = None
    status: JobStatus = "queued"
    background: bool = False
    pid: int | None = Field(default=None, ge=1)
    exit_code: int | None = None
    output: list[CommandOutputChunk] = Field(default_factory=list)
    timing: CommandTiming = Field(default_factory=CommandTiming)


class RunCommandRequest(BaseModel):
    project_id: str
    argv: list[str] = Field(default_factory=list)
    cwd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    timeout_sec: int | None = Field(default=None, ge=1)
    background: bool = False
    preset: str | None = None


class RunCommandResponse(BaseModel):
    job: JobRecord


class GetJobRequest(BaseModel):
    project_id: str
    job_id: str


class GetJobResponse(BaseModel):
    job: JobRecord


class CancelJobRequest(BaseModel):
    project_id: str
    job_id: str
    signal: str | None = None


class CancelJobResponse(BaseModel):
    job: JobRecord


__all__ = [
    "CancelJobRequest",
    "CancelJobResponse",
    "CommandOutputChunk",
    "CommandTiming",
    "GetJobRequest",
    "GetJobResponse",
    "JobRecord",
    "JobStatus",
    "PresetDefinition",
    "RunCommandRequest",
    "RunCommandResponse",
]
