from __future__ import annotations

import re
from dataclasses import dataclass, field

from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.errors import ErrorCode

_HUNK_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)"
    r"(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)"
    r"(?:,(?P<new_count>\d+))? @@"
)


@dataclass(slots=True)
class UnifiedHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str] = field(default_factory=list)


@dataclass(slots=True)
class UnifiedFilePatch:
    old_path: str | None
    new_path: str | None
    hunks: list[UnifiedHunk] = field(default_factory=list)


def parse_unified_diff(patch_text: str) -> list[UnifiedFilePatch]:
    lines = patch_text.splitlines()
    patches: list[UnifiedFilePatch] = []
    current: UnifiedFilePatch | None = None
    current_hunk: UnifiedHunk | None = None
    index = 0

    while index < len(lines):
        line = lines[index]
        if not line:
            if current_hunk is not None:
                current_hunk.lines.append(" ")
            index += 1
            continue
        if line.startswith(("diff --git ", "index ", "new file mode ", "deleted file mode ")):
            index += 1
            continue
        if line.startswith("--- "):
            old_path = _normalize_patch_path(line[4:])
            index += 1
            if index >= len(lines) or not lines[index].startswith("+++ "):
                raise DomainError(
                    code=ErrorCode.PATCH_FAILED,
                    message="Unified diff is missing the '+++' file header.",
                )
            new_path = _normalize_patch_path(lines[index][4:])
            current = UnifiedFilePatch(old_path=old_path, new_path=new_path)
            patches.append(current)
            current_hunk = None
            index += 1
            continue
        if line.startswith("@@ "):
            if current is None:
                raise DomainError(
                    code=ErrorCode.PATCH_FAILED,
                    message="Unified diff hunk appeared before any file header.",
                )
            match = _HUNK_RE.match(line)
            if match is None:
                raise DomainError(
                    code=ErrorCode.PATCH_FAILED,
                    message=f"Invalid unified diff hunk header: {line}",
                )
            current_hunk = UnifiedHunk(
                old_start=int(match.group("old_start")),
                old_count=int(match.group("old_count") or "1"),
                new_start=int(match.group("new_start")),
                new_count=int(match.group("new_count") or "1"),
            )
            current.hunks.append(current_hunk)
            index += 1
            continue
        if current_hunk is not None and line[:1] in {" ", "+", "-", "\\"}:
            current_hunk.lines.append(line)
            index += 1
            continue
        raise DomainError(
            code=ErrorCode.PATCH_FAILED,
            message=f"Unsupported patch line: {line}",
        )

    if not patches:
        raise DomainError(
            code=ErrorCode.PATCH_FAILED,
            message="Patch did not contain any file changes.",
        )
    return patches


def apply_unified_diff_to_text(original_text: str, file_patch: UnifiedFilePatch) -> str:
    original_lines = original_text.splitlines()
    result: list[str] = []
    original_index = 0

    for hunk in file_patch.hunks:
        start_index = max(hunk.old_start - 1, 0)
        if start_index < original_index:
            raise DomainError(
                code=ErrorCode.PATCH_FAILED,
                message="Patch hunks overlap or are out of order.",
            )
        result.extend(original_lines[original_index:start_index])
        current_index = start_index
        consumed_old = 0
        consumed_new = 0

        for line in hunk.lines:
            prefix = line[:1]
            if prefix == "\\":
                continue
            content = line[1:]
            if prefix == " ":
                _assert_line_matches(original_lines, current_index, content)
                result.append(content)
                current_index += 1
                consumed_old += 1
                consumed_new += 1
            elif prefix == "-":
                _assert_line_matches(original_lines, current_index, content)
                current_index += 1
                consumed_old += 1
            elif prefix == "+":
                result.append(content)
                consumed_new += 1
            else:
                raise DomainError(
                    code=ErrorCode.PATCH_FAILED,
                    message=f"Unsupported hunk operation: {line}",
                )

        if consumed_old != hunk.old_count:
            raise DomainError(
                code=ErrorCode.PATCH_FAILED,
                message="Patch hunk old-line count did not match the header.",
            )
        if consumed_new != hunk.new_count:
            raise DomainError(
                code=ErrorCode.PATCH_FAILED,
                message="Patch hunk new-line count did not match the header.",
            )
        original_index = current_index

    result.extend(original_lines[original_index:])
    patched = "\n".join(result)
    if result and (original_text.endswith("\n") or _patch_adds_trailing_newline(file_patch)):
        patched += "\n"
    return patched


def _assert_line_matches(original_lines: list[str], index: int, expected: str) -> None:
    actual = original_lines[index] if index < len(original_lines) else None
    if actual != expected:
        raise DomainError(
            code=ErrorCode.PATCH_FAILED,
            message="Patch context did not match file contents.",
            details={"expected": expected, "actual": actual, "line_index": index},
        )


def _patch_adds_trailing_newline(file_patch: UnifiedFilePatch) -> bool:
    for hunk in reversed(file_patch.hunks):
        for line in reversed(hunk.lines):
            if line.startswith("\\"):
                continue
            return True
    return False


def _normalize_patch_path(raw_path: str) -> str | None:
    path = raw_path.strip()
    if path == "/dev/null":
        return None
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


__all__ = [
    "UnifiedFilePatch",
    "UnifiedHunk",
    "apply_unified_diff_to_text",
    "parse_unified_diff",
]
