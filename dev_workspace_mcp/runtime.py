from __future__ import annotations

from dataclasses import dataclass

from dev_workspace_mcp.codegraph.index_manager import CodegraphIndexManager
from dev_workspace_mcp.codegraph.providers import build_codegraph_provider
from dev_workspace_mcp.codegraph.service import CodegraphService
from dev_workspace_mcp.codegraph.watcher_manager import CodegraphWatcherManager
from dev_workspace_mcp.commands.service import CommandService
from dev_workspace_mcp.config import Settings, get_settings
from dev_workspace_mcp.http_tools.local_client import LocalHttpClient
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


@dataclass(slots=True)
class DevWorkspaceRuntime:
    name: str
    settings: Settings
    project_registry: ProjectRegistry
    services: RuntimeServices


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
    return RuntimeServices(
        command_service=command_service,
        service_manager=service_manager,
        probe_service=probe_service,
        codegraph_service=codegraph_service,
        http_client=http_client,
        bootstrap_service=bootstrap_service,
        connection_service=connection_service,
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
    "create_runtime",
    "create_runtime_services",
]
