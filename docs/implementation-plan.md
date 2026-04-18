# Dev Workspace MCP Implementation Plan

> For Hermes: use subagent-driven-development once the repo skeleton exists and the public contract is locked.

## Goal

Build the first working public version of Dev Workspace MCP: a project-aware Streamable HTTP MCP server that lets external coding agents inspect code, patch files, run bounded commands, control declared services, inspect logs, use semantic code intelligence, and maintain repo-local working state.

## Architecture

The server is built around one non-negotiable rule: every project-scoped tool takes `project_id`, and all filesystem or runtime operations resolve through that project record. Semantic code understanding comes from an internal CodeGraph-style subsystem, but the public surface is a new, stable MCP contract.

Runtime features are split into focused modules: projects, codegraph, files, commands, services, state_docs, gittools, probes, and HTTP verification. Each module owns its domain logic and is registered into the MCP layer through a shared result envelope and error model.

## Tech stack

- Python 3.11+
- FastMCP or a similarly modern Python MCP server library with Streamable HTTP support
- Pydantic v2 for schemas and validation
- PyYAML for manifest loading
- GitPython or subprocess-backed git wrapper
- pytest for tests
- Useful CodeGraphAgent internals ported directly into this repo behind the in-process codegraph boundary

## Core implementation rules

- Public tool names must be the new names only.
- Old CodeGraphAgent names stay internal.
- `project_id` is required for all project-scoped tools.
- Relative paths only; no public absolute-path contract.
- Commands use `argv[]`, not raw shell strings, by default.
- Services and probes must be declared in the manifest.
- `.devworkspace/memory.md`, `.devworkspace/roadmap.md`, and `.devworkspace/tasks.md` enforce character limits.
- Every tool returns structured results and stable domain error codes.

---

## Target repository structure

```text
dev-workspace-mcp/
  README.md
  AGENTS.md
  pyproject.toml
  .env.example

  dev_workspace_mcp/
    __init__.py
    app.py
    config.py

    models/
      common.py
      projects.py
      files.py
      commands.py
      services.py
      git.py
      state_docs.py
      errors.py

    mcp_server/
      server.py
      tool_registry.py
      result_envelope.py
      errors.py
      transport_http.py

    projects/
      registry.py
      discovery.py
      manifest.py
      resolver.py
      snapshots.py

    codegraph/
      adapters.py
      index_manager.py
      watcher_manager.py
      models.py

    files/
      service.py
      patching.py
      validation.py

    commands/
      service.py
      jobs.py
      allowlist.py
      presets.py

    services/
      manager.py
      process_store.py
      logs.py
      health.py
      models.py

    state_docs/
      service.py
      parser.py
      limits.py

    gittools/
      service.py

    http_tools/
      local_client.py

    probes/
      service.py

    shared/
      paths.py
      subprocess.py
      time.py
      text.py
      security.py

  tests/
    test_projects.py
    test_project_snapshot.py
    test_files.py
    test_commands.py
    test_services.py
    test_state_docs.py
    test_gittools.py
    test_http_tools.py
    test_codegraph_adapters.py
    test_mcp_server.py
```

---

## Delivery phases

### Phase 0: bootstrap the repository

#### Task 0.1: create initial repo files

**Objective:** Create the minimum repo shell and project metadata.

**Files:**
- Create: `README.md`
- Create: `AGENTS.md`
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `dev_workspace_mcp/__init__.py`

**Implementation notes:**
- `README.md` should stay product-level and architectural.
- `AGENTS.md` should define coding standards, test commands, and implementation rules.
- `pyproject.toml` should define package metadata, Python version, dev dependencies, and test tooling.

**Verification:**
- Repo installs in editable mode.
- `python -m pytest` runs with zero or placeholder tests discovered cleanly.

#### Task 0.2: create package skeleton

**Objective:** Create all module directories so implementation work lands in stable paths immediately.

**Files:**
- Create package directories and `__init__.py` files under every `dev_workspace_mcp/*` module path.
- Create `tests/` package skeleton.

**Verification:**
- `python -c "import dev_workspace_mcp"` succeeds.

---

### Phase 1: core models, config, and result envelope

#### Task 1.1: define shared config

**Objective:** Centralize runtime configuration for workspace roots, HTTP settings, and optional policy switches.

**Files:**
- Create: `dev_workspace_mcp/config.py`

**Implementation details:**
- Define settings for:
  - workspace roots
  - host/port
  - command allowlist mode
  - log retention defaults
  - job output caps
  - state-doc limits
- Use Pydantic settings or equivalent typed config loader.

**Verification:**
- Config can load from environment.
- Defaults are sensible and testable.

#### Task 1.2: define core Pydantic models

**Objective:** Lock the domain model before writing handlers.

**Files:**
- Create: `dev_workspace_mcp/models/common.py`
- Create: `dev_workspace_mcp/models/projects.py`
- Create: `dev_workspace_mcp/models/files.py`
- Create: `dev_workspace_mcp/models/commands.py`
- Create: `dev_workspace_mcp/models/services.py`
- Create: `dev_workspace_mcp/models/git.py`
- Create: `dev_workspace_mcp/models/state_docs.py`
- Create: `dev_workspace_mcp/models/errors.py`

**Implementation details:**
- Define request/response DTOs for all public tools.
- Include `ProjectRecord`, `ServiceDefinition`, `ProbeDefinition`, `PresetDefinition`, `ToolError`, and result summary models.
- Keep models transport-agnostic.

**Verification:**
- Schema generation succeeds.
- Models validate example payloads from the README.

#### Task 1.3: define result envelope and error model

**Objective:** Make every tool return consistent success/error structure.

**Files:**
- Create: `dev_workspace_mcp/mcp_server/result_envelope.py`
- Create: `dev_workspace_mcp/mcp_server/errors.py`

**Implementation details:**
- Define helpers for:
  - success envelope
  - MCP-compatible error envelope
  - stable domain error codes
- Include shared functions to convert exceptions into tool errors.

**Verification:**
- Unit tests prove success and error envelopes serialize predictably.

---

### Phase 2: project registry, discovery, and manifest loading

#### Task 2.1: implement `.devworkspace.yaml` parsing

**Objective:** Parse project metadata and manifest-defined services, probes, presets, aliases, and CodeGraph configuration.

**Files:**
- Create: `dev_workspace_mcp/projects/manifest.py`
- Test: `tests/test_projects.py`

**Implementation details:**
- Validate YAML structure.
- Support optional `project_id` and derived fallback.
- Normalize relative manifest paths.

**Verification:**
- Valid manifest parses into typed models.
- Invalid manifest raises structured validation errors.

#### Task 2.2: implement project discovery

**Objective:** Find candidate projects under configured workspace roots.

**Files:**
- Create: `dev_workspace_mcp/projects/discovery.py`
- Test: `tests/test_projects.py`

**Implementation details:**
- Discover projects by presence of `.devworkspace.yaml`, `.git`, or explicit config registration.
- Collect basic metadata without expensive indexing.

**Verification:**
- Multiple projects under one root are discovered correctly.
- Non-project folders are ignored.

#### Task 2.3: implement project registry and resolver

**Objective:** Resolve `project_id` and aliases into stable `ProjectRecord` objects.

**Files:**
- Create: `dev_workspace_mcp/projects/registry.py`
- Create: `dev_workspace_mcp/projects/resolver.py`
- Test: `tests/test_projects.py`

**Implementation details:**
- Registry owns the canonical in-memory view.
- Resolver handles alias lookup and deterministic errors for missing projects.
- Root path stays server-side only.

**Verification:**
- `project_id` and aliases both resolve.
- Unknown projects raise `PROJECT_NOT_FOUND`.

#### Task 2.4: implement `list_projects`

**Objective:** Ship the first public tool.

**Files:**
- Modify: `dev_workspace_mcp/projects/registry.py`
- Modify: `dev_workspace_mcp/mcp_server/tool_registry.py`
- Test: `tests/test_projects.py`

**Implementation details:**
- Return `project_id`, display name, aliases, manifest presence, services summary, and optional path info.

**Verification:**
- Tool returns predictable structured project summaries.

---

### Phase 3: project snapshot

#### Task 3.1: implement snapshot assembler

**Objective:** Build the high-value first-call summary tool.

**Files:**
- Create: `dev_workspace_mcp/projects/snapshots.py`
- Test: `tests/test_project_snapshot.py`

**Implementation details:**
- Aggregate:
  - project metadata
  - manifest summary
  - git summary
  - service summary
  - watcher summary
  - recent changed files
  - available probes and presets
  - state doc status
  - warnings
- Keep snapshot resilient: partial failures should degrade gracefully with warnings.

**Verification:**
- Snapshot works even if CodeGraph or services are not yet active.
- Warning fields explain partial degradation.

#### Task 3.2: implement `project_snapshot`

**Objective:** Expose snapshot aggregation as the primary starting tool.

**Files:**
- Modify: `dev_workspace_mcp/mcp_server/tool_registry.py`
- Test: `tests/test_project_snapshot.py`

**Verification:**
- Tool output contains all required sections.
- Errors remain structured and stable.

---

### Phase 4: safe file tools

#### Task 4.1: implement path validation helpers

**Objective:** Prevent path traversal and absolute path abuse.

**Files:**
- Create: `dev_workspace_mcp/files/validation.py`
- Create: `dev_workspace_mcp/shared/paths.py`
- Test: `tests/test_files.py`

**Implementation details:**
- Normalize relative paths.
- Reject traversal outside project root.
- Separate path resolution from file IO.

**Verification:**
- `../` traversal attempts fail with `INVALID_RELATIVE_PATH`.

#### Task 4.2: implement file service

**Objective:** Add bounded project-relative reads and writes.

**Files:**
- Create: `dev_workspace_mcp/files/service.py`
- Test: `tests/test_files.py`

**Implementation details:**
- Implement:
  - `list_dir`
  - `read_file`
  - `write_file`
  - `move_path`
  - `delete_path`
- Enforce output truncation and size limits.

**Verification:**
- Reads and writes work inside the project.
- Deletes and moves respect validation rules.

#### Task 4.3: implement patching

**Objective:** Support agent-friendly file mutation without full rewrites every time.

**Files:**
- Create: `dev_workspace_mcp/files/patching.py`
- Modify: `dev_workspace_mcp/files/service.py`
- Test: `tests/test_files.py`

**Implementation details:**
- Implement `apply_patch` for at least unified diff input.
- Return applied diff and validation failures cleanly.

**Verification:**
- Clean patch applies.
- Invalid patch returns structured error information.

---

### Phase 5: commands and jobs

#### Task 5.1: implement subprocess helpers

**Objective:** Centralize bounded subprocess execution.

**Files:**
- Create: `dev_workspace_mcp/shared/subprocess.py`
- Create: `dev_workspace_mcp/shared/time.py`
- Test: `tests/test_commands.py`

**Implementation details:**
- Support timeout handling.
- Capture stdout/stderr separately.
- Provide duration metadata.

**Verification:**
- Foreground command execution behaves predictably under success, failure, and timeout.

#### Task 5.2: implement command allowlist and presets

**Objective:** Avoid turning `run_command` into arbitrary remote shell.

**Files:**
- Create: `dev_workspace_mcp/commands/allowlist.py`
- Create: `dev_workspace_mcp/commands/presets.py`
- Test: `tests/test_commands.py`

**Implementation details:**
- Validate executable names.
- Allow manifest-defined presets.
- Keep shell-string execution out of v1.

**Verification:**
- Allowed commands pass.
- Blocked commands return `COMMAND_NOT_ALLOWED`.

#### Task 5.3: implement jobs store and command service

**Objective:** Add foreground and background command execution.

**Files:**
- Create: `dev_workspace_mcp/commands/jobs.py`
- Create: `dev_workspace_mcp/commands/service.py`
- Test: `tests/test_commands.py`

**Implementation details:**
- Implement:
  - `run_command`
  - `get_job`
  - `cancel_job`
- Background jobs should track status, timestamps, output tails, and exit codes.

**Verification:**
- Foreground and background flows both work.
- Cancelled jobs transition cleanly.

---

### Phase 6: services, logs, and health

#### Task 6.1: define service runtime models

**Objective:** Model service definitions and runtime state separately.

**Files:**
- Create: `dev_workspace_mcp/services/models.py`
- Test: `tests/test_services.py`

**Verification:**
- Models validate manifest definitions and runtime snapshots.

#### Task 6.2: implement process store and log capture

**Objective:** Track long-running development services with identity.

**Files:**
- Create: `dev_workspace_mcp/services/process_store.py`
- Create: `dev_workspace_mcp/services/logs.py`
- Test: `tests/test_services.py`

**Implementation details:**
- Track service instance id, pid, started_at, last_exit_code, restart_count, and in-memory log ring buffer.
- Support append-only on-disk log file later if needed, but at least design for it now.

**Verification:**
- Log tails are captured and retrievable.

#### Task 6.3: implement health checks

**Objective:** Support `http`, `command`, and `none` health types.

**Files:**
- Create: `dev_workspace_mcp/services/health.py`
- Test: `tests/test_services.py`

**Verification:**
- HTTP health checks pass/fail predictably.
- `none` does not break service control.

#### Task 6.4: implement service manager

**Objective:** Add the core runtime control surface.

**Files:**
- Create: `dev_workspace_mcp/services/manager.py`
- Test: `tests/test_services.py`

**Implementation details:**
- Implement:
  - `list_services`
  - `service_status`
  - `start_service`
  - `stop_service`
  - `restart_service`
  - `get_logs`
- Only declared services can be managed.
- `restart_service` should stop, start, wait for health or timeout, then return status.

**Verification:**
- Service lifecycle works end to end on a small dummy app.
- Logs and health data appear in `service_status`.

---

### Phase 7: state documents

#### Task 7.1: implement state-doc limits and parser

**Objective:** Manage `.devworkspace/*.md` safely and predictably.

**Files:**
- Create: `dev_workspace_mcp/state_docs/limits.py`
- Create: `dev_workspace_mcp/state_docs/parser.py`
- Test: `tests/test_state_docs.py`

**Implementation details:**
- Enforce size limits:
  - memory: 4000
  - roadmap: 8000
  - tasks: 8000
- Parse markdown headings into section summaries for patch updates.

**Verification:**
- Oversize content returns `STATE_DOC_LIMIT_EXCEEDED`.
- Section parsing behaves predictably.

#### Task 7.2: implement state-doc service

**Objective:** Add the repo-local cross-session state contract.

**Files:**
- Create: `dev_workspace_mcp/state_docs/service.py`
- Test: `tests/test_state_docs.py`

**Implementation details:**
- Implement:
  - `read_state_doc`
  - `write_state_doc`
  - `patch_state_doc`
- Preserve existing content outside patched sections.

**Verification:**
- Reads return raw markdown, parsed sections, char counts, and timestamps.
- Section patching does not destroy unrelated content.

---

### Phase 8: semantic code tools

#### Task 8.1: extract or vendor the CodeGraph layer

**Objective:** Bring semantic code understanding into the new repo without making old repo structure the new public boundary.

**Files:**
- Create: `dev_workspace_mcp/codegraph/models.py`
- Create: `dev_workspace_mcp/codegraph/index_manager.py`
- Create: `dev_workspace_mcp/codegraph/watcher_manager.py`
- Create: `dev_workspace_mcp/codegraph/adapters.py`
- Test: `tests/test_codegraph_adapters.py`

**Implementation details:**
- Reuse the minimum viable subset from CodeGraphAgent.
- Keep transport, naming, and tool result formatting local to the new repo.
- Key everything by `project_id`.

**Verification:**
- Semantic tools return stable structured results.
- Watcher state can be queried independently.

#### Task 8.2: expose semantic public tools

**Objective:** Ship the code-understanding layer behind the new names.

**Files:**
- Modify: `dev_workspace_mcp/mcp_server/tool_registry.py`
- Test: `tests/test_codegraph_adapters.py`

**Implementation details:**
- Implement public tool registration for:
  - `module_overview`
  - `function_context`
  - `grep`
  - `find_references`
  - `read_source`
  - `recent_changes`
  - `call_path`
  - `watcher_health`

**Verification:**
- Old internal names are not exposed publicly.

---

### Phase 9: git, probes, and local HTTP verification

#### Task 9.1: implement git service

**Objective:** Keep common git actions first-class and structured.

**Files:**
- Create: `dev_workspace_mcp/gittools/service.py`
- Test: `tests/test_gittools.py`

**Implementation details:**
- Implement:
  - `git_status`
  - `git_diff`
  - `git_checkout`
  - `git_commit`

**Verification:**
- Commands work against a temp git repo fixture.

#### Task 9.2: implement local HTTP client

**Objective:** Verify backend and frontend state without dragging in full browser automation.

**Files:**
- Create: `dev_workspace_mcp/http_tools/local_client.py`
- Test: `tests/test_http_tools.py`

**Implementation details:**
- Implement `http_request` with timeout, headers, body, truncation, and latency capture.

**Verification:**
- Requests to a local test server succeed and fail predictably.

#### Task 9.3: implement probes service

**Objective:** Run named diagnostics from the manifest under a safe contract.

**Files:**
- Create: `dev_workspace_mcp/probes/service.py`
- Test: `tests/test_http_tools.py`

**Implementation details:**
- Implement:
  - `list_probes`
  - `run_probe`
- Probes must come from manifest declarations.

**Verification:**
- Declared probes run.
- Unknown probes return `PROBE_NOT_DECLARED` or equivalent.

---

### Phase 10: MCP server bootstrap and HTTP transport

#### Task 10.1: implement MCP tool registry

**Objective:** Centralize public tool registration and schema ownership.

**Files:**
- Create: `dev_workspace_mcp/mcp_server/tool_registry.py`
- Test: `tests/test_mcp_server.py`

**Implementation details:**
- Register every public tool exactly once.
- Keep schema definitions close to transport-facing wrappers.

**Verification:**
- Tool list matches the public contract and does not leak internal names.

#### Task 10.2: implement server bootstrap

**Objective:** Wire all services together into a runnable app.

**Files:**
- Create: `dev_workspace_mcp/mcp_server/server.py`
- Create: `dev_workspace_mcp/app.py`
- Test: `tests/test_mcp_server.py`

**Implementation details:**
- Compose config, registry, services, and tool wrappers.
- Initialize project registry on startup.

**Verification:**
- App boots locally and exposes tools.

#### Task 10.3: implement Streamable HTTP transport

**Objective:** Expose the server through the intended remote contract.

**Files:**
- Create: `dev_workspace_mcp/mcp_server/transport_http.py`
- Test: `tests/test_mcp_server.py`

**Implementation details:**
- Add HTTP entrypoint and session handling as required by the chosen MCP library.
- Keep transport concerns out of domain modules.

**Verification:**
- MCP client can connect over Streamable HTTP and invoke tools successfully.

---

### Phase 11: end-to-end verification and hardening

#### Task 11.1: add fixture projects

**Objective:** Test against realistic mini-repos instead of fake unit-only abstractions.

**Files:**
- Create: `tests/fixtures/mini_backend_project/...`
- Create: `tests/fixtures/mini_fullstack_project/...`

**Verification:**
- Fixture projects support service, file, and command tests.

#### Task 11.2: add end-to-end tests

**Objective:** Verify the intended agent workflow actually works.

**Files:**
- Modify: `tests/test_mcp_server.py`
- Create additional scenario tests as needed.

**Implementation details:**
- Test flow:
  1. `list_projects`
  2. `project_snapshot`
  3. `read_file`
  4. `run_command`
  5. `start_service`
  6. `get_logs`
  7. `http_request`
  8. `read_state_doc`

**Verification:**
- Full workflow passes on fixture project.

#### Task 11.3: harden errors and caps

**Objective:** Make failure behavior boring and reliable.

**Files:**
- Modify relevant modules and tests.

**Implementation details:**
- Finalize truncation rules.
- Finalize error codes.
- Audit path validation.
- Audit command policy.

**Verification:**
- All safety-related tests pass.

---

## Public contract checklist

Before calling v0.1 ready, verify that these public tools exist and use the final names only:

- `list_projects`
- `project_snapshot`
- `list_dir`
- `read_file`
- `write_file`
- `apply_patch`
- `move_path`
- `delete_path`
- `module_overview`
- `function_context`
- `grep`
- `find_references`
- `read_source`
- `recent_changes`
- `call_path`
- `watcher_health`
- `run_command`
- `get_job`
- `cancel_job`
- `list_services`
- `service_status`
- `start_service`
- `stop_service`
- `restart_service`
- `get_logs`
- `http_request`
- `list_probes`
- `run_probe`
- `git_status`
- `git_diff`
- `git_checkout`
- `git_commit`
- `read_state_doc`
- `write_state_doc`
- `patch_state_doc`

## Suggested implementation order if time is tight

If you want the fastest path to a compelling usable prototype, do it in this order:

1. repo bootstrap
2. config + models + result envelope
3. project registry + manifest
4. `list_projects`
5. `project_snapshot`
6. file tools
7. `run_command` + jobs
8. service lifecycle + logs + health
9. state-doc tools
10. semantic CodeGraph adapters
11. local HTTP, probes, git
12. Streamable HTTP MCP transport
13. end-to-end tests and hardening

## Definition of done for the first usable release

The first usable release is done when all of the following are true:

- a remote MCP client can connect over Streamable HTTP
- the client can enumerate projects via `list_projects`
- the client can inspect one project via `project_snapshot`
- the client can read and patch files with path safety enforced
- the client can run a bounded test command and inspect output
- the client can start, stop, restart, and inspect a declared service
- the client can read logs and verify health
- the client can use semantic code tools keyed by `project_id`
- the client can read and patch repo-local state docs
- the client can verify fixes with `http_request`
- structured error codes are stable and documented
- end-to-end tests cover the main agent loop

## Final recommendation

Don’t waste time trying to make the old CodeGraphAgent repo become the product. That path will drag old assumptions into the new public contract.

Build the new repo cleanly, keep CodeGraph as an internal engine, and make `project_id` plus `project_snapshot` the backbone of the whole system. That is the version that will actually feel good to external coding models.
