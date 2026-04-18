from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dev_workspace_mcp.codegraph.models import CodegraphEdge, CodegraphIndexSnapshot, CodegraphNode
from dev_workspace_mcp.mcp_server.errors import DomainError
from dev_workspace_mcp.models.codegraph import (
    CallPathNode,
    CallPathResponse,
    ClassOverviewItem,
    CodeMatch,
    FunctionContextResponse,
    FunctionOverviewItem,
    GrepResponse,
    ModuleOverviewResponse,
    SourceReadResponse,
    SymbolContextMatch,
)
from dev_workspace_mcp.models.errors import ErrorCode
from dev_workspace_mcp.shared.paths import resolve_project_path, to_relative_display
from dev_workspace_mcp.shared.text import truncate_text

_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
}


@dataclass(slots=True)
class InProcessCodegraphProvider:
    max_matches: int = 200
    max_source_chars: int = 20_000

    def module_overview(self, project_root: Path, path: str) -> ModuleOverviewResponse:
        file_path = self._resolve_project_path(project_root, path)
        content = self._read_text_file(file_path)
        lines = content.splitlines()
        if file_path.suffix == ".py":
            tree = self._parse_python(content, path)
            imports: list[str] = []
            classes: list[ClassOverviewItem] = []
            functions: list[FunctionOverviewItem] = []
            for node in tree.body:
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    imports.extend(f"{module}.{alias.name}".strip(".") for alias in node.names)
                elif isinstance(node, ast.ClassDef):
                    methods = [
                        child.name
                        for child in node.body
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ]
                    classes.append(
                        ClassOverviewItem(
                            name=node.name,
                            line_start=node.lineno,
                            line_end=self._end_lineno(node),
                            methods=methods,
                        )
                    )
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append(
                        FunctionOverviewItem(
                            name=node.name,
                            line_start=node.lineno,
                            line_end=self._end_lineno(node),
                        )
                    )
            return ModuleOverviewResponse(
                path=to_relative_display(file_path, project_root),
                language="python",
                imports=imports,
                classes=classes,
                functions=functions,
                line_count=len(lines),
            )

        return ModuleOverviewResponse(
            path=to_relative_display(file_path, project_root),
            language=self._detect_language(file_path),
            line_count=len(lines),
        )

    def function_context(
        self,
        project_root: Path,
        symbol: str,
        *,
        path: str | None = None,
        watched_paths: list[str] | None = None,
    ) -> FunctionContextResponse:
        matches: list[SymbolContextMatch] = []
        for file_path in self._iter_candidate_files(
            project_root,
            path=path,
            watched_paths=watched_paths,
            python_only=True,
        ):
            content = self._read_text_file(file_path)
            display_path = to_relative_display(file_path, project_root)
            tree = self._parse_python(content, display_path)
            lines = content.splitlines()
            for node, kind in self._iter_python_symbols(tree):
                if getattr(node, "name", None) != symbol:
                    continue
                line_start = node.lineno
                line_end = self._end_lineno(node)
                snippet = "\n".join(lines[line_start - 1 : line_end])
                signature = lines[line_start - 1].strip() if lines else symbol
                matches.append(
                    SymbolContextMatch(
                        name=symbol,
                        kind=kind,
                        path=display_path,
                        line_start=line_start,
                        line_end=line_end,
                        signature=signature,
                        source=truncate_text(snippet, self.max_source_chars),
                    )
                )
        if not matches:
            raise DomainError(
                code=ErrorCode.PATH_NOT_FOUND,
                message=f"Symbol not found: {symbol}",
                hint="Use module_overview or grep first to find the right path or symbol name.",
            )
        matches.sort(key=lambda item: (item.path, item.line_start))
        return FunctionContextResponse(symbol=symbol, matches=matches)

    def grep(
        self,
        project_root: Path,
        pattern: str,
        *,
        path: str | None = None,
        watched_paths: list[str] | None = None,
        ignore_case: bool = False,
    ) -> GrepResponse:
        try:
            regex = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
        except re.error as exc:
            raise DomainError(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"Invalid regex pattern: {pattern}",
                details={"error": str(exc)},
            ) from exc

        matches: list[CodeMatch] = []
        truncated = False
        for file_path in self._iter_candidate_files(
            project_root,
            path=path,
            watched_paths=watched_paths,
        ):
            content = self._read_text_file(file_path, allow_missing=True)
            if content is None:
                continue
            for line_number, line_text in enumerate(content.splitlines(), start=1):
                if regex.search(line_text):
                    matches.append(
                        CodeMatch(
                            path=to_relative_display(file_path, project_root),
                            line_number=line_number,
                            line_text=line_text,
                        )
                    )
                    if len(matches) >= self.max_matches:
                        truncated = True
                        break
            if truncated:
                break
        return GrepResponse(pattern=pattern, matches=matches, truncated=truncated)

    def find_references(
        self,
        project_root: Path,
        symbol: str,
        *,
        path: str | None = None,
        watched_paths: list[str] | None = None,
    ) -> GrepResponse:
        pattern = rf"\b{re.escape(symbol)}\b"
        return self.grep(project_root, pattern, path=path, watched_paths=watched_paths)

    def call_path(
        self,
        project_root: Path,
        symbol: str,
        *,
        path: str | None = None,
        watched_paths: list[str] | None = None,
    ) -> CallPathResponse:
        indexed: dict[str, dict[str, object]] = {}

        for file_path in self._iter_candidate_files(
            project_root,
            path=path,
            watched_paths=watched_paths,
            python_only=True,
        ):
            content = self._read_text_file(file_path)
            display_path = to_relative_display(file_path, project_root)
            tree = self._parse_python(content, display_path)
            for node, kind in self._iter_python_symbols(tree):
                name = getattr(node, "name", None)
                if not isinstance(name, str):
                    continue
                indexed[name] = {
                    "kind": kind,
                    "path": display_path,
                    "line_start": getattr(node, "lineno", 1),
                    "line_end": self._end_lineno(node),
                    "calls": set() if kind == "class" else self._extract_called_names(node),
                }

        target = indexed.get(symbol)
        if target is None:
            raise DomainError(
                code=ErrorCode.PATH_NOT_FOUND,
                message=f"Symbol not found: {symbol}",
                hint="Use module_overview or function_context first to find the symbol.",
            )

        incoming: list[CallPathNode] = []
        for candidate_symbol, meta in indexed.items():
            if candidate_symbol == symbol:
                continue
            calls = meta.get("calls", set())
            if symbol in calls:
                incoming.append(
                    CallPathNode(
                        symbol=candidate_symbol,
                        kind=str(meta["kind"]),
                        path=str(meta["path"]),
                        line_start=int(meta["line_start"]),
                        line_end=int(meta["line_end"]),
                    )
                )

        outgoing: list[CallPathNode] = []
        for called in sorted(target.get("calls", set())):
            callee = indexed.get(called)
            if callee is None:
                continue
            outgoing.append(
                CallPathNode(
                    symbol=called,
                    kind=str(callee["kind"]),
                    path=str(callee["path"]),
                    line_start=int(callee["line_start"]),
                    line_end=int(callee["line_end"]),
                )
            )

        incoming.sort(key=lambda item: (item.path, item.line_start, item.symbol))
        return CallPathResponse(
            symbol=symbol,
            definition=CallPathNode(
                symbol=symbol,
                kind=str(target["kind"]),
                path=str(target["path"]),
                line_start=int(target["line_start"]),
                line_end=int(target["line_end"]),
            ),
            incoming=incoming,
            outgoing=outgoing,
        )

    def read_source(
        self,
        project_root: Path,
        path: str,
        *,
        start_line: int = 1,
        end_line: int | None = None,
    ) -> SourceReadResponse:
        file_path = self._resolve_project_path(project_root, path)
        lines = self._read_text_file(file_path).splitlines()
        if not lines:
            return SourceReadResponse(path=path, start_line=1, end_line=1, content="")
        last_line = len(lines) if end_line is None else min(end_line, len(lines))
        first_line = max(start_line, 1)
        if first_line > last_line:
            raise DomainError(
                code=ErrorCode.VALIDATION_ERROR,
                message="start_line must be less than or equal to end_line.",
            )
        snippet = "\n".join(lines[first_line - 1 : last_line])
        truncated = len(snippet) > self.max_source_chars
        return SourceReadResponse(
            path=to_relative_display(file_path, project_root),
            start_line=first_line,
            end_line=last_line,
            content=truncate_text(snippet, self.max_source_chars),
            truncated=truncated,
        )

    def build_index_snapshot(
        self,
        project_id: str,
        project_root: Path,
        *,
        watched_paths: list[str] | None = None,
    ) -> CodegraphIndexSnapshot:
        file_paths = sorted(
            self._iter_candidate_files(
                project_root,
                watched_paths=watched_paths,
            ),
            key=lambda item: to_relative_display(item, project_root),
        )
        nodes: list[CodegraphNode] = []
        edges: list[CodegraphEdge] = []
        digest = hashlib.sha256()

        for file_path in file_paths:
            display_path = to_relative_display(file_path, project_root)
            digest.update(display_path.encode("utf-8"))
            raw = file_path.read_bytes()
            digest.update(raw)
            nodes.append(
                CodegraphNode(
                    identifier=display_path,
                    name=file_path.name,
                    kind="file",
                    path=display_path,
                )
            )
            if file_path.suffix != ".py":
                continue
            content = raw.decode("utf-8", errors="replace")
            tree = self._parse_python(content, display_path)
            lines = content.splitlines()
            for node, kind in self._iter_python_symbols(tree):
                name = getattr(node, "name", None)
                if not isinstance(name, str):
                    continue
                identifier = f"{display_path}:{name}"
                line_start = getattr(node, "lineno", 1)
                line_end = self._end_lineno(node)
                snippet = "\n".join(lines[line_start - 1 : line_end])
                signature = lines[line_start - 1].strip() if lines else name
                nodes.append(
                    CodegraphNode(
                        identifier=identifier,
                        name=name,
                        kind=kind,
                        path=display_path,
                        line_start=line_start,
                        line_end=line_end,
                        signature=signature,
                        source=truncate_text(snippet, self.max_source_chars),
                    )
                )
                edges.append(
                    CodegraphEdge(
                        source=display_path,
                        target=identifier,
                        relation="defines",
                        path=display_path,
                    )
                )
                if kind == "class":
                    continue
                for called_name, call_line_number, call_line_text in self._extract_call_sites(
                    node,
                    lines,
                ):
                    edges.append(
                        CodegraphEdge(
                            source=identifier,
                            target=called_name,
                            relation="calls",
                            path=display_path,
                            line_number=call_line_number,
                            line_text=call_line_text,
                        )
                    )

        symbol_count = sum(1 for node in nodes if node.kind != "file")
        revision = digest.hexdigest()[:16] if file_paths else None
        return CodegraphIndexSnapshot(
            project_id=project_id,
            revision=revision,
            indexed_at=datetime.now(UTC),
            file_count=len(file_paths),
            symbol_count=symbol_count,
            nodes=nodes,
            edges=edges,
        )

    def _iter_candidate_files(
        self,
        project_root: Path,
        *,
        path: str | None = None,
        watched_paths: list[str] | None = None,
        python_only: bool = False,
    ):
        if path is not None:
            roots = [self._resolve_project_path(project_root, path)]
        else:
            configured_paths = list(watched_paths or []) or ["."]
            roots = [self._resolve_project_path(project_root, item) for item in configured_paths]

        seen: set[Path] = set()
        for root in roots:
            if root.is_file():
                if root not in seen and (not python_only or root.suffix == ".py"):
                    seen.add(root)
                    yield root
                continue
            for file_path in root.rglob("*"):
                if any(part in _IGNORED_DIRS for part in file_path.parts):
                    continue
                if not file_path.is_file():
                    continue
                resolved_file = resolve_project_path(
                    project_root,
                    str(file_path.relative_to(project_root)),
                )
                if resolved_file in seen:
                    continue
                if python_only and resolved_file.suffix != ".py":
                    continue
                seen.add(resolved_file)
                yield resolved_file

    def _resolve_project_path(self, project_root: Path, relative_path: str) -> Path:
        path = resolve_project_path(project_root, relative_path)
        if not path.exists() or (not path.is_file() and not path.is_dir()):
            raise DomainError(
                code=ErrorCode.PATH_NOT_FOUND,
                message=f"Path does not exist: {relative_path}",
            )
        return path

    def _read_text_file(self, path: Path, *, allow_missing: bool = False) -> str | None:
        try:
            raw = path.read_bytes()
        except OSError:
            if allow_missing:
                return None
            raise
        if b"\x00" in raw:
            return None if allow_missing else raw.decode("utf-8", errors="replace")
        return raw.decode("utf-8", errors="replace")

    def _parse_python(self, content: str, display_path: str) -> ast.Module:
        try:
            return ast.parse(content)
        except SyntaxError as exc:
            raise DomainError(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"Failed to parse Python source in {display_path}",
                details={"error": str(exc)},
            ) from exc

    @staticmethod
    def _iter_python_symbols(tree: ast.Module):
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                yield node, "class"
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        yield child, "method"
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield node, "function"

    @staticmethod
    def _extract_called_names(node: ast.AST) -> set[str]:
        return {name for name, _, _ in InProcessCodegraphProvider._extract_call_sites(node, [])}

    @staticmethod
    def _extract_call_sites(node: ast.AST, lines: list[str]) -> list[tuple[str, int, str]]:
        calls: list[tuple[str, int, str]] = []
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            name: str | None = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if not name:
                continue
            line_number = getattr(child, "lineno", getattr(node, "lineno", 1))
            line_text = lines[line_number - 1] if 0 < line_number <= len(lines) else ""
            calls.append((name, line_number, line_text))
        return calls

    @staticmethod
    def _end_lineno(node: ast.AST) -> int:
        end_lineno = getattr(node, "end_lineno", None)
        return end_lineno if isinstance(end_lineno, int) else getattr(node, "lineno", 1)

    @staticmethod
    def _detect_language(path: Path) -> str:
        if path.suffix == ".py":
            return "python"
        if path.suffix in {".ts", ".tsx", ".js", ".jsx"}:
            return "typescript" if path.suffix in {".ts", ".tsx"} else "javascript"
        if path.suffix in {".md", ".txt", ".json", ".yaml", ".yml"}:
            return path.suffix.lstrip(".")
        return "text"


__all__ = ["InProcessCodegraphProvider"]
