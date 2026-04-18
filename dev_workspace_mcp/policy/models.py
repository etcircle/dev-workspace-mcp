from __future__ import annotations

from fnmatch import fnmatch
from typing import Literal

from pydantic import BaseModel, Field


class PathsPolicy(BaseModel):
    writable_roots: list[str] = Field(default_factory=lambda: ["src", "tests", ".devworkspace"])
    follow_symlinks_for_read: bool = False
    follow_symlinks_for_write: bool = False


class EnvPolicy(BaseModel):
    inherit: bool = False
    allow: list[str] = Field(default_factory=lambda: ["PATH", "HOME", "LANG", "LC_ALL"])
    redact: list[str] = Field(
        default_factory=lambda: [
            "*TOKEN*",
            "*SECRET*",
            "*PASSWORD*",
            "AWS_*",
            "GITHUB_TOKEN",
        ]
    )

    def is_redacted(self, name: str) -> bool:
        upper_name = name.upper()
        return any(fnmatch(upper_name, pattern.upper()) for pattern in self.redact)


class CommandRule(BaseModel):
    allow_args: list[list[str]] = Field(default_factory=list)
    deny_args: list[list[str]] = Field(default_factory=list)
    max_seconds: int | None = None
    max_output_bytes: int | None = None
    network: bool | None = None


class CommandPolicy(BaseModel):
    default: Literal["allow", "deny"] = "deny"
    commands: dict[str, CommandRule] = Field(default_factory=dict)


class NetworkPolicy(BaseModel):
    default: Literal["allow", "deny"] = "deny"
    allow_localhost: bool = True
    allowed_hosts: list[str] = Field(default_factory=list)


class EffectivePolicySummary(BaseModel):
    writable_roots: list[str] = Field(default_factory=list)
    follow_symlinks_for_read: bool = False
    follow_symlinks_for_write: bool = False
    env_inherit: bool = False
    env_allow: list[str] = Field(default_factory=list)
    command_default: Literal["allow", "deny"] = "deny"
    configured_commands: list[str] = Field(default_factory=list)
    network_default: Literal["allow", "deny"] = "deny"
    allow_localhost: bool = True
    allowed_hosts: list[str] = Field(default_factory=list)


class ProjectPolicy(BaseModel):
    version: int = 1
    paths: PathsPolicy = Field(default_factory=PathsPolicy)
    env: EnvPolicy = Field(default_factory=EnvPolicy)
    network: NetworkPolicy = Field(default_factory=NetworkPolicy)
    command_policy: CommandPolicy = Field(default_factory=CommandPolicy)

    def summary(self) -> EffectivePolicySummary:
        return EffectivePolicySummary(
            writable_roots=list(self.paths.writable_roots),
            follow_symlinks_for_read=self.paths.follow_symlinks_for_read,
            follow_symlinks_for_write=self.paths.follow_symlinks_for_write,
            env_inherit=self.env.inherit,
            env_allow=list(self.env.allow),
            command_default=self.command_policy.default,
            configured_commands=sorted(self.command_policy.commands.keys()),
            network_default=self.network.default,
            allow_localhost=self.network.allow_localhost,
            allowed_hosts=list(self.network.allowed_hosts),
        )


__all__ = [
    "CommandPolicy",
    "CommandRule",
    "EffectivePolicySummary",
    "EnvPolicy",
    "NetworkPolicy",
    "PathsPolicy",
    "ProjectPolicy",
]
