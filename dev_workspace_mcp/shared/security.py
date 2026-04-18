from __future__ import annotations

import re
from fnmatch import fnmatch

from dev_workspace_mcp.policy.models import EnvPolicy

_ASSIGNMENT_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)=([^\s]+)")
_AUTHORIZATION_PATTERN = re.compile(r"(?im)^(authorization:\s*)(bearer\s+)?(.+)$")
_GENERIC_SECRET_NAME_PATTERNS = (
    "*TOKEN*",
    "*SECRET*",
    "*PASSWORD*",
    "*API_KEY*",
    "*PRIVATE_KEY*",
    "AWS_*",
)


def redact_secrets(text: str, *, env_policy: EnvPolicy | None = None) -> str:
    """Replace common inline secret assignments and headers with placeholders."""

    if not text:
        return text

    patterns = {pattern.upper() for pattern in _GENERIC_SECRET_NAME_PATTERNS}
    if env_policy is not None:
        patterns.update(pattern.upper() for pattern in env_policy.redact)

    redacted = _ASSIGNMENT_PATTERN.sub(lambda match: _redact_assignment(match, patterns), text)
    return _AUTHORIZATION_PATTERN.sub(_redact_authorization_header, redacted)


def _redact_assignment(match: re.Match[str], patterns: set[str]) -> str:
    name = match.group(1)
    if any(fnmatch(name.upper(), pattern) for pattern in patterns):
        return f"{name}=[REDACTED]"
    return match.group(0)


def _redact_authorization_header(match: re.Match[str]) -> str:
    prefix = match.group(1)
    scheme = match.group(2) or ""
    return f"{prefix}{scheme}[REDACTED]"


__all__ = ["redact_secrets"]
