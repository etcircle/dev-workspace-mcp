from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

BootstrapMode = Literal["create", "clone", "import"]
BootstrapTemplate = Literal["generic", "python", "node"]


class BootstrapProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: BootstrapMode
    folder_name: str | None = None
    repo_url: str | None = None
    path: str | None = None
    branch: str | None = None
    project_id: str | None = None
    display_name: str | None = None
    git_init: bool = False
    template: BootstrapTemplate | None = None

    @model_validator(mode="after")
    def validate_mode_specific_fields(self) -> BootstrapProjectRequest:
        mode_forbidden_fields: dict[BootstrapMode, dict[str, Any]] = {
            "create": {
                "repo_url": self.repo_url,
                "path": self.path,
                "branch": self.branch,
            },
            "clone": {
                "path": self.path,
                "git_init": self.git_init,
                "template": self.template,
            },
            "import": {
                "folder_name": self.folder_name,
                "repo_url": self.repo_url,
                "branch": self.branch,
                "git_init": self.git_init,
                "template": self.template,
            },
        }
        if self.mode == "create" and not (self.folder_name or "").strip():
            raise ValueError("folder_name is required for create mode")
        if self.mode == "clone" and not (self.repo_url or "").strip():
            raise ValueError("repo_url is required for clone mode")
        if self.mode == "import" and not (self.path or "").strip():
            raise ValueError("path is required for import mode")
        if self.template is not None:
            raise ValueError("template is not implemented in this wave")
        forbidden = [
            field_name
            for field_name, value in mode_forbidden_fields[self.mode].items()
            if value not in (None, False)
        ]
        if forbidden:
            fields = ", ".join(sorted(forbidden))
            raise ValueError(f"{fields} not allowed for {self.mode} mode")
        return self


class BootstrapProjectResponse(BaseModel):
    project_id: str
    root_path: str
    manifest_path: str
    created_files: list[str] = Field(default_factory=list)
    git_initialized: bool = False
    git_cloned: bool = False
    warnings: list[str] = Field(default_factory=list)
    recommended_next_tools: list[str] = Field(default_factory=list)


__all__ = [
    "BootstrapMode",
    "BootstrapProjectRequest",
    "BootstrapProjectResponse",
    "BootstrapTemplate",
]
