from __future__ import annotations

from collections.abc import Mapping

from dev_workspace_mcp.policy.models import EnvPolicy


def build_subprocess_env(
    base_env: Mapping[str, str],
    env_policy: EnvPolicy,
    *,
    overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build a bounded subprocess environment from policy and explicit overrides."""

    if env_policy.inherit:
        env = dict(base_env)
    else:
        env = {name: value for name, value in base_env.items() if name in env_policy.allow}

    for name in env_policy.allow:
        if name in base_env:
            env[name] = base_env[name]

    if overrides:
        for name, value in overrides.items():
            if env_policy.is_redacted(name):
                continue
            if env_policy.inherit or name in env_policy.allow:
                env[name] = value

    for name in list(env):
        if env_policy.is_redacted(name):
            env.pop(name, None)

    return env


__all__ = ["build_subprocess_env"]
