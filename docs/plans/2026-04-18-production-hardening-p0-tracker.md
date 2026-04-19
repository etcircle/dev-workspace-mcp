# Dev Workspace MCP Production Hardening P0 Tracker

## Scope

This tracker is the current-wave execution fence for the production-hardening P0 slice.

Canonical plan:
- `docs/plans/2026-04-18-production-hardening-p0-plan.md`

If a child needs more files than the fence below, amend this tracker first.

## Current repo state at wave start

Verified before execution:
- branch: `main`
- `HEAD == origin/main == e05627e`
- baseline tests: `python -m pytest -q` pass
- pre-existing dirtiness:
  - untracked `.hermes/`
  - untracked `docs/plans/2026-04-18-project-bootstrap-and-connections-handover.md`

## Parent-owned seams

These files define contract/default behavior and should not drift casually across child tasks:
- `dev_workspace_mcp/config.py`
- `dev_workspace_mcp/app.py`
- `dev_workspace_mcp/mcp_server/transport_http.py`

Parent owns:
- unsafe/public bind flag and warning semantics
- HTTP origin-filter shape
- retention defaults exposed through settings

## Delegated task fences

### Task 1 — state-doc path safety

Child may modify only:
- `dev_workspace_mcp/state_docs/service.py`
- `tests/test_state_docs.py`
- optional only if strictly required by testable resolver behavior: `dev_workspace_mcp/shared/paths.py`

### Task 2 — HTTP serve hardening

Child may modify only:
- `dev_workspace_mcp/config.py`
- `dev_workspace_mcp/app.py`
- `dev_workspace_mcp/mcp_server/transport_http.py`
- `tests/test_app.py`
- `tests/test_transport_http.py`

### Task 3 — bounded command/service retention

Child may modify only:
- `dev_workspace_mcp/config.py`
- `dev_workspace_mcp/commands/jobs.py`
- `dev_workspace_mcp/commands/service.py`
- `dev_workspace_mcp/services/logs.py`
- `tests/test_commands.py`
- `tests/test_services.py`

Parent-amended follow-up after review/fix:
- `dev_workspace_mcp/services/manager.py`
- `dev_workspace_mcp/services/health.py`

### Task 4 — README truthfulness reset

Child may modify only:
- `README.md`

## Sequencing rules

- Task 1 can run independently.
- Task 2 and Task 3 both touch `dev_workspace_mcp/config.py` and therefore must **not** run in parallel.
- Task 4 can run in parallel with Task 1 or after Task 2/3; it must not invent feature claims beyond the plan.
- Parent should reconcile `config.py` changes directly if both Task 2 and Task 3 need defaults there.

## Required proofs

### Task 1
- symlinked `.devworkspace` path is denied
- symlinked state-doc file is denied
- normal state-doc read/write/patch still works

### Task 2
- localhost serve path still works
- public bind without override is denied
- public bind with override warns
- unexpected origin is rejected

### Task 3
- command output retention stays bounded under large stdout
- background capture still completes and stores bounded output
- service logs stay bounded under flood conditions

### Task 4
- README describes the live repo honestly
- README includes trusted-local / not-publicly-hardened warning

## Verification commands

Parent must rerun:
- `python -m pytest -q tests/test_state_docs.py`
- `python -m pytest -q tests/test_app.py tests/test_transport_http.py`
- `python -m pytest -q tests/test_commands.py tests/test_services.py`
- `python -m pytest -q`
- `python -m dev_workspace_mcp.app describe`

## Deferred items for later wave

Valid but intentionally deferred:
- durable job/log persistence across restarts
- token/bearer auth for remote HTTP exposure
- port/service-scoped localhost HTTP restrictions
- writable-roots enforcement
- broader secret redaction patterns
- identifier validation

## Verdict log

### Task 1 — state-doc path safety
- Status: PASS
- Parent notes:
  - `dev_workspace_mcp/state_docs/service.py` now resolves state-doc paths via `resolve_project_path(..., forbid_symlinks=True)` with `allow_missing_leaf=True` for write/patch.
  - `tests/test_state_docs.py` covers symlinked `.devworkspace` denial, symlinked state-doc file denial, and normal read/write/patch behavior.

### Task 2 — HTTP serve hardening
- Status: PASS
- Parent notes:
  - `serve-http` now rejects non-local binds unless `--allow-public-bind` is explicitly passed.
  - explicit public bind prints a loud warning.
  - HTTP transport now rejects unexpected `Origin` headers before the tool layer.

### Task 3 — bounded command/service retention
- Status: PASS
- Parent notes:
  - command output retention is globally bounded in `InMemoryJobStore`.
  - foreground command capture no longer relies on `capture_output=True`.
  - service logs are byte-bounded and preserve line integrity while still exposing in-flight partial lines.
  - follow-up fixes also hardened missing-executable failure handling in command/service paths and health-command degradation.

### Task 4 — README truthfulness reset
- Status: PASS
- Parent notes:
  - `README.md` now uses the shorter proposed structure.
  - it explicitly warns that the repo is trusted-local only for now and not publicly hardened.
