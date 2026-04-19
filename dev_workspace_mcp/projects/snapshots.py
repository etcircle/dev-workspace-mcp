from __future__ import annotations

import json
import subprocess
import tomllib
from collections import OrderedDict
from pathlib import Path

from dev_workspace_mcp.models.common import WarningMessage
from dev_workspace_mcp.models.projects import (
    CapabilitySummary,
    GitSummary,
    ProjectSnapshot,
    ProjectSnapshotHeader,
    ProjectStackSummary,
    ServiceSummary,
    StateDocSummary,
    WatcherSummary,
)
from dev_workspace_mcp.projects.registry import ProjectRegistry
from dev_workspace_mcp.state_docs.parser import parse_state_document

_STATE_DOC_PATHS = {
    "agents": "AGENTS.md",
    "memory": ".devworkspace/memory.md",
    "roadmap": ".devworkspace/roadmap.md",
    "tasks": ".devworkspace/tasks.md",
}

_DOC_PREVIEW_LIMIT = 5
_SUMMARY_LIMIT = 5
_RECOMMENDED_COMMAND_LIMIT = 6
_STACK_SCAN_FILE_LIMIT = 2_000
_SKIP_STACK_DIRS = {".git", ".venv", "node_modules", "dist", "build", "__pycache__"}

_PYTHON_MANIFESTS = ("pyproject.toml", "requirements.txt", "requirements-dev.txt", "setup.py")
_PACKAGE_MANAGER_FILES = {
    "npm": ("package-lock.json",),
    "pip": ("pyproject.toml", "requirements.txt", "requirements-dev.txt", "setup.py"),
    "poetry": ("poetry.lock",),
    "pipenv": ("Pipfile",),
    "pnpm": ("pnpm-lock.yaml",),
    "yarn": ("yarn.lock",),
    "bun": ("bun.lock", "bun.lockb"),
}
_FRAMEWORK_NAMES = {
    "django": "Django",
    "express": "Express",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "next": "Next.js",
    "react": "React",
    "vue": "Vue",
}
_CAPABILITIES = CapabilitySummary(
    code_navigation=(
        "Code navigation is available through module_overview, read_source, "
        "function_context, find_references, and call_path."
    ),
    watcher=(
        "Watcher status is snapshot-backed only. It reports indexed watch_paths, "
        "but there is no real filesystem watcher backend yet."
    ),
    services=(
        "Manifest-declared services can be listed, started, stopped, restarted, "
        "and inspected for runtime status plus basic health."
    ),
    state_docs=(
        "Repo-local memory, roadmap, and tasks docs can be read and patched under .devworkspace/."
    ),
    commands=(
        "Bounded commands support argv execution, presets, timeouts, "
        "and background jobs under project policy."
    ),
    search=(
        "Text search is available via grep, codegraph symbol tools use an in-memory snapshot, "
        "and search_workspace_memory can query the local SQLite memory index "
        "when it has been indexed."
    ),
    github=(
        "GitHub Issues remain the canonical work tracker, and read-only GitHub repo, issue, "
        "and PR lookups are available from the project's origin remote. Write helpers are "
        "still not implemented in this server."
    ),
)


def build_project_snapshot(
    registry: ProjectRegistry,
    project_id: str,
    *,
    service_manager=None,
    memory_index_service_factory=None,
) -> tuple[ProjectSnapshot, list[WarningMessage]]:
    record = registry.require(project_id)
    warnings: list[WarningMessage] = []
    project_root = Path(record.root_path)

    if not record.manifest_path:
        warnings.append(
            WarningMessage(
                code="MANIFEST_MISSING",
                message="Project discovered without .devworkspace.yaml; using derived defaults.",
            )
        )

    git_summary = _build_git_summary(project_root, warnings)
    state_doc_text = {
        kind: _read_state_doc_text(project_root, kind, warnings=warnings)
        for kind in _STATE_DOC_PATHS
    }
    state_docs = _collect_state_docs(project_root, warnings, state_doc_text=state_doc_text)
    services = _build_service_summaries(record, warnings, service_manager=service_manager)
    watcher = WatcherSummary(
        configured=bool(record.manifest.codegraph.watch_paths),
        active=False,
        watched_paths=record.manifest.codegraph.watch_paths,
        status="configured" if record.manifest.codegraph.watch_paths else "not_configured",
    )
    memory_index_status = None
    recent_decision_titles: list[str] = []
    if memory_index_service_factory is not None:
        try:
            memory_service = memory_index_service_factory(record.project_id)
            memory_index_status = memory_service.get_status().status
            recent_decision_titles = memory_service.recent_decision_titles(limit=_SUMMARY_LIMIT)
        except Exception:
            warnings.append(
                WarningMessage(
                    code="MEMORY_INDEX_STATUS_UNAVAILABLE",
                    message=(
                        "Workspace memory hints could not be refreshed cleanly; "
                        "returning repo-local snapshot context only."
                    ),
                )
            )
    recent_decision_titles = _merge_unique_items(
        recent_decision_titles,
        _recent_decision_doc_titles(project_root, limit=_SUMMARY_LIMIT),
        limit=_SUMMARY_LIMIT,
    )
    standards_docs = _standards_doc_paths(project_root, limit=_SUMMARY_LIMIT)
    tracking_systems = _tracking_systems(
        include_repo_decisions=bool(recent_decision_titles),
        include_memory_index=memory_index_status is not None,
    )

    snapshot = ProjectSnapshot(
        project=ProjectSnapshotHeader(
            project_id=record.project_id,
            display_name=record.display_name,
            aliases=list(record.aliases),
            manifest_present=record.manifest_path is not None,
        ),
        git=git_summary,
        services=services,
        watcher=watcher,
        recent_changed_files=git_summary.changed_paths[:10],
        probes=sorted(record.manifest.probes.keys()),
        presets=sorted(record.manifest.presets.keys()),
        state_docs=state_docs,
        policy=record.policy.summary(),
        stack=_build_stack_summary(project_root),
        agents_summary=_summary_lines_from_markdown(state_doc_text["agents"]),
        memory_summary=_summary_lines_from_markdown(state_doc_text["memory"]),
        active_tasks=_summary_lines_from_state_doc(state_doc_text["tasks"], heading="Active"),
        memory_index_status=memory_index_status,
        recent_decision_titles=recent_decision_titles,
        standards_docs=standards_docs,
        tracking_systems=tracking_systems,
        recommended_commands=_build_recommended_commands(record),
        recommended_next_tools=_build_recommended_next_tools(
            record,
            state_docs,
            watcher,
            memory_index_status=memory_index_status,
        ),
        capabilities=_CAPABILITIES.model_copy(deep=True),
    )
    return snapshot, warnings


def _build_service_summaries(
    record,
    warnings: list[WarningMessage],
    *,
    service_manager=None,
) -> list[ServiceSummary]:
    summaries: list[ServiceSummary] = []
    for name, definition in sorted(record.manifest.services.items()):
        summary = ServiceSummary(
            name=name,
            cwd=definition.cwd,
            ports=list(definition.ports),
            has_health_check=definition.health is not None,
            start_command=list(definition.start),
        )
        if service_manager is not None:
            try:
                service = service_manager.service_status(record.project_id, name).service
            except Exception:
                warnings.append(
                    WarningMessage(
                        code="SERVICE_STATUS_UNAVAILABLE",
                        message=f"Service '{name}' runtime status could not be read cleanly.",
                    )
                )
            else:
                summary = summary.model_copy(
                    update={
                        "status": service.runtime.status,
                        "health_status": service.runtime.health.status,
                        "health_message": service.runtime.health.message,
                        "start_command": list(service.runtime.command or definition.start),
                    },
                    deep=True,
                )
        summaries.append(summary)
    return summaries


def _collect_state_docs(
    project_root: Path,
    warnings: list[WarningMessage],
    *,
    state_doc_text: dict[str, str],
) -> list[StateDocSummary]:
    summaries: list[StateDocSummary] = []
    for kind, relative_path in _STATE_DOC_PATHS.items():
        text = state_doc_text[kind]
        parsed = parse_state_document(text) if text else {}
        summaries.append(
            StateDocSummary(
                kind=kind,
                path=relative_path,
                exists=bool(text) or (project_root / relative_path).exists(),
                char_count=len(text),
                section_headings=[heading for heading in parsed if heading != "body"],
                preview_lines=_preview_lines(text),
            )
        )
        if kind == "agents" and not (project_root / relative_path).exists():
            warnings.append(
                WarningMessage(
                    code="AGENTS_MISSING",
                    message="Project is missing AGENTS.md, so stable repo guidance is absent.",
                )
            )
    return summaries


def _build_stack_summary(project_root: Path) -> ProjectStackSummary:
    languages: set[str] = set()
    frameworks: set[str] = set()
    package_managers: set[str] = set()

    pyproject_path = project_root / "pyproject.toml"
    package_json_path = project_root / "package.json"

    if any((project_root / name).exists() for name in _PYTHON_MANIFESTS):
        languages.add("Python")
    if pyproject_path.exists():
        frameworks.update(_frameworks_from_pyproject(pyproject_path))

    package_json = _load_json(package_json_path)
    if package_json_path.exists():
        languages.add("JavaScript")
        frameworks.update(_frameworks_from_package_json(package_json))
        if _package_json_implies_typescript(package_json):
            languages.add("TypeScript")

    languages.update(_languages_from_project_files(project_root))

    for manager, filenames in _PACKAGE_MANAGER_FILES.items():
        if any((project_root / filename).exists() for filename in filenames):
            package_managers.add(manager)

    if "TypeScript" in languages and "JavaScript" in languages:
        languages.remove("JavaScript")

    return ProjectStackSummary(
        languages=sorted(languages),
        frameworks=sorted(frameworks),
        package_managers=sorted(package_managers),
    )


def _frameworks_from_pyproject(path: Path) -> set[str]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return set()

    dependencies: list[str] = []
    project_data = data.get("project", {})
    if isinstance(project_data, dict):
        dependencies.extend(project_data.get("dependencies", []))
        optional_dependencies = project_data.get("optional-dependencies", {})
        if isinstance(optional_dependencies, dict):
            for values in optional_dependencies.values():
                if isinstance(values, list):
                    dependencies.extend(values)

    tool_data = data.get("tool", {})
    if isinstance(tool_data, dict):
        poetry_data = tool_data.get("poetry", {})
        if isinstance(poetry_data, dict):
            poetry_dependencies = poetry_data.get("dependencies", {})
            if isinstance(poetry_dependencies, dict):
                dependencies.extend(poetry_dependencies.keys())

    return _frameworks_from_dependency_names(dependencies)


def _frameworks_from_package_json(data: dict[str, object]) -> set[str]:
    dependencies: list[str] = []
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        values = data.get(key, {})
        if isinstance(values, dict):
            dependencies.extend(values.keys())
    return _frameworks_from_dependency_names(dependencies)


def _frameworks_from_dependency_names(names) -> set[str]:
    frameworks: set[str] = set()
    for name in names:
        framework = _FRAMEWORK_NAMES.get(_normalize_dependency_name(name))
        if framework:
            frameworks.add(framework)
    return frameworks


def _normalize_dependency_name(name) -> str:
    normalized = str(name).strip().lower().split("[", 1)[0].strip()
    for separator in ("<=", ">=", "==", "!=", "~=", "<", ">", "=", "^"):
        normalized = normalized.split(separator, 1)[0].strip()
    return normalized


def _package_json_implies_typescript(data: dict[str, object]) -> bool:
    for key in ("dependencies", "devDependencies"):
        values = data.get(key, {})
        if isinstance(values, dict) and "typescript" in values:
            return True
    return False


def _languages_from_project_files(project_root: Path) -> set[str]:
    languages: set[str] = set()
    scanned_files = 0
    for path in project_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_STACK_DIRS for part in path.parts):
            continue

        scanned_files += 1
        if scanned_files > _STACK_SCAN_FILE_LIMIT:
            break

        suffix = path.suffix.lower()
        if suffix == ".py":
            languages.add("Python")
        elif suffix in {".ts", ".tsx"}:
            languages.add("TypeScript")
        elif suffix in {".js", ".jsx"}:
            languages.add("JavaScript")
    return languages


def _build_recommended_commands(record) -> list[str]:
    commands: list[str] = []
    for preset_name in sorted(record.manifest.presets):
        commands.append(f"run_command preset={preset_name}")
    for probe_name in sorted(record.manifest.probes):
        commands.append(f"run_probe probe_name={probe_name}")
    for service_name in sorted(record.manifest.services):
        commands.append(f"start_service service_name={service_name}")
        commands.append(f"service_status service_name={service_name}")
    return commands[:_RECOMMENDED_COMMAND_LIMIT]


def _build_recommended_next_tools(
    record,
    state_docs: list[StateDocSummary],
    watcher: WatcherSummary,
    *,
    memory_index_status: str | None,
) -> list[str]:
    tools: list[str] = []
    if any(doc.exists for doc in state_docs):
        tools.append("read_state_doc")
    if memory_index_status is not None:
        tools.append("memory_index_status")
        if memory_index_status in {"missing", "empty", "stale"}:
            tools.append("reindex_workspace_memory")
        if memory_index_status in {"ready", "stale"}:
            tools.append("search_workspace_memory")
    if record.manifest.presets:
        tools.append("run_command")
    if record.manifest.probes:
        tools.append("run_probe")
    if record.manifest.services:
        tools.append("service_status")
    if watcher.configured:
        tools.append("watcher_health")
    tools.extend(["read_file", "grep"])
    return list(OrderedDict.fromkeys(tools))



def _standards_doc_paths(project_root: Path, *, limit: int) -> list[str]:
    standards_dir = project_root / "docs" / "standards"
    if limit <= 0 or not standards_dir.is_dir():
        return []
    paths = [
        path.relative_to(project_root).as_posix()
        for path in sorted(standards_dir.rglob("*.md"))
        if path.is_file() and not path.is_symlink()
    ]
    return paths[:limit]



def _recent_decision_doc_titles(project_root: Path, *, limit: int) -> list[str]:
    decisions_dir = project_root / "docs" / "decisions"
    if limit <= 0 or not decisions_dir.is_dir():
        return []
    candidates = [
        path
        for path in decisions_dir.rglob("*.md")
        if path.is_file() and not path.is_symlink()
    ]
    candidates.sort(key=lambda path: (path.stat().st_mtime, path.name), reverse=True)
    titles: list[str] = []
    for path in candidates:
        title = _markdown_title(path) or path.stem
        titles.append(title)
        if len(titles) >= limit:
            break
    return titles



def _tracking_systems(
    *,
    include_repo_decisions: bool,
    include_memory_index: bool,
) -> list[str]:
    systems = ["GitHub Issues"]
    if include_repo_decisions:
        systems.append("Repo Decisions")
    if include_memory_index:
        systems.append("SQLite Memory Index")
    return systems



def _merge_unique_items(*groups: list[str], limit: int) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            merged.append(normalized)
            seen.add(normalized)
            if len(merged) >= limit:
                return merged
    return merged



def _markdown_title(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
    return None



def _preview_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        lines.append(stripped)
        if len(lines) >= _DOC_PREVIEW_LIMIT:
            break
    return lines


def _summary_lines_from_markdown(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            item = stripped.lstrip("#").strip()
        elif stripped[0] in {"-", "*", "+"}:
            item = stripped[1:].strip()
        elif ". " in stripped:
            prefix, remainder = stripped.split(". ", 1)
            item = remainder.strip() if prefix.isdigit() else stripped
        else:
            item = stripped
        if item:
            lines.append(item)
        if len(lines) >= _SUMMARY_LIMIT:
            break
    return lines


def _summary_lines_from_state_doc(text: str, *, heading: str | None = None) -> list[str]:
    if heading:
        parsed = parse_state_document(text)
        section = parsed.get(heading)
        if section:
            return _summary_lines_from_markdown(section)
    return _summary_lines_from_markdown(text)


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_state_doc_text(
    project_root: Path,
    kind: str,
    *,
    warnings: list[WarningMessage] | None = None,
) -> str:
    path = project_root / _STATE_DOC_PATHS[kind]
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        if warnings is not None:
            warnings.append(
                WarningMessage(
                    code="STATE_DOC_UNREADABLE",
                    message=f"State doc '{_STATE_DOC_PATHS[kind]}' could not be read as UTF-8.",
                )
            )
        return ""


def _build_git_summary(project_root: Path, warnings: list[WarningMessage]) -> GitSummary:
    if not (project_root / ".git").exists():
        return GitSummary(is_repo=False)

    branch_result = _run_git(project_root, ["branch", "--show-current"])
    status_result = _run_git(
        project_root,
        ["status", "--short", "--branch", "--untracked-files=all"],
    )
    if branch_result is None or status_result is None:
        warnings.append(
            WarningMessage(
                code="GIT_STATUS_UNAVAILABLE",
                message="Project looks git-backed but git status could not be read cleanly.",
            )
        )
        return GitSummary(is_repo=True)

    lines = status_result.splitlines()
    header = lines[0] if lines else ""
    entries = lines[1:] if header.startswith("##") else lines

    changed_paths: list[str] = []
    staged_count = 0
    unstaged_count = 0
    untracked_count = 0

    for line in entries:
        if not line:
            continue
        if line.startswith("??"):
            untracked_count += 1
            changed_paths.append(line[3:])
            continue
        status = line[:2]
        if len(status) == 2:
            if status[0] not in {" ", "?"}:
                staged_count += 1
            if status[1] != " ":
                unstaged_count += 1
        changed_paths.append(line[3:])

    return GitSummary(
        is_repo=True,
        branch=(branch_result.strip() or None),
        dirty=bool(entries),
        staged_count=staged_count,
        unstaged_count=unstaged_count,
        untracked_count=untracked_count,
        changed_paths=changed_paths,
    )


def _run_git(project_root: Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()
