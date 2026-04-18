from __future__ import annotations

import subprocess
from pathlib import Path

import httpx

from dev_workspace_mcp.models.common import ServiceHealth
from dev_workspace_mcp.models.projects import ServiceDefinition
from dev_workspace_mcp.models.services import ServiceRecord


class ServiceHealthChecker:
    """Compute a small health view for managed services."""

    def check(
        self,
        service_definition: ServiceDefinition,
        service_record: ServiceRecord,
        *,
        project_root: Path,
    ) -> ServiceHealth:
        health = service_definition.health
        if health is None or health.type == "none":
            if service_record.runtime.status == "running":
                return ServiceHealth(status="healthy", message="Service process is running.")
            if service_record.runtime.status == "failed":
                return ServiceHealth(status="unhealthy", message="Service process failed.")
            return ServiceHealth(status="unknown", message="Service is not running.")

        if health.type == "http" and health.url:
            try:
                response = httpx.get(health.url, timeout=2.0)
                ok = health.expect_status is None or response.status_code == health.expect_status
                return ServiceHealth(
                    status="healthy" if ok else "unhealthy",
                    message=f"HTTP {response.status_code} from {health.url}",
                )
            except httpx.HTTPError as exc:
                return ServiceHealth(status="unhealthy", message=str(exc))

        if health.type == "command" and health.argv:
            cwd = project_root / service_definition.cwd
            result = subprocess.run(
                health.argv,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return ServiceHealth(
                status="healthy" if result.returncode == 0 else "unhealthy",
                message=(result.stdout or result.stderr or f"exit={result.returncode}").strip(),
            )

        return ServiceHealth(status="unknown", message="Unsupported health configuration.")


__all__ = ["ServiceHealthChecker"]
