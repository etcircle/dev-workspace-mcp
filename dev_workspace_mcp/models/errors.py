from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from dev_workspace_mcp.models.common import ToolError


class ErrorCode(StrEnum):
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    PROJECT_CONFLICT = "PROJECT_CONFLICT"
    MANIFEST_INVALID = "MANIFEST_INVALID"
    INVALID_PROJECT_ID = "INVALID_PROJECT_ID"
    INVALID_PATH = "INVALID_PATH"
    PATH_NOT_FOUND = "PATH_NOT_FOUND"
    PATCH_FAILED = "PATCH_FAILED"
    COMMAND_NOT_ALLOWED = "COMMAND_NOT_ALLOWED"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    JOB_TIMEOUT = "JOB_TIMEOUT"
    SERVICE_NOT_FOUND = "SERVICE_NOT_FOUND"
    SERVICE_NOT_RUNNING = "SERVICE_NOT_RUNNING"
    PROBE_NOT_FOUND = "PROBE_NOT_FOUND"
    GIT_NOT_AVAILABLE = "GIT_NOT_AVAILABLE"
    GIT_OPERATION_FAILED = "GIT_OPERATION_FAILED"
    HTTP_REQUEST_FAILED = "HTTP_REQUEST_FAILED"
    STATE_DOC_NOT_FOUND = "STATE_DOC_NOT_FOUND"
    STATE_DOC_LIMIT_EXCEEDED = "STATE_DOC_LIMIT_EXCEEDED"
    WATCHER_UNAVAILABLE = "WATCHER_UNAVAILABLE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ValidationIssue(BaseModel):
    field: str
    message: str
    input_value: Any | None = None


class ErrorDescriptor(BaseModel):
    code: ErrorCode
    category: Literal[
        "projects", "files", "commands", "services", "git", "state_docs", "internal"
    ] = "internal"
    retryable: bool = False
    default_message: str | None = None


class ValidationErrorDetail(BaseModel):
    error: ToolError
    issues: list[ValidationIssue] = Field(default_factory=list)


__all__ = [
    "ErrorCode",
    "ErrorDescriptor",
    "ToolError",
    "ValidationErrorDetail",
    "ValidationIssue",
]
