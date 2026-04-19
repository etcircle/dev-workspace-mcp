# Dev Workspace MCP Persistent Memory + GitHub Tracking Implementation Plan

> **For Hermes:** execute this in a fresh session with `subagent-driven-development`. Use one implementation subagent per task group, then a separate review subagent, then a separate test/proof subagent. Parent verifies every claimed proof before committing anything.

**Goal:** give new agents a fast, honest boot path into project state by combining git-tracked standards/decisions, GitHub-backed work tracking, and a local SQLite/FTS memory index for session summaries and searchable recall.

**Architecture:** do **not** make SQLite the source of truth. Use **GitHub** as the canonical place for issues, backlog, and change tracking; use **repo docs** as the canonical place for standards, decisions, and durable agent guidance; use **SQLite/FTS** only as the local retrieval/index layer for fast search across canonical docs plus agent-submitted session summaries and decision records.

**Tech Stack:** Python 3.11, SQLite + FTS5, existing `state_docs` and `project_snapshot` seams, MCP tool registry, CLI parity, pytest, ruff.

---

## Non-negotiable design rules

1. **GitHub is canonical for backlog/change tracking.**
   - Do not build a fake local issue tracker in SQLite.
   - Do not turn `.devworkspace/tasks.md` into a second issue system.
   - Use GitHub Issues/Projects/Milestones for durable work tracking.

2. **Repo docs are canonical for agent guidance.**
   - `AGENTS.md`
   - `.devworkspace/memory.md`
   - `.devworkspace/roadmap.md`
   - `docs/decisions/`
   - `docs/standards/`

3. **SQLite is retrieval, not truth.**
   - Store indexed chunks of canonical docs.
   - Store session summaries and explicit decisions.
   - Store GitHub refs/metadata only as searchable references, not as the authority.

4. **Boot context must stay honest.**
   - If the DB is stale, say so.
   - If GitHub data is not synced/imported, say so.
   - If a fact only comes from a session summary, expose the source ref.

5. **No transcript-hoarding bullshit in Wave 1.**
   - Session summaries, decisions, and references first.
   - Raw transcript archival is explicitly deferred.

---

## What this wave should deliver

By the end of this implementation, a fresh agent should be able to:

1. read canonical repo guidance
2. search a local memory index for prior summaries/decisions/standards
3. record a session summary with linked GitHub refs and decision entries
4. tell whether the memory index is fresh
5. understand that GitHub is the canonical work tracker

---

## Canonical source-of-truth split

### GitHub (canonical)
Use GitHub for:
- issues
- backlog
- milestones
- change tracking
- PR-linked execution history

### Repo docs (canonical)
Use repo docs for:
- agent rules and conventions
- architecture/design decisions
- frontend/backend/design-system standards
- current project memory and direction

### SQLite (derived/indexed)
Use SQLite for:
- full-text search over canonical docs
- session summaries from agents
- extracted decision records
- source refs to GitHub issues/PRs/discussions/threads
- freshness/index metadata

---

## Required new docs structure

```text
docs/
  decisions/
    0001-source-of-truth-github-docs-sqlite.md
    0002-session-summary-contract.md
  standards/
    backend.md
    frontend.md
    design-system.md
```

### Required document intent

- `0001-source-of-truth-github-docs-sqlite.md`
  - explicitly states the canonical split above
  - explains why SQLite is not the issue tracker

- `0002-session-summary-contract.md`
  - defines required summary payload shape
  - defines `source_refs`
  - defines `decision` entries and statuses

- `docs/standards/backend.md`
  - backend conventions agents must read before implementing

- `docs/standards/frontend.md`
  - frontend conventions agents must read before implementing

- `docs/standards/design-system.md`
  - design-system / UX conventions agents must read before implementing UI work

These do not need to be long. They need to exist, be blunt, and be searchable.

---

## Proposed code shape

### New package

Create a dedicated package:

```text
dev_workspace_mcp/memory_index/
  __init__.py
  models.py
  sqlite_store.py
  indexer.py
  service.py
```

### Existing files likely to change

- `dev_workspace_mcp/config.py`
- `dev_workspace_mcp/runtime.py`
- `dev_workspace_mcp/mcp_server/tool_registry.py`
- `dev_workspace_mcp/cli/main.py`
- `dev_workspace_mcp/projects/snapshots.py`
- `dev_workspace_mcp/models/projects.py`
- maybe `dev_workspace_mcp/models/common.py` if shared refs belong there

### Tests to add

- `tests/test_memory_index.py`
- `tests/test_memory_index_tools.py`
- `tests/test_memory_index_cli.py`
- update `tests/test_project_snapshot.py`
- update `tests/test_mcp_server.py` if tool registration coverage belongs there

---

## Proposed SQLite schema

Use boring SQLite with FTS5. No vectors. No drama.

### Core tables

#### `documents`
Tracks canonical indexed files.

Suggested columns:
- `id`
- `project_id`
- `path`
- `kind` (`agents`, `memory`, `roadmap`, `decision`, `standard`, `other`)
- `content_hash`
- `indexed_at`

#### `document_chunks`
FTS-backed chunk storage.

Suggested columns:
- `document_id`
- `chunk_index`
- `heading`
- `content`

Use FTS5 over `heading, content`.

#### `session_summaries`
Structured session memory submitted by agents.

Suggested columns:
- `id`
- `project_id`
- `source_platform`
- `source_session_ref`
- `source_thread_ref`
- `agent_name`
- `started_at`
- `ended_at`
- `summary`
- `outcome`
- `created_at`

#### `session_decisions`
Decision rows linked to session summaries.

Suggested columns:
- `id`
- `session_summary_id`
- `title`
- `status` (`proposed`, `active`, `superseded`, `rejected`)
- `rationale`
- `tags_json`
- `github_ref`
- `doc_path`

#### `source_refs`
Optional normalized links to external references.

Suggested columns:
- `id`
- `session_summary_id`
- `ref_kind` (`github_issue`, `github_pr`, `github_discussion`, `chat_thread`, `doc`, `commit`)
- `ref_value`

#### `index_status`
One-row-per-project or per-scope freshness metadata.

Suggested columns:
- `project_id`
- `last_indexed_at`
- `last_index_reason`
- `documents_indexed`
- `status`
- `warning`

---

## Public tool contract for this wave

### 1. `search_workspace_memory`

**Purpose:** search indexed docs, session summaries, and decisions.

**Suggested request shape:**
- `project_id`
- `query`
- `scope` = `all | docs | sessions | decisions`
- `limit` (default 10, hard cap 50)

**Suggested response shape:**
- `results[]` with:
  - `kind`
  - `title`
  - `snippet`
  - `source_path`
  - `source_ref`
  - `score`
- `index_status`
- `warnings[]`

### 2. `record_session_summary`

**Purpose:** record one agent session summary plus explicit decisions and references.

**Suggested request shape:**
- `project_id`
- `source_platform`
- `source_session_ref`
- `source_thread_ref` (optional)
- `agent_name`
- `started_at` (optional)
- `ended_at` (optional)
- `summary`
- `outcome` (optional)
- `decisions[]`
- `source_refs[]`

**Decision item shape:**
- `title`
- `status`
- `rationale`
- `tags`
- `github_ref` (optional)
- `doc_path` (optional)

**Source ref shape:**
- `kind`
- `value`

### 3. `memory_index_status`

**Purpose:** expose freshness and counts honestly.

**Suggested response shape:**
- `status`
- `last_indexed_at`
- `documents_indexed`
- `session_summary_count`
- `decision_count`
- `warnings[]`

### 4. `reindex_workspace_memory`

**Purpose:** rebuild indexed canonical docs for one project.

Keep this explicit. Do not silently reindex everything on every search call.

---

## Project snapshot enrichment

After the base tools work, add a **small** honest extension to `project_snapshot`.

### Additions to `ProjectSnapshot`

Suggested new fields:
- `memory_index_status: str | None`
- `recent_decision_titles: list[str]`
- `standards_docs: list[str]`
- `tracking_systems: list[str]` with values like `GitHub Issues`, `Repo Decisions`, `SQLite Memory Index`

### Important rule

Do **not** dump search results into the snapshot.
The snapshot should hint where to look next, not become an unbounded briefing novel.

---

## CLI parity for this wave

Add a narrow CLI surface, not everything.

Suggested commands:

```bash
dev-workspace-mcp cli memory-index status <project_id>
dev-workspace-mcp cli memory-index reindex <project_id>
dev-workspace-mcp cli --json memory-index search <project_id> --query "session continuity"
dev-workspace-mcp cli --json memory-index record-session <project_id> --input path/to/summary.json
```

### Important rule

For `record-session`, prefer JSON input file or stdin JSON rather than an explosion of CLI flags. Fifty flags is how CLI tools become garbage.

---

## Suggested task breakdown for delegated execution

### Task Group 1 — Canonical docs scaffolding

**Objective:** create the standards and decision docs that define the truth model before any DB code lands.

**Files:**
- Create: `docs/decisions/0001-source-of-truth-github-docs-sqlite.md`
- Create: `docs/decisions/0002-session-summary-contract.md`
- Create: `docs/standards/backend.md`
- Create: `docs/standards/frontend.md`
- Create: `docs/standards/design-system.md`

**Implementation notes:**
- keep them short and blunt
- explicitly state GitHub canonical tracking
- define source refs and decision status values

**Verification:**
- read-through for internal consistency
- ensure the docs do not contradict `AGENTS.md` or existing state-doc conventions

**Commit:**
- `docs: add canonical standards and memory decision docs`

---

### Task Group 2 — Models + config for memory index

**Objective:** define stable DTOs and config before wiring services.

**Files:**
- Modify: `dev_workspace_mcp/config.py`
- Create: `dev_workspace_mcp/memory_index/models.py`
- Optionally create or modify shared DTO files if cleaner:
  - `dev_workspace_mcp/models/common.py`
  - or `dev_workspace_mcp/models/memory_index.py`

**Implementation notes:**
- add config for DB path and maybe chunk size limits
- define request/response DTOs for:
  - search
  - record session summary
  - index status
  - reindex
- define structured `DecisionRecord` and `SourceRef`

**Verification:**
- targeted model validation tests
- config defaults test

**Tests:**
- `tests/test_config.py`
- `tests/test_memory_index.py`

**Commit:**
- `feat: add memory index models and config`

---

### Task Group 3 — SQLite store + FTS indexer

**Objective:** build the local DB foundation and canonical-doc indexing.

**Files:**
- Create: `dev_workspace_mcp/memory_index/sqlite_store.py`
- Create: `dev_workspace_mcp/memory_index/indexer.py`
- Create: `dev_workspace_mcp/memory_index/service.py`
- Create: `dev_workspace_mcp/memory_index/__init__.py`
- Tests: `tests/test_memory_index.py`

**Implementation notes:**
- create tables lazily on first use
- index canonical docs only from safe repo-local paths:
  - `AGENTS.md`
  - `.devworkspace/memory.md`
  - `.devworkspace/roadmap.md`
  - `docs/decisions/**/*.md`
  - `docs/standards/**/*.md`
- chunk documents deterministically
- store content hash to avoid pointless reindex churn
- expose honest index status

**Verification:**
- fresh DB initializes
- doc indexing works
- search hits return snippets from indexed docs
- reindex updates hashes/status cleanly

**Commit:**
- `feat: add sqlite fts memory index foundation`

---

### Task Group 4 — Session-summary ingestion

**Objective:** let agents submit structured summaries with decisions and GitHub refs.

**Files:**
- Modify: `dev_workspace_mcp/memory_index/service.py`
- Tests: `tests/test_memory_index.py`
- maybe shared DTO file from Task Group 2

**Implementation notes:**
- store summaries, decisions, and source refs transactionally
- keep GitHub references as refs/metadata only
- do not attempt live GitHub API writes in this wave
- dedupe only if there is a clean deterministic rule; otherwise prefer append-only

**Verification:**
- inserted summaries are searchable
- decisions are searchable separately
- source refs are preserved

**Commit:**
- `feat: add session summary and decision ingestion`

---

### Task Group 5 — MCP tools + runtime wiring + CLI parity

**Objective:** expose the memory index through the public surface.

**Files:**
- Modify: `dev_workspace_mcp/runtime.py`
- Modify: `dev_workspace_mcp/mcp_server/tool_registry.py`
- Modify: `dev_workspace_mcp/cli/main.py`
- Tests: `tests/test_memory_index_tools.py`
- Tests: `tests/test_memory_index_cli.py`
- Update: `tests/test_mcp_server.py` if needed for registration assertions

**Implementation notes:**
- wire service into runtime
- register only the 3-4 tools listed above
- add narrow CLI parity
- keep result envelopes consistent with current tool contract

**Verification:**
- tool registration present
- CLI search/status/reindex/record-session work
- JSON envelopes stay stable

**Commit:**
- `feat: expose workspace memory tools and cli`

---

### Task Group 6 — Snapshot enrichment and truthfulness pass

**Objective:** give agents a better boot hint without bloating the snapshot.

**Files:**
- Modify: `dev_workspace_mcp/models/projects.py`
- Modify: `dev_workspace_mcp/projects/snapshots.py`
- Update tests: `tests/test_project_snapshot.py`
- Update docs: `README.md` only if the public surface changes enough to require it

**Implementation notes:**
- add a small memory/search status hint to the snapshot
- mention GitHub tracking in capabilities/recommended next tools if appropriate
- do not overclaim sync or freshness

**Verification:**
- project snapshot stays concise
- snapshot reflects the new memory/search capability honestly

**Commit:**
- `feat: enrich project snapshot with memory index hints`

---

## Subagent execution model for the next session

### Implementation agents
Use one implementation subagent per task group or tightly-related pair:
- Agent A: Task Group 1
- Agent B: Task Groups 2-3
- Agent C: Task Groups 4-5
- Parent or final agent: Task Group 6 after the base tools are proven

Do **not** run agents B and C in parallel until DTOs and DB seams from Task Group 2 are settled.

### Review agent
After each task group lands, spawn a fresh reviewer that checks only:
- contract honesty
- regression risk
- source-of-truth discipline
- GitHub-vs-SQLite separation

### Test/proof agent
After review passes, spawn a fresh proof agent that runs:
- targeted pytest nodes
- CLI smoke checks
- one manual search / record-session / reindex path

### Parent verification
Parent reruns every claimed proof locally before accepting the task group.
No exceptions.

---

## Required verification commands at the end

### Narrow checks during implementation
```bash
python -m pytest -q tests/test_memory_index.py
python -m pytest -q tests/test_memory_index_tools.py tests/test_memory_index_cli.py
python -m pytest -q tests/test_project_snapshot.py
```

### Full checks before calling it done
```bash
python -m ruff check .
python -m pytest -q
python -m dev_workspace_mcp.app describe
python -m dev_workspace_mcp.app cli --json memory-index status <project_id>
python -m dev_workspace_mcp.app cli --json memory-index search <project_id> --query "design system"
```

### Manual proof expectations
- search returns hits from standards/decisions docs
- recorded session summary becomes searchable
- decisions retain GitHub refs in results
- status call shows fresh/stale state honestly
- project snapshot does not become bloated nonsense

---

## Explicit non-goals for this implementation

Not now:
- GitHub write integration
- syncing full issue bodies/comments into SQLite as truth
- full roadmap CRUD in SQLite
- transcript archival
- vector DB / embeddings
- hosted/shared remote memory service

Keep it local, searchable, and honest first.

---

## Final acceptance criteria

This plan is complete only when:
- GitHub is explicitly documented as canonical work tracking
- repo standards/decision docs exist and are indexed
- local SQLite/FTS memory index works
- agents can record session summaries with decisions/source refs
- memory search is exposed via MCP and CLI
- project snapshot gives a compact, honest memory hint
- all tests and parent-side proofs pass

If any of that is missing, the implementation is still half-baked.
