# Project Bootstrap + Connections Wave Tracker

## Scope

This tracker is the execution fence for the project bootstrap + direct connections slice.

Canonical source docs:
- `docs/plans/2026-04-18-project-onboarding-and-db-connections.md`
- `docs/plans/2026-04-18-project-bootstrap-and-connections-implementation-plan.md`

This tracker is narrower than the broad plan. If a task needs additional files, the parent agent must amend this tracker before delegating.

## Current repo state at execution start

Verified live before implementation:
- branch: `main`
- status: `main...origin/main`
- pre-existing dirtiness: untracked `.hermes/` plus untracked planning docs under `docs/plans/`
- baseline tests: `python -m pytest -q` passed

## Frozen contract decisions

### Tool names
- `bootstrap_project`
- `list_connections`
- `configure_connection`
- `test_connection`

### CLI shape
- `python -m dev_workspace_mcp.app cli bootstrap create <folder_name> ...`
- `python -m dev_workspace_mcp.app cli bootstrap clone <repo_url> ...`
- `python -m dev_workspace_mcp.app cli bootstrap import <path> ...`
- `python -m dev_workspace_mcp.app cli connections list <project_id>`
- `python -m dev_workspace_mcp.app cli connections configure <project_id> <connection_name> ...`
- `python -m dev_workspace_mcp.app cli connections test <project_id> <connection_name>`
- repeated env writes use `--env KEY=VALUE`

### Product truth
- this wave supports only `transport: direct`
- `test_connection` proves only env resolution + host/port parsing + TCP reachability
- tracked manifest stores env variable names, never secret values
- local secret/env values live in `.devworkspace/agent.env`
- bootstrap must ensure `.gitignore` contains `.devworkspace/agent.env` exactly once
- `project_id` falls back to the same folder-name-derived rule the registry already uses; no bootstrap-only slugifier

## Task 1 parent-owned seam

These files are parent-owned and frozen before delegation:
- `dev_workspace_mcp/models/errors.py`
- `dev_workspace_mcp/models/projects.py`
- `dev_workspace_mcp/models/project_bootstrap.py`
- `dev_workspace_mcp/models/connections.py`
- `tests/test_project_bootstrap.py`
- `tests/test_connections.py`

Parent owns:
- bootstrap request/response model shape
- connection profile schema and direct-only transport contract
- manifest `connections` field shape
- bootstrap/connection error codes

## Delegated file fences

### Task 2 — manifest write + env helpers
- `dev_workspace_mcp/projects/manifest.py`
- `dev_workspace_mcp/shared/env_files.py`
- `tests/test_project_bootstrap.py`
- `tests/test_connections.py`

### Task 3 — bootstrap service
- `dev_workspace_mcp/projects/bootstrap.py`
- `dev_workspace_mcp/projects/registry.py` *(only if a tiny shared helper seam is truly required)*
- `dev_workspace_mcp/config.py` *(only if a small helper/default is truly required)*
- `tests/test_project_bootstrap.py`
- `tests/test_projects.py`

### Task 4 — connection service
- `dev_workspace_mcp/projects/connections.py`
- `dev_workspace_mcp/projects/manifest.py`
- `dev_workspace_mcp/shared/security.py` *(only if a small redaction fix is actually required)*
- `tests/test_connections.py`
- `tests/test_commands.py` *(only if helper reuse truly touches command-output redaction)*

### Task 5 — runtime + MCP tool wiring
- `dev_workspace_mcp/runtime.py`
- `dev_workspace_mcp/mcp_server/tool_registry.py`
- `dev_workspace_mcp/mcp_server/server.py` *(only if service plumbing genuinely requires it)*
- `tests/test_mcp_server.py`

### Task 6 — CLI parity
- `dev_workspace_mcp/cli/main.py`
- `tests/test_cli.py`

### Task 7 — docs + final proofs
- `README.md`
- proof commands only

## Required proofs

At minimum this slice must prove:
1. bootstrap model and connection model validation are real and stable
2. manifest writes round-trip `connections`
3. `.devworkspace/agent.env` writes are local-only and `.gitignore` handling is idempotent
4. bootstrap create/clone/import makes the project discoverable immediately
5. connection configure/list/test is honest and direct-only
6. MCP tool list and CLI parity are updated exactly
7. full repo tests still pass
8. temp-workspace smoke proves the real onboarding lane end to end

## Verification commands

Parent must personally rerun:
- `python -m pytest -q tests/test_project_bootstrap.py tests/test_connections.py tests/test_projects.py tests/test_mcp_server.py tests/test_cli.py`
- `python -m ruff check .`
- `python -m pytest -q`
- `python -m dev_workspace_mcp.app describe`
- `python -m dev_workspace_mcp.app cli projects`
- temp-workspace bootstrap/configure/list/test smoke

## Verdict log

### Task 1 — parent-owned seam
- Status: PASS
- Notes:
  - parent froze the contract in:
    - `dev_workspace_mcp/models/project_bootstrap.py`
    - `dev_workspace_mcp/models/connections.py`
    - `dev_workspace_mcp/models/projects.py`
    - `dev_workspace_mcp/models/errors.py`
    - `tests/test_project_bootstrap.py`
    - `tests/test_connections.py`
  - first spec review verdict: `PASS`
  - first quality review verdict: `REQUEST_CHANGES`
  - valid review gaps fixed in parent:
    - bootstrap request now rejects mixed-mode payloads
    - connection env refs now require env-variable-style names
    - `ConfigureConnectionRequest.env_updates` keys are validated for env-file follow-on work
    - tests now cover mixed-mode bootstrap payloads, invalid env-name refs, invalid env-update keys, and invalid nested manifest connections
  - re-review verdict after fixes: `APPROVED`
  - parent verification succeeded:
    - `python -m pytest -q tests/test_project_bootstrap.py tests/test_connections.py`
    - `python -m ruff check dev_workspace_mcp/models/project_bootstrap.py dev_workspace_mcp/models/connections.py dev_workspace_mcp/models/projects.py dev_workspace_mcp/models/errors.py tests/test_project_bootstrap.py tests/test_connections.py`

### Task 2 — manifest write + env helpers
- Status: PASS
- Notes:
  - delegated implementation stayed inside the frozen fence:
    - `dev_workspace_mcp/projects/manifest.py`
    - `dev_workspace_mcp/shared/env_files.py`
    - `tests/test_project_bootstrap.py`
    - `tests/test_connections.py`
  - first spec review verdict: `PASS`
  - first quality review verdict: `REQUEST_CHANGES`
  - valid review gaps fixed in parent:
    - consolidated atomic text writes behind shared `write_text_atomic`
    - `.gitignore` handling now preserves the first existing entry position instead of moving it to EOF
    - tests now cover duplicate env keys and comment/position preservation in `.gitignore`
    - `.gitignore` read/write failures now raise `ENV_FILE_INVALID` instead of leaking raw `OSError`
  - re-review verdict after fixes: `APPROVED`
  - parent verification succeeded:
    - `python -m pytest -q tests/test_project_bootstrap.py tests/test_connections.py`
    - `python -m ruff check dev_workspace_mcp/projects/manifest.py dev_workspace_mcp/shared/env_files.py tests/test_project_bootstrap.py tests/test_connections.py`

### Task 3 — bootstrap service
- Status: PASS
- Notes:
  - delegated implementation stayed inside the frozen fence:
    - `dev_workspace_mcp/projects/bootstrap.py`
    - `tests/test_project_bootstrap.py`
  - first spec review verdict: `PASS`
  - first quality review verdict: `REQUEST_CHANGES`
  - valid review gaps fixed in parent:
    - clone/import now fail before scaffolding on manifest-driven `project_id` conflicts
    - clone conflict cleanup removes the just-cloned directory instead of leaving junk behind
    - bootstrap request now rejects unimplemented `template` values instead of silently accepting a no-op field
    - tests now cover clone/import manifest-conflict cases and no-mutation/no-leftovers behavior
  - re-review verdict after fixes: `APPROVED`
  - parent verification succeeded:
    - `python -m pytest -q tests/test_project_bootstrap.py tests/test_projects.py`
    - `python -m ruff check dev_workspace_mcp/projects/bootstrap.py dev_workspace_mcp/models/project_bootstrap.py tests/test_project_bootstrap.py tests/test_projects.py`

### Task 4 — connection service
- Status: PASS
- Notes:
  - delegated implementation stayed inside the main fence for the first pass:
    - `dev_workspace_mcp/projects/connections.py`
    - `tests/test_connections.py`
  - parent-approved follow-up seam amendment was required:
    - `dev_workspace_mcp/models/connections.py`
    - `dev_workspace_mcp/shared/env_files.py`
    - reason: fix pytest collection gotcha for `TestConnectionRequest` and close real secret-leak / env-file-detail issues discovered in review
  - first spec review verdict: `REQUEST_CHANGES`
  - first quality review verdict: `REQUEST_CHANGES`
  - valid review gaps fixed in parent:
    - strengthened runtime host validation, including malformed URL-like and bad dotted-quad values
    - stopped `test_connection` from reading arbitrary unapproved process env vars by default
    - removed raw secret-bearing env-file lines from `ENV_FILE_INVALID` error details
    - expanded negative coverage for process-env leakage, TCP failure, invalid runtime host values, and non-leak assertions on error surfaces
  - final re-review verdict after fixes: `APPROVED`
  - parent verification succeeded:
    - `python -m pytest -q tests/test_connections.py`
    - `python -m ruff check dev_workspace_mcp/projects/connections.py dev_workspace_mcp/models/connections.py dev_workspace_mcp/shared/env_files.py dev_workspace_mcp/projects/manifest.py tests/test_connections.py`

### Task 5 — runtime + MCP tool wiring
- Status: PASS
- Notes:
  - delegated implementation stayed inside the frozen fence:
    - `dev_workspace_mcp/runtime.py`
    - `dev_workspace_mcp/mcp_server/tool_registry.py`
    - `tests/test_mcp_server.py`
  - `dev_workspace_mcp/mcp_server/server.py` was not needed
  - first spec review verdict: `REQUEST_CHANGES`
  - first quality review verdict: `REQUEST_CHANGES`
  - valid review gaps fixed in parent:
    - request models now forbid unexpected extra fields for bootstrap/connection tool payloads
    - registry argument-shape errors now surface as `VALIDATION_ERROR` instead of fake `INTERNAL_ERROR`
    - tests now cover extra-arg rejection and generic argument-shape validation behavior
  - re-review verdict after fixes: `APPROVED`
  - parent verification succeeded:
    - `python -m pytest -q tests/test_mcp_server.py`
    - `python -m ruff check dev_workspace_mcp/runtime.py dev_workspace_mcp/mcp_server/tool_registry.py dev_workspace_mcp/models/project_bootstrap.py dev_workspace_mcp/models/connections.py tests/test_mcp_server.py`

### Task 6 — CLI parity
- Status: PASS
- Notes:
  - delegated implementation stayed inside the frozen fence:
    - `dev_workspace_mcp/cli/main.py`
    - `tests/test_cli.py`
  - first spec review verdict: `REQUEST_CHANGES`
  - first quality review verdict: `REQUEST_CHANGES`
  - valid review gaps fixed in parent:
    - added bootstrap clone/import parity coverage, not just create
    - fixed `run` parsing so flags after `project_id` in the natural call shape are parsed as CLI flags before command start
    - preserved command argv entries that look like CLI flags once command parsing has started
  - re-review verdict after fixes: `APPROVED`
  - parent verification succeeded:
    - `python -m pytest -q tests/test_cli.py`
    - `python -m ruff check dev_workspace_mcp/cli/main.py tests/test_cli.py`

### Task 7 — docs + final proofs
- Status: PASS
- Notes:
  - delegated implementation updated `README.md` truthfully for bootstrap + direct connection profiles
  - parent final verification succeeded:
    - `python -m ruff check .`
    - `python -m pytest -q tests/test_project_bootstrap.py tests/test_connections.py tests/test_projects.py tests/test_mcp_server.py tests/test_cli.py`
    - `python -m pytest -q`
    - `python -m dev_workspace_mcp.app describe`
    - `python -m dev_workspace_mcp.app cli projects`
    - temp-workspace smoke: bootstrap create + projects + connections configure/list/test all passed with reachable=true and `.devworkspace.yaml`, `.devworkspace/agent.env`, and `.gitignore` verified
  - final integration review found one real merge blocker outside the README itself:
    - `.env.example` used a plain string for `DEV_WORKSPACE_MCP_WORKSPACE_ROOTS` even though `Settings.workspace_roots` is `list[str]` and needs JSON-list syntax
  - parent fixed the blocker by changing `.env.example` to:
    - `DEV_WORKSPACE_MCP_WORKSPACE_ROOTS=["~/dev-workspaces"]`
  - final verdict: `PASS`
