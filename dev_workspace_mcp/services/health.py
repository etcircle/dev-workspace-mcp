from __future__ import annotations

import os
import subprocess
from pathlib import Path

from dev_workspace_mcp.commands.allowlist import evaluate_command_policy
from dev_workspace_mcp.http_tools.local_client import LocalHttpClient
from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.common import ServiceHealth
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.models.projects import ServiceDefinition
from dev_workspace_mcp.models.services import ServiceRecord
from dev_workspace_mcp.policy.env import build_subprocess_env
from dev_workspace_mcp.policy.models import ProjectPolicy
from dev_workspace_mcp.shared.paths import resolve_project_path
from dev_workspace_mcp.shared.security import redact_secrets


class ServiceHealthChecker:
    """Compute a small health view for managed services."""

    def __init__(self, *, http_client: LocalHttpClient | None = None) -> None:
        self.http_client = http_client or LocalHttpClient()

    def check(
        self,
        service_definition: ServiceDefinition,
        service_record: ServiceRecord,
        *,
        project_root: Path,
        policy: ProjectPolicy,
    ) -> ServiceHealth:
        health = service_definition.health
        if service_record.runtime.status != "running":
            if service_record.runtime.status == "failed":
                return ServiceHealth(status="unhealthy", message="Service process failed.")
            return ServiceHealth(status="unknown", message="Service is not running.")
        if health is None or health.type == "none":
            return ServiceHealth(status="healthy", message="Service process is running.")

        if health.type == "http" and health.url:
            try:
                response = self.http_client.request(
                    method="GET",
                    url=health.url,
                    timeout_sec=2,
                    network_policy=policy.network,
                )
            except DomainError as exc:
                if exc.code == ErrorCode.HTTP_REQUEST_FAILED:
                    return ServiceHealth(status="unhealthy", message=str(exc))
                raise
            ok = health.expect_status is None or response.status_code == health.expect_status
            return ServiceHealth(
                status="healthy" if ok else "unhealthy",
                message=f"HTTP {response.status_code} from {health.url}",
            )

        if health.type == "command" and health.argv:
            decision = evaluate_command_policy(policy, health.argv)
            if not decision.allowed:
                raise DomainError(
                    code=ErrorCode.POLICY_DENIED,
                    message=decision.message,
                    hint=decision.hint,
                    details={"argv": list(health.argv)},
                )

            cwd = resolve_project_path(project_root, service_definition.cwd)
            if not cwd.exists() or not cwd.is_dir():
                raise DomainError(
                    code=ErrorCode.PATH_NOT_FOUND,
                    message=f"Service cwd does not exist: {service_definition.cwd}",
                )

            timeout = 5
            if decision.rule is not None and decision.rule.max_seconds is not None:
                timeout = min(timeout, decision.rule.max_seconds)

            try:
                result = subprocess.run(
                    health.argv,
                    cwd=str(cwd),
                    env=build_subprocess_env(os.environ, policy.env),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
            except FileNotFoundError as exc:
                return ServiceHealth(
                    status="unhealthy",
                    message=f"health command failed to start: {exc}",
                )
            except OSError as exc:
                return ServiceHealth(
                    status="unhealthy",
                    message=f"health command failed to start: {exc}",
                )
            except subprocess.TimeoutExpired:
                return ServiceHealth(
                    status="unhealthy",
                    message=f"timed out after {timeout} seconds",
                )

            message = (result.stdout or result.stderr or f"exit={result.returncode}").strip()
            return ServiceHealth(
                status="healthy" if result.returncode == 0 else "unhealthy",
                message=redact_secrets(message, env_policy=policy.env),
            )

        return ServiceHealth(status="unknown", message="Unsupported health configuration.")


__all__ = ["ServiceHealthChecker"]
