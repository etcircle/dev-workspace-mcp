from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from dev_workspace_mcp.cli import main as cli_module
from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.tool_registry import build_tool_registry
from dev_workspace_mcp.projects.registry import ProjectRegistry


def _build_tools(workspace_root: Path):
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    return build_tool_registry(registry)


def _invoke_cli(
    monkeypatch,
    capsys,
    workspace_root: Path,
    argv: list[str],
) -> tuple[int, dict[str, object]]:
    settings = Settings(workspace_roots=[str(workspace_root)])
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    exit_code = cli_module.main(argv)
    output = capsys.readouterr().out
    return exit_code, json.loads(output)


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


def test_cli_memory_index_status_search_and_reindex_match_tool_registry(
    monkeypatch,
    capsys,
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    _seed_memory_docs(project_root)
    tools = _build_tools(workspace_root)

    expected_status = tools.run("memory_index_status", project_id="manifest-id")

    status_exit_code, status_payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        ["--json", "memory-index", "status", "manifest-id"],
    )
    reindex_exit_code, reindex_payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        ["--json", "memory-index", "reindex", "manifest-id"],
    )
    search_exit_code, search_payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        [
            "--json",
            "memory-index",
            "search",
            "manifest-id",
            "--query",
            "universal routing key",
            "--scope",
            "docs",
            "--limit",
            "5",
        ],
    )

    assert status_exit_code == 0
    assert status_payload == expected_status

    assert reindex_exit_code == 0
    assert reindex_payload["ok"] is True
    assert reindex_payload["data"]["documents_indexed"] == 5
    assert reindex_payload["data"]["index_status"]["status"] == "ready"

    assert search_exit_code == 0
    assert search_payload == tools.run(
        "search_workspace_memory",
        project_id="manifest-id",
        query="universal routing key",
        scope="docs",
        limit=5,
    )


def test_cli_memory_index_record_session_accepts_file_input(
    monkeypatch,
    capsys,
    workspace_root,
    make_manifest_project,
    tmp_path,
) -> None:
    project_root = make_manifest_project()
    _seed_memory_docs(project_root)
    tools = _build_tools(workspace_root)
    tools.run("reindex_workspace_memory", project_id="manifest-id")

    summary_payload = {
        "source_platform": "openclaw",
        "source_session_ref": "session-77",
        "source_thread_ref": "thread-11",
        "agent_name": "Hermes",
        "summary": "Retry replaced the partial summary with the final local recall artifact.",
        "outcome": "Final capture is complete.",
        "decisions": [
            {
                "title": "Promote stable guidance later",
                "status": "active",
                "rationale": "Only Git-tracked docs are durable authority.",
                "github_ref": "owner/repo#456",
                "doc_path": "docs/decisions/0001-source-of-truth.md",
            }
        ],
        "source_refs": [
            {"kind": "chat_thread", "value": "openclaw:thread-11"},
            {"kind": "doc", "value": "docs/decisions/0001-source-of-truth.md"},
        ],
    }
    input_path = tmp_path / "summary.json"
    input_path.write_text(json.dumps(summary_payload), encoding="utf-8")

    exit_code, payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        [
            "--json",
            "memory-index",
            "record-session",
            "manifest-id",
            "--input",
            str(input_path),
        ],
    )
    expected = tools.run(
        "record_session_summary",
        project_id="manifest-id",
        **summary_payload,
    )

    assert exit_code == 0
    assert payload == expected



def test_cli_memory_index_record_session_accepts_stdin_json(
    monkeypatch,
    capsys,
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    _seed_memory_docs(project_root)
    tools = _build_tools(workspace_root)
    tools.run("reindex_workspace_memory", project_id="manifest-id")

    summary_payload = {
        "source_platform": "openclaw",
        "source_session_ref": "session-88",
        "agent_name": "Hermes",
        "summary": "Captured a stdin-provided memory summary.",
        "source_refs": [
            {"kind": "doc", "value": "docs/decisions/0001-source-of-truth.md"},
        ],
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(summary_payload)))

    exit_code, payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        [
            "--json",
            "memory-index",
            "record-session",
            "manifest-id",
            "--input",
            "-",
        ],
    )
    expected = tools.run(
        "record_session_summary",
        project_id="manifest-id",
        **summary_payload,
    )

    assert exit_code == 0
    assert payload == expected



def test_cli_memory_index_record_session_rejects_project_id_mismatch(
    monkeypatch,
    capsys,
    workspace_root,
    make_manifest_project,
    tmp_path,
) -> None:
    project_root = make_manifest_project()
    _seed_memory_docs(project_root)

    input_path = tmp_path / "summary-mismatch.json"
    input_path.write_text(
        json.dumps(
            {
                "project_id": "other-project",
                "source_platform": "openclaw",
                "source_session_ref": "session-99",
                "agent_name": "Hermes",
                "summary": "Mismatched project id should fail.",
            }
        ),
        encoding="utf-8",
    )

    exit_code, payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        [
            "--json",
            "memory-index",
            "record-session",
            "manifest-id",
            "--input",
            str(input_path),
        ],
    )

    assert exit_code == 1
    assert payload == {
        "ok": False,
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Invalid CLI input.",
            "hint": "Check the JSON payload and CLI arguments.",
            "details": {
                "issues": [
                    {
                        "field": "__root__",
                        "message": (
                            "record-session input project_id does not match "
                            "the CLI project_id argument."
                        ),
                        "input_value": None,
                    }
                ]
            },
        },
    }



def test_cli_memory_index_record_session_rejects_invalid_json(
    monkeypatch,
    capsys,
    workspace_root,
    make_manifest_project,
    tmp_path,
) -> None:
    project_root = make_manifest_project()
    _seed_memory_docs(project_root)

    input_path = tmp_path / "broken-summary.json"
    input_path.write_text('{"source_platform": "openclaw",', encoding="utf-8")

    exit_code, payload = _invoke_cli(
        monkeypatch,
        capsys,
        workspace_root,
        [
            "--json",
            "memory-index",
            "record-session",
            "manifest-id",
            "--input",
            str(input_path),
        ],
    )

    assert exit_code == 1
    assert payload == {
        "ok": False,
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Invalid CLI input.",
            "hint": "Check the JSON payload and CLI arguments.",
            "details": {
                "issues": [
                    {
                        "field": "__root__",
                        "message": (
                            "Input must be valid JSON: Expecting property name enclosed "
                            "in double quotes"
                        ),
                        "input_value": None,
                    }
                ]
            },
        },
    }
