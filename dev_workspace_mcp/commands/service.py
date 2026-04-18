from __future__ import annotations

import os
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dev_workspace_mcp.commands.allowlist import CommandAllowlist
from dev_workspace_mcp.commands.jobs import InMemoryJobStore
from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.commands import (
    CancelJobResponse,
    CommandTiming,
    GetJobResponse,
    JobRecord,
    RunCommandResponse,
)
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.projects.registry import ProjectRegistry
from dev_workspace_mcp.shared.paths import resolve_relative_path
from dev_workspace_mcp.shared.subprocess import coerce_argv


class CommandService:
    """Runs bounded commands and tracks jobs in memory."""

    def __init__(
        self,
        project_registry: ProjectRegistry,
        *,
        allowlist: CommandAllowlist | None = None,
        job_store: InMemoryJobStore | None = None,
        default_timeout_sec: int = 30,
        enforce_allowlist: bool = True,
    ) -> None:
        self.project_registry = project_registry
        self.allowlist = allowlist or CommandAllowlist()
        self.job_store = job_store or InMemoryJobStore()
        self.default_timeout_sec = default_timeout_sec
        self.enforce_allowlist = enforce_allowlist

    def run_command(
        self,
        project_id: str,
        *,
        argv: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int | None = None,
        background: bool = False,
        preset: str | None = None,
    ) -> RunCommandResponse:
        project = self.project_registry.require(project_id)
        resolved_argv = self._resolve_argv(project_id, preset=preset, argv=argv or [])
        self._ensure_allowed(resolved_argv)
        resolved_cwd = self._resolve_cwd(Path(project.root_path), cwd)
        started_at = datetime.now(UTC)
        timeout = timeout_sec or self.default_timeout_sec

        job = JobRecord(
            job_id=str(uuid4()),
            project_id=project_id,
            argv=resolved_argv,
            cwd=str(resolved_cwd),
            status="running",
            background=background,
            timing=CommandTiming(started_at=started_at),
        )
        job = self.job_store.save(job)

        if background:
            return RunCommandResponse(
                job=self._start_background_job(job, resolved_cwd, env or {}, timeout),
            )
        return RunCommandResponse(
            job=self._run_foreground_job(job, resolved_cwd, env or {}, timeout),
        )

    def get_job(self, project_id: str, job_id: str) -> GetJobResponse:
        job = self._require_job(project_id, job_id)
        return GetJobResponse(job=job)

    def cancel_job(self, project_id: str, job_id: str) -> CancelJobResponse:
        job = self._require_job(project_id, job_id)
        active = self.job_store.get_process(job_id)
        if active is None:
            return CancelJobResponse(job=job)

        if active.process.poll() is None:
            active.process.terminate()
            try:
                active.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                active.process.kill()
                active.process.wait(timeout=2)

        cancelled = self.job_store.update(
            job_id,
            status="cancelled",
            exit_code=active.process.returncode,
            timing=_finish_timing(job.timing),
        )
        return CancelJobResponse(job=cancelled)

    def _resolve_argv(self, project_id: str, *, preset: str | None, argv: list[str]) -> list[str]:
        if preset and argv:
            raise DomainError(
                code=ErrorCode.VALIDATION_ERROR,
                message="Provide either argv or preset, not both.",
            )

        resolved_argv = coerce_argv(argv)
        if preset:
            project = self.project_registry.require(project_id)
            if preset not in project.manifest.presets:
                raise DomainError(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"Unknown preset: {preset}",
                    hint="Use one of the presets exposed by project_snapshot.",
                )
            resolved_argv = coerce_argv(project.manifest.presets[preset])

        if not resolved_argv:
            raise DomainError(
                code=ErrorCode.VALIDATION_ERROR,
                message="run_command requires a non-empty argv or preset.",
            )
        return resolved_argv

    def _ensure_allowed(self, argv: list[str]) -> None:
        if self.enforce_allowlist and not self.allowlist.is_allowed(argv):
            raise DomainError(
                code=ErrorCode.COMMAND_NOT_ALLOWED,
                message=f"Command not allowed: {argv[0]}",
                hint=self.allowlist.explain(argv),
            )

    def _resolve_cwd(self, project_root: Path, cwd: str | None) -> Path:
        if cwd in {None, "", "."}:
            return project_root
        resolved = resolve_relative_path(project_root, cwd).resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise DomainError(
                code=ErrorCode.PATH_NOT_FOUND,
                message=f"Command cwd does not exist: {cwd}",
            )
        return resolved

    def _run_foreground_job(
        self,
        job: JobRecord,
        cwd: Path,
        env: dict[str, str],
        timeout: int,
    ) -> JobRecord:
        try:
            result = subprocess.run(
                job.argv,
                cwd=str(cwd),
                env=_merged_env(env),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if result.stdout:
                self.job_store.append_output(job.job_id, "stdout", result.stdout)
            if result.stderr:
                self.job_store.append_output(job.job_id, "stderr", result.stderr)
            return self.job_store.update(
                job.job_id,
                status="succeeded" if result.returncode == 0 else "failed",
                exit_code=result.returncode,
                timing=_finish_timing(job.timing),
            )
        except subprocess.TimeoutExpired as exc:
            if exc.stdout:
                self.job_store.append_output(job.job_id, "stdout", exc.stdout)
            if exc.stderr:
                self.job_store.append_output(job.job_id, "stderr", exc.stderr)
            return self.job_store.update(
                job.job_id,
                status="timed_out",
                timing=_finish_timing(job.timing),
            )

    def _start_background_job(
        self,
        job: JobRecord,
        cwd: Path,
        env: dict[str, str],
        timeout: int,
    ) -> JobRecord:
        process = subprocess.Popen(
            job.argv,
            cwd=str(cwd),
            env=_merged_env(env),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        current = self.job_store.update(job.job_id, pid=process.pid)

        stdout_thread = threading.Thread(
            target=self._capture_stream,
            args=(job.job_id, "stdout", process.stdout),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._capture_stream,
            args=(job.job_id, "stderr", process.stderr),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        self.job_store.attach_process(
            job.job_id,
            process,
            stdout_thread=stdout_thread,
            stderr_thread=stderr_thread,
        )
        waiter = threading.Thread(
            target=self._wait_for_background_job,
            args=(job.job_id, timeout),
            daemon=True,
        )
        waiter.start()
        return current

    def _capture_stream(self, job_id: str, stream: str, handle) -> None:
        if handle is None:
            return
        try:
            text = handle.read()
            if text:
                self.job_store.append_output(job_id, stream, text)
        finally:
            handle.close()

    def _wait_for_background_job(self, job_id: str, timeout: int) -> None:
        active = self.job_store.get_process(job_id)
        if active is None:
            return

        try:
            exit_code = active.process.wait(timeout=timeout)
            status = "succeeded" if exit_code == 0 else "failed"
        except subprocess.TimeoutExpired:
            active.process.kill()
            active.process.wait(timeout=2)
            exit_code = active.process.returncode
            status = "timed_out"

        if active.stdout_thread is not None:
            active.stdout_thread.join(timeout=1)
        if active.stderr_thread is not None:
            active.stderr_thread.join(timeout=1)

        existing = self.job_store.get(job_id)
        if existing is None:
            return
        final_status = existing.status if existing.status == "cancelled" else status
        self.job_store.update(
            job_id,
            status=final_status,
            exit_code=exit_code,
            timing=_finish_timing(existing.timing),
        )
        self.job_store.pop_process(job_id)

    def _require_job(self, project_id: str, job_id: str) -> JobRecord:
        job = self.job_store.get(job_id)
        if job is None or job.project_id != project_id:
            raise DomainError(
                code=ErrorCode.JOB_NOT_FOUND,
                message=f"Unknown job_id: {job_id}",
                hint="Use the job_id returned from run_command.",
            )
        return job



def _merged_env(env: dict[str, str]) -> dict[str, str]:
    merged = os.environ.copy()
    merged.update(env)
    return merged



def _finish_timing(timing: CommandTiming) -> CommandTiming:
    finished_at = datetime.now(UTC)
    started_at = timing.started_at or finished_at
    duration_ms = max(int((finished_at - started_at).total_seconds() * 1000), 0)
    return timing.model_copy(
        update={
            "finished_at": finished_at,
            "duration_ms": duration_ms,
        },
        deep=True,
    )


__all__ = ["CommandService"]
