from __future__ import annotations

import threading
from dataclasses import dataclass
from subprocess import Popen

from dev_workspace_mcp.models.commands import CommandOutputChunk, JobRecord


@dataclass(slots=True)
class ActiveProcess:
    process: Popen
    stdout_thread: threading.Thread | None = None
    stderr_thread: threading.Thread | None = None


class InMemoryJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._processes: dict[str, ActiveProcess] = {}
        self._lock = threading.Lock()

    def save(self, job: JobRecord) -> JobRecord:
        with self._lock:
            self._jobs[job.job_id] = job.model_copy(deep=True)
            return self._jobs[job.job_id].model_copy(deep=True)

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return None if job is None else job.model_copy(deep=True)

    def update(self, job_id: str, **fields) -> JobRecord:
        with self._lock:
            job = self._jobs[job_id].model_copy(update=fields, deep=True)
            self._jobs[job_id] = job
            return job.model_copy(deep=True)

    def append_output(self, job_id: str, stream: str, text: str) -> JobRecord:
        with self._lock:
            job = self._jobs[job_id].model_copy(deep=True)
            if text:
                job.output.append(CommandOutputChunk(stream=stream, text=text))
            self._jobs[job_id] = job
            return job.model_copy(deep=True)

    def attach_process(
        self,
        job_id: str,
        process: Popen,
        *,
        stdout_thread: threading.Thread | None = None,
        stderr_thread: threading.Thread | None = None,
    ) -> None:
        with self._lock:
            self._processes[job_id] = ActiveProcess(
                process=process,
                stdout_thread=stdout_thread,
                stderr_thread=stderr_thread,
            )

    def get_process(self, job_id: str) -> ActiveProcess | None:
        with self._lock:
            return self._processes.get(job_id)

    def pop_process(self, job_id: str) -> ActiveProcess | None:
        with self._lock:
            return self._processes.pop(job_id, None)


__all__ = ["ActiveProcess", "InMemoryJobStore"]
