# Dev Workspace MCP

A project-aware MCP server and small JSON-first CLI for coding agents.

> **Trusted-local only for now.** This repo is a local development workspace server, not a publicly hardened hosted product. Do **not** expose `serve-http` directly to the public internet or to untrusted users/browsers. It does **not** yet provide remote auth for public exposure, durable job/log storage across restarts, or the rest of the production-hardening work needed for multi-user/public deployment.

Dev Workspace MCP gives agents a safer, structured way to inspect, edit, run, and verify real development projects without treating raw SSH as the main interface.

## What it provides

- Project discovery through stable `project_id` values
- Project snapshots for agent bootstrapping
- Safe project-relative file reads, writes, moves, deletes, and patches
- Semantic code tools such as module overview, grep, references, source reads, recent changes, and call paths
- Policy-gated command execution and background jobs
- Declared development services with start, stop, restart, status, health, and logs
- Local HTTP verification and manifest-declared probes
- Local git helpers for status, diff, checkout, and commit
- Repo-local state files for memory, roadmap, and tasks
- MCP over Streamable HTTP or stdio
- A small CLI that uses the same runtime as the MCP tools

## Status

This is a working local development workspace server.

Implemented today:

- Streamable HTTP MCP transport
- stdio MCP transport
- project bootstrap: create, clone, import
- project snapshots
- safe file tools
- semantic code tools
- policy-aware command execution
- background jobs
- service lifecycle and logs
- probes and local HTTP checks
- local git tools
- direct connection profiles
- repo-local state documents
- small JSON-first CLI

Not implemented yet / still open:

- SSH tunnel lifecycle management
- GitHub issue, PR, review, or Actions tools
- persistent SQLite/BM25 search
- durable job/log storage across server restarts
- full CLI parity with every MCP tool
- remote/public authentication and authorization for hosted exposure
- remaining production-hardening work for public or multi-tenant deployment

## Install

```bash
python -m pip install -e '.[dev]'
```

The default workspace root is:

```text
~/dev-workspaces
```

Projects are discovered from workspace folders that contain either `.devworkspace.yaml` or `.git`.

After install, you can use either the `dev-workspace-mcp` console script or `python -m dev_workspace_mcp.app ...`. The examples below use `python -m` so they also work directly from the repo.

## Run

Inspect the server and available tools:

```bash
python -m dev_workspace_mcp.app describe
```

Start MCP over HTTP:

```bash
python -m dev_workspace_mcp.app serve-http --host 127.0.0.1 --port 8081 --path /mcp
```

The MCP endpoint is then:

```text
http://127.0.0.1:8081/mcp
```

Start MCP over stdio:

```bash
python -m dev_workspace_mcp.app stdio
```

Use the CLI:

```bash
python -m dev_workspace_mcp.app cli --json projects
```

## Quick CLI examples

Create, clone, or import a project:

```bash
python -m dev_workspace_mcp.app cli bootstrap create scratch-api --project-id scratch-api --git-init
python -m dev_workspace_mcp.app cli bootstrap clone https://github.com/example/service.git --project-id example-service
python -m dev_workspace_mcp.app cli bootstrap import ~/dev-workspaces/existing-app --project-id existing-app
```

Read project state:

```bash
python -m dev_workspace_mcp.app cli --json snapshot scratch-api
python -m dev_workspace_mcp.app cli --json read scratch-api README.md
python -m dev_workspace_mcp.app cli --json git status scratch-api
python -m dev_workspace_mcp.app cli --json memory read scratch-api
```

Run an allowed command and patch memory:

```bash
python -m dev_workspace_mcp.app cli --json run scratch-api -- python3 -c "print('hello')"
python -m dev_workspace_mcp.app cli --json memory patch scratch-api \
  --section "Current objective" "Ship a safe first production build."
```

Configure and test one tracked direct connection profile:

```bash
python -m dev_workspace_mcp.app cli connections configure scratch-api primary-db \
  --kind postgres \
  --host-env DB_HOST \
  --port-env DB_PORT \
  --database-env DB_NAME \
  --user-env DB_USER \
  --password-env DB_PASSWORD \
  --env DB_HOST=127.0.0.1 \
  --env DB_PORT=5432
python -m dev_workspace_mcp.app cli connections list scratch-api
python -m dev_workspace_mcp.app cli connections test scratch-api primary-db
```

Connection metadata lives in `.devworkspace.yaml`. Local values live in `.devworkspace/agent.env`, which should stay gitignored. `test_connection` / `connections test` only do a direct TCP smoke test today. SSH tunnel lifecycle is not implemented yet.

## Project manifest

Each project can define `.devworkspace.yaml`:

```yaml
name: Example Service
project_id: example-service
aliases:
  - service

codegraph:
  watch_paths:
    - src
    - tests

services:
  api:
    cwd: .
    start: ["python3", "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"]
    stop_signal: SIGTERM
    ports: [8000]
    health:
      type: http
      url: http://127.0.0.1:8000/health
      expect_status: 200

probes:
  tests:
    cwd: .
    argv: ["python3", "-m", "pytest", "-q"]
    timeout_sec: 60

presets:
  test: ["python3", "-m", "pytest", "-q"]

connections:
  local-db:
    kind: postgres
    transport: direct
    host_env: DB_HOST
    port_env: DB_PORT
    database_env: DB_NAME
    user_env: DB_USER
    password_env: DB_PASSWORD
    test:
      type: tcp
      timeout_sec: 3
```

## Command policy

Commands are denied by default unless the project allows them in `.devworkspace/policy.yaml`.

```yaml
version: 1

command_policy:
  default: deny
  commands:
    python3:
      allow_args:
        - ["-m", "pytest", "-q"]
        - ["-c"]
      max_seconds: 120
      max_output_bytes: 200000
    git:
      allow_args:
        - ["status", "--short"]
        - ["diff"]
      deny_args:
        - ["push"]
        - ["reset", "--hard"]

env:
  inherit: false
  allow:
    - PATH
    - HOME
    - LANG
  redact:
    - "*TOKEN*"
    - "*SECRET*"
    - "*PASSWORD*"

network:
  default: deny
  allow_localhost: true
  allowed_hosts: []
```

`allow_args` and `deny_args` match the command arguments after the executable name. For example, for `python3 -m pytest -q`, the policy pattern is `['-m', 'pytest', '-q']`.

## State files

Projects can keep explicit agent state in the repo:

```text
AGENTS.md
.devworkspace/memory.md
.devworkspace/roadmap.md
.devworkspace/tasks.md
.devworkspace/policy.yaml
.devworkspace/agent.env
```

Recommended use:

- `AGENTS.md`: durable project guidance for humans and agents
- `.devworkspace/memory.md`: current facts, decisions, and handoff notes
- `.devworkspace/tasks.md`: active work, blockers, and done items
- `.devworkspace/roadmap.md`: medium-term direction
- `.devworkspace/policy.yaml`: command, environment, path, and network policy
- `.devworkspace/agent.env`: local-only secrets and connection values

## Safety notes

- Treat this as trusted-local agent tooling, not a public SaaS or multi-tenant control plane.
- Do **not** assume the HTTP server is safe for direct public exposure. Remote/public auth is still an open gap.
- Keep HTTP bound to `127.0.0.1` unless you intentionally add your own network controls, auth, and proxy layer.
- Keep command policy at `default: deny` and allow only the specific commands you actually want agents to run.
- Keep `.devworkspace/agent.env` out of git.
- Job history and captured service logs are currently runtime-local and not durable across restarts.
- Review git diffs before commits or publishing.
- There are still production-hardening gaps beyond what this README documents. Do not market or deploy this as publicly hardened yet.
