from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.memory_index.indexer import CanonicalDocumentIndexer
from dev_workspace_mcp.memory_index.sqlite_store import SQLiteMemoryStore
from dev_workspace_mcp.models.memory_index import (
    MemoryIndexStatus,
    MemorySearchResult,
    RecordSessionSummaryRequest,
    RecordSessionSummaryResponse,
    ReindexWorkspaceMemoryRequest,
    ReindexWorkspaceMemoryResponse,
    SearchWorkspaceMemoryRequest,
    SearchWorkspaceMemoryResponse,
    SourceRef,
)
from dev_workspace_mcp.shared.time import utc_now

_QUERY_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


class MemoryIndexService:
    def __init__(
        self,
        project_root: Path,
        project_id: str,
        settings: Settings | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.project_id = project_id
        self.settings = settings or Settings()
        self.store = SQLiteMemoryStore(self.settings.memory_index_db_path(self.project_root))
        self.indexer = CanonicalDocumentIndexer(
            self.project_root,
            chunk_size=self.settings.memory_index_chunk_size,
            chunk_overlap=self.settings.memory_index_chunk_overlap,
        )

    @property
    def db_path(self) -> Path:
        return self.store.db_path

    def get_status(self) -> MemoryIndexStatus:
        if not self.store.exists():
            return MemoryIndexStatus(
                project_id=self.project_id,
                status="missing",
                warnings=["Memory index database has not been initialized yet."],
            )

        counts = self.store.get_counts(self.project_id)
        status_row = self.store.get_index_status_row(self.project_id)
        indexed_documents = self.store.get_documents(self.project_id)
        current_documents = {
            document.path: document for document in self.indexer.collect_documents()
        }

        warnings: list[str] = []
        if counts["documents_indexed"] == 0:
            status = "empty"
            warnings.append("Canonical docs have not been indexed yet.")
        else:
            status = "ready"
            missing_paths = sorted(set(current_documents) - set(indexed_documents))
            removed_paths = sorted(set(indexed_documents) - set(current_documents))
            changed_paths = sorted(
                path
                for path in set(current_documents) & set(indexed_documents)
                if indexed_documents[path].content_hash != current_documents[path].content_hash
            )
            if missing_paths or removed_paths or changed_paths:
                status = "stale"
                warnings.extend(_freshness_warnings(missing_paths, removed_paths, changed_paths))

        if counts["documents_indexed"] == 0 and counts["session_summary_count"] > 0:
            warnings.append(
                "Session summaries exist, but canonical docs have not been indexed yet."
            )

        if status_row is not None and status_row.get("warning"):
            warning = str(status_row["warning"])
            if warning not in warnings:
                warnings.append(warning)

        return MemoryIndexStatus(
            project_id=self.project_id,
            status=status,
            last_indexed_at=None
            if status_row is None
            else _parse_last_indexed_at(status_row.get("last_indexed_at")),
            documents_indexed=counts["documents_indexed"],
            document_chunk_count=counts["document_chunk_count"],
            session_summary_count=counts["session_summary_count"],
            decision_count=counts["decision_count"],
            warnings=warnings,
        )

    def reindex(self, request: ReindexWorkspaceMemoryRequest) -> ReindexWorkspaceMemoryResponse:
        self._ensure_project_id(request.project_id)
        documents = self.indexer.collect_documents()
        indexed_at = utc_now()
        existing_paths = set(self.store.get_documents(self.project_id))
        changed = 0
        current_paths: set[str] = set()

        for document in documents:
            current_paths.add(document.path)
            if self.store.replace_document(self.project_id, document, indexed_at=indexed_at):
                changed += 1

        removed = self.store.delete_documents(
            self.project_id,
            sorted(existing_paths - current_paths),
        )
        warning = None if documents else "No canonical documents were found to index."
        self.store.set_index_status(
            self.project_id,
            last_indexed_at=indexed_at,
            last_index_reason=request.reason,
            status="ready" if documents else "empty",
            warning=warning,
        )
        status = self.get_status()
        return ReindexWorkspaceMemoryResponse(
            project_id=self.project_id,
            documents_indexed=len(documents),
            documents_changed=changed,
            documents_removed=removed,
            index_status=status,
        )

    def record_session_summary(
        self,
        request: RecordSessionSummaryRequest,
    ) -> RecordSessionSummaryResponse:
        self._ensure_project_id(request.project_id)
        self._validate_record_session_summary_request(request)
        session_summary_id = self.store.insert_session_summary(
            self.project_id,
            request,
            created_at=utc_now(),
        )
        return RecordSessionSummaryResponse(
            project_id=self.project_id,
            session_summary_id=session_summary_id,
            decision_count=len(request.decisions),
            source_ref_count=len(request.source_refs),
        )

    def search(self, request: SearchWorkspaceMemoryRequest) -> SearchWorkspaceMemoryResponse:
        self._ensure_project_id(request.project_id)
        status = self.get_status()
        if not self.store.exists():
            return SearchWorkspaceMemoryResponse(
                index_status=status,
                warnings=list(status.warnings),
            )

        limit = min(request.limit, self.settings.memory_index_max_search_results)
        match_query = _build_match_query(request.query)
        results: list[MemorySearchResult] = []

        if request.scope in {"all", "docs"}:
            results.extend(self._doc_results(match_query, limit))
        if request.scope in {"all", "sessions"}:
            results.extend(self._session_results(match_query, limit))
        if request.scope in {"all", "decisions"}:
            results.extend(self._decision_results(match_query, limit))

        results.sort(key=lambda item: item.score, reverse=True)
        return SearchWorkspaceMemoryResponse(
            results=results[:limit],
            index_status=status,
            warnings=list(status.warnings),
        )

    def recent_decision_titles(self, *, limit: int = 5) -> list[str]:
        return self.store.list_recent_decision_titles(self.project_id, limit=limit)

    def _doc_results(self, match_query: str, limit: int) -> list[MemorySearchResult]:
        rows = self.store.search_documents(self.project_id, match_query, limit=limit)
        results: list[MemorySearchResult] = []
        for row in rows:
            source_path = row["path"]
            title = row["heading"] or source_path
            source_ref = SourceRef(kind="doc", value=source_path)
            results.append(
                MemorySearchResult(
                    kind="doc",
                    title=title,
                    snippet=_normalize_snippet(row["snippet"], fallback=source_path),
                    source_path=source_path,
                    source_ref=source_ref.encoded(),
                    source_refs=[source_ref],
                    score=float(row["score"]),
                )
            )
        return results

    def _session_results(self, match_query: str, limit: int) -> list[MemorySearchResult]:
        rows = self.store.search_session_summaries(self.project_id, match_query, limit=limit)
        session_ids = [int(row["session_summary_id"]) for row in rows]
        refs_by_session = self.store.get_source_refs_for_sessions(session_ids)
        results: list[MemorySearchResult] = []
        for row in rows:
            session_id = int(row["session_summary_id"])
            source_refs = refs_by_session.get(session_id, [])
            title = f"Session: {row['agent_name']} ({row['source_platform']})"
            primary_ref = _primary_source_ref(source_refs)
            results.append(
                MemorySearchResult(
                    kind="session",
                    title=title,
                    snippet=_normalize_snippet(
                        row["snippet"],
                        fallback=str(row["outcome"] or row["source_session_ref"]),
                    ),
                    source_ref=primary_ref,
                    source_refs=source_refs,
                    score=float(row["score"]),
                )
            )
        return results

    def _decision_results(self, match_query: str, limit: int) -> list[MemorySearchResult]:
        rows = self.store.search_decisions(self.project_id, match_query, limit=limit)
        session_ids = sorted({int(row["session_summary_id"]) for row in rows})
        refs_by_session = self.store.get_source_refs_for_sessions(session_ids)
        results: list[MemorySearchResult] = []
        for row in rows:
            source_refs = _decision_source_refs(
                session_refs=refs_by_session.get(int(row["session_summary_id"]), []),
                github_ref=str(row["github_ref"] or "") or None,
                doc_path=str(row["doc_path"] or "") or None,
            )
            results.append(
                MemorySearchResult(
                    kind="decision",
                    title=row["title"],
                    snippet=_normalize_snippet(row["snippet"], fallback=row["status"]),
                    source_path=row["doc_path"],
                    source_ref=_primary_source_ref(source_refs),
                    source_refs=source_refs,
                    score=float(row["score"]),
                )
            )
        return results

    def _ensure_project_id(self, project_id: str) -> None:
        if project_id != self.project_id:
            raise ValueError(
                "Memory index service is bound to "
                f"project_id={self.project_id!r}, got {project_id!r}."
            )

    def _validate_record_session_summary_request(
        self,
        request: RecordSessionSummaryRequest,
    ) -> None:
        canonical_doc_paths = {document.path for document in self.indexer.collect_documents()}
        for decision in request.decisions:
            if decision.doc_path is not None:
                self._ensure_canonical_doc_path(
                    decision.doc_path,
                    canonical_doc_paths=canonical_doc_paths,
                    label="Decision doc_path",
                )
        for source_ref in request.source_refs:
            if source_ref.kind == "doc":
                self._ensure_canonical_doc_path(
                    source_ref.value,
                    canonical_doc_paths=canonical_doc_paths,
                    label="SourceRef(kind='doc')",
                )

    def _ensure_canonical_doc_path(
        self,
        doc_path: str,
        *,
        canonical_doc_paths: set[str],
        label: str,
    ) -> None:
        if doc_path not in canonical_doc_paths:
            raise ValueError(
                f"{label} must point to a canonical document in this project: {doc_path}"
            )


def _build_match_query(query: str) -> str:
    tokens = _QUERY_TOKEN_PATTERN.findall(query.lower())
    if not tokens:
        escaped = query.strip().replace('"', '""')
        return f'"{escaped}"'
    return " ".join(f'"{token}"' for token in tokens)


def _freshness_warnings(
    missing_paths: list[str],
    removed_paths: list[str],
    changed_paths: list[str],
) -> list[str]:
    warnings: list[str] = []
    if missing_paths:
        warnings.append(
            "New canonical docs are not indexed yet: " + ", ".join(missing_paths[:3])
        )
    if removed_paths:
        warnings.append(
            "Indexed canonical docs no longer exist on disk: " + ", ".join(removed_paths[:3])
        )
    if changed_paths:
        warnings.append(
            "Canonical docs changed since the last reindex: " + ", ".join(changed_paths[:3])
        )
    return warnings


def _normalize_snippet(snippet: str | None, *, fallback: str) -> str:
    normalized = (snippet or "").strip()
    return normalized or fallback


def _decision_source_refs(
    *,
    session_refs: list[SourceRef],
    github_ref: str | None,
    doc_path: str | None,
) -> list[SourceRef]:
    source_refs: list[SourceRef] = []
    if github_ref:
        source_refs.extend(_decision_github_source_refs(session_refs, github_ref))
    if doc_path:
        source_refs.append(SourceRef(kind="doc", value=doc_path))
    source_refs.extend(session_refs)
    return _dedupe_source_refs(source_refs)


def _decision_github_source_refs(session_refs: list[SourceRef], github_ref: str) -> list[SourceRef]:
    for ref in session_refs:
        if ref.value == github_ref and ref.kind.startswith("github"):
            return [ref]
    return [SourceRef(kind="github", value=github_ref)]


def _dedupe_source_refs(source_refs: list[SourceRef]) -> list[SourceRef]:
    deduped: list[SourceRef] = []
    seen: set[str] = set()
    for ref in source_refs:
        encoded = ref.encoded()
        if encoded in seen:
            continue
        deduped.append(ref)
        seen.add(encoded)
    return deduped


def _primary_source_ref(source_refs: list[SourceRef]) -> str | None:
    if not source_refs:
        return None
    return source_refs[0].encoded()


def _parse_last_indexed_at(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


__all__ = ["MemoryIndexService"]
