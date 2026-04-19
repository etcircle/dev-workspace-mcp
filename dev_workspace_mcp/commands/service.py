from __future__ import annotations

import os
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dev_workspace_mcp.commands.allowlist import (
    CommandAllowlist,
    CommandPolicyDecision,
    evaluate_command_policy,
)
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
from dev_workspace_mcp.models.projects import ProjectRecord
from dev_workspace_mcp.policy.env import build_subprocess_env
from dev_workspace_mcp.policy.models import CommandRule, EnvPolicy
from dev_workspace_mcp.projects.registry import ProjectRegistry
from dev_workspace_mcp.shared.paths import resolve_project_path
from dev_workspace_mcp.shared.security import redact_secrets
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
        settings = project_registry.settings
        self.max_output_bytes = getattr(settings, "max_command_output_bytes", 200_000)
        self.stream_chunk_bytes = getattr(settings, "subprocess_stream_chunk_bytes", 4096)
        self.stream_redaction_tail_chars = max(self.stream_chunk_bytes * 4, 256)
        self.stream_flush_threshold_chars = max(
            self.stream_redaction_tail_chars * 4,
            self.stream_chunk_bytes * 8,
        )
        self.job_store = job_store or InMemoryJobStore(max_output_bytes=self.max_output_bytes)
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
        resolved_argv = self._resolve_argv(project, preset=preset, argv=argv or [])
        decision = self._ensure_allowed(project, resolved_argv)
        resolved_cwd = self._resolve_cwd(Path(project.root_path), cwd)
        started_at = datetime.now(UTC)
        timeout = self._effective_timeout(timeout_sec, decision.rule)
        subprocess_env = build_subprocess_env(os.environ, project.policy.env, overrides=env or {})

        job = JobRecord(
            job_id=str(uuid4()),
            project_id=project_id,
            argv=resolved_argv,
            cwd=str(resolved_cwd),
            status="running",
            background=background,
            timing=CommandTiming(started_at=started_at),
        )

        if background:
            return RunCommandResponse(
                job=self._start_background_job(
                    job,
                    resolved_cwd,
                    subprocess_env,
                    timeout,
                    env_policy=project.policy.env,
                    max_output_bytes=self._max_output_bytes(decision.rule),
                ),
            )
        return RunCommandResponse(
            job=self._run_foreground_job(
                job,
                resolved_cwd,
                subprocess_env,
                timeout,
                env_policy=project.policy.env,
                max_output_bytes=self._max_output_bytes(decision.rule),
            ),
        )

    def get_job(self, project_id: str, job_id: str) -> GetJobResponse:
        job = self._require_job(project_id, job_id)
        return GetJobResponse(job=job)

    def cancel_job(self, project_id: str, job_id: str) -> CancelJobResponse:
        job = self._require_job(project_id, job_id)
        active = self.job_store.get_process(job_id)
        if active is None:
            return CancelJobResponse(job=job)

        if active.process.poll() is not None:
            if active.stdout_thread is not None:
                active.stdout_thread.join(timeout=1)
            if active.stderr_thread is not None:
                active.stderr_thread.join(timeout=1)
            completed = self.job_store.update(
                job_id,
                status=self._completed_process_status(job, active.process.returncode),
                exit_code=active.process.returncode,
                timing=_finish_timing(job.timing),
            )
            self.job_store.pop_process(job_id)
            return CancelJobResponse(job=completed)

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

    def _resolve_argv(
        self,
        project: ProjectRecord,
        *,
        preset: str | None,
        argv: list[str],
    ) -> list[str]:
        if preset and argv:
            raise DomainError(
                code=ErrorCode.VALIDATION_ERROR,
                message="Provide either argv or preset, not both.",
            )

        resolved_argv = coerce_argv(argv)
        if preset:
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

    def _ensure_allowed(self, project: ProjectRecord, argv: list[str]) -> CommandPolicyDecision:
        if self.enforce_allowlist and not self.allowlist.is_allowed(argv):
            raise DomainError(
                code=ErrorCode.COMMAND_NOT_ALLOWED,
                message=f"Command not allowed: {argv[0]}",
                hint=self.allowlist.explain(argv),
            )

        decision = evaluate_command_policy(project.policy, argv)
        if not decision.allowed:
            raise DomainError(
                code=ErrorCode.POLICY_DENIED,
                message=decision.message,
                hint=decision.hint,
                details={"argv": list(argv)},
            )
        return decision

    def _resolve_cwd(self, project_root: Path, cwd: str | None) -> Path:
        if cwd in {None, "", "."}:
            return project_root
        resolved = resolve_project_path(project_root, cwd)
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
        *,
        env_policy: EnvPolicy,
        max_output_bytes: int | None,
    ) -> JobRecord:
        try:
            process = subprocess.Popen(
                job.argv,
                cwd=str(cwd),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except OSError as exc:
            raise DomainError(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"Command failed to start: {exc}",
                hint="Verify the executable exists and is available on PATH.",
                details={"argv": list(job.argv), "cwd": str(cwd)},
            ) from exc
        job = self.job_store.save(job)
        stdout_thread, stderr_thread = self._start_output_threads(
            job.job_id,
            process,
            env_policy=env_policy,
            max_output_bytes=max_output_bytes,
        )
        try:
            exit_code = process.wait(timeout=timeout)
            status = "succeeded" if exit_code == 0 else "failed"
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
            exit_code = process.returncode
            status = "timed_out"
        finally:
            if stdout_thread is not None:
                stdout_thread.join(timeout=1)
            if stderr_thread is not None:
                stderr_thread.join(timeout=1)

        return self.job_store.update(
            job.job_id,
            status=status,
            exit_code=exit_code,
            timing=_finish_timing(job.timing),
        )

    def _start_background_job(
        self,
        job: JobRecord,
        cwd: Path,
        env: dict[str, str],
        timeout: int,
        *,
        env_policy: EnvPolicy,
        max_output_bytes: int | None,
    ) -> JobRecord:
        try:
            process = subprocess.Popen(
                job.argv,
                cwd=str(cwd),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except OSError as exc:
            raise DomainError(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"Command failed to start: {exc}",
                hint="Verify the executable exists and is available on PATH.",
                details={"argv": list(job.argv), "cwd": str(cwd)},
            ) from exc
        self.job_store.save(job)
        current = self.job_store.update(job.job_id, pid=process.pid)

        stdout_thread, stderr_thread = self._start_output_threads(
            job.job_id,
            process,
            env_policy=env_policy,
            max_output_bytes=max_output_bytes,
        )
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

    def _start_output_threads(
        self,
        job_id: str,
        process: subprocess.Popen,
        *,
        env_policy: EnvPolicy,
        max_output_bytes: int | None,
    ) -> tuple[threading.Thread | None, threading.Thread | None]:
        stdout_thread = threading.Thread(
            target=self._capture_stream,
            args=(job_id, "stdout", process.stdout, env_policy, max_output_bytes),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._capture_stream,
            args=(job_id, "stderr", process.stderr, env_policy, max_output_bytes),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        return stdout_thread, stderr_thread

    def _capture_stream(
        self,
        job_id: str,
        stream: str,
        handle,
        env_policy: EnvPolicy,
        max_output_bytes: int | None,
    ) -> None:
        if handle is None:
            return
        pending = ""
        redacting_secret = False
        try:
            for text in iter(lambda: handle.read(self.stream_chunk_bytes), ""):
                pending += _normalize_output_text(text)
                pending, redacting_secret = self._flush_buffered_output(
                    job_id,
                    stream,
                    pending,
                    env_policy,
                    max_output_bytes,
                    redacting_secret=redacting_secret,
                )
            if not redacting_secret:
                self._store_output(job_id, stream, pending, env_policy, max_output_bytes)
        finally:
            handle.close()

    def _flush_buffered_output(
        self,
        job_id: str,
        stream: str,
        pending: str,
        env_policy: EnvPolicy,
        max_output_bytes: int | None,
        *,
        redacting_secret: bool,
    ) -> tuple[str, bool]:
        if not pending:
            return "", redacting_secret

        if redacting_secret:
            secret_end = _first_whitespace_boundary(pending)
            if secret_end < 0:
                return "", True
            pending = pending[secret_end:]
            redacting_secret = False
            if not pending:
                return "", False

        pending_secret = _pending_secret_assignment(pending, env_policy=env_policy)
        if pending_secret is not None:
            token_start, secret_name = pending_secret
            if token_start > 0:
                self._store_output(
                    job_id,
                    stream,
                    pending[:token_start],
                    env_policy,
                    max_output_bytes,
                )
            self._store_output(
                job_id,
                stream,
                f"{secret_name}=[REDACTED]",
                env_policy,
                max_output_bytes,
            )
            return "", True

        newline_boundary = _last_line_boundary(pending)
        if newline_boundary > 0:
            self._store_output(
                job_id,
                stream,
                pending[:newline_boundary],
                env_policy,
                max_output_bytes,
            )
            return pending[newline_boundary:], False

        if len(pending) < self.stream_flush_threshold_chars:
            return pending, False

        preserve_from = max(len(pending) - self.stream_redaction_tail_chars, 0)
        whitespace_boundary = _last_whitespace_boundary(pending, preserve_from)
        flush_boundary = whitespace_boundary or preserve_from
        if flush_boundary <= 0:
            return pending, False

        self._store_output(
            job_id,
            stream,
            pending[:flush_boundary],
            env_policy,
            max_output_bytes,
        )
        return pending[flush_boundary:], False

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

    def _effective_timeout(self, timeout_sec: int | None, rule: CommandRule | None) -> int:
        timeout = timeout_sec or self.default_timeout_sec
        if rule is not None and rule.max_seconds is not None:
            timeout = min(timeout, rule.max_seconds)
        return timeout

    def _store_output(
        self,
        job_id: str,
        stream: str,
        text: str | bytes | None,
        env_policy: EnvPolicy,
        max_output_bytes: int | None,
    ) -> None:
        sanitized = _sanitize_output(text, env_policy=env_policy)
        if sanitized:
            self.job_store.append_output(
                job_id,
                stream,
                sanitized,
                max_output_bytes=max_output_bytes,
            )

    def _completed_process_status(self, job: JobRecord, returncode: int | None) -> str:
        if job.status != "running":
            return job.status
        return "succeeded" if returncode == 0 else "failed"

    def _max_output_bytes(self, rule: CommandRule | None) -> int | None:
        if rule is None or rule.max_output_bytes is None:
            return self.max_output_bytes
        return min(rule.max_output_bytes, self.max_output_bytes)


def _normalize_output_text(text: str | bytes | None) -> str:
    if not text:
        return ""
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    return text


def _last_line_boundary(text: str) -> int:
    last_newline = max(text.rfind("\n"), text.rfind("\r"))
    return last_newline + 1 if last_newline >= 0 else 0


def _first_whitespace_boundary(text: str) -> int:
    for index, char in enumerate(text):
        if char.isspace():
            return index
    return -1


def _last_whitespace_boundary(text: str, limit: int) -> int:
    search_limit = min(max(limit, 0), len(text))
    for index in range(search_limit - 1, -1, -1):
        if text[index].isspace():
            return index + 1
    return 0


def _pending_secret_assignment(
    text: str,
    *,
    env_policy: EnvPolicy,
) -> tuple[int, str] | None:
    token_start = _last_whitespace_boundary(text, len(text))
    token = text[token_start:]
    if not token:
        return None

    sanitized = _sanitize_output(token, env_policy=env_policy)
    if sanitized == token or not sanitized.endswith("=[REDACTED]"):
        return None
    return token_start, sanitized.removesuffix("=[REDACTED]")


def _sanitize_output(
    text: str | bytes | None,
    *,
    env_policy: EnvPolicy,
) -> str:
    normalized = _normalize_output_text(text)
    if not normalized:
        return ""

    return redact_secrets(normalized, env_policy=env_policy)


def _finish_timing(timing: CommandTiming) -> CommandTiming:
    finished_at = datetime.now(UTC)
    started_at = timing.started_at or finished_at
    duration_ms = max(int((finished_at - started_at).total_seconds() * 1000), 0)
    return timing.model_copy(
        update={
            "finished_at": finished_at,
            "duration_ms": duration_ms,
        },
    )


__all__ = ["CommandService"]
