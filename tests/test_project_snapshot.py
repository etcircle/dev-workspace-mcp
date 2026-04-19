from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from dev_workspace_mcp.codegraph.service import CodegraphService
from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.tool_registry import build_tool_registry
from dev_workspace_mcp.projects.registry import ProjectRegistry


def _write_policy(project_root, lines: list[str]) -> None:
    policy_dir = project_root / ".devworkspace"
    policy_dir.mkdir(exist_ok=True)
    (policy_dir / "policy.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_project_snapshot_warns_when_manifest_and_agents_are_missing(
    workspace_root,
    make_git_project,
) -> None:
    make_git_project()
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    tools = build_tool_registry(registry)

    result = tools.run("project_snapshot", project_id="git-project")

    assert result["ok"] is True
    assert result["data"]["project"] == {
        "project_id": "git-project",
        "display_name": "git-project",
        "aliases": [],
        "manifest_present": False,
    }
    assert "root_path" not in result["data"]["project"]
    assert "manifest_path" not in result["data"]["project"]
    assert "manifest" not in result["data"]["project"]
    assert "policy" not in result["data"]["project"]
    warning_codes = {warning["code"] for warning in result["warnings"]}
    assert {"MANIFEST_MISSING", "AGENTS_MISSING", "GIT_STATUS_UNAVAILABLE"} <= warning_codes
    assert result["data"]["git"]["is_repo"] is True
    assert result["data"]["watcher"]["configured"] is False
    assert result["data"]["recent_changed_files"] == []
    assert result["data"]["memory_index_status"] == "missing"
    assert result["data"]["recent_decision_titles"] == []
    assert result["data"]["standards_docs"] == []
    assert result["data"]["tracking_systems"] == ["GitHub Issues", "SQLite Memory Index"]
    assert result["data"]["policy"]["command_default"] == "deny"
    assert result["data"]["policy"]["allow_localhost"] is True
    assert any(
        doc["kind"] == "agents" and doc["exists"] is False
        for doc in result["data"]["state_docs"]
    )


def test_project_snapshot_expands_boot_packet_from_repo_local_sources(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project(
        services_block=[
            "services:",
            "  backend:",
            "    cwd: backend",
            f"    start: ['{sys.executable}', '-u', 'service.py']",
            "    ports: [8000]",
            "presets:",
            "  test_backend: ['pytest', '-q']",
            "probes:",
            "  backend_db:",
            "    cwd: backend",
            f"    argv: ['{sys.executable}', '-c', 'print(123)']",
        ]
    )
    (project_root / "AGENTS.md").write_text(
        "# Repo Rules\n"
        "- Use pytest -q\n"
        "- Keep patches small\n\n"
        "# Workflow\n"
        "- Prefer presets first\n",
        encoding="utf-8",
    )
    state_dir = project_root / ".devworkspace"
    state_dir.mkdir()
    (state_dir / "memory.md").write_text(
        "# Context\n"
        "- API runs locally\n"
        "- No Docker in this repo\n",
        encoding="utf-8",
    )
    (state_dir / "tasks.md").write_text(
        "# Active\n"
        "- Finish boot packet\n"
        "- Verify snapshot output\n\n"
        "# Backlog\n"
        "- Later cleanup\n",
        encoding="utf-8",
    )
    _write_policy(
        project_root,
        [
            "env:",
            "  allow: ['PATH', 'HOME', 'LANG', 'LC_ALL', 'APP_MODE']",
            "network:",
            "  allowed_hosts: ['example.com']",
            "command_policy:",
            "  commands:",
            f"    {Path(sys.executable).name}: {{}}",
            "    pytest: {}",
        ],
    )
    src = project_root / "src"
    src.mkdir()
    backend = project_root / "backend"
    backend.mkdir()
    frontend = project_root / "frontend"
    frontend.mkdir()
    (backend / "service.py").write_text(
        "import time\n"
        "print('ready', flush=True)\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    (
        src / "sample.py"
    ).write_text(
        "class Service:\n"
        "    def run(self):\n"
        "        return helper()\n\n"
        "def helper():\n"
        "    return 'ok'\n",
        encoding="utf-8",
    )
    (frontend / "app.tsx").write_text(
        "export function App() {\n"
        "  return <div>ok</div>;\n"
        "}\n",
        encoding="utf-8",
    )
    (project_root / "pyproject.toml").write_text(
        "[project]\n"
        "name = 'demo-app'\n"
        "dependencies = ['fastapi>=0.110']\n",
        encoding="utf-8",
    )
    (project_root / "package.json").write_text(
        json.dumps(
            {
                "name": "demo-app",
                "dependencies": {"react": "18.0.0"},
                "devDependencies": {"typescript": "5.0.0"},
            }
        ),
        encoding="utf-8",
    )
    (project_root / "package-lock.json").write_text("{}\n", encoding="utf-8")
    (project_root / "README.md").write_text("outside watcher scope\n", encoding="utf-8")

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    tools = build_tool_registry(registry)

    watcher_before_index = tools.run("watcher_health", project_id="manifest-id")
    assert watcher_before_index["ok"] is True
    assert watcher_before_index["data"] == {
        "project_id": "manifest-id",
        "configured": True,
        "active": False,
        "watched_paths": ["src"],
        "status": "configured",
        "revision": None,
        "indexed_at": None,
        "file_count": 0,
        "symbol_count": 0,
    }

    indexed = tools.run("function_context", project_id="manifest-id", symbol="helper")
    assert indexed["ok"] is True

    started = tools.run("start_service", project_id="manifest-id", service_name="backend")
    assert started["ok"] is True

    deadline = time.monotonic() + 3
    logs = tools.run("get_logs", project_id="manifest-id", service_name="backend")
    while not logs["data"]["lines"] and time.monotonic() < deadline:
        time.sleep(0.05)
        logs = tools.run("get_logs", project_id="manifest-id", service_name="backend")

    try:
        result = tools.run("project_snapshot", project_id="manifest-id")

        assert result["ok"] is True
        assert result["warnings"] == []
        assert result["data"]["project"] == {
            "project_id": "manifest-id",
            "display_name": "Manifest Project",
            "aliases": ["manifest-id-alias"],
            "manifest_present": True,
        }
        assert "root_path" not in result["data"]["project"]
        assert "manifest_path" not in result["data"]["project"]
        assert "manifest" not in result["data"]["project"]
        assert "policy" not in result["data"]["project"]
        assert result["data"]["services"] == [
            {
                "name": "backend",
                "cwd": "backend",
                "ports": [8000],
                "has_health_check": False,
                "status": "running",
                "health_status": "healthy",
                "health_message": "Service process is running.",
                "start_command": [sys.executable, "-u", "service.py"],
            }
        ]
        assert result["data"]["stack"] == {
            "languages": ["Python", "TypeScript"],
            "frameworks": ["FastAPI", "React"],
            "package_managers": ["npm", "pip"],
        }
        assert result["data"]["watcher"]["watched_paths"] == ["src"]
        assert result["data"]["watcher"]["active"] is False
        assert result["data"]["watcher"]["status"] == "indexed"
        assert result["data"]["watcher"]["file_count"] == 1
        assert result["data"]["watcher"]["symbol_count"] == 3
        assert result["data"]["watcher"]["revision"]
        assert result["data"]["watcher"]["indexed_at"]
        assert result["data"]["probes"] == ["backend_db"]
        assert result["data"]["presets"] == ["test_backend"]
        assert result["data"]["policy"] == {
            "writable_roots": ["src", "tests", ".devworkspace"],
            "follow_symlinks_for_read": False,
            "follow_symlinks_for_write": False,
            "env_inherit": False,
            "env_allow": ["PATH", "HOME", "LANG", "LC_ALL", "APP_MODE"],
            "command_default": "deny",
            "configured_commands": sorted([Path(sys.executable).name, "pytest"]),
            "network_default": "deny",
            "allow_localhost": True,
            "allowed_hosts": ["example.com"],
        }
        assert result["data"]["agents_summary"] == [
            "Repo Rules",
            "Use pytest -q",
            "Keep patches small",
            "Workflow",
            "Prefer presets first",
        ]
        assert result["data"]["memory_summary"] == [
            "Context",
            "API runs locally",
            "No Docker in this repo",
        ]
        assert result["data"]["active_tasks"] == [
            "Finish boot packet",
            "Verify snapshot output",
        ]
        assert result["data"]["memory_index_status"] == "missing"
        assert result["data"]["recent_decision_titles"] == []
        assert result["data"]["standards_docs"] == []
        assert result["data"]["tracking_systems"] == ["GitHub Issues", "SQLite Memory Index"]
        assert result["data"]["recommended_commands"] == [
            "run_command preset=test_backend",
            "run_probe probe_name=backend_db",
            "start_service service_name=backend",
            "service_status service_name=backend",
        ]
        assert result["data"]["recommended_next_tools"] == [
            "read_state_doc",
            "memory_index_status",
            "reindex_workspace_memory",
            "run_command",
            "run_probe",
            "service_status",
            "watcher_health",
            "read_file",
            "grep",
        ]
        assert result["data"]["capabilities"] == {
            "code_navigation": (
                "Code navigation is available through module_overview, read_source, "
                "function_context, find_references, and call_path."
            ),
            "watcher": (
                "Watcher status is snapshot-backed only. It reports indexed watch_paths, "
                "but there is no real filesystem watcher backend yet."
            ),
            "services": (
                "Manifest-declared services can be listed, started, stopped, restarted, "
                "and inspected for runtime status plus basic health."
            ),
            "state_docs": (
                "Repo-local memory, roadmap, and tasks docs can be read and "
                "patched under .devworkspace/."
            ),
            "commands": (
                "Bounded commands support argv execution, presets, timeouts, "
                "and background jobs under project policy."
            ),
            "search": (
                "Text search is available via grep, codegraph symbol tools use an "
                "in-memory snapshot, and search_workspace_memory can query the local "
                "SQLite memory index when it has been indexed."
            ),
            "github": (
                "GitHub Issues remain the canonical work tracker, and read-only GitHub repo, "
                "issue, and PR lookups are available from the project's origin remote. "
                "Write helpers are still not implemented in this server."
            ),
        }

        agents_doc = next(doc for doc in result["data"]["state_docs"] if doc["kind"] == "agents")
        assert agents_doc["section_headings"] == ["Repo Rules", "Workflow"]
        assert agents_doc["preview_lines"] == [
            "# Repo Rules",
            "- Use pytest -q",
            "- Keep patches small",
            "# Workflow",
            "- Prefer presets first",
        ]

        memory_doc = next(doc for doc in result["data"]["state_docs"] if doc["kind"] == "memory")
        assert memory_doc["section_headings"] == ["Context"]
        assert memory_doc["preview_lines"] == [
            "# Context",
            "- API runs locally",
            "- No Docker in this repo",
        ]

        tasks_doc = next(doc for doc in result["data"]["state_docs"] if doc["kind"] == "tasks")
        assert tasks_doc["section_headings"] == ["Active", "Backlog"]
        assert tasks_doc["preview_lines"] == [
            "# Active",
            "- Finish boot packet",
            "- Verify snapshot output",
            "# Backlog",
            "- Later cleanup",
        ]
    finally:
        stopped = tools.run("stop_service", project_id="manifest-id", service_name="backend")
        assert stopped["ok"] is True



def test_watcher_health_only_reports_existing_index_state(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    src = project_root / "src"
    src.mkdir()
    (src / "sample.py").write_text(
        "def helper():\n"
        "    return 'ok'\n",
        encoding="utf-8",
    )

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    tools = build_tool_registry(registry)

    initial = tools.run("watcher_health", project_id="manifest-id")

    assert initial["ok"] is True
    assert initial["data"] == {
        "project_id": "manifest-id",
        "configured": True,
        "active": False,
        "watched_paths": ["src"],
        "status": "configured",
        "revision": None,
        "indexed_at": None,
        "file_count": 0,
        "symbol_count": 0,
    }

    context = tools.run("function_context", project_id="manifest-id", symbol="helper")

    assert context["ok"] is True

    indexed = tools.run("watcher_health", project_id="manifest-id")

    assert indexed["ok"] is True
    assert indexed["data"]["project_id"] == "manifest-id"
    assert indexed["data"]["configured"] is True
    assert indexed["data"]["active"] is False
    assert indexed["data"]["watched_paths"] == ["src"]
    assert indexed["data"]["status"] == "indexed"
    assert indexed["data"]["revision"]
    assert indexed["data"]["indexed_at"]
    assert indexed["data"]["file_count"] == 1
    assert indexed["data"]["symbol_count"] == 1



def test_project_snapshot_adds_compact_memory_hints(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    state_dir = project_root / ".devworkspace"
    standards_dir = project_root / "docs" / "standards"
    decisions_dir = project_root / "docs" / "decisions"
    state_dir.mkdir()
    standards_dir.mkdir(parents=True)
    decisions_dir.mkdir(parents=True)
    (project_root / "AGENTS.md").write_text(
        "# Repo Rules\n- Keep session summaries concise\n",
        encoding="utf-8",
    )
    (state_dir / "memory.md").write_text(
        "# Context\n- Prefer repo docs\n",
        encoding="utf-8",
    )
    (state_dir / "roadmap.md").write_text(
        "# Roadmap\n- Ship wave one\n",
        encoding="utf-8",
    )
    (standards_dir / "backend.md").write_text(
        "# Backend\nUse boring service seams.\n",
        encoding="utf-8",
    )
    (standards_dir / "frontend.md").write_text(
        "# Frontend\nPrefer explicit contracts.\n",
        encoding="utf-8",
    )
    (decisions_dir / "0001-source-of-truth.md").write_text(
        "# Source of truth\nGitHub is canonical.\n",
        encoding="utf-8",
    )

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    tools = build_tool_registry(registry)
    assert tools.run("reindex_workspace_memory", project_id="manifest-id")["ok"] is True
    assert (
        tools.run(
            "record_session_summary",
            project_id="manifest-id",
            source_platform="openclaw",
            source_session_ref="session-1",
            agent_name="Hermes",
            summary="Captured the final authority split.",
            decisions=[
                {
                    "title": "Keep GitHub canonical for tracking",
                    "status": "active",
                    "rationale": "SQLite remains a local recall layer.",
                    "doc_path": "docs/decisions/0001-source-of-truth.md",
                }
            ],
            source_refs=[
                {"kind": "doc", "value": "docs/decisions/0001-source-of-truth.md"},
            ],
        )["ok"]
        is True
    )

    snapshot = tools.run("project_snapshot", project_id="manifest-id")

    assert snapshot["ok"] is True
    assert snapshot["data"]["memory_index_status"] == "ready"
    assert snapshot["data"]["recent_decision_titles"] == [
        "Keep GitHub canonical for tracking",
        "Source of truth",
    ]
    assert snapshot["data"]["standards_docs"] == [
        "docs/standards/backend.md",
        "docs/standards/frontend.md",
    ]
    assert snapshot["data"]["tracking_systems"] == [
        "GitHub Issues",
        "Repo Decisions",
        "SQLite Memory Index",
    ]
    assert "search_workspace_memory" in snapshot["data"]["recommended_next_tools"]
    assert "reindex_workspace_memory" not in snapshot["data"]["recommended_next_tools"]


def test_project_snapshot_degrades_when_state_docs_or_watcher_health_fail(
    workspace_root,
    make_manifest_project,
    monkeypatch,
) -> None:
    project_root = make_manifest_project()
    (project_root / "AGENTS.md").write_bytes(b"\xff\xfe")
    state_dir = project_root / ".devworkspace"
    state_dir.mkdir()
    (state_dir / "memory.md").write_bytes(b"\xff\xfe")

    def _boom(self, project_id: str):
        raise RuntimeError(f"watcher refresh failed for {project_id}")

    monkeypatch.setattr(CodegraphService, "watcher_health", _boom)

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    tools = build_tool_registry(registry)

    result = tools.run("project_snapshot", project_id="manifest-id")

    assert result["ok"] is True
    warning_codes = {warning["code"] for warning in result["warnings"]}
    assert {"STATE_DOC_UNREADABLE", "WATCHER_STATUS_UNAVAILABLE"} <= warning_codes
    assert result["data"]["agents_summary"] == []
    assert result["data"]["memory_summary"] == []
    assert result["data"]["watcher"]["configured"] is True
    assert result["data"]["watcher"]["active"] is False
    assert result["data"]["watcher"]["status"] == "configured"

    agents_doc = next(doc for doc in result["data"]["state_docs"] if doc["kind"] == "agents")
    assert agents_doc["exists"] is True
    assert agents_doc["char_count"] == 0
    assert agents_doc["section_headings"] == []
    assert agents_doc["preview_lines"] == []
