# 0002 - Session summary contract

- Status: active
- Date: 2026-04-19

## Decision

Session summaries are **structured, concise recall records** for retrieval.
They are not raw transcript dumps.
They do not replace GitHub for work tracking or repo docs for durable guidance and decisions.
If a summary disagrees with GitHub or git-tracked docs, the canonical source wins.
SQLite may persist these summaries and searchable decision records locally, but that storage is recall-only, not authority.

## Required payload

Each session summary records:
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

## `source_platform`

- Use a short lowercase string naming the origin system, for example `openclaw`, `github`, or `slack`.
- Wave 1 convention: free-form lowercase `[a-z0-9_]+`. Do not create mixed-case aliases for the same platform.

## Summary rules

- Write what happened, what changed, what matters next.
- Keep it short enough to scan.
- Link out with `source_refs` instead of stuffing in transcripts.
- Treat the summary as a recall artifact, not durable authority.
- If a decision becomes durable repo guidance, promote it into `docs/decisions/` or `docs/standards/`.

## `source_refs`

Each `source_ref` is:
- `kind`
- `value`

Allowed `kind` values for Wave 1:
- `github`
- `github_issue`
- `github_pr`
- `github_discussion`
- `chat_thread`
- `doc`
- `commit`

Normalize `value` to one stable compact form per `kind`, not whatever URL happened to be pasted:
- `github`: `owner/repo#123` when the exact GitHub subtype is not available
- GitHub refs: `owner/repo#123`
- `doc`: repo-relative path such as `docs/decisions/0002-session-summary-contract.md`
- `commit`: full 40-char SHA
- `chat_thread`: platform-native stable thread identifier

These are references only. They do not make SQLite the source of truth.

## `decisions[]`

Each decision entry is:
- `title`
- `status`
- `rationale`
- `tags` (optional)
- `github_ref` (optional)
- `doc_path` (optional)

Allowed `status` values:
- `proposed` - raised in the session, not adopted yet
- `active` - adopted and currently in force
- `superseded` - replaced by a newer decision
- `rejected` - considered and declined

## Rules

- Use `github_ref` only as a pointer back to canonical GitHub tracking.
- Use `doc_path` when the decision is captured in a canonical repo doc.
- Do not record raw transcript blobs in this contract.
