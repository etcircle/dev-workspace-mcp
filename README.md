# Dev Workspace MCP

A project-aware MCP server for remote coding agents.

Dev Workspace MCP gives external LLMs and chat products like Claude, ChatGPT, Codex, and similar coding agents a structured way to understand, modify, run, and verify real development workspaces without falling back to raw SSH as the primary contract.

## Why this exists

Most remote coding setups are too shell-centric. That works, but it is noisy, brittle, and inefficient for models.

Dev Workspace MCP takes the better route:

- use standard MCP as the public interface
- make `project_id` the universal routing key
- expose code intelligence, files, commands, jobs, services, logs, probes, git, and state docs as structured tools
- keep long-running development services first-class
- keep repo-local agent state explicit and inspectable

The goal is a smooth end-to-end agent loop:

1. identify the project
2. inspect project and service state
3. inspect the relevant code
4. patch files
5. run tests or builds
6. restart services if needed
7. verify locally
8. update task state

## Core principles

### 1. Standard MCP, not a new protocol

This is a normal MCP server with:

- native Streamable HTTP transport
- native stdio transport
- an in-process JSON-first CLI that hits the same runtime/service layer

### 2. `project_id` is mandatory

Every project-scoped tool takes a `project_id`.

The model should not need to reason about arbitrary absolute machine paths. The server resolves project roots internally.

### 3. CodeGraph is an internal subsystem

CodeGraph-style semantic understanding is part of the solution, but not the public product boundary.

Public tools should expose a clean, model-friendly contract such as:

- `module_overview`
- `function_context`
- `grep`
- `find_references`
- `read_source`
- `recent_changes`
- `call_path`
- `watcher_health`

### 4. Services are first-class

Persistent backend/frontend dev processes are not just generic jobs.

They have:

- identity
- start/stop/restart semantics
- logs
- health checks
- restart counts
- ports
- captured status

### 5. Repo-local state matters

Each project should support explicit local state files:

- `AGENTS.md`
- `.devworkspace/memory.md`
- `.devworkspace/roadmap.md`
- `.devworkspace/tasks.md`

This gives cross-session continuity without hiding state in black-box memory.

### 6. Descriptive tool names beat faux-Unix naming

Public tool names should be explicit and model-native:

- `read_file`, not `cat`
- `run_command`, not `sh`
- `get_logs`, not `tail`
- `http_request`, not `curl`

If shell familiarity helps, that belongs in MCP titles/descriptions, not in a vague public contract.

## High-level architecture

```text
dev-workspace-mcp/
  README.md
  AGENTS.md
  pyproject.toml

  dev_workspace_mcp/
    app.py
    config.py

    mcp_server/
    projects/
    codegraph/
    files/
    commands/
    services/
    state_docs/
    gittools/
    http_tools/
    probes/
    shared/

  tests/
```

### Main subsystems

#### `mcp_server/`
Owns server bootstrap, tool registration, HTTP transport, and result formatting.

#### `projects/`
Owns project discovery, registration, manifest parsing, alias resolution, and snapshot assembly.

#### `codegraph/`
Owns semantic code understanding adapters and watcher/index management.

#### `files/`
Owns safe project-relative filesystem access and patching.

#### `commands/`
Owns bounded command execution and background job tracking.

#### `services/`
Owns service lifecycle, logs, health checks, and restart semantics.

#### `state_docs/`
Owns `.devworkspace/*.md` read/write/patch operations and size limits.

#### `gittools/`
Owns routine git operations under a structured contract.

#### `http_tools/`
Owns local HTTP verification for backends and frontends.

#### `probes/`
Owns named diagnostics declared by the project manifest.

## Project model

Every project is represented by a stable server-side record:

- `project_id`: canonical slug, required
- `display_name`: human-readable name
- `root_path`: resolved absolute path on the server
- `manifest_path`: optional path to `.devworkspace.yaml`
- `aliases`: optional alternate names
- `services`: declared service definitions
- `probes`: declared diagnostic probes
- `presets`: declared command presets
- `codegraph`: semantic indexing/watch configuration

Recommended rule:

- if `.devworkspace.yaml` defines `project_id`, that is canonical
- otherwise derive from folder name on first registration and persist it

## Public MCP tool surface

### Project tools
- `bootstrap_project`
- `list_projects`
- `project_snapshot`

### File tools
- `list_dir`
- `read_file`
- `write_file`
- `apply_patch`
- `move_path`
- `delete_path`

### Semantic code tools
- `module_overview`
- `function_context`
- `grep`
- `find_references`
- `read_source`
- `recent_changes`
- `call_path`
- `watcher_health`

### Command and job tools
- `run_command`
- `get_job`
- `cancel_job`

### Service tools
- `list_services`
- `service_status`
- `start_service`
- `stop_service`
- `restart_service`
- `get_logs`

### HTTP and probe tools
- `http_request`
- `list_probes`
- `run_probe`

### Connection tools
- `list_connections`
- `configure_connection`
- `test_connection`

### Git tools
- `git_status`
- `git_diff`
- `git_checkout`
- `git_commit`

### State document tools
- `read_state_doc`
- `write_state_doc`
- `patch_state_doc`

## CodeGraph adapter mapping

Internal semantic handlers can be adapted behind the public names:

- `get_module_overview` -> `module_overview`
- `get_function_context` -> `function_context`
- `grep_code` -> `grep`
- `find_references` -> `find_references`
- `get_file_content` -> `read_source`
- `diff_since` -> `recent_changes`
- `explain_path` -> `call_path`
- `get_watcher_health` -> `watcher_health`

Do not expose the old names and the new names together. Pick one public contract and stick to it.

## State documents

### `AGENTS.md`
Human-owned, durable repo guidance.

Use for:
- repo purpose
- key directories
- test/build/run commands
- conventions
- operational rules
- definition of done

### `.devworkspace/memory.md`
Current truth and handoff notes.

Recommended max size: 4,000 chars.

### `.devworkspace/roadmap.md`
Medium-term direction and major decisions.

Recommended max size: 8,000 chars.

### `.devworkspace/tasks.md`
Active execution state.

Recommended max size: 8,000 chars.

## Quick start

```bash
python -m pip install -e '.[dev]'
python -m dev_workspace_mcp.app describe
python -m dev_workspace_mcp.app serve-http --host 127.0.0.1 --port 8081 --path /mcp
# or
python -m dev_workspace_mcp.app stdio
# or
python -m dev_workspace_mcp.app cli projects
```

The native MCP HTTP endpoint is then available at:

```text
http://127.0.0.1:8081/mcp
```

CLI notes:

- `dev-workspace-mcp cli` returns the same stable JSON result envelope as the MCP tools.
- output is compact JSON by default
- `--json` pretty-prints the same envelope for humans
- current CLI parity slice is intentionally small and honest:
  - `projects`
  - `bootstrap create <folder_name> [--project-id ...] [--display-name ...] [--git-init]`
  - `bootstrap clone <repo_url> [--branch ...] [--project-id ...] [--display-name ...]`
  - `bootstrap import <path> [--project-id ...] [--display-name ...]`
  - `snapshot <project_id>`
  - `read <project_id> <path>`
  - `run <project_id> -- ...`
  - `connections list <project_id>`
  - `connections configure <project_id> <connection_name> --kind ... --host-env ... --port-env ... [--env KEY=VALUE ...]`
  - `connections test <project_id> <connection_name>`
  - `git status <project_id>`
  - `memory read <project_id>`
  - `memory patch <project_id> --section ...`

Quick CLI examples:

```bash
# create / clone / import
python -m dev_workspace_mcp.app cli bootstrap create scratch-api --project-id scratch-api --git-init
python -m dev_workspace_mcp.app cli bootstrap clone https://github.com/example/service.git --project-id example-service
python -m dev_workspace_mcp.app cli bootstrap import ~/dev-workspaces/existing-app --project-id existing-app

# track one direct connection profile
python -m dev_workspace_mcp.app cli connections configure di-copilot primary-db \
  --kind postgres \
  --host-env DB_HOST \
  --port-env DB_PORT \
  --database-env DB_NAME \
  --user-env DB_USER \
  --password-env DB_PASSWORD \
  --env DB_HOST=127.0.0.1 \
  --env DB_PORT=5432

python -m dev_workspace_mcp.app cli connections list di-copilot
python -m dev_workspace_mcp.app cli connections test di-copilot primary-db
```

Tracked connection profiles store env variable names in `.devworkspace.yaml`. Local values live in `.devworkspace/agent.env` and are gitignored.
`test_connection` / `connections test` only do a direct TCP dial today. SSH tunnel lifecycle is not implemented in this wave.

## Manifest example

```yaml
name: DI Copilot
project_id: di-copilot
aliases:
  - dicopilot

codegraph:
  watch_paths:
    - backend
    - frontend

services:
  backend:
    cwd: backend
    start: ["uv", "run", "uvicorn", "app.main:app", "--reload", "--port", "8000"]
    stop_signal: SIGTERM
    ports: [8000]
    health:
      type: http
      url: http://127.0.0.1:8000/health
      expect_status: 200

  frontend:
    cwd: frontend
    start: ["pnpm", "dev", "--port", "3000"]
    stop_signal: SIGTERM
    ports: [3000]
    health:
      type: http
      url: http://127.0.0.1:3000/
      expect_status: 200

probes:
  backend_db:
    cwd: backend
    argv: ["python", "-m", "scripts.check_db"]
    timeout_sec: 30

presets:
  test_backend: ["pytest", "-q"]
  test_frontend: ["pnpm", "test"]
  build_frontend: ["pnpm", "build"]

connections:
  primary_db:
    kind: postgres
    transport: direct
    host_env: DB_HOST
    port_env: DB_PORT
    database_env: DB_NAME
    user_env: DB_USER
    password_env: DB_PASSWORD
    ssl_mode_env: DB_SSLMODE
    test:
      type: tcp
      timeout_sec: 3
```

The manifest tracks connection profile metadata and env var names only. Put local values in `.devworkspace/agent.env`, not in `.devworkspace.yaml`.

## Safety model

This server should not be a remote footgun.

Required safeguards:

- all file paths validated and constrained to the resolved project root
- no arbitrary absolute-path writes
- command execution uses `argv[]`, not free-form shell strings, by default
- allowed binaries can be policy-gated
- only declared services can be controlled through service tools
- only declared probes can be run through probe tools
- file read and log output sizes are capped
- state document limits are enforced
- structured domain errors are returned with stable codes

Example error codes:

- `PROJECT_NOT_FOUND`
- `INVALID_PATH`
- `SERVICE_NOT_FOUND`
- `JOB_NOT_FOUND`
- `STATE_DOC_LIMIT_EXCEEDED`
- `COMMAND_NOT_ALLOWED`
- `WATCHER_UNAVAILABLE`

## Recommended first-call workflow

For most debugging and implementation tasks, the model should start here:

1. `list_projects`
2. `project_snapshot(project_id=...)`
3. `service_status(project_id=..., service_name=...)`
4. `get_logs(project_id=..., service_name=...)`
5. semantic code tools like `grep`, `module_overview`, `function_context`
6. `apply_patch` or `write_file`
7. `run_command`
8. `restart_service`
9. `http_request` or `service_status` again to verify
10. `patch_state_doc(kind="tasks")` or `patch_state_doc(kind="memory")`

If `project_snapshot` is good, the entire agent experience gets dramatically better.

## `project_snapshot` boot packet

`project_snapshot` is no longer just a light project summary. It is meant to be the agent's boot packet.

Current fields include:

- project record and git summary
- policy summary
- declared services with runtime status, health summary, ports, and start command
- watcher/index summary
- recent changed files
- probes and presets
- state-doc existence plus short previews
- stack summary:
  - `languages`
  - `frameworks`
  - `package_managers`
- repo guidance summary from `AGENTS.md`
- short memory summary from `.devworkspace/memory.md`
- active task summary from `.devworkspace/tasks.md`
- recommended commands
- recommended next tools
- explicit capability summary

Honesty rules matter here:

- watcher metadata may be snapshot-backed even when there is no real filesystem watcher backend yet
- grep + in-memory codegraph snapshots are useful, but they are not a persistent search service
- GitHub helpers should not be implied if the repo only exposes local git tools today
- if git status, watcher refresh, or state-doc reads fail, snapshot should degrade with warnings instead of lying or crashing

## Historical build order

### Phase 1
- create repo skeleton
- define core models and result envelope
- implement project registry and manifest loading
- implement `list_projects`
- implement `project_snapshot` skeleton

### Phase 2
- port/adapt CodeGraph semantic handlers
- implement watcher health integration

### Phase 3
- implement file tools
- implement command execution and jobs

### Phase 4
- implement services, logs, and health checks

### Phase 5
- implement state-doc tools

### Phase 6
- implement git, HTTP verification, and probes

### Phase 7
- expose native Streamable HTTP transport
- add auth, richer MCP metadata, and end-to-end transport tests

## Non-goals

At least for the first cut, this should not try to be:

- a generic SSH replacement platform
- a full browser automation system
- a database admin tunnel
- a Kubernetes control plane
- an everything-agent

The job is much simpler: be an excellent remote development workspace MCP server.

## Status

This repository now has a working local implementation of:

- project bootstrap (`bootstrap_project`) for create / clone / import flows
- project discovery, alias resolution, and richer project snapshots
- policy-aware path safety, environment filtering, and local-network restrictions
- first semantic code tools (`module_overview`, `function_context`, `grep`, `find_references`, `read_source`, `recent_changes`, `call_path`, `watcher_health`)
- an in-process codegraph boundary that keeps the public MCP contract stable while we port useful CodeGraph logic directly into this repo
- safe file tools
- state-doc tools
- bounded commands and jobs
- service lifecycle, logs, and health checks
- git tools
- local HTTP verification
- manifest-declared probes
- tracked direct connection profiles in `.devworkspace.yaml`
- local connection/env values in `.devworkspace/agent.env`
- direct TCP smoke testing for tracked connections
- native Streamable HTTP MCP transport wiring
- native stdio MCP transport wiring
- a small in-process JSON-first CLI parity slice, including bootstrap and connection helpers
- a `project_snapshot` boot packet that summarizes stack, repo guidance, memory, active tasks, services, and honest capability limits

What is not here yet:

- SSH tunnel lifecycle management is not implemented yet.
- Connection testing is direct-only today; no tunnel bring-up/tear-down happens behind the scenes.

The next document to read should be:

- `docs/implementation-plan.md`
