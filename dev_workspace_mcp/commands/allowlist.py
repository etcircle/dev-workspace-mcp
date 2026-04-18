from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from dev_workspace_mcp.policy.models import CommandRule, ProjectPolicy

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


@dataclass(frozen=True, slots=True)
class CommandPolicyDecision:
    allowed: bool
    message: str
    hint: str | None = None
    rule: CommandRule | None = None


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


def evaluate_command_policy(policy: ProjectPolicy, argv: list[str]) -> CommandPolicyDecision:
    if not argv:
        return CommandPolicyDecision(
            allowed=False,
            message="Command policy requires a non-empty argv.",
        )

    command_name = Path(argv[0]).name
    args = list(argv[1:])
    command_policy = policy.command_policy
    rule = command_policy.commands.get(command_name)

    if rule is None:
        if command_policy.default == "allow":
            return CommandPolicyDecision(
                allowed=True,
                message=f"Project policy allows '{command_name}' by default.",
            )
        return CommandPolicyDecision(
            allowed=False,
            message=f"Project policy denies command '{command_name}'.",
            hint="Add a matching rule to .devworkspace/policy.yaml if this command is required.",
        )

    if _matches_any(args, rule.deny_args):
        return CommandPolicyDecision(
            allowed=False,
            message=f"Project policy denies this argv for '{command_name}'.",
            hint="The argv matched a deny_args rule in .devworkspace/policy.yaml.",
            rule=rule,
        )

    if rule.allow_args and not _matches_any(args, rule.allow_args):
        return CommandPolicyDecision(
            allowed=False,
            message=f"Project policy does not allow this argv for '{command_name}'.",
            hint="The argv did not match any allow_args rule in .devworkspace/policy.yaml.",
            rule=rule,
        )

    return CommandPolicyDecision(
        allowed=True,
        message=f"Project policy allows '{command_name}'.",
        rule=rule,
    )


def _matches_any(args: list[str], patterns: list[list[str]]) -> bool:
    return any(_matches_pattern(args, pattern) for pattern in patterns)


def _matches_pattern(args: list[str], pattern: list[str]) -> bool:
    if len(pattern) > len(args):
        return False
    return args[: len(pattern)] == pattern


__all__ = [
    "CommandAllowlist",
    "CommandPolicyDecision",
    "DEFAULT_ALLOWED_COMMANDS",
    "evaluate_command_policy",
]
