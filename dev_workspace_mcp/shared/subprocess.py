from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass(slots=True)
class CommandSpec:
    """Minimal structured command specification."""

    argv: list[str] = field(default_factory=list)
    cwd: str | None = None
    timeout_sec: int = 30


def coerce_argv(argv: Sequence[str] | None) -> list[str]:
    """Normalize a command sequence into a plain argv list."""

    return [str(part) for part in (argv or []) if str(part)]


__all__ = ["CommandSpec", "coerce_argv"]