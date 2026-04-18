# Dev Workspace MCP — Project Onboarding + DB Connections

**Status:** proposal / next-implementation candidate  
**Repo:** `~/dev-workspaces/dev-workspace-mcp`

## What exists today

Grounded in the current codebase:
- project discovery is automatic under configured workspace roots (`dev_workspace_mcp/projects/discovery.py`)
- a folder is treated as a project if it has `.git` or `.devworkspace.yaml`
- canonical `project_id` comes from `.devworkspace.yaml` or falls back to folder name (`dev_workspace_mcp/projects/registry.py`)
- the public surface has `list_projects` and `project_snapshot`, but **no first-class project bootstrap/import flow yet**
- command execution is bounded and policy-gated (`dev_workspace_mcp/commands/service.py`)
- env passthrough is tightly bounded by `.devworkspace/policy.yaml` (`dev_workspace_mcp/policy/env.py`, `dev_workspace_mcp/policy/models.py`)
- default command allowlist does **not** include SSH or database CLIs (`dev_workspace_mcp/commands/allowlist.py`)

## Opinionated product stance

Do **not** make raw SSH the primary product abstraction for databases. That is too low-level and too leaky.

The right split is:
1. **project bootstrap** is first-class
2. **connection profiles** are first-class
3. **SSH tunneling** is an optional transport strategy for some connection profiles
4. raw `run_command` remains the escape hatch, not the main UX

## Desired onboarding flow

### Flow A — create a new empty workspace
Input:
- `folder_name`
- optional `project_id`
- optional `display_name`
- optional `git_init`
- optional template/profile (`python`, `node`, `generic`)

Behavior:
- create `~/dev-workspaces/<folder_name>`
- optionally `git init`
- write `.devworkspace.yaml`
- write `.devworkspace/memory.md`
- write `.devworkspace/tasks.md`
- write `.devworkspace/roadmap.md`
- write `.devworkspace/policy.yaml`
- return the created `project_id` plus recommended next commands

### Flow B — clone/import an existing GitHub repo
Input:
- `repo_url`
- optional `folder_name`
- optional `branch`
- optional `project_id`
- optional `display_name`

Behavior:
- clone repo into a workspace root
- if `.devworkspace.yaml` is missing, scaffold it
- persist canonical `project_id`
- return project summary + next steps

### Flow C — register an existing local folder
Input:
- `absolute_path` or project-root selection from a local picker
- optional `project_id`
- optional `display_name`

Behavior:
- validate the path lives under an allowed workspace root, or explicitly import it
- scaffold `.devworkspace.yaml` if missing
- do **not** copy the repo
- return the new project record

## Minimal new MCP/CLI surface

### 1. `bootstrap_project`
The main creation/import tool.

Suggested modes:
- `mode="create"`
- `mode="clone"`
- `mode="import"`

Suggested output:
- `project_id`
- `root_path`
- `created_files`
- `git_initialized` / `git_cloned`
- `manifest_path`
- `warnings`
- `recommended_next_tools`

### 2. `configure_connection`
Creates or updates a connection profile for a project.

### 3. `list_connections`
Returns safe metadata only — no secrets.

### 4. `test_connection`
Runs a bounded connectivity check using the configured profile.

### 5. later, not first wave: `open_tunnel` / `close_tunnel`
Only if SSH tunneling becomes common enough to deserve first-class lifecycle handling.

## Connection model

Add a tracked, non-secret project config surface for connections.

Best shape:
- tracked metadata in `.devworkspace.yaml` **or** `.devworkspace/connections.yaml`
- secrets in a local-only file such as `.devworkspace/agent.env`
- `.gitignore` should exclude the secret env file

### Suggested connection profile fields
- `name`
- `kind`: `postgres | mysql | redis | neo4j | falkordb | mongodb | generic_tcp`
- `mode`: `direct | ssh_tunnel`
- `host_env`
- `port_env`
- `database_env`
- `user_env`
- `password_env` / `token_env`
- `ssl_mode_env` (optional)
- `ssh_host_env` / `ssh_user_env` / `ssh_key_path_env` (for tunnel mode)
- `local_port` (optional override)
- `healthcheck`
- `recommended_client_command` (optional)

This keeps the manifest honest and portable while keeping secrets out of git.

## Why env references beat inline secrets

Because writing raw credentials into tracked YAML is dumb.

Use the tracked manifest to say **which env vars matter**, not their values. Example:
- `host_env: PGHOST`
- `password_env: PGPASSWORD`
- `token_env: NEO4J_PASSWORD`

Then the local-only env file or machine env provides the actual value.

## SSH stance

SSH should be treated as **one connection transport mode**, not the universal tool.

Good use cases:
- bastion-only DB access
- private VPC DBs
- temporary debugging tunnels

Bad use case:
- making every DB action be “just run some ssh commands manually”

That turns the MCP into a shitty shell wrapper instead of a product.

## What needs to change in policy/runtime

Current code blocks this flow by default unless we extend policy and allowlists.

Needed changes:
1. extend command allowlist to optionally permit:
   - `ssh`
   - `psql`
   - `mysql`
   - `redis-cli`
   - `mongosh`
   - `cypher-shell`
2. keep them policy-gated per project, not globally free-for-all
3. allow project env policy to whitelist DB-related env vars
4. keep redaction on stdout/stderr for secrets and auth headers
5. if tunnel mode exists, represent it as a service/job with explicit status

## Bootstrapping UX recommendation

### Phase 1 — CLI + MCP only
Do this first.

Why:
- current repo already has HTTP + stdio + CLI
- there is no real web UI surface today
- shipping a tiny web UI first would be architecture cosplay

### Phase 2 — thin local web UI
After CLI/MCP bootstrap works, add a tiny local UI for:
- create/import project
- edit manifest basics
- configure connection profiles
- test connectivity

That UI should call the same runtime/service layer. No duplicate business logic.

## Recommended implementation order

1. add bootstrap domain models
2. implement `bootstrap_project` in runtime + tool registry + CLI
3. persist canonical `project_id` into `.devworkspace.yaml`
4. scaffold default `.devworkspace/` files
5. add connection profile schema
6. implement `configure_connection`, `list_connections`, `test_connection`
7. add local-only secret env handling + gitignore rules
8. only then decide whether first-class SSH tunnel lifecycle is worth it

## Recommended first proof

The first honest proof is:
- create a fresh folder under `~/dev-workspaces`
- scaffold `.devworkspace.yaml` with explicit `project_id`
- show it appears in `list_projects`
- show `project_snapshot` reflects it
- add one safe connection profile with env references only
- run `test_connection` and return a clean success/failure envelope

## What not to do yet

- do not build a fat web UI first
- do not store DB passwords in tracked manifest files
- do not make arbitrary SSH the main onboarding story
- do not add database-specific query tools before connection bootstrap exists
- do not hide tunnel state inside magic shell commands with no lifecycle visibility

## Short version

The next real product slice should be:
- **first-class project bootstrap**
- **first-class connection profiles**
- **local-only secrets/env handling**
- **optional SSH tunnel mode**
- **web UI later, not first**
