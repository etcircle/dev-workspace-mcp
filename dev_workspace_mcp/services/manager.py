from __future__ import annotations

import os
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dev_workspace_mcp.commands.allowlist import evaluate_command_policy
from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.models.projects import ProjectRecord, ServiceDefinition
from dev_workspace_mcp.models.services import (
    GetLogsResponse,
    ListServicesResponse,
    ServiceActionResponse,
    ServicePort,
    ServiceRecord,
    ServiceRuntimeState,
    ServiceStatusResponse,
)
from dev_workspace_mcp.policy.env import build_subprocess_env
from dev_workspace_mcp.projects.registry import ProjectRegistry
from dev_workspace_mcp.services.health import ServiceHealthChecker
from dev_workspace_mcp.services.logs import ServiceLogStore
from dev_workspace_mcp.services.process_store import InMemoryProcessStore
from dev_workspace_mcp.shared.paths import resolve_project_path
from dev_workspace_mcp.shared.security import redact_secrets


class ServiceManager:
    """Manage manifest-declared dev services, logs, and runtime state."""

    def __init__(
        self,
        project_registry: ProjectRegistry,
        *,
        process_store: InMemoryProcessStore | None = None,
        log_store: ServiceLogStore | None = None,
        health_checker: ServiceHealthChecker | None = None,
    ) -> None:
        self.project_registry = project_registry
        self.process_store = process_store or InMemoryProcessStore()
        self.log_store = log_store or ServiceLogStore()
        self.health_checker = health_checker or ServiceHealthChecker()

    def list_services(self, project_id: str) -> ListServicesResponse:
        project = self.project_registry.require(project_id)
        services = [
            self._current_record(project.project_id, name, definition)
            for name, definition in sorted(project.manifest.services.items())
        ]
        return ListServicesResponse(services=services)

    def service_status(self, project_id: str, service_name: str) -> ServiceStatusResponse:
        project, definition = self._project_and_definition(project_id, service_name)
        record = self._current_record(project_id, service_name, definition)
        record = self._apply_health(project, definition, record)
        self.process_store.save(self._service_key(project_id, service_name), record)
        return ServiceStatusResponse(service=record)

    def start_service(self, project_id: str, service_name: str) -> ServiceActionResponse:
        project, definition = self._project_and_definition(project_id, service_name)
        key = self._service_key(project_id, service_name)
        current = self._current_record(project_id, service_name, definition)
        active = self.process_store.get_process(key)
        if active is not None and active.process.poll() is None:
            record = self._apply_health(project, definition, current)
            return ServiceActionResponse(service=record)

        if not definition.start:
            raise DomainError(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"Service '{service_name}' does not define a start command.",
            )

        self._ensure_command_allowed(project, definition.start, service_name=service_name)
        cwd = self._resolve_service_cwd(Path(project.root_path), definition)
        process = subprocess.Popen(
            definition.start,
            cwd=str(cwd),
            env=build_subprocess_env(os.environ, project.policy.env),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        instance_id = str(uuid4())
        runtime = current.runtime.model_copy(
            update={
                "status": "running",
                "service_instance_id": instance_id,
                "pid": process.pid,
                "command": list(definition.start),
                "cwd": str(cwd),
                "last_started_at": datetime.now(UTC),
                "health": current.runtime.health,
            },
            deep=True,
        )
        record = current.model_copy(update={"runtime": runtime}, deep=True)
        record = self._apply_health(project, definition, record)
        record = self.process_store.save(key, record)

        stdout_thread = threading.Thread(
            target=self._capture_stream,
            args=(key, "stdout", process.stdout, project.policy.env),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._capture_stream,
            args=(key, "stderr", process.stderr, project.policy.env),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        self.process_store.attach_process(
            key,
            process,
            stdout_thread=stdout_thread,
            stderr_thread=stderr_thread,
        )
        waiter = threading.Thread(
            target=self._watch_service_exit,
            args=(project_id, service_name, definition, instance_id),
            daemon=True,
        )
        waiter.start()
        return ServiceActionResponse(service=record)

    def stop_service(self, project_id: str, service_name: str) -> ServiceActionResponse:
        project, definition = self._project_and_definition(project_id, service_name)
        key = self._service_key(project_id, service_name)
        current = self._current_record(project_id, service_name, definition)
        active = self.process_store.get_process(key)

        if active is not None and active.process.poll() is None:
            active.process.terminate()
            try:
                active.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                active.process.kill()
                active.process.wait(timeout=2)

        runtime = current.runtime.model_copy(
            update={
                "status": "stopped",
                "service_instance_id": None,
                "pid": None,
                "last_stopped_at": datetime.now(UTC),
            },
            deep=True,
        )
        record = current.model_copy(update={"runtime": runtime}, deep=True)
        record = self._apply_health(project, definition, record)
        self.process_store.save(key, record)
        self.process_store.pop_process(key)
        return ServiceActionResponse(service=record)

    def restart_service(self, project_id: str, service_name: str) -> ServiceActionResponse:
        project, definition = self._project_and_definition(project_id, service_name)
        current = self._current_record(project_id, service_name, definition)
        restart_count = current.runtime.restart_count + 1
        self.stop_service(project_id, service_name)
        started = self.start_service(project_id, service_name).service
        runtime = started.runtime.model_copy(update={"restart_count": restart_count}, deep=True)
        record = started.model_copy(update={"runtime": runtime}, deep=True)
        self.process_store.save(self._service_key(project_id, service_name), record)
        return ServiceActionResponse(service=record)

    def get_logs(
        self,
        project_id: str,
        service_name: str,
        *,
        offset: int = 0,
        limit: int = 200,
    ) -> GetLogsResponse:
        self._project_and_definition(project_id, service_name)
        key = self._service_key(project_id, service_name)
        return self.log_store.slice(key, offset=offset, limit=limit)

    def _project_and_definition(
        self,
        project_id: str,
        service_name: str,
    ):
        project = self.project_registry.require(project_id)
        definition = project.manifest.services.get(service_name)
        if definition is None:
            raise DomainError(
                code=ErrorCode.SERVICE_NOT_FOUND,
                message=f"Unknown service: {service_name}",
                hint="Use list_services or project_snapshot to find declared services.",
            )
        return project, definition

    def _current_record(
        self,
        project_id: str,
        service_name: str,
        definition: ServiceDefinition,
    ) -> ServiceRecord:
        key = self._service_key(project_id, service_name)
        current = self.process_store.get(key)
        if current is not None:
            active = self.process_store.get_process(key)
            process_finished = active is not None and active.process.poll() is not None
            if process_finished and current.runtime.status == "running":
                runtime = current.runtime.model_copy(
                    update={
                        "status": "failed" if active.process.returncode else "stopped",
                        "service_instance_id": None,
                        "pid": None,
                        "last_stopped_at": datetime.now(UTC),
                    },
                    deep=True,
                )
                current = current.model_copy(update={"runtime": runtime}, deep=True)
                self.process_store.save(key, current)
                self.process_store.pop_process(key)
            return current

        project = self.project_registry.require(project_id)
        project_root = Path(project.root_path)
        cwd = self._resolve_service_cwd(project_root, definition)
        return ServiceRecord(
            project_id=project_id,
            service_name=service_name,
            display_name=service_name,
            ports=[ServicePort(port=port) for port in definition.ports],
            runtime=ServiceRuntimeState(
                status="stopped",
                command=list(definition.start),
                cwd=str(cwd),
            ),
        )

    def _apply_health(
        self,
        project: ProjectRecord,
        definition: ServiceDefinition,
        record: ServiceRecord,
    ) -> ServiceRecord:
        health = self.health_checker.check(
            definition,
            record,
            project_root=Path(project.root_path),
            policy=project.policy,
        )
        runtime = record.runtime.model_copy(update={"health": health}, deep=True)
        return record.model_copy(update={"runtime": runtime}, deep=True)

    def _capture_stream(self, key: str, stream: str, handle, env_policy) -> None:
        if handle is None:
            return
        try:
            for line in iter(handle.readline, ""):
                message = redact_secrets(line.rstrip("\n"), env_policy=env_policy)
                self.log_store.append(key, stream, message)
        finally:
            handle.close()

    def _watch_service_exit(
        self,
        project_id: str,
        service_name: str,
        definition: ServiceDefinition,
        instance_id: str,
    ) -> None:
        key = self._service_key(project_id, service_name)
        active = self.process_store.get_process(key)
        if active is None:
            return
        exit_code = active.process.wait()
        if active.stdout_thread is not None:
            active.stdout_thread.join(timeout=1)
        if active.stderr_thread is not None:
            active.stderr_thread.join(timeout=1)

        current = self.process_store.get(key)
        if current is None or current.runtime.service_instance_id != instance_id:
            return
        status = "stopped" if exit_code == 0 else "failed"
        runtime = current.runtime.model_copy(
            update={
                "status": status,
                "pid": None,
                "last_stopped_at": datetime.now(UTC),
            },
            deep=True,
        )
        record = current.model_copy(update={"runtime": runtime}, deep=True)
        project = self.project_registry.require(project_id)
        record = self._apply_health(project, definition, record)
        self.process_store.save(key, record)
        self.process_store.pop_process(key)

    def _resolve_service_cwd(self, project_root: Path, definition: ServiceDefinition) -> Path:
        cwd = resolve_project_path(project_root, definition.cwd)
        if not cwd.exists() or not cwd.is_dir():
            raise DomainError(
                code=ErrorCode.PATH_NOT_FOUND,
                message=f"Service cwd does not exist: {definition.cwd}",
            )
        return cwd

    def _ensure_command_allowed(
        self,
        project: ProjectRecord,
        argv: list[str],
        *,
        service_name: str,
    ) -> None:
        decision = evaluate_command_policy(project.policy, argv)
        if not decision.allowed:
            raise DomainError(
                code=ErrorCode.POLICY_DENIED,
                message=f"Service '{service_name}' start blocked. {decision.message}",
                hint=decision.hint,
                details={"argv": list(argv), "service_name": service_name},
            )

    @staticmethod
    def _service_key(project_id: str, service_name: str) -> str:
        return f"{project_id}:{service_name}"


__all__ = ["ServiceManager"]
