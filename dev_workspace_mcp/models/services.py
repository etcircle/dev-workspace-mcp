from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from dev_workspace_mcp.models.common import ServiceHealth

ServiceStatus = Literal["stopped", "starting", "running", "degraded", "failed", "unknown"]


class ServicePort(BaseModel):
    port: int = Field(ge=1, le=65535)
    protocol: Literal["tcp", "udp"] = "tcp"
    description: str | None = None


class ServiceRuntimeState(BaseModel):
    status: ServiceStatus = "unknown"
    service_instance_id: str | None = None
    pid: int | None = Field(default=None, ge=1)
    command: list[str] = Field(default_factory=list)
    cwd: str | None = None
    restart_count: int = Field(default=0, ge=0)
    last_started_at: datetime | None = None
    last_stopped_at: datetime | None = None
    health: ServiceHealth = Field(default_factory=ServiceHealth)


class ServiceRecord(BaseModel):
    project_id: str
    service_name: str
    display_name: str | None = None
    ports: list[ServicePort] = Field(default_factory=list)
    runtime: ServiceRuntimeState = Field(default_factory=ServiceRuntimeState)


class ListServicesRequest(BaseModel):
    project_id: str


class ListServicesResponse(BaseModel):
    services: list[ServiceRecord] = Field(default_factory=list)


class ServiceStatusRequest(BaseModel):
    project_id: str
    service_name: str


class ServiceStatusResponse(BaseModel):
    service: ServiceRecord


class ServiceActionRequest(BaseModel):
    project_id: str
    service_name: str


class ServiceActionResponse(BaseModel):
    service: ServiceRecord


class LogLine(BaseModel):
    message: str
    stream: Literal["stdout", "stderr", "system"] = "stdout"
    line_number: int | None = Field(default=None, ge=0)
    timestamp: datetime | None = None


class GetLogsRequest(BaseModel):
    project_id: str
    service_name: str
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=200, ge=1)


class GetLogsResponse(BaseModel):
    service_name: str
    lines: list[LogLine] = Field(default_factory=list)
    next_offset: int | None = Field(default=None, ge=0)
    truncated: bool = False


__all__ = [
    "GetLogsRequest",
    "GetLogsResponse",
    "ListServicesRequest",
    "ListServicesResponse",
    "LogLine",
    "ServiceActionRequest",
    "ServiceActionResponse",
    "ServicePort",
    "ServiceRecord",
    "ServiceRuntimeState",
    "ServiceStatus",
    "ServiceStatusRequest",
    "ServiceStatusResponse",
]
