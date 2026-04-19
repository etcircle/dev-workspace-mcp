# Dev Workspace MCP Persistent Workspace Memory Program

> **For Hermes:** treat this as the umbrella program plan. Execute the immediate slice from the paired wave tracker, not from this whole document at once.

**Goal:** give every agent a fast, honest way to understand current project state without rereading the entire repo or inventing history.

**Architecture:** keep human-readable repo docs as the source of truth for standards/decisions, keep GitHub as the source of truth for issues and change tracking, then layer a local SQLite search/index store on top for fast retrieval of session summaries, decisions, and indexed canonical docs. Do **not** make SQLite the only truth source; that would turn the project into an opaque box full of half-stale rows.

**Tech Stack:** Python 3.11, SQLite + FTS5, existing state-doc services, MCP tools, pytest.

---

## Strong opinion

Do **not** start by dumping full raw chat transcripts into SQLite and pretending that is memory.

That path gets noisy, bloated, privacy-hostile, and useless fast.

Start with:
- session summaries
- explicit decisions
- issue / roadmap state
- pattern / standards docs
- searchable chunks from repo-local canonical docs

If later you want raw transcript retention, add it as an optional secondary lane with size limits and retention rules.

---

## The right shape: three layers

### 1. Canonical repo-local docs

These stay human-editable and reviewable in git.

Keep or extend:
- `AGENTS.md` — stable repo rules and working conventions
- `.devworkspace/memory.md` — current facts, known constraints, recent durable learnings
- `.devworkspace/tasks.md` — active work and blockers
- `.devworkspace/roadmap.md` — near/mid-term direction

Add:
- `docs/decisions/` — ADR-style design decisions
- `docs/standards/frontend.md`
- `docs/standards/backend.md`
- `docs/standards/design-system.md`
- optional later: `docs/patterns/` for reusable implementation patterns

Why: agents need a **human-legible source of truth** before they search a database.

### 2. GitHub tracking

GitHub is the durable tracker for:
- issues
- backlog
- milestones
- change slices / PR-linked execution

Do **not** rebuild that as a second local issue tracker in SQLite.

### 3. Local SQLite memory/index store

SQLite is the fast recall and search layer, not the sole authority.

Use it for:
- session summaries submitted by agents
- extracted decisions
- indexed chunks of canonical docs
- quick boot-time retrieval via FTS5
- searchable refs back to GitHub issues/PRs and external chat sessions

### 4. MCP boot + search tools

Agents should not manually stitch context from ten files every time.

Add tools that can:
- return a compact boot packet
- search prior decisions and summaries
- submit a session summary / decisions payload
- reindex canonical docs when they change

---

## Recommended information model

### Canonical docs remain primary for:
- rules
- current tasks
- roadmap
- design standards
- ADRs / decisions that matter long term

### SQLite stores structured searchable records for:
- `sessions`
  - source platform
  - external thread/session reference
  - agent name
  - start/end timestamps
  - summary
  - outcome
- `decisions`
  - title
  - status (`proposed`, `active`, `superseded`, `rejected`)
  - rationale
  - tags
  - source session/doc references
  - optional GitHub issue/PR refs
- `documents`
  - canonical doc metadata
  - path
  - hash
  - last indexed at
- `document_chunks`
  - chunk text for FTS search
- `source_refs`
  - GitHub issue/PR refs
  - external chat/thread refs
  - commit/doc references

### GitHub remains canonical for:
- issues
- roadmap/backlog
- change tracking
- execution slices tied to PRs/issues

Use the local DB to **index or reference** GitHub state if useful later, but not to replace it.

### FTS scopes

Use FTS5 over at least:
- session summaries
- decisions
- canonical doc chunks
- work items

That gives you fast search without dragging in vector-search theater on day one.

---

## What agents should read before implementing anything

I would formalize a required preflight contract:

1. `project_snapshot`
2. `AGENTS.md`
3. `.devworkspace/memory.md`
4. `.devworkspace/tasks.md`
5. `.devworkspace/roadmap.md`
6. top relevant hits from `search_workspace_memory`
7. standards docs for the touched domain (`frontend`, `backend`, `design-system`)
8. relevant decision docs under `docs/decisions/`

That beats “grep the repo and vibe it out,” which is how agents reinvent garbage.

---

## Suggested new docs layout

```text
docs/
  decisions/
    0001-source-of-truth-docs-vs-sqlite-index.md
    0002-session-summary-ingestion.md
  standards/
    frontend.md
    backend.md
    design-system.md
  patterns/
    search-tool-patterns.md          # optional later
    state-doc-update-patterns.md     # optional later
```

### Suggested rules

- `docs/decisions/` = long-lived architectural decisions
- `docs/standards/` = implementation guardrails agents must check first
- `docs/patterns/` = “how we do X here” once repeated enough to matter

Do not dump all of that into `.devworkspace/memory.md`. That file should stay compact.

---

## Suggested MCP tools

### Wave 1 tools
- `search_workspace_memory(project_id, query, scope='all')`
- `record_session_summary(project_id, summary, decisions=[], work_items=[], source_ref=...)`
- `reindex_workspace_memory(project_id)`
- `memory_index_status(project_id)`

### Wave 2 tools
- `get_boot_context(project_id, goal=...)`
- `list_decisions(project_id, status=...)`
- `list_work_items(project_id, kind=..., status=...)`

### Wave 3 tools
- `upsert_decision(...)`
- `upsert_work_item(...)`
- `link_artifact(...)`

Do **not** start with a giant CRUD jungle. Start with ingestion + search + boot context.

---

## Recommended phase breakdown

### Phase A — canonical-memory contract

Goal: define what lives in docs vs SQLite.

Deliverables:
- decision doc for source-of-truth split
- standards-doc skeletons
- boot contract for agents
- rules for session-summary payloads

### Phase B — SQLite memory/index foundation

Goal: add the local DB and FTS-backed indexing.

Deliverables:
- schema + migrations/bootstrap
- indexer for canonical docs
- index status / rebuild support
- tests for indexing and search correctness

### Phase C — session-summary ingestion

Goal: let agents submit summaries and decisions cleanly.

Deliverables:
- MCP tool for summary submission
- validation rules
- dedupe / merge behavior
- source refs to external chat/platform context

### Phase D — boot-context retrieval

Goal: one call gives a new agent the current state.

Deliverables:
- boot-context tool
- project snapshot enrichment from indexed memory
- top open tasks / roadmap / recent decisions

### Phase E — richer issue / roadmap / pattern workflows

Goal: better project coordination without making the system bloated.

Deliverables:
- structured work-item views
- decision listing and supersession
- optional artifact linking
- optional pattern-library indexing

---

## Immediate next wave I recommend

Do **not** jump straight into issues + roadmap + patterns + chat logs all at once.

The next sane slice is:

1. lock the source-of-truth model
2. add standards/decisions doc skeletons
3. build SQLite schema + FTS for docs + session summaries + decisions
4. expose **one search tool** and **one session-summary ingestion tool**
5. keep GitHub as the canonical issue/backlog tracker instead of cloning that into SQLite

That is enough to prove the architecture without building a monster.

---

## Things you are likely missing

A few important pieces that matter just as much as the DB:

### 1. Decision supersession
A decision system without `superseded by` / status rules turns into archaeological sludge.

### 2. Source refs
Every session summary / decision should keep a pointer to where it came from:
- platform
- chat/thread/session ref
- agent name
- optional commit/doc path

### 3. Reindex truthfulness
Search results are worthless if agents do not know whether the DB is fresh.
Expose index freshness and source hashes.

### 4. Boot packet discipline
Agents need one compact “where are we now?” call, not ten semi-overlapping tools.

### 5. Standards before search
If frontend/backend/design conventions are not written down, search just helps agents find inconsistency faster.

---

## Non-goals for the immediate wave

Not now:
- embeddings/vector DB
- full raw transcript archival
- hosted multi-user sync
- remote auth complexity for the memory subsystem
- full issue tracker replacement for GitHub/Linear
- automatic LLM-written decisions without review

Keep this boring and local first.

---

## Acceptance criteria for the first real implementation wave

The first wave is good enough if:
- there is a documented source-of-truth split between docs and SQLite
- standards docs exist in repo
- decisions docs have a stable home
- SQLite schema exists locally under project control
- FTS search works across canonical docs and session summaries
- agents can submit a session summary with decisions
- a fresh agent can recover the current state faster than reading the whole repo manually

If those are not true, the wave is not done.
