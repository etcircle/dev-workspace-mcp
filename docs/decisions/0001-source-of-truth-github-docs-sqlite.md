# 0001 - Source of truth: GitHub, repo docs, SQLite

- Status: active
- Date: 2026-04-19

## Decision

Split truth on purpose:

- **GitHub is canonical** for issues, backlog, milestones, PRs, and change tracking.
- **Repo docs are canonical** for standards, decisions, and agent guidance.
- **SQLite/FTS under `.devworkspace/` is non-canonical local state** for retrieval, indexing, search, and recall artifacts.

## Canonical locations

### GitHub owns work tracking

Use GitHub for:
- issues
- backlog
- milestones
- PR-linked execution history
- change tracking

Do **not** build or imply a local issue tracker in SQLite or markdown.
Do **not** turn `.devworkspace/tasks.md` into a second backlog system.
Use `.devworkspace/tasks.md` for short-lived active task state, current blockers, and in-flight coordination only.
It is not canonical backlog or change-history storage.

### Repo docs own guidance and durable decisions

Use repo docs for:
- `AGENTS.md`
- `.devworkspace/memory.md`
- `.devworkspace/roadmap.md`
- `docs/decisions/`
- `docs/standards/`

If a rule should survive agent sessions, put it in git-tracked docs.

### SQLite owns search, not truth

Use SQLite/FTS for:
- indexing canonical docs
- persisting local session-summary / decision recall artifacts for retrieval
- storing searchable source refs and freshness metadata

SQLite is a cache/index plus local recall storage. If it disagrees with GitHub or repo docs, SQLite is wrong.

## Consequences

- Agents must read repo docs before implementation.
- Agents must treat GitHub as the source for open work and change history.
- Session memory stays concise and structured. No transcript hoarding in Wave 1.
