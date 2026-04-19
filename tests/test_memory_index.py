from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.memory_index.service import MemoryIndexService
from dev_workspace_mcp.models.memory_index import (
    DecisionRecord,
    RecordSessionSummaryRequest,
    ReindexWorkspaceMemoryRequest,
    SearchWorkspaceMemoryRequest,
    SourceRef,
)


def _make_project(project_root: Path) -> None:
    (project_root / ".devworkspace").mkdir(parents=True)
    (project_root / "docs" / "decisions").mkdir(parents=True)
    (project_root / "docs" / "standards").mkdir(parents=True)
    (project_root / "AGENTS.md").write_text(
        "# Agent Guide\n\nproject_id is the universal routing key.\n",
        encoding="utf-8",
    )
    (project_root / ".devworkspace" / "memory.md").write_text(
        "# Memory\n\nKeep continuity sharp for agents.\n",
        encoding="utf-8",
    )
    (project_root / ".devworkspace" / "roadmap.md").write_text(
        "# Roadmap\n\nWave one adds persistent workspace memory.\n",
        encoding="utf-8",
    )
    (project_root / "docs" / "decisions" / "0001-source-of-truth.md").write_text(
        "# Source of truth\n\nGitHub is canonical for backlog tracking.\n",
        encoding="utf-8",
    )
    (project_root / "docs" / "standards" / "backend.md").write_text(
        "# Backend\n\nKeep SQLite derived only and prefer explicit service seams.\n",
        encoding="utf-8",
    )
    (project_root / "notes.md").write_text(
        "this should never be indexed into workspace memory\n",
        encoding="utf-8",
    )


def _make_service(tmp_path: Path) -> tuple[Path, MemoryIndexService]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _make_project(project_root)
    settings = Settings(workspace_roots=[str(tmp_path)])
    return project_root, MemoryIndexService(
        project_root=project_root,
        project_id="demo-project",
        settings=settings,
    )


def _fetch_document_indexed_at(db_path: Path, path: str) -> str | None:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT indexed_at FROM documents WHERE path = ?",
            (path,),
        ).fetchone()
    return None if row is None else str(row[0])


def _insert_session_summary_row(
    db_path: Path,
    *,
    project_id: str,
    source_platform: str,
    source_session_ref: str,
) -> None:
    with sqlite3.connect(db_path) as connection, connection:
        connection.execute(
            """
            INSERT INTO session_summaries (
                project_id,
                source_platform,
                source_session_ref,
                source_thread_ref,
                agent_name,
                started_at,
                ended_at,
                summary,
                outcome,
                source_refs_text,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                source_platform,
                source_session_ref,
                None,
                "Hermes",
                None,
                None,
                "Captured a session.",
                None,
                "",
                datetime(2026, 4, 19, 10, 0, tzinfo=UTC).isoformat(),
            ),
        )


def test_memory_index_models_enforce_contract() -> None:
    assert SourceRef(kind="commit", value="A" * 40).value == "a" * 40
    assert (
        DecisionRecord(
            title="Keep SQLite derived only",
            status="active",
            rationale="GitHub remains canonical.",
            github_ref="owner/repo#123",
        ).github_ref
        == "owner/repo#123"
    )

    with pytest.raises(ValidationError, match="source_platform"):
        RecordSessionSummaryRequest(
            project_id="demo-project",
            source_platform="OpenClaw",
            source_session_ref="session-1",
            agent_name="Hermes",
            summary="Kept working.",
        )

    with pytest.raises(ValidationError, match="compact owner/repo#123"):
        SourceRef(kind="github_issue", value="owner/repo/issues/123")

    with pytest.raises(ValidationError, match="compact owner/repo#123"):
        DecisionRecord(
            title="Keep SQLite derived only",
            status="active",
            rationale="GitHub remains canonical.",
            github_ref="https://github.com/owner/repo/pull/123",
        )

    with pytest.raises(ValidationError, match="40-character SHAs"):
        SourceRef(kind="commit", value="abc123")

    with pytest.raises(ValidationError, match="simple nonblank tokens"):
        SourceRef(kind="chat_thread", value="thread 7")

    with pytest.raises(ValidationError, match="must not be blank"):
        SourceRef(kind="doc", value="   ")

    with pytest.raises(ValidationError, match="must not be"):
        SourceRef(kind="doc", value=".")

    with pytest.raises(ValidationError, match="doc_path"):
        DecisionRecord(
            title="Keep SQLite derived only",
            status="active",
            rationale="GitHub remains canonical.",
            doc_path="../outside.md",
        )

    with pytest.raises(ValidationError, match="relative to the project root"):
        SourceRef(kind="doc", value="/tmp/outside.md")


def test_memory_index_reports_missing_before_initialization(tmp_path: Path) -> None:
    _, service = _make_service(tmp_path)

    status = service.get_status()

    assert status.status == "missing"
    assert status.documents_indexed == 0
    assert status.session_summary_count == 0
    assert "not been initialized" in status.warnings[0]
    assert not service.db_path.exists()


def test_reindex_indexes_only_canonical_docs_and_tracks_staleness(tmp_path: Path) -> None:
    project_root, service = _make_service(tmp_path)

    first = service.reindex(
        ReindexWorkspaceMemoryRequest(project_id="demo-project", reason="initial-bootstrap")
    )

    assert service.db_path.exists()
    assert first.documents_indexed == 5
    assert first.documents_changed == 5
    assert first.documents_removed == 0
    assert first.index_status.status == "ready"

    doc_search = service.search(
        SearchWorkspaceMemoryRequest(
            project_id="demo-project",
            query="universal routing key",
            scope="docs",
            limit=5,
        )
    )
    assert doc_search.index_status.status == "ready"
    assert any(result.source_path == "AGENTS.md" for result in doc_search.results)
    assert any(result.source_ref == "doc:AGENTS.md" for result in doc_search.results)

    ignored_search = service.search(
        SearchWorkspaceMemoryRequest(
            project_id="demo-project",
            query="never indexed",
            scope="docs",
            limit=5,
        )
    )
    assert ignored_search.results == []

    first_indexed_at = _fetch_document_indexed_at(service.db_path, "AGENTS.md")
    second = service.reindex(
        ReindexWorkspaceMemoryRequest(project_id="demo-project", reason="repeat")
    )
    second_indexed_at = _fetch_document_indexed_at(service.db_path, "AGENTS.md")
    assert second.documents_changed == 0
    assert second.documents_removed == 0
    assert second_indexed_at == first_indexed_at

    (project_root / "docs" / "standards" / "backend.md").write_text(
        "# Backend\n\nKeep SQLite derived only, expose honest stale signals, "
        "and avoid hidden state.\n",
        encoding="utf-8",
    )
    stale = service.get_status()
    assert stale.status == "stale"
    assert any("backend.md" in warning for warning in stale.warnings)


def test_session_summary_ingestion_is_searchable_and_preserves_provenance(tmp_path: Path) -> None:
    _, service = _make_service(tmp_path)
    service.reindex(ReindexWorkspaceMemoryRequest(project_id="demo-project", reason="initial"))

    request = RecordSessionSummaryRequest(
        project_id="demo-project",
        source_platform="openclaw",
        source_session_ref="session-42",
        source_thread_ref="thread-7",
        agent_name="Hermes",
        started_at=datetime(2026, 4, 19, 9, 0, tzinfo=UTC),
        ended_at=datetime(2026, 4, 19, 10, 0, tzinfo=UTC),
        summary="Implemented the session continuity path and indexed the sqlite memory foundation.",
        outcome="Focused tests passed for workspace memory.",
        decisions=[
            DecisionRecord(
                title="Keep SQLite derived only",
                status="active",
                rationale="GitHub remains canonical while SQLite stays search-only.",
                tags=["sqlite", "memory", "sqlite"],
                github_ref="owner/repo#123",
                doc_path="docs/decisions/0001-source-of-truth.md",
            )
        ],
        source_refs=[
            SourceRef(kind="github_issue", value="owner/repo#123"),
            SourceRef(kind="doc", value="docs/decisions/0001-source-of-truth.md"),
        ],
    )

    response = service.record_session_summary(request)

    assert response.session_summary_id > 0
    assert response.decision_count == 1
    assert response.source_ref_count == 2

    session_search = service.search(
        SearchWorkspaceMemoryRequest(
            project_id="demo-project",
            query="session continuity sqlite foundation",
            scope="sessions",
            limit=5,
        )
    )
    assert len(session_search.results) == 1
    assert session_search.results[0].kind == "session"
    assert session_search.results[0].source_ref == "github_issue:owner/repo#123"
    assert any(ref.value == "owner/repo#123" for ref in session_search.results[0].source_refs)

    decision_search = service.search(
        SearchWorkspaceMemoryRequest(
            project_id="demo-project",
            query="search only canonical",
            scope="decisions",
            limit=5,
        )
    )
    assert len(decision_search.results) == 1
    decision_result = decision_search.results[0]
    assert decision_result.kind == "decision"
    assert decision_result.source_ref == "github_issue:owner/repo#123"
    assert decision_result.source_path == "docs/decisions/0001-source-of-truth.md"
    assert decision_result.source_refs == [
        SourceRef(kind="github_issue", value="owner/repo#123"),
        SourceRef(kind="doc", value="docs/decisions/0001-source-of-truth.md"),
    ]

    status = service.get_status()
    assert status.status == "ready"
    assert status.session_summary_count == 1
    assert status.decision_count == 1

    with sqlite3.connect(service.db_path) as connection:
        source_ref_count = connection.execute("SELECT COUNT(*) FROM source_refs").fetchone()[0]
        decision_count = connection.execute("SELECT COUNT(*) FROM session_decisions").fetchone()[0]
    assert source_ref_count == 2
    assert decision_count == 1


def test_record_session_summary_reuses_natural_key_on_retry(tmp_path: Path) -> None:
    _, service = _make_service(tmp_path)
    service.reindex(ReindexWorkspaceMemoryRequest(project_id="demo-project", reason="initial"))

    first_request = RecordSessionSummaryRequest(
        project_id="demo-project",
        source_platform="openclaw",
        source_session_ref="session-77",
        source_thread_ref="thread-11",
        agent_name="Hermes",
        summary="First pass captured partial workspace memory notes.",
        outcome="Partial capture only.",
        decisions=[
            DecisionRecord(
                title="Promote stable guidance later",
                status="proposed",
                rationale="The first pass only captured local recall.",
            )
        ],
        source_refs=[SourceRef(kind="chat_thread", value="openclaw:thread-11")],
    )
    retry_request = RecordSessionSummaryRequest(
        project_id="demo-project",
        source_platform="openclaw",
        source_session_ref="session-77",
        source_thread_ref="thread-11",
        agent_name="Hermes",
        summary="Retry replaced the partial summary with the final local recall artifact.",
        outcome="Final capture is complete.",
        decisions=[
            DecisionRecord(
                title="Promote stable guidance later",
                status="active",
                rationale="Only Git-tracked docs are durable authority.",
                github_ref="owner/repo#456",
                doc_path="docs/decisions/0001-source-of-truth.md",
            )
        ],
        source_refs=[
            SourceRef(kind="chat_thread", value="openclaw:thread-11"),
            SourceRef(kind="doc", value="docs/decisions/0001-source-of-truth.md"),
        ],
    )

    first_response = service.record_session_summary(first_request)
    retry_response = service.record_session_summary(retry_request)

    assert retry_response.session_summary_id == first_response.session_summary_id
    assert retry_response.decision_count == 1
    assert retry_response.source_ref_count == 2

    session_search = service.search(
        SearchWorkspaceMemoryRequest(
            project_id="demo-project",
            query="final local recall artifact",
            scope="sessions",
            limit=5,
        )
    )
    assert len(session_search.results) == 1
    assert session_search.results[0].source_ref == "chat_thread:openclaw:thread-11"

    old_session_search = service.search(
        SearchWorkspaceMemoryRequest(
            project_id="demo-project",
            query="partial workspace memory notes",
            scope="sessions",
            limit=5,
        )
    )
    assert old_session_search.results == []

    decision_search = service.search(
        SearchWorkspaceMemoryRequest(
            project_id="demo-project",
            query="durable authority",
            scope="decisions",
            limit=5,
        )
    )
    assert len(decision_search.results) == 1
    assert decision_search.results[0].source_ref == "github:owner/repo#456"
    assert decision_search.results[0].source_refs == [
        SourceRef(kind="github", value="owner/repo#456"),
        SourceRef(kind="doc", value="docs/decisions/0001-source-of-truth.md"),
        SourceRef(kind="chat_thread", value="openclaw:thread-11"),
    ]

    with sqlite3.connect(service.db_path) as connection:
        session_count = connection.execute(
            "SELECT COUNT(*) FROM session_summaries WHERE project_id = ?",
            ("demo-project",),
        ).fetchone()[0]
        source_ref_count = connection.execute("SELECT COUNT(*) FROM source_refs").fetchone()[0]
        decision_count = connection.execute("SELECT COUNT(*) FROM session_decisions").fetchone()[0]
    assert session_count == 1
    assert source_ref_count == 2
    assert decision_count == 1


def test_session_summary_identity_is_db_unique(tmp_path: Path) -> None:
    _, service = _make_service(tmp_path)
    service.store.initialize()

    _insert_session_summary_row(
        service.db_path,
        project_id="demo-project",
        source_platform="openclaw",
        source_session_ref="session-88",
    )

    with pytest.raises(sqlite3.IntegrityError):
        _insert_session_summary_row(
            service.db_path,
            project_id="demo-project",
            source_platform="openclaw",
            source_session_ref="session-88",
        )


def test_record_session_summary_rejects_noncanonical_doc_refs(tmp_path: Path) -> None:
    _, service = _make_service(tmp_path)
    service.reindex(ReindexWorkspaceMemoryRequest(project_id="demo-project", reason="initial"))

    with pytest.raises(ValueError, match="Decision doc_path must point to a canonical document"):
        service.record_session_summary(
            RecordSessionSummaryRequest(
                project_id="demo-project",
                source_platform="openclaw",
                source_session_ref="session-91",
                agent_name="Hermes",
                summary="Tried to store a non-canonical decision doc.",
                decisions=[
                    DecisionRecord(
                        title="Do not cite loose notes",
                        status="rejected",
                        rationale="Only canonical docs should be referenced.",
                        doc_path="notes.md",
                    )
                ],
            )
        )

    with pytest.raises(
        ValueError,
        match=r"SourceRef\(kind='doc'\) must point to a canonical document",
    ):
        service.record_session_summary(
            RecordSessionSummaryRequest(
                project_id="demo-project",
                source_platform="openclaw",
                source_session_ref="session-92",
                agent_name="Hermes",
                summary="Tried to store a missing canonical-ish doc ref.",
                source_refs=[SourceRef(kind="doc", value="docs/decisions/missing.md")],
            )
        )


def test_record_session_summary_rejects_inverted_timestamps() -> None:
    with pytest.raises(ValidationError, match="ended_at"):
        RecordSessionSummaryRequest(
            project_id="demo-project",
            source_platform="openclaw",
            source_session_ref="session-9",
            agent_name="Hermes",
            started_at=datetime(2026, 4, 19, 11, 0, tzinfo=UTC),
            ended_at=datetime(2026, 4, 19, 10, 59, tzinfo=UTC) - timedelta(seconds=1),
            summary="bad timestamps",
        )
