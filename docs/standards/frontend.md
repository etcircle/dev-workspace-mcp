# Frontend standard

## Canonical sources

- **GitHub is canonical** for issues, backlog, and change tracking.
- **Repo docs are canonical** for standards, decisions, and agent guidance.
- **SQLite under `.devworkspace/` is retrieval/index state only**, not truth.

## Rules

- Read `docs/standards/design-system.md` before UI work.
- Keep frontend code thin. Backend/tool contracts stay authoritative for data shape and behavior.
- Prefer simple, inspectable UI flows over hidden state and clever client logic.
- Do not invent a local backlog UI that competes with GitHub.
- When a frontend rule should persist, write it here or in `docs/decisions/`.

## Current posture

There is no excuse to invent framework-specific doctrine in random PRs. If a durable frontend convention is needed, document it first.
