from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")

ConnectionKind = Literal[
    "postgres",
    "mysql",
    "redis",
    "neo4j",
    "falkordb",
    "mongodb",
    "generic_tcp",
]
ConnectionTransport = Literal["direct"]


class ConnectionTestDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["tcp"] = "tcp"
    timeout_sec: int = Field(default=3, ge=1)


class ConnectionProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ConnectionKind
    transport: ConnectionTransport = "direct"
    host_env: str
    port_env: str
    database_env: str | None = None
    user_env: str | None = None
    password_env: str | None = None
    token_env: str | None = None
    ssl_mode_env: str | None = None
    test: ConnectionTestDefinition = Field(default_factory=ConnectionTestDefinition)

    @field_validator(
        "host_env",
        "port_env",
        "database_env",
        "user_env",
        "password_env",
        "token_env",
        "ssl_mode_env",
        mode="before",
    )
    @classmethod
    def strip_env_refs(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("env reference cannot be empty")
        if not _ENV_NAME_RE.fullmatch(normalized):
            raise ValueError("env reference must be a valid environment variable name")
        return normalized


class ConfigureConnectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    connection_name: str
    profile: ConnectionProfile
    env_updates: dict[str, str] = Field(default_factory=dict)

    @field_validator("env_updates")
    @classmethod
    def validate_env_updates(cls, value: dict[str, str]) -> dict[str, str]:
        for key in value:
            if not _ENV_NAME_RE.fullmatch(key):
                raise ValueError("env update keys must be valid environment variable names")
        return value


class ConfigureConnectionResponse(BaseModel):
    project_id: str
    connection_name: str
    profile: ConnectionProfile
    env_keys_updated: list[str] = Field(default_factory=list)


class ListConnectionsResponse(BaseModel):
    project_id: str
    connections: dict[str, ConnectionProfile] = Field(default_factory=dict)


class TestConnectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    __test__ = False

    project_id: str
    connection_name: str


class TestConnectionResponse(BaseModel):
    __test__ = False

    connection_name: str
    kind: ConnectionKind
    transport: ConnectionTransport
    host: str
    port: int = Field(ge=1, le=65535)
    reachable: bool
    message: str


__all__ = [
    "ConfigureConnectionRequest",
    "ConfigureConnectionResponse",
    "ConnectionKind",
    "ConnectionProfile",
    "ConnectionTestDefinition",
    "ConnectionTransport",
    "ListConnectionsResponse",
    "TestConnectionRequest",
    "TestConnectionResponse",
]
