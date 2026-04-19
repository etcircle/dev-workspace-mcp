from __future__ import annotations

import subprocess
from pathlib import Path

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.tool_registry import build_tool_registry
from dev_workspace_mcp.projects.registry import ProjectRegistry
from dev_workspace_mcp.runtime import create_runtime_services

SAMPLE_SOURCE = '''import os
from pathlib import Path


class Greeter:
    def greet(self, name: str) -> str:
        return helper(name)


def helper(name: str) -> str:
    return f"Hello {name}"


def use_helper() -> str:
    return helper("world")
'''


def _build_tools(workspace_root: Path):
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    return build_tool_registry(registry)


def _init_git(project_root: Path) -> None:
    subprocess.run(["git", "-C", str(project_root), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(project_root), "config", "user.name", "Test User"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(project_root), "config", "user.email", "test@example.com"],
        check=True,
    )



def test_module_overview_and_function_context(workspace_root, make_manifest_project) -> None:
    project_root = make_manifest_project()
    src = project_root / "src"
    src.mkdir()
    (src / "sample.py").write_text(SAMPLE_SOURCE, encoding="utf-8")
    tools = _build_tools(workspace_root)

    overview = tools.run("module_overview", project_id="manifest-id", path="src/sample.py")
    assert overview["ok"] is True
    assert overview["data"]["path"] == "src/sample.py"
    assert overview["data"]["language"] == "python"
    assert overview["data"]["imports"] == ["os", "pathlib.Path"]
    assert overview["data"]["classes"][0]["name"] == "Greeter"
    assert overview["data"]["classes"][0]["methods"] == ["greet"]
    assert [item["name"] for item in overview["data"]["functions"]] == ["helper", "use_helper"]

    context = tools.run("function_context", project_id="manifest-id", symbol="helper")
    assert context["ok"] is True
    match = context["data"]["matches"][0]
    assert match["path"] == "src/sample.py"
    assert match["kind"] == "function"
    assert "def helper(name: str) -> str:" in match["source"]
    assert match["line_start"] < match["line_end"]



def test_grep_find_references_and_read_source(workspace_root, make_manifest_project) -> None:
    project_root = make_manifest_project()
    src = project_root / "src"
    src.mkdir()
    (src / "sample.py").write_text(SAMPLE_SOURCE, encoding="utf-8")
    tools = _build_tools(workspace_root)

    grep_result = tools.run("grep", project_id="manifest-id", pattern="helper")
    assert grep_result["ok"] is True
    assert len(grep_result["data"]["matches"]) >= 3
    assert all(match["path"] == "src/sample.py" for match in grep_result["data"]["matches"])

    references = tools.run("find_references", project_id="manifest-id", symbol="helper")
    assert references["ok"] is True
    assert any(
        "return helper(name)" in match["line_text"]
        for match in references["data"]["matches"]
    )

    source = tools.run(
        "read_source",
        project_id="manifest-id",
        path="src/sample.py",
        start_line=10,
        end_line=12,
    )
    assert source["ok"] is True
    assert source["data"]["path"] == "src/sample.py"
    assert source["data"]["start_line"] == 10
    assert "def helper(name: str) -> str:" in source["data"]["content"]



def test_call_path_shows_callers_and_callees(workspace_root, make_manifest_project) -> None:
    project_root = make_manifest_project()
    src = project_root / "src"
    src.mkdir()
    (src / "sample.py").write_text(SAMPLE_SOURCE, encoding="utf-8")
    tools = _build_tools(workspace_root)

    result = tools.run("call_path", project_id="manifest-id", symbol="helper")

    assert result["ok"] is True
    data = result["data"]
    assert data["symbol"] == "helper"
    assert data["definition"]["path"] == "src/sample.py"
    assert sorted(item["symbol"] for item in data["incoming"]) == ["greet", "use_helper"]
    assert data["outgoing"] == []



def test_recent_changes_and_watcher_health(workspace_root, make_manifest_project) -> None:
    project_root = make_manifest_project()
    src = project_root / "src"
    src.mkdir()
    sample = src / "sample.py"
    sample.write_text(SAMPLE_SOURCE, encoding="utf-8")
    (project_root / "README.md").write_text("outside watched paths\n", encoding="utf-8")
    _init_git(project_root)
    subprocess.run(["git", "-C", str(project_root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(project_root), "commit", "-m", "initial"], check=True)
    sample.write_text(SAMPLE_SOURCE + "\n# changed\n", encoding="utf-8")

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    runtime_services = create_runtime_services(registry)
    tools = build_tool_registry(registry, services=runtime_services)

    recent = tools.run("recent_changes", project_id="manifest-id", path="src/sample.py")
    assert recent["ok"] is True
    assert "diff --git a/src/sample.py b/src/sample.py" in recent["data"]["diff"]
    assert "+# changed" in recent["data"]["diff"]

    watcher_manager = runtime_services.codegraph_service.watcher_manager
    state_before = watcher_manager.get_state("manifest-id").model_dump(mode="json")
    assert state_before == {
        "project_id": "manifest-id",
        "active": False,
        "status": "not_configured",
        "watched_paths": [],
        "revision": None,
        "indexed_at": None,
        "file_count": 0,
        "symbol_count": 0,
    }

    watcher = tools.run("watcher_health", project_id="manifest-id")
    assert watcher["ok"] is True
    assert watcher["data"]["project_id"] == "manifest-id"
    assert watcher["data"]["configured"] is True
    assert watcher["data"]["active"] is False
    assert watcher["data"]["watched_paths"] == ["src"]
    assert watcher["data"]["status"] == "configured"
    assert watcher["data"]["file_count"] == 0
    assert watcher["data"]["symbol_count"] == 0
    assert watcher["data"]["revision"] is None
    assert watcher["data"]["indexed_at"] is None
    assert watcher_manager.get_state("manifest-id").model_dump(mode="json") == state_before

    context = tools.run("function_context", project_id="manifest-id", symbol="helper")
    assert context["ok"] is True

    indexed = tools.run("watcher_health", project_id="manifest-id")
    assert indexed["ok"] is True
    assert indexed["data"]["project_id"] == "manifest-id"
    assert indexed["data"]["configured"] is True
    assert indexed["data"]["active"] is False
    assert indexed["data"]["watched_paths"] == ["src"]
    assert indexed["data"]["status"] == "indexed"
    assert indexed["data"]["file_count"] == 1
    assert indexed["data"]["symbol_count"] == 4
    assert indexed["data"]["revision"]
    assert indexed["data"]["indexed_at"]

    sample.write_text(SAMPLE_SOURCE + "\n# changed again\n", encoding="utf-8")

    stale = tools.run("watcher_health", project_id="manifest-id")
    assert stale["ok"] is True
    assert stale["data"] == {
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
