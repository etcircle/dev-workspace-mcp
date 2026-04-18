from __future__ import annotations

import ipaddress
import os
import re
import socket
from fnmatch import fnmatch
from pathlib import Path

from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.connections import (
    ConfigureConnectionRequest,
    ConfigureConnectionResponse,
    ConnectionProfile,
    ListConnectionsResponse,
    TestConnectionRequest,
    TestConnectionResponse,
)
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.policy.models import NetworkPolicy
from dev_workspace_mcp.projects.manifest import manifest_path_for, update_manifest
from dev_workspace_mcp.projects.registry import ProjectRegistry
from dev_workspace_mcp.shared.env_files import (
    agent_env_path_for,
    ensure_agent_env_gitignore,
    load_agent_env,
    update_agent_env,
    write_text_atomic,
)

_ALLOWED_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_HOST_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


class ProjectConnectionService:
    def __init__(self, project_registry: ProjectRegistry) -> None:
        self.project_registry = project_registry

    def list_connections(self, project_id: str) -> ListConnectionsResponse:
        record = self._require_project(project_id)
        return ListConnectionsResponse(
            project_id=record.project_id,
            connections={
                name: profile.model_copy(deep=True)
                for name, profile in record.manifest.connections.items()
            },
        )

    def configure_connection(
        self,
        request: ConfigureConnectionRequest,
    ) -> ConfigureConnectionResponse:
        record = self._require_project(request.project_id)
        project_root = Path(record.root_path)
        manifest_path = manifest_path_for(project_root)
        manifest_before = self._read_optional_text(manifest_path)
        gitignore_path = project_root / ".gitignore"
        gitignore_before = self._read_optional_text(gitignore_path)
        env_path = agent_env_path_for(project_root)
        env_before = self._read_optional_text(env_path)

        try:
            update_manifest(
                project_root,
                lambda manifest: self._updated_manifest(
                    manifest=manifest,
                    connection_name=request.connection_name,
                    profile=request.profile,
                ),
            )
            if request.env_updates:
                ensure_agent_env_gitignore(project_root)
                update_agent_env(project_root, request.env_updates)
        except Exception:
            self._restore_optional_text(manifest_path, manifest_before)
            self._restore_optional_text(gitignore_path, gitignore_before)
            self._restore_optional_text(env_path, env_before)
            raise

        updated_record = self._require_project(record.project_id)
        updated_profile = self._require_connection(updated_record, request.connection_name)
        return ConfigureConnectionResponse(
            project_id=updated_record.project_id,
            connection_name=request.connection_name,
            profile=updated_profile,
            env_keys_updated=list(request.env_updates.keys()),
        )

    def test_connection(self, request: TestConnectionRequest) -> TestConnectionResponse:
        record = self._require_project(request.project_id)
        profile = self._require_connection(record, request.connection_name)
        project_root = Path(record.root_path)

        environment = self._resolve_connection_env(record, profile, project_root)

        missing_env_keys = [
            env_name
            for env_name in (profile.host_env, profile.port_env)
            if env_name not in environment
        ]
        if missing_env_keys:
            raise DomainError(
                code=ErrorCode.CONNECTION_TEST_FAILED,
                message=(
                    "Missing required environment variables for connection test: "
                    + ", ".join(missing_env_keys)
                ),
                hint=(
                    "Set the missing env vars in the process environment or "
                    ".devworkspace/agent.env."
                ),
                details={
                    "connection_name": request.connection_name,
                    "missing_env_keys": missing_env_keys,
                },
            )

        host = self._validate_host(environment[profile.host_env], env_name=profile.host_env)
        port = self._validate_port(environment[profile.port_env], env_name=profile.port_env)
        self._enforce_network_policy(host=host, port=port, network_policy=record.policy.network)

        try:
            with socket.create_connection((host, port), timeout=profile.test.timeout_sec):
                pass
        except OSError as exc:
            return TestConnectionResponse(
                connection_name=request.connection_name,
                kind=profile.kind,
                transport=profile.transport,
                host=host,
                port=port,
                reachable=False,
                message=f"TCP connection failed: {exc}",
            )

        return TestConnectionResponse(
            connection_name=request.connection_name,
            kind=profile.kind,
            transport=profile.transport,
            host=host,
            port=port,
            reachable=True,
            message="TCP connection succeeded.",
        )

    def _require_project(self, project_id: str):
        self.project_registry.refresh()
        return self.project_registry.require(project_id)

    def _require_connection(self, record, connection_name: str) -> ConnectionProfile:
        profile = record.manifest.connections.get(connection_name)
        if profile is None:
            raise DomainError(
                code=ErrorCode.CONNECTION_NOT_FOUND,
                message=f"Unknown connection profile: {connection_name}",
                hint="Call list_connections first to find a valid connection name.",
                details={"project_id": record.project_id, "connection_name": connection_name},
            )
        return profile

    def _updated_manifest(
        self,
        *,
        manifest,
        connection_name: str,
        profile: ConnectionProfile,
    ):
        updated_manifest = manifest.model_copy(deep=True)
        updated_manifest.connections[connection_name] = profile.model_copy(deep=True)
        return updated_manifest

    @staticmethod
    def _read_optional_text(path: Path) -> str | None:
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _restore_optional_text(path: Path, previous_text: str | None) -> None:
        if previous_text is None:
            if path.exists():
                path.unlink()
            return
        write_text_atomic(path, previous_text)

    def _resolve_connection_env(
        self,
        record,
        profile: ConnectionProfile,
        project_root: Path,
    ) -> dict[str, str]:
        agent_env = load_agent_env(project_root)
        environment = dict(agent_env)
        referenced_env_names = {
            env_name
            for env_name in (
                profile.host_env,
                profile.port_env,
                profile.database_env,
                profile.user_env,
                profile.password_env,
                profile.token_env,
                profile.ssl_mode_env,
            )
            if env_name is not None
        }
        for env_name in referenced_env_names:
            if env_name in environment:
                continue
            if not self._can_use_process_env(record, env_name):
                continue
            if env_name in os.environ:
                environment[env_name] = os.environ[env_name]
        return environment

    def _can_use_process_env(self, record, env_name: str) -> bool:
        return record.policy.env.inherit or env_name in record.policy.env.allow

    def _validate_host(self, host: str, *, env_name: str) -> str:
        normalized = host.strip()
        if (
            not normalized
            or any(character.isspace() for character in normalized)
            or "://" in normalized
            or any(token in normalized for token in ("/", "?", "#"))
            or normalized.startswith("[")
            or normalized.endswith("]")
        ):
            raise DomainError(
                code=ErrorCode.CONNECTION_TEST_FAILED,
                message=f"Connection host env var {env_name} must contain a valid hostname.",
                hint="Set the host env var to a plain hostname or IP address.",
                details={"env_key": env_name},
            )
        try:
            ipaddress.ip_address(normalized)
        except ValueError:
            pass
        else:
            return normalized
        if ":" in normalized:
            raise DomainError(
                code=ErrorCode.CONNECTION_TEST_FAILED,
                message=f"Connection host env var {env_name} must contain a valid hostname.",
                hint="Set the host env var to a plain hostname or IP address.",
                details={"env_key": env_name},
            )
        labels = normalized.split(".")
        if all(label.isdigit() for label in labels):
            raise DomainError(
                code=ErrorCode.CONNECTION_TEST_FAILED,
                message=f"Connection host env var {env_name} must contain a valid hostname.",
                hint="Set the host env var to a plain hostname or IP address.",
                details={"env_key": env_name},
            )
        if any(not label or not _HOST_LABEL_RE.fullmatch(label) for label in labels):
            raise DomainError(
                code=ErrorCode.CONNECTION_TEST_FAILED,
                message=f"Connection host env var {env_name} must contain a valid hostname.",
                hint="Set the host env var to a plain hostname or IP address.",
                details={"env_key": env_name},
            )
        return normalized

    def _validate_port(self, port_value: str, *, env_name: str) -> int:
        try:
            port = int(port_value.strip())
        except ValueError as exc:
            raise DomainError(
                code=ErrorCode.CONNECTION_TEST_FAILED,
                message=(
                    f"Connection port env var {env_name} must be an integer between 1 and 65535."
                ),
                hint="Set the port env var to a numeric TCP port.",
                details={"env_key": env_name},
            ) from exc

        if port < 1 or port > 65535:
            raise DomainError(
                code=ErrorCode.CONNECTION_TEST_FAILED,
                message=(
                    f"Connection port env var {env_name} must be an integer between 1 and 65535."
                ),
                hint="Set the port env var to a numeric TCP port.",
                details={"env_key": env_name},
            )
        return port

    def _enforce_network_policy(
        self,
        *,
        host: str,
        port: int,
        network_policy: NetworkPolicy,
    ) -> None:
        if self._is_allowed_host(host, network_policy):
            return
        raise DomainError(
            code=ErrorCode.NETWORK_DENIED,
            message=f"Refusing connection destination outside project policy: {host}:{port}",
            hint=(
                "Allow localhost or add the hostname to "
                ".devworkspace/policy.yaml network.allowed_hosts."
            ),
            details={"hostname": host, "port": port},
        )

    def _is_allowed_host(self, hostname: str, network_policy: NetworkPolicy) -> bool:
        normalized = hostname.lower()
        if normalized in _ALLOWED_LOCAL_HOSTS and network_policy.allow_localhost:
            return True
        if any(fnmatch(normalized, pattern.lower()) for pattern in network_policy.allowed_hosts):
            return True
        return network_policy.default == "allow"


__all__ = ["ProjectConnectionService"]
