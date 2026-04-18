from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dev_workspace_mcp.codegraph.service import CodegraphService
from dev_workspace_mcp.commands.service import CommandService
from dev_workspace_mcp.files.service import FileService
from dev_workspace_mcp.gittools.service import GitService
from dev_workspace_mcp.http_tools.local_client import LocalHttpClient
from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.mcp_server.result_envelope import error_result, ok
from dev_workspace_mcp.models.common import WarningMessage
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.models.projects import WatcherSummary
from dev_workspace_mcp.models.state_docs import StateDocKind
from dev_workspace_mcp.projects.snapshots import build_project_snapshot
from dev_workspace_mcp.runtime import RuntimeServices, create_runtime_services
from dev_workspace_mcp.services.manager import ServiceManager
from dev_workspace_mcp.state_docs.service import StateDocumentService

ToolHandler = Callable[..., dict[str, Any]]


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        self._tools[definition.name] = definition

    def list_tools(self) -> list[ToolDefinition]:
        return [self._tools[name] for name in sorted(self._tools)]

    def run(self, name: str, **kwargs: Any) -> dict[str, Any]:
        try:
            tool = self._tools.get(name)
            if tool is None:
                raise DomainError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Unknown tool: {name}",
                    hint="Use the registered tool names exposed by the server.",
                )
            return tool.handler(**kwargs)
        except DomainError as exc:
            return error_result(exc)
        except Exception as exc:  # pragma: no cover - defensive envelope stability
            return error_result(
                DomainError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Tool '{name}' failed unexpectedly.",
                    details={"error": str(exc)},
                )
            )



def build_tool_registry(
    project_registry,
    *,
    services: RuntimeServices | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    runtime_services = services or create_runtime_services(project_registry)
    command_service = runtime_services.command_service
    service_manager = runtime_services.service_manager
    probe_service = runtime_services.probe_service
    codegraph_service = runtime_services.codegraph_service
    http_client = runtime_services.http_client

    registry.register(
        ToolDefinition(
            name="apply_patch",
            description="Apply a unified diff patch to one or more project-relative files.",
            handler=lambda project_id, patch: ok(
                _file_service(project_registry, project_id).apply_patch(patch)
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="call_path",
            description="Explain the direct caller/callee path for a project symbol.",
            handler=lambda project_id, symbol, path=None: ok(
                codegraph_service.call_path(project_id, symbol, path=path)
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="cancel_job",
            description="Cancel a running background job.",
            handler=lambda project_id, job_id: ok(command_service.cancel_job(project_id, job_id)),
        )
    )
    registry.register(
        ToolDefinition(
            name="get_job",
            description="Get the latest state of a previously started job.",
            handler=lambda project_id, job_id: ok(command_service.get_job(project_id, job_id)),
        )
    )
    registry.register(
        ToolDefinition(
            name="get_logs",
            description="Get captured logs for a declared service.",
            handler=lambda project_id, service_name, offset=0, limit=200: ok(
                service_manager.get_logs(
                    project_id,
                    service_name,
                    offset=offset,
                    limit=limit,
                )
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="git_checkout",
            description="Checkout an existing ref or create a new branch.",
            handler=lambda project_id, ref, create=False, force=False: ok(
                _git_service(project_registry, project_id).git_checkout(
                    ref=ref,
                    create=create,
                    force=force,
                )
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="git_commit",
            description="Create a git commit for staged or explicitly provided paths.",
            handler=lambda project_id, message, paths=None, all=False: ok(
                _git_service(project_registry, project_id).git_commit(
                    message=message,
                    paths=paths,
                    all=all,
                )
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="git_diff",
            description="Return a git diff for the working tree, staged changes, or a ref.",
            handler=lambda project_id, path=None, ref=None, staged=False, context_lines=3: ok(
                _git_service(project_registry, project_id).git_diff(
                    path=path,
                    ref=ref,
                    staged=staged,
                    context_lines=context_lines,
                )
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="git_status",
            description="Return structured git status for a project repository.",
            handler=lambda project_id, include_untracked=True: ok(
                _git_service(project_registry, project_id).git_status(
                    include_untracked=include_untracked,
                )
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="delete_path",
            description="Delete a project-relative file or directory.",
            handler=lambda project_id, path, recursive=False, missing_ok=False: ok(
                _file_service(project_registry, project_id).delete_path(
                    path,
                    recursive=recursive,
                    missing_ok=missing_ok,
                )
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="find_references",
            description="Find textual references to a symbol across the project codebase.",
            handler=lambda project_id, symbol, path=None: ok(
                codegraph_service.find_references(project_id, symbol, path=path)
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="function_context",
            description="Return the source context for a function, method, or class symbol.",
            handler=lambda project_id, symbol, path=None: ok(
                codegraph_service.function_context(project_id, symbol, path=path)
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="grep",
            description="Search text or regex patterns across project files.",
            handler=lambda project_id, pattern, path=None, ignore_case=False: ok(
                codegraph_service.grep(
                    project_id,
                    pattern,
                    path=path,
                    ignore_case=ignore_case,
                )
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="http_request",
            description="Make a local-only HTTP request for verification against running services.",
            handler=lambda project_id, method, url, headers=None, body=None, timeout_sec=15: ok(
                _http_request(
                    project_registry,
                    http_client,
                    project_id,
                    method,
                    url,
                    headers,
                    body,
                    timeout_sec,
                )
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="list_dir",
            description="List files under a project-relative directory.",
            handler=lambda project_id, path=".", recursive=False, limit=None: ok(
                _file_service(project_registry, project_id).list_dir(
                    path,
                    recursive=recursive,
                    limit=limit,
                )
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="list_probes",
            description="List manifest-declared diagnostic probes for a project.",
            handler=lambda project_id: ok(probe_service.list_probes(project_id)),
        )
    )
    registry.register(
        ToolDefinition(
            name="list_projects",
            description="List known projects and their basic metadata.",
            handler=lambda query=None, include_paths=False: ok(
                {"projects": project_registry.list_items(query=query, include_paths=include_paths)}
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="list_services",
            description="List manifest-declared services for a project.",
            handler=lambda project_id: ok(service_manager.list_services(project_id)),
        )
    )
    registry.register(
        ToolDefinition(
            name="module_overview",
            description="Summarize the structure of one source module.",
            handler=lambda project_id, path: ok(
                codegraph_service.module_overview(project_id, path)
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="move_path",
            description="Move or rename a project-relative file or directory.",
            handler=lambda project_id, source_path, destination_path, overwrite=False: ok(
                _file_service(project_registry, project_id).move_path(
                    source_path,
                    destination_path,
                    overwrite=overwrite,
                )
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="patch_state_doc",
            description="Patch heading sections in a repo-local state document.",
            handler=lambda project_id, kind, section_updates, create_missing_sections=True: ok(
                _state_doc_service(project_registry, project_id).patch(
                    _state_doc_kind(kind),
                    section_updates,
                    create_missing_sections=create_missing_sections,
                )
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="project_snapshot",
            description="Return a high-value summary of one project.",
            handler=lambda project_id: _project_snapshot_handler(
                project_registry,
                codegraph_service,
                service_manager,
                project_id,
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="read_file",
            description="Read a project-relative text file.",
            handler=lambda project_id, path, offset=1, limit=None: ok(
                _file_service(project_registry, project_id).read_file(
                    path,
                    offset=offset,
                    limit=limit,
                )
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="read_source",
            description="Read source code from a project-relative file with optional line bounds.",
            handler=lambda project_id, path, start_line=1, end_line=None: ok(
                codegraph_service.read_source(
                    project_id,
                    path,
                    start_line=start_line,
                    end_line=end_line,
                )
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="read_state_doc",
            description="Read a repo-local state document.",
            handler=lambda project_id, kind: ok(
                _state_doc_service(project_registry, project_id).read(_state_doc_kind(kind))
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="recent_changes",
            description=(
                "Return recent git diff content for a project or one "
                "project-relative path."
            ),
            handler=lambda project_id, path=None, ref=None, staged=False, context_lines=3: ok(
                codegraph_service.recent_changes(
                    project_id,
                    path=path,
                    ref=ref,
                    staged=staged,
                    context_lines=context_lines,
                )
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="restart_service",
            description="Restart a declared long-running service.",
            handler=lambda project_id, service_name: ok(
                service_manager.restart_service(project_id, service_name)
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="run_command",
            description="Run a bounded command inside a project workspace.",
            handler=_make_run_command_handler(command_service),
        )
    )
    registry.register(
        ToolDefinition(
            name="run_probe",
            description="Run one named diagnostic probe declared in the project manifest.",
            handler=lambda project_id, probe_name: ok(
                probe_service.run_probe(project_id, probe_name)
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="service_status",
            description="Get the latest state of one declared service.",
            handler=lambda project_id, service_name: ok(
                service_manager.service_status(project_id, service_name)
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="start_service",
            description="Start a declared long-running service.",
            handler=lambda project_id, service_name: ok(
                service_manager.start_service(project_id, service_name)
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="stop_service",
            description="Stop a declared long-running service.",
            handler=lambda project_id, service_name: ok(
                service_manager.stop_service(project_id, service_name)
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="watcher_health",
            description="Report codegraph watcher configuration and current activity state.",
            handler=lambda project_id: ok(codegraph_service.watcher_health(project_id)),
        )
    )
    registry.register(
        ToolDefinition(
            name="write_file",
            description="Write a project-relative text file.",
            handler=lambda project_id, path, content, create_parents=True, overwrite=True: ok(
                _file_service(project_registry, project_id).write_file(
                    path,
                    content,
                    create_parents=create_parents,
                    overwrite=overwrite,
                )
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="write_state_doc",
            description="Write a repo-local state document.",
            handler=lambda project_id, kind, raw_markdown: ok(
                _state_doc_service(project_registry, project_id).write(
                    _state_doc_kind(kind),
                    raw_markdown,
                )
            ),
        )
    )

    return registry



def _project_snapshot_handler(
    project_registry,
    codegraph_service: CodegraphService,
    service_manager: ServiceManager,
    project_id: str,
) -> dict[str, Any]:
    snapshot, warnings = build_project_snapshot(
        project_registry,
        project_id,
        service_manager=service_manager,
    )
    try:
        watcher = codegraph_service.watcher_health(project_id)
    except Exception:
        warnings.append(
            WarningMessage(
                code="WATCHER_STATUS_UNAVAILABLE",
                message=(
                    "Watcher health could not be refreshed cleanly; "
                    "returning the declared snapshot view."
                ),
            )
        )
    else:
        snapshot.watcher = WatcherSummary(
            configured=watcher.configured,
            active=watcher.active,
            watched_paths=watcher.watched_paths,
            status=watcher.status,
            revision=watcher.revision,
            indexed_at=watcher.indexed_at,
            file_count=watcher.file_count,
            symbol_count=watcher.symbol_count,
        )
    return ok(snapshot, warnings=warnings)



def _http_request(
    project_registry,
    http_client: LocalHttpClient,
    project_id: str,
    method: str,
    url: str,
    headers: dict[str, str] | None,
    body: str | bytes | None,
    timeout_sec: int,
):
    project = project_registry.require(project_id)
    return http_client.request(
        method=method,
        url=url,
        headers=headers,
        body=body,
        timeout_sec=timeout_sec,
        network_policy=project.policy.network,
    )



def _make_run_command_handler(command_service: CommandService) -> ToolHandler:
    def _handler(
        project_id,
        argv=None,
        cwd=None,
        env=None,
        timeout_sec=None,
        background=False,
        preset=None,
    ) -> dict[str, Any]:
        return ok(
            command_service.run_command(
                project_id,
                argv=argv,
                cwd=cwd,
                env=env,
                timeout_sec=timeout_sec,
                background=background,
                preset=preset,
            )
        )

    return _handler



def _file_service(project_registry, project_id: str) -> FileService:
    project = project_registry.require(project_id)
    max_read_bytes = getattr(project_registry.settings, "max_read_bytes", 200_000)
    return FileService(Path(project.root_path), max_read_bytes=max_read_bytes)



def _git_service(project_registry, project_id: str) -> GitService:
    project = project_registry.require(project_id)
    max_diff_bytes = getattr(project_registry.settings, "max_read_bytes", 200_000)
    return GitService(Path(project.root_path), max_diff_bytes=max_diff_bytes)



def _state_doc_service(project_registry, project_id: str) -> StateDocumentService:
    project = project_registry.require(project_id)
    return StateDocumentService(Path(project.root_path))



def _state_doc_kind(kind: str | StateDocKind) -> StateDocKind:
    try:
        return kind if isinstance(kind, StateDocKind) else StateDocKind(kind)
    except ValueError as exc:
        raise DomainError(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Unsupported state doc kind: {kind}",
            hint="Use one of: memory, roadmap, tasks.",
        ) from exc
