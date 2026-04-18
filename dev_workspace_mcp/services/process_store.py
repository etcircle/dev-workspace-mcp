from __future__ import annotations

import threading
from dataclasses import dataclass
from subprocess import Popen

from dev_workspace_mcp.models.services import ServiceRecord


@dataclass(slots=True)
class ActiveServiceProcess:
    process: Popen
    stdout_thread: threading.Thread | None = None
    stderr_thread: threading.Thread | None = None


class InMemoryProcessStore:
    """Simple in-memory process registry for service metadata."""

    def __init__(self) -> None:
        self._services: dict[str, ServiceRecord] = {}
        self._processes: dict[str, ActiveServiceProcess] = {}
        self._lock = threading.Lock()

    def save(self, key: str, service: ServiceRecord) -> ServiceRecord:
        with self._lock:
            self._services[key] = service.model_copy(deep=True)
            return self._services[key].model_copy(deep=True)

    def get(self, key: str) -> ServiceRecord | None:
        with self._lock:
            service = self._services.get(key)
            return None if service is None else service.model_copy(deep=True)

    def list(self, prefix: str | None = None) -> list[ServiceRecord]:
        with self._lock:
            items = self._services.items()
            if prefix is not None:
                items = [(key, value) for key, value in items if key.startswith(prefix)]
            return [service.model_copy(deep=True) for _, service in items]

    def attach_process(
        self,
        key: str,
        process: Popen,
        *,
        stdout_thread: threading.Thread | None = None,
        stderr_thread: threading.Thread | None = None,
    ) -> None:
        with self._lock:
            self._processes[key] = ActiveServiceProcess(
                process=process,
                stdout_thread=stdout_thread,
                stderr_thread=stderr_thread,
            )

    def get_process(self, key: str) -> ActiveServiceProcess | None:
        with self._lock:
            return self._processes.get(key)

    def pop_process(self, key: str) -> ActiveServiceProcess | None:
        with self._lock:
            return self._processes.pop(key, None)


__all__ = ["ActiveServiceProcess", "InMemoryProcessStore"]
