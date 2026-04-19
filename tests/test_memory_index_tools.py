from __future__ import annotations

from pathlib import Path

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.tool_registry import build_tool_registry
from dev_workspace_mcp.projects.registry import ProjectRegistry


def _build_tools(workspace_root: Path):
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    return build_tool_registry(registry)


def _seed_memory_docs(project_root: Path) -> None:
    state_dir = project_root / ".devworkspace"
    standards_dir = project_root / "docs" / "standards"
    decisions_dir = project_root / "docs" / "decisions"
    state_dir.mkdir(parents=True, exist_ok=True)
    standards_dir.mkdir(parents=True, exist_ok=True)
    decisions_dir.mkdir(parents=True, exist_ok=True)
    (project_root / "AGENTS.md").write_text(
        "# Agent Guide\n\nproject_id is the universal routing key.\n",
        encoding="utf-8",
    )
    (state_dir / "memory.md").write_text(
        "# Memory\n\nKeep continuity sharp for agents.\n",
        encoding="utf-8",
    )
    (state_dir / "roadmap.md").write_text(
        "# Roadmap\n\nWave one adds persistent workspace memory.\n",
        encoding="utf-8",
    )
    (decisions_dir / "0001-source-of-truth.md").write_text(
        "# Source of truth\n\nGitHub is canonical for backlog tracking.\n",
        encoding="utf-8",
    )
    (standards_dir / "backend.md").write_text(
        "# Backend\n\nKeep SQLite derived only and prefer explicit service seams.\n",
        encoding="utf-8",
    )


def test_memory_index_tools_reindex_search_and_status_flow(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    _seed_memory_docs(project_root)
    tools = _build_tools(workspace_root)

    status_before = tools.run("memory_index_status", project_id="manifest-id")
    search_before = tools.run(
        "search_workspace_memory",
        project_id="manifest-id",
        query="universal routing key",
        scope="docs",
        limit=5,
    )
    reindex = tools.run("reindex_workspace_memory", project_id="manifest-id")
    search_after = tools.run(
        "search_workspace_memory",
        project_id="manifest-id",
        query="universal routing key",
        scope="docs",
        limit=5,
    )

    assert status_before["ok"] is True
    assert status_before["data"]["status"] == "missing"
    assert status_before["warnings"] == []

    assert search_before["ok"] is True
    assert search_before["data"]["results"] == []
    assert search_before["data"]["index_status"]["status"] == "missing"

    assert reindex["ok"] is True
    assert reindex["warnings"] == []
    assert reindex["data"]["documents_indexed"] == 5
    assert reindex["data"]["documents_changed"] == 5
    assert reindex["data"]["documents_removed"] == 0
    assert reindex["data"]["index_status"]["status"] == "ready"

    assert search_after["ok"] is True
    assert search_after["warnings"] == []
    assert search_after["data"]["warnings"] == []
    assert search_after["data"]["index_status"]["status"] == "ready"
    assert any(
        result["source_path"] == "AGENTS.md"
        for result in search_after["data"]["results"]
    )
    assert any(
        result["source_ref"] == "doc:AGENTS.md"
        for result in search_after["data"]["results"]
    )


def test_record_session_summary_tool_keeps_searchable_provenance(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    _seed_memory_docs(project_root)
    tools = _build_tools(workspace_root)
    tools.run("reindex_workspace_memory", project_id="manifest-id")

    record = tools.run(
        "record_session_summary",
        project_id="manifest-id",
        source_platform="openclaw",
        source_session_ref="session-42",
        source_thread_ref="thread-7",
        agent_name="Hermes",
        summary=(
            "Implemented the session continuity path and indexed the sqlite memory foundation."
        ),
        outcome="Focused tests passed for workspace memory.",
        decisions=[
            {
                "title": "Keep SQLite derived only",
                "status": "active",
                "rationale": "Only Git-tracked docs are durable authority.",
                "tags": ["sqlite", "memory"],
                "github_ref": "owner/repo#123",
                "doc_path": "docs/decisions/0001-source-of-truth.md",
            }
        ],
        source_refs=[
            {"kind": "github_issue", "value": "owner/repo#123"},
            {"kind": "doc", "value": "docs/decisions/0001-source-of-truth.md"},
        ],
    )
    decision_search = tools.run(
        "search_workspace_memory",
        project_id="manifest-id",
        query="durable authority",
        scope="decisions",
        limit=5,
    )

    assert record["ok"] is True
    assert record["warnings"] == []
    assert record["data"]["project_id"] == "manifest-id"
    assert record["data"]["session_summary_id"] > 0
    assert record["data"]["decision_count"] == 1
    assert record["data"]["source_ref_count"] == 2

    assert decision_search["ok"] is True
    assert decision_search["data"]["index_status"]["decision_count"] == 1
    assert len(decision_search["data"]["results"]) == 1
    result = decision_search["data"]["results"][0]
    assert result["kind"] == "decision"
    assert result["title"] == "Keep SQLite derived only"
    assert "durable" in result["snippet"].lower() or "authority" in result["snippet"].lower()
    assert result["source_path"] == "docs/decisions/0001-source-of-truth.md"
    assert result["source_ref"] == "github_issue:owner/repo#123"
    assert result["source_refs"] == [
        {"kind": "github_issue", "value": "owner/repo#123"},
        {"kind": "doc", "value": "docs/decisions/0001-source-of-truth.md"},
    ]
    assert result["score"] >= 0



def test_record_session_summary_tool_maps_noncanonical_doc_refs_to_validation_errors(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    _seed_memory_docs(project_root)
    tools = _build_tools(workspace_root)
    tools.run("reindex_workspace_memory", project_id="manifest-id")

    invalid = tools.run(
        "record_session_summary",
        project_id="manifest-id",
        source_platform="openclaw",
        source_session_ref="session-99",
        agent_name="Hermes",
        summary="Tried to cite a loose notes file.",
        decisions=[
            {
                "title": "Do not cite loose notes",
                "status": "rejected",
                "rationale": "Only canonical docs should be referenced.",
                "doc_path": "notes.md",
            }
        ],
    )

    assert invalid["ok"] is False
    assert invalid["error"]["code"] == "VALIDATION_ERROR"
    assert invalid["error"]["details"] == {
        "issues": [
            {
                "field": "__root__",
                "message": (
                    "Decision doc_path must point to a canonical document in this project: notes.md"
                ),
                "input_value": None,
            }
        ]
    }


def test_record_session_summary_tool_rejects_nested_extra_fields(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    _seed_memory_docs(project_root)
    tools = _build_tools(workspace_root)
    tools.run("reindex_workspace_memory", project_id="manifest-id")

    invalid = tools.run(
        "record_session_summary",
        project_id="manifest-id",
        source_platform="openclaw",
        source_session_ref="session-extra",
        agent_name="Hermes",
        summary="Tried to send an extra nested field.",
        decisions=[
            {
                "title": "Reject nested junk",
                "status": "rejected",
                "rationale": "Public payloads should fail closed.",
                "bogus": "x",
            }
        ],
    )

    assert invalid["ok"] is False
    assert invalid["error"]["code"] == "VALIDATION_ERROR"
    assert invalid["error"]["details"]["issues"] == [
        {
            "field": "decisions.0.bogus",
            "message": "Extra inputs are not permitted",
            "input_value": None,
        }
    ]



def test_memory_index_tools_report_unreadable_canonical_docs_as_validation_errors(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    _seed_memory_docs(project_root)
    tools = _build_tools(workspace_root)
    assert tools.run("reindex_workspace_memory", project_id="manifest-id")["ok"] is True

    (project_root / "AGENTS.md").write_bytes(b"\xff\xfe\x80not-utf8")

    status_result = tools.run("memory_index_status", project_id="manifest-id")
    reindex_result = tools.run("reindex_workspace_memory", project_id="manifest-id")
    search_result = tools.run(
        "search_workspace_memory",
        project_id="manifest-id",
        query="routing key",
        scope="docs",
        limit=5,
    )

    for payload in (status_result, reindex_result, search_result):
        assert payload["ok"] is False
        assert payload["error"]["code"] == "VALIDATION_ERROR"
        assert payload["error"]["details"]["issues"] == [
            {
                "field": "__root__",
                "message": "Canonical document is not readable as UTF-8: AGENTS.md",
                "input_value": None,
            }
        ]
