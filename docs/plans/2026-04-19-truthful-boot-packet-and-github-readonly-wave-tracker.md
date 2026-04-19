# Dev Workspace MCP Truthful Boot Packet + Read-Only GitHub Surface — Wave Tracker

## Scope

This tracker fences the next delegated wave after the persistent memory slice.

Canonical plan:
- `docs/plans/2026-04-19-truthful-boot-packet-and-github-readonly-implementation-plan.md`

This is the execution artifact for the next session. Older peer-review Wave 4 boot-packet notes are background context only.

---

## Repo checkpoint at tracker creation

Verified at creation time:
- date: `2026-04-19 12:38:03 BST`
- branch: `main`
- `HEAD = 5bf469a`
- branch state: `main...origin/main [ahead 2]`
- pre-existing dirt:
  - untracked `.hermes/`

Known current baseline:
- `python -m pytest -q` passes
- `python -m ruff check .` passes

---

## Wave objective

Land the smallest honest follow-up after the memory-index wave:
1. make `project_snapshot` compact and public-facing instead of leaking internal project record shape
2. stop reporting a fake active watcher backend
3. refresh README/docs to match live repo state
4. add a narrow read-only GitHub surface resolved from project remotes

---

## Explicitly in scope

### Track A — truthfulness reset
- snapshot public contract slimming
- watcher honesty fix
- README/docs truthfulness refresh

### Track B — read-only GitHub surface
- resolve `owner/repo` from project git remote
- repo read
- issue read/search
- PR read/files
- structured GitHub/auth/remote errors

---

## Explicitly deferred

Not in this wave:
- GitHub write tools
- GitHub Actions runs/logs tools
- durable jobs/logs across restarts
- public/hosted auth
- real filesystem watcher backend
- full CLI parity for the new GitHub tools

If implementation drifts into those lanes, stop and cut scope back down.

---

## Parent-owned seams

These are contract-defining / high-risk seam files for this wave:
- `dev_workspace_mcp/models/projects.py`
- `dev_workspace_mcp/codegraph/models.py`
- `dev_workspace_mcp/codegraph/service.py`
- `dev_workspace_mcp/models/errors.py`
- `dev_workspace_mcp/mcp_server/tool_registry.py`
- `dev_workspace_mcp/runtime.py`

Parent owns:
- public snapshot shape
- watcher status semantics
- GitHub tool names
- GitHub error semantics
- project-remote resolution policy

---

## Delegated file fence

### Task Group 1 — snapshot contract reset
Child may modify only:
- `dev_workspace_mcp/models/projects.py`
- `dev_workspace_mcp/projects/snapshots.py`
- `tests/test_project_snapshot.py`
- `tests/test_transport_http.py` only if snapshot/transport expectations require it

### Task Group 2 — watcher honesty
Child may modify only:
- `dev_workspace_mcp/codegraph/models.py`
- `dev_workspace_mcp/codegraph/watcher_manager.py`
- `dev_workspace_mcp/codegraph/service.py`
- `dev_workspace_mcp/projects/snapshots.py`
- `tests/test_project_snapshot.py`
- optional only if needed: `tests/test_codegraph_tools.py`

### Task Group 3 — README/docs truthfulness
Child may modify only:
- `README.md`
- `docs/plans/2026-04-18-peer-review-wave-tracker.md`

### Task Group 4 — GitHub foundation
Child may modify only:
- `dev_workspace_mcp/models/errors.py`
- `dev_workspace_mcp/gittools/service.py` (optional, if remote parsing belongs here)
- `dev_workspace_mcp/models/github.py`
- `dev_workspace_mcp/github_tools/__init__.py`
- `dev_workspace_mcp/github_tools/service.py`
- `tests/test_gittools.py`
- `tests/test_github_tools.py`

### Task Group 5 — GitHub MCP wiring
Child may modify only:
- `dev_workspace_mcp/runtime.py`
- `dev_workspace_mcp/mcp_server/tool_registry.py`
- `tests/test_mcp_server.py`
- `tests/test_transport_http.py`
- `tests/test_github_tools.py`

---

## Sequencing rules

- Task Groups 1 and 2 both touch snapshot/watcher contract files and must run in one lane, not in parallel.
- Task Group 3 can run after the parent freezes the truthfulness language for the wave.
- Task Groups 4 and 5 should stay in one lane because they share the public GitHub tool contract.
- Do not let children redefine tool names or watcher semantics mid-wave.

---

## Required proofs

### Snapshot contract
- no absolute `root_path` / `manifest_path` leakage in `project_snapshot`
- public snapshot header is compact
- relative path fields stay relative

### Watcher honesty
- no fake active watcher when no real backend exists
- snapshot capability text matches real runtime behavior

### Docs truthfulness
- README no longer claims memory search is absent
- README still honestly calls out missing GitHub writes / no real watcher backend / deferred durable jobs/logs
- old peer-review Wave 4 note is demoted from “next thing to execute” status

### GitHub foundation
- HTTPS + SSH GitHub origin parsing works
- missing/non-GitHub origin returns structured error
- repo/issues/PR reads stay read-only

### Tool/transport proof
- new GitHub tools appear in registry + HTTP transport enumeration
- tool success/error envelopes are stable

---

## Verification commands

Parent must rerun:
```bash
python -m pytest -q tests/test_project_snapshot.py tests/test_transport_http.py
python -m pytest -q tests/test_gittools.py tests/test_github_tools.py tests/test_mcp_server.py
python -m pytest -q
python -m ruff check .
python -m dev_workspace_mcp.app describe
```

Manual parent smoke should also cover:
- `project_snapshot`
- `github_repo`
- one GitHub issue/PR read path
- one missing/non-GitHub remote error path

---

## Verdict log

### Task Group 1 — snapshot contract reset
- Status: PASS
- Notes:
  - `project_snapshot.data.project` is now a compact public header (`project_id`, `display_name`, `aliases`, `manifest_present`)
  - no `root_path`, `manifest_path`, raw manifest, or raw policy leak under `data.project`

### Task Group 2 — watcher honesty
- Status: PASS
- Notes:
  - `watcher_health` no longer mutates state on read
  - watcher responses use honest `not_configured` / `configured` / `indexed` semantics with `active=false`
  - watched-path safety is still enforced on read paths

### Task Group 3 — README/docs truthfulness
- Status: PASS
- Notes:
  - README now reflects shipped memory-index support and the new read-only GitHub surface
  - old 2026-04-18 Wave 4 boot-packet direction is demoted to historical/background context

### Task Group 4 — GitHub foundation
- Status: PASS
- Notes:
  - GitHub owner/repo resolves from `origin`
  - HTTPS / SSH GitHub remote formats are covered
  - missing/non-GitHub origin returns `GITHUB_REMOTE_NOT_CONFIGURED`

### Task Group 5 — GitHub MCP wiring
- Status: PASS
- Notes:
  - registry/transport expose `github_repo`, `github_issue_read`, `github_issue_search`, `github_pr_read`, `github_pr_files`
  - handlers validate inputs with pydantic request models and return stable envelopes
