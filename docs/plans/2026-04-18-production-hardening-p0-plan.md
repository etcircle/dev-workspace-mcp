# Dev Workspace MCP Production Hardening P0 Plan

> **For Hermes:** Use `subagent-driven-development` for implementation, then `requesting-code-review` style independent review, then rerun parent-side proofs.

**Goal:** Land the smallest honest hardening wave that fixes the real state-doc path escape, blocks accidental public HTTP exposure, bounds in-memory output/log growth, and replaces the README with the shorter truthful version plus explicit safety warnings.

**Architecture:** Keep the public product surface intact. Harden the existing seams instead of inventing a new runtime layer. Reuse the shared path resolver for state docs, add explicit serve-time HTTP bind/origin protections, bound job/log capture in memory, and tell the truth in docs.

**Tech Stack:** Python 3.11, FastMCP / FastAPI HTTP transport, Pydantic settings/models, pytest.

---

## Why this wave exists

The peer review is directionally right, but the repo has already moved since the older multi-wave program. The current live checkpoint is:

- branch: `main`
- `HEAD == origin/main == e05627e`
- baseline tests: `python -m pytest -q` pass
- current dirt before this wave: untracked `.hermes/` and `docs/plans/2026-04-18-project-bootstrap-and-connections-handover.md`

This wave is intentionally **narrower** than the peer review memo. It fixes the sharpest blockers we can land honestly in one slice.

### In scope now

1. State-doc symlink/path safety
2. Explicit HTTP bind guard + origin filtering + startup warning for unsafe bind
3. Bounded command output capture and bounded service log retention
4. README replacement with the shorter truthful version plus explicit trusted-local warnings

### Explicitly deferred from this wave

These are valid follow-ups, but not part of this immediate slice:

- durable job/log persistence across server restarts
- bearer/token auth for remote HTTP exposure
- port/service-scoped localhost HTTP restrictions
- writable-roots enforcement across all write-capable tools
- broader secret redaction expansion
- identifier validation for project IDs / aliases / service / probe names

Do not smuggle deferred work into this wave.

---

## Canonical tracker

Use this tracker as the execution fence for the current wave:

- `docs/plans/2026-04-18-production-hardening-p0-tracker.md`

If implementation needs more files than the tracker allows, amend the tracker first.

---

## Execution order

### Task 1: Harden state-doc path resolution

**Objective:** Route `.devworkspace/*.md` reads/writes/patches through the shared resolver so symlinked `.devworkspace` paths or symlinked state-doc files cannot escape the project root.

**Files:**
- Modify: `dev_workspace_mcp/state_docs/service.py`
- Test: `tests/test_state_docs.py`
- Optional only if genuinely needed: `dev_workspace_mcp/shared/paths.py`

**Required behavior:**
- `StateDocumentService.doc_path()` or equivalent helper must resolve via `resolve_project_path(...)`
- reads must reject symlink traversal
- writes/patches must support missing-leaf creation under an in-project parent without allowing symlink escapes
- error semantics should stay consistent with existing path safety errors (`PATH_SYMLINK_DENIED` / `PATH_OUTSIDE_PROJECT`)

**Required proofs:**
- `.devworkspace` symlink to outside path is denied on read/write/patch
- `.devworkspace/memory.md` symlink to outside file is denied on read/write/patch
- normal read/write/patch still work for real in-project state docs

**Verification commands:**
- `python -m pytest -q tests/test_state_docs.py`

---

### Task 2: Harden HTTP serving defaults

**Objective:** Make accidental public bind materially harder and reject hostile browser origins for the HTTP MCP app.

**Files:**
- Modify: `dev_workspace_mcp/config.py`
- Modify: `dev_workspace_mcp/app.py`
- Modify: `dev_workspace_mcp/mcp_server/transport_http.py`
- Test: `tests/test_app.py`
- Test: `tests/test_transport_http.py`

**Required behavior:**
- default bind remains `127.0.0.1`
- `serve-http --host 0.0.0.0` or other non-local bind must be rejected unless an explicit unsafe/public-bind flag is provided
- starting with an unsafe/public bind flag must print a loud warning
- HTTP transport must reject unexpected `Origin` headers when serving local MCP over HTTP
- keep current tool registration / FastMCP mounting behavior intact

**Notes:**
- do not add full token auth in this wave
- do not break localhost CLI/dev usage
- keep the implementation boring; a thin ASGI wrapper or middleware is fine

**Required proofs:**
- normal localhost serve path still dispatches correctly
- public bind without override fails cleanly
- public bind with override succeeds and warns
- same-origin / no-origin requests still work
- disallowed origin gets rejected before the tool layer

**Verification commands:**
- `python -m pytest -q tests/test_app.py tests/test_transport_http.py`

---

### Task 3: Bound command/job output and service logs

**Objective:** Stop unbounded memory growth in foreground/background command capture and service logs, while preserving stable response shapes.

**Files:**
- Modify: `dev_workspace_mcp/config.py`
- Modify: `dev_workspace_mcp/commands/jobs.py`
- Modify: `dev_workspace_mcp/commands/service.py`
- Modify: `dev_workspace_mcp/services/logs.py`
- Test: `tests/test_commands.py`
- Test: `tests/test_services.py`

**Required behavior:**
- foreground command execution must not rely on `capture_output=True` for effectively unbounded output
- background capture must stream incrementally instead of `handle.read()` of the full stream
- command output retained in `JobRecord.output` must be globally bounded
- service logs retained in `ServiceLogStore` must be bounded
- pagination / `next_offset` behavior for service logs should remain honest after trimming
- preserve redaction and current public response models

**Notes:**
- durable disk persistence is deferred
- a bounded ring buffer / byte-capped retention model is enough for this wave
- if the cap is split across stdout/stderr, make it explicit and deterministic

**Required proofs:**
- large stdout does not explode retained output size
- background capture still returns streamed/truncated output sanely
- service log flood trims old lines instead of growing forever
- ordinary command/service tests still pass

**Verification commands:**
- `python -m pytest -q tests/test_commands.py tests/test_services.py`

---

### Task 4: Replace README with the proposed shorter version, but add blunt safety warnings

**Objective:** Swap the aspirational README for the shorter truthful one, without pretending the remaining deferred hardening work is done.

**Files:**
- Modify: `README.md`

**Required behavior:**
- replace the long architecture-heavy README with the shorter proposed structure
- add explicit trusted-local / not-publicly-hardened warning near the top or safety section
- mention the still-open hardening areas honestly: auth/public exposure, durable logs/jobs, remaining production-hardening gaps
- keep CLI examples truthful to the live repo

**Verification commands:**
- `python -m dev_workspace_mcp.app describe`
- manual README read-through for truthfulness against live repo

---

## Parent-side review sequence

After implementation lands:

1. run targeted test nodes for each task
2. run `python -m pytest -q`
3. run `python -m dev_workspace_mcp.app describe`
4. inspect `git diff --stat`
5. dispatch independent review subagents:
   - review A: spec compliance against this plan/tracker only
   - review B: code quality / regression risk on touched files only
6. if reviews find issues, fix narrowly and rerun proofs

---

## Final acceptance criteria

This wave is done only if all of these are true:

- state-doc symlink escape tests exist and pass
- unsafe public bind is blocked unless explicitly overridden
- unsafe bind emits a warning when explicitly allowed
- origin filtering is in place for the HTTP transport
- command output retention is bounded
- service log retention is bounded
- README is shorter and more truthful than the current one
- `python -m pytest -q` passes
- `python -m dev_workspace_mcp.app describe` still works

If any of those are false, the wave is not done.
