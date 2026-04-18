from __future__ import annotations

from pydantic import BaseModel, Field


class HttpRequestResponse(BaseModel):
    method: str
    url: str
    status_code: int
    headers: dict[str, str] = Field(default_factory=dict)
    text_body: str = ""
    json_body: dict | list | str | int | float | bool | None = None


__all__ = ["HttpRequestResponse"]
