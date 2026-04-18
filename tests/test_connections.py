from __future__ import annotations

import socket
import subprocess
import threading
from pathlib import Path

import pytest
from pydantic import ValidationError

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.connections import (
    ConfigureConnectionRequest,
    ConnectionProfile,
    TestConnectionRequest,
    TestConnectionResponse,
)
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.models.projects import ProjectManifest
from dev_workspace_mcp.projects.connections import ProjectConnectionService
from dev_workspace_mcp.projects.manifest import load_manifest, write_manifest
from dev_workspace_mcp.projects.registry import ProjectRegistry
from dev_workspace_mcp.shared.env_files import load_agent_env, update_agent_env

_VALID_PROFILE = {
    "kind": "postgres",
    "transport": "direct",
    "host_env": "PGHOST",
    "port_env": "PGPORT",
    "database_env": "PGDATABASE",
    "user_env": "PGUSER",
    "password_env": "PGPASSWORD",
}


def _make_project(
    workspace_root: Path,
    *,
    folder_name: str = "demo-project",
    project_id: str = "demo-project",
) -> Path:
    project_root = workspace_root / folder_name
    project_root.mkdir()
    write_manifest(
        project_root,
        ProjectManifest(
            name="Demo Project",
            project_id=project_id,
        ),
    )
    return project_root


@pytest.fixture
def connection_service(workspace_root: Path) -> ProjectConnectionService:
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    return ProjectConnectionService(registry)


@pytest.fixture
def tcp_server() -> tuple[str, int, threading.Event]:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen()
    server.settimeout(0.2)

    accepted = threading.Event()
    stop_event = threading.Event()

    def _serve() -> None:
        while not stop_event.is_set():
            try:
                client, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            with client:
                accepted.set()

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()

    host, port = server.getsockname()
    yield host, port, accepted

    stop_event.set()
    server.close()
    thread.join(timeout=1)


def test_project_manifest_round_trips_connections() -> None:
    manifest = ProjectManifest.model_validate({"connections": {"primary": _VALID_PROFILE}})

    dumped = manifest.model_dump(mode="python")
    reloaded = ProjectManifest.model_validate(dumped)

    assert reloaded.connections["primary"].kind == "postgres"
    assert reloaded.connections["primary"].transport == "direct"
    assert reloaded.connections["primary"].host_env == "PGHOST"


def test_write_manifest_round_trips_connections(tmp_path: Path) -> None:
    project_root = tmp_path / "demo-project"
    project_root.mkdir()
    manifest = ProjectManifest.model_validate(
        {
            "name": "Demo Project",
            "project_id": "demo-project",
            "connections": {"primary": _VALID_PROFILE},
        }
    )

    manifest_path = write_manifest(project_root, manifest)
    reloaded = load_manifest(project_root)

    assert manifest_path == project_root / ".devworkspace.yaml"
    assert reloaded.project_id == "demo-project"
    assert reloaded.connections["primary"].password_env == "PGPASSWORD"


@pytest.mark.parametrize(
    "payload",
    [
        {**_VALID_PROFILE, "transport": "ssh_tunnel"},
        {key: value for key, value in _VALID_PROFILE.items() if key != "host_env"},
        {key: value for key, value in _VALID_PROFILE.items() if key != "port_env"},
        {**_VALID_PROFILE, "host_env": "   "},
        {**_VALID_PROFILE, "host_env": "db.example.com"},
        {**_VALID_PROFILE, "port_env": "5432"},
        {**_VALID_PROFILE, "host_env": "PG HOST"},
    ],
)
def test_connection_profile_rejects_unsupported_transport_or_missing_required_env_refs(
    payload: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        ConnectionProfile.model_validate(payload)


def test_configure_connection_request_rejects_invalid_env_update_keys() -> None:
    profile = ConnectionProfile.model_validate(_VALID_PROFILE)

    with pytest.raises(ValidationError):
        ConfigureConnectionRequest.model_validate(
            {
                "project_id": "demo-id",
                "connection_name": "primary",
                "profile": profile.model_dump(mode="python"),
                "env_updates": {"": "secret"},
            }
        )


def test_project_manifest_rejects_invalid_nested_connection_profiles() -> None:
    with pytest.raises(ValidationError):
        ProjectManifest.model_validate(
            {"connections": {"primary": {**_VALID_PROFILE, "port_env": ""}}}
        )


def test_agent_env_updates_replace_existing_keys_without_duplication(tmp_path: Path) -> None:
    project_root = tmp_path / "demo-project"
    project_root.mkdir()

    env_path = update_agent_env(project_root, {"PGHOST": "db.internal", "PGPORT": "5432"})
    update_agent_env(project_root, {"PGHOST": "db.example.com", "PGDATABASE": "app"})

    assert env_path == project_root / ".devworkspace" / "agent.env"
    assert load_agent_env(project_root) == {
        "PGHOST": "db.example.com",
        "PGPORT": "5432",
        "PGDATABASE": "app",
    }
    assert env_path.read_text(encoding="utf-8").splitlines() == [
        "PGHOST=db.example.com",
        "PGPORT=5432",
        "PGDATABASE=app",
    ]


def test_agent_env_load_raises_domain_error_for_malformed_file(tmp_path: Path) -> None:
    project_root = tmp_path / "demo-project"
    env_dir = project_root / ".devworkspace"
    env_dir.mkdir(parents=True)
    malformed_line = "export PGHOST=db.internal"
    (env_dir / "agent.env").write_text(f"{malformed_line}\n", encoding="utf-8")

    with pytest.raises(DomainError) as exc:
        load_agent_env(project_root)

    assert exc.value.code == ErrorCode.ENV_FILE_INVALID
    assert "line" not in exc.value.details
    assert malformed_line not in exc.value.message
    assert malformed_line not in (exc.value.hint or "")
    assert malformed_line not in str(exc.value.details)


def test_agent_env_load_rejects_duplicate_keys(tmp_path: Path) -> None:
    project_root = tmp_path / "demo-project"
    env_dir = project_root / ".devworkspace"
    env_dir.mkdir(parents=True)
    (env_dir / "agent.env").write_text(
        "PGHOST=db.internal\nPGHOST=db.example.com\n",
        encoding="utf-8",
    )

    with pytest.raises(DomainError) as exc:
        load_agent_env(project_root)

    assert exc.value.code == ErrorCode.ENV_FILE_INVALID


def test_configure_connection_and_list_round_trip_keeps_env_values_local_only(
    workspace_root: Path,
    connection_service: ProjectConnectionService,
) -> None:
    project_root = _make_project(workspace_root)
    request = ConfigureConnectionRequest.model_validate(
        {
            "project_id": "demo-project",
            "connection_name": "primary",
            "profile": _VALID_PROFILE,
            "env_updates": {
                "PGHOST": "db.internal",
                "PGPORT": "5432",
                "PGDATABASE": "app",
                "PGUSER": "app_user",
                "PGPASSWORD": "super-secret",
            },
        }
    )

    configured = connection_service.configure_connection(request)
    listed = connection_service.list_connections("demo-project")
    manifest_text = (project_root / ".devworkspace.yaml").read_text(encoding="utf-8")

    assert configured.project_id == "demo-project"
    assert configured.connection_name == "primary"
    assert configured.profile.password_env == "PGPASSWORD"
    assert set(configured.env_keys_updated) == {
        "PGHOST",
        "PGPORT",
        "PGDATABASE",
        "PGUSER",
        "PGPASSWORD",
    }
    assert listed.project_id == "demo-project"
    assert listed.connections["primary"].kind == "postgres"
    assert listed.connections["primary"].password_env == "PGPASSWORD"
    assert load_manifest(project_root).connections["primary"].password_env == "PGPASSWORD"
    assert "super-secret" not in manifest_text
    assert "db.internal" not in manifest_text
    assert "PGPASSWORD" in manifest_text
    assert load_agent_env(project_root) == {
        "PGHOST": "db.internal",
        "PGPORT": "5432",
        "PGDATABASE": "app",
        "PGUSER": "app_user",
        "PGPASSWORD": "super-secret",
    }


def test_test_connection_fails_cleanly_for_missing_env_vars(
    monkeypatch: pytest.MonkeyPatch,
    workspace_root: Path,
    connection_service: ProjectConnectionService,
) -> None:
    _make_project(workspace_root)
    host_env = "TASK4_MISSING_HOST"
    port_env = "TASK4_MISSING_PORT"
    monkeypatch.delenv(host_env, raising=False)
    monkeypatch.delenv(port_env, raising=False)

    connection_service.configure_connection(
        ConfigureConnectionRequest(
            project_id="demo-project",
            connection_name="primary",
            profile=ConnectionProfile(
                kind="generic_tcp",
                transport="direct",
                host_env=host_env,
                port_env=port_env,
            ),
        )
    )

    with pytest.raises(DomainError) as exc:
        connection_service.test_connection(
            TestConnectionRequest(project_id="demo-project", connection_name="primary")
        )

    assert exc.value.code == ErrorCode.CONNECTION_TEST_FAILED
    assert exc.value.details["missing_env_keys"] == [host_env, port_env]
    assert host_env in exc.value.message
    assert port_env in exc.value.message


def test_test_connection_does_not_read_unapproved_process_env_vars(
    monkeypatch: pytest.MonkeyPatch,
    workspace_root: Path,
    connection_service: ProjectConnectionService,
) -> None:
    _make_project(workspace_root)
    host_env = "TASK4_SECRET_HOST"
    port_env = "TASK4_SECRET_PORT"
    secret_host = "TOKENVALUE123"
    secret_port = "5432"
    monkeypatch.setenv(host_env, secret_host)
    monkeypatch.setenv(port_env, secret_port)

    connection_service.configure_connection(
        ConfigureConnectionRequest(
            project_id="demo-project",
            connection_name="primary",
            profile=ConnectionProfile(
                kind="generic_tcp",
                transport="direct",
                host_env=host_env,
                port_env=port_env,
            ),
        )
    )

    with pytest.raises(DomainError) as exc:
        connection_service.test_connection(
            TestConnectionRequest(project_id="demo-project", connection_name="primary")
        )

    assert exc.value.code == ErrorCode.CONNECTION_TEST_FAILED
    assert exc.value.details["missing_env_keys"] == [host_env, port_env]
    assert secret_host not in exc.value.message
    assert secret_host not in (exc.value.hint or "")
    assert secret_host not in str(exc.value.details)
    assert secret_port not in str(exc.value.details)


def test_test_connection_succeeds_against_local_ephemeral_tcp_server(
    tcp_server: tuple[str, int, threading.Event],
    workspace_root: Path,
    connection_service: ProjectConnectionService,
) -> None:
    host, port, accepted = tcp_server
    _make_project(workspace_root)
    host_env = "TASK4_TCP_HOST"
    port_env = "TASK4_TCP_PORT"

    connection_service.configure_connection(
        ConfigureConnectionRequest(
            project_id="demo-project",
            connection_name="primary",
            profile=ConnectionProfile(
                kind="generic_tcp",
                transport="direct",
                host_env=host_env,
                port_env=port_env,
            ),
            env_updates={host_env: host, port_env: str(port)},
        )
    )

    response = connection_service.test_connection(
        TestConnectionRequest(project_id="demo-project", connection_name="primary")
    )

    assert response.connection_name == "primary"
    assert response.kind == "generic_tcp"
    assert response.transport == "direct"
    assert response.host == host
    assert response.port == port
    assert response.reachable is True
    assert response.message == "TCP connection succeeded."
    assert accepted.wait(timeout=1)


def test_test_connection_returns_reachable_false_for_tcp_failure(
    workspace_root: Path,
    connection_service: ProjectConnectionService,
) -> None:
    project_root = _make_project(workspace_root)
    port_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    port_socket.bind(("127.0.0.1", 0))
    _, port = port_socket.getsockname()
    port_socket.close()

    connection_service.configure_connection(
        ConfigureConnectionRequest(
            project_id="demo-project",
            connection_name="primary",
            profile=ConnectionProfile(
                kind="generic_tcp",
                transport="direct",
                host_env="TASK4_TCP_FAIL_HOST",
                port_env="TASK4_TCP_FAIL_PORT",
            ),
            env_updates={
                "TASK4_TCP_FAIL_HOST": "127.0.0.1",
                "TASK4_TCP_FAIL_PORT": str(port),
            },
        )
    )

    response = connection_service.test_connection(
        TestConnectionRequest(project_id="demo-project", connection_name="primary")
    )

    assert response.reachable is False
    assert response.host == "127.0.0.1"
    assert response.port == port
    assert "TCP connection failed:" in response.message
    assert "super-secret" not in (project_root / ".devworkspace.yaml").read_text(encoding="utf-8")


def test_test_connection_denies_localhost_when_policy_disallows_it(
    workspace_root: Path,
    connection_service: ProjectConnectionService,
) -> None:
    project_root = _make_project(workspace_root)
    (project_root / ".devworkspace").mkdir(exist_ok=True)
    (project_root / ".devworkspace" / "policy.yaml").write_text(
        "version: 1\n"
        "network:\n"
        "  default: deny\n"
        "  allow_localhost: false\n",
        encoding="utf-8",
    )

    connection_service.configure_connection(
        ConfigureConnectionRequest(
            project_id="demo-project",
            connection_name="primary",
            profile=ConnectionProfile(
                kind="generic_tcp",
                transport="direct",
                host_env="TASK4_DENIED_HOST",
                port_env="TASK4_DENIED_PORT",
            ),
            env_updates={
                "TASK4_DENIED_HOST": "127.0.0.1",
                "TASK4_DENIED_PORT": "5432",
            },
        )
    )

    with pytest.raises(DomainError) as exc:
        connection_service.test_connection(
            TestConnectionRequest(project_id="demo-project", connection_name="primary")
        )

    assert exc.value.code == ErrorCode.NETWORK_DENIED
    assert exc.value.details["hostname"] == "127.0.0.1"


@pytest.mark.parametrize(
    "host_value",
    [
        "http://127.0.0.1",
        "bad_host!",
        "-foo",
        "foo..bar",
        ".foo",
        "foo.",
        "999.999.999.999",
    ],
)
def test_test_connection_rejects_invalid_runtime_host_value(
    host_value: str,
    workspace_root: Path,
    connection_service: ProjectConnectionService,
) -> None:
    _make_project(workspace_root)
    connection_service.configure_connection(
        ConfigureConnectionRequest(
            project_id="demo-project",
            connection_name="primary",
            profile=ConnectionProfile(
                kind="generic_tcp",
                transport="direct",
                host_env="TASK4_INVALID_HOST",
                port_env="TASK4_INVALID_PORT",
            ),
            env_updates={
                "TASK4_INVALID_HOST": host_value,
                "TASK4_INVALID_PORT": "5432",
            },
        )
    )

    with pytest.raises(DomainError) as exc:
        connection_service.test_connection(
            TestConnectionRequest(project_id="demo-project", connection_name="primary")
        )

    assert exc.value.code == ErrorCode.CONNECTION_TEST_FAILED
    assert exc.value.details["env_key"] == "TASK4_INVALID_HOST"


def test_test_connection_response_keeps_honest_tcp_result_shape() -> None:
    response = TestConnectionResponse(
        connection_name="primary",
        kind="postgres",
        transport="direct",
        host="127.0.0.1",
        port=5432,
        reachable=True,
        message="TCP connection succeeded.",
    )

    assert response.connection_name == "primary"
    assert response.reachable is True
    assert response.message == "TCP connection succeeded."


def test_configure_connection_refuses_to_write_tracked_agent_env(
    workspace_root: Path,
    connection_service: ProjectConnectionService,
) -> None:
    project_root = _make_project(workspace_root)
    subprocess.run(
        ["git", "-C", str(project_root), "init"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(project_root), "config", "user.name", "Test User"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(project_root), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    agent_env = project_root / ".devworkspace" / "agent.env"
    agent_env.parent.mkdir(exist_ok=True)
    agent_env.write_text("PGHOST=tracked-host\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(project_root), "add", ".devworkspace/agent.env"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(project_root), "commit", "-m", "track agent env"],
        check=True,
        capture_output=True,
    )

    with pytest.raises(DomainError) as exc:
        connection_service.configure_connection(
            ConfigureConnectionRequest(
                project_id="demo-project",
                connection_name="primary",
                profile=ConnectionProfile.model_validate(_VALID_PROFILE),
                env_updates={"PGHOST": "new-secret-host"},
            )
        )

    assert exc.value.code == ErrorCode.ENV_FILE_INVALID
    assert "new-secret-host" not in exc.value.message
    assert "primary" not in load_manifest(project_root).connections
    assert agent_env.read_text(encoding="utf-8") == "PGHOST=tracked-host\n"


def test_configure_connection_refuses_to_write_agent_env_when_gitignore_unignores_it(
    workspace_root: Path,
    connection_service: ProjectConnectionService,
) -> None:
    project_root = _make_project(workspace_root)
    subprocess.run(
        ["git", "-C", str(project_root), "init"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(project_root), "config", "user.name", "Test User"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(project_root), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    gitignore_path = project_root / ".gitignore"
    gitignore_path.write_text(
        ".devworkspace/agent.env\n!.devworkspace/agent.env\n",
        encoding="utf-8",
    )

    with pytest.raises(DomainError) as exc:
        connection_service.configure_connection(
            ConfigureConnectionRequest(
                project_id="demo-project",
                connection_name="primary",
                profile=ConnectionProfile.model_validate(_VALID_PROFILE),
                env_updates={"PGHOST": "new-secret-host"},
            )
        )

    assert exc.value.code == ErrorCode.ENV_FILE_INVALID
    assert "new-secret-host" not in exc.value.message
    assert "primary" not in load_manifest(project_root).connections
    assert gitignore_path.read_text(encoding="utf-8") == (
        ".devworkspace/agent.env\n!.devworkspace/agent.env\n"
    )


def test_configure_connection_refuses_to_write_agent_env_when_git_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    workspace_root: Path,
    connection_service: ProjectConnectionService,
) -> None:
    project_root = _make_project(workspace_root)
    subprocess.run(
        ["git", "-C", str(project_root), "init"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(project_root), "config", "user.name", "Test User"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(project_root), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    (project_root / ".gitignore").write_text(
        ".devworkspace/agent.env\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PATH", "")

    with pytest.raises(DomainError) as exc:
        connection_service.configure_connection(
            ConfigureConnectionRequest(
                project_id="demo-project",
                connection_name="primary",
                profile=ConnectionProfile.model_validate(_VALID_PROFILE),
                env_updates={"PGHOST": "new-secret-host"},
            )
        )

    assert exc.value.code == ErrorCode.ENV_FILE_INVALID
    assert "new-secret-host" not in exc.value.message
    assert "primary" not in load_manifest(project_root).connections


def test_configure_connection_rolls_back_manifestless_git_project_on_env_failure(
    monkeypatch: pytest.MonkeyPatch,
    workspace_root: Path,
) -> None:
    project_root = workspace_root / "git-only-project"
    project_root.mkdir()
    subprocess.run(
        ["git", "-C", str(project_root), "init"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(project_root), "config", "user.name", "Test User"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(project_root), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    (project_root / ".gitignore").write_text(
        ".devworkspace/agent.env\n",
        encoding="utf-8",
    )
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    connection_service = ProjectConnectionService(registry)
    monkeypatch.setenv("PATH", "")

    with pytest.raises(DomainError) as exc:
        connection_service.configure_connection(
            ConfigureConnectionRequest(
                project_id="git-only-project",
                connection_name="primary",
                profile=ConnectionProfile.model_validate(_VALID_PROFILE),
                env_updates={"PGHOST": "new-secret-host"},
            )
        )

    assert exc.value.code == ErrorCode.ENV_FILE_INVALID
    assert not (project_root / ".devworkspace.yaml").exists()
    assert not (project_root / ".devworkspace" / "agent.env").exists()


def test_configure_connection_refuses_to_write_agent_env_inside_parent_git_repo(
    workspace_root: Path,
) -> None:
    subprocess.run(
        ["git", "-C", str(workspace_root), "init"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(workspace_root), "config", "user.name", "Test User"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(workspace_root), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    project_root = _make_project(
        workspace_root,
        folder_name="nested-project",
        project_id="nested-project",
    )
    agent_env = project_root / ".devworkspace" / "agent.env"
    agent_env.parent.mkdir(exist_ok=True)
    agent_env.write_text("PGHOST=tracked-host\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(workspace_root), "add", "nested-project/.devworkspace/agent.env"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(workspace_root), "commit", "-m", "track nested agent env"],
        check=True,
        capture_output=True,
    )
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    connection_service = ProjectConnectionService(registry)

    with pytest.raises(DomainError) as exc:
        connection_service.configure_connection(
            ConfigureConnectionRequest(
                project_id="nested-project",
                connection_name="primary",
                profile=ConnectionProfile.model_validate(_VALID_PROFILE),
                env_updates={"PGHOST": "new-secret-host"},
            )
        )

    assert exc.value.code == ErrorCode.ENV_FILE_INVALID
    assert "new-secret-host" not in exc.value.message
    assert "primary" not in load_manifest(project_root).connections
    assert agent_env.read_text(encoding="utf-8") == "PGHOST=tracked-host\n"
