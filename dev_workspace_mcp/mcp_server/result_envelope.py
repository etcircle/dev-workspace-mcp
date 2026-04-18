from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel

from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.common import ToolError, ToolErrorResult, ToolResult, WarningMessage

JsonLike = dict[str, Any] | list[Any] | str | int | float | bool | None


def _normalize(value: Any) -> JsonLike:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def ok(
    data: dict[str, Any] | BaseModel | None = None,
    warnings: list[WarningMessage] | None = None,
) -> dict[str, Any]:
    payload = _normalize(data or {})
    return ToolResult(data=payload, warnings=warnings or []).model_dump(mode="json")


def error_result(error: DomainError) -> dict[str, Any]:
    return ToolErrorResult(
        error=ToolError(
            code=_normalize(error.code),
            message=error.message,
            hint=error.hint,
            details=_normalize(error.details) or {},
        )
    ).model_dump(mode="json")
