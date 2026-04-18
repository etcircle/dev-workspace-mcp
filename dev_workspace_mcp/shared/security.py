from __future__ import annotations

import re

_SECRET_PATTERN = re.compile(r"(?i)\b(token|password|secret|api[_-]?key)=([^\s]+)")


def redact_secrets(text: str) -> str:
    """Replace common inline secret assignments with a placeholder."""

    # TODO: Expand coverage for structured configs and headers.
    return _SECRET_PATTERN.sub(r"\1=[REDACTED]", text)


__all__ = ["redact_secrets"]