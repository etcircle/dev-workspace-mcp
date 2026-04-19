from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from dev_workspace_mcp.codegraph.index_manager import CodegraphIndexManager
from dev_workspace_mcp.codegraph.providers import build_codegraph_provider
from dev_workspace_mcp.codegraph.service import CodegraphService
from dev_workspace_mcp.codegraph.watcher_manager import CodegraphWatcherManager
from dev_workspace_mcp.commands.service import CommandService
from dev_workspace_mcp.config import Settings, get_settings
from dev_workspace_mcp.github_tools.service import GitHubService
from dev_workspace_mcp.http_tools.local_client import LocalHttpClient
from dev_workspace_mcp.memory_index.service import MemoryIndexService
from dev_workspace_mcp.probes.service import ProbeService
from dev_workspace_mcp.projects.bootstrap import ProjectBootstrapService
from dev_workspace_mcp.projects.connections import ProjectConnectionService
from dev_workspace_mcp.projects.registry import ProjectRegistry
from dev_workspace_mcp.services.manager import ServiceManager


@dataclass(slots=True)
class RuntimeServices:
    command_service: CommandService
    service_manager: ServiceManager
    probe_service: ProbeService
    codegraph_service: CodegraphService
    http_client: LocalHttpClient
    bootstrap_service: ProjectBootstrapService
    connection_service: ProjectConnectionService
    github_service_factory: Callable[[str], GitHubService]
    memory_index_service_factory: Callable[[str], MemoryIndexService]


@dataclass(slots=True)
class DevWorkspaceRuntime:
    name: str
    settings: Settings
    project_registry: ProjectRegistry
    services: RuntimeServices


def create_memory_index_service(
    project_registry: ProjectRegistry,
    project_id: str,
) -> MemoryIndexService:
    project = project_registry.require(project_id)
    return MemoryIndexService(
        project_root=project.root_path,
        project_id=project.project_id,
        settings=project_registry.settings,
    )


def create_github_service(
    project_registry: ProjectRegistry,
    project_id: str,
) -> GitHubService:
    project = project_registry.require(project_id)
    return GitHubService(project.root_path)


def create_runtime_services(project_registry: ProjectRegistry) -> RuntimeServices:
    enforce_allowlist = (
        getattr(project_registry.settings, "command_policy", "policy") == "allowlist"
    )
    command_service = CommandService(
        project_registry,
        enforce_allowlist=enforce_allowlist,
    )
    service_manager = ServiceManager(project_registry)
    probe_service = ProbeService(
        project_registry,
        enforce_allowlist=enforce_allowlist,
    )
    provider = build_codegraph_provider(
        max_matches=getattr(project_registry.settings, "codegraph_max_matches", 200),
        max_source_chars=getattr(project_registry.settings, "codegraph_max_source_chars", 20_000),
    )
    codegraph_service = CodegraphService(
        project_registry=project_registry,
        watcher_manager=CodegraphWatcherManager(),
        index_manager=CodegraphIndexManager(),
        provider=provider,
    )
    http_client = LocalHttpClient()
    bootstrap_service = ProjectBootstrapService(project_registry)
    connection_service = ProjectConnectionService(project_registry)

    def github_service_factory(project_id: str) -> GitHubService:
        return create_github_service(project_registry, project_id)

    def memory_index_service_factory(project_id: str) -> MemoryIndexService:
        return create_memory_index_service(project_registry, project_id)

    return RuntimeServices(
        command_service=command_service,
        service_manager=service_manager,
        probe_service=probe_service,
        codegraph_service=codegraph_service,
        http_client=http_client,
        bootstrap_service=bootstrap_service,
        connection_service=connection_service,
        github_service_factory=github_service_factory,
        memory_index_service_factory=memory_index_service_factory,
    )


def create_runtime(settings: Settings | None = None) -> DevWorkspaceRuntime:
    runtime_settings = settings or get_settings()
    project_registry = ProjectRegistry(runtime_settings)
    project_registry.refresh()
    services = create_runtime_services(project_registry)
    return DevWorkspaceRuntime(
        name="dev-workspace-mcp",
        settings=runtime_settings,
        project_registry=project_registry,
        services=services,
    )


__all__ = [
    "DevWorkspaceRuntime",
    "RuntimeServices",
    "create_github_service",
    "create_memory_index_service",
    "create_runtime",
    "create_runtime_services",
]
