from __future__ import annotations

import os
import subprocess
from pathlib import Path

from dev_workspace_mcp.commands.allowlist import CommandAllowlist, evaluate_command_policy
from dev_workspace_mcp.files.validation import validate_relative_path
from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.models.probes import ListProbesResponse, ProbeRunResult, ProbeSummary
from dev_workspace_mcp.policy.env import build_subprocess_env
from dev_workspace_mcp.projects.registry import ProjectRegistry
from dev_workspace_mcp.shared.paths import resolve_project_path
from dev_workspace_mcp.shared.security import redact_secrets


class ProbeService:
    """Execute manifest-declared diagnostic probes with bounded runtime."""

    def __init__(
        self,
        project_registry: ProjectRegistry,
        *,
        allowlist: CommandAllowlist | None = None,
        enforce_allowlist: bool = True,
    ) -> None:
        self.project_registry = project_registry
        self.allowlist = allowlist or CommandAllowlist()
        self.enforce_allowlist = enforce_allowlist

    def list_probes(self, project_id: str) -> ListProbesResponse:
        project = self.project_registry.require(project_id)
        probes = [
            ProbeSummary(
                name=name,
                cwd=definition.cwd,
                argv=list(definition.argv),
                timeout_sec=definition.timeout_sec,
            )
            for name, definition in sorted(project.manifest.probes.items())
        ]
        return ListProbesResponse(probes=probes)

    def run_probe(self, project_id: str, probe_name: str) -> ProbeRunResult:
        project = self.project_registry.require(project_id)
        definition = project.manifest.probes.get(probe_name)
        if definition is None:
            raise DomainError(
                code=ErrorCode.PROBE_NOT_FOUND,
                message=f"Unknown probe: {probe_name}",
                hint="Use list_probes or project_snapshot to find declared probes.",
            )
        if not definition.argv:
            raise DomainError(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"Probe '{probe_name}' does not define an argv command.",
            )

        self._ensure_allowed(project_id, project.policy, definition.argv)
        cwd = self._resolve_probe_cwd(Path(project.root_path), definition.cwd)
        timeout = definition.timeout_sec
        decision = evaluate_command_policy(project.policy, definition.argv)
        if decision.rule is not None and decision.rule.max_seconds is not None:
            timeout = min(timeout, decision.rule.max_seconds)

        try:
            result = subprocess.run(
                definition.argv,
                cwd=str(cwd),
                env=build_subprocess_env(os.environ, project.policy.env),
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise DomainError(
                code=ErrorCode.JOB_TIMEOUT,
                message=f"Probe '{probe_name}' timed out after {timeout} seconds.",
                details={"probe_name": probe_name, "timeout_sec": timeout},
            ) from exc

        return ProbeRunResult(
            probe_name=probe_name,
            ok=result.returncode == 0,
            cwd=validate_relative_path(definition.cwd),
            argv=list(definition.argv),
            timeout_sec=timeout,
            exit_code=result.returncode,
            stdout=redact_secrets(result.stdout, env_policy=project.policy.env),
            stderr=redact_secrets(result.stderr, env_policy=project.policy.env),
        )

    def _ensure_allowed(self, project_id: str, policy, argv: list[str]) -> None:
        if self.enforce_allowlist and not self.allowlist.is_allowed(argv):
            raise DomainError(
                code=ErrorCode.COMMAND_NOT_ALLOWED,
                message=f"Probe command is not allowed: {argv[0]}",
                hint=self.allowlist.explain(argv),
                details={"project_id": project_id, "argv": list(argv)},
            )

        decision = evaluate_command_policy(policy, argv)
        if not decision.allowed:
            raise DomainError(
                code=ErrorCode.POLICY_DENIED,
                message=decision.message,
                hint=decision.hint,
                details={"project_id": project_id, "argv": list(argv)},
            )

    def _resolve_probe_cwd(self, project_root: Path, relative_cwd: str) -> Path:
        normalized = validate_relative_path(relative_cwd)
        cwd = resolve_project_path(project_root, normalized)
        if not cwd.exists() or not cwd.is_dir():
            raise DomainError(
                code=ErrorCode.PATH_NOT_FOUND,
                message=f"Probe cwd does not exist: {relative_cwd}",
            )
        return cwd


__all__ = ["ProbeService"]
