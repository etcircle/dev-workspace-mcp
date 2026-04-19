# Backend standard

## Canonical sources

- **GitHub is canonical** for issues, backlog, and change tracking.
- **Repo docs are canonical** for standards, decisions, and agent guidance.
- **SQLite under `.devworkspace/` is retrieval/index state only**, not truth.

## Rules

- Use Python 3.11.
- Keep modules thin, boring, and transport-agnostic where possible.
- Prefer stable models and explicit error handling over clever abstractions.
- Public tool contracts use `project_id` and project-relative paths.
- Prefer `argv[]` command execution over raw shell strings.
- Put durable backend rules in repo docs, not in issue comments or session memory.

## Memory-specific rule

If backend code touches workspace memory, keep GitHub as the canonical tracker and keep SQLite as search-only derived state.
