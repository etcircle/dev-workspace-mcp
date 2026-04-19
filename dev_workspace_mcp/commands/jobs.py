from __future__ import annotations

import threading
from dataclasses import dataclass
from subprocess import Popen

from dev_workspace_mcp.config import get_settings
from dev_workspace_mcp.models.commands import CommandOutputChunk, JobRecord


@dataclass(slots=True)
class ActiveProcess:
    process: Popen
    stdout_thread: threading.Thread | None = None
    stderr_thread: threading.Thread | None = None


class InMemoryJobStore:
    def __init__(self, *, max_output_bytes: int | None = None) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._processes: dict[str, ActiveProcess] = {}
        self._lock = threading.Lock()
        self._max_output_bytes = (
            get_settings().max_command_output_bytes
            if max_output_bytes is None
            else max_output_bytes
        )

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

    def append_output(
        self,
        job_id: str,
        stream: str,
        text: str,
        *,
        max_output_bytes: int | None = None,
    ) -> JobRecord:
        with self._lock:
            job = self._jobs[job_id].model_copy(deep=True)
            if text:
                job.output.append(CommandOutputChunk(stream=stream, text=text))
                output_limit = (
                    self._max_output_bytes
                    if max_output_bytes is None
                    else max_output_bytes
                )
                if output_limit is not None:
                    job.output = _trim_output_chunks(job.output, output_limit)
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


def _trim_output_chunks(
    chunks: list[CommandOutputChunk],
    max_output_bytes: int,
) -> list[CommandOutputChunk]:
    trimmed = [chunk.model_copy(deep=True) for chunk in chunks]
    total_bytes = sum(_chunk_size_bytes(chunk) for chunk in trimmed)
    while trimmed and total_bytes > max_output_bytes:
        first = trimmed[0]
        first_size = _chunk_size_bytes(first)
        overflow = total_bytes - max_output_bytes
        if first_size <= overflow:
            total_bytes -= first_size
            trimmed.pop(0)
            continue
        updated_text = _trim_text_from_start(first.text, overflow)
        total_bytes -= first_size - len(updated_text.encode("utf-8"))
        if updated_text:
            trimmed[0] = first.model_copy(update={"text": updated_text}, deep=True)
        else:
            trimmed.pop(0)
    return trimmed


def _chunk_size_bytes(chunk: CommandOutputChunk) -> int:
    return len(chunk.text.encode("utf-8"))


def _trim_text_from_start(text: str, drop_bytes: int) -> str:
    if drop_bytes <= 0:
        return text
    encoded = text.encode("utf-8")
    if drop_bytes >= len(encoded):
        return ""
    return encoded[drop_bytes:].decode("utf-8", errors="ignore")


__all__ = ["ActiveProcess", "InMemoryJobStore"]
