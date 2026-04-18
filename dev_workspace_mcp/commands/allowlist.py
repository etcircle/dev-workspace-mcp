from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

DEFAULT_ALLOWED_COMMANDS = {
    "python",
    "python3",
    "pytest",
    "uv",
    "git",
    "node",
    "npm",
    "pnpm",
    "npx",
    "echo",
    "true",
    "false",
}


class CommandAllowlist:
    """Small command policy object for bounded local execution."""

    def __init__(self, allowed_commands: Iterable[str] | None = None) -> None:
        commands = allowed_commands if allowed_commands is not None else DEFAULT_ALLOWED_COMMANDS
        self._allowed_commands = {command for command in commands if command}

    def is_allowed(self, argv: list[str]) -> bool:
        """Return whether a command should be allowed under the current policy."""

        if not argv:
            return False
        command = Path(argv[0]).name
        return command in self._allowed_commands

    def explain(self, argv: list[str]) -> str:
        """Provide a short explanation for policy decisions."""

        return "allowed" if self.is_allowed(argv) else "blocked by allowlist"


__all__ = ["CommandAllowlist", "DEFAULT_ALLOWED_COMMANDS"]
