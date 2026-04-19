from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dev_workspace_mcp.memory_index.indexer import IndexedDocument
from dev_workspace_mcp.models.memory_index import (
    RecordSessionSummaryRequest,
    SourceRef,
)

_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL,
    path TEXT NOT NULL,
    kind TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    UNIQUE(project_id, path)
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    kind TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    heading TEXT,
    content TEXT NOT NULL,
    UNIQUE(document_id, chunk_index)
);

CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
    project_id UNINDEXED,
    path UNINDEXED,
    kind UNINDEXED,
    heading,
    content
);

CREATE TABLE IF NOT EXISTS session_summaries (
    id INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL,
    source_platform TEXT NOT NULL,
    source_session_ref TEXT NOT NULL,
    source_thread_ref TEXT,
    agent_name TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    summary TEXT NOT NULL,
    outcome TEXT,
    source_refs_text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS session_summaries_identity_idx
ON session_summaries(project_id, source_platform, source_session_ref);

CREATE VIRTUAL TABLE IF NOT EXISTS session_summaries_fts USING fts5(
    project_id UNINDEXED,
    session_summary_id UNINDEXED,
    source_platform,
    source_session_ref,
    source_thread_ref,
    agent_name,
    summary,
    outcome,
    source_refs_text
);

CREATE TABLE IF NOT EXISTS source_refs (
    id INTEGER PRIMARY KEY,
    session_summary_id INTEGER NOT NULL REFERENCES session_summaries(id) ON DELETE CASCADE,
    ref_kind TEXT NOT NULL,
    ref_value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_decisions (
    id INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL,
    session_summary_id INTEGER NOT NULL REFERENCES session_summaries(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    rationale TEXT NOT NULL,
    tags_json TEXT NOT NULL DEFAULT '[]',
    tags_text TEXT NOT NULL DEFAULT '',
    github_ref TEXT,
    doc_path TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS session_decisions_fts USING fts5(
    project_id UNINDEXED,
    decision_id UNINDEXED,
    session_summary_id UNINDEXED,
    title,
    status,
    rationale,
    tags_text,
    github_ref,
    doc_path
);

CREATE TABLE IF NOT EXISTS index_status (
    project_id TEXT PRIMARY KEY,
    last_indexed_at TEXT,
    last_index_reason TEXT,
    status TEXT NOT NULL,
    warning TEXT
);
"""


@dataclass(frozen=True)
class StoredDocument:
    id: int
    path: str
    kind: str
    content_hash: str
    indexed_at: datetime | None


class SQLiteMemoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def exists(self) -> bool:
        return self.db_path.exists()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
            self._ensure_session_summary_identity_uniqueness(connection)

    def _ensure_session_summary_identity_uniqueness(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        duplicate_rows = connection.execute(
            """
            SELECT GROUP_CONCAT(id) AS duplicate_ids
            FROM session_summaries
            GROUP BY project_id, source_platform, source_session_ref
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        for row in duplicate_rows:
            duplicate_ids = [
                int(value)
                for value in str(row["duplicate_ids"] or "").split(",")
                if value
            ]
            self._delete_session_summary_rows(connection, duplicate_ids[1:])
        connection.execute("DROP INDEX IF EXISTS session_summaries_identity_idx")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS session_summaries_identity_idx
            ON session_summaries(project_id, source_platform, source_session_ref)
            """
        )

    def get_documents(self, project_id: str) -> dict[str, StoredDocument]:
        if not self.exists():
            return {}
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, path, kind, content_hash, indexed_at
                FROM documents
                WHERE project_id = ?
                ORDER BY path
                """,
                (project_id,),
            ).fetchall()
        return {
            row["path"]: StoredDocument(
                id=row["id"],
                path=row["path"],
                kind=row["kind"],
                content_hash=row["content_hash"],
                indexed_at=_parse_optional_datetime(row["indexed_at"]),
            )
            for row in rows
        }

    def replace_document(
        self,
        project_id: str,
        document: IndexedDocument,
        *,
        indexed_at: datetime,
    ) -> bool:
        self.initialize()
        with self._connect() as connection, connection:
            existing = connection.execute(
                "SELECT id, content_hash FROM documents WHERE project_id = ? AND path = ?",
                (project_id, document.path),
            ).fetchone()
            if existing is not None and existing["content_hash"] == document.content_hash:
                return False

            if existing is not None:
                connection.execute(
                    "DELETE FROM document_chunks_fts WHERE project_id = ? AND path = ?",
                    (project_id, document.path),
                )
                connection.execute("DELETE FROM documents WHERE id = ?", (existing["id"],))

            cursor = connection.execute(
                """
                INSERT INTO documents (project_id, path, kind, content_hash, indexed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    document.path,
                    document.kind,
                    document.content_hash,
                    indexed_at.isoformat(),
                ),
            )
            document_id = int(cursor.lastrowid)
            for chunk in document.chunks:
                chunk_cursor = connection.execute(
                    """
                    INSERT INTO document_chunks (
                        project_id,
                        document_id,
                        path,
                        kind,
                        chunk_index,
                        heading,
                        content
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        document_id,
                        document.path,
                        document.kind,
                        chunk.chunk_index,
                        chunk.heading,
                        chunk.content,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO document_chunks_fts (
                        rowid,
                        project_id,
                        path,
                        kind,
                        heading,
                        content
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(chunk_cursor.lastrowid),
                        project_id,
                        document.path,
                        document.kind,
                        chunk.heading or "",
                        chunk.content,
                    ),
                )
        return True

    def delete_documents(self, project_id: str, paths: list[str]) -> int:
        if not paths or not self.exists():
            return 0
        removed = 0
        with self._connect() as connection, connection:
            for path in paths:
                connection.execute(
                    "DELETE FROM document_chunks_fts WHERE project_id = ? AND path = ?",
                    (project_id, path),
                )
                cursor = connection.execute(
                    "DELETE FROM documents WHERE project_id = ? AND path = ?",
                    (project_id, path),
                )
                removed += cursor.rowcount
        return removed

    def set_index_status(
        self,
        project_id: str,
        *,
        last_indexed_at: datetime | None,
        last_index_reason: str,
        status: str,
        warning: str | None,
    ) -> None:
        self.initialize()
        with self._connect() as connection, connection:
            connection.execute(
                """
                INSERT INTO index_status (
                    project_id,
                    last_indexed_at,
                    last_index_reason,
                    status,
                    warning
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    last_indexed_at = excluded.last_indexed_at,
                    last_index_reason = excluded.last_index_reason,
                    status = excluded.status,
                    warning = excluded.warning
                """,
                (
                    project_id,
                    None if last_indexed_at is None else last_indexed_at.isoformat(),
                    last_index_reason,
                    status,
                    warning,
                ),
            )

    def get_index_status_row(self, project_id: str) -> dict[str, Any] | None:
        if not self.exists():
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT project_id, last_indexed_at, last_index_reason, status, warning
                FROM index_status
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def get_counts(self, project_id: str) -> dict[str, int]:
        if not self.exists():
            return {
                "documents_indexed": 0,
                "document_chunk_count": 0,
                "session_summary_count": 0,
                "decision_count": 0,
            }
        with self._connect() as connection:
            documents_indexed = _fetch_scalar(
                connection,
                "SELECT COUNT(*) FROM documents WHERE project_id = ?",
                (project_id,),
            )
            document_chunk_count = _fetch_scalar(
                connection,
                "SELECT COUNT(*) FROM document_chunks WHERE project_id = ?",
                (project_id,),
            )
            session_summary_count = _fetch_scalar(
                connection,
                "SELECT COUNT(*) FROM session_summaries WHERE project_id = ?",
                (project_id,),
            )
            decision_count = _fetch_scalar(
                connection,
                "SELECT COUNT(*) FROM session_decisions WHERE project_id = ?",
                (project_id,),
            )
        return {
            "documents_indexed": documents_indexed,
            "document_chunk_count": document_chunk_count,
            "session_summary_count": session_summary_count,
            "decision_count": decision_count,
        }

    def insert_session_summary(
        self,
        project_id: str,
        request: RecordSessionSummaryRequest,
        *,
        created_at: datetime,
    ) -> int:
        self.initialize()
        source_refs_text = " ".join(ref.encoded() for ref in request.source_refs)
        with self._connect() as connection, connection:
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
                ON CONFLICT(project_id, source_platform, source_session_ref) DO UPDATE SET
                    source_thread_ref = excluded.source_thread_ref,
                    agent_name = excluded.agent_name,
                    started_at = excluded.started_at,
                    ended_at = excluded.ended_at,
                    summary = excluded.summary,
                    outcome = excluded.outcome,
                    source_refs_text = excluded.source_refs_text
                """,
                (
                    project_id,
                    request.source_platform,
                    request.source_session_ref,
                    request.source_thread_ref,
                    request.agent_name,
                    _serialize_optional_datetime(request.started_at),
                    _serialize_optional_datetime(request.ended_at),
                    request.summary,
                    request.outcome,
                    source_refs_text,
                    created_at.isoformat(),
                ),
            )
            session_id = self._get_session_summary_id(
                connection,
                project_id=project_id,
                source_platform=request.source_platform,
                source_session_ref=request.source_session_ref,
            )
            self._clear_session_summary_artifacts(connection, session_id)

            connection.execute(
                """
                INSERT INTO session_summaries_fts (
                    rowid,
                    project_id,
                    session_summary_id,
                    source_platform,
                    source_session_ref,
                    source_thread_ref,
                    agent_name,
                    summary,
                    outcome,
                    source_refs_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    project_id,
                    session_id,
                    request.source_platform,
                    request.source_session_ref,
                    request.source_thread_ref or "",
                    request.agent_name,
                    request.summary,
                    request.outcome or "",
                    source_refs_text,
                ),
            )

            for ref in request.source_refs:
                connection.execute(
                    """
                    INSERT INTO source_refs (session_summary_id, ref_kind, ref_value)
                    VALUES (?, ?, ?)
                    """,
                    (session_id, ref.kind, ref.value),
                )

            for decision in request.decisions:
                tags_json = json.dumps(decision.tags)
                tags_text = " ".join(decision.tags)
                decision_cursor = connection.execute(
                    """
                    INSERT INTO session_decisions (
                        project_id,
                        session_summary_id,
                        title,
                        status,
                        rationale,
                        tags_json,
                        tags_text,
                        github_ref,
                        doc_path
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        session_id,
                        decision.title,
                        decision.status,
                        decision.rationale,
                        tags_json,
                        tags_text,
                        decision.github_ref,
                        decision.doc_path,
                    ),
                )
                decision_id = int(decision_cursor.lastrowid)
                connection.execute(
                    """
                    INSERT INTO session_decisions_fts (
                        rowid,
                        project_id,
                        decision_id,
                        session_summary_id,
                        title,
                        status,
                        rationale,
                        tags_text,
                        github_ref,
                        doc_path
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        decision_id,
                        project_id,
                        decision_id,
                        session_id,
                        decision.title,
                        decision.status,
                        decision.rationale,
                        tags_text,
                        decision.github_ref or "",
                        decision.doc_path or "",
                    ),
                )
        return session_id

    def _get_session_summary_id(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        source_platform: str,
        source_session_ref: str,
    ) -> int:
        row = connection.execute(
            """
            SELECT id
            FROM session_summaries
            WHERE project_id = ? AND source_platform = ? AND source_session_ref = ?
            """,
            (project_id, source_platform, source_session_ref),
        ).fetchone()
        if row is None:
            raise RuntimeError("Session summary row was not persisted.")
        return int(row["id"])

    def _clear_session_summary_artifacts(
        self,
        connection: sqlite3.Connection,
        session_id: int,
    ) -> None:
        connection.execute(
            "DELETE FROM session_summaries_fts WHERE session_summary_id = ?",
            (session_id,),
        )
        connection.execute(
            "DELETE FROM session_decisions_fts WHERE session_summary_id = ?",
            (session_id,),
        )
        connection.execute(
            "DELETE FROM source_refs WHERE session_summary_id = ?",
            (session_id,),
        )
        connection.execute(
            "DELETE FROM session_decisions WHERE session_summary_id = ?",
            (session_id,),
        )

    def _delete_session_summary_rows(
        self,
        connection: sqlite3.Connection,
        session_ids: list[int],
    ) -> None:
        if not session_ids:
            return
        placeholders = ", ".join("?" for _ in session_ids)
        params = tuple(session_ids)
        connection.execute(
            f"DELETE FROM session_summaries_fts WHERE session_summary_id IN ({placeholders})",
            params,
        )
        connection.execute(
            f"DELETE FROM session_decisions_fts WHERE session_summary_id IN ({placeholders})",
            params,
        )
        connection.execute(
            f"DELETE FROM session_summaries WHERE id IN ({placeholders})",
            params,
        )

    def get_source_refs_for_sessions(self, session_ids: list[int]) -> dict[int, list[SourceRef]]:
        if not session_ids or not self.exists():
            return {}
        placeholders = ", ".join("?" for _ in session_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT session_summary_id, ref_kind, ref_value
                FROM source_refs
                WHERE session_summary_id IN ({placeholders})
                ORDER BY session_summary_id, id
                """,
                tuple(session_ids),
            ).fetchall()
        refs_by_session: dict[int, list[SourceRef]] = {}
        for row in rows:
            refs_by_session.setdefault(row["session_summary_id"], []).append(
                SourceRef(kind=row["ref_kind"], value=row["ref_value"])
            )
        return refs_by_session

    def list_recent_decision_titles(self, project_id: str, *, limit: int) -> list[str]:
        if limit <= 0 or not self.exists():
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT session_decisions.title
                FROM session_decisions
                JOIN session_summaries
                  ON session_summaries.id = session_decisions.session_summary_id
                WHERE session_decisions.project_id = ?
                ORDER BY session_summaries.created_at DESC, session_decisions.id DESC
                LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
        return [str(row["title"]) for row in rows]

    def search_documents(
        self,
        project_id: str,
        match_query: str,
        *,
        limit: int,
    ) -> list[sqlite3.Row]:
        if not self.exists():
            return []
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT
                    path,
                    kind,
                    heading,
                    snippet(document_chunks_fts, 4, '[', ']', '…', 18) AS snippet,
                    (-bm25(document_chunks_fts)) AS score
                FROM document_chunks_fts
                WHERE project_id = ? AND document_chunks_fts MATCH ?
                ORDER BY score DESC
                LIMIT ?
                """,
                (project_id, match_query, limit),
            ).fetchall()

    def search_session_summaries(
        self,
        project_id: str,
        match_query: str,
        *,
        limit: int,
    ) -> list[sqlite3.Row]:
        if not self.exists():
            return []
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT
                    session_summary_id,
                    source_platform,
                    source_session_ref,
                    source_thread_ref,
                    agent_name,
                    outcome,
                    snippet(session_summaries_fts, 6, '[', ']', '…', 18) AS snippet,
                    (-bm25(session_summaries_fts)) AS score
                FROM session_summaries_fts
                WHERE project_id = ? AND session_summaries_fts MATCH ?
                ORDER BY score DESC
                LIMIT ?
                """,
                (project_id, match_query, limit),
            ).fetchall()

    def search_decisions(
        self,
        project_id: str,
        match_query: str,
        *,
        limit: int,
    ) -> list[sqlite3.Row]:
        if not self.exists():
            return []
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT
                    decision_id,
                    session_summary_id,
                    title,
                    status,
                    github_ref,
                    doc_path,
                    snippet(session_decisions_fts, 5, '[', ']', '…', 18) AS snippet,
                    (-bm25(session_decisions_fts)) AS score
                FROM session_decisions_fts
                WHERE project_id = ? AND session_decisions_fts MATCH ?
                ORDER BY score DESC
                LIMIT ?
                """,
                (project_id, match_query, limit),
            ).fetchall()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _fetch_scalar(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> int:
    row = connection.execute(sql, params).fetchone()
    return 0 if row is None else int(row[0])


def _parse_optional_datetime(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _serialize_optional_datetime(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


__all__ = ["SQLiteMemoryStore", "StoredDocument"]
