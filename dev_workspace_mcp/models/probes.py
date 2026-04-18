from __future__ import annotations

from pydantic import BaseModel, Field


class ProbeSummary(BaseModel):
    name: str
    cwd: str
    argv: list[str] = Field(default_factory=list)
    timeout_sec: int = 30


class ListProbesResponse(BaseModel):
    probes: list[ProbeSummary] = Field(default_factory=list)


class ProbeRunResult(BaseModel):
    probe_name: str
    ok: bool = True
    cwd: str
    argv: list[str] = Field(default_factory=list)
    timeout_sec: int = 30
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""


__all__ = ["ListProbesResponse", "ProbeRunResult", "ProbeSummary"]
