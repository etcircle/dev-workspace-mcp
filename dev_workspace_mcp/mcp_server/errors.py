from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dev_workspace_mcp.models.errors import ErrorCode


@dataclass(slots=True)
class DomainError(Exception):
    code: ErrorCode | str
    message: str
    hint: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"
