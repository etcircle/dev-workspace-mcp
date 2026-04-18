from __future__ import annotations

from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.models.state_docs import StateDocKind

STATE_DOC_LIMITS: dict[StateDocKind, int] = {
    StateDocKind.memory: 4_000,
    StateDocKind.roadmap: 8_000,
    StateDocKind.tasks: 8_000,
}



def get_char_limit(kind: StateDocKind) -> int:
    return STATE_DOC_LIMITS[kind]



def ensure_within_limit(kind: StateDocKind, text: str) -> None:
    limit = get_char_limit(kind)
    if len(text) > limit:
        raise DomainError(
            code=ErrorCode.STATE_DOC_LIMIT_EXCEEDED,
            message=f"{kind.value}.md exceeds its {limit}-character limit.",
            hint="Trim the document before writing it back.",
            details={"kind": kind.value, "char_count": len(text), "limit": limit},
        )


__all__ = ["STATE_DOC_LIMITS", "ensure_within_limit", "get_char_limit"]
