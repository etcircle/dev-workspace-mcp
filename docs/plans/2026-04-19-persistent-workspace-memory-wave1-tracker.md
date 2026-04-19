# Dev Workspace MCP Persistent Workspace Memory + GitHub Tracking — Wave 1 Tracker

## Scope

This tracker fences the immediate wave for persistent workspace memory.

Canonical umbrella plan:
- `docs/plans/2026-04-19-persistent-workspace-memory-program.md`

This wave is intentionally **not** the whole memory system.
It is the smallest honest slice that proves the architecture.

---

## Repo checkpoint at tracker creation

Verified at creation time:
- date: `2026-04-19 09:09:43 BST`
- branch: `main`
- `HEAD = f80943b`
- repo dirt before writing tracker:
  - untracked `.hermes/`

---

## Wave 1 objective

Land the minimum foundation for searchable project memory without turning the repo into a giant opaque database product.

That means:
1. lock the docs-vs-SQLite-vs-GitHub source-of-truth split
2. add canonical standards/decision docs scaffolding
3. add a local SQLite + FTS index for canonical docs, session summaries, and decisions
4. expose one search tool and one session-summary ingestion tool
5. keep GitHub as the canonical place for backlog/change tracking

---

## In scope now

### Track 1 — source-of-truth contract
- define what stays in repo docs
- define what GitHub owns as canonical issue/backlog/change tracking
- define what is indexed into SQLite
- define required session-summary payload shape

### Track 2 — canonical docs scaffolding
- add `docs/decisions/`
- add `docs/standards/frontend.md`
- add `docs/standards/backend.md`
- add `docs/standards/design-system.md`
- add a first decision doc for docs-vs-SQLite-vs-GitHub split

### Track 3 — SQLite memory/index foundation
- local DB path/config
- schema/bootstrap
- FTS-backed indexing of canonical docs
- indexing for session summaries and decisions
- index status / rebuild path

### Track 4 — minimal MCP surface
- `search_workspace_memory(...)`
- `record_session_summary(...)`
- maybe `memory_index_status(...)` if needed for honesty

---

## Explicitly deferred

Not in this wave:
- raw transcript archival
- embeddings/vector search
- full issue CRUD
- full roadmap CRUD
- artifact linking
- automatic decision generation from arbitrary chat
- hosted/multi-user memory sync
- replacing GitHub/Linear with an in-repo issue tracker

If implementation drifts into those lanes, stop and cut scope back down.

---

## Parent-owned seams

These need deliberate parent review because they affect the public contract or long-term repo shape:
- `README.md`
- `dev_workspace_mcp/config.py`
- `dev_workspace_mcp/models/`
- `dev_workspace_mcp/mcp_server/tool_registry.py`
- `dev_workspace_mcp/projects/snapshots.py`

Parent owns:
- public tool names and request/response shape
- DB location/default config
- project snapshot enrichment fields
- the docs-vs-SQLite-vs-GitHub source-of-truth rule

---

## Likely files for this wave

Expected areas, subject to narrowing during implementation:
- `dev_workspace_mcp/config.py`
- `dev_workspace_mcp/models/` for memory/search DTOs
- `dev_workspace_mcp/mcp_server/tool_registry.py`
- `dev_workspace_mcp/projects/snapshots.py`
- new memory/index module(s), likely under a new package such as:
  - `dev_workspace_mcp/memory_index/` or `dev_workspace_mcp/search/`
- tests for indexing/search/tool behavior
- `docs/decisions/`
- `docs/standards/`

---

## Required proofs

### Contract/docs proof
- standards docs exist and are readable in repo
- first ADR / decision doc exists
- docs-vs-SQLite split is explicit and not hand-wavy

### Index/search proof
- SQLite DB initializes locally
- FTS search returns hits from canonical docs
- index freshness/status is visible
- reindex path works cleanly

### Session-summary proof
- summary submission stores structured rows
- decisions from the payload are searchable
- external source refs are preserved
- GitHub issue/PR refs survive ingestion without pretending SQLite owns them

### Agent boot proof
- a fresh agent can recover current state faster than manual repo trawling
- snapshot / search outputs stay honest about what is indexed vs not indexed
- GitHub remains clearly identified as the canonical work tracker

---

## Review questions to answer during implementation

- Is SQLite only an index/search layer, or are we accidentally making it the hidden source of truth?
- Are standards/decisions readable in git without touching the DB?
- Can search results explain where a fact came from?
- Can agents tell when the index is stale?
- Are we storing concise summaries, not garbage transcript dumps?

---

## Good first implementation order

1. Add docs scaffolding and first decision doc
2. Add schema/bootstrap for SQLite + FTS
3. Index canonical docs
4. Add search tool
5. Add session-summary ingestion
6. Enrich snapshot / boot path only after the above works

That order matters. Search before a stable source-of-truth model is just faster confusion.
