# Dev Workspace MCP Peer Review Wave Tracker

## Scope

This tracker is the current-wave execution fence for the peer-review implementation program.

Canonical architecture/source plan:
- `.hermes/plans/2026-04-18_125142-dev-workspace-mcp-peer-review-implementation-plan.md`

Execution status note:
- Waves 1-4 in this tracker are historical/background only.
- In particular, the old Wave 4 boot-packet direction below is **not** the active execution artifact anymore.
- Use the current 2026-04-19 execution pair instead:
  - `docs/plans/2026-04-19-truthful-boot-packet-and-github-readonly-implementation-plan.md`
  - `docs/plans/2026-04-19-truthful-boot-packet-and-github-readonly-wave-tracker.md`

This tracker is narrower than the broad plan. If a wave needs additional files, the parent agent must amend this tracker before delegating.

## Current repo state at wave start

Verified at start of execution:
- branch: `main`
- status: `main...origin/main`
- pre-existing dirtiness: untracked `.hermes/` only
- baseline tests: `python -m pytest -q` passed

## Wave 1 goal

Centralize real path resolution and containment checks so project-scoped file/cwd/index paths cannot escape the project root through lexical tricks or symlinks.

## Wave 1 parent-owned seam

These files define the contract and are parent-owned for Wave 1:
- `dev_workspace_mcp/shared/paths.py`
- `dev_workspace_mcp/models/errors.py`

Parent owns:
- resolver function shape
- outside-project / symlink-denied error semantics
- exported helper names

## Wave 1 delegated file fence

Implementation child may modify only these files unless the tracker is amended first:
- `dev_workspace_mcp/files/service.py`
- `dev_workspace_mcp/commands/service.py`
- `dev_workspace_mcp/probes/service.py`
- `dev_workspace_mcp/services/manager.py`
- `dev_workspace_mcp/codegraph/index_manager.py`
- `dev_workspace_mcp/codegraph/adapters.py`
- `tests/test_files.py`
- `tests/test_commands.py`
- `tests/test_services.py`
- `tests/test_http_and_probes.py`

Optional delegated additions only if genuinely required by tests and still in-scope:
- one targeted new test file under `tests/` for shared path resolver coverage

## Wave 1 seam notes

- `files/validation.py` remains lexical-only for public relative-path normalization in this wave; the real trust boundary moves to `shared/paths.py` post-resolution containment.
- `gittools/service.py` is intentionally deferred. It still uses lexical path validation today, but git path hardening is out of Wave 1 fence and belongs to a later policy/risk wave unless parent amends scope.
- `http_tools/local_client.py` is also deferred for Wave 1; network restriction work belongs to Wave 2.
- `services/manager.py` currently resolves cwd without shared helper use; Wave 1 must route it through the central resolver.

## Wave 1 required proofs

At minimum the wave must prove:
1. symlink to file outside project is denied
2. symlink to directory outside project is denied for project-scoped file operations
3. command cwd symlink escape is denied
4. service cwd symlink escape is denied
5. safe creation with missing leaf under an in-project parent still works

## Wave 1 verification commands

Parent must rerun:
- `python -m pytest -q`

If targeted nodes are added during the wave, also run the exact targeted tests before the full suite.

## Wave 2 goal

Replace coarse executable-name trust with project policy, bounded subprocess environment construction, and policy-aware local network checks. Wave 2 is still a safety wave, not a CLI/search/GitHub wave.

## Wave 2 parent-owned seam

These files define the Wave 2 contract and are parent-owned:
- `dev_workspace_mcp/models/errors.py`
- `dev_workspace_mcp/models/projects.py`
- `dev_workspace_mcp/projects/registry.py`
- `dev_workspace_mcp/policy/__init__.py`
- `dev_workspace_mcp/policy/models.py`
- `dev_workspace_mcp/policy/service.py`
- `dev_workspace_mcp/policy/env.py`

Parent owns:
- policy schema and defaults
- policy loader path and error semantics
- env-builder contract
- `ProjectRecord` / `ProjectSnapshot` policy fields

## Wave 2 delegated file fence

Implementation child may modify only these files unless the tracker is amended first:
- `dev_workspace_mcp/config.py`
- `dev_workspace_mcp/shared/security.py`
- `dev_workspace_mcp/commands/allowlist.py`
- `dev_workspace_mcp/commands/service.py`
- `dev_workspace_mcp/probes/service.py`
- `dev_workspace_mcp/services/manager.py`
- `dev_workspace_mcp/services/health.py`
- `dev_workspace_mcp/http_tools/local_client.py`
- `dev_workspace_mcp/projects/snapshots.py`
- `tests/test_commands.py`
- `tests/test_http_and_probes.py`
- `tests/test_services.py`
- `tests/test_project_snapshot.py`
- `tests/test_config.py`
- optional: one new targeted test file under `tests/` if genuinely required for policy parsing or env builder behavior

## Wave 2 seam notes

- `.devworkspace/policy.yaml` is the source of truth for project execution/network/env policy. Do not repurpose `.devworkspace.yaml` for this wave.
- Existing `CommandAllowlist` may remain as a narrow fallback or helper, but Wave 2 behavior must be policy-aware at runtime using `project.policy`.
- `build_subprocess_env(...)` in `dev_workspace_mcp/policy/env.py` is the contract for subprocess environment construction; children must use it instead of ad-hoc `os.environ.copy()` behavior.
- `shared/security.py` is allowed to grow better redaction helpers, but do not invent a second env-builder there.
- `http_request` and service health checks should stay local-first by default and deny non-local/non-allowed destinations unless policy explicitly permits them.

## Wave 2 required proofs

At minimum the wave must prove:
1. missing `.devworkspace/policy.yaml` yields safe defaults
2. malformed policy returns a structured `POLICY_INVALID` error during project load/refresh
3. subprocess execution does not inherit arbitrary secret env vars by default
4. allowed env vars survive into subprocesses
5. denied argv combinations are rejected cleanly under project policy
6. non-local or non-allowed HTTP/health destinations are denied unless policy permits them
7. `project_snapshot` exposes effective policy summary

## Wave 2 verification commands

Parent must rerun:
- targeted policy/env/network tests for the final changed nodes
- `python -m pytest -q`

## Wave 3 goal

Extract a real shared runtime/service container, add stdio MCP transport, and land the smallest honest CLI parity slice without duplicating business logic or going over HTTP to talk to ourselves.

## Wave 3 parent-owned seam

These files define the Wave 3 contract and are parent-owned:
- `dev_workspace_mcp/runtime.py`
- `dev_workspace_mcp/mcp_server/server.py`
- `dev_workspace_mcp/mcp_server/transport_stdio.py`
- `dev_workspace_mcp/mcp_server/tool_registry.py`

Parent owns:
- runtime/service-container shape
- compatibility expectation that `build_tool_registry(project_registry)` still works for existing tests/callers
- stdio transport entrypoint contract
- server/runtime relationship

## Wave 3 delegated file fence

Implementation child may modify only these files unless the tracker is amended first:
- `dev_workspace_mcp/app.py`
- `pyproject.toml`
- `dev_workspace_mcp/cli/__init__.py`
- `dev_workspace_mcp/cli/main.py`
- `dev_workspace_mcp/cli/json_output.py`
- `tests/test_app.py`
- `tests/test_transport_http.py`
- `tests/test_transport_stdio.py`
- `tests/test_cli.py`

## Wave 3 seam notes

- top-level command contract for this wave is:
  - `describe`
  - `serve-http`
  - `stdio`
  - `cli ...`
- Wave 3 CLI parity slice is limited to:
  - `projects`
  - `snapshot`
  - `read`
  - `run`
  - `git status`
  - `memory read`
  - `memory patch`
- `--json` must be supported and stable for the CLI commands in scope
- CLI must run in-process against the runtime/tool/service layer; do not implement it by making localhost HTTP calls back into the MCP server
- keep scope out of Wave 4 snapshot expansion; only expose what already exists cleanly in Wave 3

## Wave 3 required proofs

At minimum the wave must prove:
1. existing `describe` and `serve-http` behavior still works
2. `dev-workspace-mcp stdio` boots the MCP server via FastMCP stdio transport
3. CLI JSON commands work for the scoped slice
4. CLI results match MCP/tool-layer behavior for the same inputs
5. the runtime extraction did not break current MCP transport tests

## Wave 3 verification commands

Parent must rerun:
- targeted app/transport/cli tests for the final changed nodes
- `python -m pytest -q`
- smoke:
  - `python -m dev_workspace_mcp.app describe`
  - `python -m dev_workspace_mcp.app stdio` (or equivalent non-hanging boot smoke suitable for tests)

## Wave 4 goal

Upgrade `project_snapshot` from a light summary into an honest boot packet that tells an agent what stack it is in, what repo-local guidance/state exists, what services/presets are worth caring about, and which tool lanes are real versus still future work.

## Wave 4 parent-owned seam

These files define the Wave 4 contract and are parent-owned:
- `dev_workspace_mcp/models/projects.py`
- `dev_workspace_mcp/mcp_server/tool_registry.py`

Parent owns:
- expanded snapshot model shape
- whether snapshot gets live service runtime/health via the already-built runtime service manager
- the exact top-level field names for stack/guidance/task/tool/capability boot context

## Wave 4 delegated file fence

Implementation child may modify only these files unless the tracker is amended first:
- `dev_workspace_mcp/projects/snapshots.py`
- `tests/test_project_snapshot.py`

Optional delegated additions only if genuinely required and still in-scope:
- `dev_workspace_mcp/state_docs/service.py`
- `tests/test_cli.py` (only if snapshot shape changes require CLI snapshot assertions to be normalized)

## Wave 4 seam notes

- Derive from existing repo-local sources first: manifest, git, `AGENTS.md`, `.devworkspace/memory.md`, `.devworkspace/tasks.md`, declared services/probes/presets, and current tool surface.
- Be honest about watcher reality: snapshot-backed semantic index exists, but the watcher manager is still a stub and must not be described as a real filesystem watcher.
- Do not drag SQLite/search/activity/GitHub implementation into this wave.
- If service runtime/health is included, thread the existing runtime `ServiceManager` through snapshot wiring instead of constructing a fresh manager that forgets live state.

## Wave 4 required proofs

At minimum the wave must prove:
1. `project_snapshot` returns richer stack / guidance / task / capability fields from current repo-local sources
2. service summaries are more useful than mere manifest names and stay honest about runtime/health
3. snapshot does not overclaim search/GitHub/real watcher capabilities
4. targeted snapshot tests pass
5. full suite still passes

## Wave 4 verification commands

Parent must rerun:
- `python -m pytest -q tests/test_project_snapshot.py`
- `python -m pytest -q`

## Wave verdict log

### Wave 1
- Status: PASS
- Parent notes:
  - parent locked the resolver/error seam first in:
    - `dev_workspace_mcp/shared/paths.py`
    - `dev_workspace_mcp/models/errors.py`
  - delegated implementation stayed inside the frozen fence and used one allowed extra targeted test file:
    - `tests/test_codegraph_path_safety.py`
  - first spec review verdict: `PASS`
  - first test/quality review verdict: `REQUEST_CHANGES`
  - requested change was valid: destructive mutation paths (`apply_patch`, `move_path`, `delete_path`) needed explicit negative tests for symlink escape
  - parent patched `tests/test_files.py` to add:
    - `test_apply_patch_denies_symlink_source_escape`
    - `test_move_path_denies_symlink_source_escape`
    - `test_delete_path_denies_symlink_source_escape`
  - re-review verdict after fix: `APPROVED`
  - parent verification succeeded:
    - `python -m pytest -q tests/test_files.py::test_apply_patch_denies_symlink_source_escape tests/test_files.py::test_move_path_denies_symlink_source_escape tests/test_files.py::test_delete_path_denies_symlink_source_escape`
    - `python -m pytest -q`
  - current Wave 1 changed files:
    - `dev_workspace_mcp/shared/paths.py`
    - `dev_workspace_mcp/models/errors.py`
    - `dev_workspace_mcp/files/service.py`
    - `dev_workspace_mcp/commands/service.py`
    - `dev_workspace_mcp/probes/service.py`
    - `dev_workspace_mcp/services/manager.py`
    - `dev_workspace_mcp/codegraph/index_manager.py`
    - `dev_workspace_mcp/codegraph/adapters.py`
    - `tests/test_files.py`
    - `tests/test_commands.py`
    - `tests/test_services.py`
    - `tests/test_http_and_probes.py`
    - `tests/test_codegraph_path_safety.py`

### Wave 2
- Status: PASS
- Parent notes:
  - parent froze the policy/env/network seam first in:
    - `dev_workspace_mcp/models/errors.py`
    - `dev_workspace_mcp/models/projects.py`
    - `dev_workspace_mcp/projects/registry.py`
    - `dev_workspace_mcp/policy/__init__.py`
    - `dev_workspace_mcp/policy/models.py`
    - `dev_workspace_mcp/policy/service.py`
    - `dev_workspace_mcp/policy/env.py`
  - delegated implementation stayed inside the frozen fence for the main pass
  - one parent-approved follow-up seam amendment was required:
    - `dev_workspace_mcp/mcp_server/tool_registry.py`
    - reason: pass `project.policy.network` explicitly into `http_request` and remove the brittle caller-frame inference from `LocalHttpClient`
  - first spec review verdict: `PASS`
  - first test/quality review verdict: `REQUEST_CHANGES`
  - requested change was valid: explicit subprocess env overrides could bypass `env.allow`
  - parent fixed the bypass in `dev_workspace_mcp/policy/env.py` and added regression coverage in `tests/test_commands.py`
  - re-review verdict after fix: `APPROVED`
  - parent verification succeeded:
    - `python -m pytest -q tests/test_commands.py::test_run_command_filters_explicit_env_overrides_through_policy`
    - `python -m pytest -q tests/test_commands.py tests/test_http_and_probes.py tests/test_services.py tests/test_project_snapshot.py tests/test_config.py`
    - `python -m pytest -q`
  - current Wave 2 changed files:
    - `dev_workspace_mcp/models/errors.py`
    - `dev_workspace_mcp/models/projects.py`
    - `dev_workspace_mcp/projects/registry.py`
    - `dev_workspace_mcp/policy/__init__.py`
    - `dev_workspace_mcp/policy/models.py`
    - `dev_workspace_mcp/policy/service.py`
    - `dev_workspace_mcp/policy/env.py`
    - `dev_workspace_mcp/config.py`
    - `dev_workspace_mcp/shared/security.py`
    - `dev_workspace_mcp/commands/allowlist.py`
    - `dev_workspace_mcp/commands/service.py`
    - `dev_workspace_mcp/probes/service.py`
    - `dev_workspace_mcp/services/manager.py`
    - `dev_workspace_mcp/services/health.py`
    - `dev_workspace_mcp/http_tools/local_client.py`
    - `dev_workspace_mcp/projects/snapshots.py`
    - `dev_workspace_mcp/mcp_server/tool_registry.py`
    - `tests/test_commands.py`
    - `tests/test_http_and_probes.py`
    - `tests/test_services.py`
    - `tests/test_project_snapshot.py`
    - `tests/test_config.py`

### Wave 3
- Status: PASS
- Parent notes:
  - parent froze the runtime/container/std.io seam first in:
    - `dev_workspace_mcp/runtime.py`
    - `dev_workspace_mcp/mcp_server/server.py`
    - `dev_workspace_mcp/mcp_server/transport_stdio.py`
    - `dev_workspace_mcp/mcp_server/tool_registry.py`
  - delegated implementation stayed inside the frozen fence
  - first spec review verdict: `PASS`
  - first test/quality review verdict: `REQUEST_CHANGES`
  - requested changes were valid:
    - `--json` needed to be honest rather than a no-op
    - stdio proof needed to build a real FastMCP server instead of only a stub wrapper
    - touched files needed to pass Ruff
  - parent fixed the slice by:
    - making compact JSON the default CLI output and `--json` the pretty-print flag in `dev_workspace_mcp/cli/json_output.py` and `dev_workspace_mcp/cli/main.py`
    - strengthening `tests/test_transport_stdio.py` to build a real server and intercept `FastMCP.run_stdio_async`
    - cleaning touched files to pass Ruff
  - re-review verdict after fix: `APPROVED`
  - parent verification succeeded:
    - `python -m ruff check dev_workspace_mcp/app.py dev_workspace_mcp/runtime.py dev_workspace_mcp/mcp_server/server.py dev_workspace_mcp/mcp_server/tool_registry.py dev_workspace_mcp/mcp_server/transport_stdio.py dev_workspace_mcp/cli/main.py dev_workspace_mcp/cli/json_output.py tests/test_app.py tests/test_transport_stdio.py tests/test_cli.py`
    - `python -m pytest -q tests/test_app.py tests/test_transport_http.py tests/test_transport_stdio.py tests/test_cli.py`
    - `python -m pytest -q`
    - `python -m dev_workspace_mcp.app describe`
    - `python -m dev_workspace_mcp.app cli projects`
    - `python -m dev_workspace_mcp.app cli --json projects`
    - `python -m dev_workspace_mcp.app stdio < /dev/null`
  - current Wave 3 changed files:
    - `dev_workspace_mcp/runtime.py`
    - `dev_workspace_mcp/mcp_server/server.py`
    - `dev_workspace_mcp/mcp_server/transport_stdio.py`
    - `dev_workspace_mcp/mcp_server/tool_registry.py`
    - `dev_workspace_mcp/app.py`
    - `dev_workspace_mcp/cli/__init__.py`
    - `dev_workspace_mcp/cli/main.py`
    - `dev_workspace_mcp/cli/json_output.py`
    - `tests/test_app.py`
    - `tests/test_transport_stdio.py`
    - `tests/test_cli.py`

### Wave 4
- Status: PASS
- Parent notes:
  - parent froze the snapshot boot-packet seam first in:
    - `dev_workspace_mcp/models/projects.py`
    - `dev_workspace_mcp/mcp_server/tool_registry.py`
  - delegated implementation stayed inside the frozen fence for the main pass:
    - `dev_workspace_mcp/projects/snapshots.py`
    - `tests/test_project_snapshot.py`
  - first spec review verdict: `REQUEST_CHANGES`
  - valid spec gap: `active_tasks` initially summarized the top of `.devworkspace/tasks.md` generically and leaked backlog headings/items instead of the active-task section only
  - first test/quality review verdict: `REQUEST_CHANGES`
  - valid review issues were:
    - missing `ServiceManager` import / Ruff failure in `tool_registry.py`
    - long-line Ruff debt in touched files
    - snapshot should degrade with warnings when watcher refresh or state-doc reads fail
  - parent fixed the slice by:
    - scoping `active_tasks` to the `# Active` section when present
    - making state-doc reads degrade to `STATE_DOC_UNREADABLE` warnings instead of failing the snapshot
    - making watcher refresh degrade to `WATCHER_STATUS_UNAVAILABLE` while keeping the declared watcher snapshot view
    - catching git command process launch failure and keeping `git.is_repo=True` when the repo is clearly git-backed but status cannot be read
    - tightening `recommended_next_tools` so probe-only projects recommend `run_probe` rather than pretending `run_command` is always the right next move
    - capping stack-file scan work and cleaning remaining Ruff debt
  - re-review verdict after fixes: spec `PASS`, quality `APPROVED`
  - parent verification succeeded:
    - `python -m pytest -q tests/test_project_snapshot.py`
    - `python -m ruff check dev_workspace_mcp/projects/snapshots.py tests/test_project_snapshot.py dev_workspace_mcp/models/projects.py dev_workspace_mcp/mcp_server/tool_registry.py`
    - `python -m pytest -q`
  - current Wave 4 changed files:
    - `dev_workspace_mcp/models/projects.py`
    - `dev_workspace_mcp/mcp_server/tool_registry.py`
    - `dev_workspace_mcp/projects/snapshots.py`
    - `tests/test_project_snapshot.py`
