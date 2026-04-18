from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class WarningMessage(BaseModel):
    code: str
    message: str


class ToolError(BaseModel):
    code: str
    message: str
    hint: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    ok: bool = True
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[WarningMessage] = Field(default_factory=list)


class ToolErrorResult(BaseModel):
    ok: bool = False
    error: ToolError


class ServiceHealth(BaseModel):
    status: Literal["healthy", "unhealthy", "unknown"] = "unknown"
    message: str | None = None
