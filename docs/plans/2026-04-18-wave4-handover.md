# Dev Workspace MCP — Wave 4 Handover

**Created:** 2026-04-18 14:41 BST  
**Repo:** `~/dev-workspaces/dev-workspace-mcp`  
**Branch:** `main`  
**Purpose:** continue from the verified post-Wave-3 checkpoint and start **Wave 4** in a new session.

---

## Current checkpoint

Waves **1–3 are complete and PASS**.

### Completed waves
- **Wave 1 — Path safety and symlink containment**
- **Wave 2 — Policy / env isolation / network restrictions**
- **Wave 3 — Shared runtime container / stdio transport / minimal CLI parity**

### Not started yet
- **Wave 4 — Project snapshot expansion / boot-packet upgrade**

### Canonical execution artifacts
- broad implementation plan:  
  `.hermes/plans/2026-04-18_125142-dev-workspace-mcp-peer-review-implementation-plan.md`
- wave-by-wave tracker with fences, verdicts, and parent fixes:  
  `docs/plans/2026-04-18-peer-review-wave-tracker.md`

If you only read one file before continuing, read the **tracker**.

---

## Verified state at handover

These passed in the parent session after Wave 3:

```bash
python -m ruff check dev_workspace_mcp/app.py dev_workspace_mcp/runtime.py dev_workspace_mcp/mcp_server/server.py dev_workspace_mcp/mcp_server/tool_registry.py dev_workspace_mcp/mcp_server/transport_stdio.py dev_workspace_mcp/cli/main.py dev_workspace_mcp/cli/json_output.py tests/test_app.py tests/test_transport_stdio.py tests/test_cli.py
python -m pytest -q tests/test_app.py tests/test_transport_http.py tests/test_transport_stdio.py tests/test_cli.py
python -m pytest -q
python -m dev_workspace_mcp.app describe
python -m dev_workspace_mcp.app cli projects
python -m dev_workspace_mcp.app cli --json projects
python -m dev_workspace_mcp.app stdio < /dev/null
```

### Meaning
- runtime extraction is stable
- stdio transport boots
- minimal CLI slice works
- full pytest suite is green
- Wave 3 touched files are Ruff-clean

---

## Repo state at handover

This is an **intentionally dirty** working tree because Waves 1–3 are implemented but not yet committed.

### Current modified / new files
```text
M  dev_workspace_mcp/app.py
M  dev_workspace_mcp/codegraph/adapters.py
M  dev_workspace_mcp/codegraph/index_manager.py
M  dev_workspace_mcp/commands/allowlist.py
M  dev_workspace_mcp/commands/service.py
M  dev_workspace_mcp/config.py
M  dev_workspace_mcp/files/service.py
M  dev_workspace_mcp/http_tools/local_client.py
M  dev_workspace_mcp/mcp_server/server.py
M  dev_workspace_mcp/mcp_server/tool_registry.py
M  dev_workspace_mcp/models/errors.py
M  dev_workspace_mcp/models/projects.py
M  dev_workspace_mcp/probes/service.py
M  dev_workspace_mcp/projects/registry.py
M  dev_workspace_mcp/projects/snapshots.py
M  dev_workspace_mcp/services/health.py
M  dev_workspace_mcp/services/manager.py
M  dev_workspace_mcp/shared/paths.py
M  dev_workspace_mcp/shared/security.py
M  tests/test_app.py
M  tests/test_commands.py
M  tests/test_config.py
M  tests/test_files.py
M  tests/test_http_and_probes.py
M  tests/test_project_snapshot.py
M  tests/test_services.py
?? dev_workspace_mcp/cli/
?? dev_workspace_mcp/mcp_server/transport_stdio.py
?? dev_workspace_mcp/policy/
?? dev_workspace_mcp/runtime.py
?? tests/test_cli.py
?? tests/test_codegraph_path_safety.py
?? tests/test_transport_stdio.py
```

### Important note
Do **not** start unrelated work from this state. This is a staged remediation/program worktree. Continue the program, don’t mix in random crap.

---

## What Wave 4 should do

### Objective
Turn `project_snapshot` from a light summary into a real **agent boot packet**.

### Current snapshot already includes
- project record
- git summary
- services summary
- watcher summary
- probes
- presets
- state-doc existence / char counts
- policy summary

### Wave 4 should add
As already planned in the main implementation plan:
- languages / frameworks / package managers
- memory summary
- active tasks summary
- better service runtime / health summary
- declared commands / presets worth using
- recommended next tools
- more honest capability-style context without pretending later-wave features already exist

### Strong scope warning
Do **not** turn Wave 4 into search/activity/SQLite work. That belongs later.

Wave 4 should derive from **existing sources first**:
- manifest
- git
- `AGENTS.md`
- `.devworkspace/memory.md`
- `.devworkspace/tasks.md`
- existing services / presets / probes / policy

---

## Recommended Wave 4 starting fence

This fence was **not yet frozen** in the prior session, but this is the sane starting point.

### Parent-owned seam to freeze first
- `dev_workspace_mcp/models/projects.py`

Reason: snapshot shape is the contract. Lock that first before delegating anything.

### Likely delegated Wave 4 files
- `dev_workspace_mcp/projects/snapshots.py`
- `dev_workspace_mcp/state_docs/service.py` *(only if needed for lightweight summary helpers; do not broaden into concurrency yet)*
- `tests/test_project_snapshot.py`
- possibly `tests/test_cli.py` **only if** the CLI snapshot parity tests need normalization updates because the snapshot shape changed

### Keep out of Wave 4 unless strictly necessary
- `dev_workspace_mcp/mcp_server/tool_registry.py`
- `dev_workspace_mcp/cli/main.py`
- any SQLite/search/activity files
- any GitHub files

If `tool_registry.py` ends up needed only because of snapshot response wiring, parent should explicitly amend the tracker before delegation.

---

## Recommended session-open sequence for the next run

1. Read:
   - `docs/plans/2026-04-18-peer-review-wave-tracker.md`
   - `docs/plans/2026-04-18-wave4-handover.md`
   - `.hermes/plans/2026-04-18_125142-dev-workspace-mcp-peer-review-implementation-plan.md`

2. Reconfirm the checkpoint:
```bash
git status --short --branch
python -m pytest -q
```

3. Freeze the exact Wave 4 fence in the tracker before delegation.

4. Use the same execution pattern as Waves 1–3:
   - parent freezes seam
   - implementation subagent
   - spec-review subagent
   - test/quality-review subagent
   - parent reruns proofs and records verdict

---

## Suggested Wave 4 proof lane

At minimum, Wave 4 should prove:
1. `project_snapshot` now includes richer boot-packet fields from current repo-local sources
2. snapshot does **not** overclaim later-wave capabilities
3. snapshot tests cover the new summary fields cleanly
4. full suite still passes

### Expected verification commands
Start with something like:
```bash
python -m pytest -q tests/test_project_snapshot.py
python -m pytest -q
```

Add any more targeted nodes only if the real Wave 4 fence touches them.

---

## Completed-wave caveats worth remembering

### Wave 2
- a real bug existed where explicit subprocess env overrides bypassed `env.allow`
- it was fixed in `dev_workspace_mcp/policy/env.py`
- regression test lives in `tests/test_commands.py`

### Wave 3
- the first CLI/stdio pass was functionally okay but sloppy
- parent had to fix:
  - `--json` being a no-op
  - shallow stdio proof
  - Ruff debt in touched files
- do not regress those when touching snapshot/CLI parity tests later

---

## Bottom line

You are handing off from a **verified post-Wave-3 checkpoint**.

The next sane move is:
1. freeze **Wave 4 snapshot model shape**
2. delegate **Wave 4 snapshot expansion**
3. review + verify exactly like the earlier waves

Do **not** reopen Wave 1–3 unless new evidence shows a regression.
