from __future__ import annotations

import shutil
from hashlib import sha256
from pathlib import Path

from dev_workspace_mcp.files.patching import apply_unified_diff_to_text, parse_unified_diff
from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.models.files import (
    ApplyPatchResponse,
    DirEntry,
    FileSummary,
    ListDirResponse,
    PathMutationResponse,
    ReadFileResponse,
    WriteFileResponse,
)
from dev_workspace_mcp.shared.paths import resolve_project_path, to_relative_display


class FileService:
    """Project-relative file operations with basic safety and truncation."""

    def __init__(self, project_root: Path, *, max_read_bytes: int = 200_000) -> None:
        self.project_root = Path(project_root).resolve()
        self.max_read_bytes = max_read_bytes

    def resolve_path(
        self,
        relative_path: str,
        *,
        allow_missing_leaf: bool = False,
        forbid_symlinks: bool = False,
    ) -> Path:
        return resolve_project_path(
            self.project_root,
            relative_path,
            allow_missing_leaf=allow_missing_leaf,
            forbid_symlinks=forbid_symlinks,
        )

    def list_dir(
        self,
        relative_path: str = ".",
        *,
        recursive: bool = False,
        limit: int | None = None,
    ) -> ListDirResponse:
        path = self.resolve_path(relative_path)
        if not path.exists():
            raise DomainError(
                code=ErrorCode.PATH_NOT_FOUND,
                message=f"Path does not exist: {relative_path}",
            )
        if not path.is_dir():
            raise DomainError(
                code=ErrorCode.INVALID_PATH,
                message=f"Path is not a directory: {relative_path}",
            )

        iterator = path.rglob("*") if recursive else path.iterdir()
        entries: list[DirEntry] = []
        truncated = False
        for child in sorted(iterator, key=lambda item: str(item.relative_to(path))):
            if limit is not None and len(entries) >= limit:
                truncated = True
                break
            entries.append(
                DirEntry(
                    path=to_relative_display(child, self.project_root),
                    name=child.name,
                    kind=_kind_for(child),
                    size_bytes=child.stat().st_size if child.exists() and child.is_file() else None,
                    is_hidden=child.name.startswith("."),
                )
            )
        return ListDirResponse(
            path=to_relative_display(path, self.project_root),
            entries=entries,
            truncated=truncated,
        )

    def read_file(
        self,
        relative_path: str,
        *,
        offset: int = 1,
        limit: int | None = None,
        encoding: str = "utf-8",
    ) -> ReadFileResponse:
        path = self.resolve_path(relative_path)
        if not path.exists() or not path.is_file():
            raise DomainError(
                code=ErrorCode.PATH_NOT_FOUND,
                message=f"File does not exist: {relative_path}",
            )

        raw_bytes = path.read_bytes()
        truncated = len(raw_bytes) > self.max_read_bytes
        if truncated:
            raw_bytes = raw_bytes[: self.max_read_bytes]

        text = raw_bytes.decode(encoding, errors="replace")
        lines = text.splitlines()
        start_index = max(offset - 1, 0)
        end_index = None if limit is None else start_index + limit
        selected_lines = lines[start_index:end_index]
        content = "\n".join(selected_lines)
        if text.endswith("\n") and selected_lines and end_index is None:
            content += "\n"

        display_path = to_relative_display(path, self.project_root)
        return ReadFileResponse(
            path=display_path,
            content=content,
            encoding=encoding,
            truncated=truncated,
            summary=_build_summary(display_path, raw_bytes, encoding),
        )

    def write_file(
        self,
        relative_path: str,
        content: str,
        *,
        encoding: str = "utf-8",
        create_parents: bool = True,
        overwrite: bool = True,
    ) -> WriteFileResponse:
        path = self.resolve_path(
            relative_path,
            allow_missing_leaf=True,
            forbid_symlinks=True,
        )
        if path.exists() and not overwrite:
            raise DomainError(
                code=ErrorCode.INVALID_PATH,
                message=f"Refusing to overwrite existing file: {relative_path}",
            )
        if create_parents:
            path.parent.mkdir(parents=True, exist_ok=True)
        elif not path.parent.exists():
            raise DomainError(
                code=ErrorCode.PATH_NOT_FOUND,
                message=f"Parent directory does not exist for: {relative_path}",
            )

        path.write_text(content, encoding=encoding)
        display_path = to_relative_display(path, self.project_root)
        return WriteFileResponse(
            path=display_path,
            bytes_written=len(content.encode(encoding)),
            summary=_build_summary(display_path, path.read_bytes(), encoding),
        )

    def apply_patch(self, patch_text: str) -> ApplyPatchResponse:
        file_patches = parse_unified_diff(patch_text)
        changed_paths: list[str] = []

        for file_patch in file_patches:
            if file_patch.old_path is None and file_patch.new_path is None:
                raise DomainError(
                    code=ErrorCode.PATCH_FAILED,
                    message="Patch must reference at least one project-relative path.",
                )
            if file_patch.new_path is None:
                if file_patch.old_path is None:
                    raise DomainError(
                        code=ErrorCode.PATCH_FAILED,
                        message="Patch delete operation was missing a source path.",
                    )
                self.delete_path(file_patch.old_path)
                changed_paths.append(file_patch.old_path)
                continue

            destination = self.resolve_path(
                file_patch.new_path,
                allow_missing_leaf=True,
                forbid_symlinks=True,
            )
            if file_patch.old_path is None:
                original_text = ""
                destination.parent.mkdir(parents=True, exist_ok=True)
            else:
                source = self.resolve_path(file_patch.old_path, forbid_symlinks=True)
                if not source.exists() or not source.is_file():
                    raise DomainError(
                        code=ErrorCode.PATH_NOT_FOUND,
                        message=f"Patch source file does not exist: {file_patch.old_path}",
                    )
                original_text = source.read_text(encoding="utf-8")
                destination.parent.mkdir(parents=True, exist_ok=True)

            patched_text = apply_unified_diff_to_text(original_text, file_patch)
            destination.write_text(patched_text, encoding="utf-8")
            changed_paths.append(to_relative_display(destination, self.project_root))

        return ApplyPatchResponse(
            changed_paths=changed_paths,
            diff=patch_text,
        )

    def move_path(
        self,
        source_path: str,
        destination_path: str,
        *,
        overwrite: bool = False,
    ) -> PathMutationResponse:
        source = self.resolve_path(source_path, forbid_symlinks=True)
        destination = self.resolve_path(
            destination_path,
            allow_missing_leaf=True,
            forbid_symlinks=True,
        )
        if not source.exists():
            raise DomainError(
                code=ErrorCode.PATH_NOT_FOUND,
                message=f"Path does not exist: {source_path}",
            )
        if destination.exists():
            if not overwrite:
                raise DomainError(
                    code=ErrorCode.INVALID_PATH,
                    message=f"Destination already exists: {destination_path}",
                )
            if destination.is_dir() and not source.is_dir():
                raise DomainError(
                    code=ErrorCode.INVALID_PATH,
                    message="Refusing to overwrite a directory with a file move.",
                )
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        return PathMutationResponse(
            path=to_relative_display(destination, self.project_root),
            existed=True,
            changed=True,
        )

    def delete_path(
        self,
        relative_path: str,
        *,
        recursive: bool = False,
        missing_ok: bool = False,
    ) -> PathMutationResponse:
        path = self.resolve_path(relative_path, forbid_symlinks=True)
        existed = path.exists()
        if not existed:
            if not missing_ok:
                raise DomainError(
                    code=ErrorCode.PATH_NOT_FOUND,
                    message=f"Path does not exist: {relative_path}",
                )
            return PathMutationResponse(path=relative_path, existed=False, changed=False)

        if path.is_dir():
            if not recursive:
                raise DomainError(
                    code=ErrorCode.INVALID_PATH,
                    message="Refusing to delete a directory without recursive=True.",
                )
            shutil.rmtree(path)
        else:
            path.unlink()
        return PathMutationResponse(
            path=to_relative_display(path, self.project_root),
            existed=True,
            changed=True,
        )



def _build_summary(display_path: str, raw_bytes: bytes, encoding: str) -> FileSummary:
    text = raw_bytes.decode(encoding, errors="replace")
    return FileSummary(
        path=display_path,
        size_bytes=len(raw_bytes),
        line_count=len(text.splitlines()),
        encoding=encoding,
        sha256=sha256(raw_bytes).hexdigest(),
    )



def _kind_for(path: Path) -> str:
    if path.is_symlink():
        return "symlink"
    if path.is_dir():
        return "directory"
    if path.is_file():
        return "file"
    return "other"


__all__ = ["FileService"]
